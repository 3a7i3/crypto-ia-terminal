"""PPL-QUIESCENCE-01 lot C1b — process scenarios (plan A3 §6, contract C1b v0).

Every scenario runs the synthetic driver ``c1b_driver.py`` as a real child
process (C1b wiring, real authority runtime, C1a simulator, real handlers).
Oracles are external to the driver: ledger bytes re-read by
``DurableEventStore``, sha256 of files, the proof chain re-read by
``ProofStore.scan``, ``assess`` re-run here, and the JSON of the lot B witness
launched as an isolated ``python -I -B`` subprocess.

Hermetic: temp dirs, no network, no exchange, no Telegram, no Advisor.  Waits
are bounded rendezvous on the driver's stdout events (watchdog ``GUARD``),
never pacing delays; children are killed and reaped in every case.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from paper_trading import ppl_quiescence_proof as qp
from paper_trading import ppl_quiescence_witness as witness
from paper_trading.durable_event_store import DurableEventStore
from paper_trading.ppl_admission_gate import AdmissionGate
from paper_trading.ppl_authority_runtime import (
    authority_manifest_sha256,
    write_authority_manifest,
)
from tests.paper_trading import c1b_driver as drv

ROOT = Path(__file__).resolve().parents[2]
DRIVER = Path(__file__).with_name("c1b_driver.py")
GUARD = 30.0

pytestmark = pytest.mark.skipif(
    not Path("/proc/self/stat").exists(), reason="requires Linux /proc"
)

_children: list[subprocess.Popen] = []


@pytest.fixture(autouse=True)
def _reap():
    yield
    for proc in _children:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            pass
    _children.clear()


_GATE_CHILD = """
import json, sys
from paper_trading.ppl_admission_gate import AdmissionGate
path, epoch, msha, action = sys.argv[1:5]
gate = AdmissionGate(path, paper_epoch_id=epoch, manifest_sha256=msha)
if action == "close":
    print(json.dumps(gate.close(decided_by="other-process", reason="c1b test")))
elif action == "state":
    print(json.dumps(gate.state()))
elif action.startswith("drain:"):
    print(json.dumps(list(gate.drain_barrier(timeout_s=float(action[6:])))))
