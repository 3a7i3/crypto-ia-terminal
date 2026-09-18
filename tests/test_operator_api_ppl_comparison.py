from __future__ import annotations

import json
import threading

from fastapi.testclient import TestClient

from observability.operator_api import app as api_app
from observability.operator_api.ppl_comparison_reader import (
    PplComparisonSnapshotReader,
    validate_ppl_comparison_snapshot,
)
from observability.ppl_comparison import build_ppl_comparison_snapshot


class _OffSim:
    def __init__(self):
        self._lock = threading.Lock()
        self._capital = 10.0
        self._initial_capital = 10.0
        self._positions = {}
        self._closed = []
        self._shadow_observer = None


def _doc():
    return build_ppl_comparison_snapshot(
        _OffSim(),
        cycle=1,
        process_instance_id="p1",
        source_sha="a" * 40,
        now_fn=lambda: 100.0,
    )


def test_closed_schema_accepts_real_producer_document():
    assert validate_ppl_comparison_snapshot(_doc())


def test_reader_returns_missing_as_structured_failure(tmp_path):
    result = PplComparisonSnapshotReader(
        tmp_path / "missing.json",
        now_fn=lambda: 100.0,
    ).read()
    assert not result.ok
    assert result.error_code == "PPL_COMPARISON_SNAPSHOT_MISSING"


def test_reader_rejects_unknown_financial_field(tmp_path):
    doc = _doc()
    doc["invented_finance"] = 123
    path = tmp_path / "comparison.json"
    path.write_text(json.dumps(doc), encoding="utf-8")

    result = PplComparisonSnapshotReader(
        path,
        now_fn=lambda: 100.0,
    ).read()
    assert not result.ok
    assert result.error_code == "PPL_COMPARISON_INVALID_SCHEMA"


def test_get_route_transports_producer_values_without_recomputation(tmp_path):
    doc = _doc()
    path = tmp_path / "comparison.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    api_app.configure_ppl_comparison_reader(
        path,
        stale_after_s=90.0,
        now_fn=lambda: 120.0,
    )

    response = TestClient(api_app.app).get(
        "/api/operator/v1/ppl-comparison"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["shadow_status"] == "OFF"
    assert body["comparison_available"] is False
    assert body["comparisons"] == []
    assert body["snapshot_age_s"] == 20.0
    assert body["freshness_classification"] == "FRESH"


def test_get_route_missing_artifact_is_honest_503(tmp_path):
    api_app.configure_ppl_comparison_reader(
        tmp_path / "missing.json",
        now_fn=lambda: 120.0,
    )
    response = TestClient(api_app.app).get(
        "/api/operator/v1/ppl-comparison"
    )
    assert response.status_code == 503
    assert response.json()["error_code"] == (
        "PPL_COMPARISON_SNAPSHOT_MISSING"
    )


def test_reader_rejects_invented_nested_authority_provenance(tmp_path):
    doc = _doc()
    doc["legacy_source"]["invented_authority_hint"] = "TRUST_ME"
    path = tmp_path / "comparison.json"
    path.write_text(json.dumps(doc), encoding="utf-8")

    result = PplComparisonSnapshotReader(
        path,
        now_fn=lambda: 100.0,
    ).read()
    assert not result.ok
    assert result.error_code == "PPL_COMPARISON_INVALID_SCHEMA"



def test_reader_rejects_inconsistent_summary_counts(tmp_path):
    doc = _doc()
    doc["summary"]["equal"] = 1
    path = tmp_path / "comparison.json"
    path.write_text(json.dumps(doc), encoding="utf-8")

    result = PplComparisonSnapshotReader(
        path,
        now_fn=lambda: 100.0,
    ).read()
    assert not result.ok
    assert result.error_code == "PPL_COMPARISON_INVALID_SCHEMA"


def test_reader_rejects_non_finite_json_constants(tmp_path):
    path = tmp_path / "comparison.json"
    path.write_text(
        '{"schema_version": NaN}',
        encoding="utf-8",
    )

    result = PplComparisonSnapshotReader(
        path,
        now_fn=lambda: 100.0,
    ).read()
    assert not result.ok
    assert result.error_code == "PPL_COMPARISON_MALFORMED_JSON"
