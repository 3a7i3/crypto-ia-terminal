from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from observability import runtime_service_snapshot as runtime
from observability.runtime_service_contract import validate_runtime_service_snapshot

NOW = 1_791_000_000.0
INVOCATION = "a" * 32
HOST = "host-fixture"
PROPERTIES = {
    "LoadState": "loaded",
    "ActiveState": "active",
    "SubState": "running",
    "MainPID": "1234",
    "NRestarts": "0",
    "ExecMainStartTimestamp": "Thu 2026-10-01 00:00:00 UTC",
    "InvocationID": INVOCATION,
}


def runner(properties=None, code=0):
    values = PROPERTIES if properties is None else properties
    stdout = "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
    return Mock(
        return_value=subprocess.CompletedProcess(
            [], code, stdout, "secret stderr must never appear"
        )
    )


def snapshot(**kwargs):
    return runtime.build_runtime_service_snapshot(
        run_command=runner(), now_fn=lambda: NOW, host_id=HOST, **kwargs
    )


def evidence_file(tmp_path, **changes):
    doc = {
        "schema_version": "1.0.0",
        "product": "RuntimeServiceDeploymentEvidence",
        "host_id": HOST,
        "unit": "crypto-advisor.service",
        "invocation_id": INVOCATION,
        "source_code_sha": "b" * 40,
        "evidence_ref": "deployment-proof-01",
        "observed_at_utc": "2026-10-01T00:00:01Z",
        **changes,
    }
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(doc))
    return path


def test_fixed_safe_read_only_command_and_no_deployment_inference():
    run = runner()
    doc = runtime.build_runtime_service_snapshot(
        run_command=run, now_fn=lambda: NOW, host_id=HOST
    )
    args, kwargs = run.call_args
    assert args == (list(runtime.COMMAND),)
    assert args[0][:3] == ["/usr/bin/systemctl", "show", "--no-pager"]
    assert args[0][-2:] == ["--", "crypto-advisor.service"]
    assert not kwargs.get("shell", False)
    assert kwargs["timeout"] == 3 and kwargs["env"]["TZ"] == "UTC"
    assert set(runtime.SAFE_PROPERTIES) == set(PROPERTIES)
    assert not any(
        key in args[0][3] for key in ["Environment", "ExecStart", "ExecStop", "Journal"]
    )
    assert doc["service"]["restart_count"] == 0
    assert doc["deployment"]["status"] == "NOT_AVAILABLE"
    assert validate_runtime_service_snapshot(doc)
    assert "secret stderr" not in json.dumps(doc)


@pytest.mark.parametrize(
    "active,sub,pid",
    [
        ("inactive", "dead", "0"),
        ("failed", "failed", "0"),
        ("activating", "start", "0"),
    ],
)
def test_inactive_failed_and_transition_are_observations_not_health(active, sub, pid):
    run = runner({**PROPERTIES, "ActiveState": active, "SubState": sub, "MainPID": pid})
    doc = runtime.build_runtime_service_snapshot(
        run_command=run, now_fn=lambda: NOW, host_id=HOST
    )
    assert doc["service"]["active_state"] == active
    assert doc["service"]["main_pid"] == 0
    assert "healthy" not in doc["service"]


@pytest.mark.parametrize(
    "error,status",
    [
        (subprocess.TimeoutExpired("show", 3), "TIMEOUT"),
        (FileNotFoundError(), "COMMAND_UNAVAILABLE"),
        (PermissionError(), "COMMAND_UNAVAILABLE"),
    ],
)
def test_query_errors_never_fabricate_zero_or_liveness(error, status):
    doc = runtime.build_runtime_service_snapshot(
        run_command=Mock(side_effect=error), now_fn=lambda: NOW, host_id=HOST
    )
    assert doc["service"]["query_status"] == status
    assert doc["service"]["main_pid"] is None
    assert doc["service"]["restart_count"] is None
    assert doc["service"]["active_state"] is None


