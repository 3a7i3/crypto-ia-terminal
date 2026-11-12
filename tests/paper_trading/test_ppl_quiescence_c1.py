"""PPL-QUIESCENCE-01 lot C1a — contract v0.3 (sha256 eeb912f8...41be2).

Hermetic tests: synthetic data, temp dirs only, no network, no exchange, no
Telegram, no Advisor.  Child processes are fresh ``subprocess`` interpreters
with bounded waits and kill+wait cleanup.

The admission gate journal is synthesised in ``_open_gate`` (test-only): a
real ``open()`` needs a succession clearance bundle, which is out of scope for
these tests and is already covered by ``test_ppl_succession_01``.

Naming follows the contract: scenarios S1-S20 (§8.3), interleavings I1-I13
(§8.4), negative tests N1-N7 (§8.5), exception boundary H1-H9 (§8.3 #19,
erratum §15) and transitions TT1-TT10 (§8.3 #9).
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
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

import pytest

from paper_trading import ppl_admission_gate as gm
from paper_trading import ppl_quiescence_proof as qp
from paper_trading.admission_ledger import (
    get_admission_ledger,
    reset_admission_ledger_singleton,
)
from paper_trading.admission_types import (
    AdmissionDecision,
    AdmissionLevel,
    AdmissionVerdict,
    WriteResult,
)
from paper_trading.durable_event_store import (
    DurableEventStore,
    StoreCorruptionError,
)
from paper_trading.mexc_simulator import (
    COUNTERS_PROTOCOL,
    GateWiringRefusal,
    MexcSimulator,
    OrderStatus,
)
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
EPOCH = "C1A-TEST-EPOCH"
CODE = "c1" * 20  # 40 lowercase hex
GUARD = 20.0  # watchdog for every rendezvous; never a pacing delay

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
        config_snapshot_hash="cfg-hash-c1a",
        legacy_log_bytes=b"",
        quiescence=EpochRotationQuiescence(0, 0, 0, True),
        predecessor_authority_epoch_id="PRED-EPOCH",
    )


def _open_gate(gate: AdmissionGate) -> None:
    """Test-only synthesis of a valid chained OPEN record (see module doc)."""
    with gate._locked():
        assert gate._records() == []
        gate._append(
            {
                "seq": 1,
                "prev_sha256": "0" * 64,
                "action": "OPEN",
                "paper_epoch_id": gate.paper_epoch_id,
                "manifest_sha256": gate.manifest_sha256,
                "decision_sha256": "d" * 64,
                "clearance_proof_sha256": "e" * 64,
                "decided_by": "test-c1a",
                "reason": "",
            }
        )
    assert gate.state() == "OPEN"


class World:
    def __init__(
        self,
        tmp: Path,
        *,
        wire_gate: bool = True,
        code_sha: str | None = CODE,
        open_gate: bool = True,
    ) -> None:
        self.tmp = tmp
        self.authority_root = tmp / "authority"
        self.manifest = _manifest()
        self.manifest_sha = authority_manifest_sha256(self.manifest)
        self.store = DurableEventStore(self.authority_root)
        self.runtime = PPLAuthorityRuntime(manifest=self.manifest, store=self.store)
        state = self.runtime.bind(now=NOW)
        self.gate_path = tmp / "gate" / "gate.jsonl"
        self.gate = AdmissionGate(
            self.gate_path, paper_epoch_id=EPOCH, manifest_sha256=self.manifest_sha
        )
        if open_gate:
            _open_gate(self.gate)
        self.notes: list[str] = []
        self.sim = MexcSimulator(
            telegram_fn=self.notes.append,
            lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
            authority_runtime=self.runtime,
            admission_gate=self.gate if wire_gate else None,
            gate_wiring_code_sha=code_sha if wire_gate else None,
        )
        self.sim._capital = state.available_cash
        self.sim._initial_capital = 1000.0
        self.proof_dir = tmp / "proofs"
        self.proofs = qp.ProofStore(self.proof_dir, forbidden_roots=[self.authority_root])

    # -- actions
    def buy(self, symbol: str = "BTC/USDT", price: float = 100.0, **kw):
        return self.sim.place_market_order(symbol, "BUY", 10.0, current_price=price, **kw)

    def close(self, symbol: str = "BTC/USDT", price: float = 101.0, reason: str = "TP"):
        self.sim._close_position(symbol, price, reason)

    def other_gate(self) -> AdmissionGate:
        return AdmissionGate(
            self.gate_path, paper_epoch_id=EPOCH, manifest_sha256=self.manifest_sha
        )

    # -- reads
    def epoch_file(self) -> Path:
        return self.store._epoch_path(EPOCH)

    def ledger_sha(self) -> str:
        return hashlib.sha256(self.epoch_file().read_bytes()).hexdigest()

    def events(self):
        return DurableEventStore(self.authority_root).load_epoch(EPOCH)

    def opened(self) -> list[str]:
        return [e.trade_id for e in self.events() if e.event_type == "POSITION_OPENED"]

    def journal_actions(self) -> list[str]:
        records = self.gate._records()
        assert records is not None
        return [r["action"] for r in records]

    def observe(self, identity=None):
        return qp.observe_runtime(
            self.sim,
            self.runtime,
            manifest=self.manifest,
            manifest_sha256=self.manifest_sha,
            gate=self.gate,
            identity=identity
            or qp.current_process_identity(
                process_instance_id="inst-c1a",
                lock_path=str(self.tmp / "advisor.lock"),
                lock_fd=None,
            ),
            source_sha="source-sha-c1a",
        )


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


@pytest.fixture(autouse=True)
def _isolated_admission_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_ADMISSION_LEDGER", str(tmp_path / "admission.jsonl"))
    reset_admission_ledger_singleton()
    yield
    reset_admission_ledger_singleton()


_children: list[subprocess.Popen] = []


@pytest.fixture(autouse=True)
def _reap_children():
    yield
    for proc in _children:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            pass
    _children.clear()


def _approved(n: int = 0) -> AdmissionVerdict:
    return AdmissionVerdict(
        decision=AdmissionDecision.APPROVED,
        level=AdmissionLevel.A,
        n_at_check=n,
        hard_max_at_check=10,
        checked_by="test-c1a",
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


_GATE_CHILD = """
import json, sys
from paper_trading.ppl_admission_gate import AdmissionGate
path, epoch, msha, action = sys.argv[1:5]
gate = AdmissionGate(path, paper_epoch_id=epoch, manifest_sha256=msha)
if action == "close":
    print(json.dumps({"durable": gate.close(decided_by="child", reason="c1a")}))
elif action.startswith("drain:"):
    print(json.dumps(list(gate.drain_barrier(timeout_s=float(action[6:])))))
elif action == "state":
    print(json.dumps(gate.state()))
"""


def _child_gate(world: World, action: str) -> object:
    res = _py(_GATE_CHILD, str(world.gate_path), EPOCH, world.manifest_sha, action)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


_HOLDER_CHILD = """
import fcntl, os, sys, time
lock, ready = sys.argv[1], sys.argv[2]
fd = os.open(lock, os.O_RDONLY)
fcntl.flock(fd, fcntl.LOCK_EX)
open(ready, "w").close()
deadline = time.monotonic() + 60
while time.monotonic() < deadline:
    time.sleep(0.05)
