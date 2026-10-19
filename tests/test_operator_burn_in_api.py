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


def test_statistics_route_has_same_boundary_and_fails_closed(tmp_path):
    path = tmp_path / 'burn.json'
    payload = _snapshot()
    path.write_text(json.dumps(payload), encoding='utf-8')
    prior = api_app.get_burn_in_status_reader()
    api_app._burn_in_status_reader = BurnInStatusSnapshotReader(path=path, now_fn=lambda:260.0)
    try:
        with TestClient(api_app.app) as client:
            result = client.get('/api/operator/v1/burn-in/statistics')
            assert result.status_code == 200
            assert result.json()['ppl_stream_sha256'] == payload['ppl_stream_sha256']
            assert result.json()['population']['closed'] == 1
            assert client.post('/api/operator/v1/burn-in/statistics').status_code == 405
            path.unlink()
            assert client.get('/api/operator/v1/burn-in/statistics').status_code == 503
    finally:
        api_app._burn_in_status_reader = prior


def test_statistics_route_returns_structured_error_for_inconsistent_subcounts(tmp_path):
    path = tmp_path / 'burn.json'
    payload = _snapshot()
    # The prior presentation contract admits swapped closed/unresolved counts.
    payload['lifecycle_counts'].update(closed=0, unresolved=2)
    path.write_text(json.dumps(payload), encoding='utf-8')
    prior = api_app.get_burn_in_status_reader()
    api_app._burn_in_status_reader = BurnInStatusSnapshotReader(path=path, now_fn=lambda:260.0)
    try:
        with TestClient(api_app.app) as client:
            response = client.get('/api/operator/v1/burn-in/statistics')
            assert response.status_code == 503
            assert response.json()['error_code'] in ('BURN_IN_STATISTICS_INVALID_POPULATION', 'BURN_IN_STATUS_INVALID_SCHEMA')
    finally:
        api_app._burn_in_status_reader = prior