"""


def _py(code: str, *args: str, timeout: float = GUARD) -> subprocess.CompletedProcess:
    script = f"import sys; sys.path.insert(0, {str(ROOT)!r})\n" + textwrap.dedent(code)
    return subprocess.run(
        [sys.executable, "-I", "-B", "-c", script, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


class Driver:
    def __init__(self, rig: "Rig", args: list[str]) -> None:
        self.rig = rig
        self.events: queue.Queue = queue.Queue()
        self.seen: list[dict] = []
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-B",
                str(DRIVER),
                "--repo",
                str(ROOT),
                "--root",
                str(rig.root),
                *args,
            ],
            stdout=subprocess.PIPE,
            stderr=open(rig.root / f"driver-{len(rig.drivers)}.log", "w"),
            text=True,
            env=rig.env,
            start_new_session=True,
        )
        _children.append(self.proc)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        for line in self.proc.stdout:
            self.events.put(json.loads(line))
        self.events.put({"event": "eof"})

    def expect(self, event: str, timeout: float = GUARD) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(f"no {event!r} event; seen={self.seen}")
            try:
                item = self.events.get(timeout=remaining)
            except queue.Empty:
                continue
            self.seen.append(item)
            if item["event"] == event:
                return item
            if item["event"] == "eof":
                raise AssertionError(f"driver ended before {event!r}; seen={self.seen}")

    def send(self, op: str, **kw) -> str:
        """Submit a command without waiting for its result."""
        self.rig.ncmd += 1
        name = f"{self.rig.ncmd:04d}"
        tmp = self.rig.root / "cmd" / f"{name}.tmp"
        tmp.parent.mkdir(exist_ok=True)
        tmp.write_text(json.dumps({"op": op, **kw}))
        tmp.rename(tmp.with_suffix(".json"))
        return name

    def result(self, name: str) -> dict:
        for item in self.seen:
            if item["event"] == "cmd" and item["name"] == name:
                return item["result"]
        while True:
            item = self.expect("cmd")
            if item["name"] == name:
                return item["result"]

    def cmd(self, op: str, **kw) -> dict:
        self.rig.ncmd += 1
        name = f"{self.rig.ncmd:04d}"
        tmp = self.rig.root / "cmd" / f"{name}.tmp"
        tmp.parent.mkdir(exist_ok=True)
        tmp.write_text(json.dumps({"op": op, **kw}))
        tmp.rename(tmp.with_suffix(".json"))
        while True:
            item = self.expect("cmd")
            if item["name"] == name:
                return item["result"]

    def stop(self, sig: int = signal.SIGTERM) -> tuple[dict, int]:
        self.proc.send_signal(sig)
        outcome = self.expect("outcome")
        return outcome, self.proc.wait(timeout=GUARD)

    def kill(self) -> None:
        self.proc.send_signal(signal.SIGKILL)
        self.proc.wait(timeout=GUARD)


class Rig:
    def __init__(self, tmp: Path) -> None:
        self.root = tmp
        for name in ("authority", "gate", "proofs", "run"):
            (tmp / name).mkdir()
        (tmp / "prices.json").write_text(
            json.dumps({"BTC/USDT": 100.0, "ETH/USDT": 100.0})
        )
        self.manifest = drv.manifest()
        self.manifest_sha = authority_manifest_sha256(self.manifest)
        self.gate_journal = tmp / "gate" / "gate.jsonl"
        self.identity_lock = tmp / "run" / "advisor.identity.lock"
        self.proof_dir = tmp / "proofs"
        self.authority_root = tmp / "authority"
        self.drivers: list[Driver] = []
        self.ncmd = 0
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("PPL_", "PAPER_", "MEXC_", "TELEGRAM"))
        }
        env.update(
            PPL_ADMISSION_GATE_JOURNAL=str(self.gate_journal),
            PPL_QUIESCENCE_PROOF_DIR=str(self.proof_dir),
            PPL_ADVISOR_IDENTITY_LOCK=str(self.identity_lock),
            PPL_AUTHORITY_STORE_ROOT=str(self.authority_root),
            PAPER_ADMISSION_LEDGER=str(tmp / "admission.jsonl"),
            PAPER_TRADE_LOG=str(tmp / "trades.jsonl"),
            PYTHONDONTWRITEBYTECODE="1",
        )
        self.env = env

    # -- driver
    def start(self, *args: str, ready: bool = True) -> Driver:
        d = Driver(self, list(args))
        self.drivers.append(d)
        if ready:
            d.expect("ready")
        return d

    # -- gate (test-only synthesis of OPEN, as in the C1a tests)
    def open_gate(self) -> None:
        gate = AdmissionGate(
            self.gate_journal,
            paper_epoch_id=drv.EPOCH,
            manifest_sha256=self.manifest_sha,
        )
        with gate._locked():
            gate._append(
                {
                    "seq": 1,
                    "prev_sha256": "0" * 64,
                    "action": "OPEN",
                    "paper_epoch_id": drv.EPOCH,
                    "manifest_sha256": self.manifest_sha,
                    "decision_sha256": "d" * 64,
                    "clearance_proof_sha256": "e" * 64,
                    "decided_by": "test-c1b",
                    "reason": "",
                }
            )
        assert gate.state() == "OPEN"

    def close_gate_elsewhere(self) -> None:
        res = _py(
            _GATE_CHILD, str(self.gate_journal), drv.EPOCH, self.manifest_sha, "close"
        )
        assert res.returncode == 0, res.stderr
        assert json.loads(res.stdout) is True

    # -- oracles
    def epoch_bytes(self) -> bytes:
        return (
            DurableEventStore(self.authority_root)._epoch_path(drv.EPOCH).read_bytes()
        )

    def events(self) -> list:
        return DurableEventStore(self.authority_root).load_epoch(drv.EPOCH)

    def event_types(self) -> list[str]:
        return [e.event_type for e in self.events()]

    def proofs(self) -> qp.ProofStore:
        return qp.ProofStore(self.proof_dir, forbidden_roots=[self.authority_root])

    def chain(self) -> list:
        return list(self.proofs().scan().records)

    def observation(self):
        return next(r for r in reversed(self.chain()) if r.kind == qp.KIND_OBSERVATION)

    def assess(self) -> qp.Assessment:
        return qp.assess(
            self.proofs(),
            manifest=self.manifest,
            manifest_sha256=self.manifest_sha,
            store_root=self.authority_root,
            now=time.time(),
            max_age_s=900.0,
        )

    def witness(self, observation_sha: str | None = None) -> tuple[dict, int]:
        """Lot B witness as an isolated subprocess (external oracle)."""
        observation_sha = observation_sha or self.observation().record_sha256
        manifest_file = self.root / "manifest.json"
        if not manifest_file.exists():
            write_authority_manifest(manifest_file, self.manifest)
        coordination = self.root / f"coordination-{observation_sha[:12]}.json"
        now = time.time()
        coordination.write_text(
            json.dumps(
                {
                    "schema": witness.COORDINATION_SCHEMA,
                    "observation_sha256": observation_sha,
                    "authority_store_root": str(self.authority_root.resolve()),
                    "boot_id": qp.read_boot_id(),
                    "pid_namespace": qp.read_pid_namespace(),
                    "created_at": now - 1,
                    "expires_at": now + 120,
                    "operator": "synthetic operator",
                    "reason": "c1b process test",
                    "start_paths_inhibited": True,
                }
            )
        )
        res = _py(
            "from paper_trading.ppl_quiescence_witness import main\n"
            "raise SystemExit(main(sys.argv[1:]))\n",
            "--manifest",
            str(manifest_file),
            "--authority-root",
            str(self.authority_root),
            "--proof-dir",
            str(self.proof_dir),
            "--coordination-file",
            str(coordination),
            "--epoch",
            drv.EPOCH,
            "--observation-sha256",
            observation_sha,
            timeout=60,
        )
        return json.loads(res.stdout), res.returncode

    def adapter_refuses(self) -> bool:
        try:
            qp.to_epoch_rotation_quiescence(self.assess(), self.observation().body)
        except qp.QuiescenceRefusal:
            return True
        return False

    def notes(self) -> list[str]:
        path = self.root / "notes.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def _never_attested(result: dict) -> None:
    assert result["assessment"]["verdict"] != qp.V_CLEAN_CONFIRMED
    rendered = json.dumps(result)
    assert "VERIFIED" not in rendered and "ATTESTED" not in rendered


# ------------------------------------------------------------------- B1


def test_b1_open_admitted_is_durable_and_counters_observed_zero(rig):
    rig.open_gate()
    d = rig.start()
    before = rig.event_types()
    assert d.cmd("buy")["status"] == "FILLED"
    assert rig.event_types() == before + ["POSITION_OPENED"]
    outcome, code = d.stop()
    assert outcome["status"] == "SEALED" and code == 0
    body = rig.observation().body
    assert qp.observed_value(body, "admissions_in_flight") == 0
    assert qp.observed_value(body, "lifecycle_transitions_in_flight") == 0
    assert qp.observed_value(body, "runtime_consults_gate") is True
    assert qp.observed_value(body, "source_sha") == drv.CODE
    # one open position and the gate still OPEN: sealed, never quiescent
    result, wcode = rig.witness()
    assert wcode == 10 and result["quiescent"] is False
    _never_attested(result)
    assert rig.adapter_refuses()


# ------------------------------------------------------------------- B2


def test_b2_open_refused_after_close_by_another_process_writes_nothing(rig):
    rig.open_gate()
    d = rig.start()
    rig.close_gate_elsewhere()
    before = hashlib.sha256(rig.epoch_bytes()).hexdigest()
    res = d.cmd("buy")
    assert res == {"status": "REJECTED", "reject_code": "GATE_CLOSED_MARKER"}
    assert hashlib.sha256(rig.epoch_bytes()).hexdigest() == before
    outcome, code = d.stop()
    assert code == 0
    body = rig.observation().body
    assert qp.observed_value(body, "admissions_in_flight") == 0
    gate_notes = [n for n in rig.notes() if "GATE_CLOSED_MARKER" in n]
    assert len(gate_notes) == 1  # the existing C1a notification, unchanged
    assert len(rig.notes()) == 2  # plus the existing start message; none from C1b


# ------------------------------------------------------------------- B3


def _gate_child(rig: Rig, action: str) -> subprocess.Popen:
    script = f"import sys; sys.path.insert(0, {str(ROOT)!r})\n" + textwrap.dedent(
        _GATE_CHILD
    )
    proc = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            script,
            str(rig.gate_journal),
            drv.EPOCH,
            rig.manifest_sha,
            action,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _children.append(proc)
    return proc


def _child_json(proc: subprocess.Popen):
    out, err = proc.communicate(timeout=GUARD)
    assert proc.returncode == 0, err
    return json.loads(out)


def test_b3_integrated_open_at_commit_close_and_drain_from_other_processes(rig):
    """Plan A3 B3 on the C1b-wired path.  The OPEN is admitted and blocked at
    its durable commit by a deterministic barrier; another process closes the
    gate and drains (first DRAIN_TIMEOUT); after release the admitted OPEN
    becomes durable before DRAINED returns; after DRAINED no new OPEN is
    admitted; CLOSE is preserved.  close/drain run only in this external test
    orchestration, never in C1b or the Advisor."""
    rig.open_gate()
    d = rig.start("--inject", "barrier")
    pending = d.send("buy")
    d.expect("commit_blocked")  # admitted, inside admission_hold, not durable
    assert "POSITION_OPENED" not in rig.event_types()
    # another process closes the gate: marker durable; no CLOSE record possible
    # while the admission holds the journal lock (C1a I10)
    assert _child_json(_gate_child(rig, "close")) is True
    status, _ = _child_json(_gate_child(rig, "drain:0.1"))
    assert status == "DRAIN_TIMEOUT"
    # a patient drainer is waiting while the commit is released
    drainer = _gate_child(rig, "drain:" + str(GUARD))
    time.sleep(0.2)  # let the drainer block on the gate lock (not a pacing proof)
    assert drainer.poll() is None
    assert "POSITION_OPENED" not in rig.event_types()
    (rig.root / "release").write_text("")
    status, _ = _child_json(drainer)
    assert status == "DRAINED"
    # the admitted OPEN became durable before DRAINED returned
    assert rig.event_types().count("POSITION_OPENED") == 1
    assert d.result(pending)["status"] == "FILLED"
    # after the barrier: no new OPEN is durable
    ledger_after_drain = rig.epoch_bytes()
    res = d.cmd("buy", symbol="ETH/USDT")
    assert res == {"status": "REJECTED", "reject_code": "GATE_CLOSED_MARKER"}
    assert rig.epoch_bytes() == ledger_after_drain
    # CLOSE preserved: the monitor closes the admitted position at TP
    (rig.root / "prices.json").write_text(
        json.dumps({"BTC/USDT": 200.0, "ETH/USDT": 100.0})
    )
    deadline = time.monotonic() + GUARD
    while "POSITION_CLOSED" not in rig.event_types():
        assert time.monotonic() < deadline, rig.event_types()
        time.sleep(0.02)
    assert rig.event_types().count("POSITION_OPENED") == 1
    outcome, code = d.stop()
    assert outcome["status"] == "SEALED" and code == 0
    result, wcode = rig.witness()
    (rig.root / "witness_b3.json").write_text(json.dumps(result, sort_keys=True))
    assert result["assessment"]["verdict"] == qp.V_SEALED_STOPPED
    assert result["quiescent"] is True and wcode == 12
    assert result["operational_qualification"] == "NOT_QUALIFIED"
    _never_attested(result)


# ------------------------------------------------------------------- B4


@pytest.mark.parametrize("state", ["closed", "corrupt", "lock_held", "never_opened"])
def test_b4_close_still_allowed_and_restart_not_refused(rig, state):
    rig.open_gate()
    d = rig.start()
    assert d.cmd("buy")["status"] == "FILLED"
    d.stop()
    # gate state for the restart
    holder = None
    if state == "closed":
        rig.close_gate_elsewhere()
    elif state == "corrupt":
        with rig.gate_journal.open("ab") as fh:
            fh.write(b"{not json\n")
    elif state == "never_opened":
        for p in rig.gate_journal.parent.iterdir():
            p.unlink()
    elif state == "lock_held":
        holder = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-c",
                "import fcntl,os,sys,time\n"
                "fd=os.open(sys.argv[1],os.O_RDWR|os.O_CREAT,0o600)\n"
                "fcntl.flock(fd,fcntl.LOCK_EX)\nprint('held',flush=True)\ntime.sleep(60)\n",
                str(rig.gate_journal.parent / (rig.gate_journal.name + ".lock")),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        _children.append(holder)
        assert holder.stdout.readline().strip() == "held"
    d2 = rig.start()
    ready = d2.seen[-1]
    assert ready["positions"] == ["BTC/USDT"]  # restored from PPL, start not refused
    t0 = time.monotonic()
    (rig.root / "prices.json").write_text(
        json.dumps({"BTC/USDT": 200.0, "ETH/USDT": 100.0})
    )  # crosses the TP of the restored position
    deadline = time.monotonic() + GUARD
    while "POSITION_CLOSED" not in rig.event_types():
        assert time.monotonic() < deadline, rig.event_types()
        time.sleep(0.02)
    elapsed = time.monotonic() - t0
    assert elapsed < 5.0  # independent of the third-party gate lock
    # a new OPEN is refused (fail closed) in every non-OPEN state
    expected = {
        "closed": "GATE_CLOSED_MARKER",
        "corrupt": "GATE_JOURNAL_INVALID",
        "never_opened": "GATE_NEVER_OPENED",
    }
    if state in expected:
        res = d2.cmd("buy", symbol="ETH/USDT")
        assert res == {"status": "REJECTED", "reject_code": expected[state]}
    outcome, code = d2.stop()
    assert outcome["status"] == "SEALED"


# ---------------------------------------------------------------- B5a / B6


def test_b5a_error_before_write_is_never_fabricated(rig):
    rig.open_gate()
    d = rig.start("--inject", "before_write")
    before = rig.event_types()
    res = d.cmd("buy")
    assert res.get("raised") == "OSError"
    assert rig.event_types() == before
    outcome, code = d.stop()
    assert outcome["status"] == "SEALED" and code == 0
    body = rig.observation().body
    assert qp.observed_value(body, "lifecycle_transitions_in_flight") == 1
    rig.close_gate_elsewhere()
    result, wcode = rig.witness()
    assert result["quiescent"] is False and wcode == 10
    assert rig.adapter_refuses()


def test_b5b_visible_append_then_successful_retry_counts_zero(rig):
    """B5b(1), C1b-wired process: one fsync failure after the bytes were
    written; the store retry succeeds.  FILLED, one durable OPEN, no
    transition in flight, SEALED.  Mirrors C1a ``test_tt3``."""
    rig.open_gate()
    d = rig.start("--inject", "fsync_once")
    res = d.cmd("buy")
    assert res.get("status") == "FILLED", res
    assert rig.event_types().count("POSITION_OPENED") == 1
    rig.close_gate_elsewhere()
    outcome, code = d.stop()
    assert outcome["status"] == "SEALED" and code == 0
    body = rig.observation().body
    assert qp.observed_value(body, "lifecycle_transitions_in_flight") == 0
    assert qp.observed_value(body, "lifecycle_transitions_detail") == []
    assert qp.observed_value(body, "memory_matches_durable") is not False


def test_b5b_visible_append_retry_fails_is_applied_durable_not_memory(rig):
    """B5b(2), C1b-wired process: the retry fails as well.  The order raises,
    the OPEN is durable but not in memory: one transition in flight of class
    APPLIED_DURABLE_NOT_MEMORY, memory does not match durable, the proof is
    sealed but the witness and the adapter refuse.  Mirrors C1a ``test_tt4``."""
    rig.open_gate()
    d = rig.start("--inject", "fsync_twice")
    res = d.cmd("buy")
    assert res.get("raised") == "OSError", res
    assert rig.event_types().count("POSITION_OPENED") == 1
    rig.close_gate_elsewhere()
    outcome, code = d.stop()
    assert outcome["status"] == "SEALED" and code == 0
    body = rig.observation().body
    assert qp.observed_value(body, "lifecycle_transitions_in_flight") == 1
    detail = qp.observed_value(body, "lifecycle_transitions_detail")
    assert [item["class"] for item in detail] == [
        qp.TRANSITION_APPLIED_DURABLE_NOT_MEMORY
    ]
    assert body["memory_matches_durable"]["value"] is False
    result, wcode = rig.witness()
    assert result["quiescent"] is False and wcode == 10
    assert rig.adapter_refuses()


def test_b6_interrupted_transition_blocks_quiescence_for_life(rig):
    rig.open_gate()
    d = rig.start("--inject", "base_exception")
    res = d.cmd("buy")
    assert res.get("raised") == "_InjectedBase"
    rig.close_gate_elsewhere()
    outcome, code = d.stop()
    assert outcome["status"] == "SEALED" and code == 0
    body = rig.observation().body
    assert qp.observed_value(body, "lifecycle_transitions_in_flight") == 1
    result, wcode = rig.witness()
    assert result["assessment"]["verdict"] == qp.V_SEALED_STOPPED
    assert result["quiescent"] is False and wcode == 10
    assert rig.adapter_refuses()


# ------------------------------------------------------------------- B7


def test_b7_live_writer_is_running_never_stopped(rig):
    rig.open_gate()
    d = rig.start("--pause-after", "seal")
    rig.close_gate_elsewhere()
    d.proc.send_signal(signal.SIGTERM)
    d.expect("paused")  # O and SENTINEL written, the process is still alive
    result, wcode = rig.witness()
    assert result["assessment"]["verdict"] == qp.V_RUNNING
    assert wcode == 10 and result["quiescent"] is False
    _never_attested(result)
    assert rig.adapter_refuses()
    d.kill()


# ------------------------------------------------------------------- B8


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
def test_b8_orderly_stop_is_sealed_then_stopped_never_clean_confirmed(rig, sig):
    rig.open_gate()
    d = rig.start()
    lock_before = d.seen[-1]["lock"]
    rig.close_gate_elsewhere()
    notes_before = rig.notes()
    outcome, code = d.stop(sig)
    # (a) normal exit with a sealed proof
    assert outcome["status"] == "SEALED" and code == 0
    # (b) chain OBSERVATION then SENTINEL, both confirmed
    chain = rig.chain()
    assert [r.kind for r in chain] == [qp.KIND_OBSERVATION, qp.KIND_SENTINEL]
    assert all(r.confirmed for r in chain)
    # (c)(d) witness: sealed then stopped, quiescent, exit 12 (never 0)
    result, wcode = rig.witness()
    assert result["assessment"]["verdict"] == qp.V_SEALED_STOPPED
    assert result["quiescent"] is True
    assert wcode == 12
    assert result["operational_qualification"] == "NOT_QUALIFIED"
    _never_attested(result)
    # B13: the only case where the adapter yields an instance
    assert not rig.adapter_refuses()
    # identity lock still present, same (dev, ino, ctime, mtime)
    info = os.lstat(rig.identity_lock)
    assert [info.st_dev, info.st_ino, info.st_ctime_ns, info.st_mtime_ns] == lock_before
    # L5: no notification from the stop path (the driver has no Advisor message)
    assert rig.notes() == notes_before


# ------------------------------------------------------------------- B9


def test_b9a_killed_between_observation_and_seal_is_interrupted(rig):
    rig.open_gate()
    d = rig.start("--pause-after", "observation")
    rig.close_gate_elsewhere()
    d.proc.send_signal(signal.SIGTERM)
    d.expect("paused")
    d.kill()
    result, wcode = rig.witness()
    assert result["assessment"]["verdict"] == qp.V_INTERRUPTED
    assert result["quiescent"] is False and wcode == 10
    assert result["assessment"]["historical_unknowns"]
    _never_attested(result)
    assert rig.adapter_refuses()


def test_b9b_killed_after_seal_is_sealed_then_stopped_not_clean(rig):
    rig.open_gate()
    d = rig.start("--pause-after", "seal")
    rig.close_gate_elsewhere()
    d.proc.send_signal(signal.SIGTERM)
    d.expect("paused")
    d.kill()
    result, wcode = rig.witness()
    # a sentinel is not an exit: same verdict as B8, never CLEAN_STOP_CONFIRMED
    assert result["assessment"]["verdict"] == qp.V_SEALED_STOPPED
    _never_attested(result)
    assert result["quiescent"] is True and wcode == 12


def test_b9c_killed_without_handled_signal_has_no_proof(rig):
    rig.open_gate()
    d = rig.start()
    d.cmd("buy")
    d.kill()
    assert rig.chain() == []
    verdict = rig.assess()
    assert verdict.verdict == qp.V_UNKNOWN and verdict.quiescent is False


def test_b9d_ii_lock_replaced_after_stop_gives_unknown(rig):
    rig.open_gate()
    d = rig.start()
    rig.close_gate_elsewhere()
    _, code = d.stop()
    assert code == 0
    rig.identity_lock.unlink()
    rig.identity_lock.write_text("")
    result, wcode = rig.witness()
    assert result["assessment"]["verdict"] == qp.V_UNKNOWN
    assert result["quiescent"] is False and wcode == 10
    _never_attested(result)


def test_b9d_lock_replaced_while_running_refuses_the_proof(rig):
    rig.open_gate()
    d = rig.start()
    rig.identity_lock.unlink()
    rig.identity_lock.write_text("")
    outcome, code = d.stop()
    assert outcome["status"] == "IDENTITY_LOCK_CHANGED" and code == 3
    assert rig.chain() == []


def _tree(rig: Rig) -> list[str]:
    return sorted(
        str(p.relative_to(rig.root))
        for p in rig.root.rglob("*")
        if not p.name.startswith("driver-")
    )


# R2: the three refusal classes of contract §13.2, each with the effects it
# really has (driver: prepare_from_env -> runtime.bind -> bind_wiring, the same
# order as the Advisor).


def test_r2_class1_partial_configuration_refuses_before_any_creation(rig):
    rig.env.pop("PPL_ADVISOR_IDENTITY_LOCK")
    before = _tree(rig)
    d = rig.start(ready=False)
    refused = d.expect("refused")
    assert refused["type"] == "C1bConfigRefusal" and "partial" in refused["detail"]
    assert d.proc.wait(timeout=GUARD) == 1
    assert _tree(rig) == before  # nothing created: no lock, no authority, no proof
    assert not rig.identity_lock.exists()


def test_r2_class2_lock_held_by_another_instance_refuses_without_new_writes(rig):
    holder = rig.start()  # first instance: creates and holds the identity lock
    epoch_before = rig.epoch_bytes()
    before = _tree(rig)
    d = rig.start(ready=False)
    refused = d.expect("refused")
    assert refused["type"] == "C1bIdentityRefusal"
    assert "held by another process" in refused["detail"]
    assert d.proc.wait(timeout=GUARD) == 1
    assert _tree(rig) == before  # the lock pre-existed; nothing new
    assert rig.epoch_bytes() == epoch_before  # refused before the authority bind
    holder.stop()


@pytest.mark.parametrize(
    "args, match",
    [(["--worktree", "DIRTY"], "not CLEAN"), (["--head", "ab" * 20], "differs")],
    ids=["dirty", "other_head"],
)
def test_r2_class3_post_bind_refusal_effects_are_lock_and_authority_bind_only(
    rig, args, match
):
    """Class 3: refused in ``bind_wiring``, after the identity lock (class 2) and
    after the authority bind.  Those earlier effects are admitted, not denied;
    C1b itself wrote no gate journal, proof, position or admission."""
    before = _tree(rig)
    d = rig.start(*args, ready=False)
    refused = d.expect("refused")
    assert refused["type"] == "C1bIdentityRefusal" and match in refused["detail"]
    assert d.proc.wait(timeout=GUARD) == 1
    created = set(_tree(rig)) - set(before)
    lock_rel = str(rig.identity_lock.relative_to(rig.root))
    assert lock_rel in created  # admitted: created by prepare, never deleted
    authority = {p for p in created if p.startswith("authority")}
    assert authority  # admitted: the authority bind created/replayed the epoch
    assert created == {lock_rel} | authority, sorted(created)
    assert not [t for t in rig.event_types() if t.startswith("POSITION_")]
    assert rig.chain() == []
    assert not rig.gate_journal.exists()


# ------------------------------------------------------- B10 / exigence 1


@pytest.mark.parametrize("step", ["observation", "seal"])
def test_b10_ex1_late_monitor_close_never_yields_a_proof(rig, step):
    rig.open_gate()
    d = rig.start("--close-after", step)
    assert d.cmd("buy")["status"] == "FILLED"
    rig.close_gate_elsewhere()
    ledger_before = rig.epoch_bytes()
    outcome, code = d.stop()
    assert outcome["status"] == "SEALED"
    assert rig.epoch_bytes() != ledger_before  # the late CLOSE is durable
    result, wcode = rig.witness()
    assert result["assessment"]["verdict"] == qp.V_INTERRUPTED
    assert result["quiescent"] is False and wcode == 10
    _never_attested(result)
    assert rig.adapter_refuses()
    # the witness repaired nothing
    assert "POSITION_CLOSED" in rig.event_types()


def test_b10_ex1_close_after_stop_before_observation_is_simply_observed(rig):
    rig.open_gate()
    d = rig.start("--close-after", "stop")
    assert d.cmd("buy")["status"] == "FILLED"
    rig.close_gate_elsewhere()
    outcome, code = d.stop()
    assert outcome["status"] == "SEALED" and code == 0
    result, wcode = rig.witness()
    assert result["assessment"]["verdict"] == qp.V_SEALED_STOPPED
    assert result["quiescent"] is True and wcode == 12


def test_b10_ex1_ledger_write_after_witness_is_stale(rig):
    rig.open_gate()
    d = rig.start()
    assert d.cmd("buy")["status"] == "FILLED"
    rig.close_gate_elsewhere()
    _, code = d.stop()
    assert code == 0
    result, wcode = rig.witness()
    assert result["assessment"]["verdict"] == qp.V_SEALED_STOPPED
    assert result["quiescent"] is False  # a position is open
    # a later writer: restart, the monitor closes the position, then SIGKILL
    d2 = rig.start()
    (rig.root / "prices.json").write_text(json.dumps({"BTC/USDT": 200.0}))
    deadline = time.monotonic() + GUARD
    while "POSITION_CLOSED" not in rig.event_types():
        assert time.monotonic() < deadline
        time.sleep(0.02)
    d2.kill()
    verdict = rig.assess()
    assert verdict.verdict == qp.V_STALE and verdict.quiescent is False
    assert rig.adapter_refuses()


# ------------------------------------------------------------------ B11d


def test_b11d_declaration_is_not_attestation(rig):
    rig.open_gate()
    d = rig.start()
    rig.close_gate_elsewhere()
    d.stop()
    body = rig.observation().body
    rendered = json.dumps(body)
    assert "VERIFIED" not in rendered and "ATTESTED" not in rendered
    log = (rig.root / "driver-0.log").read_text()
    assert "GIT_HEAD_AT_BOOT" in log and "CLAIMED_ONLY" in log
    assert "VERIFIED" not in log and "ATTESTED" not in log