"""


def _spawn_holder(world: World) -> subprocess.Popen:
    ready = world.tmp / f"holder-{len(_children)}.ready"
    proc = subprocess.Popen(
        [sys.executable, "-I", "-c", _HOLDER_CHILD, str(world.gate._lock_path), str(ready)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _children.append(proc)
    deadline = time.monotonic() + 15
    while not ready.exists():
        assert proc.poll() is None and time.monotonic() < deadline, "holder not ready"
        time.sleep(0.01)
    return proc


def _flock_free_elsewhere(lock_path: Path) -> bool:
    """A distinct PROCESS tries LOCK_EX|LOCK_NB once (no wait)."""
    res = _py(
        """
        import fcntl, os, sys
        fd = os.open(sys.argv[1], os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print("FREE")
        except OSError:
            print("HELD")
        """,
        str(lock_path),
    )
    assert res.returncode == 0, res.stderr
    return res.stdout.strip() == "FREE"


def _fds_on_inode(dev: int, ino: int) -> list[str]:
    out = []
    for name in os.listdir("/proc/self/fd"):
        try:
            st = os.stat(f"/proc/self/fd/{name}")
        except OSError:
            continue
        if (st.st_dev, st.st_ino) == (dev, ino):
            out.append(name)
    return out


# ------------------------------------------------------------ rendezvous


class Points:
    """Deterministic rendezvous inside the admitter thread (no production hooks).

    P1 after the t1 marker check, P2 after the t2 journal read, P3 after the t3
    marker check, PF after the flock is obtained, P4 inside store.append before
    writing, P5 after store.append returned, P6 after the gate fd is closed.
    """

    def __init__(self, world: World, point: str, monkeypatch, thread: str = "admitter"):
        self.point = point
        self.thread = thread
        self.reached = threading.Event()
        self.release = threading.Event()
        gate = world.gate
        calls = {"marker": 0}
        real_marker = gate._marker_present
        real_records = gate._records

        def marker():
            out = real_marker()
            if self._mine():
                calls["marker"] += 1
                self.hit("P1" if calls["marker"] == 1 else "P3")
            return out

        def records():
            out = real_records()
            if self._mine():
                self.hit("P2")
            return out

        monkeypatch.setattr(gate, "_marker_present", marker)
        monkeypatch.setattr(gate, "_records", records)
        real_flock = gm._flock_ro

        def flock(fd, timeout):
            out = real_flock(fd, timeout)
            if self._mine():
                self.hit("PF")
            return out

        monkeypatch.setattr(gm, "_flock_ro", flock)
        real_close_fd = gm._close_fd

        def close_fd(fd):
            real_close_fd(fd)
            if self._mine() and fd is not None:
                self.hit("P6")

        monkeypatch.setattr(gm, "_close_fd", close_fd)
        store = world.store
        real_append = store.append

        def append(epoch_id, event):
            if self._mine():
                self.hit("P4")
            out = real_append(epoch_id, event)
            if self._mine():
                self.hit("P5")
            return out

        monkeypatch.setattr(store, "append", append)

    def _mine(self) -> bool:
        return threading.current_thread().name == self.thread

    def hit(self, name: str) -> None:
        if name == self.point and not self.reached.is_set():
            self.reached.set()
            assert self.release.wait(GUARD), f"rendezvous {name} never released"

    def wait(self) -> None:
        assert self.reached.wait(GUARD), f"admitter never reached {self.point}"


def _start(target, name: str):
    box: dict = {}

    def run():
        try:
            box["result"] = target()
        except BaseException as exc:  # noqa: BLE001 - surfaced by the test
            box["error"] = exc

    th = threading.Thread(target=run, name=name, daemon=True)
    th.start()
    return th, box


def _join(th: threading.Thread, box: dict):
    th.join(GUARD)
    assert not th.is_alive(), f"{th.name} did not finish"
    if "error" in box:
        raise box["error"]
    return box.get("result")


def _close_now(world: World, closer: str, *, patient: bool = False):
    """Create the closure marker (and maybe the journal CLOSE) from a thread
    of this process or from a child process.  ``patient``: the thread closer
    waits for the journal flock as long as the guard (instead of close()'s own
    1 s), so that its CLOSE record deterministically follows a held commit."""
    if closer == "process":
        return _child_gate(world, "close")
    closer_gate = world.other_gate()
    if patient:
        real_locked = closer_gate._locked
        closer_gate._locked = lambda timeout=None: real_locked(timeout=GUARD)
    th, box = _start(lambda: closer_gate.close(decided_by="t", reason="c1a"), "closer")
    deadline = time.monotonic() + GUARD
    while not world.gate._closed_marker.exists():
        assert time.monotonic() < deadline
        time.sleep(0.002)
    return th, box


# ============================================================ S1 (AC1)

_DRIVER = r"""
import hashlib, itertools, json, os, sys, time, uuid
root, work = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)
os.chdir(work)
_u = itertools.count(1)
uuid.uuid4 = lambda: uuid.UUID(int=next(_u) << 96)
_t = itertools.count(0)
time.time = lambda: 1_900_000_000.0 + next(_t)
os.environ["PAPER_ADMISSION_LEDGER"] = os.path.join(work, "admission.jsonl")
import paper_trading.admission_types as at
class _DT(at.datetime):
    @classmethod
    def now(cls, tz=None):
        return at.datetime.fromtimestamp(time.time(), tz=tz)
at.datetime = _DT
from paper_trading.admission_ledger import reset_admission_ledger_singleton
reset_admission_ledger_singleton()
from paper_trading.admission_types import (AdmissionDecision, AdmissionLevel,
    AdmissionVerdict)
from paper_trading.durable_event_store import DurableEventStore
from paper_trading.mexc_simulator import MexcSimulator
from paper_trading.paper_authority import PaperLifecycleAuthority
from paper_trading.ppl_authority_runtime import (EpochRotationQuiescence,
    PPLAuthorityRuntime, build_experiment_manifest)
m = build_experiment_manifest(paper_epoch_id="C1A-AC1-EPOCH", created_at=1.0,
    initial_virtual_capital=1000.0, code_sha="a" * 40, config_snapshot_hash="cfg",
    legacy_log_bytes=b"", quiescence=EpochRotationQuiescence(0, 0, 0, True),
    predecessor_authority_epoch_id="PRED")
store = DurableEventStore(os.path.join(work, "authority"))
rt = PPLAuthorityRuntime(manifest=m, store=store)
state = rt.bind(now=1_900_000_000.0)
notes = []
sim = MexcSimulator(telegram_fn=notes.append,
    lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY, authority_runtime=rt)
sim._capital = state.available_cash
sim._initial_capital = 1000.0
def ok(n):
    return AdmissionVerdict(decision=AdmissionDecision.APPROVED,
        level=AdmissionLevel.A, n_at_check=n, hard_max_at_check=10, checked_by="d")
def no(n):
    return AdmissionVerdict(decision=AdmissionDecision.REJECTED,
        level=AdmissionLevel.A, n_at_check=n, hard_max_at_check=10, checked_by="d")
st = []
def buy(sym, qty, price, adm):
    o = sim.place_market_order(sym, "BUY", qty, current_price=price, admission=adm,
        cycle_id="c")
    st.append(o.status.value)
