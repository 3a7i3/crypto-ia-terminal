"""Lot B: synthetic inputs and local children only; no production authority."""

from __future__ import annotations

import dataclasses
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from paper_trading import ppl_quiescence_proof as qp
from paper_trading import ppl_quiescence_witness as witness
from paper_trading.ppl_authority_runtime import write_authority_manifest
from tests.paper_trading.test_ppl_quiescence_01 import World, _children, _spawn_advisor


@pytest.fixture
def sample(tmp_path):
    world = World(tmp_path)
    process, identity, lock = _spawn_advisor(tmp_path)
    try:
        world.gate.close(decided_by="synthetic", reason="test window")
        body = world.observe(identity)
        record = qp.write_observation(world.store, body, now=time.time())
        qp.write_seal(world.store, record, now=time.time())
        manifest = tmp_path / "manifest.json"
        write_authority_manifest(manifest, world.manifest)
        coordination = tmp_path / "coordination.json"
        now = time.time()
        coordination.write_text(
            json.dumps(
                {
                    "schema": witness.COORDINATION_SCHEMA,
                    "observation_sha256": record.record_sha256,
                    "authority_store_root": str(world.authority_root),
                    "boot_id": qp.read_boot_id(),
                    "pid_namespace": qp.read_pid_namespace(),
                    "created_at": now - 1,
                    "expires_at": now + 120,
                    "operator": "synthetic operator",
                    "reason": "controlled test launcher",
                    "start_paths_inhibited": True,
                }
            )
        )
        request = witness.Request(
            str(manifest),
            str(world.authority_root),
            str(world.proof_dir),
            str(coordination),
            world.manifest.paper_epoch_id,
            record.record_sha256,
        )
        yield world, process, lock, request
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        _children.remove(process)


def stopped(sample):
    world, process, lock, request = sample
    process.send_signal(signal.SIGKILL)
    process.wait(timeout=5)
    return world, lock, request


def snapshot(root):
    return {
        str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def test_real_worker_sealed_sigkill_has_no_clean_exit_or_quiescence(sample):
    world, lock, request = stopped(sample)
    authority_before = snapshot(world.authority_root)
    gate_before = snapshot(world.tmp / "unused")
    gate_files = {p.name: p.read_bytes() for p in world.tmp.glob("gate*")}
    result, code = witness.run(request)
    assert code == 10, result
    assert result["publication_state"] == "CONFIRMED"
    assert result["assessment"]["verdict"] == qp.V_SEALED_STOPPED
    assert result["quiescent"] is False
    assert result["operational_qualification"] == "NOT_QUALIFIED"
    assert result["coordination_verified"] is False
    assert result["witness"]["receipt_durable"] is True
    assert len(result["witness_package_sha256"]) == 64
    assert (
        result["coordination_sha256"]
        == hashlib.sha256(Path(request.coordination_file).read_bytes()).hexdigest()
    )
    assert snapshot(world.authority_root) == authority_before
    assert {p.name: p.read_bytes() for p in world.tmp.glob("gate*")} == gate_files
    assert snapshot(world.tmp / "unused") == gate_before
    assert lock.exists()
    stored = world.store.scan().records[-1].body
    assert qp.observed_value(stored, "coordination_verified") is False
    assert qp.observed_value(stored, "operational_qualification") == "NOT_QUALIFIED"
    assert (
        qp.observed_value(stored, "coordination_sha256")
        == result["coordination_sha256"]
    )
    assert qp.observed_value(stored, "publication_guard_atomic") is False


def test_alive_process_is_running_and_nonconclusive(sample):
    _, _, _, request = sample
    result, code = witness.run(request)
    assert code == 10
    assert result["assessment"]["verdict"] == qp.V_RUNNING
    assert result["quiescent"] is False


@pytest.mark.parametrize("change", ["absent", "replaced", "touched", "symlink"])
def test_ambiguous_lock_never_becomes_stop(sample, change, tmp_path):
    _, lock, request = stopped(sample)
    if change in ("absent", "replaced", "symlink"):
        lock.unlink()
    if change == "replaced":
        lock.write_text("replacement")
    elif change == "touched":
        os.utime(lock, ns=(1, 1))
    elif change == "symlink":
        other = tmp_path / "other"
        other.write_text("")
        lock.symlink_to(other)
    result, code = witness.run(request)
    assert code == 10
    assert result["assessment"]["verdict"] == qp.V_UNKNOWN
    assert result["quiescent"] is False


def test_without_sentinel_is_interrupted(sample):
    world, _, request = stopped(sample)
    for path in world.proof_dir.glob("quiescence-00000002-*"):
        path.unlink()
    result, code = witness.run(request)
    assert code == 10
    assert result["assessment"]["verdict"] == qp.V_INTERRUPTED
    assert "pending_order_count" in result["assessment"]["historical_unknowns"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("epoch", "other"),
        ("observation_sha256", "0" * 64),
        ("manifest", "relative.json"),
        ("authority_root", "."),
        ("timeout", float("nan")),
        ("timeout", True),
        ("timeout", 0),
        ("timeout", 61),
        ("max_age", float("inf")),
        ("max_age", 0),
    ],
)
def test_bad_request_refused_without_publication(sample, field, value):
    world, _, _, request = sample
    before = snapshot(world.proof_dir)
    result, code = witness.run(dataclasses.replace(request, **{field: value}))
    assert code == 20, result
    assert result["quiescent"] is False
    assert snapshot(world.proof_dir) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("expires_at", 1),
        ("created_at", float("nan")),
        ("start_paths_inhibited", False),
        ("start_paths_inhibited", "true"),
        ("observation_sha256", "0" * 64),
        ("authority_store_root", "/"),
        ("boot_id", "other"),
        ("pid_namespace", "other"),
        ("operator", ""),
    ],
)
def test_coordination_is_bound_and_fresh(sample, field, value):
    world, _, _, request = sample
    path = Path(request.coordination_file)
    body = json.loads(path.read_text())
    body[field] = value
    path.write_text(json.dumps(body))
    before = snapshot(world.proof_dir)
    result, code = witness.run(request)
    assert code == 20, result
    assert snapshot(world.proof_dir) == before


