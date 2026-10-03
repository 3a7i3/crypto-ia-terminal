"""U2b real collector/parser → atomic artifact → strict reader → GET fixture.

Only systemd transport is injected. No actual service/VPS is contacted.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from observability.operator_api import app as api
from observability.operator_api.runtime_service_reader import (
    RuntimeServiceSnapshotReader,
)
from observability.runtime_service_snapshot import (
    COMMAND,
    write_runtime_service_snapshot,
)

NOW = 1_791_000_000.0
INVOCATION = "a" * 32
HOST = "host-cross-stack"


def generate(out_dir: Path) -> dict:
    producer = Path(out_dir) / "_producer" / "K_runtime_service"
    producer.mkdir(parents=True, exist_ok=True)
    evidence = producer / "deployment-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "product": "RuntimeServiceDeploymentEvidence",
                "host_id": HOST,
                "unit": "crypto-advisor.service",
                "invocation_id": INVOCATION,
                "source_code_sha": "b" * 40,
                "evidence_ref": "cross-stack-deployment-01",
                "observed_at_utc": "2026-10-01T00:00:01Z",
            }
        )
    )
    prior_evidence = evidence.read_bytes()
    commands = []

    def transport(command, **kwargs):
        commands.append(command)
        assert command == list(COMMAND)
        return subprocess.CompletedProcess(
            command,
            0,
            "\n".join(
                [
                    "LoadState=loaded",
                    "ActiveState=active",
                    "SubState=running",
                    "MainPID=4321",
                    "NRestarts=0",
                    "ExecMainStartTimestamp=Thu 2026-10-01 00:00:00 UTC",
                    f"InvocationID={INVOCATION}",
                    "",
                ]
            ),
            "",
        )

    artifact = producer / "runtime_service_snapshot.json"
    produced = write_runtime_service_snapshot(
        artifact,
        run_command=transport,
        now_fn=lambda: NOW,
        host_id=HOST,
        deployment_path=evidence,
    )
    prior = api.get_runtime_service_reader()
    api._runtime_service_reader = RuntimeServiceSnapshotReader(
        artifact, now_fn=lambda: NOW + 5
    )
    try:
        with TestClient(api.app) as client:
            response = client.get("/api/operator/v1/runtime-service")
    finally:
        api._runtime_service_reader = prior
    result = {
        "http_status": response.status_code,
        "body": response.json(),
        "_proof": {
            "producer_authority": produced["authority"],
            "systemd_commands": commands,
            "deployment_evidence_unchanged": evidence.read_bytes() == prior_evidence,
            "artifact_is_regular_file": artifact.is_file()
            and not artifact.is_symlink(),
        },
    }
    (Path(out_dir) / "K_runtime_service.json").write_text(
        json.dumps(result, indent=2, sort_keys=True)
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    result = generate(parser.parse_args().out)
    if result["http_status"] != 200:
        raise SystemExit("U2B_CROSS_STACK_FAILED")
    print("APP_UNIFY_U2B_CROSS_STACK=PASS")


if __name__ == "__main__":
    main()