buy("BTC/USDT", 10.0, 100.0, ok(0))
buy("BTC/USDT", 10.0, 100.0, ok(1))
buy("ETH/USDT", 10.0, 50.0, no(1))
buy("ETH/USDT", 0.5, 50.0, ok(1))
buy("SOL/USDT", 10.0, 0.0, ok(1))
buy("ETH/USDT", 10.0, 50.0, ok(1))
buy("SOL/USDT", 10.0, 20.0, ok(2))
sim._close_position("BTC/USDT", 105.0, "TP")
sim._close_position("ETH/USDT", 48.0, "SL")
sim._close_position("SOL/USDT", 20.0, "TIMEOUT")
ppl = store._epoch_path("C1A-AC1-EPOCH").read_bytes()
adm = open(os.path.join(work, "admission.jsonl"), "rb").read()
print(json.dumps({
    "statuses": st,
    "ppl_sha256": hashlib.sha256(ppl).hexdigest(),
    "admission_sha256": hashlib.sha256(adm).hexdigest(),
    "notes_sha256": hashlib.sha256("\n".join(notes).encode()).hexdigest(),
    "capital": repr(sim._capital),
    "generation": sim._legacy_generation,
}, sort_keys=True))
"""

def _drive(root: Path, work: Path) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    res = subprocess.run(
        [sys.executable, "-I", "-c", _DRIVER, str(root), str(work)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


# Digests produced by this exact driver against main@7cd4c4e9 (base tree, where
# no gate parameter exists), twice, deterministic.  Byte identity of the PPL
# epoch file, the admission ledger and the notifications is asserted on them.
AC1_EXPECTED = {
    "admission_sha256": "5608a00a462c116594d1c758344cd365b9180cd752e12666a63b4581ab1dcd58",
    "capital": "1000.0099150424788",
    "generation": 6,
    "notes_sha256": "e7771d19b6262c4de353da8434584dab64a0740bedaac0aa79800abe84a8f052",
    "ppl_sha256": "2de660bd5925f48df2da20e467f658d2a38cf3fbea6b53c9ee9c66acf75cfeba",
    "statuses": ["FILLED", "REJECTED", "REJECTED", "REJECTED", "REJECTED", "FILLED", "FILLED"],
}


def test_s1_default_without_gate_is_byte_identical_to_base(tmp_path):
    """S1/AC1: with no gate injected, ledgers, notifications and memory are
    byte-identical to main@7cd4c4e9 for the same frozen synthetic sequence."""
    current = _drive(ROOT, tmp_path / "current")
    assert current["statuses"] == [
        "FILLED",
        "REJECTED",
        "REJECTED",
        "REJECTED",
        "REJECTED",
        "FILLED",
        "FILLED",
    ]
    base_root = os.environ.get("C1A_BASELINE_ROOT")
    if base_root:
        assert _drive(Path(base_root), tmp_path / "base") == current
    assert current == AC1_EXPECTED, "differs from the main@7cd4c4e9 digests"


# ============================================================ S2/S3 (AC2, AC3a)


def _prep_absent(w: World):
    pass


def _prep_lock_only(w: World):
    with w.gate._locked():
        pass


def _prep_close_journal(w: World):
    _open_gate(w.gate)
    recs = w.gate._records()
    with w.gate._locked():
        w.gate._append(
            {
                "seq": 2,
                "prev_sha256": recs[-1]["record_sha256"],
                "action": "CLOSE",
                "paper_epoch_id": EPOCH,
                "manifest_sha256": w.manifest_sha,
                "decision_sha256": "",
                "clearance_proof_sha256": "",
                "decided_by": "t",
                "reason": "synth",
            }
        )


def _prep_marker(w: World):
    _open_gate(w.gate)
    assert w.other_gate().close(decided_by="t", reason="r") is True


def _prep_corrupt(w: World):
    _open_gate(w.gate)
    with open(w.gate_path, "ab") as fh:
        fh.write(b"garbage\n")


def _prep_truncated(w: World):
    _open_gate(w.gate)
    raw = w.gate_path.read_bytes()
    w.gate_path.write_bytes(raw[:-5])


def _prep_journal_symlink(w: World):
    _open_gate(w.gate)
    real = w.gate_path.with_name("real.jsonl")
    os.replace(w.gate_path, real)
    os.symlink(real, w.gate_path)


def _prep_marker_dir(w: World):
    _open_gate(w.gate)
    w.gate._closed_marker.mkdir()


def _prep_other_epoch(w: World):
    _open_gate(AdmissionGate(w.gate_path, paper_epoch_id="OTHER", manifest_sha256=w.manifest_sha))


def _prep_other_manifest(w: World):
    _open_gate(AdmissionGate(w.gate_path, paper_epoch_id=EPOCH, manifest_sha256="f" * 64))


def _prep_lock_symlink(w: World):
    _open_gate(w.gate)
    real = w.gate._lock_path.with_name("real.lock")
    os.replace(w.gate._lock_path, real)
    os.symlink(real, w.gate._lock_path)


_MATRIX = {
    "absent": (_prep_absent, gm.GATE_NEVER_OPENED),
    "lock_without_journal": (_prep_lock_only, gm.GATE_NEVER_OPENED),
    "close_last": (_prep_close_journal, gm.GATE_CLOSED_JOURNAL),
    "marker": (_prep_marker, gm.GATE_CLOSED_MARKER),
    "corrupt_line": (_prep_corrupt, gm.GATE_JOURNAL_INVALID),
    "truncated_line": (_prep_truncated, gm.GATE_JOURNAL_INVALID),
    "journal_symlink": (_prep_journal_symlink, gm.GATE_JOURNAL_INVALID),
    "marker_is_directory": (_prep_marker_dir, gm.GATE_CLOSED_MARKER),
    "other_epoch": (_prep_other_epoch, gm.GATE_JOURNAL_INVALID),
    "other_manifest": (_prep_other_manifest, gm.GATE_JOURNAL_INVALID),
    "lock_symlink": (_prep_lock_symlink, gm.GATE_LOCK_INVALID),
}


@pytest.mark.parametrize("case", sorted(_MATRIX))
def test_s2_gate_matrix_refuses_open_without_any_ppl_write(tmp_path, case):
    prep, code = _MATRIX[case]
    w = World(tmp_path, open_gate=False)
    prep(w)
    before = w.ledger_sha()
    order = w.buy(admission=_approved(), cycle_id="c")
    assert order.status is OrderStatus.REJECTED
    assert order.reject_code == code
    assert w.ledger_sha() == before
    assert w.sim._positions == {}
    outcomes = [e for e in get_admission_ledger().events() if e["event"] == "ADMISSION_OUTCOME"]
    assert [(o["write_result"], o["anomaly"]) for o in outcomes] == [
        ("REJECTED_GATE_CLOSED", code)
    ]
    assert any(code in n for n in w.notes)


def test_s2_marker_lstat_error_is_closed(world, monkeypatch):
    real = Path.lstat

    def lstat(self, *a, **k):
        if self == world.gate._closed_marker:
            raise PermissionError(errno.EACCES, "injected")
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "lstat", lstat)
    before = world.ledger_sha()
    order = world.buy()
    assert order.reject_code == gm.GATE_CLOSED_MARKER
    assert world.ledger_sha() == before


def test_s2_unexpected_read_error_is_typed_refusal(world, monkeypatch):
    real = os.open

    def bad_open(path, flags, *a, **k):
        if Path(path) == world.gate._lock_path:
            raise OSError(errno.EIO, "injected")
        return real(path, flags, *a, **k)

    monkeypatch.setattr(gm.os, "open", bad_open)
    before = world.ledger_sha()
    order = world.buy()
    assert order.reject_code == gm.GATE_READ_ERROR
    assert world.ledger_sha() == before


def test_s3_open_gate_admits_and_records_filled(world):
    order = world.buy(admission=_approved(), cycle_id="c")
    assert order.status is OrderStatus.FILLED and order.reject_code is None
    assert world.opened() == [order.order_id]
    assert world.journal_actions() == ["OPEN"]
    outcomes = [e for e in get_admission_ledger().events() if e["event"] == "ADMISSION_OUTCOME"]
    assert [o["write_result"] for o in outcomes] == ["FILLED"]
    assert _flock_free_elsewhere(world.gate._lock_path)


# ============================================================ S4 / S8 (AC3b, AC5)


class _BlockingTicker:
    def __init__(self, price: float = 100.0):
        self.price = price
        self.entered = threading.Event()
        self.release = threading.Event()
        self.spot = self

    def fetch_ticker(self, symbol):
        self.entered.set()
        assert self.release.wait(GUARD)
        return {"last": self.price}


def _adm_count(sim) -> int:
    with sim._lock:
        return sim._ppl_admissions_in_flight


def test_s4_close_during_price_fetch_refuses_and_counts_admission(world):
    ticker = _BlockingTicker(100.0)
    world.sim._mexc = ticker
    th, box = _start(lambda: world.buy("BTC/USDT", price=100.0), "admitter")
    assert ticker.entered.wait(GUARD)
    assert _adm_count(world.sim) == 1  # S8: >0 during the fetch window
    body = world.observe()
    assert body["admissions_in_flight"]["value"] == 1
    assert world.other_gate().close(decided_by="t", reason="r") is True
    ticker.release.set()
    order = _join(th, box)
    assert order.reject_code == gm.GATE_CLOSED_MARKER
    assert world.opened() == []
    assert _adm_count(world.sim) == 0


class _Boom(Exception):
    pass


def _exit_cases():
    def short_circuit(w):
        verdict = AdmissionVerdict(
            decision=AdmissionDecision.REJECTED,
            level=AdmissionLevel.A,
            n_at_check=0,
            hard_max_at_check=10,
        )
        return w.buy(admission=verdict, cycle_id="c")

    def price_unavailable(w):
        return w.buy(price=0.0)

    def ohlcv_deviation(w):
        w.sim._mexc = type("M", (), {"spot": type("S", (), {"fetch_ticker": staticmethod(lambda s: {"last": 1.0})})()})()
        return w.buy(price=100.0)

    def gate_refusal(w):
        w.other_gate().close(decided_by="t", reason="r")
        return w.buy()

    def duplicate(w):
        w.buy()
        return w.buy()

    def capital(w):
        return w.sim.place_market_order("BTC/USDT", "BUY", 0.5, current_price=100.0)

    def filled(w):
        return w.buy()

    return {
        "short_circuit": (short_circuit, None),
        "price_unavailable": (price_unavailable, None),
        "ohlcv_deviation": (ohlcv_deviation, None),
        "gate_refusal": (gate_refusal, None),
        "duplicate": (duplicate, None),
        "capital": (capital, None),
        "filled": (filled, None),
    }


@pytest.mark.parametrize("case", sorted(_exit_cases()))
def test_s8_admissions_counter_back_to_zero_on_every_return(world, case):
    action, _ = _exit_cases()[case]
    action(world)
    assert _adm_count(world.sim) == 0


@pytest.mark.parametrize(
    "where", ["enter_admission", "fetch_price", "commit_open", "exit_admission"]
)
@pytest.mark.parametrize("exc_type", [_Boom, KeyboardInterrupt, SystemExit])
def test_s8_admissions_counter_back_to_zero_on_exceptions(world, monkeypatch, where, exc_type):
    exc = exc_type("injected")

    def boom(*a, **k):
        raise exc

    if where == "enter_admission":
        monkeypatch.setattr(world.sim, "_enter_admission", boom)
    elif where == "fetch_price":
        monkeypatch.setattr(world.sim, "_fetch_price", boom)
    elif where == "commit_open":
        monkeypatch.setattr(world.runtime, "commit_open", boom)
    else:
        monkeypatch.setattr(world.sim, "_exit_admission", boom)
    with pytest.raises(exc_type) as info:
        world.buy(price=100.0)
    assert info.value is exc
    assert _adm_count(world.sim) == 0
    assert _flock_free_elsewhere(world.gate._lock_path)


# ============================================================ S7 (AC4)


def test_s7_close_is_never_gated(world):
    for sym in ("A/USDT", "B/USDT", "C/USDT"):
        assert world.buy(sym).status is OrderStatus.FILLED
    assert world.other_gate().close(decided_by="t", reason="r") is True
    world.close("A/USDT", 105.0, "TP")
    world.close("B/USDT", 90.0, "SL")
    world.close("C/USDT", 100.0, "TIMEOUT")
    closed = [e for e in world.events() if e.event_type == "POSITION_CLOSED"]
    assert len(closed) == 3
    assert world.sim._positions == {}
    with world.sim._lock:
        assert world.sim._ppl_started_transitions == set()
    assert world.buy("D/USDT").reject_code == gm.GATE_CLOSED_MARKER


def test_s7_close_works_even_with_gate_flock_held_elsewhere(world):
    assert world.buy().status is OrderStatus.FILLED
    _spawn_holder(world)
    world.close()
    assert world.sim._positions == {}


# ============================================================ S9 / S18 (TT1-TT10)


def _counters(world):
    body = world.observe()
    return body, body["lifecycle_transitions_in_flight"], body["lifecycle_transitions_detail"]


def test_tt1_normal_open_close_counts_zero(world):
    world.buy()
    world.close()
    body, item, detail = _counters(world)
    assert item["status"] == qp.OBSERVED and item["value"] == 0
    assert type(item["value"]) is int
    assert detail["value"] == []
    assert body["admissions_in_flight"] == qp.observed(
        0, f"simulator counter under sim._lock ({COUNTERS_PROTOCOL})"
    )


def test_tt2_refusal_before_append_keeps_the_key(world, monkeypatch):
    before = world.ledger_sha()

    def refuse(**facts):
        raise ValueError("semantic refusal before append (injected)")

    monkeypatch.setattr(world.runtime, "commit_open", refuse)
    with pytest.raises(ValueError):
        world.buy()
    monkeypatch.undo()
    assert world.ledger_sha() == before
    body, item, detail = _counters(world)
    assert item["value"] == 1  # never removed after a refusal before append
    assert [d["class"] for d in detail["value"]] == [qp.TRANSITION_NOT_APPLIED]


def _fail_fsync_once(world, monkeypatch, times: int):
    real = os.fsync
    state = {"n": 0}

    def flaky(fd):
        st = os.fstat(fd)
        if stat.S_ISREG(st.st_mode) and state["n"] < times:
            try:
                target = os.readlink(f"/proc/self/fd/{fd}")
            except OSError:
                target = ""
            if target.endswith(".jsonl") and "epochs" in target:
                state["n"] += 1
                raise OSError(errno.EIO, "injected fsync failure")
        return real(fd)

    monkeypatch.setattr(os, "fsync", flaky)


def test_tt3_visible_append_then_successful_retry_counts_zero(world, monkeypatch):
    _fail_fsync_once(world, monkeypatch, times=1)
    order = world.buy()
    monkeypatch.undo()
    assert order.status is OrderStatus.FILLED
    _, item, _ = _counters(world)
    assert item["value"] == 0


def test_tt4_visible_append_retry_fails_is_applied_durable_not_memory(world, monkeypatch):
    _fail_fsync_once(world, monkeypatch, times=2)
    with pytest.raises(OSError):
        world.buy()
    monkeypatch.undo()
    body, item, detail = _counters(world)
    assert item["value"] == 1
    assert [d["class"] for d in detail["value"]] == [qp.TRANSITION_APPLIED_DURABLE_NOT_MEMORY]
    assert body["memory_matches_durable"]["value"] is False
    # OPEN déchiré: a new OPEN on the symbol is refused by the durable duplicate check
    assert world.buy().status is OrderStatus.REJECTED
    assert len(world.opened()) == 1


def _tear_close(world, monkeypatch):
    world.buy()
    real = world.runtime.consistent_view
    state = {"n": 0}

    def view_after_commit():
        state["n"] += 1
        if state["n"] == 2:  # 1st: _durable_close lookup; 2nd: after commit_close
            raise RuntimeError("injected failure after durable CLOSE")
        return real()

    monkeypatch.setattr(world.runtime, "consistent_view", view_after_commit)
    with pytest.raises(RuntimeError):
        world.close("BTC/USDT", 105.0, "TP")
    monkeypatch.undo()


def test_tt5_torn_close_idempotent_retry_resolves(world, monkeypatch):
    _tear_close(world, monkeypatch)
    _, item, detail = _counters(world)
    assert item["value"] == 1
    assert [d["class"] for d in detail["value"]] == [qp.TRANSITION_APPLIED_DURABLE_NOT_MEMORY]
    n_events = len(world.events())
    world.close("BTC/USDT", 999.0, "TP")  # retry replays the durable facts
    assert len(world.events()) == n_events  # ALREADY_EXISTS, no second event
    closed = [e for e in world.events() if e.event_type == "POSITION_CLOSED"]
    assert float(closed[0].payload["exit_price"]) != 999.0
    _, item, _ = _counters(world)
    assert item["value"] == 0


def test_tt6_torn_close_without_new_trigger_stays_counted(world, monkeypatch):
    _tear_close(world, monkeypatch)
    for _ in range(3):
        body, item, _ = _counters(world)
        assert item["value"] == 1
    assert body["memory_matches_durable"]["value"] is False


def test_tt7_unreadable_ledger_keeps_value_and_is_unresolved(world, monkeypatch):
    def refuse(**facts):
        raise ValueError("injected")

    monkeypatch.setattr(world.runtime, "commit_open", refuse)
    with pytest.raises(ValueError):
        world.buy()
    monkeypatch.undo()
    with open(world.epoch_file(), "ab") as fh:
        fh.write(b'{"torn":')  # no final newline: whole epoch unreadable
    body, item, detail = _counters(world)
    assert item["value"] == 1
    assert [d["class"] for d in detail["value"]] == [qp.TRANSITION_UNRESOLVED]
    assert body["ledger_sha256"]["status"] == qp.UNRESOLVED
    assert body["durable_open_positions"]["status"] == qp.UNRESOLVED
    assert body["memory_matches_durable"]["status"] == qp.UNRESOLVED


def test_tt8_without_declaration_values_identical_to_base(tmp_path):
    w = World(tmp_path, wire_gate=False)
    body = w.observe()
    assert body["lifecycle_transitions_in_flight"] == qp.not_applicable(
        "PPL_AUTHORITY path performs OPEN/CLOSE entirely under simulator._lock; "
        "the legacy counter is never incremented there and is not read as zero"
    )
    assert body["admissions_in_flight"] == qp.unknown(
        "no admission-in-flight counter exists in the runtime"
    )
    assert "lifecycle_transitions_detail" not in body
    assert body["runtime_consults_gate"]["status"] == qp.UNKNOWN


def test_tt8b_without_declaration_unreadable_view_raises_as_v12(tmp_path):
    """Review D-02: without a counters declaration (C1a not wired), an
    unreadable authority view keeps the v1.2 behaviour of 7cd4c4e9: the
    StoreCorruptionError of consistent_view() propagates out of
    observe_runtime; nothing is downgraded to UNRESOLVED silently."""
    w = World(tmp_path, wire_gate=False)
    assert w.buy().status is OrderStatus.FILLED
    with open(w.epoch_file(), "ab") as fh:
        fh.write(b'{"torn":')  # no final newline: whole epoch unreadable
    with pytest.raises(StoreCorruptionError):
        w.observe()


def test_tt8c_code_sha_without_counters_protocol_keeps_v12(tmp_path):
    """Same v1.2 behaviour when a gate is wired but the declaration does not
    name PPL-QUIESCENCE-COUNTERS-V1 (counters not published)."""
    w = World(tmp_path)
    w.sim.ppl_gate_wiring_v1 = {
        k: v for k, v in w.sim.ppl_gate_wiring_v1.items() if k != "counters_protocol"
    }
    assert "admissions_in_flight" in w.observe()  # v1.2 field, not the counter
    assert "lifecycle_transitions_detail" not in w.observe()
    with open(w.epoch_file(), "ab") as fh:
        fh.write(b'{"torn":')
    with pytest.raises(StoreCorruptionError):
        w.observe()


def test_tt9_adapter_reports_the_exact_value_and_bool_is_refused(world):
    body = world.observe()
    assert qp._count(body["lifecycle_transitions_in_flight"]) == 0
    forged = dict(body["lifecycle_transitions_in_flight"], value=False)
    assert qp._count(forged) is None
    with world.sim._lock:
        world.sim._ppl_admissions_in_flight = True  # forged bool in memory
    assert world.observe()["admissions_in_flight"]["status"] == qp.UNRESOLVED


def test_tt10_interrupted_and_succession_keep_unknown():
    import paper_trading.ppl_interrupted_succession as succ

    assert "lifecycle_transitions_in_flight" in succ._UNKNOWN_FIELDS


# ============================================================ S10 (AC7)


def test_s10_declaration_bound_to_constructor_code_sha(world):
    decl = world.sim.ppl_gate_wiring_v1
    assert decl["protocol"] == "PPL-GATE-WIRING-V1"
    assert decl["code_sha"] == CODE and decl["code_sha_provenance"] == "CONSTRUCTOR_DECLARED"
    assert decl["consults_gate_under_lock"] is True
    assert decl["counters_protocol"] == COUNTERS_PROTOCOL
    assert decl["module_sha256_provenance"] == "FILE_BYTES_AT_CONSTRUCTION"
    assert set(decl["module_sha256"]) == {
        "paper_trading/mexc_simulator.py",
        "paper_trading/ppl_admission_gate.py",
    }
    body = world.observe()
    assert body["runtime_consults_gate"] == qp.observed(
        True, f"RUNTIME_DECLARATION:PPL-GATE-WIRING-V1@{CODE}"
    )
    assert body["code_sha_provenance"]["value"] == "CONSTRUCTOR_DECLARED"
    assert body["lifecycle_transitions_in_flight"]["status"] == qp.OBSERVED


def test_s10_other_code_sha_is_unresolved_and_counters_unpublished(tmp_path):
    w = World(tmp_path, code_sha="d" * 40)
    body = w.observe()
    assert body["runtime_consults_gate"]["status"] == qp.UNRESOLVED
    assert body["lifecycle_transitions_in_flight"]["status"] == qp.NOT_APPLICABLE
    assert body["admissions_in_flight"]["status"] == qp.UNKNOWN


def test_s10_gate_without_code_sha_publishes_no_declaration(tmp_path):
    w = World(tmp_path, code_sha=None)
    assert not hasattr(w.sim, "ppl_gate_wiring_v1")  # never copied from manifest
    assert w.observe()["runtime_consults_gate"]["status"] == qp.UNKNOWN
    assert w.buy().status is OrderStatus.FILLED  # the gate is still consulted


def test_s10_no_gate_no_declaration(tmp_path):
    w = World(tmp_path, wire_gate=False)
    assert not hasattr(w.sim, "ppl_gate_wiring_v1")
    assert w.observe()["runtime_consults_gate"]["status"] == qp.UNKNOWN


# ============================================================ S11 (AC8)

_ADVISOR_CHILD = """
import fcntl, json, os, sys, time
from paper_trading import ppl_quiescence_proof as qp
lock_path, out_path = sys.argv[1], sys.argv[2]
fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
ident = qp.current_process_identity(
    process_instance_id="inst-%d" % os.getpid(), lock_path=lock_path, lock_fd=fd)
