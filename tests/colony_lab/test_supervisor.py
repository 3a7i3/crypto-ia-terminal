"""Supervisor: refusals, quotas, external stop, crash recovery and a hostile child.

Synthetic lab only. Tests that need the OS sandbox skip with its verified
reason when the host refuses unprivileged namespaces; the fail-closed test
does not skip.
"""

import errno
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from colony_lab import lineage
from colony_lab import supervisor as sup
from sentinel_activity.store import ActivityStore
from tests.colony_lab.builders import BUDGET, archivist_spec, founder, lab_root, qualification

ROOT = Path(__file__).resolve().parents[2]
MISSION = "fixture-colony-mission"
TASKS = {**sup.TASKS, "HOSTILE": sup.TaskType("DIAGNOSTIC_PRODUCE", "tests.colony_lab.hostile"),
         "ARCHIVE": sup.TaskType("GOVERNED_ARTIFACT_READ", "tests.colony_lab.hostile")}


def task(task_id, mode=None, task_type="HOSTILE", mission=MISSION, **payload):
    if mode is not None:
        payload["mode"] = mode
    return {"task_schema": sup.TASK_SCHEMA, "task_id": task_id, "mission_id": mission, "task_type": task_type,
            "payload": payload}


def journal(root, agent_id):
    return ActivityStore(root / "individuals" / agent_id / sup.JOURNAL_DIR).snapshot()[1]


@pytest.fixture
def lab(tmp_path):
    def make(budget=None, permissions=("DIAGNOSTIC_PRODUCE", "GOVERNED_ARTIFACT_READ")):
        root = lab_root(tmp_path)
        body, record = founder(permissions=permissions, budget=budget)
        supervisor = sup.Supervisor(root, missions=frozenset({MISSION}), tasks=TASKS)
        supervisor.admit(record, body)
        return supervisor, record
    return make


