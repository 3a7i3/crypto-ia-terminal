from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from observability.operator_api import app as api
from observability.operator_api.runtime_service_reader import (
    RuntimeServiceSnapshotReader,
)
from observability.runtime_service_snapshot import _utc
from tests.test_runtime_service_snapshot import NOW, snapshot


@pytest.fixture
def configured(tmp_path, monkeypatch):
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(snapshot()))
    reader = RuntimeServiceSnapshotReader(
        path, stale_after_s=90, now_fn=lambda: NOW + 5
    )
    monkeypatch.setattr(api, "_runtime_service_reader", reader)
    return path, reader


def test_real_reader_route_and_get_only(configured):
    _path, _reader = configured
    with TestClient(api.app) as client:
        response = client.get("/api/operator/v1/runtime-service")
        assert response.status_code == 200
        assert response.json()["snapshot_age_s"] == 5
        assert response.json()["freshness_classification"] == "FRESH"
        for method in ["post", "put", "patch", "delete"]:
            assert (
                getattr(client, method)("/api/operator/v1/runtime-service").status_code
                == 405
            )


def test_stale_is_measured_from_observation_not_republication(configured):
    path, _ = configured
    doc = snapshot()
    # Same old observation, newer publisher timestamp must not rejuvenate it.
    doc["generated_at_utc"] = _utc(NOW + 60)
    path.write_text(json.dumps(doc))
    result = RuntimeServiceSnapshotReader(path, now_fn=lambda: NOW + 86400).read()
    assert result.ok
    assert result.snapshot["freshness_classification"] == "STALE"
    assert result.snapshot["snapshot_age_s"] == 86400


def test_missing_returns_governed_error(configured):
    path, _ = configured
    path.unlink()
    with TestClient(api.app) as client:
        response = client.get("/api/operator/v1/runtime-service")
    assert response.status_code == 503
    assert response.json() == {"error_code": "RUNTIME_SERVICE_MISSING"}


@pytest.mark.parametrize(
    "raw",
    [
        '{"schema_version":1,"schema_version":2}',
        '{"secret":NaN}',
        "{broken",
        "[]",
        "x" * 16385,
    ],
)
def test_malformed_duplicate_and_oversized_artifacts_fail_closed(configured, raw):
    path, reader = configured
    path.write_text(raw)
    assert reader.read().error_code == "RUNTIME_SERVICE_INVALID_ARTIFACT"


def test_symlink_is_rejected_without_reading_target(configured, tmp_path):
    path, reader = configured
    target = tmp_path / "target.json"
    path.rename(target)
    path.symlink_to(target)
    assert reader.read().error_code == "RUNTIME_SERVICE_INVALID_ARTIFACT"


def test_reader_rejects_invalid_schema_and_future_evidence(configured):
    path, reader = configured
    doc = snapshot()
    doc["authority"] = "API_HEALTH"
    path.write_text(json.dumps(doc))
    assert reader.read().error_code == "RUNTIME_SERVICE_INVALID_SCHEMA"
    path.write_text(json.dumps(snapshot()))
    assert (
        RuntimeServiceSnapshotReader(path, now_fn=lambda: NOW - 1).read().error_code
        == "RUNTIME_SERVICE_FUTURE_TIMESTAMP"
    )


@pytest.mark.parametrize("threshold", [0, -1, float("inf"), float("nan")])
def test_invalid_freshness_threshold(threshold):
    with pytest.raises(ValueError):
        RuntimeServiceSnapshotReader(stale_after_s=threshold)


def test_api_never_collects_host_state(configured, monkeypatch):
    from observability import runtime_service_snapshot as producer

    collect = Mock(side_effect=AssertionError("API must not query host"))
    monkeypatch.setattr(producer, "collect_service", collect)
    with TestClient(api.app) as client:
        assert client.get("/api/operator/v1/runtime-service").status_code == 200
    collect.assert_not_called()