tmp = out_path + ".tmp"
with open(tmp, "w") as fh:
    json.dump(ident, fh)
os.replace(tmp, out_path)
deadline = time.monotonic() + 60
while time.monotonic() < deadline:
    time.sleep(0.05)
"""


def _spawn_advisor(tmp: Path):
    out = tmp / "ident.json"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-c",
            f"import sys; sys.path.insert(0, {str(ROOT)!r})\n" + _ADVISOR_CHILD,
            str(tmp / "advisor.lock"),
            str(out),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _children.append(proc)
    deadline = time.monotonic() + 15
    while not out.exists():
        assert proc.poll() is None and time.monotonic() < deadline
        time.sleep(0.02)
    return proc, json.loads(out.read_text())


def _assess_after_stop(w: World, *, close_gate=True, edit=None):
    proc, ident = _spawn_advisor(w.tmp)
    if close_gate:
        assert w.other_gate().close(decided_by="t", reason="r") is True
    if edit:
        edit(w)
    body = w.observe(ident)
    rec = qp.write_observation(w.proofs, body, now=NOW)
    qp.write_seal(w.proofs, rec, body, now=NOW + 0.5)
    proc.send_signal(signal.SIGKILL)
    proc.wait(timeout=10)
    qp.write_witness(
        w.proofs, rec, body, store_root=w.authority_root, epoch_id=EPOCH, now=NOW + 1
    )
    result = qp.assess(
        w.proofs,
        manifest=w.manifest,
        manifest_sha256=w.manifest_sha,
        store_root=w.authority_root,
        now=NOW + 5,
        max_age_s=900.0,
    )
    return result, body


def test_s11_full_quiescence_reachable_only_with_every_condition(world):
    world.buy()
    world.close()
    result, body = _assess_after_stop(world)
    assert result.quiescent is True, result.blocking
    adapted = qp.to_epoch_rotation_quiescence(result, body)
    assert adapted.quiescent and adapted.authority_transitions_in_flight == 0


def _with_open_position(w):
    w.buy("Z/USDT")


def _with_transition(w):
    with w.sim._lock:
        w.sim._ppl_started_transitions.add(("OPEN", "FORGED"))


def _with_admission(w):
    with w.sim._lock:
        w.sim._ppl_admissions_in_flight = 1


@pytest.mark.parametrize(
    "variant", ["gate_open", "open_position", "transition", "admission", "no_declaration"]
)
def test_s11_removing_any_condition_blocks_quiescence(tmp_path, variant):
    w = World(tmp_path, wire_gate=variant != "no_declaration")
    if variant == "open_position":
        _with_open_position(w)  # before the gate closes
    edit = {
        "transition": _with_transition,
        "admission": _with_admission,
    }.get(variant)
    result, body = _assess_after_stop(w, close_gate=variant != "gate_open", edit=edit)
    assert result.quiescent is False
    with pytest.raises(qp.QuiescenceRefusal):
        qp.to_epoch_rotation_quiescence(result, body)


# ============================================================ S12 (AC9)


class _SpyEnv(dict):
    touched: list = []

    def __getitem__(self, k):
        self.touched.append(k)
        return super().__getitem__(k)

    def get(self, k, d=None):
        self.touched.append(k)
        return super().get(k, d)


def test_s12_gate_paths_never_read_the_environment(world, monkeypatch):
    for var, val in (
        ("PB_MAX_POSITIONS", "1"),
        ("MEXC_SIM_FEE", "0.5"),
        ("MEXC_SIM_SLIP", "0.5"),
    ):
        monkeypatch.setenv(var, val)
    touched: list = []
    monkeypatch.setattr(gm.os, "getenv", lambda *a, **k: touched.append(a) or None)
    spy = _SpyEnv(os.environ)
    spy.touched = touched
    monkeypatch.setattr(gm.os, "environ", spy)
    with world.gate.admission_hold(lock_timeout_s=0.25) as chk:
        assert chk.permitted
    assert world.other_gate().drain_barrier(timeout_s=0.1).status == gm.NOT_CLOSED
    monkeypatch.undo()
    assert touched == []
    source = (ROOT / "paper_trading" / "ppl_admission_gate.py").read_text()
    assert "os.getenv" not in source and "os.environ" not in source


def test_s12_gate_result_identical_whatever_the_fee_and_ceiling_env(tmp_path, monkeypatch):
    results = []
    for value in ("1", "999"):
        monkeypatch.setenv("PB_MAX_POSITIONS", value)
        w = World(tmp_path / value)
        with w.gate.admission_hold(lock_timeout_s=0.25) as chk:
            results.append(tuple(chk))
    assert results[0] == results[1] == (True, gm.GATE_OPEN, "")


# ============================================================ S13 (AC10)


def test_s13_lock_order_stress_no_deadlock(world):
    stop = threading.Event()
    errors: list = []

    def admitter(prefix):
        i = 0
        while not stop.is_set() and i < 40:
            sym = f"{prefix}{i}/USDT"
            try:
                if world.buy(sym).status is OrderStatus.FILLED:
                    world.close(sym)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            i += 1

    def observer():
        while not stop.is_set():
            body = world.observe()
            for name in ("admissions_in_flight", "lifecycle_transitions_in_flight"):
                v = body[name]["value"]
                if type(v) is not int or v < 0:
                    errors.append((name, v))

    threads = [
        threading.Thread(target=admitter, args=("A",), daemon=True),
        threading.Thread(target=admitter, args=("B",), daemon=True),
        threading.Thread(target=observer, daemon=True),
    ]
    for th in threads:
        th.start()
    time.sleep(0.2)
    assert world.other_gate().close(decided_by="t", reason="r") is True
    assert world.other_gate().drain_barrier(timeout_s=GUARD).status == gm.DRAINED
    stop.set()
    for th in threads:
        th.join(GUARD)
        assert not th.is_alive(), "deadlock suspected"
    assert errors == []
    body = world.observe()
    assert body["admissions_in_flight"]["value"] == 0
    assert body["lifecycle_transitions_in_flight"]["value"] == 0
    assert body["memory_matches_durable"]["value"] is True


# ============================================================ S14


def test_s14_constructor_refusals(tmp_path):
    w = World(tmp_path)
    rt, gate = w.runtime, w.gate
    with pytest.raises(GateWiringRefusal):
        MexcSimulator(admission_gate=gate)  # LEGACY
    with pytest.raises(GateWiringRefusal):
        MexcSimulator(gate_wiring_code_sha=CODE)  # code sha without gate
    for bad_gate in (
        AdmissionGate(w.gate_path, paper_epoch_id="OTHER", manifest_sha256=w.manifest_sha),
        AdmissionGate(w.gate_path, paper_epoch_id=EPOCH, manifest_sha256="f" * 64),
    ):
        with pytest.raises(GateWiringRefusal):
            MexcSimulator(
                lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
                authority_runtime=rt,
                admission_gate=bad_gate,
            )
    for bad_sha in ("XYZ", "C1" * 20, "c1" * 19, 123):
        with pytest.raises(GateWiringRefusal):
            MexcSimulator(
                lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
                authority_runtime=rt,
                admission_gate=gate,
                gate_wiring_code_sha=bad_sha,
            )
    with pytest.raises(ValueError):  # existing rule: PPL_AUTHORITY needs a runtime
        MexcSimulator(
            lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY, admission_gate=gate
        )


# ============================================================ S16 (zero write)

_FORBIDDEN_FLAGS = os.O_CREAT | os.O_WRONLY | os.O_RDWR | os.O_TRUNC | os.O_APPEND


class _SyscallSpy:
    def __init__(self, monkeypatch):
        self.violations: list = []
        real_open = os.open

        def spy_open(path, flags, *a, **k):
            if flags & _FORBIDDEN_FLAGS:
                self.violations.append(("os.open", str(path), flags))
            return real_open(path, flags, *a, **k)

        monkeypatch.setattr(os, "open", spy_open)
        for name in ("mkdir", "makedirs", "unlink", "rename", "replace", "fsync",
                     "ftruncate", "utime", "write", "remove", "rmdir", "symlink"):
            real = getattr(os, name)
            monkeypatch.setattr(os, name, self._deny(f"os.{name}", real))
        monkeypatch.setattr(Path, "mkdir", self._deny("Path.mkdir", Path.mkdir))
        monkeypatch.setattr(Path, "write_bytes", self._deny("Path.write_bytes", Path.write_bytes))
        import builtins

        real_bopen = builtins.open

        def spy_bopen(file, mode="r", *a, **k):
            if any(c in mode for c in "wax+"):
                self.violations.append(("open", str(file), mode))
            return real_bopen(file, mode, *a, **k)

        monkeypatch.setattr(builtins, "open", spy_bopen)

    def _deny(self, name, real):
        def wrapper(*a, **k):
            self.violations.append((name, a))
            return real(*a, **k)

        return wrapper


def _snapshot(directory: Path):
    if not directory.exists():
        return None
    out = {}
    for entry in sorted(os.scandir(directory), key=lambda e: e.name):
        st = os.lstat(entry.path)
        digest = None
        if stat.S_ISREG(st.st_mode):
            with open(entry.path, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
        out[entry.name] = (
            stat.S_IFMT(st.st_mode), st.st_size, st.st_ino, st.st_mtime_ns,
            st.st_ctime_ns, digest,
        )
    return out


_ZERO_CASES = dict(_MATRIX)
_ZERO_CASES["open"] = (lambda w: _open_gate(w.gate), gm.GATE_OPEN)


def _prep_lock_absent_journal_open(w: World):
    _open_gate(w.gate)
    os.unlink(w.gate._lock_path)


_ZERO_CASES["lock_absent_journal_open"] = (_prep_lock_absent_journal_open, gm.GATE_NEVER_OPENED)


@pytest.mark.parametrize("case", sorted(_ZERO_CASES))
def test_s16_admission_hold_writes_nothing(tmp_path, monkeypatch, case):
    prep, code = _ZERO_CASES[case]
    w = World(tmp_path, open_gate=False)
    prep(w)
    gate_dir = w.gate_path.parent
    before = _snapshot(gate_dir)
    with monkeypatch.context() as m:
        spy = _SyscallSpy(m)
        with w.gate.admission_hold(lock_timeout_s=0.1) as chk:
            pass
    assert spy.violations == []
    assert chk.code == code
    assert _snapshot(gate_dir) == before
    if case == "absent":
        assert before is None and not gate_dir.exists()
    if case == "lock_absent_journal_open":
        assert not w.gate._lock_path.exists()


@pytest.mark.parametrize("status", ["NOT_CLOSED", "DRAINED", "DRAINED_NO_LOCK", "DRAIN_TIMEOUT", "DRAIN_ERROR"])
def test_s16_drain_barrier_writes_nothing(tmp_path, monkeypatch, status):
    w = World(tmp_path, open_gate=status != "DRAINED_NO_LOCK")
    if status != "NOT_CLOSED":
        if status == "DRAINED_NO_LOCK":
            w.gate_path.parent.mkdir(parents=True)
            w.gate._closed_marker.write_bytes(b"{}")
        else:
            assert w.other_gate().close(decided_by="t", reason="r") is True
    if status == "DRAIN_TIMEOUT":
        _spawn_holder(w)
    if status == "DRAIN_ERROR":
        real = w.gate._lock_path.with_name("real.lock")
        os.replace(w.gate._lock_path, real)
        os.symlink(real, w.gate._lock_path)
    gate_dir = w.gate_path.parent
    before = _snapshot(gate_dir)
    with monkeypatch.context() as m:
        spy = _SyscallSpy(m)
        result = w.gate.drain_barrier(timeout_s=0.1)
    assert spy.violations == []
    assert result.status == status.replace("_NO_LOCK", "")
    assert _snapshot(gate_dir) == before


# ============================================================ S17 (ledger readers)


def test_s17_ledger_readers_are_label_invariant(world, tmp_path):
    from research_data import stress_d1_capture as cap
    from research_data import stress_d1_snapshot_audit as aud
    from paper_trading.admission_ledger import AdmissionLedger
    from datetime import datetime, timezone

    world.buy(admission=_approved(), cycle_id="c")  # FILLED pair
    world.other_gate().close(decided_by="t", reason="r")
    world.buy("ETH/USDT", admission=_approved(1), cycle_id="c")  # gate refusal pair
    raw = (tmp_path / "admission.jsonl").read_bytes()
    assert b"REJECTED_GATE_CLOSED" in raw
    twin = raw.replace(b"REJECTED_GATE_CLOSED", b"REJECTED_INSUFFICIENT_CAPITAL")
    (tmp_path / "a.jsonl").write_bytes(raw)
    (tmp_path / "b.jsonl").write_bytes(twin)

    def view(path: Path):
        led = AdmissionLedger(str(path))
        rows = led.events()
        strip = lambda r: {k: v for k, v in r.items() if k != "write_result"}  # noqa: E731
        records = {k: [] for k in cap.KINDS}
        records["admission_ledger"] = rows
        start = datetime(2000, 1, 1, tzinfo=timezone.utc)
        end = datetime(2100, 1, 1, tzinfo=timezone.utc)
        return (
            [strip(r) for r in rows],
            [(strip(a), strip(o) if o else None) for a, o in led.pairs()],
            cap._coverage(records, start, end),
            aud.count_summary({k: list(v) for k, v in records.items()}),
        )

    va, vb = view(tmp_path / "a.jsonl"), view(tmp_path / "b.jsonl")
    assert va == vb
    assert "ADMISSION_ORPHAN_OR_UNPAIRED" not in json.dumps(va[2], default=str)
    assert WriteResult("REJECTED_GATE_CLOSED") is WriteResult.REJECTED_GATE_CLOSED


def test_s17_operator_stage_copy_is_label_invariant(world, tmp_path, monkeypatch):
    """S17, reader `research_data/stress_d1_operator_stage.acquire_one`: the
    byte-prefix copy of `admission_ledger.jsonl`, run on the twin ledgers in
    tmp_path only (SOURCE redirected; `main()` itself is not run: it requires
    root and writes under /var/lib).  Outputs equal up to the label bytes."""
    from research_data import stress_d1_operator_stage as stage

    world.buy(admission=_approved(), cycle_id="c")
    world.other_gate().close(decided_by="t", reason="r")
    world.buy("ETH/USDT", admission=_approved(1), cycle_id="c")
    rows = [json.loads(line) for line in (tmp_path / "admission.jsonl").read_bytes().splitlines()]
    assert any(r.get("write_result") == "REJECTED_GATE_CLOSED" for r in rows)
    for i, row in enumerate(rows):  # inside the reader's fixed UTC day window
        row["ts"] = f"2026-10-10T12:00:{i:02d}+00:00"
    raw = b"".join(json.dumps(r, sort_keys=True).encode() + b"\n" for r in rows)
    label_a, label_b = b"REJECTED_GATE_CLOSED", b"REJECTED_INSUFFICIENT_CAPITAL"
    twin = raw.replace(label_a, label_b)
    variable = {"source_inode", "source_device", "source_prefix_bytes", "source_prefix_sha256",
                "selected_sha256", "selected_bytes", "offset_index_sha256"}

    def run(name: str, data: bytes):
        src = tmp_path / f"src-{name}"
        src.mkdir()
        (src / "admission_ledger.jsonl").write_bytes(data)
        out = tmp_path / f"out-{name}"
        out.mkdir()
        monkeypatch.setattr(stage, "SOURCE", src)
        spec = next(s for s in stage.SPECS if s[0] == "admission_ledger")
        result = stage.acquire_one(out, *spec)
        return result, (out / "admission_ledger.jsonl").read_bytes()

    (ra, copy_a), (rb, copy_b) = run("a", raw), run("b", twin)
    assert {k: v for k, v in ra.items() if k not in variable} == {
        k: v for k, v in rb.items() if k not in variable
    }
    assert ra["selected_rows"] == ra["source_total_rows"] == len(rows)
    assert copy_a == raw and copy_b == twin  # verbatim, label never interpreted
    assert copy_a.replace(label_a, label_b) == copy_b


# ============================================================ §8.4 interleavings


def _admit_paused(world: World, monkeypatch, point: str, symbol: str = "BTC/USDT"):
    pts = Points(world, point, monkeypatch)
    th, box = _start(lambda: world.buy(symbol), "admitter")
    pts.wait()
    return pts, th, box


def _drain_async(world: World, timeout: float = GUARD):
    def run():
        result = world.other_gate().drain_barrier(timeout_s=timeout)
        # what is durable at the very moment DRAINED returns (chain validated)
        return result, [e.trade_id for e in world.events() if e.event_type == "POSITION_OPENED"]

    return _start(run, "drainer")


def _still_running(th: threading.Thread, seconds: float = 0.3) -> bool:
    th.join(seconds)
    return th.is_alive()


CLOSERS = ["thread", "process"]


@pytest.mark.parametrize("closer", CLOSERS)
def test_i1_marker_before_t0_refuses(world, closer):
    out = _close_now(world, closer)
    if closer == "thread":
        _join(*out)
    order = world.buy()
    assert order.reject_code == gm.GATE_CLOSED_MARKER
    assert world.opened() == []
    assert world.other_gate().drain_barrier(timeout_s=0).status == gm.DRAINED


@pytest.mark.parametrize("closer", CLOSERS)
@pytest.mark.parametrize("point", ["P1", "P2"])
def test_i2_i3_marker_before_t3_refuses(world, monkeypatch, closer, point):
    pts, th, box = _admit_paused(world, monkeypatch, point)
    closing = _close_now(world, closer)
    if closer == "thread":
        _join(*closing)  # deterministic: close() fully returned before release
    dth, dbox = _drain_async(world)
    pts.release.set()
    order = _join(th, box)
    # P1: the flock is free, close() also appended CLOSE -> refused at t2.
    # P2: the admitter holds the flock, close() could only create the marker
    #     -> refused at t3.  Either way: refused, nothing durable.
    expected = gm.GATE_CLOSED_JOURNAL if point == "P1" else gm.GATE_CLOSED_MARKER
    assert order.reject_code == expected
    # Observed CLOSE record (contract §8.4, rows I2/I3 as revised after review):
    # P1 -> appended by close() before t2; P2 -> close() timed out (1 s) on the
    # admitter's flock, returned True, and wrote no CLOSE record.
    expected_actions = ["OPEN", "CLOSE"] if point == "P1" else ["OPEN"]
    assert world.journal_actions() == expected_actions
    result, durable = _join(dth, dbox)
    assert result.status == gm.DRAINED and durable == []
    assert world.opened() == []


@pytest.mark.parametrize("closer", CLOSERS)
@pytest.mark.parametrize("point", ["P3", "P4"])
def test_i4_i5_n1_n4_admitted_open_persisted_after_marker_before_drained(
    world, monkeypatch, closer, point
):
    pts, th, box = _admit_paused(world, monkeypatch, point)
    closing = _close_now(world, closer, patient=True)
    after_marker = time.time()  # wall clock strictly after the marker exists
    assert world.opened() == []  # N1: marker exists, the OPEN is not yet durable
    dth, dbox = _drain_async(world)
    assert _still_running(dth), "drain must wait for the admitted commit"
    pts.release.set()
    order = _join(th, box)
    assert order.status is OrderStatus.FILLED  # admitted at t3, before closure
    result, durable_at_drain = _join(dth, dbox)
    assert result.status == gm.DRAINED
    assert durable_at_drain == [order.order_id]  # durable before DRAINED returned
    event = next(e for e in world.events() if e.trade_id == order.order_id)
    # N4: opened_at was fixed before t3, i.e. before the marker existed, yet the
    # event became durable after it: the timestamp proves no ordering.
    assert event.timestamp < after_marker
    if closer == "thread":
        th_c, box_c = closing
        assert _join(th_c, box_c) is True
        assert world.journal_actions() == ["OPEN", "CLOSE"]  # CLOSE after the OPEN
    assert world.buy("ETH/USDT").reject_code == gm.GATE_CLOSED_MARKER


@pytest.mark.parametrize("closer", CLOSERS)
def test_i6_marker_at_p5_open_already_durable(world, monkeypatch, closer):
    pts, th, box = _admit_paused(world, monkeypatch, "P5")
    assert len(world.opened()) == 1  # durable before the marker
    closing = _close_now(world, closer)
    dth, dbox = _drain_async(world)
    assert _still_running(dth)
    pts.release.set()
    order = _join(th, box)
    assert order.status is OrderStatus.FILLED
    result, durable = _join(dth, dbox)
    assert result.status == gm.DRAINED and durable == [order.order_id]
    if closer == "thread":
        _join(*closing)


@pytest.mark.parametrize("closer", CLOSERS)
def test_i7_marker_after_release_drains_immediately(world, monkeypatch, closer):
    pts, th, box = _admit_paused(world, monkeypatch, "P6")
    assert _flock_free_elsewhere(world.gate._lock_path)
    closing = _close_now(world, closer)
    assert world.other_gate().drain_barrier(timeout_s=0).status == gm.DRAINED
    pts.release.set()
    assert _join(th, box).status is OrderStatus.FILLED
    if closer == "thread":
        _join(*closing)


def _hold_flock_in_thread(world: World):
    fd = os.open(world.gate._lock_path, os.O_RDONLY)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


@pytest.mark.parametrize("holder", ["thread", "process"])
def test_i8_marker_with_flock_held_refuses_at_t1(world, holder):
    assert world.other_gate().close(decided_by="t", reason="r") is True
    fd = _hold_flock_in_thread(world) if holder == "thread" else None
    if holder == "process":
        _spawn_holder(world)
    t0 = time.monotonic()
    order = world.buy()
    assert order.reject_code == gm.GATE_CLOSED_MARKER
    assert time.monotonic() - t0 < 0.25
    if fd is not None:
        os.close(fd)


@pytest.mark.parametrize("holder", ["thread", "process"])
def test_i9_flock_held_elsewhere_times_out_closed(world, holder):
    fd = _hold_flock_in_thread(world) if holder == "thread" else None
    if holder == "process":
        _spawn_holder(world)
    order = world.buy()
    assert order.reject_code == gm.GATE_LOCK_TIMEOUT
    assert world.opened() == []
    assert world.other_gate().drain_barrier(timeout_s=0).status == gm.NOT_CLOSED
    if fd is not None:
        os.close(fd)


@pytest.mark.parametrize("closer", CLOSERS)
def test_i10_n2_close_returns_before_drain(world, monkeypatch, closer):
    pts, th, box = _admit_paused(world, monkeypatch, "P4")
    if closer == "thread":
        th_c, box_c = _close_now(world, closer)
        assert _join(th_c, box_c) is True  # N2: close() says durable...
    else:
        assert _close_now(world, closer) == {"durable": True}
    assert world.journal_actions() == ["OPEN"]  # ...without a CLOSE record
    assert world.other_gate().drain_barrier(timeout_s=0.1).status == gm.DRAIN_TIMEOUT
    pts.release.set()
    assert _join(th, box).status is OrderStatus.FILLED
    assert world.other_gate().drain_barrier(timeout_s=5).status == gm.DRAINED


def _replace_lock(world: World, how: str):
    lock = world.gate._lock_path
    if how == "process":
        res = _py(
            "import os, sys; os.unlink(sys.argv[1]); open(sys.argv[1], 'w').close()",
            str(lock),
        )
        assert res.returncode == 0, res.stderr
    else:
        os.unlink(lock)
        open(lock, "w").close()


@pytest.mark.parametrize("how", ["thread", "process"])
def test_i12_n6_lock_replaced_after_flock_is_detected(world, monkeypatch, how):
    pts, th, box = _admit_paused(world, monkeypatch, "PF")
    _replace_lock(world, how)
    pts.release.set()
    order = _join(th, box)
    assert order.reject_code == gm.GATE_LOCK_IDENTITY_CHANGED
    assert world.opened() == []


def test_i12_lock_replaced_before_open_is_harmless(world, monkeypatch):
    """Replacement at P1 precedes the admitter's own open(): it locks the new
    inode, and the identity check passes (documented in the report)."""
    pts, th, box = _admit_paused(world, monkeypatch, "P1")
    _replace_lock(world, "thread")
    pts.release.set()
    assert _join(th, box).status is OrderStatus.FILLED


def test_i12_drain_detects_replacement(world, monkeypatch):
    assert world.other_gate().close(decided_by="t", reason="r") is True
    drainer_gate = world.gate
    pts = Points(world, "PF", monkeypatch, thread="drainer")
    th, box = _start(lambda: drainer_gate.drain_barrier(timeout_s=1), "drainer")
    pts.wait()
    _replace_lock(world, "thread")
    pts.release.set()
    assert _join(th, box).status == gm.DRAIN_ERROR


def test_n6_existing_open_close_lock_does_not_detect_replacement(world):
    old = _hold_flock_in_thread(world)
    _replace_lock(world, "thread")
    with world.other_gate()._locked(timeout=0.1):  # acquired on the NEW inode
        pass
    os.close(old)


@pytest.mark.parametrize("point", ["P1", "P2", "P3", "P4", "P5"])
def test_i13_observer_is_serialised_with_the_admission(world, monkeypatch, point):
    pts, th, box = _admit_paused(world, monkeypatch, point)
    oth, obox = _start(world.observe, "observer")
    assert _still_running(oth), "observer must wait for sim._lock"
    pts.release.set()
    order = _join(th, box)
    body = _join(oth, obox)
    assert order.status is OrderStatus.FILLED
    assert body["durable_open_positions"]["value"] == [order.order_id]
    assert body["memory_matches_durable"]["value"] is True


# ============================================================ N3, N5


def test_n3_drained_says_nothing_about_non_consulting_processes(tmp_path):
    w = World(tmp_path / "a")
    assert w.other_gate().close(decided_by="t", reason="r") is True
    assert w.other_gate().drain_barrier(timeout_s=1).status == gm.DRAINED
    unguarded = World(tmp_path / "b", wire_gate=False)
    assert unguarded.buy().status is OrderStatus.FILLED  # OPEN after DRAINED


def test_n5_removing_the_marker_reopens_the_gate(world):
    fd = _hold_flock_in_thread(world)  # close() cannot append its CLOSE record
    assert world.other_gate().close(decided_by="t", reason="r") is True
    os.close(fd)
    assert world.journal_actions() == ["OPEN"]
    os.unlink(world.gate._closed_marker)  # disk tampering (trust boundary R2)
    with world.other_gate().admission_hold(lock_timeout_s=0.25) as chk:
        assert chk.code == gm.GATE_OPEN


# ============================================================ S6 (AC3d, erratum)


@pytest.mark.parametrize("closer", CLOSERS)
def test_s6_no_new_admission_after_close_and_no_durable_open_after_drained(world, closer):
    attempts: list = []
    stop = threading.Event()
    closed_at = {}

    def loop():
        i = 0
        while not stop.is_set() and i < 400:
            started = time.monotonic()
            order = world.buy(f"S{i}/USDT")
            attempts.append((started, order.status, order.reject_code))
            i += 1

    th = threading.Thread(target=loop, name="admitter-loop", daemon=True)
    th.start()
    deadline = time.monotonic() + GUARD
    while sum(1 for a in attempts if a[1] is OrderStatus.FILLED) < 3:
        assert time.monotonic() < deadline
        time.sleep(0.005)
    if closer == "process":
        assert _child_gate(world, "close") == {"durable": True}
    else:
        assert world.other_gate().close(decided_by="t", reason="c1a") is True
    closed_at["t"] = time.monotonic()
    # (a) every check that starts after close() returned is a gate refusal
    if closer == "process":
        drained = _child_gate(world, "drain:10")
        assert drained[0] == gm.DRAINED
    else:
        assert world.other_gate().drain_barrier(timeout_s=10).status == gm.DRAINED
    opened_at_drain = world.opened()  # chain validated by load_epoch
    time.sleep(0.2)
    stop.set()
    th.join(GUARD)
    assert not th.is_alive()
    after = [a for a in attempts if a[0] > closed_at["t"]]
    assert after, "the loop must keep trying after the closure"
    assert all(a[1] is OrderStatus.REJECTED and a[2] in gm.GATE_REFUSAL_CODES for a in after)
    # (b) no additional durable OPEN after DRAINED
    assert world.opened() == opened_at_drain
    # (c) OPENs persisted between close() and DRAINED are recorded, not errors
    in_between = [
        a for a in attempts if a[1] is OrderStatus.FILLED and a[0] <= closed_at["t"]
    ]
    assert len(world.opened()) == len(in_between)


# ============================================================ H1-H9 (C-01)


def _lock_inode(world):
    st = os.stat(world.gate._lock_path)
    return st.st_dev, st.st_ino


def _assert_released(world):
    assert _fds_on_inode(*_lock_inode(world)) == []
    assert _flock_free_elsewhere(world.gate._lock_path)


@pytest.mark.parametrize(
    "exc", [OSError(errno.EIO, "H1 injected"), KeyboardInterrupt("H3"), SystemExit(4)],
    ids=["H1_oserror", "H3_keyboardinterrupt", "H4_systemexit"],
)
def test_h1_h3_h4_body_exception_propagates_unchanged(world, monkeypatch, exc):
    fds_before = sorted(os.listdir("/proc/self/fd"))

    def boom(**facts):
        raise exc

    monkeypatch.setattr(world.runtime, "commit_open", boom)
    with pytest.raises(type(exc)) as info:
        world.buy()
    assert info.value is exc
    _assert_released(world)
    assert sorted(os.listdir("/proc/self/fd")) == fds_before
    assert _adm_count(world.sim) == 0
    assert world.opened() == []


def test_h2_visible_open_retry_failure_propagates(world, monkeypatch):
    _fail_fsync_once(world, monkeypatch, times=2)
    with pytest.raises(OSError, match="injected fsync failure"):
        world.buy()
    monkeypatch.undo()
    _assert_released(world)
    assert _adm_count(world.sim) == 0


@pytest.mark.parametrize("exc_type", [KeyboardInterrupt, SystemExit])
def test_h5_baseexception_while_waiting_for_flock_is_not_a_timeout(
    world, monkeypatch, exc_type
):
    _spawn_holder(world)
    exc = exc_type("H5")

    def sleep(_):
        raise exc

    monkeypatch.setattr(gm.time, "sleep", sleep)
    fds_before = sorted(os.listdir("/proc/self/fd"))
    with pytest.raises(exc_type) as info:
        world.buy()
    monkeypatch.undo()
    assert info.value is exc
    assert sorted(os.listdir("/proc/self/fd")) == fds_before
    assert _adm_count(world.sim) == 0


def test_h6_systemexit_during_journal_read_propagates(world, monkeypatch):
    exc = SystemExit(6)

    def records():
        raise exc

    monkeypatch.setattr(world.gate, "_records", records)
    with pytest.raises(SystemExit) as info:
        world.buy()
    assert info.value is exc
    monkeypatch.undo()
    _assert_released(world)


def test_h7_oserror_on_lock_open_is_a_read_error_refusal(world, monkeypatch):
    real = os.open

    def bad(path, flags, *a, **k):
        if Path(path) == world.gate._lock_path:
            raise OSError(errno.EIO, "H7")
        return real(path, flags, *a, **k)

    monkeypatch.setattr(gm.os, "open", bad)
    order = world.buy()
    monkeypatch.undo()
    assert order.reject_code == gm.GATE_READ_ERROR


def test_h8_close_error_after_real_close_keeps_body_exception_and_releases(
    world, monkeypatch
):
    """Erratum §15 #3: the injected error happens AFTER the real close(2)."""
    dev, ino = _lock_inode(world)
    real_close = os.close
    calls = []

    def close_then_fail(fd):
        try:
            st = os.fstat(fd)
            ours = (st.st_dev, st.st_ino) == (dev, ino)
        except OSError:
            ours = False
        real_close(fd)  # descriptor and flock released, as Linux does
        if ours:
            calls.append(fd)
            raise OSError(errno.EIO, "H8 injected after close")

    body_exc = _Boom("body")

    def boom(**facts):
        raise body_exc

    monkeypatch.setattr(world.runtime, "commit_open", boom)
    monkeypatch.setattr(gm.os, "close", close_then_fail)
    with pytest.raises(_Boom) as info:
        world.buy()
    monkeypatch.undo()
    assert info.value is body_exc
    assert len(calls) == 1  # never a second close()
    assert _fds_on_inode(dev, ino) == []  # descriptor proven released (inode)
    assert _flock_free_elsewhere(world.gate._lock_path)  # flock proven free
    assert world.other_gate().close(decided_by="t", reason="r") is True
    assert world.other_gate().drain_barrier(timeout_s=0).status == gm.DRAINED