def _host_has_namespaces() -> bool:
    """Checked independently of the supervisor, so a broken sandbox fails instead of skipping."""
    try:
        probe = subprocess.run(["unshare", "--user", "--map-root-user", "--net", "--mount", "--pid", "--fork",
                                "--mount-proc", "setpriv", "--no-new-privs", "--bounding-set=-all", "true"],
                               capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


HOST_NAMESPACES = _host_has_namespaces()


@pytest.fixture
def sandboxed(lab):
    def make(**kwargs):
        if not HOST_NAMESPACES:
            pytest.skip("host refuses unprivileged user/net/mount/pid namespaces; supervisor fails closed")
        supervisor, record = lab(**kwargs)
        assert supervisor.verify_sandbox() == "VERIFIED"
        return supervisor, record
    return make


def test_lab_root_is_never_created_and_must_be_private(tmp_path):
    for bad in (tmp_path / "colony-lab-missing", Path("relative/colony-lab-x"), tmp_path):
        with pytest.raises(sup.LabError):
            sup.Supervisor(bad, missions=frozenset())
    loose = tmp_path / "colony-lab-loose"
    loose.mkdir(mode=0o755)
    os.chmod(loose, 0o755)
    with pytest.raises(sup.LabError, match="LAB_ROOT_DENIED"):
        sup.Supervisor(loose, missions=frozenset())
    assert not (tmp_path / "colony-lab-missing").exists()


def test_missing_sandbox_fails_closed_without_running(lab):
    supervisor, record = lab()
    supervisor._tools = None
    result = supervisor.run(record["agent_id"], task("t-closed", "network"))
    assert result["status"] == "SANDBOX_UNAVAILABLE" and result["output"] is None
    events = journal(supervisor.root, record["agent_id"])
    assert [e["event_type"] for e in events] == ["POLICY_DENIED"]
    assert json.loads((supervisor.root / "individuals" / record["agent_id"] / "usage.json").read_text()) \
        == {"runs": 0}


@pytest.mark.parametrize("bad,code", [
    (task("t-1", task_type="DEPLOY"), "TASK_TYPE_UNKNOWN"),
    (task("t-1", mission="other-mission"), "MISSION_NOT_ADMITTED"),
    (task("../escape"), "TASK_ID_INVALID"),
    ({"task_id": "t-1"}, "TASK_SCHEMA_VIOLATION"),
    (task("t-1", note="ghp_" + "b" * 36), "SECRET_REJECTED"),
])
def test_typed_task_refusals_are_journaled(lab, bad, code):
    supervisor, record = lab()
    result = supervisor.run(record["agent_id"], bad)
    assert result["status"] == "REFUSED" and result["code"] == code
    assert journal(supervisor.root, record["agent_id"])[-1]["event_type"] == "POLICY_DENIED"


def test_capability_must_be_explicitly_granted(lab):
    supervisor, record = lab(permissions=["DIAGNOSTIC_PRODUCE"])
    result = supervisor.run(record["agent_id"], task("t-archive", task_type="ARCHIVE", mode="network"))
    assert result["status"] == "REFUSED" and result["code"] == "CAPABILITY_NOT_GRANTED"


def test_unknown_or_tampered_individual_is_never_run(lab):
    supervisor, record = lab()
    assert supervisor.run("0" * 64, task("t-x"))["status"] == "INDIVIDUAL_UNKNOWN"
    assert supervisor.run("../../etc", task("t-x"))["status"] == "INDIVIDUAL_UNKNOWN"
    path = supervisor.root / "individuals" / record["agent_id"] / "record.json"
    forged = json.loads(path.read_text())
    forged["lab_permissions"].append("REPOSITORY_READ")
    path.write_text(json.dumps(forged))
    result = supervisor.run(record["agent_id"], task("t-x"))
    assert result["status"] == "INDIVIDUAL_INVALID" and result["code"] == "RECORD_HASH_MISMATCH"


def test_descendant_admission_requires_the_parent_qualification(lab):
    supervisor, parent = lab()
    child_spec = archivist_spec()
    from colony_lab import lineage
    parent_spec = json.loads((supervisor.root / "individuals" / parent["agent_id"] / "spec.json").read_text())
    record = lineage.make_descendant(parent, parent_spec, child_spec, parent_qualification=qualification(parent),
                                     lab_permissions=["GOVERNED_ARTIFACT_READ"], budget=dict(BUDGET),
                                     declared_diff=lineage.spec_diff(parent_spec, child_spec))
    with pytest.raises(sup.LabError, match="QUALIFICATION_INVALID"):
        supervisor.admit(record, child_spec)
    assert supervisor.admit(record, child_spec, parent_qualification=qualification(parent))["status"] \
        == "ADMITTED_TO_LAB"
    assert supervisor.load(record["agent_id"])[0] == record
    with pytest.raises(sup.LabError, match="ALREADY_ADMITTED"):
        supervisor.admit(record, child_spec, parent_qualification=qualification(parent))


def test_hostile_child_is_contained(sandboxed):
    supervisor, record = sandboxed()
    aid = record["agent_id"]
    home = supervisor.root / "individuals" / aid
    (supervisor.root / "decoy").write_text("lab state")
    outside = supervisor.root.parent
    net = supervisor.run(aid, task("t-net", "network"))
    assert net["status"] == "COMPLETED" and net["output"]["connected"] is False
    writes = supervisor.run(aid, task("t-write", "write", targets=[str(outside), str(home), str(ROOT), "/tmp", "/",
                                                                   str(ROOT / "colony_lab"), "/dev"]))
    refused = {f"DENIED:{code}" for code in (errno.EROFS, errno.EACCES, errno.EPERM, errno.ENOENT)}
    assert set(writes["output"].values()) <= refused  # refused at creation, never EFBIG after it
    assert writes["output"][str(ROOT)] == f"DENIED:{errno.EROFS}"
    assert not any(p.name == "hostile-was-here" for p in outside.rglob("hostile-was-here"))
    reads = supervisor.run(aid, task("t-read", "read", targets=[str(supervisor.root), str(home / "record.json"),
                                                               str(ROOT / ".env.example")]))
    assert reads["output"][str(supervisor.root)] == "DENIED"  # not in the sandbox root at all
    assert reads["output"][str(home / "record.json")] == "DENIED"
    assert reads["output"][str(ROOT / ".env.example")] in (0, "DENIED")
    killed = supervisor.run(aid, task("t-signal", "signal", pid=os.getpid()))
    assert killed["output"]["killed"] is False
    target = str(supervisor.root)
    unmount = supervisor.run(aid, task("t-umount", "unmount", target=target))
    assert unmount["output"]["status"] != 0


def test_unix_sockets_outside_the_allowlist_are_unreachable(sandboxed, tmp_path):
    supervisor, record = sandboxed()
    with socket.socket(socket.AF_UNIX) as named, socket.socket(socket.AF_UNIX) as abstract:
        named.bind(str(tmp_path / "host.sock"))
        named.listen(1)
        abstract.bind("\0colony-test-" + record["agent_id"][:16])
        abstract.listen(1)
        targets = [str(tmp_path / "host.sock"), "@colony-test-" + record["agent_id"][:16]]
        result = supervisor.run(record["agent_id"], task("t-unix", "unix", targets=targets))
    assert result["status"] == "COMPLETED"
    assert all(value.startswith("DENIED") for value in result["output"].values())


def test_cpu_budget_counts_every_process(sandboxed):
    """Four children each under the per-process limit, together above the budget."""
    budget = {**BUDGET, "cpu_seconds": 2, "wall_seconds": 30}
    supervisor, record = sandboxed(budget=budget)
    result = supervisor.run(record["agent_id"], task("t-fork-spin", "fork_spin", processes=4, each_cpu_ms=1500))
    assert (result["status"], result["code"]) == ("BUDGET_EXHAUSTED", "CPU")


def test_cpu_budget_counts_live_processes(sandboxed):
    """Nothing is reaped: the CPU is only visible in /proc, and the budget still applies."""
    budget = {**BUDGET, "cpu_seconds": 2, "wall_seconds": 30}
    supervisor, record = sandboxed(budget=budget)
    result = supervisor.run(record["agent_id"], task("t-hold-spin", "hold_spin", processes=4, each_cpu_ms=1500))
    assert (result["status"], result["code"]) == ("BUDGET_EXHAUSTED", "CPU")


def test_process_count_is_bounded(sandboxed):
    supervisor, record = sandboxed()
    result = supervisor.run(record["agent_id"], task("t-fork-bomb", "fork_bomb"))
    assert result["status"] == "COMPLETED"
    assert result["output"]["forked"] <= sup.MAX_PROCESSES - 2  # init and the child itself count


@pytest.mark.parametrize("mode,payload", [
    ("exit_code", {"code": sup.SANDBOX_EXIT}), ("self_signal", {"signal": int(signal.SIGKILL)}),
    ("self_signal", {"signal": int(signal.SIGXCPU)}),
])
def test_child_cannot_choose_its_classification(sandboxed, mode, payload):
    supervisor, record = sandboxed()
    result = supervisor.run(record["agent_id"], task("t-forge", mode, **payload))
    assert (result["status"], result["code"]) == ("INTERRUPTED", "CHILD_FAILED")
    assert supervisor.sandbox == "VERIFIED"


def test_tampered_descendant_is_refused_even_when_rehashed(lab):
    supervisor, parent = lab()
    parent_spec = supervisor.load(parent["agent_id"])[1]
    child_spec = archivist_spec()
    record = lineage.make_descendant(parent, parent_spec, child_spec, parent_qualification=qualification(parent),
                                     lab_permissions=["GOVERNED_ARTIFACT_READ"], budget=dict(BUDGET),
                                     declared_diff=lineage.spec_diff(parent_spec, child_spec))
    supervisor.admit(record, child_spec, parent_qualification=qualification(parent))
    home = supervisor.root / "individuals" / record["agent_id"]
    forged = {**record, "lab_permissions": sorted(["DIAGNOSTIC_PRODUCE", "GOVERNED_ARTIFACT_READ"])}
    forged["record_hash"] = lineage._record_hash(forged)
    (home / "record.json").write_text(json.dumps(forged))
    with pytest.raises(sup.LabError):
        supervisor.load(record["agent_id"])
    (home / "record.json").write_text(json.dumps(record))
    assert supervisor.load(record["agent_id"])[0] == record
    (home / "birth_qualification.json").write_text(json.dumps(qualification(parent, reviewer=parent["agent_id"])))
    with pytest.raises(sup.LabError, match="SELF_QUALIFICATION_DENIED"):
        supervisor.load(record["agent_id"])


def test_untrusted_claims_change_nothing(sandboxed):
    supervisor, record = sandboxed()
    aid = record["agent_id"]
    before = supervisor.load(aid)
    fake = supervisor.run(aid, task("t-fake", "fake_verdict"))
    assert fake["status"] == "COMPLETED"
    assert supervisor.load(aid) == before
    stored = json.loads((supervisor.root / "individuals" / aid / "results" / "t-fake.json").read_text())
    assert stored["claims_are_untrusted"] is True
    assert not any((supervisor.root / "individuals" / aid).glob("*qualification*"))
    leak = supervisor.run(aid, task("t-secret", "secret"))
    assert "ghp_" not in json.dumps(leak) and leak["output_redactions"] == 1
    assert "ghp_" not in (supervisor.root / "individuals" / aid / "results" / "t-secret.json").read_text()
    assert supervisor.run(aid, task("t-garbage", "garbage"))["code"] == "CHILD_FAILED"


@pytest.mark.parametrize("mode,status,code", [
    ("spin", "BUDGET_EXHAUSTED", "CPU"), ("flood", "BUDGET_EXHAUSTED", "OUTPUT"),
    ("memory", "BUDGET_EXHAUSTED", "MEMORY"), ("sleep", "INTERRUPTED", "WALL_TIMEOUT"),
])
def test_per_run_quotas(sandboxed, mode, status, code):
    budget = {**BUDGET, "cpu_seconds": 1, "wall_seconds": 3, "memory_bytes": 512 << 20, "output_bytes": 4096}
    supervisor, record = sandboxed(budget=budget)
    started = time.monotonic()
    result = supervisor.run(record["agent_id"], task("t-" + mode, mode))
    assert (result["status"], result["code"]) == (status, code)
    assert time.monotonic() - started < 10
    assert journal(supervisor.root, record["agent_id"])[-1]["event_type"] in {"BUDGET_EXHAUSTED",
                                                                             "RUN_INTERRUPTED"}


def test_run_budget_and_deduplication(sandboxed):
    supervisor, record = sandboxed(budget={**BUDGET, "runs": 1})
    aid = record["agent_id"]
    assert supervisor.run(aid, task("t-a", "network"))["status"] == "COMPLETED"
    assert supervisor.run(aid, task("t-a", "network"))["status"] == "DUPLICATE_TASK"
    assert supervisor.run(aid, task("t-a", "secret"))["status"] == "TASK_ID_CONFLICT"
    exhausted = supervisor.run(aid, task("t-b", "network"))
    assert (exhausted["status"], exhausted["code"]) == ("BUDGET_EXHAUSTED", "RUNS")


def test_orphans_die_with_the_run(sandboxed):
    supervisor, record = sandboxed()
    assert supervisor.run(record["agent_id"], task("t-orphan", "orphan"))["status"] == "COMPLETED"
    time.sleep(0.3)
    out = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
    assert "tests.colony_lab.hostile" not in out


def test_external_stop_interrupts_and_latches(sandboxed):
    supervisor, record = sandboxed()
    aid = record["agent_id"]
    results = []
    worker = threading.Thread(target=lambda: results.append(supervisor.run(aid, task("t-long", "sleep"))))
    worker.start()
    time.sleep(1.0)
    (supervisor.root / "STOP").write_text("operator stop")
    worker.join(10)
    assert results and (results[0]["status"], results[0]["code"]) == ("STOPPED", "EXTERNAL_STOP")
    assert supervisor.run(aid, task("t-after", "network"))["status"] == "STOPPED"
    (supervisor.root / "STOP").unlink()
    assert supervisor.run(aid, task("t-resumed", "network"))["status"] == "COMPLETED"
    supervisor.stop()
    assert supervisor.run(aid, task("t-latched", "network"))["status"] == "STOPPED"
    assert supervisor.resume() is True
    assert supervisor.run(aid, task("t-again", "network"))["status"] == "COMPLETED"


def test_supervisor_crash_is_recovered_as_interrupted_and_identity_survives(sandboxed, tmp_path):
    supervisor, record = sandboxed()
    aid = record["agent_id"]
    code = (
        "import sys\n"
        "from pathlib import Path\n"
        "from colony_lab import supervisor as sup\n"
        "from tests.colony_lab.test_supervisor import TASKS, task\n"
        "s = sup.Supervisor(Path(sys.argv[1]), missions=frozenset({'fixture-colony-mission'}), tasks=TASKS)\n"
        "s.run(sys.argv[2], task('t-crash', 'sleep'))\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", code, str(supervisor.root), aid], cwd=ROOT)
    inflight = supervisor.root / "individuals" / aid / "inflight.json"
    deadline = time.monotonic() + 20
    while not inflight.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert inflight.exists()
    time.sleep(0.5)
    proc.send_signal(signal.SIGKILL)
    proc.wait(10)
    time.sleep(0.3)
    assert "tests.colony_lab.hostile" not in subprocess.run(["ps", "-eo", "args"], capture_output=True,
                                                            text=True).stdout
    restarted = sup.Supervisor(supervisor.root, missions=frozenset({MISSION}), tasks=TASKS)
    assert restarted.load(aid)[0]["agent_id"] == aid
    result = restarted.run(aid, task("t-next", "network"))
    assert result["status"] == "COMPLETED" and result["recovered_interrupted_runs"] == ["t-crash"]
    kinds = [(e["event_type"], e["payload"]["code"]) for e in journal(supervisor.root, aid)]
    assert ("RUN_INTERRUPTED", "SUPERVISOR_CRASH") in kinds and kinds[-1] == ("OBSERVATION_RECORDED",
                                                                             "RUN_COMPLETED")
    assert restarted.run(aid, task("t-crash", "sleep"))["status"] == "DUPLICATE_TASK"