def test_duplicate_manifest_keys_and_noncanonical_bytes_refused(sample):
    world, _, _, request = sample
    path = Path(request.manifest)
    raw = path.read_bytes()
    for invalid in (raw.replace(b"{", b'{"created_at":1,', 1), raw + b" "):
        path.write_bytes(invalid)
        before = snapshot(world.proof_dir)
        assert witness.run(request)[1] == 20
        assert snapshot(world.proof_dir) == before


def test_newer_or_unconfirmed_observation_refused(sample):
    world, _, _, request = sample
    body = world.observe()
    record = qp.write_observation(world.store, body, now=time.time())
    assert witness.run(request)[1] == 20
    request = dataclasses.replace(request, observation_sha256=record.record_sha256)
    for receipt in world.proof_dir.glob("quiescence-00000003-*.ok"):
        receipt.unlink()
    assert witness.run(request)[1] == 20


def test_stale_observation_refused_before_append(sample):
    world, _, _, request = sample
    time.sleep(0.02)
    before = snapshot(world.proof_dir)
    result, code = witness.run(dataclasses.replace(request, max_age=0.001))
    assert code == 20, result
    assert snapshot(world.proof_dir) == before


def test_tree_and_file_limits_and_symlinks(sample, tmp_path):
    world, _, _, request = sample
    path = world.authority_root / "oversized"
    path.write_bytes(b"x" * (witness.MIB + 1))
    assert witness.run(request)[1] == 20
    path.unlink()
    path.symlink_to(Path(request.manifest))
    assert witness.run(request)[1] == 20
    path.unlink()
    alias = tmp_path / "authority-alias"
    alias.symlink_to(world.authority_root)
    assert witness.run(dataclasses.replace(request, authority_root=str(alias)))[1] == 20


def test_authority_and_proof_overlap_refused(sample):
    world, _, _, request = sample
    before = snapshot(world.authority_root)
    assert (
        witness.run(dataclasses.replace(request, proof_dir=request.authority_root))[1]
        == 20
    )
    assert snapshot(world.authority_root) == before


