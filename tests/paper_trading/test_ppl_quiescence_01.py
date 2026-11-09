"""PPL-QUIESCENCE-01 lot A — hermetic tests (synthetic data, temp dirs only).

Child processes are fresh ``subprocess`` interpreters with bounded waits and
guaranteed kill+wait cleanup (no fork, no Pool): the cause of the initial
TEST REGRESSION GATE stall of #565 is not demonstrated, so nothing here can
wait unboundedly.
"""

from __future__ import annotations

import errno
import json
import os
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from paper_trading import ppl_quiescence_proof as qp
from paper_trading.admission_ledger import (
    AdmissionLedger,  # noqa: F401  (import sanity)
)
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
EPOCH = "QUIESCENCE-TEST-EPOCH"

pytestmark = pytest.mark.skipif(
    not Path("/proc/self/stat").exists(), reason="requires Linux /proc"
)


# ----------------------------------------------------------------- fixtures


class World:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.authority_root = tmp / "authority"
        self.proof_dir = tmp / "proofs"
        self.manifest = build_experiment_manifest(
            paper_epoch_id=EPOCH,
            created_at=1.0,
            initial_virtual_capital=1000.0,
            code_sha="code-sha-test",
            config_snapshot_hash="cfg-hash-test",
            legacy_log_bytes=b"",
            quiescence=EpochRotationQuiescence(0, 0, 0, True),
            predecessor_authority_epoch_id="PRED-EPOCH",
        )
        self.manifest_sha = authority_manifest_sha256(self.manifest)
        self.runtime = PPLAuthorityRuntime(
            manifest=self.manifest, store=DurableEventStore(self.authority_root)
        )
        state = self.runtime.bind(now=NOW)
        self.sim = MexcSimulator(
            lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
            authority_runtime=self.runtime,
        )
        self.sim._capital = state.available_cash
        self.sim._initial_capital = 1000.0
        self.gate = AdmissionGate(
            tmp / "gate.jsonl",
            paper_epoch_id=EPOCH,
            manifest_sha256=self.manifest_sha,
        )
        self.store = qp.ProofStore(
            self.proof_dir, forbidden_roots=[self.authority_root]
        )

    def open_position(self, symbol: str = "BTC/USDT") -> None:
        order = self.sim.place_market_order(symbol, "BUY", 10.0, current_price=100.0)
        assert order.status.value == "FILLED"

    def close_position(self, symbol: str = "BTC/USDT") -> None:
        self.sim._close_position(symbol, 101.0, "TP")

    def identity(self, **overrides):
        ident = qp.current_process_identity(
            process_instance_id="inst-parent",
            lock_path=str(self.tmp / "advisor.lock"),
            lock_fd=None,
        )
        ident.update(overrides)
        return ident

    def observe(self, identity=None):
        return qp.observe_runtime(
            self.sim,
            self.runtime,
            manifest=self.manifest,
            manifest_sha256=self.manifest_sha,
            gate=self.gate,
            identity=identity or self.identity(),
            source_sha="source-sha-test",
        )

    def assess(self, now=NOW + 5, max_age=900.0):
        return qp.assess(
            self.store,
            manifest=self.manifest,
            manifest_sha256=self.manifest_sha,
            store_root=self.authority_root,
            now=now,
            max_age_s=max_age,
        )


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


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


