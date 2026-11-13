"""PPL-QUIESCENCE-01 lot C1b — module tests (contract C1b v0).

Hermetic: synthetic data, temp dirs only, no network, no exchange, no Telegram,
no Advisor.  Child processes are fresh interpreters with bounded waits and
kill+wait cleanup.  Process scenarios with the external witness (lot B) live in
``test_ppl_quiescence_c1b_process.py``.

Naming follows the matrix of plan A3 §6 (B4, B9d, B11a-c, L2-L4, L6, L7);
``test_shutdown_*`` cover the typed outcomes (exigence 2) and ``test_ex1_*``
the late monitor writes (exigence 1, in-process half).
"""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from paper_trading import ppl_quiescence_c1b as c1b
from paper_trading import ppl_quiescence_proof as qp
from paper_trading.admission_ledger import reset_admission_ledger_singleton
from paper_trading.durable_event_store import DurableEventStore
from paper_trading.mexc_simulator import MexcSimulator
from paper_trading.paper_authority import PaperLifecycleAuthority
from paper_trading.ppl_admission_gate import AdmissionGate
from paper_trading.ppl_authority_runtime import (
    EpochRotationQuiescence,
    PPLAuthorityRuntime,
    authority_manifest_sha256,
    build_experiment_manifest,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = 2_000_000_000.0
EPOCH = "C1B-TEST-EPOCH"
CODE = "cb" * 20

pytestmark = pytest.mark.skipif(
    not Path("/proc/self/stat").exists(), reason="requires Linux /proc"
)


# ----------------------------------------------------------------- fixtures


def _manifest(code_sha: str = CODE):
    return build_experiment_manifest(
        paper_epoch_id=EPOCH,
        created_at=1.0,
        initial_virtual_capital=1000.0,
        code_sha=code_sha,
        config_snapshot_hash="cfg-hash-c1b",
        legacy_log_bytes=b"",
        quiescence=EpochRotationQuiescence(0, 0, 0, True),
        predecessor_authority_epoch_id="PRED-EPOCH",
    )


def _open_gate(gate: AdmissionGate) -> None:
    """Test-only synthesis of a chained OPEN record (as in the C1a tests): a
    real ``open()`` needs a succession clearance, which C1b never produces."""
    with gate._locked():
        gate._append(
            {
                "seq": 1,
                "prev_sha256": "0" * 64,
                "action": "OPEN",
                "paper_epoch_id": gate.paper_epoch_id,
                "manifest_sha256": gate.manifest_sha256,
                "decision_sha256": "d" * 64,
                "clearance_proof_sha256": "e" * 64,
                "decided_by": "test-c1b",
                "reason": "",
            }
        )
    assert gate.state() == "OPEN"


def _evidence(sha: str = CODE, worktree: str = "CLEAN"):
    return SimpleNamespace(source_sha=sha, worktree_state=worktree)


class Layout:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.authority_root = tmp / "authority"
        self.gate_dir = tmp / "gate"
        self.gate_dir.mkdir()
        self.gate_journal = self.gate_dir / "gate.jsonl"
        self.proof_dir = tmp / "proofs"
        self.proof_dir.mkdir()
        self.lock_dir = tmp / "run"
        self.lock_dir.mkdir()
        self.identity_lock = self.lock_dir / "advisor.identity.lock"
        self.legacy_lock = tmp / "logs" / "advisor.lock"

    def env(self, **over) -> dict[str, str]:
        env = {
            c1b.ENV_GATE_JOURNAL: str(self.gate_journal),
            c1b.ENV_PROOF_DIR: str(self.proof_dir),
            c1b.ENV_IDENTITY_LOCK: str(self.identity_lock),
            "PPL_AUTHORITY_STORE_ROOT": str(self.authority_root),
        }
        env.update(over)
        return {k: v for k, v in env.items() if v is not None}


@pytest.fixture
def layout(tmp_path):
    return Layout(tmp_path)


@pytest.fixture(autouse=True)
def _isolated_admission_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_ADMISSION_LEDGER", str(tmp_path / "admission.jsonl"))
    reset_admission_ledger_singleton()
    yield
    reset_admission_ledger_singleton()


_children: list[subprocess.Popen] = []
_prepared: list[c1b.C1bPrepared] = []


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    for prep in _prepared:
        prep.signals.restore()
        prep.identity_lock.close()
    _prepared.clear()
    for proc in _children:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            pass
    _children.clear()


def _prepare(layout: Layout, **over) -> c1b.C1bPrepared:
    prep = c1b.prepare_from_env(
        layout.env(**over), legacy_lock_path=str(layout.legacy_lock)
    )
    assert prep is not None
    _prepared.append(prep)
    return prep


class World:
    """Real authority runtime + C1a simulator wired through ``bind_wiring``."""

    def __init__(self, layout: Layout, *, open_gate: bool = True) -> None:
        self.layout = layout
        self.manifest = _manifest()
        self.manifest_sha = authority_manifest_sha256(self.manifest)
        self.store = DurableEventStore(layout.authority_root)
        self.runtime = PPLAuthorityRuntime(manifest=self.manifest, store=self.store)
        state = self.runtime.bind(now=NOW)
        if open_gate:
            _open_gate(
                AdmissionGate(
                    layout.gate_journal,
                    paper_epoch_id=EPOCH,
                    manifest_sha256=self.manifest_sha,
                )
            )
        self.prepared = _prepare(layout)
        self.wiring = c1b.bind_wiring(
            self.prepared,
            SimpleNamespace(ppl_is_authoritative=True),
            self.runtime,
            capture_fn=_evidence,
        )
        self.notes: list[str] = []
        self.sim = MexcSimulator(
            telegram_fn=self.notes.append,
            lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
            authority_runtime=self.runtime,
            **self.wiring.simulator_kwargs(),
        )
        self.sim._capital = state.available_cash
        self.sim._initial_capital = 1000.0

    def buy(self, symbol: str = "BTC/USDT", price: float = 100.0):
        return self.sim.place_market_order(symbol, "BUY", 10.0, current_price=price)

    def close(self, symbol: str = "BTC/USDT", price: float = 101.0):
        self.sim._close_position(symbol, price, "TP")

    def ledger_sha(self) -> str:
        import hashlib

        return hashlib.sha256(self.store._epoch_path(EPOCH).read_bytes()).hexdigest()

    def shutdown(self, **kw) -> c1b.ShutdownOutcome:
        return c1b.shutdown_proof(
            self.wiring,
            self.sim,
            self.runtime,
            process_instance_id="inst-c1b",
            **kw,
        )

    def proofs(self) -> qp.ProofStore:
        return qp.ProofStore(
            self.layout.proof_dir, forbidden_roots=[self.layout.authority_root]
        )

    def assess(self, now: float | None = None) -> qp.Assessment:
        return qp.assess(
            self.proofs(),
            manifest=self.manifest,
            manifest_sha256=self.manifest_sha,
            store_root=self.layout.authority_root,
            now=time.time() if now is None else now,
            max_age_s=900.0,
        )


def _py(code: str, *args: str, timeout: float = 30.0) -> subprocess.CompletedProcess:
    script = f"import sys; sys.path.insert(0, {str(ROOT)!r})\n" + textwrap.dedent(code)
    return subprocess.run(
        [sys.executable, "-I", "-c", script, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


# ------------------------------------------- L3 (and L4, L7): configuration


def test_l3_no_variable_means_c1b_off(layout):
    env = {"PPL_AUTHORITY_STORE_ROOT": str(layout.authority_root)}
    assert c1b.c1b_requested(env) is False
    assert c1b.load_c1b_config(env) is None
    assert c1b.prepare_from_env(env) is None
    assert c1b.c1b_requested({c1b.ENV_PROOF_DIR: "   "}) is False


@pytest.mark.parametrize("missing", c1b.C1B_ENV_VARS)
def test_l3_partial_configuration_is_refused(layout, missing):
    env = layout.env(**{missing: None})
    assert c1b.c1b_requested(env) is True
    with pytest.raises(c1b.C1bConfigRefusal, match="partial C1b configuration"):
        c1b.load_c1b_config(env)


def test_l3_single_variable_is_refused(layout):
    with pytest.raises(c1b.C1bConfigRefusal, match="partial"):
        c1b.load_c1b_config({c1b.ENV_IDENTITY_LOCK: str(layout.identity_lock)})


@pytest.mark.parametrize("var", c1b.C1B_ENV_VARS)
@pytest.mark.parametrize("bad", ["relative/path", "/abs/../escape"])
def test_l3_paths_must_be_absolute_without_dotdot(layout, var, bad):
    with pytest.raises(c1b.C1bConfigRefusal):
        c1b.load_c1b_config(layout.env(**{var: bad}))


def test_l3_symlink_component_is_refused(layout):
    real = layout.tmp / "real-proofs"
    real.mkdir()
    link = layout.tmp / "link-proofs"
    link.symlink_to(real)
    with pytest.raises(c1b.C1bConfigRefusal, match="symbolic link"):
        c1b.load_c1b_config(layout.env(**{c1b.ENV_PROOF_DIR: str(link)}))
    parent_link = layout.tmp / "linkdir"
    parent_link.symlink_to(layout.lock_dir)
    with pytest.raises(c1b.C1bConfigRefusal, match="symbolic link"):
        c1b.load_c1b_config(
            layout.env(**{c1b.ENV_IDENTITY_LOCK: str(parent_link / "id.lock")})
        )


def test_l3_wrong_file_types_are_refused(layout):
    (layout.tmp / "jdir").mkdir()
    with pytest.raises(c1b.C1bConfigRefusal, match="wrong file type"):
        c1b.load_c1b_config(
            layout.env(**{c1b.ENV_GATE_JOURNAL: str(layout.tmp / "jdir")})
        )
    (layout.tmp / "pfile").write_text("")
    with pytest.raises(c1b.C1bConfigRefusal, match="wrong file type"):
        c1b.load_c1b_config(
            layout.env(**{c1b.ENV_PROOF_DIR: str(layout.tmp / "pfile")})
        )
    (layout.tmp / "ldir").mkdir()
    with pytest.raises(c1b.C1bConfigRefusal, match="wrong file type"):
        c1b.load_c1b_config(
            layout.env(**{c1b.ENV_IDENTITY_LOCK: str(layout.tmp / "ldir")})
        )


def test_l3_identity_lock_parent_must_exist_and_nothing_is_created(layout):
    target = layout.tmp / "absent" / "deeper" / "id.lock"
    with pytest.raises(c1b.C1bConfigRefusal, match="parent directory does not exist"):
        c1b.load_c1b_config(layout.env(**{c1b.ENV_IDENTITY_LOCK: str(target)}))
    assert not (layout.tmp / "absent").exists()


def test_l3_validation_creates_nothing(layout):
    env = layout.env(
        **{
            c1b.ENV_GATE_JOURNAL: str(layout.tmp / "g2" / "gate.jsonl"),
            c1b.ENV_PROOF_DIR: str(layout.tmp / "p2"),
        }
    )
    before = sorted(p.name for p in layout.tmp.iterdir())
    cfg = c1b.load_c1b_config(env)
    assert cfg is not None
    assert sorted(p.name for p in layout.tmp.iterdir()) == before
    assert not layout.identity_lock.exists()


@pytest.mark.parametrize(
    "over",
    [
        {c1b.ENV_PROOF_DIR: "{gate}"},
        {c1b.ENV_PROOF_DIR: "{gate}/proofs"},
        {c1b.ENV_IDENTITY_LOCK: "{gate}/id.lock"},
        {c1b.ENV_IDENTITY_LOCK: "{proofs}/id.lock"},
        {"PPL_AUTHORITY_STORE_ROOT": "{proofs}"},
        {"PPL_AUTHORITY_STORE_ROOT": "{tmp}"},
        {c1b.ENV_GATE_JOURNAL: "{authority}/gate.jsonl"},
        {"PAPER_TRADE_LOG": "{proofs}/trades.jsonl"},
    ],
)
def test_l3_overlapping_areas_are_refused(layout, over):
    subst = {
        "gate": str(layout.gate_dir),
        "proofs": str(layout.proof_dir),
        "tmp": str(layout.tmp),
        "authority": str(layout.authority_root),
    }
    (layout.authority_root).mkdir(exist_ok=True)
    env = layout.env(**{k: v.format(**subst) for k, v in over.items()})
    with pytest.raises(c1b.C1bConfigRefusal, match="overlaps"):
        c1b.load_c1b_config(env)


def test_l3_identity_lock_cannot_be_the_legacy_advisor_lock(layout):
    layout.legacy_lock.parent.mkdir()
    env = layout.env(**{c1b.ENV_IDENTITY_LOCK: str(layout.legacy_lock)})
    with pytest.raises(c1b.C1bConfigRefusal, match="legacy advisor lock"):
        c1b.load_c1b_config(env, legacy_lock_path=str(layout.legacy_lock))


def _code_without_docstrings():
    import ast

    tree = ast.parse((ROOT / "paper_trading" / "ppl_quiescence_c1b.py").read_text())
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(body, list)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(getattr(body[0], "value", None), ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body[0] = ast.Pass()
    return tree


def test_l4_module_reads_no_strategy_or_capital_variable():
    import ast

    code = ast.unparse(_code_without_docstrings())
    for forbidden in (
        "PB_MAX_POSITIONS",
        "epoch_role",
        "WALLET_PAPER_CAPITAL",
        "FEATURE_AUTO_CALIBRATION",
        "telegram",
        "clearance",
        "VERIFIED",
        "ATTESTED",
    ):
        assert forbidden not in code, forbidden


def test_l7_module_never_drives_the_gate():
    """Role neutrality (D-C1b-7): no call to open/close/drain on any object
    other than ``os`` file descriptors."""
    import ast

    for node in ast.walk(_code_without_docstrings()):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("open", "close", "drain_barrier", "admission_hold"):
                owner = ast.unparse(node.func.value)
                assert owner in ("os", "lock"), ast.unparse(node)


# -------------------------------------- B9d + exigence 3: identity lock


def test_b9d_lock_acquire_creates_private_file_never_written(layout):
    lock = c1b.IdentityLock.acquire(layout.identity_lock)
    try:
        info = os.lstat(layout.identity_lock)
        assert stat.S_ISREG(info.st_mode)
        assert stat.S_IMODE(info.st_mode) & 0o077 == 0
        assert info.st_size == 0
        assert lock.verify() == (True, "")
        assert (info.st_dev, info.st_ino) == lock.identity[:2]
    finally:
        lock.close()
    assert layout.identity_lock.stat().st_size == 0


def test_b9d_lock_second_acquirer_in_same_process_is_refused(layout):
    first = c1b.IdentityLock.acquire(layout.identity_lock)
    try:
        with pytest.raises(c1b.C1bIdentityRefusal, match="held by another process"):
            c1b.IdentityLock.acquire(layout.identity_lock)
        assert first.verify() == (True, "")
    finally:
        first.close()


_ACQUIRE_CHILD = """
import json, os, sys, time
from paper_trading import ppl_quiescence_c1b as c1b
path, go, hold = sys.argv[1], sys.argv[2], float(sys.argv[3])
while not os.path.exists(go):
    time.sleep(0.001)
try:
    lock = c1b.IdentityLock.acquire(path)
except c1b.C1bIdentityRefusal as exc:
    print(json.dumps({"won": False, "why": str(exc)}), flush=True)
    sys.exit(0)
print(json.dumps({"won": True, "ino": lock.identity[1]}), flush=True)
time.sleep(hold)
"""


def test_b9d_lock_concurrent_acquirers_exactly_one_wins(layout):
    go = layout.tmp / "go"
    procs = []
    for _ in range(8):
        script = f"import sys; sys.path.insert(0, {str(ROOT)!r})\n" + textwrap.dedent(
            _ACQUIRE_CHILD
        )
        proc = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-c",
                script,
                str(layout.identity_lock),
                str(go),
                "3",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _children.append(proc)
        procs.append(proc)
    time.sleep(0.5)  # let the interpreters start; the race is on the go file
    go.write_text("")
    results = []
    for proc in procs:
        out, err = proc.communicate(timeout=30)
        assert proc.returncode == 0, err
        results.append(json.loads(out.strip().splitlines()[0]))
    winners = [r for r in results if r["won"]]
    assert len(winners) == 1, results
    assert all("held by another process" in r["why"] for r in results if not r["won"])
    assert winners[0]["ino"] == os.lstat(layout.identity_lock).st_ino


def test_b9d_lock_lock_is_released_by_kernel_when_holder_is_killed(layout):
    go = layout.tmp / "go"
    go.write_text("")
    script = f"import sys; sys.path.insert(0, {str(ROOT)!r})\n" + textwrap.dedent(
        _ACQUIRE_CHILD
    )
    proc = subprocess.Popen(
        [sys.executable, "-I", "-c", script, str(layout.identity_lock), str(go), "60"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _children.append(proc)
    line = proc.stdout.readline()
    assert json.loads(line)["won"] is True
    with pytest.raises(c1b.C1bIdentityRefusal):
        c1b.IdentityLock.acquire(layout.identity_lock)
    proc.send_signal(signal.SIGKILL)
    proc.wait(timeout=10)
    lock = c1b.IdentityLock.acquire(layout.identity_lock)  # same inode, now free
    try:
        assert lock.verify() == (True, "")
    finally:
        lock.close()


def test_b9d_lock_unlink_and_recreate_is_detected_as_replacement(layout):
    lock = c1b.IdentityLock.acquire(layout.identity_lock)
    try:
        layout.identity_lock.unlink()
        assert lock.verify() == (False, "identity lock path removed")
        layout.identity_lock.write_text("")
        os.chmod(layout.identity_lock, 0o600)
        ok, why = lock.verify()
        assert ok is False and "replaced" in why
        # the newcomer can be locked by someone else: two "owners" would exist,
        # which is exactly why the shutdown proof refuses (IDENTITY_LOCK_CHANGED).
        other = c1b.IdentityLock.acquire(layout.identity_lock)
        other.close()
    finally:
        lock.close()


def test_b9d_lock_rename_over_is_detected(layout):
    lock = c1b.IdentityLock.acquire(layout.identity_lock)
    try:
        other = layout.lock_dir / "other"
        other.write_text("")
        os.replace(other, layout.identity_lock)
        ok, why = lock.verify()
        assert ok is False and "replaced" in why
    finally:
        lock.close()


@pytest.mark.parametrize("mutate", ["chmod", "touch", "write"])
def test_b9d_lock_metadata_change_is_detected(layout, mutate):
    lock = c1b.IdentityLock.acquire(layout.identity_lock)
    try:
        time.sleep(0.01)
        if mutate == "chmod":
            os.chmod(layout.identity_lock, 0o400)
        elif mutate == "touch":
            os.utime(layout.identity_lock, ns=(1, 1))
        else:
            with open(layout.identity_lock, "a") as fh:
                fh.write("x")
        ok, why = lock.verify()
        assert ok is False and "metadata changed" in why
    finally:
        lock.close()


def test_b9d_lock_symlink_at_lock_path_is_refused(layout):
    target = layout.lock_dir / "target"
    target.write_text("")
    os.chmod(target, 0o600)
    layout.identity_lock.symlink_to(target)
    with pytest.raises(c1b.C1bIdentityRefusal, match="cannot be opened"):
        c1b.IdentityLock.acquire(layout.identity_lock)
    with pytest.raises(c1b.C1bConfigRefusal, match="symbolic link"):
        c1b.load_c1b_config(layout.env())


def test_b9d_lock_group_or_world_writable_lock_is_refused(layout):
    layout.identity_lock.write_text("")
    os.chmod(layout.identity_lock, 0o620)
    with pytest.raises(c1b.C1bIdentityRefusal, match="writable by group or others"):
        c1b.IdentityLock.acquire(layout.identity_lock)


def test_b9d_lock_non_regular_lock_is_refused(layout):
    fifo = layout.lock_dir / "fifo"
    os.mkfifo(fifo, 0o600)
    with pytest.raises(c1b.C1bIdentityRefusal):
        c1b.IdentityLock.acquire(fifo)
    (layout.lock_dir / "d").mkdir()
    with pytest.raises(c1b.C1bIdentityRefusal, match="cannot be opened"):
        c1b.IdentityLock.acquire(layout.lock_dir / "d")


def test_b9d_lock_lock_is_independent_from_legacy_advisor_lock(layout):
    """The legacy ``logs/advisor.lock`` is truncated and deleted by the Advisor
    and read as a PID file elsewhere; the identity lock does not depend on it."""
    layout.legacy_lock.parent.mkdir()
    layout.legacy_lock.write_text("12345")
    lock = c1b.IdentityLock.acquire(layout.identity_lock)
    try:
        layout.legacy_lock.write_text("")
        layout.legacy_lock.unlink()
        assert lock.verify() == (True, "")
    finally:
        lock.close()


def test_b9d_lock_lock_fd_is_the_one_probed_by_process_identity(layout):
    lock = c1b.IdentityLock.acquire(layout.identity_lock)
    try:
        ident = qp.current_process_identity(
            process_instance_id="inst", lock_path=str(lock.path), lock_fd=lock.fd
        )
        rendered = json.dumps(ident)
        assert str(lock.identity[1]) in rendered
    finally:
        lock.close()


# ---------------------------------------------------------------- signals


def test_sig_handlers_only_record_the_first_signal(layout):
    prep = _prepare(layout)
    assert prep.signals.requested is False
    os.kill(os.getpid(), signal.SIGTERM)
    assert prep.signals.wait(5.0) is True
    assert prep.signals.signum == signal.SIGTERM
    os.kill(os.getpid(), signal.SIGINT)  # no KeyboardInterrupt in C1b mode
    assert prep.signals.signum == signal.SIGTERM  # the first signal received wins


def test_sig_sigint_first_selects_the_existing_manual_stop_message(layout):
    prep = _prepare(layout)
    os.kill(os.getpid(), signal.SIGINT)
    assert prep.signals.wait(5.0) is True
    assert prep.signals.signum == signal.SIGINT


def _tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def test_r2_class1_secondary_thread_with_absent_lock_refuses_and_tree_unchanged(layout):
    """R2: the main-thread precondition is checked before the identity lock is
    opened, so a refusal from a secondary thread creates nothing."""
    assert not layout.identity_lock.exists()
    before = _tree(layout.tmp)
    box: dict = {}

    def run():
        try:
            c1b.prepare_from_env(layout.env())
        except BaseException as exc:  # noqa: BLE001
            box["exc"] = exc

    th = threading.Thread(target=run)
    th.start()
    th.join(20)
    assert not th.is_alive()
    assert isinstance(box.get("exc"), c1b.C1bConfigRefusal)
    assert "main thread" in str(box["exc"])
    assert _tree(layout.tmp) == before
    assert not layout.identity_lock.exists()
    assert signal.getsignal(signal.SIGTERM) is not c1b.StopSignals._handler


def test_r2_class2_handler_install_failure_after_lock_keeps_the_created_lock(
    layout, monkeypatch
):
    """Class 2: a refusal after the lock was opened may leave the created lock
    file; it is released (fd closed) but never deleted to look intact."""

    def boom(self):
        raise c1b.C1bConfigRefusal("synthetic install failure")

    monkeypatch.setattr(c1b.StopSignals, "install", boom)
    with pytest.raises(c1b.C1bConfigRefusal, match="synthetic"):
        c1b.prepare_from_env(layout.env())
    assert layout.identity_lock.exists()  # created, admitted, not deleted
    lock = c1b.IdentityLock.acquire(layout.identity_lock)  # released
    lock.close()


class _SecondInstallFails:
    """Deterministic R5 injection: the real ``signal.signal`` except that the
    ``fail_on``-th call that installs the C1b handler raises; optionally, the
    restoration of SIGTERM raises as well.  Every call is recorded."""

    def __init__(self, *, fail_on: int = 2, fail_restore: bool = False) -> None:
        self.real = signal.signal
        self.fail_on = fail_on
        self.fail_restore = fail_restore
        self.installs = 0
        self.calls: list[tuple[int, str]] = []
        self.error = OSError(22, "injected failure of the second signal.signal()")

    def __call__(self, sig, handler):
        installing = getattr(handler, "__func__", None) is c1b.StopSignals._handler
        self.calls.append((int(sig), "install" if installing else "restore"))
        if installing:
            self.installs += 1
            if self.installs == self.fail_on:
                raise self.error
        elif self.fail_restore and sig == signal.SIGTERM:
            raise RuntimeError("injected restore failure")
        return self.real(sig, handler)


def _raise_site(exc: BaseException) -> str:
    tb = exc.__traceback__
    while tb.tb_next is not None:
        tb = tb.tb_next
    return tb.tb_frame.f_code.co_name


def test_r5_second_install_failure_restores_sigterm_and_keeps_the_exception(
    layout, monkeypatch
):
    """R5 (rev2): SIGTERM is installed, SIGINT fails.  SIGTERM is put back to its
    previous disposition (none left partially installed), the original
    exception object propagates with its traceback (raised by the second
    ``signal.signal``), the identity lock is released, no proof is written."""
    term_before = signal.getsignal(signal.SIGTERM)
    int_before = signal.getsignal(signal.SIGINT)
    inject = _SecondInstallFails()
    monkeypatch.setattr(c1b.signal, "signal", inject)
    with pytest.raises(OSError) as info:
        c1b.prepare_from_env(layout.env())
    monkeypatch.undo()
    assert info.value is inject.error  # same object, not rewrapped
    assert _raise_site(info.value) == "__call__"  # original traceback kept
    assert not getattr(info.value, "__notes__", None)
    assert inject.calls == [
        (int(signal.SIGTERM), "install"),
        (int(signal.SIGINT), "install"),
        (int(signal.SIGTERM), "restore"),
    ]
    assert signal.getsignal(signal.SIGTERM) == term_before
    assert signal.getsignal(signal.SIGINT) == int_before
    lock = c1b.IdentityLock.acquire(layout.identity_lock)  # released
    lock.close()
    assert list(layout.proof_dir.iterdir()) == []  # no proof fabricated
    assert not layout.gate_journal.exists()


def test_r5_restore_failure_is_noted_on_the_original_exception(layout, monkeypatch):
    """R5: if putting SIGTERM back fails too, the original exception is still
    the one raised; the restore failure is attached as a note only."""
    term_before = signal.getsignal(signal.SIGTERM)
    inject = _SecondInstallFails(fail_restore=True)
    monkeypatch.setattr(c1b.signal, "signal", inject)
    try:
        with pytest.raises(OSError) as info:
            c1b.prepare_from_env(layout.env())
    finally:
        monkeypatch.undo()
        signal.signal(signal.SIGTERM, term_before)
    assert info.value is inject.error
    assert _raise_site(info.value) == "__call__"
    assert any("restoring signal" in n for n in info.value.__notes__)
    lock = c1b.IdentityLock.acquire(layout.identity_lock)
    lock.close()
    assert list(layout.proof_dir.iterdir()) == []


def test_r5_first_install_failure_installs_nothing(layout, monkeypatch):
    term_before = signal.getsignal(signal.SIGTERM)
    inject = _SecondInstallFails(fail_on=1)
    monkeypatch.setattr(c1b.signal, "signal", inject)
    with pytest.raises(OSError):
        c1b.prepare_from_env(layout.env())
    monkeypatch.undo()
    assert inject.calls == [(int(signal.SIGTERM), "install")]
    assert signal.getsignal(signal.SIGTERM) == term_before


def test_r5_nominal_install_is_unchanged_and_restorable(layout):
    """Nominal path: both handlers installed, the handler is the lock-free one."""
    prep = _prepare(layout)
    for sig in c1b.StopSignals.HANDLED:
        assert (
            getattr(signal.getsignal(sig), "__func__", None) is c1b.StopSignals._handler
        )
    prep.signals.restore()


def test_sig_restore_puts_previous_handlers_back(layout):
    before = signal.getsignal(signal.SIGTERM)
    prep = _prepare(layout)
    assert signal.getsignal(signal.SIGTERM) != before
    prep.signals.restore()
    assert signal.getsignal(signal.SIGTERM) == before


def test_l6_r1_handler_makes_no_call_at_all():
    """R1: the handler body contains no call (so no lock can be taken through
    one), only a comparison and one attribute assignment.  The original
    candidate's ``self.event.set()`` fails this test."""
    import ast
    import inspect

    src = textwrap.dedent(inspect.getsource(c1b.StopSignals._handler))
    tree = ast.parse(src)
    calls = [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert calls == [], calls
    body = tree.body[0].body
    stores = [
        ast.unparse(t)
        for n in ast.walk(tree)
        if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign))
        for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
    ]
    assert stores == ["self._signum"], stores
    assert len(body) == 1 and isinstance(body[0], ast.If)


def test_l6_r1_stop_signals_use_no_threading_primitive():
    import inspect

    import ast

    tree = ast.parse(textwrap.dedent(inspect.getsource(c1b.StopSignals)))
    for node in ast.walk(tree):  # drop docstrings: only code is checked
        body = getattr(node, "body", None)
        if (
            isinstance(body, list)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(getattr(body[0], "value", None), ast.Constant)
        ):
            body[0] = ast.Pass()
    code = ast.unparse(tree)
    for forbidden in ("threading", "Event", "Lock", "Condition", "Semaphore"):
        assert forbidden not in code, forbidden


# R1 deterministic regression.  The child traces StopSignals.wait and every
# frame it reaches in ``threading`` and in the C1b module, and sends SIGTERM to
# itself at EACH executed line (bounded burst of 200): a signal therefore lands
# on every line of the waiting code, including while a ``threading`` lock is
# held, and on every line of the handler itself (reentrant burst).  With the
# original ``Event`` mechanism the child deadlocks and the watchdog fires; the
# revised mechanism returns.  ``C1B_R1_CANDIDATE_ROOT`` selects the tree under
# test (default: this repository), so the same test is run against the original
# candidate to prove that it fails there.
_R1_CHILD = r"""
import json, os, signal, sys, threading
sys.path.insert(0, __ROOT__)
from paper_trading import ppl_quiescence_c1b as c1b
assert c1b.__file__.startswith(__ROOT__), c1b.__file__
s = c1b.StopSignals()
s.install()
watched = {os.path.realpath(threading.__file__), os.path.realpath(c1b.__file__)}
# test-only reset between probes (original: event; revision: attribute)
def reset():
    if hasattr(s, "event"):
        s.event.clear()
    else:
        s._signum = None
state = {"mode": None, "k": 0, "line": 0, "sent": 0}
def local(frame, event, arg):
    if event != "line":
        return local
    state["line"] += 1
    if state["mode"] == "burst" and state["sent"] < 200:
        state["sent"] += 1
        os.kill(os.getpid(), signal.SIGTERM)
    elif state["mode"] == "kth" and state["line"] == state["k"]:
        state["sent"] += 1
        os.kill(os.getpid(), signal.SIGTERM)
    return local
def trace(frame, event, arg):
    if os.path.realpath(frame.f_code.co_filename) in watched:
        return local(frame, event, arg)
    return None
print("ARMED", flush=True)
# Phase 1: a signal on the k-th executed line of one wait, for every k reached
# (the whole waiting window, including lines run while a lock is held).
reached = []
for k in range(1, 61):
    reset()
    state.update(mode="kth", k=k, line=0)
    sys.settrace(trace)
    got = s.wait(0.05)
    sys.settrace(None)
    reached.append((k, state["line"], got, s.requested))
    print("K", k, flush=True)
    if state["line"] < k:
        break  # every line of this wait has been probed
# Phase 2: a signal at every executed line, including inside the handler
# itself (reentrant burst, bounded to 200 signals).
reset()
state.update(mode="burst", line=0, sent=0)
sys.settrace(trace)
first = s.wait(0.3)
again = s.wait(0.3)
sys.settrace(None)
print(json.dumps({"returned": True, "first": first, "again": again,
                  "requested": s.requested, "signum": s.signum,
                  "burst_sent": state["sent"], "kth_probes": len(reached),
                  "kth_seen_in_wait": sum(1 for k, n, g, r in reached if n >= k and g),
                  "kth_never_lost": all(r for k, n, g, r in reached if n >= k)}),
      flush=True)
"""

R1_WATCHDOG_S = 20.0


def _r1_candidate_root() -> str:
    return os.environ.get("C1B_R1_CANDIDATE_ROOT") or str(ROOT)


def test_r1_deterministic_signal_at_every_line_of_wait_and_handler_never_deadlocks():
    root = _r1_candidate_root()
    script = _R1_CHILD.replace("__ROOT__", repr(root))
    proc = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    _children.append(proc)
    try:
        out, err = proc.communicate(timeout=R1_WATCHDOG_S)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate(timeout=10)
        pytest.fail(
            f"R1 DEADLOCK: no return within {R1_WATCHDOG_S}s (root={root}); "
            f"stdout={out!r} stderr={err[-500:]!r}"
        )
    assert proc.returncode == 0, err
    lines = out.strip().splitlines()
    assert lines[0] == "ARMED"
    result = json.loads(lines[-1])
    assert result["returned"] is True
    assert result["first"] is True and result["again"] is True
    assert result["requested"] is True and result["signum"] == signal.SIGTERM
    assert result["burst_sent"] >= 2  # the burst reached the handler (reentrancy)
    # every probed line got its signal recorded (none lost); a signal landing
    # on the timeout-return line is recorded but seen by the next check only
    assert result["kth_probes"] >= 2 and result["kth_never_lost"] is True
    assert result["kth_seen_in_wait"] >= 1


def test_r1_signal_during_inter_cycle_wait_is_taken_within_bound(layout):
    """Announced bound: 1.0 s between the signal and the return of the wait
    (POLL_S = 0.1 s plus scheduling margin); watchdog 20 s."""
    prep = _prepare(layout)
    in_wait = threading.Event()  # test-side rendezvous only, never in a handler
    sent: dict = {}

    def sender():
        in_wait.wait(20)
        time.sleep(0.2)  # let the main thread enter the sleep slice
        sent["at"] = time.monotonic()
        os.kill(os.getpid(), signal.SIGTERM)

    th = threading.Thread(target=sender, daemon=True)
    th.start()
    in_wait.set()
    started = time.monotonic()
    returned = prep.signals.wait(20.0)
    ended = time.monotonic()
    th.join(20)
    assert returned is True
    assert ended - started < 20.0
    assert ended - sent["at"] < 1.0, ended - sent["at"]
    assert c1b.StopSignals.POLL_S <= 0.1


def test_r1_wait_without_signal_returns_false_after_timeout(layout):
    prep = _prepare(layout)
    started = time.monotonic()
    assert prep.signals.wait(0.25) is False
    assert 0.2 <= time.monotonic() - started < 1.0


# ------------------------------------------------ B11b-c: code identity


def test_b11bc_clean_head_equal_to_manifest_is_claimed_only():
    code = c1b.resolve_code_identity(_manifest(), lambda: _evidence())
    assert code.code_sha == CODE
    assert code.provenance == "GIT_HEAD_AT_BOOT"
    assert code.evidence_status == "CLAIMED_ONLY"


@pytest.mark.parametrize(
    "evidence, match",
    [
        (_evidence(worktree="DIRTY"), "not CLEAN"),
        (_evidence(worktree="UNKNOWN"), "not CLEAN"),
        (_evidence(sha=None), "unknown or malformed"),
        (_evidence(sha=CODE.upper()), "unknown or malformed"),
        (_evidence(sha=CODE[:39]), "unknown or malformed"),
        (_evidence(sha="ab" * 20), "differs from the authority manifest"),
        (None, "unknown or malformed"),
    ],
)
def test_b11bc_code_identity_refusals(evidence, match):
    with pytest.raises(c1b.C1bIdentityRefusal, match=match):
        c1b.resolve_code_identity(_manifest(), lambda: evidence)


def test_b11bc_capture_failure_is_refusal():
    def boom():
        raise OSError("git missing")

    with pytest.raises(c1b.C1bIdentityRefusal, match="capture failed"):
        c1b.resolve_code_identity(_manifest(), boom)


def test_b11bc_value_is_never_taken_from_manifest():
    """A manifest whose code_sha matches is only the comparand: an absent HEAD
    is refused even though the manifest carries a well-formed sha."""
    with pytest.raises(c1b.C1bIdentityRefusal):
        c1b.resolve_code_identity(
            _manifest(), lambda: SimpleNamespace(worktree_state="CLEAN")
        )


# ---------------------------------------------------------- bind_wiring


def test_l2_bind_requires_ppl_authority_and_runtime(layout):
    world_manifest = _manifest()
    runtime = PPLAuthorityRuntime(
        manifest=world_manifest, store=DurableEventStore(layout.authority_root)
    )
    runtime.bind(now=NOW)
    prep = _prepare(layout)
    with pytest.raises(c1b.C1bConfigRefusal, match="PPL_AUTHORITY"):
        c1b.bind_wiring(
            prep,
            SimpleNamespace(ppl_is_authoritative=False),
            runtime,
            capture_fn=_evidence,
        )
    with pytest.raises(c1b.C1bConfigRefusal, match="bound PPL authority runtime"):
        c1b.bind_wiring(
            prep, SimpleNamespace(ppl_is_authoritative=True), None, capture_fn=_evidence
        )


def test_l3_bind_refuses_overlap_with_the_bound_store_root(layout):
    """The env store root may be absent or differ: the bound one is checked."""
    store_root = layout.proof_dir / "authority"
    runtime = PPLAuthorityRuntime(
        manifest=_manifest(), store=DurableEventStore(store_root)
    )
    runtime.bind(now=NOW)
    prep = _prepare(layout, PPL_AUTHORITY_STORE_ROOT=None)
    with pytest.raises(c1b.C1bConfigRefusal, match="bound authority store root"):
        c1b.bind_wiring(
            prep,
            SimpleNamespace(ppl_is_authoritative=True),
            runtime,
            capture_fn=_evidence,
        )


def test_b11b_bind_refuses_code_mismatch(layout):
    runtime = PPLAuthorityRuntime(
        manifest=_manifest(), store=DurableEventStore(layout.authority_root)
    )
    runtime.bind(now=NOW)
    prep = _prepare(layout)
    with pytest.raises(c1b.C1bIdentityRefusal, match="differs"):
        c1b.bind_wiring(
            prep,
            SimpleNamespace(ppl_is_authoritative=True),
            runtime,
            capture_fn=lambda: _evidence(sha="ab" * 20),
        )


def test_b4iv_b11a_gate_never_opened_is_logged_not_blocking(layout, caplog):
    caplog.set_level("INFO", logger="paper_trading.ppl_quiescence_c1b")
    world = World(layout, open_gate=False)
    assert world.wiring.gate_state_at_boot == "CLOSED"
    assert any(
        r.levelname == "CRITICAL" and "D-EPOCH-PATH" in r.getMessage()
        for r in caplog.records
    )
    assert any("CLAIMED_ONLY" in r.getMessage() for r in caplog.records)
    # OPEN is refused by C1a (fail closed), nothing is written to PPL
    before = world.store.load_epoch(EPOCH)
    world.buy()
    assert world.store.load_epoch(EPOCH) == before
    assert world.sim._positions == {} or "BTC/USDT" not in world.sim._positions
    assert not layout.gate_journal.exists() or world.wiring.gate.state() == "CLOSED"


def test_b11a_identities_come_from_the_bound_runtime(layout):
    world = World(layout)
    gate = world.wiring.gate
    assert gate.paper_epoch_id == EPOCH
    assert gate.manifest_sha256 == world.manifest_sha
    assert world.wiring.simulator_kwargs() == {
        "admission_gate": gate,
        "gate_wiring_code_sha": CODE,
    }
    assert world.wiring.gate_state_at_boot == "OPEN"


def test_l7_role_neutrality_bind_never_opens_closes_or_drains(layout, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("C1b must not drive the gate")

    for name in ("open", "close", "drain_barrier"):
        monkeypatch.setattr(AdmissionGate, name, forbidden)
    world = World(layout, open_gate=False)
    world.shutdown()


# ------------------------------------------------------- shutdown outcomes


def test_shutdown_seals_and_exit_code_zero(layout):
    world = World(layout)
    assert world.buy().status.name == "FILLED"
    world.close()
    out = world.shutdown()
    assert out.status == c1b.SEALED and out.sealed and out.exit_code == 0
    chain = world.proofs().scan()
    assert [r.kind for r in chain.records] == [qp.KIND_OBSERVATION, qp.KIND_SENTINEL]
    assert chain.records[0].record_sha256 == out.observation_sha256
    assert chain.records[1].record_sha256 == out.seal_sha256
    assert world.sim._running is False
    # The process is alive: without an external witness this is never a stop.
    verdict = world.assess()
    assert verdict.verdict != qp.V_SEALED_STOPPED
    assert verdict.verdict != qp.V_CLEAN_CONFIRMED


def test_shutdown_observation_uses_c1b_identity_and_head(layout):
    world = World(layout)
    world.shutdown()
    obs = world.proofs().scan().records[0].body
    assert obs["code_sha"]["value"] == CODE
    assert obs["source_sha"]["value"] == CODE  # the claimed HEAD, not the manifest
    rendered = json.dumps(obs)
    assert str(layout.identity_lock) in rendered
    # counters come from the C1a declaration, never fabricated
    for name, item in obs.items():
        if item.get("status") == "OBSERVED":
            assert item.get("provenance"), name


def test_shutdown_with_open_position_is_sealed_but_not_quiescent(layout):
    world = World(layout)
    world.buy()
    out = world.shutdown()
    assert out.status == c1b.SEALED
    obs = world.proofs().scan().records[0].body
    assert len(qp.observed_value(obs, "durable_open_positions")) == 1
    assert len(qp.observed_value(obs, "memory_open_positions")) == 1


def test_shutdown_no_simulator(layout):
    world = World(layout)
    out = c1b.shutdown_proof(world.wiring, None, world.runtime, process_instance_id="i")
    assert out.status == c1b.NO_SIMULATOR and out.exit_code == 3
    assert world.proofs().scan().status == "EMPTY"


@pytest.mark.parametrize("how", ["unlink", "replace", "chmod"])
def test_shutdown_identity_lock_changed_writes_nothing(layout, how):
    world = World(layout)
    path = layout.identity_lock
    if how == "unlink":
        path.unlink()
    elif how == "replace":
        path.unlink()
        path.write_text("")
    else:
        os.chmod(path, 0o400)
    out = world.shutdown()
    assert out.status == c1b.IDENTITY_LOCK_CHANGED and out.exit_code == 3
    assert world.proofs().scan().status == "EMPTY"


def test_shutdown_observation_failure(layout, monkeypatch):
    world = World(layout)

    def boom(*a, **k):
        raise qp.QuiescenceRefusal("synthetic")

    monkeypatch.setattr(qp, "observe_runtime", boom)
    out = world.shutdown()
    assert out.status == c1b.OBSERVATION_FAILED and out.exit_code == 3
    assert world.proofs().scan().status == "EMPTY"


def test_shutdown_proof_store_refused(layout):
    world = World(layout)
    layout.proof_dir.rmdir()
    layout.proof_dir.write_text("not a dir")
    out = world.shutdown()
    assert out.status == c1b.PROOF_STORE_REFUSED and out.exit_code == 3


def test_shutdown_proof_store_refuses_authority_overlap(layout, monkeypatch):
    world = World(layout)
    world.wiring.store_root = layout.proof_dir  # simulate a late overlap
    out = world.shutdown()
    assert out.status == c1b.PROOF_STORE_REFUSED


def _fail_fsync(monkeypatch, *, method: str, on_call: int):
    calls = {"n": 0}
    original = getattr(qp.ProofStore, method)

    def flaky(self, *a, **k):
        calls["n"] += 1
        if calls["n"] == on_call:
            raise OSError(5, "synthetic EIO")
        return original(self, *a, **k)

    monkeypatch.setattr(qp.ProofStore, method, flaky)
    return calls


def test_shutdown_observation_not_persisted(layout, monkeypatch):
    world = World(layout)
    _fail_fsync(monkeypatch, method="_fsync_fd", on_call=1)
    out = world.shutdown()
    assert out.status == c1b.OBSERVATION_NOT_PERSISTED and out.exit_code == 3
    assert world.proofs().scan().status == "EMPTY"


def test_shutdown_observation_uncertain(layout, monkeypatch):
    world = World(layout)
    _fail_fsync(monkeypatch, method="_fsync_directory", on_call=1)
    out = world.shutdown()
    assert out.status == c1b.OBSERVATION_UNCERTAIN and out.exit_code == 3
    assert world.assess().verdict == qp.V_UNCERTAIN


def test_shutdown_seal_not_persisted(layout, monkeypatch):
    world = World(layout)
    calls = {"n": 0}
    original = qp.ProofStore._publish_bytes

    def publish(self, raw, final):
        calls["n"] += 1
        if calls["n"] == 3:  # O record, O receipt, then the SENTINEL record
            raise qp.PersistBlocked("synthetic")
        return original(self, raw, final)

    monkeypatch.setattr(qp.ProofStore, "_publish_bytes", publish)
    out = world.shutdown()
    assert out.status == c1b.SEAL_NOT_PERSISTED and out.exit_code == 3
    assert out.observation_sha256 and out.seal_sha256 is None
    kinds = [r.kind for r in world.proofs().scan().records]
    assert kinds == [qp.KIND_OBSERVATION]


def test_shutdown_seal_uncertain(layout, monkeypatch):
    world = World(layout)
    # dir fsyncs: O publish (1), O receipt (2), seal publish (3)
    _fail_fsync(monkeypatch, method="_fsync_directory", on_call=3)
    out = world.shutdown()
    assert out.status == c1b.SEAL_UNCERTAIN and out.exit_code == 3


def test_shutdown_seal_receipt_not_durable(layout, monkeypatch):
    world = World(layout)
    _fail_fsync(monkeypatch, method="_fsync_directory", on_call=4)
    out = world.shutdown()
    assert out.status == c1b.SEALED_RECEIPT_NOT_DURABLE
    assert out.sealed is False and out.exit_code == 3


def test_shutdown_seal_refused_when_observation_superseded(layout):
    world = World(layout)

    def concurrent_observation():
        body = world.proofs().scan().records[0].body
        qp.write_observation(world.proofs(), body, now=time.time())

    out = world.shutdown(hooks={"after_observation": concurrent_observation})
    assert out.status == c1b.SEAL_REFUSED and out.exit_code == 3


def test_exit_codes_distinguish_only_sealed():
    for status in (
        c1b.SEALED_RECEIPT_NOT_DURABLE,
        c1b.NO_SIMULATOR,
        c1b.IDENTITY_LOCK_CHANGED,
        c1b.OBSERVATION_FAILED,
        c1b.PROOF_STORE_REFUSED,
        c1b.OBSERVATION_NOT_PERSISTED,
        c1b.OBSERVATION_UNCERTAIN,
        c1b.SEAL_NOT_PERSISTED,
        c1b.SEAL_UNCERTAIN,
        c1b.SEAL_REFUSED,
    ):
        assert c1b.ShutdownOutcome(status).exit_code == c1b.EXIT_PROOF_NOT_SEALED == 3
    assert c1b.ShutdownOutcome(c1b.SEALED).exit_code == 0


# ------------------------------------------- exigence 1: late monitor writes


def _witness(world: World, now: float | None = None) -> None:
    store = world.proofs()
    obs = next(
        r for r in reversed(store.scan().records) if r.kind == qp.KIND_OBSERVATION
    )
    result = qp.AppendResult(obs.seq, obs.record_sha256, Path(), True)
    qp.write_witness(
        store,
        result,
        store_root=world.layout.authority_root,
        epoch_id=EPOCH,
        now=time.time() if now is None else now,
    )


def test_ex1_monitor_close_between_observation_and_seal_is_never_a_proof(layout):
    world = World(layout)
    world.buy()
    out = world.shutdown(hooks={"after_observation": world.close})
    # the seal copies O's ledger digest, which is no longer the ledger's
    assert out.status == c1b.SEALED
    _witness(world)
    verdict = world.assess()
    assert verdict.quiescent is False
    assert verdict.verdict not in (qp.V_SEALED_STOPPED, qp.V_CLEAN_CONFIRMED)


def test_ex1_monitor_close_after_seal_is_never_a_proof(layout):
    world = World(layout)
    world.buy()
    out = world.shutdown(hooks={"after_seal": world.close})
    assert out.status == c1b.SEALED
    _witness(world)
    verdict = world.assess()
    assert verdict.quiescent is False
    assert verdict.verdict not in (qp.V_SEALED_STOPPED, qp.V_CLEAN_CONFIRMED)


def test_ex1_monitor_close_after_witness_is_never_a_proof(layout):
    world = World(layout)
    world.buy()
    world.shutdown()
    _witness(world)
    world.close()
    verdict = world.assess()
    assert verdict.quiescent is False
    assert verdict.verdict not in (qp.V_SEALED_STOPPED, qp.V_CLEAN_CONFIRMED)


def test_ex1_monitor_close_after_stop_before_observation_is_observed(layout):
    world = World(layout)
    world.buy()
    out = world.shutdown(hooks={"after_stop": world.close})
    assert out.status == c1b.SEALED
    obs = world.proofs().scan().records[0].body
    assert qp.observed_value(obs, "durable_open_positions") == []
    assert qp.observed_value(obs, "ledger_sha256") == world.ledger_sha()


# ------------------------------------------- B12: no fabricated zero counters


def _o_body(world: World) -> dict:
    return world.proofs().scan().records[0].body


def test_b12_i_without_gate_wiring_counters_stay_unknown(layout):
    world = World(layout)
    plain = MexcSimulator(
        telegram_fn=world.notes.append,
        lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
        authority_runtime=world.runtime,
    )
    out = c1b.shutdown_proof(
        world.wiring, plain, world.runtime, process_instance_id="i"
    )
    assert out.status == c1b.SEALED
    body = _o_body(world)
    assert body["runtime_consults_gate"]["status"] == "UNKNOWN"
    assert body["admissions_in_flight"]["status"] == "UNKNOWN"
    assert body["lifecycle_transitions_in_flight"]["status"] == "NOT_APPLICABLE"
    for name in ("admissions_in_flight", "lifecycle_transitions_in_flight"):
        assert "value" not in body[name] or body[name]["value"] is None
    with pytest.raises(qp.QuiescenceRefusal):
        qp.to_epoch_rotation_quiescence(world.assess(), body)


@pytest.mark.parametrize(
    "tamper",
    [
        lambda d: {**d, "code_sha": "ab" * 20},
        lambda d: {**d, "consults_gate_under_lock": 1},
        lambda d: "not a mapping",
    ],
)
def test_b12_ii_iii_tampered_declaration_is_unresolved_never_zero(layout, tamper):
    world = World(layout)
    world.sim.ppl_gate_wiring_v1 = tamper(dict(world.sim.ppl_gate_wiring_v1))
    out = world.shutdown()
    assert out.status == c1b.SEALED
    body = _o_body(world)
    assert body["runtime_consults_gate"]["status"] == "UNRESOLVED"
    assert body["admissions_in_flight"]["status"] != "OBSERVED"
    with pytest.raises(qp.QuiescenceRefusal):
        qp.to_epoch_rotation_quiescence(world.assess(), body)


def test_b12_iii_counters_typed_bool_are_not_counts(layout):
    world = World(layout)
    world.sim._ppl_admissions_in_flight = False
    world.shutdown()
    body = _o_body(world)
    assert body["admissions_in_flight"]["status"] == "UNRESOLVED"
    assert body["admissions_in_flight"]["value"] is None
    with pytest.raises(qp.QuiescenceRefusal):
        qp.to_epoch_rotation_quiescence(world.assess(), body)


# ------------------------------------------------- B11a: wrongly bound gate


def test_b11a_gate_bound_to_another_epoch_is_refused_by_c1a(layout):
    from paper_trading.mexc_simulator import GateWiringRefusal

    world = World(layout)
    other = AdmissionGate(
        layout.gate_journal,
        paper_epoch_id="OTHER-EPOCH",
        manifest_sha256=world.manifest_sha,
    )
    with pytest.raises(GateWiringRefusal):
        MexcSimulator(
            lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
            authority_runtime=world.runtime,
            admission_gate=other,
            gate_wiring_code_sha=CODE,
        )


def test_b11a_journal_of_another_epoch_reads_invalid_and_refuses_open(layout):
    manifest_sha = authority_manifest_sha256(_manifest())
    foreign = AdmissionGate(
        layout.gate_journal, paper_epoch_id="OTHER-EPOCH", manifest_sha256=manifest_sha
    )
    _open_gate(foreign)
    world = World(layout, open_gate=False)
    assert world.wiring.gate_state_at_boot != "OPEN"
    before = world.store.load_epoch(EPOCH)
    order = world.buy()
    assert order is None or order.status.name == "REJECTED"
    assert world.store.load_epoch(EPOCH) == before


# ------------------------------------------------------------- L6: stress


def test_l6_stress_no_deadlock_no_torn_transition(layout):
    """OPEN in a loop, monitor-like CLOSE, concurrent observations and a burst
    of SIGTERM delivered while commits run: no blocking (bounded joins), the
    handler only sets the flag, counters return to zero and the ledger stays
    consistent (every OPEN is either still open or closed exactly once)."""
    world = World(layout)
    stop = threading.Event()
    errors: list[BaseException] = []
    iterations = {"open": 0, "observe": 0, "signals": 0}

    def opener():
        try:
            for i in range(200):
                world.sim.place_market_order(
                    "BTC/USDT", "BUY", 1.0, current_price=100.0 + (i % 3)
                )
                iterations["open"] += 1
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            stop.set()

    def closer():
        try:
            while not stop.is_set():
                if "BTC/USDT" in world.sim._positions:
                    world.sim._close_position("BTC/USDT", 101.0, "TP")
                time.sleep(0)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def observer():
        try:
            while not stop.is_set():
                qp.observe_runtime(
                    world.sim,
                    world.runtime,
                    manifest=world.manifest,
                    manifest_sha256=world.manifest_sha,
                    gate=world.wiring.gate,
                    identity=qp.current_process_identity(
                        process_instance_id="stress",
                        lock_path=str(layout.identity_lock),
                        lock_fd=world.prepared.identity_lock.fd,
                    ),
                    source_sha=CODE,
                )
                iterations["observe"] += 1
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=f, daemon=True) for f in (opener, closer, observer)
    ]
    started = time.monotonic()
    for th in threads:
        th.start()
    while not stop.is_set() and time.monotonic() - started < 60:
        os.kill(os.getpid(), signal.SIGTERM)  # handled by the main thread: flag only
        iterations["signals"] += 1
        time.sleep(0.001)
    for th in threads:
        th.join(60)
        assert not th.is_alive(), "deadlock"
    assert errors == []
    assert time.monotonic() - started < 60
    assert iterations["open"] == 200 and iterations["signals"] > 0
    assert world.prepared.signals.requested is True
    assert world.sim._ppl_admissions_in_flight == 0
    assert (
        world.sim._ppl_started_transitions == {}
        or not world.sim._ppl_started_transitions
    )
    events = world.store.load_epoch(EPOCH)
    opened = [e.trade_id for e in events if e.event_type == "POSITION_OPENED"]
    closed = [e.trade_id for e in events if e.event_type == "POSITION_CLOSED"]
    assert len(set(closed)) == len(closed)
    assert set(closed) <= set(opened)
    assert len(opened) - len(closed) == len(world.sim._positions)
    out = world.shutdown()
    assert out.status == c1b.SEALED
