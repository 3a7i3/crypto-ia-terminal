from __future__ import annotations

import json

from fastapi.testclient import TestClient

from observability.operator_api import app as api_app
from observability.operator_api.burn_in_status_reader import BurnInStatusSnapshotReader
from tests.test_burn_in_status_snapshot import _snapshot


def test_reader_and_route_transport_only_validated_artifact(tmp_path):
    path = tmp_path / "burn.json"
    payload = _snapshot()
    path.write_text(json.dumps(payload), encoding="utf-8")

    prior = api_app.get_burn_in_status_reader()
    api_app._burn_in_status_reader = BurnInStatusSnapshotReader(
        path=path,
        stale_after_s=100.0,
        now_fn=lambda: 260.0,
    )
    try:
        with TestClient(api_app.app) as client:
            response = client.get("/api/operator/v1/burn-in")
        assert response.status_code == 200
        body = response.json()
        assert body["paper_epoch_id"] == "BURN-IN-EPOCH-TEST"
        assert body["lifecycle_counts"]["total"] == 3
        assert body["snapshot_age_s"] == 10.0
        assert body["freshness_classification"] == "FRESH"
    finally:
        api_app._burn_in_status_reader = prior


def test_route_fails_closed_when_artifact_missing(tmp_path):
    prior = api_app.get_burn_in_status_reader()
    api_app._burn_in_status_reader = BurnInStatusSnapshotReader(
        path=tmp_path / "missing.json",
        now_fn=lambda: 260.0,
    )
    try:
        with TestClient(api_app.app) as client:
            response = client.get("/api/operator/v1/burn-in")
        assert response.status_code == 503
        assert response.json()["error_code"] == "BURN_IN_STATUS_MISSING"
    finally:
        api_app._burn_in_status_reader = prior


def test_reader_rejects_malformed_http_200_candidate(tmp_path):
    path = tmp_path / "burn.json"
    payload = _snapshot()
    payload["lifecycle_counts"]["closed"] = 99
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = BurnInStatusSnapshotReader(path=path).read()
    assert result.ok is False
    assert result.error_code == "BURN_IN_STATUS_INVALID_SCHEMA"