def test_h8_neg_error_before_close_is_not_a_proof(world, monkeypatch):
    """Documentary only (not an acceptance criterion): an OSError raised BEFORE
    the real close(2) matches no Linux behaviour and leaves the flock held."""
    dev, ino = _lock_inode(world)
    real_close = os.close

    def fail_first(fd):
        try:
            st = os.fstat(fd)
            ours = (st.st_dev, st.st_ino) == (dev, ino)
        except OSError:
            ours = False
        if ours:
            raise OSError(errno.EIO, "simulated before close")
        real_close(fd)

    monkeypatch.setattr(gm.os, "close", fail_first)
    with world.gate.admission_hold(lock_timeout_s=0.25) as chk:
        assert chk.permitted
    monkeypatch.undo()
    leaked = _fds_on_inode(dev, ino)
    assert leaked and not _flock_free_elsewhere(world.gate._lock_path)
    for fd in leaked:
        os.close(int(fd))


def test_h9_arbitrary_body_exception_is_never_suppressed(world):
    hold = world.gate.admission_hold(lock_timeout_s=0.25)
    check = hold.__enter__()
    assert check.permitted
    err = RuntimeError("H9")
    assert hold.__exit__(RuntimeError, err, None) is False
    _assert_released(world)
    with pytest.raises(RuntimeError) as info:
        with world.gate.admission_hold(lock_timeout_s=0.25):
            raise err
    assert info.value is err