def test_supervisor_imports_nothing_from_runtime_or_exchange():
    import ast
    banned = ("paper_trading", "core", "observability", "financial_institute", "ccxt", "requests", "httpx",
              "telegram", "agents", "dotenv")
    for path in (ROOT / "colony_lab").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for name in names:
                assert name.split(".")[0] not in banned, (path.name, name)


def test_sandbox_init_kills_its_namespace_when_the_lifeline_closes():
    """The lifeline alone, without the supervisor, PR_SET_PDEATHSIG or a group kill."""
    if not HOST_NAMESPACES:
        pytest.skip("host refuses unprivileged user/net/mount/pid namespaces; supervisor fails closed")
    lifeline_r, lifeline_w = os.pipe()
    report_r, report_w = os.pipe()
    argv = ["unshare", "--user", "--map-root-user", "--mount", "--pid", "--fork", "--mount-proc",
            sys.executable, "-I", "-S", "-B", str(sup.INIT), str(lifeline_r), str(report_w), "10",
            str(512 << 20), str(sup.MAX_PROCESSES), "--", "/bin/sh", "-c", "sleep 1000 & sleep 1000"]
    proc = subprocess.Popen(argv, pass_fds=(lifeline_r, report_w))
    os.close(lifeline_r)
    os.close(report_w)
    time.sleep(0.5)
    assert proc.poll() is None
    os.close(lifeline_w)
    assert proc.wait(10) == 0
    with os.fdopen(report_r, "rb") as handle:
        status = json.loads(handle.read())
    assert status["reason"] == "LIFELINE_CLOSED" and status["signal"] == signal.SIGKILL
