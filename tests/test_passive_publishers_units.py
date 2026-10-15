"""Source review of the passive-publisher units (runtime-service, storage, events).

Nothing here installs or starts a unit.  The tests (1) pin the least-privilege,
no-overlap and cadence properties of the unit files, and (2) run the exact
command each unit would run, against temporary directories, to prove that the
sources are not modified, that only the dedicated output directory is written,
that publication is atomic, and that a failed run leaves the previous artifact
untouched.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

from observability.event_center_contract import validate_event_center
from observability.operator_api.event_center_reader import EventCenterReader
from observability.operator_api.runtime_service_reader import (
    RuntimeServiceSnapshotReader,
)
from observability.operator_api.storage_reader import StorageSnapshotReader
from observability.storage_contract import validate_storage_snapshot

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "deploy" / "passive_publishers"
OUT = "/home/mathieu/operator_presentation"
RT = "/home/mathieu/crypto_ai_terminal"
RELEASE_SHA = "1728b3ad952b87d903ccb7442579000da292b848"
PY = f"/opt/crypto-ai-terminal/operator/staging-envs/{RELEASE_SHA}/bin/python"
STALE_AFTER_S = 90
NAMES = ("runtime-service", "storage", "events")
ARTIFACT = {
    "runtime-service": "runtime_service_snapshot.json",
    "storage": "storage_snapshot.json",
    "events": "event_center_snapshot.json",
}
MODULE = {
    "runtime-service": "observability.runtime_service_snapshot",
    "storage": "observability.storage_snapshot",
    "events": "observability.event_center_snapshot",
}


def _service(name: str) -> str:
    return (DIR / f"crypto-publish-{name}.service").read_text(encoding="utf-8")


def _timer(name: str) -> str:
    return (DIR / f"crypto-publish-{name}.timer").read_text(encoding="utf-8")


def _directives(text: str, key: str) -> list[str]:
    return [
        line.split("=", 1)[1]
        for line in text.splitlines()
        if line.startswith(key + "=")
    ]


def _seconds(value: str) -> int:
    assert value.endswith("s"), value
    return int(value[:-1])


# ----------------------------- unit properties -----------------------------


@pytest.mark.parametrize("name", NAMES)
def test_service_is_oneshot_least_privilege_and_not_restarting(name):
    text = _service(name)
    assert _directives(text, "Type") == ["oneshot"]  # systemd never overlaps a run
    assert _directives(text, "Restart") == []
    assert _directives(text, "EnvironmentFile") == []
    assert _directives(text, "User") == ["mathieu"]
    assert _directives(text, "ReadWritePaths") == [OUT]  # the only writable path
    for key, value in {
        "NoNewPrivileges": "true",
        "PrivateNetwork": "true",
        "PrivateTmp": "true",
        "PrivateDevices": "true",
        "ProtectSystem": "strict",
        "ProtectHome": "read-only",
        "CapabilityBoundingSet": "",
        "RestrictSUIDSGID": "true",
    }.items():
        assert _directives(text, key) == [value], key
    assert _directives(text, "ConditionPathIsDirectory") == [OUT]  # never creates it
    assert _seconds(_directives(text, "TimeoutStartSec")[0]) <= 30
    assert _directives(text, "MemoryMax") and _directives(text, "TasksMax")
    assert _directives(text, "Nice") == ["19"]


@pytest.mark.parametrize("name", NAMES)
def test_service_text_has_no_runtime_mutation_secret_or_network_reference(name):
    text = _service(name)
    code = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    forbidden = (
        ".env",
        "secret",
        "token",
        "git ",
        "curl",
        "wget",
        "sudo",
        "systemctl restart",
        "systemctl stop",
        "systemctl start",
        "systemctl kill",
        "crypto-advisor",
        "advisor_loop",
    )
    for word in forbidden:
        assert word not in code.lower(), word


@pytest.mark.parametrize("name", NAMES)
def test_exec_start_runs_pinned_release_module_and_writes_only_to_output(name):
    (exec_start,) = _directives(_service(name), "ExecStart")
    assert PY in exec_start
    assert f"-m {MODULE[name]}" in exec_start
    assert f"{OUT}/{ARTIFACT[name]}" in exec_start
    assert exec_start.count(OUT) == 1  # the output dir is never also a source
    for flag in ("--out", "--path"):
        if flag in exec_start:
            assert f"{flag} {OUT}/{ARTIFACT[name]}" in exec_start


def test_sources_are_explicit_and_distinct_from_the_output_directory():
    storage = _directives(_service("storage"), "ExecStart")[0]
    events = _directives(_service("events"), "ExecStart")[0]
    assert f"--source-directory {RT}/databases" in storage
    assert f"--p12-alerts {RT}/cache/startup/alerts.jsonl" in events
    assert f"--ppl-lifecycles {RT}/databases/burn_in_status_snapshot.json" in events
    assert "--supervision-alerts" not in events  # path unproven: stays NOT_CONFIGURED
    for text in (storage, events):
        assert OUT not in re.sub(rf"{re.escape(OUT)}/\w+\.json", "", text)


@pytest.mark.parametrize("name", NAMES)
def test_timer_cadence_is_below_the_api_freshness_threshold(name):
    text = _timer(name)
    assert _directives(text, "Unit") == [f"crypto-publish-{name}.service"]
    cadence = _seconds(_directives(text, "OnUnitActiveSec")[0])
    assert 30 <= cadence < STALE_AFTER_S
    # Failure margin: one failed or hung run (up to TimeoutStartSec) must not turn FRESH into STALE.
    (timeout,) = _directives(_service(name), "TimeoutStartSec")
    assert 2 * cadence + _seconds(timeout) < STALE_AFTER_S
    assert _directives(text, "Persistent") == ["false"]  # no catch-up burst after downtime
    assert _directives(text, "OnCalendar") == []
    assert _directives(text, "WantedBy") == ["timers.target"]


@pytest.mark.parametrize("name", NAMES)
def test_every_publisher_survives_one_missed_run(name):
    cadence = _seconds(_directives(_timer(name), "OnUnitActiveSec")[0])
    assert 2 * cadence <= STALE_AFTER_S


def test_api_dropin_only_points_three_readers_at_the_output_directory():
    text = (DIR / "API_DROPIN_30-presentation-paths.conf").read_text(encoding="utf-8")
    lines = [
        line for line in text.splitlines() if line and not line.startswith("#")
    ]
    assert lines == [
        "[Service]",
        f"Environment=RUNTIME_SERVICE_SNAPSHOT_PATH={OUT}/runtime_service_snapshot.json",
        f"Environment=STORAGE_SNAPSHOT_PATH={OUT}/storage_snapshot.json",
        f"Environment=EVENT_CENTER_SNAPSHOT_PATH={OUT}/event_center_snapshot.json",
    ]


# ------------------------------ behaviour ----------------------------------


def _command(name: str, out: Path, rt: Path) -> list[str]:
    (exec_start,) = _directives(_service(name), "ExecStart")
    argv = shlex.split(exec_start)
    argv = [
        token.replace("%%", "%")
        .replace(OUT, str(out))
        .replace(RT, str(rt))
        .replace(PY, sys.executable)
        for token in argv
    ]
    return argv


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "TZ": "UTC",
        "LC_ALL": "C",
    }
    return subprocess.run(
        argv, cwd=ROOT, env=env, capture_output=True, text=True, timeout=30
    )


def _tree(path: Path) -> dict:
    """Byte-exact fingerprint of everything under path (names, bytes, mtimes)."""
    state = {}
    for item in sorted(path.rglob("*")):
        info = item.lstat()
        digest = (
            hashlib.sha256(item.read_bytes()).hexdigest() if item.is_file() else None
        )
        state[str(item.relative_to(path))] = (info.st_mode, info.st_mtime_ns, digest)
    state["."] = (path.lstat().st_mtime_ns,)
    return state


@pytest.fixture()
def machine(tmp_path):
    rt = tmp_path / "crypto_ai_terminal"
    (rt / "databases").mkdir(parents=True)
    (rt / "cache" / "startup").mkdir(parents=True)
    out = tmp_path / "operator_presentation"
    out.mkdir()
    for index in range(5):
        (rt / "databases" / f"decision_packets_2026-10-1{index}.jsonl").write_text(
            '{"x":1}\n' * (index + 1), encoding="utf-8"
        )
    (rt / "databases" / "other.sqlite").write_bytes(b"not-a-packet")
    alert = {
        "rule": "DRAWDOWN",
        "severity": "WARNING",
        "ts": time.time() - 5,
        "message": "m",
        "value": 1.0,
        "threshold": 2.0,
    }
    (rt / "cache" / "startup" / "alerts.jsonl").write_text(
        json.dumps(alert) + "\n", encoding="utf-8"
    )
    return rt, out


def test_storage_publisher_does_not_touch_sources_and_writes_one_valid_file(machine):
    rt, out = machine
    before = _tree(rt)
    result = _run(_command("storage", out, rt))
    assert result.returncode == 0, result.stderr
    assert _tree(rt) == before  # content, mode, mtime of every source file and dir
    assert [p.name for p in out.iterdir()] == ["storage_snapshot.json"]  # no temp left
    doc = json.loads((out / "storage_snapshot.json").read_text())
    assert validate_storage_snapshot(doc)
    assert doc["source_status"] == "PRESENT"
    assert (doc["matched_file_count"], doc["entries_observed"]) == (5, 6)
    assert doc["total_bytes"] == sum(8 * n for n in range(1, 6))
    served = StorageSnapshotReader(out / "storage_snapshot.json").read()
    assert served.ok and served.snapshot["freshness_classification"] == "FRESH"


def test_whole_second_stamp_would_turn_a_live_packet_file_into_invalid_metadata(
    machine,
):
    """Why the unit uses a sub-second stamp (finding reproduced, not assumed)."""
    rt, out = machine
    packet = rt / "databases" / "decision_packets_2026-10-14.jsonl"
    packet.write_text('{"x":1}\n', encoding="utf-8")
    second = int(time.time()) - 5
    os.utime(packet, (second, second + 0.5))  # modified mid-second S
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(second))  # whole second S
    result = _run(
        [
            sys.executable,
            "-m",
            "observability.storage_snapshot",
            "--out",
            str(out / "whole.json"),
            "--source-directory",
            str(rt / "databases"),
            "--generated-at-utc",
            stamp,
        ]
    )
    assert result.returncode == 0
    assert json.loads((out / "whole.json").read_text())["source_status"] == (
        "INVALID_METADATA"
    )


def test_events_publisher_reads_sources_read_only_and_reports_missing_honestly(machine):
    rt, out = machine
    before = _tree(rt)
    result = _run(_command("events", out, rt))
    assert result.returncode == 0, result.stderr
    assert _tree(rt) == before
    assert [p.name for p in out.iterdir()] == ["event_center_snapshot.json"]
    doc = json.loads((out / "event_center_snapshot.json").read_text())
    assert validate_event_center(doc)
    status = {s["source_id"]: s["status"] for s in doc["sources"]}
    assert status == {
        "p12_alerts": "PRESENT",
        "supervision_alerts": "NOT_CONFIGURED",
        "ppl_lifecycles": "MISSING",  # burn-in projection absent: shown, not invented
    }
    served = EventCenterReader(out / "event_center_snapshot.json").read()
    assert served.ok and served.snapshot["freshness_classification"] == "FRESH"


def test_runtime_service_publisher_writes_a_valid_artifact_and_nothing_else(machine):
    rt, out = machine
    before = _tree(rt)
    result = _run(_command("runtime-service", out, rt))
    assert result.returncode == 0, result.stderr
    assert _tree(rt) == before
    assert [p.name for p in out.iterdir()] == ["runtime_service_snapshot.json"]
    served = RuntimeServiceSnapshotReader(
        out / "runtime_service_snapshot.json"
    ).read()
    assert served.ok
    assert served.snapshot["mode"] == "READ_ONLY"
    assert served.snapshot["deployment"]["status"] == "NOT_AVAILABLE"  # no evidence file given


@pytest.mark.parametrize(
    ("name", "refused"),
    (
        ("storage", Path("databases") / "inside.json"),  # output inside the scanned dir
        ("events", Path("cache") / "startup" / "alerts.jsonl"),  # output is a source
    ),
)
def test_failed_run_leaves_the_previous_artifact_byte_identical(machine, name, refused):
    rt, out = machine
    assert _run(_command(name, out, rt)).returncode == 0
    published = out / ARTIFACT[name]
    previous = published.read_bytes()
    sources = _tree(rt)
    argv = [t.replace(str(published), str(rt / refused)) for t in _command(name, out, rt)]
    result = _run(argv)
    assert result.returncode != 0  # the publisher refuses before writing anything
    assert _tree(rt) == sources
    assert published.read_bytes() == previous
    assert [p.name for p in out.iterdir()] == [ARTIFACT[name]]


@pytest.mark.parametrize("name", NAMES)
def test_concurrent_runs_never_expose_a_partial_or_temporary_file(machine, name):
    rt, out = machine
    argv = _command(name, out, rt)
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT)}
    procs = [
        subprocess.Popen(argv, cwd=ROOT, env=env, stdout=subprocess.DEVNULL)
        for _ in range(6)
    ]
    published = out / ARTIFACT[name]
    while any(p.poll() is None for p in procs):
        if published.exists():
            json.loads(published.read_bytes())  # never half-written
    assert [p.wait() for p in procs] == [0] * 6
    assert [p.name for p in out.iterdir()] == [ARTIFACT[name]]
    json.loads(published.read_bytes())


# ------------- reserves raised before finalising: budget, limit, race ----------


def _alert_line(ts: float) -> str:
    return json.dumps({"rule": "DRAWDOWN", "severity": "WARNING", "ts": ts,
                       "message": "m", "value": 1.0, "threshold": 2.0}) + "\n"


def _big_alert_log(path: Path, extra: int = 4000) -> int:
    line = _alert_line(time.time() - 5)
    count = 2_097_152 // len(line) + extra
    path.write_text(line * count, encoding="utf-8")
    return count


def test_events_total_read_budget_is_bounded_by_the_fixed_source_count(tmp_path, monkeypatch):
    """Bytes read per run <= len(SOURCE_IDS) * (MAX_BYTES + 1), independent of file sizes.

    The producer only accepts the fixed SOURCE_IDS; adding a source changes this bound
    explicitly (the pinned numbers below must then be reviewed, not silently exceeded).
    A windowed JSONL read is smaller still (TAIL_WINDOW_BYTES + 1).
    """
    from observability import event_center_artifact as artifact
    from observability import event_center_snapshot as snapshot
    from observability.event_center_contract import MAX_BYTES, SOURCE_IDS, TAIL_WINDOW_BYTES

    assert SOURCE_IDS == ("p12_alerts", "supervision_alerts", "ppl_lifecycles")
    assert len(SOURCE_IDS) * MAX_BYTES == 3 * 2_097_152  # documented budget: 6 MiB
    assert TAIL_WINDOW_BYTES + 1 <= MAX_BYTES + 1
    big = tmp_path / "big.jsonl"
    _big_alert_log(big)
    spaces = tmp_path / "burn_in.json"
    spaces.write_bytes(b" " * (MAX_BYTES * 3))
    consumed = []

    def counting(real):
        def wrapper(path):
            consumed.append(path)
            return real(path)
        return wrapper

    monkeypatch.setattr(snapshot, "read_bytes", counting(artifact.read_bytes))
    monkeypatch.setattr(snapshot, "read_jsonl_window", counting(artifact.read_jsonl_window))
    doc = snapshot.build_event_center(
        generated_at_utc="2026-10-14T20:00:00.000000Z",
        p12_alerts=big, supervision_alerts=big, ppl_lifecycles=spaces)
    assert len(consumed) == len(SOURCE_IDS)
    assert [s["status"] for s in doc["sources"]][2] == "OUTPUT_LIMIT"
    assert len(consumed) * (MAX_BYTES + 1) < 6_300_000


def test_alerts_over_the_limit_is_an_explicit_partial_tail_never_presented_as_exhaustive(machine):
    rt, out = machine
    alerts = rt / "cache" / "startup" / "alerts.jsonl"
    count = _big_alert_log(alerts)
    size = alerts.stat().st_size
    assert size > 2_097_152
    before = _tree(rt)
    result = _run(_command("events", out, rt))
    assert result.returncode == 0, result.stderr
    assert _tree(rt) == before
    doc = json.loads((out / "event_center_snapshot.json").read_text())
    assert validate_event_center(doc) and doc["schema_version"] == "1.1.0"
    p12 = doc["sources"][0]
    assert p12["status"] == "PARTIAL_TAIL" and p12["coverage"] == "TAIL_WINDOW"
    assert p12["source_bytes"] == size and p12["window_bytes"] < size
    assert p12["records_observed"] < count  # records before the window are never counted
    assert {e["source_id"] for e in doc["events"]} == {"p12_alerts"}
    served = EventCenterReader(out / "event_center_snapshot.json").read()
    assert served.ok and served.snapshot["sources"][0]["status"] == "PARTIAL_TAIL"


def test_a_log_just_under_the_limit_is_still_published_whole_with_schema_1_0_0(machine):
    rt, out = machine
    alerts = rt / "cache" / "startup" / "alerts.jsonl"
    base = _alert_line(time.time() - 5)
    line = base.replace('"message": "m"', '"message": "' + "m" * (256 - len(base) + 1) + '"')
    assert len(line) == 256  # 7 864 lines (< 10 000 records) for the size measured at G0
    alerts.write_text(line * (2_013_413 // 256), encoding="utf-8")
    result = _run(_command("events", out, rt))
    assert result.returncode == 0, result.stderr
    doc = json.loads((out / "event_center_snapshot.json").read_text())
    assert doc["schema_version"] == "1.0.0" and doc["sources"][0]["status"] == "PRESENT"


def test_a_missing_or_oversized_source_does_not_block_another_valid_source(tmp_path):
    from observability.event_center_snapshot import build_event_center

    good = tmp_path / "alerts.jsonl"
    good.write_text(_alert_line(time.time() - 5), encoding="utf-8")
    huge = tmp_path / "burn_in.json"
    huge.write_bytes(b" " * 2_097_153)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
    doc = build_event_center(generated_at_utc=stamp, p12_alerts=good, ppl_lifecycles=huge)
    status = {s["source_id"]: s["status"] for s in doc["sources"]}
    assert status == {"p12_alerts": "PRESENT", "supervision_alerts": "NOT_CONFIGURED",
                      "ppl_lifecycles": "OUTPUT_LIMIT"}
    assert len(doc["events"]) == 1 and doc["events"][0]["source_id"] == "p12_alerts"


def test_write_after_the_stamp_is_rejected_not_silently_accepted(machine):
    """The stamp is taken before the scan: a file written after it cannot be hidden.

    observed_at is therefore a lower bound; the sub-second stamp narrows the window,
    it does not remove the race, and the outcome of a lost race is INVALID_METADATA
    (never a FRESH snapshot claiming an observation it did not make).
    """
    rt, out = machine
    packet = rt / "databases" / "decision_packets_2026-10-14.jsonl"
    stamp_epoch = time.time() - 5
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(stamp_epoch)) + ".500000Z"
    stamp_value = int(stamp_epoch) + 0.5

    def run(mtime: float) -> str:
        for other in (rt / "databases").glob("decision_packets_*.jsonl"):
            os.utime(other, (stamp_value - 1, stamp_value - 1))
        os.utime(packet, (mtime, mtime))
        result = _run([sys.executable, "-m", "observability.storage_snapshot",
                       "--out", str(out / "race.json"),
                       "--source-directory", str(rt / "databases"),
                       "--generated-at-utc", stamp])
        assert result.returncode == 0, result.stderr
        return json.loads((out / "race.json").read_text())["source_status"]

    assert run(stamp_value - 0.2) == "PRESENT"           # written before the stamp
    assert run(stamp_value + 0.2) == "INVALID_METADATA"  # written after it: detected


def _g0(rt, out, extra_env=None, path=None):
    env = {"PATH": path or os.environ.get("PATH", "/usr/bin:/bin"), "RT": str(rt), "OUT": str(out)}
    env.update(extra_env or {})
    return subprocess.run(["sh", str(DIR / "g0_readonly_checks.sh")], env=env,
                          capture_output=True, text=True, timeout=60)


def test_g0_script_is_read_only_bounded_and_succeeds_on_a_machine_tree(machine):
    rt, out = machine
    live = rt / "databases" / "live_snapshot.json"
    live.write_text('{"cycle": 7, "cycle_duration_ms": 1234, "ts": "x"}', encoding="utf-8")
    before = _tree(rt)
    result = _g0(rt, out, {"G0B": "1"})
    assert result.returncode == 0, result.stderr
    assert _tree(rt) == before and list(out.iterdir()) == []
    assert len(result.stdout.splitlines()) < 200
    assert "cycle_duration_ms" in result.stdout
    assert "STATUS=COMPLETE" in result.stdout and "PACKETS=5" in result.stdout
    assert "NOT the cost of the publisher" in result.stdout
    newest = result.stdout.split("from that same pass:")[1].splitlines()[1:6]
    assert [line.split()[-1] for line in newest] == [
        f"decision_packets_2026-10-1{i}.jsonl" for i in (4, 3, 2, 1, 0)
    ]  # true newest-five, found without any head truncation


def test_g0_enforces_the_entry_cap_and_flags_incomplete(machine):
    rt, out = machine
    for index in range(30):
        (rt / "databases" / f"f{index}").write_text("", encoding="utf-8")
    exact = _g0(rt, out, {"CAP": "36"})  # 5 packets + other.sqlite + 30 = 36 entries
    assert "STATUS=COMPLETE" in exact.stdout and "ENTRIES=36" in exact.stdout
    over = _g0(rt, out, {"CAP": "35"})
    assert "STATUS=INCOMPLETE(more than 35 entries" in over.stdout
    assert "PARTIAL, NOT the true newest" in over.stdout
    assert "STATUS=COMPLETE" not in over.stdout


def test_g0_keeps_timeouts_and_errors_instead_of_a_partial_result(machine, tmp_path):
    rt, out = machine
    shim = tmp_path / "shim"
    shim.mkdir()
    find = shim / "find"
    find.write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
    find.chmod(0o755)
    path = f"{shim}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    slow = _g0(rt, out, {"FIND_TIMEOUT": "1"}, path)
    assert "STATUS=INCOMPLETE(find status 124" in slow.stdout
    find.write_text(
        "#!/bin/sh\necho 'find: x: Permission denied' >&2\n"
        "printf 'E\\t5\\t1.0\\tdecision_packets_a.jsonl\\n'\nexit 1\n", encoding="utf-8")
    denied = _g0(rt, out, None, path)
    assert "STATUS=INCOMPLETE" in denied.stdout and "STATUS=COMPLETE" not in denied.stdout


# ------------------------------- G1 block (prepared, never run here) -----------


def test_g1_script_is_generated_from_the_unit_files_without_drift():
    sys.path.insert(0, str(DIR))
    try:
        import build_g1
    finally:
        sys.path.remove(str(DIR))
    assert (DIR / "g1_stage_verify_measure.sh").read_text(encoding="utf-8") == build_g1.build()


def _g1(machine, tmp_path, **env_extra):
    rt, _out = machine
    work = tmp_path / "tmpdir"
    work.mkdir()
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "RT": str(rt), "RUNS": "2",
           "PYBIN": sys.executable, "SRC": str(ROOT), "TMPDIR": str(work)}
    env.update(env_extra)
    result = subprocess.run(["sh", str(DIR / "g1_stage_verify_measure.sh")], env=env,
                            capture_output=True, text=True, timeout=120)
    return result, work


def test_g1_writes_only_to_a_temporary_directory_and_cleans_up(machine, tmp_path):
    rt, out = machine
    before = _tree(rt)
    result, work = _g1(machine, tmp_path)
    assert result.returncode == 0, result.stderr
    assert _tree(rt) == before and list(out.iterdir()) == []  # sources and output dir untouched
    assert list(work.iterdir()) == []  # the 0700 work dir is gone
    assert "cleanup OK" in result.stdout and "CLEANUP FAILED" not in result.stdout
    assert result.stdout.count("contract-valid=True") == 3
    assert "failed runs: 0/2" in result.stdout and "UNCHANGED" in result.stdout
    assert "NOT created" in result.stdout
    assert not any(line.startswith("/home/mathieu/operator_presentation") for line in result.stdout.splitlines())


def test_g1_reports_a_missing_interpreter_instead_of_a_partial_result(machine, tmp_path):
    result, work = _g1(machine, tmp_path, PYBIN="/nonexistent/python")
    assert result.returncode == 0
    assert result.stdout.count("NOT PRODUCED") == 3 and "failed runs: 2/2" in result.stdout
    assert "contract-valid=True" not in result.stdout
    assert list(work.iterdir()) == []