# ============================================================ S20 / I11 / N7 (C-03)

_KILL_CHILD = r"""
import os, signal, sys
root, tmp, mode = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, root)
os.chdir(tmp)
os.environ["PAPER_ADMISSION_LEDGER"] = os.path.join(tmp, "child-admission.jsonl")
from pathlib import Path
from paper_trading.durable_event_store import DurableEventStore
from paper_trading.mexc_simulator import MexcSimulator
from paper_trading.paper_authority import PaperLifecycleAuthority
from paper_trading.ppl_admission_gate import AdmissionGate
from paper_trading.ppl_authority_runtime import (EpochRotationQuiescence,
    PPLAuthorityRuntime, authority_manifest_sha256, build_experiment_manifest)
m = build_experiment_manifest(paper_epoch_id=%(epoch)r, created_at=1.0,
    initial_virtual_capital=1000.0, code_sha=%(code)r,
    config_snapshot_hash="cfg-hash-c1a", legacy_log_bytes=b"",
    quiescence=EpochRotationQuiescence(0, 0, 0, True),
    predecessor_authority_epoch_id="PRED-EPOCH")
rt = PPLAuthorityRuntime(manifest=m, store=DurableEventStore(Path(tmp) / "authority"))
state = rt.bind(now=%(now)r)
gate = AdmissionGate(Path(tmp) / "gate" / "gate.jsonl", paper_epoch_id=m.paper_epoch_id,
    manifest_sha256=authority_manifest_sha256(m))
sim = MexcSimulator(lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
    authority_runtime=rt, admission_gate=gate, gate_wiring_code_sha=%(code)r)
sim._capital = state.available_cash
def die():
    os.kill(os.getpid(), signal.SIGKILL)
def durable_append(path, line):
    if mode == "zero":
        die()
    with path.open("ab") as stream:
        if mode == "half":
            stream.write(line[: len(line) // 2]); stream.flush(); die()
        stream.write(line); stream.flush()
        if mode == "full_fsync":
            os.fsync(stream.fileno())
        die()
DurableEventStore._durable_append = staticmethod(durable_append)
sim.place_market_order("BTC/USDT", "BUY", 10.0, current_price=100.0)
print("NOT KILLED")
""" % {"epoch": EPOCH, "code": CODE, "now": NOW}