def _run(code: str, *args: str, timeout: float = 30.0) -> subprocess.CompletedProcess:
    script = f"import sys; sys.path.insert(0, {str(ROOT)!r})\n" + textwrap.dedent(code)
    return subprocess.run(
        [sys.executable, "-I", "-c", script, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


_ADVISOR_CHILD = """
import fcntl, json, os, sys, time
from paper_trading import ppl_quiescence_proof as qp
lock_path, out_path, hold = sys.argv[1], sys.argv[2], sys.argv[3] == "hold"
fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
if hold:
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


def _spawn_advisor(tmp: Path, *, hold: bool = True):
    lock = tmp / "advisor.lock"
    out = tmp / f"ident-{'h' if hold else 'f'}.json"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-c",
            f"import sys; sys.path.insert(0, {str(ROOT)!r})\n" + _ADVISOR_CHILD,
            str(lock),
            str(out),
            "hold" if hold else "free",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _children.append(proc)
    deadline = time.monotonic() + 15
    while not out.exists():
        if proc.poll() is not None or time.monotonic() > deadline:
            raise AssertionError("advisor child did not publish its identity")
        time.sleep(0.02)
    return proc, json.loads(out.read_text()), lock


def _kill(proc: subprocess.Popen) -> None:
    proc.send_signal(signal.SIGKILL)
    proc.wait(timeout=10)


def _seal_ready(world: World, identity):
    """Close the gate durably, observe, return (result, body)."""
    assert world.gate.close(decided_by="test", reason="quiescence test") is True
    body = world.observe(identity)
    return qp.write_observation(world.store, body, now=NOW), body


# ------------------------------------------------------------------- values


def test_unknown_statuses_never_carry_a_value():
    for make in (qp.unknown, qp.not_available, qp.not_applicable, qp.unresolved):
        item = make("why")
        assert qp.is_value(item) and item["value"] is None
    assert not qp.is_value({"status": "UNKNOWN", "value": 0, "provenance": "x"})
    assert not qp.is_value({"status": "OBSERVED", "value": 0})
    assert qp._count(qp.unknown("x")) is None
    assert qp._count(qp.observed(True, "x")) is None  # bool is not a count
    assert qp._count(qp.observed(0, "x")) == 0


def test_module_has_no_numeric_defaults_and_no_runtime_imports():
    source = (ROOT / "paper_trading" / "ppl_quiescence_proof.py").read_text()
    assert "import advisor_loop" not in source and "core.advisor_loop" not in source
    assert "mexc_simulator" not in source.replace("mexc_simulator.py", "")
    assert "PB_MAX_POSITIONS" not in source.replace('"PB_MAX_POSITIONS" not in', "")


# ------------------------------------------------------------- observation


def test_observation_of_current_runtime_keeps_unknowns(world):
    body = world.observe()
    assert body["pending_order_count"] == qp.observed(
        0, "len(simulator._orders where status=PENDING) under lock"
    )
    assert body["lifecycle_transitions_in_flight"]["status"] == qp.NOT_APPLICABLE
    assert body["lifecycle_transitions_in_flight"]["value"] is None
    assert body["runtime_consults_gate"]["status"] == qp.UNKNOWN
    assert body["admissions_in_flight"]["status"] == qp.UNKNOWN
    assert body["memory_matches_durable"]["value"] is True
    assert body["durable_open_positions"]["value"] == []
    assert body["gate_state"]["value"] == "CLOSED"
    assert body["gate_marker_sha256"]["status"] == qp.NOT_AVAILABLE
    assert all(qp.is_value(v) for v in body.values())


def test_observation_requires_authority_simulator(world):
    legacy = MexcSimulator()
    with pytest.raises(qp.QuiescenceRefusal):
        qp.observe_runtime(
            legacy,
            world.runtime,
            manifest=world.manifest,
            manifest_sha256=world.manifest_sha,
            gate=world.gate,
            identity=world.identity(),
        )


def test_memory_durable_divergence_is_reported_not_repaired(world):
    world.open_position()
    world.sim._positions.clear()  # durable OPEN without memory (OSError path)
    body = world.observe()
    assert body["memory_matches_durable"]["value"] is False
    assert (
        body["durable_open_positions"]["value"] == ["BTC-USDT"]
        or body["durable_open_positions"]["value"]
    )
    assert len(world.runtime.consistent_view().projection.open_positions) == 1


def test_ledger_binding_changes_with_every_event(world):
    first = world.observe()["ledger_sha256"]["value"]
    world.open_position()
    second = world.observe()["ledger_sha256"]["value"]
    world.close_position()
    third = world.observe()["ledger_sha256"]["value"]
    assert len({first, second, third}) == 3


def test_lock_order_is_simulator_then_runtime(world):
    events: list[str] = []

    class Spy:
        def __init__(self, name, inner):
            self.name, self.inner = name, inner

        def __enter__(self):
            events.append(f"+{self.name}")
            return self.inner.__enter__()

        def __exit__(self, *exc):
            events.append(f"-{self.name}")
            return self.inner.__exit__(*exc)

    world.sim._lock = Spy("sim", world.sim._lock)
    world.runtime._lock = Spy("runtime", world.runtime._lock)
    world.observe()
    assert events[:2] == ["+sim", "+runtime"]
    assert events.index("-runtime") < events.index("-sim")


def test_observations_stay_coherent_under_concurrent_open_close(world):
    errors: list[str] = []
    stop = threading.Event()

    def trader(symbol: str) -> None:
        try:
            for _ in range(4):
                world.sim.place_market_order(symbol, "BUY", 10.0, current_price=100.0)
                world.sim._close_position(symbol, 101.0, "TP")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"trader {symbol}: {exc!r}")

    def observer() -> None:
        try:
            while not stop.is_set():
                body = world.observe()
                if body["memory_matches_durable"]["value"] is not True:
                    errors.append("incoherent observation")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"observer: {exc!r}")

    threads = [threading.Thread(target=trader, args=(f"S{i}/USDT",)) for i in range(3)]
    watcher = threading.Thread(target=observer)
    watcher.start()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
        assert not t.is_alive()
    stop.set()
    watcher.join(timeout=30)
    assert not watcher.is_alive()
    assert errors == []


# --------------------------------------------------------------- persistence


def _record(store, n=1, **kw):
    body = {"x": qp.observed(n, "t")}
    return store.append(
        qp.KIND_OBSERVATION,
        body,
        observed_at=NOW,
        clock_provenance="t",
        max_age_s=900.0,
        **kw,
    )


def test_chain_append_and_strict_scan(tmp_path):
    store = qp.ProofStore(tmp_path / "p")
    a, b = _record(store, 1), _record(store, 2)
    chain = store.scan()
    assert chain.status == "OK" and chain.all_confirmed
    assert [r.seq for r in chain.records] == [1, 2]
    assert chain.records[1].envelope["prev_record_sha256"] == a.record_sha256
    assert b.seq == 2


def test_concurrent_threads_get_unique_contiguous_sequences(tmp_path):
    store = qp.ProofStore(tmp_path / "p")
    seen: list[int] = []
    errors: list[str] = []

    def writer(k: int) -> None:
        try:
            for i in range(5):
                seen.append(_record(qp.ProofStore(tmp_path / "p"), k * 10 + i).seq)
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=writer, args=(k,)) for k in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
        assert not t.is_alive()
    assert errors == []
    assert sorted(seen) == list(range(1, 31))
    chain = store.scan()
    assert chain.status == "OK" and chain.all_confirmed and len(chain.records) == 30


def test_concurrent_processes_serialize(tmp_path):
    code = """
    import sys
    from paper_trading import ppl_quiescence_proof as qp
    s = qp.ProofStore(sys.argv[1])
    for i in range(8):
        s.append(qp.KIND_OBSERVATION, {"x": qp.observed(i, "t")}, observed_at=2e9,
                 clock_provenance="t", max_age_s=900.0)
    """
    procs = [
        subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-c",
                f"import sys; sys.path.insert(0, {str(ROOT)!r})\n"
                + textwrap.dedent(code),
                str(tmp_path / "p"),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        for _ in range(3)
    ]
    _children.extend(procs)
    for proc in procs:
        assert proc.wait(timeout=60) == 0, proc.stderr.read().decode()
    chain = qp.ProofStore(tmp_path / "p").scan()
    assert chain.status == "OK" and len(chain.records) == 24 and chain.all_confirmed


def test_writer_lock_timeout_is_bounded(tmp_path):
    store = qp.ProofStore(tmp_path / "p", lock_timeout=0.2)
    fd = store._acquire_writer_lock()
    try:
        started = time.monotonic()
        with pytest.raises(qp.PersistBlocked):
            _record(qp.ProofStore(tmp_path / "p", lock_timeout=0.2))
        assert time.monotonic() - started < 5
    finally:
        os.close(fd)


def test_partial_and_corrupt_files_are_unresolved_never_skipped(tmp_path):
    store = qp.ProofStore(tmp_path / "p")
    rec = _record(store)
    (tmp_path / "p" / ".tmp-orphan").write_bytes(b"{partial")  # ignored
    assert store.scan().status == "OK"
    path = rec.path
    good = path.read_bytes()

    path.write_bytes(good[: len(good) // 2])  # torn JSON
    assert store.scan().status == "UNRESOLVED"
    with pytest.raises(qp.PersistBlocked):
        _record(store)  # no repair, no overwrite

    path.write_bytes(good.replace(b'"x"', b'"y"'))  # hash mismatch
    assert store.scan().status == "UNRESOLVED"

    path.write_bytes(good[:-1] + b',"seq":1}')  # duplicate key
    assert store.scan().status == "UNRESOLVED"

    path.write_bytes(good.replace(b'"observed_at":2000000000.0', b'"observed_at":NaN'))
    assert store.scan().status == "UNRESOLVED"

    path.unlink()
    path.symlink_to(tmp_path / "elsewhere")
    assert store.scan().status == "UNRESOLVED"


def test_gap_and_fork_are_unresolved(tmp_path):
    store = qp.ProofStore(tmp_path / "p")
    _record(store, 1)
    second = _record(store, 2)
    _record(store, 3)
    second.path.unlink()
    assert store.scan().status == "UNRESOLVED"  # gap

    store2 = qp.ProofStore(tmp_path / "q")
    first = _record(store2, 1)
    clone = first.path.with_name(
        first.path.name.replace(first.record_sha256[:16], "f" * 16)
    )
    clone.write_bytes(first.path.read_bytes())
    assert store2.scan().status == "UNRESOLVED"  # fork


def test_failed_file_fsync_publishes_nothing_and_consumes_no_sequence(
    tmp_path, monkeypatch
):
    store = qp.ProofStore(tmp_path / "p")
    _record(store, 1)

    def boom(self, fd):
        raise OSError(errno.ENOSPC, "no space")

    monkeypatch.setattr(qp.ProofStore, "_fsync_fd", boom)
    with pytest.raises(qp.PersistBlocked):
        _record(store, 2)
    monkeypatch.undo()
    assert [r.seq for r in store.scan().records] == [1]
    assert _record(store, 3).seq == 2  # no artificial gap
    assert not [n for n in os.listdir(tmp_path / "p") if n.startswith(".tmp-")]


@pytest.mark.parametrize("err", [errno.EIO, errno.EROFS, errno.ENOSPC])
def test_unavailable_disk_on_publish_is_blocked_not_present(tmp_path, monkeypatch, err):
    store = qp.ProofStore(tmp_path / "p")

    def boom(self, source, target):
        raise OSError(err, "disk")

    monkeypatch.setattr(qp.ProofStore, "_link", boom)
    with pytest.raises(qp.PersistBlocked):
        _record(store)
    monkeypatch.undo()
    assert store.scan().status == "EMPTY"


def test_directory_disappearing_blocks_the_writer(tmp_path):
    store = qp.ProofStore(tmp_path / "p")
    _record(store)
    for child in (tmp_path / "p").iterdir():
        child.unlink()
    (tmp_path / "p").rmdir()
    with pytest.raises(qp.PersistBlocked):
        _record(store)


def test_directory_must_not_overlap_authority_roots(tmp_path):
    authority = tmp_path / "authority"
    authority.mkdir()
    for bad in (authority, authority / "sub", tmp_path):
        with pytest.raises(qp.PersistBlocked):
            qp.ProofStore(bad, forbidden_roots=[authority])
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "real")
    (tmp_path / "real").mkdir()
    with pytest.raises(qp.PersistBlocked):
        qp.ProofStore(link)


_READER = """
import sys
from paper_trading import ppl_quiescence_proof as qp
c = qp.ProofStore(sys.argv[1]).scan()
print(c.status, [(r.seq, r.confirmed) for r in c.records])
"""

_RECOVER = """
import sys
from paper_trading import ppl_quiescence_proof as qp
print(qp.ProofStore(sys.argv[1]).recover())
"""


def test_visible_publication_then_dir_fsync_failure_retry_and_other_process(
    tmp_path, monkeypatch
):
    directory = tmp_path / "p"
    store = qp.ProofStore(directory)
    calls = {"n": 0}
    real = qp.ProofStore._fsync_directory

    def flaky(self):
        calls["n"] += 1
        raise OSError(errno.EIO, "directory fsync failed")

    monkeypatch.setattr(qp.ProofStore, "_fsync_directory", flaky)
    with pytest.raises(qp.PersistUncertain) as info:
        _record(store, 1)
    assert info.value.seq == 1
    monkeypatch.setattr(qp.ProofStore, "_fsync_directory", real)

    # The record is visible, yet another process must NOT treat it as durable proof.
    out = _run(_READER, str(directory))
    assert out.stdout.strip() == "OK [(1, False)]", out.stderr

    # A recovery attempt that still cannot sync fails closed and uses no sequence.
    monkeypatch.setattr(qp.ProofStore, "_fsync_directory", flaky)
    with pytest.raises(qp.PersistBlocked):
        qp.ProofStore(directory).recover()
    with pytest.raises(qp.PersistBlocked):
        _record(store, 2)
    monkeypatch.setattr(qp.ProofStore, "_fsync_directory", real)
    assert [(r.seq, r.confirmed) for r in store.scan().records] == [(1, False)]

    # Retry from a third process with a healthy disk: confirmed, then readable elsewhere.
    out = _run(_RECOVER, str(directory))
    assert out.stdout.strip() == "(1,)", out.stderr
    out = _run(_READER, str(directory))
    assert out.stdout.strip() == "OK [(1, True)]"
    # Next sequence continues without a gap or a re-published duplicate.
    assert _record(qp.ProofStore(directory), 2).seq == 2
    assert qp.ProofStore(directory).scan().all_confirmed


def test_append_after_uncertain_record_recovers_it_first(tmp_path, monkeypatch):
    store = qp.ProofStore(tmp_path / "p")
    real = qp.ProofStore._fsync_directory
    monkeypatch.setattr(
        qp.ProofStore,
        "_fsync_directory",
        lambda self: (_ for _ in ()).throw(OSError(errno.EIO, "x")),
    )
    with pytest.raises(qp.PersistUncertain):
        _record(store, 1)
    monkeypatch.setattr(qp.ProofStore, "_fsync_directory", real)
    assert _record(store, 2).seq == 2
    chain = store.scan()
    assert [r.confirmed for r in chain.records] == [True, True]
    receipt = json.loads(
        next((tmp_path / "p").glob("quiescence-00000001-*.ok")).read_text()
    )
    assert receipt["recovered"] is True


def test_receipt_failure_after_durable_directory_is_still_uncertain_then_recovered(
    tmp_path, monkeypatch
):
    store = qp.ProofStore(tmp_path / "p")
    real = qp.ProofStore._write_receipt

    def no_receipt(self, seq, sha, *, recovered):
        raise OSError(errno.EIO, "receipt")

    monkeypatch.setattr(qp.ProofStore, "_write_receipt", no_receipt)
    with pytest.raises(qp.PersistUncertain):
        _record(store)
    monkeypatch.setattr(qp.ProofStore, "_write_receipt", real)
    assert not store.scan().all_confirmed
    assert store.recover() == (1,)
    assert store.scan().all_confirmed
    assert store.recover() == ()  # idempotent


def test_proof_with_uncertain_record_is_refused(world, monkeypatch):
    body = world.observe()
    monkeypatch.setattr(
        qp.ProofStore,
        "_fsync_directory",
        lambda self: (_ for _ in ()).throw(OSError(errno.EIO, "x")),
    )
    with pytest.raises(qp.PersistUncertain):
        qp.write_observation(world.store, body, now=NOW)
    monkeypatch.undo()
    result = world.assess()
    assert result.verdict == qp.V_UNCERTAIN and not result.quiescent


def test_crash_mid_write_leaves_only_ignored_tmp(tmp_path):
    code = """
    import os, sys
    from paper_trading import ppl_quiescence_proof as qp
    class Dying(qp.ProofStore):
        def _link(self, source, target):
            os.kill(os.getpid(), 9)
    Dying(sys.argv[1]).append(qp.KIND_OBSERVATION, {"x": qp.observed(1, "t")},
        observed_at=2e9, clock_provenance="t", max_age_s=900.0)
    """
    out = _run(code, str(tmp_path / "p"))
    assert out.returncode == -signal.SIGKILL
    store = qp.ProofStore(tmp_path / "p")
    assert store.scan().status == "EMPTY"
    assert _record(store).seq == 1


# ---------------------------------------------------------- stop evidence


def test_live_holder_is_running_not_stopped(world, tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    rec = qp.probe_stop_evidence(ident)
    assert rec["lock_probe"]["value"] == "HELD"
    assert rec["pid_probe"]["value"] == "ALIVE"
    assert rec["process_stopped"] == {
        **rec["process_stopped"],
        "status": qp.OBSERVED,
        "value": False,
    }
    _kill(proc)


def test_free_lock_path_alone_never_proves_stop(tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path, hold=False)  # alive, lock FREE
    rec = qp.probe_stop_evidence(ident)
    assert rec["lock_probe"]["value"] == "FREE_SAME_IDENTITY"
    assert rec["pid_probe"]["value"] == "ALIVE"
    assert rec["process_stopped"]["value"] is False
    _kill(proc)
    # pid gone + same inode free -> stopped
    assert qp.probe_stop_evidence(ident)["process_stopped"]["value"] is True


def test_sigkill_with_same_free_inode_is_stopped(tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    _kill(proc)
    rec = qp.probe_stop_evidence(ident)
    assert rec["pid_probe"]["value"] == "GONE"
    assert rec["lock_probe"]["value"] == "FREE_SAME_IDENTITY"
    assert rec["process_stopped"] == {**rec["process_stopped"], "value": True}


def test_replaced_lock_file_is_unknown(tmp_path):
    proc, ident, lock = _spawn_advisor(tmp_path)
    _kill(proc)
    lock.unlink()
    lock.write_text("")  # new inode, free
    rec = qp.probe_stop_evidence(ident)
    assert rec["lock_probe"]["status"] == qp.UNKNOWN
    assert rec["process_stopped"]["status"] == qp.UNKNOWN
    assert rec["process_stopped"]["value"] is None


def test_recycled_inode_number_is_not_the_same_identity(tmp_path):
    proc, ident, lock = _spawn_advisor(tmp_path)
    _kill(proc)
    old_ino = lock.stat().st_ino
    lock.unlink()
    time.sleep(0.05)
    lock.write_text("")
    rec = qp.probe_stop_evidence(ident)
    # whatever the filesystem did with the inode number, ctime/mtime differ
    assert rec["lock_probe"]["status"] == qp.UNKNOWN, old_ino == lock.stat().st_ino


def test_touched_lock_file_is_ambiguous_not_free(tmp_path):
    proc, ident, lock = _spawn_advisor(tmp_path)
    _kill(proc)
    time.sleep(0.05)
    os.utime(lock)
    assert qp.probe_stop_evidence(ident)["lock_probe"]["status"] == qp.UNKNOWN


def test_absent_lock_file_is_unknown(tmp_path):
    proc, ident, lock = _spawn_advisor(tmp_path)
    _kill(proc)
    lock.unlink()
    rec = qp.probe_stop_evidence(ident)
    assert rec["lock_probe"]["status"] == qp.UNKNOWN
    assert rec["process_stopped"]["status"] == qp.UNKNOWN


def test_symlinked_lock_path_is_not_followed(tmp_path):
    proc, ident, lock = _spawn_advisor(tmp_path)
    _kill(proc)
    target = tmp_path / "target"
    lock.rename(target)
    lock.symlink_to(target)
    assert qp.probe_stop_evidence(ident)["lock_probe"]["status"] == qp.UNKNOWN


def test_incomplete_identity_is_unknown(tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    _kill(proc)
    for name in ("pid_starttime", "lock_ino", "pid_namespace", "pid"):
        partial = dict(ident)
        partial[name] = qp.unknown("missing")
        assert (
            qp.probe_stop_evidence(partial)["process_stopped"]["status"] == qp.UNKNOWN
        ), name


def test_other_pid_namespace_is_unknown(tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    _kill(proc)
    other = dict(ident)
    other["pid_namespace"] = qp.observed("pid:[1]", "forged")
    assert qp.probe_stop_evidence(other)["process_stopped"]["status"] == qp.UNKNOWN


def test_boot_change_proves_the_old_process_cannot_exist(tmp_path):
    proc, ident, lock = _spawn_advisor(tmp_path)
    _kill(proc)
    lock.unlink()  # lock evidence gone, boot evidence is enough
    boot = tmp_path / "boot_id"
    boot.write_text("another-boot\n")
    rec = qp.probe_stop_evidence(ident, boot_id_path=str(boot))
    assert rec["boot_probe"]["value"] == "CHANGED"
    assert rec["process_stopped"]["value"] is True


def test_pid_reuse_with_other_start_time_counts_as_gone(tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    _kill(proc)
    me = qp.current_process_identity(
        process_instance_id="x", lock_path="l", lock_fd=None
    )
    forged = dict(ident)
    forged["pid"] = me["pid"]  # a live pid with a different start time
    assert qp.probe_stop_evidence(forged)["pid_probe"]["value"] == "GONE"


# -------------------------------------------------------- verdict scenarios


def _witness(world, rec, body, *, exit_evidence=None, now=NOW + 1):
    return qp.write_witness(
        world.store,
        rec,
        body,
        store_root=world.authority_root,
        epoch_id=EPOCH,
        now=now,
        exit_evidence=exit_evidence,
    )


def test_running_process_is_never_quiescent(world, tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    rec, body = _seal_ready(world, ident)
    _witness(world, rec, body)
    result = world.assess()
    assert result.verdict == qp.V_RUNNING and not result.quiescent
    _kill(proc)


def test_interruption_without_seal_keeps_counters_unknown(world, tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    rec, body = _seal_ready(world, ident)
    _kill(proc)
    _witness(world, rec, body)
    result = world.assess()
    assert result.verdict == qp.V_INTERRUPTED and not result.quiescent
    assert "pending_order_count" in result.historical_unknowns
    assert "lifecycle_transitions_in_flight" in result.historical_unknowns


def test_sentinel_then_sigkill_is_sealed_stopped_not_clean(world, tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    rec, body = _seal_ready(world, ident)
    qp.write_seal(world.store, rec, body, now=NOW + 0.5)
    _kill(proc)  # SIGKILL right after the sentinel
    _witness(world, rec, body)
    result = world.assess()
    assert result.verdict == qp.V_SEALED_STOPPED
    assert result.verdict != qp.V_CLEAN_CONFIRMED
    assert not result.quiescent


def test_clean_stop_needs_independent_exit_status_bound_to_the_pid(world, tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    rec, body = _seal_ready(world, ident)
    qp.write_seal(world.store, rec, body, now=NOW + 0.5)
    _kill(proc)
    pid, start = ident["pid"]["value"], ident["pid_starttime"]["value"]
    _witness(
        world,
        rec,
        body,
        exit_evidence={
            "source": "test-supervisor",
            "exit_code": 0,
            "pid": pid,
            "pid_starttime": start,
        },
    )
    result = world.assess()
    assert result.verdict == qp.V_CLEAN_CONFIRMED
    assert not result.quiescent  # runtime not wired to the gate


def test_exit_evidence_for_another_process_is_ignored(world, tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    rec, body = _seal_ready(world, ident)
    qp.write_seal(world.store, rec, body, now=NOW + 0.5)
    _kill(proc)
    _witness(
        world,
        rec,
        body,
        exit_evidence={"source": "s", "exit_code": 0, "pid": 1, "pid_starttime": 1},
    )
    assert world.assess().verdict == qp.V_SEALED_STOPPED


def test_seal_broken_by_later_ledger_event_is_not_a_seal(world, tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    rec, body = _seal_ready(world, ident)
    qp.write_seal(world.store, rec, body, now=NOW + 0.5)
    world.open_position()  # the process kept writing after sealing
    _kill(proc)
    _witness(world, rec, body)
    result = world.assess()
    assert result.verdict == qp.V_INTERRUPTED


def test_missing_required_fields_degrade_to_unknown(world, tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    body = world.observe(ident)  # gate closed marker NOT written -> NOT_AVAILABLE
    rec = qp.write_observation(world.store, body, now=NOW)
    qp.write_seal(world.store, rec, body, now=NOW + 0.5)
    _kill(proc)
    _witness(world, rec, body)
    result = world.assess()
    assert result.verdict == qp.V_UNKNOWN
    assert "gate_marker_sha256" in result.missing


def test_no_witness_means_no_stop_claim(world, tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    rec, body = _seal_ready(world, ident)
    qp.write_seal(world.store, rec, body, now=NOW + 0.5)
    _kill(proc)
    assert world.assess().verdict == qp.V_UNKNOWN


@pytest.mark.parametrize("mutation", ["age", "future", "ledger", "manifest", "root"])
def test_stale_proofs_are_refused(world, tmp_path, mutation):
    proc, ident, _ = _spawn_advisor(tmp_path)
    rec, body = _seal_ready(world, ident)
    qp.write_seal(world.store, rec, body, now=NOW + 0.5)
    _kill(proc)
    _witness(world, rec, body)
    assert world.assess().verdict == qp.V_SEALED_STOPPED
    if mutation == "age":
        assert world.assess(now=NOW + 10_000).verdict == qp.V_STALE
    elif mutation == "future":
        assert world.assess(now=NOW - 100).verdict == qp.V_STALE
    elif mutation == "ledger":
        world.open_position()
        assert world.assess().verdict == qp.V_STALE
    elif mutation == "manifest":
        result = qp.assess(
            world.store,
            manifest=world.manifest,
            manifest_sha256="0" * 64,
            store_root=world.authority_root,
            now=NOW + 5,
            max_age_s=900.0,
        )
        assert result.verdict == qp.V_STALE
    else:
        result = qp.assess(
            world.store,
            manifest=world.manifest,
            manifest_sha256=world.manifest_sha,
            store_root=world.tmp / "elsewhere",
            now=NOW + 5,
            max_age_s=900.0,
        )
        assert result.verdict == qp.V_STALE


def test_restart_invalidates_previous_witness(world, tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    rec, body = _seal_ready(world, ident)
    qp.write_seal(world.store, rec, body, now=NOW + 0.5)
    _kill(proc)
    _witness(world, rec, body)
    assert world.assess().verdict == qp.V_SEALED_STOPPED
    # A new process instance observes: the old witness no longer precedes it.
    second = world.identity(process_instance_id=qp.observed("inst-restarted", "t"))
    qp.write_observation(world.store, world.observe(second), now=NOW + 2)
    assert world.assess().verdict == qp.V_UNKNOWN


def test_postmortem_assessment_needs_no_simulator_object(world, tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    rec, body = _seal_ready(world, ident)
    qp.write_seal(world.store, rec, body, now=NOW + 0.5)
    _kill(proc)
    _witness(world, rec, body)
    authority_root, proof_dir = world.authority_root, world.proof_dir
    manifest, manifest_sha = world.manifest, world.manifest_sha
    del world.sim, world.runtime  # the process and its memory are gone
    result = qp.assess(
        qp.ProofStore(proof_dir),
        manifest=manifest,
        manifest_sha256=manifest_sha,
        store_root=authority_root,
        now=NOW + 5,
        max_age_s=900.0,
    )
    assert result.verdict == qp.V_SEALED_STOPPED


def test_tampering_with_recorded_memory_fields_is_detected(world, tmp_path):
    rec, _body = _seal_ready(world, world.identity())
    path = rec.path
    path.write_bytes(
        path.read_bytes().replace(
            b'"pending_order_count":{"provenance"',
            b'"pending_order_count":{"x":1,"provenance"',
        )
    )
    assert world.assess().verdict == qp.V_UNRESOLVED_CHAIN


# --------------------------------------------------- quiescent stays forbidden


def _stopped_world(world, tmp_path, *, body_edit=None, wiring=False):
    if wiring:
        world.sim.ppl_gate_wiring_v1 = {
            "protocol": qp.GATE_WIRING_PROTOCOL,
            "code_sha": world.manifest.code_sha,
            "consults_gate_under_lock": True,
        }
    proc, ident, _ = _spawn_advisor(tmp_path)
    assert world.gate.close(decided_by="t", reason="r") is True
    body = world.observe(ident)
    if body_edit:
        body_edit(body)
    rec = qp.write_observation(world.store, body, now=NOW)
    qp.write_seal(world.store, rec, body, now=NOW + 0.5)
    _kill(proc)
    _witness(world, rec, body)
    return body


def test_current_unwired_runtime_can_never_be_quiescent(world, tmp_path):
    body = _stopped_world(world, tmp_path)
    result = world.assess()
    assert result.verdict == qp.V_SEALED_STOPPED and result.quiescent is False
    assert any("admission gate" in b for b in result.blocking)
    assert any("lifecycle_transitions_in_flight" in b for b in result.blocking)
    with pytest.raises(qp.QuiescenceRefusal):
        qp.to_epoch_rotation_quiescence(result, body)


def test_wiring_declaration_alone_does_not_make_transitions_zero(world, tmp_path):
    body = _stopped_world(world, tmp_path, wiring=True)
    assert body["runtime_consults_gate"]["status"] == qp.OBSERVED
    result = world.assess()
    assert result.quiescent is False
    assert body["lifecycle_transitions_in_flight"]["status"] == qp.NOT_APPLICABLE
    with pytest.raises(qp.QuiescenceRefusal):
        qp.to_epoch_rotation_quiescence(result, body)


def test_wiring_declaration_for_another_code_sha_is_unresolved(world):
    world.sim.ppl_gate_wiring_v1 = {
        "protocol": qp.GATE_WIRING_PROTOCOL,
        "code_sha": "someone-else",
        "consults_gate_under_lock": True,
    }
    assert world.observe()["runtime_consults_gate"]["status"] == qp.UNRESOLVED


def test_future_fully_observed_state_is_the_only_path_to_the_adapter(world, tmp_path):
    """Test-only: hand-edit the body as a *future wired* runtime would produce it."""

    def future_runtime(body):
        body["lifecycle_transitions_in_flight"] = qp.observed(
            0, "future dedicated counter"
        )
        body["admissions_in_flight"] = qp.observed(0, "future dedicated counter")

    body = _stopped_world(world, tmp_path, body_edit=future_runtime, wiring=True)
    result = world.assess()
    assert result.quiescent is True, result.blocking
    adapted = qp.to_epoch_rotation_quiescence(result, body)
    assert adapted.quiescent is True


def test_open_position_blocks_quiescence(world, tmp_path):
    world.open_position()
    _stopped_world(
        world,
        tmp_path,
        wiring=True,
        body_edit=lambda b: b.update(
            lifecycle_transitions_in_flight=qp.observed(0, "f"),
            admissions_in_flight=qp.observed(0, "f"),
        ),
    )
    result = world.assess()
    assert result.quiescent is False
    assert any("open positions" in b for b in result.blocking)


def test_adapter_refuses_unknown_instead_of_fabricating_zero(world):
    body = world.observe()
    fake = qp.Assessment(
        qp.V_SEALED_STOPPED, True
    )  # even a forged flag cannot feed zeros
    with pytest.raises(qp.QuiescenceRefusal):
        qp.to_epoch_rotation_quiescence(fake, body)


def test_required_fields_are_explicit_per_verdict():
    assert set(qp.REQUIRED_FIELDS) == {
        qp.V_INTERRUPTED,
        qp.V_SEALED_STOPPED,
        qp.V_CLEAN_CONFIRMED,
        qp.V_QUIESCENT,
    }
    assert set(qp.REQUIRED_FIELDS[qp.V_INTERRUPTED]) < set(
        qp.REQUIRED_FIELDS[qp.V_SEALED_STOPPED]
    )
    assert set(qp.REQUIRED_FIELDS[qp.V_SEALED_STOPPED]) < set(
        qp.REQUIRED_FIELDS[qp.V_QUIESCENT]
    )
    assert "runtime_consults_gate" in qp.REQUIRED_FIELDS[qp.V_QUIESCENT]
    assert "lifecycle_transitions_in_flight" in qp.REQUIRED_FIELDS[qp.V_QUIESCENT]


# --------------------------------------------------------------- isolation


def test_witness_and_assess_do_not_touch_the_authority_store(world, tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    rec, body = _seal_ready(world, ident)
    _kill(proc)

    def snapshot():
        return sorted(
            (
                str(p.relative_to(world.authority_root)),
                p.stat().st_size,
                p.stat().st_mtime_ns,
            )
            for p in world.authority_root.rglob("*")
            if p.is_file()
        )

    before = snapshot()
    _witness(world, rec, body)
    world.assess()
    assert snapshot() == before


def test_uninspectable_authority_store_is_unknown_and_not_created(tmp_path):
    empty = tmp_path / "no-store"
    empty.mkdir()
    out = qp._ledger_fingerprint(empty, EPOCH)
    assert all(v["status"] == qp.UNKNOWN for v in out.values())
    assert list(empty.iterdir()) == []


def test_pb_max_positions_is_never_consulted(world, monkeypatch):
    monkeypatch.setenv("PB_MAX_POSITIONS", "0")
    first = world.observe()
    monkeypatch.setenv("PB_MAX_POSITIONS", "99")
    assert world.observe() == first


# ------------------------------------------------- review R1: strict counters


def _future_runtime_with(**overrides):
    def edit(body):
        body["lifecycle_transitions_in_flight"] = qp.observed(0, "future counter")
        body["admissions_in_flight"] = qp.observed(0, "future counter")
        body.update(overrides)

    return edit


@pytest.mark.parametrize(
    "field",
    ["admissions_in_flight", "pending_order_count", "lifecycle_transitions_in_flight"],
)
@pytest.mark.parametrize(
    "bad",
    [
        qp.observed(1, "x"),
        qp.observed(-1, "x"),
        qp.observed(True, "x"),
        qp.observed("0", "x"),
        qp.observed(None, "x"),
        qp.observed(0.0, "x"),
        qp.unknown("x"),
        qp.not_applicable("x"),
        qp.not_available("x"),
        qp.unresolved("x"),
    ],
    ids=[
        "one",
        "minus1",
        "True",
        "str0",
        "None",
        "float0",
        "UNKNOWN",
        "NOT_APPLICABLE",
        "NOT_AVAILABLE",
        "UNRESOLVED",
    ],
)
def test_any_non_strict_zero_counter_blocks_quiescence(world, tmp_path, field, bad):
    body = _stopped_world(
        world, tmp_path, wiring=True, body_edit=_future_runtime_with(**{field: bad})
    )
    result = world.assess()
    assert result.verdict in (qp.V_SEALED_STOPPED, qp.V_UNKNOWN)
    assert result.quiescent is False
    with pytest.raises(qp.QuiescenceRefusal):
        qp.to_epoch_rotation_quiescence(result, body)


def test_adapter_refuses_nonzero_counters_even_with_a_forged_flag(world):
    body = world.observe()
    for field in (
        "pending_order_count",
        "lifecycle_transitions_in_flight",
        "admissions_in_flight",
    ):
        forged = dict(body)
        forged.update(
            pending_order_count=qp.observed(0, "x"),
            lifecycle_transitions_in_flight=qp.observed(0, "x"),
            admissions_in_flight=qp.observed(0, "x"),
        )
        forged[field] = qp.observed(1, "x")
        with pytest.raises(qp.QuiescenceRefusal):
            qp.to_epoch_rotation_quiescence(
                qp.Assessment(qp.V_SEALED_STOPPED, True), forged
            )


# ------------------------------------------- review R2: seal bound to its O


def test_seal_cannot_mix_two_snapshots(world, tmp_path):
    proc, ident, _ = _spawn_advisor(tmp_path)
    rec, _body = _seal_ready(world, ident)
    world.open_position()
    world.close_position()
    body2 = world.observe(ident)  # a different ledger digest
    assert body2["ledger_sha256"] != _body["ledger_sha256"]
    with pytest.raises(qp.QuiescenceRefusal):
        qp.write_seal(world.store, rec, body2, now=NOW + 0.5)
    tweaked = dict(_body)
    tweaked["ledger_sha256"] = qp.observed("0" * 64, "forged")
    with pytest.raises(qp.QuiescenceRefusal):
        qp.write_seal(world.store, rec, tweaked, now=NOW + 0.5)
    # old AppendResult + new O persisted afterwards: the old one is superseded
    rec2 = qp.write_observation(world.store, body2, now=NOW + 1)
    with pytest.raises(qp.QuiescenceRefusal):
        qp.write_seal(world.store, rec, None, now=NOW + 1.5)
    with pytest.raises(qp.QuiescenceRefusal):
        qp.write_witness(
            world.store,
            rec,
            None,
            store_root=world.authority_root,
            epoch_id=EPOCH,
            now=NOW + 2,
        )
    _kill(proc)
    qp.write_seal(world.store, rec2, body2, now=NOW + 1.5)  # positive case unchanged
    assert world.store.scan().status == "OK"


def test_seal_of_an_unconfirmed_observation_is_refused(world, monkeypatch):
    body = world.observe()
    monkeypatch.setattr(
        qp.ProofStore,
        "_fsync_directory",
        lambda self: (_ for _ in ()).throw(OSError(errno.EIO, "x")),
    )
    with pytest.raises(qp.PersistUncertain) as info:
        qp.write_observation(world.store, body, now=NOW)
    monkeypatch.undo()
    forged = qp.AppendResult(info.value.seq, info.value.record_sha256, world.proof_dir)
    with pytest.raises(qp.QuiescenceRefusal):
        qp.write_seal(world.store, forged, body, now=NOW + 1)


def test_reader_rejects_a_seal_of_another_snapshot_written_around_the_api(
    world, tmp_path
):
    """Defence in depth: even a hand-built SENTINEL (bypassing write_seal) cannot seal O at a later ledger."""
    proc, ident, _ = _spawn_advisor(tmp_path)
    rec, body = _seal_ready(world, ident)
    world.open_position()
    world.close_position()
    body2 = world.observe(ident)
    forged = {"seals_record_sha256": qp.observed(rec.record_sha256, "forged")}
    for name in ("ledger_sha256", *qp.PROCESS_FIELDS):
        forged[name] = dict(body2[name])
    forged["exit_intent"] = qp.observed("SEALED", "forged")
    world.store.append(
        qp.KIND_SENTINEL,
        forged,
        observed_at=NOW + 0.5,
        clock_provenance="t",
        max_age_s=900.0,
    )
    _kill(proc)
    _witness(world, rec, body)
    result = world.assess()
    assert result.verdict == qp.V_INTERRUPTED and result.quiescent is False


# -------------------------------- review R3: refusal leaves the authority intact


def _tree(root: Path):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def test_forbidden_root_refusal_creates_nothing(tmp_path):
    authority = tmp_path / "authority"
    (authority / "epochs").mkdir(parents=True)
    (authority / ".ppl-event-store.lock").write_text("")
    before = _tree(authority)
    outside_link = tmp_path / "link-to-authority"
    outside_link.symlink_to(authority)
    candidates = [
        authority,
        authority / "must-not-exist",
        authority / "a" / "b" / "c",
        authority / "epochs" / "x",
        tmp_path,  # parent of the authority
        outside_link / "via-symlink",
        outside_link / "deep" / "er",
    ]
    for bad in candidates:
        with pytest.raises(qp.PersistBlocked):
            qp.ProofStore(bad, forbidden_roots=[authority])
    assert _tree(authority) == before
    assert not (authority / "must-not-exist").exists()


# -------------------- review R4: each fsync failure point, other process, recover

_FAIL_WRITER = """
import errno, sys
from paper_trading import ppl_quiescence_proof as qp
n = int(sys.argv[2])
class F(qp.ProofStore):
    calls = 0
    def _fsync_fd(self, fd):
        F.calls += 1
        if F.calls == n:
            raise OSError(errno.EIO, "injected")
        super()._fsync_fd(fd)
try:
    r = F(sys.argv[1]).append(qp.KIND_OBSERVATION, {"x": qp.observed(1, "t")},
        observed_at=2e9, clock_provenance="t", max_age_s=900.0)
    print("OK", r.seq, r.receipt_durable)
except Exception as exc:
    print(type(exc).__name__)
"""

_NEXT_WRITER = """
import sys
from paper_trading import ppl_quiescence_proof as qp
r = qp.ProofStore(sys.argv[1]).append(qp.KIND_OBSERVATION, {"x": qp.observed(2, "t")},
    observed_at=2e9, clock_provenance="t", max_age_s=900.0)
print(r.seq)
"""


@pytest.mark.parametrize(
    ("n", "outcome", "after_failure", "after_recover_calls"),
    [
        (1, "PersistBlocked", "EMPTY []", None),  # record file fsync
        (2, "PersistUncertain", "OK [(1, False)]", "recover"),  # first directory fsync
        (3, "PersistUncertain", "OK [(1, False)]", "recover"),  # receipt file fsync
        (4, "OK 1 False", "OK [(1, True)]", "drop-receipt"),  # receipt directory fsync
    ],
    ids=["record-file", "record-dir", "receipt-file", "receipt-dir"],
)
def test_each_sync_failure_point_other_process_and_recovery(
    tmp_path, n, outcome, after_failure, after_recover_calls
):
    directory = str(tmp_path / "p")
    out = _run(_FAIL_WRITER, directory, str(n))
    assert out.stdout.strip() == outcome, out.stderr
    assert _run(_READER, directory).stdout.strip() == after_failure
    if after_recover_calls == "drop-receipt":
        # crash dropped the not-durable receipt: the record reverts to unconfirmed, safely
        for receipt in Path(directory).glob("*.ok"):
            receipt.unlink()
        assert _run(_READER, directory).stdout.strip() == "OK [(1, False)]"
    if after_recover_calls:
        assert _run(_RECOVER, directory).stdout.strip() == "(1,)"
        assert _run(_READER, directory).stdout.strip() == "OK [(1, True)]"
    expected_next = "1" if n == 1 else "2"
    assert _run(_NEXT_WRITER, directory).stdout.strip() == expected_next
    chain = qp.ProofStore(directory).scan()
    assert chain.status == "OK" and chain.all_confirmed