@pytest.mark.parametrize(
    "properties,code,status",
    [
        ({"LoadState": "not-found"}, 4, "NOT_FOUND"),
        (PROPERTIES, 1, "COMMAND_FAILED"),
        ({**PROPERTIES, "MainPID": "secret"}, 0, "INVALID_PROPERTIES"),
        ({**PROPERTIES, "MainPID": "0"}, 0, "INVALID_PROPERTIES"),
        ({**PROPERTIES, "NRestarts": "9007199254740992"}, 0, "INVALID_PROPERTIES"),
        ({**PROPERTIES, "Environment": "SECRET"}, 0, "INVALID_PROPERTIES"),
        ({**PROPERTIES, "ActiveState": "unknown-new-state"}, 0, "INVALID_PROPERTIES"),
        ({**PROPERTIES, "ExecMainStartTimestamp": "invalid"}, 0, "INVALID_PROPERTIES"),
        (
            {**PROPERTIES, "ExecMainStartTimestamp": "Fri 2099-01-01 00:00:00 UTC"},
            0,
            "INVALID_PROPERTIES",
        ),
    ],
)
def test_bad_or_missing_systemd_evidence_fails_closed(properties, code, status):
    doc = runtime.build_runtime_service_snapshot(
        run_command=runner(properties, code), now_fn=lambda: NOW, host_id=HOST
    )
    assert doc["service"]["query_status"] == status
    assert doc["service"]["main_pid"] is None


@pytest.mark.parametrize(
    "stdout,status",
    [
        ("x" * 4097, "OUTPUT_LIMIT"),
        ("LoadState=loaded\nLoadState=loaded\n", "INVALID_PROPERTIES"),
        ("LoadState=loaded\n", "INVALID_PROPERTIES"),
    ],
)
def test_output_limits_duplicates_and_partial_properties(stdout, status):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, stdout, "secret"))
    assert runtime.collect_service(run_command=run)["query_status"] == status


def test_deployment_requires_explicit_host_invocation_and_time_binding(tmp_path):
    path = evidence_file(tmp_path)
    doc = snapshot(deployment_path=path)
    assert doc["deployment"]["status"] == "PRESENT"
    assert doc["deployment"]["source_code_sha"] == "b" * 40
    assert len(doc["deployment"]["artifact_sha256"]) == 64
    assert "VERIFIED" not in json.dumps(doc)


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"host_id": "another-host"}, "HOST_MISMATCH"),
        ({"invocation_id": "c" * 32}, "INVOCATION_MISMATCH"),
        ({"observed_at_utc": "2026-09-30T23:59:59Z"}, "EVIDENCE_TIME_MISMATCH"),
        ({"observed_at_utc": "2099-01-01T00:00:00Z"}, "EVIDENCE_TIME_MISMATCH"),
        ({"secret": "not-allowed"}, "INVALID_EVIDENCE"),
        ({"source_code_sha": "unproven"}, "INVALID_EVIDENCE"),
    ],
)
def test_unbound_evidence_never_leaks_or_claims_current_source(
    tmp_path, changes, reason
):
    doc = snapshot(deployment_path=evidence_file(tmp_path, **changes))
    assert doc["deployment"]["reason"] == reason
    assert doc["deployment"]["source_code_sha"] is None
    assert doc["service"]["query_status"] == "OK"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(authority="ADVISOR_LIVENESS"),
        lambda d: d["service"].update(main_pid=True),
        lambda d: d["service"].update(active_state=[]),
        lambda d: d.update(host_id="host\nsecret"),
        lambda d: d.update(extra="secret"),
        lambda d: d.update(observed_at_utc="2026-02-30T00:00:00Z"),
        lambda d: d.update(generated_at_utc="2000-01-01T00:00:00Z"),
        lambda d: d["deployment"].update(status="PRESENT"),
        lambda d: d["service"].update(query_status="TIMEOUT"),
    ],
)
def test_closed_contract_rejects_malformed_and_contradictory_documents(mutate):
    doc = snapshot()
    mutate(doc)
    assert not validate_runtime_service_snapshot(doc)