def test_blocked_native_ledger_read_times_out_and_reaps_worker(sample, monkeypatch):
    world, _, request = stopped(sample)
    children = []
    original = subprocess.Popen

    def tracked(*args, **kwargs):
        process = original(*args, **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(witness.subprocess, "Popen", tracked)
    before = snapshot(world.authority_root)
    proof_before = snapshot(world.proof_dir)
    with (world.authority_root / ".ppl-event-store.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        started = time.monotonic()
        result, code = witness.run(dataclasses.replace(request, timeout=0.7))
        assert time.monotonic() - started < 3
    assert code == 40, result
    assert result["publication_state"] == "UNKNOWN"
    assert all(child.poll() is not None for child in children)
    assert snapshot(world.authority_root) == before
    assert snapshot(world.proof_dir) == proof_before


@pytest.mark.parametrize("point,expected_code", [(1, 30), (2, 30), (3, 30), (4, 11)])
def test_each_witness_fsync_boundary(sample, monkeypatch, point, expected_code):
    world, _, request = stopped(sample)
    original = qp.ProofStore._fsync_fd
    calls = 0

    def faulty(self, fd):
        nonlocal calls
        calls += 1
        if calls == point:
            raise OSError("synthetic fsync fault")
        return original(self, fd)

    monkeypatch.setattr(qp.ProofStore, "_fsync_fd", faulty)
    result, code = witness._measure(request)
    assert code == expected_code, result
    monkeypatch.undo()
    chain = world.store.scan()
    if point == 1:
        assert len(chain.records) == 2
        assert result["publication_state"] == "NOT_PUBLISHED"
        assert result["witness"] is None
    elif point in (2, 3):
        assert chain.records[-1].confirmed is False
        assert result["publication_state"] == "VISIBLE_UNCONFIRMED"
        assert result["witness"]["seq"] == chain.records[-1].seq
        assert result["witness"]["sha256"] == chain.records[-1].record_sha256
        world.store.recover()
        assert world.store.scan().all_confirmed
    else:
        assert result["witness"]["receipt_durable"] is False
        assert chain.all_confirmed


def test_worker_crash_and_launch_failure_are_not_success(sample, monkeypatch):
    _, _, _, request = sample
    original = subprocess.Popen
    children = []

    def crashed(args, **kwargs):
        process = original(
            [sys.executable, "-I", "-c", "import os;os._exit(7)"], **kwargs
        )
        children.append(process)
        return process

    monkeypatch.setattr(witness.subprocess, "Popen", crashed)
    assert witness.run(request)[1] == 50
    assert all(p.poll() is not None for p in children)

    def failed(*args, **kwargs):
        raise OSError("synthetic launch failure")

    monkeypatch.setattr(witness.subprocess, "Popen", failed)
    assert witness.run(request)[1] == 50


def test_oversized_child_output_is_not_a_pipe_deadlock(sample, monkeypatch):
    _, _, _, request = sample
    original = subprocess.Popen

    def noisy(args, **kwargs):
        return original(
            [sys.executable, "-I", "-c", f"print('x'*{witness.OUTPUT_BYTES + 1})"],
            **kwargs,
        )

    monkeypatch.setattr(witness.subprocess, "Popen", noisy)
    result, code = witness.run(request)
    assert code == 50, result


def test_import_is_passive_without_network_or_file_writes():
    root = Path(__file__).resolve().parents[2]
    code = f"""
import sys, os
sys.path.insert(0, {str(root)!r})
def audit(event, args):
    if event.startswith('socket.'):
        raise RuntimeError('network')
    if event == 'open' and isinstance(args[2], int) and args[2] & (os.O_CREAT|os.O_WRONLY|os.O_RDWR):
        raise RuntimeError('write')
sys.addaudithook(audit)
import paper_trading.ppl_quiescence_witness
assert 'core.advisor_loop' not in sys.modules
assert 'paper_trading.mexc_simulator' not in sys.modules
print('PASSIVE')
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PASSIVE"


def test_cli_argument_errors_are_explicit_json(capsys):
    assert witness.main([]) == 20
    result = json.loads(capsys.readouterr().out)
    assert result["command_status"] == "REFUSED"
    assert result["publication_state"] == "NOT_PUBLISHED"
    assert result["quiescent"] is False


def test_another_manifest_of_same_epoch_is_refused(sample):
    world, _, _, request = sample
    other = dataclasses.replace(world.manifest, config_snapshot_hash="other-config")
    other_path = world.tmp / "other-manifest.json"
    write_authority_manifest(other_path, other)
    request = dataclasses.replace(request, manifest=str(other_path))
    before = snapshot(world.proof_dir)
    assert witness.run(request)[1] == 20
    assert snapshot(world.proof_dir) == before


def test_superseded_observation_during_publication_does_not_succeed(
    sample, monkeypatch
):
    world, _, request = stopped(sample)
    original = qp.ProofStore.append
    first = world.store.scan().records[0]

    def raced(self, kind, body, **kwargs):
        if kind == qp.KIND_WITNESS:
            original(
                qp.ProofStore(world.proof_dir),
                qp.KIND_OBSERVATION,
                first.body,
                observed_at=time.time(),
                clock_provenance="synthetic race",
                max_age_s=900,
            )
        return original(self, kind, body, **kwargs)

    monkeypatch.setattr(qp.ProofStore, "append", raced)
    result, code = witness._measure(request)
    assert code == 20, result
    assert result["quiescent"] is False
    assert result["publication_state"] == "NOT_PUBLISHED"
    assert len(world.store.scan().records) == 3


def test_timeout_after_visible_record_preserves_uncertainty_and_recovery(
    sample, monkeypatch
):
    world, _, request = stopped(sample)
    original = subprocess.Popen
    children = []
    marker = world.tmp / "published"
    root = Path(__file__).resolve().parents[2]
    code = f"""
import sys,json,time
from pathlib import Path
sys.path.insert(0,{str(root)!r})
from paper_trading import ppl_quiescence_proof as qp
from paper_trading.ppl_quiescence_witness import Request,_worker
def blocked(self,*args,**kwargs):
    Path({str(marker)!r}).write_text('record published; receipt not published')
    time.sleep(60)
qp.ProofStore._write_receipt=blocked
sys.exit(_worker(Request(**json.loads(sys.argv[1]))))
"""

    def injected(args, **kwargs):
        process = original([sys.executable, "-I", "-B", "-c", code, args[-3]], **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(witness.subprocess, "Popen", injected)
    before = snapshot(world.authority_root)
    result, status = witness.run(dataclasses.replace(request, timeout=2))
    assert status == 40, result
    assert result["publication_state"] == "UNKNOWN"
    assert marker.exists(), "fault injection must actually reach publication"
    assert all(child.poll() is not None for child in children)
    chain = world.store.scan()
    assert len(chain.records) == 3 and not chain.records[-1].confirmed
    assert snapshot(world.authority_root) == before
    monkeypatch.undo()
    assert world.store.recover() == (3,)
    assert world.store.scan().all_confirmed


def test_denied_proc_data_does_not_invent_a_stop(sample, monkeypatch):
    _, _, request = stopped(sample)
    monkeypatch.setattr(qp, "read_pid_starttime", lambda *args: ("UNKNOWN", None))
    result, code = witness._measure(request)
    assert code == 10, result
    assert result["assessment"]["verdict"] == qp.V_UNKNOWN
    assert result["quiescent"] is False


def test_network_audit_hook_refuses_resolution(sample, monkeypatch):
    """Run the real worker with a test-only measurement trying to resolve a host."""
    _, _, _, request = sample
    root = Path(__file__).resolve().parents[2]
    code = f"""
import sys,json
sys.path.insert(0,{str(root)!r})
from paper_trading import ppl_quiescence_witness as w
def network(request, **kwargs):
    import socket
    socket.getaddrinfo('must-not-resolve.invalid',443)
w._measure=network
try:
    w._worker(w.Request(**json.loads(sys.argv[1])))
except w.Refusal:
    print('NETWORK_REFUSED')
else:
    raise AssertionError('network not refused')
"""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            code,
            json.dumps(dataclasses.asdict(request)),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "NETWORK_REFUSED"


_LIFECYCLE_CONTROLLER = r'''
import ctypes,dataclasses,fcntl,json,os,signal,subprocess,sys,time
from pathlib import Path
root,encoded,mode,lock_kind,base=sys.argv[1:]
sys.path.insert(0,root)
from paper_trading import ppl_quiescence_proof as q
from paper_trading.ppl_quiescence_witness import Request
request=Request(**json.loads(encoded)); base=Path(base)
assert ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0
marker=base/'entered'; pidfile=base/'worker'; temp=base/'temps';temp.mkdir()
lockpath=Path(request.authority_root)/'.ppl-event-store.lock' if lock_kind=='ppl' else Path(request.proof_dir)/'.writer.lock'
lock=open(lockpath,'rb');fcntl.flock(lock,fcntl.LOCK_EX)
if mode=='AFTER_PUBLISH_KILL':fcntl.flock(lock,fcntl.LOCK_UN)
hookname='_ledger_fingerprint' if lock_kind=='ppl' else None
hook=("from pathlib import Path\nimport paper_trading.ppl_quiescence_proof as q\n"
      + ("original_probe=q._ledger_fingerprint\n" if hookname else "original_probe=q.ProofStore._acquire_writer_lock\n")
      + "def probe(*a,**k):\n    Path("+repr(str(marker))+").write_text('entered')\n    return original_probe(*a,**k)\n"
      + ("q._ledger_fingerprint=probe\n" if hookname else "q.ProofStore._acquire_writer_lock=probe\n"))
if mode=='AFTER_PUBLISH_KILL':
    hook=("from pathlib import Path\nimport time\nimport paper_trading.ppl_quiescence_proof as q\n"
          + "def probe(*a,**k):\n    Path("+repr(str(marker))+").write_text('record confirmed')\n    time.sleep(60)\n"
          + "q.assess=probe\n")
caller_code="""
import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,sys.argv[2]);tempfile.tempdir=sys.argv[3]
from paper_trading import ppl_quiescence_witness as w
original=w.subprocess.Popen
def tracked(args,**kwargs):
    args=list(args);args[4]=args[4].replace('sys.exit(_worker',sys.argv[5]+'sys.exit(_worker')
    p=original(args,**kwargs);Path(sys.argv[4]).write_text(str(p.pid));return p
w.subprocess.Popen=tracked
r,c=w.run(w.Request(**json.loads(sys.argv[1])));print(json.dumps(r));sys.exit(c)
"""
caller=None;worker=None
try:
    with (base/'out').open('wb') as out,(base/'err').open('wb') as err:
        caller=subprocess.Popen([sys.executable,'-I','-B','-c',caller_code,encoded,root,str(temp),str(pidfile),hook],stdout=out,stderr=err)
    deadline=time.monotonic()+5
    while not (marker.exists() and pidfile.exists()):
        assert caller.poll() is None,(base/'err').read_text()+(base/'out').read_text()
        assert time.monotonic()<deadline,'worker did not reach the injected wait'
        time.sleep(.01)
    worker=int(pidfile.read_text());time.sleep(.05)
    outcome={}
    if mode in ('SIGTERM','SIGKILL','AFTER_PUBLISH_KILL'):
        os.kill(caller.pid,signal.SIGKILL if mode=='AFTER_PUBLISH_KILL' else getattr(signal,mode));caller.wait(timeout=3)
        deadline=time.monotonic()+3
        while True:
            pid,status=os.waitpid(worker,os.WNOHANG)
            if pid:
                outcome['worker_killed']=os.WIFSIGNALED(status) and os.WTERMSIG(status)==signal.SIGKILL
                worker=None;break
            assert time.monotonic()<deadline,'orphan survived caller death'
            time.sleep(.01)
    elif mode=='STOP':
        os.kill(caller.pid,signal.SIGSTOP)
        time.sleep(request.timeout+.3)
        stat=Path(f'/proc/{worker}/stat').read_text()
        outcome['worker_exited_while_parent_stopped']=stat[stat.rindex(')')+2:].split()[0]=='Z'
        os.kill(caller.pid,signal.SIGCONT)
    elif mode=='EXPIRE':
        path=Path(request.coordination_file); data=json.loads(path.read_text())
        data['expires_at']=time.time()-1;path.write_text(json.dumps(data))
    elif mode=='NEW_O':
        store=q.ProofStore(request.proof_dir)
        body=store.scan().records[0].body
        q.write_observation(store,body,now=time.time())
    fcntl.flock(lock,fcntl.LOCK_UN)
    if mode not in ('SIGTERM','SIGKILL','AFTER_PUBLISH_KILL'):
        outcome['exit']=caller.wait(timeout=5)
        outcome['result']=json.loads((base/'out').read_text())
        worker=None  # direct parent reaped it through run()
    time.sleep(.1)
    chain=q.ProofStore(request.proof_dir).scan()
    outcome['witness_count']=sum(r.kind==q.KIND_WITNESS for r in chain.records)
    if mode=='AFTER_PUBLISH_KILL':
        last=chain.records[-1]
        outcome['confirmed']=last.confirmed
        outcome['coordination_verified']=q.observed_value(last.body,'coordination_verified')
        outcome['qualification']=q.observed_value(last.body,'operational_qualification')
    print(json.dumps(outcome))
finally:
    lock.close()
    if caller is not None and caller.poll() is None:
        caller.kill();caller.wait(timeout=3)
    if worker is not None:
        try:os.kill(worker,signal.SIGKILL)
        except ProcessLookupError:pass
        try:os.waitpid(worker,0)
        except ChildProcessError:pass
'''


def lifecycle_probe(sample, mode, lock_kind="ppl"):
    world, _, request = stopped(sample)
    root = Path(__file__).resolve().parents[2]
    if mode == "STOP":
        request = dataclasses.replace(request, timeout=0.8)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            _LIFECYCLE_CONTROLLER,
            str(root),
            json.dumps(dataclasses.asdict(request)),
            mode,
            lock_kind,
            str(world.tmp),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("mode", ["SIGTERM", "SIGKILL"])
@pytest.mark.parametrize("lock_kind", ["ppl", "proof"])
def test_caller_death_kills_worker_before_late_publication(sample, mode, lock_kind):
    result = lifecycle_probe(sample, mode, lock_kind)
    assert result["worker_killed"] is True
    assert result["witness_count"] == 0


def test_worker_has_wall_deadline_even_when_caller_is_stopped(sample):
    result = lifecycle_probe(sample, "STOP")
    assert result["worker_exited_while_parent_stopped"] is True
    assert result["exit"] == 40
    assert result["witness_count"] == 0


def test_caller_death_after_publication_leaves_limits_in_the_record(sample):
    result = lifecycle_probe(sample, "AFTER_PUBLISH_KILL")
    assert result["worker_killed"] is True
    assert result["witness_count"] == 1
    assert result["confirmed"] is True
    assert result["coordination_verified"] is False
    assert result["qualification"] == "NOT_QUALIFIED"


@pytest.mark.parametrize("mode", ["EXPIRE", "NEW_O"])
def test_changed_preconditions_during_ledger_wait_refuse_before_publication(
    sample, mode
):
    result = lifecycle_probe(sample, mode)
    assert result["exit"] == 20
    assert result["result"]["publication_state"] == "NOT_PUBLISHED"
    assert result["witness_count"] == 0


@pytest.mark.parametrize("kind", ["expired", "new_observation", "read_error"])
def test_postpublication_failure_preserves_confirmed_record(sample, monkeypatch, kind):
    world, _, request = stopped(sample)
    original = qp.assess

    def after_publication(*args, **kwargs):
        if kind == "expired":
            path = Path(request.coordination_file)
            data = json.loads(path.read_text())
            data["expires_at"] = time.time() - 1
            path.write_text(json.dumps(data))
        elif kind == "new_observation":
            body = world.store.scan().records[0].body
            qp.write_observation(world.store, body, now=time.time())
        else:
            raise OSError("synthetic assessment read error")
        return original(*args, **kwargs)

    monkeypatch.setattr(qp, "assess", after_publication)
    result, code = witness._measure(request)
    assert code == 21
    assert result["command_status"] == "PUBLISHED_UNVALIDATED"
    assert result["publication_state"] == "CONFIRMED"
    stored = world.store.scan().records[2]
    assert result["witness"]["seq"] == stored.seq
    assert result["witness"]["sha256"] == stored.record_sha256
    assert stored.confirmed
    assert result["quiescent"] is False


def test_coordination_must_cover_entire_requested_budget(sample):
    world, _, _, request = sample
    path = Path(request.coordination_file)
    data = json.loads(path.read_text())
    data["expires_at"] = time.time() + 2
    path.write_text(json.dumps(data))
    before = snapshot(world.proof_dir)
    result, code = witness.run(request)
    assert code == 20
    assert "window" in result["reason"]
    assert snapshot(world.proof_dir) == before


def test_unresolved_and_unconfirmed_are_distinct_refusals(sample):
    world, _, _, request = sample
    receipt = next(world.proof_dir.glob("quiescence-00000002-*.ok"))
    receipt.unlink()
    result, code = witness.run(request)
    assert code == 20 and "UNCONFIRMED" in result["reason"]
    record = next(world.proof_dir.glob("quiescence-00000002-*.json"))
    record.write_bytes(b"broken")
    result, code = witness.run(request)
    assert code == 20 and "UNRESOLVED" in result["reason"]


def test_inspection_io_error_is_not_a_precondition_error(sample, monkeypatch):
    _, _, _, request = sample

    def io_failure(*args):
        raise OSError("synthetic disk EIO")

    monkeypatch.setattr(witness, "_tree_budget", io_failure)
    result, code = witness._measure(request)
    assert code == 31
    assert result["command_status"] == "IO_ERROR"
    assert result["publication_state"] == "NOT_PUBLISHED"


def test_exit_zero_requires_all_three_qualified_conditions():
    complete = {
        "witness": {"receipt_durable": True},
        "quiescent": True,
        "coordination_verified": True,
    }
    assert witness._measurement_code(complete) == 0  # reserved future contract only
    assert witness._measurement_code({**complete, "coordination_verified": False}) == 12
    assert witness._measurement_code({**complete, "quiescent": False}) == 10
    assert (
        witness._measurement_code({**complete, "witness": {"receipt_durable": False}})
        == 11
    )


def test_chain_alone_preserves_declarative_limits(sample):
    world, _, request = stopped(sample)
    witness._measure(request)
    body = world.store.scan().records[-1].body
    assert qp.observed_value(body, "coordination_verified") is False
    assert qp.observed_value(body, "operational_qualification") == "NOT_QUALIFIED"
    assert (
        qp.observed_value(body, "coordination_sha256")
        == hashlib.sha256(Path(request.coordination_file).read_bytes()).hexdigest()
    )


def test_worker_clock_is_bound_to_its_boot_not_the_predecessor_boot(sample):
    world, _, request = stopped(sample)
    body = dict(world.store.scan().records[0].body)
    body["boot_id"] = qp.observed("synthetic-previous-boot", "prior boot fixture")
    observation = qp.write_observation(world.store, body, now=time.time())
    qp.write_seal(world.store, observation, now=time.time())
    path = Path(request.coordination_file)
    data = json.loads(path.read_text())
    data["observation_sha256"] = observation.record_sha256
    path.write_text(json.dumps(data))
    request = dataclasses.replace(request, observation_sha256=observation.record_sha256)
    result, code = witness._measure(request)
    assert code == 10, result
    stored = world.store.scan().records[-1].body
    assert qp.observed_value(stored, "boot_id") == "synthetic-previous-boot"
    assert qp.observed_value(stored, "witness_boot_id") == qp.read_boot_id()


def test_isolated_absolute_cli_returns_a_measurement_without_go(sample):
    _, _, request = stopped(sample)
    args = [sys.executable, "-I", "-B", str(Path(witness.__file__).resolve())]
    for name, value in dataclasses.asdict(request).items():
        args.extend(["--" + name.replace("_", "-"), str(value)])
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=20, check=False
    )
    assert result.returncode == 10, result.stderr
    body = json.loads(result.stdout)
    assert body["schema"] == "PPL-EXTERNAL-WITNESS-RESULT-V2"
    assert body["quiescent"] is False and body["coordination_verified"] is False


def test_help_is_explicitly_not_a_measurement(capsys):
    with pytest.raises(SystemExit) as result:
        witness.main(["--help"])
    assert result.value.code == 0
    assert capsys.readouterr().out.startswith("usage:")


def test_missing_linux_guard_fails_closed_in_subprocess():
    root = Path(__file__).resolve().parents[2]
    code = f"""
import sys,time,ctypes
sys.path.insert(0,{str(root)!r})
from paper_trading import ppl_quiescence_witness as w
class Missing:
    def prctl(self,*args):return -1
ctypes.CDLL=lambda *args,**kwargs:Missing()
try:w._arm_worker(1,time.monotonic()+1)
except w.Refusal:print('REFUSED')
else:raise AssertionError('unguarded worker permitted')
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0 and result.stdout.strip() == "REFUSED"


def test_worker_memory_limit_failure_is_not_a_success(sample, monkeypatch):
    world, _, _, request = sample
    original = subprocess.Popen
    before = snapshot(world.proof_dir)

    def injected(args, **kwargs):
        args = list(args)
        hook = (
            "import paper_trading.ppl_quiescence_witness as w\n"
            "def exhaust(request,**kwargs):\n    return bytearray(1024*1024*1024)\n"
            "w._measure=exhaust\n"
        )
        args[4] = args[4].replace("sys.exit(_worker", hook + "sys.exit(_worker")
        return original(args, **kwargs)

    monkeypatch.setattr(witness.subprocess, "Popen", injected)
    result, code = witness.run(request)
    assert code == 50 and result["command_status"] == "WORKER_ERROR"
    assert result["quiescent"] is False
    assert snapshot(world.proof_dir) == before