@pytest.mark.parametrize("mode", ["zero", "half", "full_nofsync", "full_fsync"])
def test_s20_i11_n7_sigkill_during_append_recovery(world, tmp_path, mode):
    res = subprocess.run(
        [sys.executable, "-I", "-c", _KILL_CHILD, str(ROOT), str(tmp_path), mode],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert res.returncode == -signal.SIGKILL, res.stdout + res.stderr
    # DRAINED: no admitter is executing any more — and nothing more (N7)
    assert world.other_gate().close(decided_by="t", reason="after kill") is True
    assert world.other_gate().drain_barrier(timeout_s=1).status == gm.DRAINED
    path = world.epoch_file()
    sha_before = hashlib.sha256(path.read_bytes()).hexdigest()
    # Rule §4.8-1: validate the whole chain BEFORE any conclusion
    try:
        events = DurableEventStore(world.authority_root).load_epoch(EPOCH)
        chain_ok = True
    except StoreCorruptionError:
        events, chain_ok = None, False
    body = world.observe()
    if mode == "half":
        assert chain_ok is False  # E1: LEDGER_CORRUPT -> UNRESOLVED
        assert body["ledger_sha256"]["status"] == qp.UNRESOLVED
        assert body["durable_open_positions"]["status"] == qp.UNRESOLVED
    else:
        assert chain_ok is True
        assert qp.is_observed(body, "ledger_sha256")
        opened = [e for e in events if e.event_type == "POSITION_OPENED"]
        if mode == "zero":
            assert opened == []  # E0: NOT_APPLIED
        else:
            assert len(opened) == 1  # E2/E3: VISIBLE_DURABILITY_UNCONFIRMED
    # no repair, no truncation, no resync by any check above
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha_before


def test_s20_torn_gate_journal_reads_invalid(world, tmp_path):
    res = _py(
        """
        import os, signal, sys
        with open(sys.argv[1], "ab") as fh:
            fh.write(b'{"seq": 2, "act')
            fh.flush()
        os.kill(os.getpid(), signal.SIGKILL)
        """,
        str(world.gate_path),
    )
    assert res.returncode == -signal.SIGKILL
    assert world.buy().reject_code == gm.GATE_JOURNAL_INVALID