def test_atomic_publisher_does_not_mutate_source_evidence(tmp_path):
    evidence = evidence_file(tmp_path)
    prior = evidence.read_bytes()
    target = tmp_path / "runtime.json"
    doc = runtime.write_runtime_service_snapshot(
        target,
        run_command=runner(),
        now_fn=lambda: NOW,
        host_id=HOST,
        deployment_path=evidence,
    )
    assert json.loads(target.read_text()) == doc
    assert evidence.read_bytes() == prior
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_failure_preserves_previous_artifact_and_cleans_temp(
    tmp_path, monkeypatch
):
    target = tmp_path / "runtime.json"
    target.write_text("previous")
    monkeypatch.setattr(runtime.os, "replace", Mock(side_effect=OSError()))
    with pytest.raises(OSError):
        runtime.write_runtime_service_snapshot(
            target, run_command=runner(), now_fn=lambda: NOW, host_id=HOST
        )
    assert target.read_text() == "previous"
    assert not list(tmp_path.glob("*.tmp"))


def test_no_trading_imports_or_runtime_mutations_in_source():
    source = Path(runtime.__file__).read_text()
    assert not any(
        term in source
        for term in [
            "advisor_loop",
            "paper_trading",
            "os.environ",
            '"restart"',
            "daemon-reload",
            "journalctl",
            "/proc/",
        ]
    )


def test_publisher_rejects_output_source_collision(tmp_path):
    source = evidence_file(tmp_path)
    prior = source.read_bytes()
    with pytest.raises(ValueError, match="OUTPUT_SOURCE_COLLISION"):
        runtime.write_runtime_service_snapshot(source, deployment_path=source)
    assert source.read_bytes() == prior


def test_bounded_transport_discards_stderr_and_kills_on_overflow(monkeypatch):
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"x" * 4097)
    os.close(write_fd)
    process = Mock()
    process.stdout = os.fdopen(read_fd, "rb")
    process.poll.return_value = None
    popen = Mock(return_value=process)
    process.__enter__ = Mock(return_value=process)
    process.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(runtime.subprocess, "Popen", popen)
    try:
        assert runtime.collect_service()["query_status"] == "OUTPUT_LIMIT"
        process.kill.assert_called_once()
        assert popen.call_args.kwargs["stderr"] == subprocess.DEVNULL
        assert popen.call_args.kwargs["shell"] is False
        assert popen.call_args.args[0] == list(runtime.COMMAND)
    finally:
        process.stdout.close()


def test_bounded_transport_cleans_up_after_timeout(monkeypatch):
    read_fd, write_fd = os.pipe()
    process = Mock()
    process.stdout = os.fdopen(read_fd, "rb")
    process.poll.return_value = None
    process.__enter__ = Mock(return_value=process)
    process.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(runtime.subprocess, "Popen", Mock(return_value=process))
    selector = Mock()
    selector.select.return_value = []
    selector.__enter__ = Mock(return_value=selector)
    selector.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(
        runtime.selectors, "DefaultSelector", Mock(return_value=selector)
    )
    try:
        assert runtime.collect_service()["query_status"] == "TIMEOUT"
        process.kill.assert_called_once()
    finally:
        os.close(write_fd)
        process.stdout.close()


@pytest.mark.parametrize(
    "raw,expected",
    [
        (
            b"LoadState=loaded\nActiveState=inactive\nSubState=dead\nMainPID=0\nNRestarts=0\nExecMainStartTimestamp=\nInvocationID=\n",
            "OK",
        ),
        (b"\xff", "INVALID_PROPERTIES"),
    ],
)
def test_bounded_transport_reads_bytes_safely(monkeypatch, raw, expected):
    read_fd, write_fd = os.pipe()
    os.write(write_fd, raw)
    os.close(write_fd)
    process = Mock()
    process.stdout = os.fdopen(read_fd, "rb")
    process.wait.return_value = 0
    process.poll.return_value = 0
    process.__enter__ = Mock(return_value=process)
    process.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(runtime.subprocess, "Popen", Mock(return_value=process))
    try:
        assert runtime.collect_service()["query_status"] == expected
        process.kill.assert_not_called()
    finally:
        process.stdout.close()


def test_contract_rejects_deployment_of_another_invocation(tmp_path):
    doc = snapshot(deployment_path=evidence_file(tmp_path))
    doc["service"]["invocation_id"] = "c" * 32
    assert not validate_runtime_service_snapshot(doc)
