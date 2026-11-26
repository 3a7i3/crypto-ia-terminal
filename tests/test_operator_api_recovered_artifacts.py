"""P4 replay with local published-artifact fixtures."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from observability import runtime_service_artifact, storage_inventory
from observability.operator_api import agent_schedule, storage_reader
from observability.operator_api.app import app

API = "/api/operator/v1"
LAB_PATH = Path("/var/lib/cat-lab-registry/index.json")
REPORT_PATH = Path("/var/lib/cat-agent-report-inventory/inventory.json")
STAMP = "2026-01-01T00:00:00.000000Z"


def test_storage_and_lab_publish_only_valid_artifacts(tmp_path, monkeypatch):
    scanner = tmp_path / "scanner"
    scanner.mkdir()
    (scanner / "raw").mkdir()
    (scanner / "raw" / "sample").write_bytes(b"abc")
    storage = tmp_path / "storage.json"
    storage.write_text(json.dumps(storage_inventory.snapshot(scanner)))
    reports = tmp_path / "reports.json"
    reports.write_text(json.dumps({
        "observed_at": STAMP, "runs": {"files": 1, "bytes": 3},
        "rehearsals": {"files": 0, "bytes": 0},
    }))
    lab = tmp_path / "lab.json"
    card = {
        "experiment_id": "publication-smoke-20260101T000000000000Z",
        "execution_host": "cat-c1-16m-qual-01", "published_at": STAMP,
        "result_sha256": "a" * 64, "summary": {"observations": 1, "net_change": 3},
        "schema_version": 1, "status": "completed", "kind": "publication_smoke",
        "data_kind": "synthetic",
    }
    lab.write_text(json.dumps({"experiments": [card]}))
    read_document = runtime_service_artifact.read_document
    redirected = {LAB_PATH: lab, REPORT_PATH: reports}

    def read_fixture(path):
        return read_document(redirected.get(path, path))

    monkeypatch.setattr(runtime_service_artifact, "read_document", read_fixture)
    monkeypatch.setattr(storage_reader, "read_document", read_fixture)
    monkeypatch.setenv("STORAGE_INVENTORY_PATH", str(storage))
    client = TestClient(app)

    response = client.get(f"{API}/storage-inventory")
    assert response.status_code == 200
    assert response.json()["scanner"]["raw"]["bytes"] == 3
    assert response.json()["agent_reports"]["runs"] == {"files": 1, "bytes": 3}
    reports.write_text("{}")
    assert client.get(f"{API}/storage-inventory").json()["agent_reports"] is None
    storage.unlink()
    assert client.get(f"{API}/storage-inventory").status_code == 503

    response = client.get(f"{API}/lab-experiments")
    assert response.status_code == 200
    assert response.json() == {"experiments": [card]}
    lab.write_text(json.dumps({"experiments": [card, card]}))
    assert client.get(f"{API}/lab-experiments").status_code == 503


def test_recovered_agents_are_readable_without_extending_legacy_write(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_schedule, "CONTROL_PATH", tmp_path)
    client = TestClient(app)
    for agent in ("data-provenance-auditor", "market-observer"):
        report = client.get(f"{API}/agent-invocations/{agent}")
        assert report.status_code == 200
        path = f"{API}/agent-invocations/{agent}/schedule"
        assert client.get(path).status_code == 200
        assert client.post(path, headers={"x-cat-operator": "schedule"},
                           json={"rhythm": "off"}).status_code == 404
    assert not list(tmp_path.iterdir())
