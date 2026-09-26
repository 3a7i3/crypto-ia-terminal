from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import observability.operator_api.app as api_app
from observability.operator_api.research_lab_reader import ResearchLabSnapshotReader
from observability.research_lab_snapshot import (
    publish_research_lab_snapshot,
    snapshot_sha256,
    validate_research_lab_snapshot,
)

DATASET_ID = "1" * 64
BOUNDARY_ID = "2" * 64
RESEARCH_RUN_ID = "3" * 64
DIAG_RUN_ID = "4" * 64
CONFIG_HASH = "5" * 64
ARTIFACT_SHA = "6" * 64
RESEARCH_SHA = "a" * 40
BUILDER_SHA = "b" * 40


def _metric(
    name: str,
    value,
    *,
    evidence_status: str = "COMPLETE",
    statistical_strength: str = "LOW_SAMPLE",
    population_n: int = 13,
    unit: str = "usd",
    reason: str | None = None,
):
    return {
        "metric_name": name,
        "value": value,
        "unit": unit,
        "evidence_status": evidence_status,
        "statistical_strength": statistical_strength,
        "population_n": population_n,
        "derivation": "producer-authored fixture evidence",
        "source_ref": "diag-a4",
        "reason": reason,
    }


def _valid_snapshot() -> dict:
    return {
        "schema_version": "1.0.0",
        "product": "ResearchLabSnapshot",
        "domain": "research_lab",
        "authority": "RESEARCH_NON_AUTHORITATIVE",
        "generated_at_utc": "2026-09-26T01:00:00Z",
        "presentation_builder_source_sha": BUILDER_SHA,
        "research_state": "AVAILABLE",
        "provenance": {
            "primary_context": {
                "dataset_id": DATASET_ID,
                "source_boundary_id": BOUNDARY_ID,
                "paper_epoch_id": "FIXTURE-EPOCH",
                "research_run_id": RESEARCH_RUN_ID,
                "diagnostic_run_id": DIAG_RUN_ID,
                "research_source_code_sha": RESEARCH_SHA,
                "research_config_hash": CONFIG_HASH,
                "presentation_builder_source_sha": BUILDER_SHA,
                "population_definition": "POSITION_CLOSED_FOR_PERFORMANCE",
                "n": 13,
                "evidence_status": "COMPLETE",
                "statistical_strength": "LOW_SAMPLE",
            },
            "source_artifacts": [
                {
                    "artifact_ref": "diag-a4",
                    "artifact_type": "RL_DIAG_RESULT",
                    "sha256": ARTIFACT_SHA,
                }
            ],
        },
        "population": {
            "population_definition": "POSITION_CLOSED_FOR_PERFORMANCE",
            "n": 13,
            "evidence_status": "COMPLETE",
            "statistical_strength": "LOW_SAMPLE",
        },
        "performance": [
            _metric("net_realized_pnl_usd", 1.86357),
            _metric("profit_factor", 3.4994, unit="ratio"),
            _metric(
                "annualized_sharpe",
                None,
                evidence_status="NOT_AVAILABLE",
                statistical_strength="NOT_EVALUATED",
                unit="ratio",
                reason="No certified time-series/annualized return basis.",
            ),
        ],
        "risk_stability": [
            _metric("realized_close_to_close_maxdd", 0.00045, unit="ratio"),
            _metric(
                "mark_to_market_maxdd",
                None,
                evidence_status="NOT_AVAILABLE",
                statistical_strength="NOT_EVALUATED",
                unit="ratio",
                reason="No authoritative mark-to-market path.",
            ),
        ],
        "costs": [
            _metric("fees_usd", 0.26),
            _metric(
                "funding_usd",
                None,
                evidence_status="NOT_AVAILABLE",
                statistical_strength="NOT_EVALUATED",
                reason="No certified funding stream.",
            ),
        ],
        "attribution": [
            {
                "dimension": "packet_regime",
                "evidence_status": "COMPLETE",
                "statistical_strength": "LOW_SAMPLE",
                "rows": [
                    {
                        "label": "TREND_BULL",
                        "population_n": 9,
                        "metrics": [
                            _metric(
                                "net_realized_pnl_usd",
                                1.97,
                                population_n=9,
                            )
                        ],
                    },
                    {
                        "label": "RANGE",
                        "population_n": 4,
                        "metrics": [
                            _metric(
                                "net_realized_pnl_usd",
                                -0.10,
                                population_n=4,
                            )
                        ],
                    },
                ],
            }
        ],
        "candidate_registry": {
            "candidate_count": 0,
            "rows": [],
        },
        "limitations": [
            "FIXTURE_ONLY",
            "LOW_SAMPLE",
            "NO_MARK_TO_MARKET_PATH",
        ],
    }


def test_valid_research_lab_snapshot_is_admitted() -> None:
    doc = _valid_snapshot()
    assert validate_research_lab_snapshot(doc) is True


def test_unknown_top_level_field_fails_closed() -> None:
    doc = _valid_snapshot()
    doc["invented"] = "not allowed"
    assert validate_research_lab_snapshot(doc) is False


def test_wrong_authority_fails_closed() -> None:
    doc = _valid_snapshot()
    doc["authority"] = "PPL_AUTHORITY"
    assert validate_research_lab_snapshot(doc) is False


def test_research_and_presentation_source_sha_cannot_be_substituted() -> None:
    doc = _valid_snapshot()
    doc["provenance"]["primary_context"]["presentation_builder_source_sha"] = RESEARCH_SHA
    assert validate_research_lab_snapshot(doc) is False


def test_not_available_metric_cannot_publish_numeric_zero() -> None:
    doc = _valid_snapshot()
    sharpe = next(m for m in doc["performance"] if m["metric_name"] == "annualized_sharpe")
    sharpe["value"] = 0
    assert validate_research_lab_snapshot(doc) is False


def test_not_available_metric_requires_reason() -> None:
    doc = _valid_snapshot()
    sharpe = next(m for m in doc["performance"] if m["metric_name"] == "annualized_sharpe")
    sharpe["reason"] = None
    assert validate_research_lab_snapshot(doc) is False


def test_metric_source_ref_must_bind_known_artifact() -> None:
    doc = _valid_snapshot()
    doc["performance"][0]["source_ref"] = "unknown-source"
    assert validate_research_lab_snapshot(doc) is False


def test_candidate_registry_count_must_match_rows() -> None:
    doc = _valid_snapshot()
    doc["candidate_registry"]["candidate_count"] = 1
    assert validate_research_lab_snapshot(doc) is False


def test_empty_state_cannot_hide_nonempty_scientific_population() -> None:
    doc = _valid_snapshot()
    doc["research_state"] = "EMPTY"
    assert validate_research_lab_snapshot(doc) is False


def test_snapshot_hash_is_deterministic() -> None:
    a = _valid_snapshot()
    b = copy.deepcopy(a)
    assert snapshot_sha256(a) == snapshot_sha256(b)


def test_atomic_publisher_writes_only_valid_snapshot(tmp_path: Path) -> None:
    target = tmp_path / "research" / "snapshot.json"
    doc = _valid_snapshot()

    digest = publish_research_lab_snapshot(target, doc)

    assert target.is_file()
    assert digest == snapshot_sha256(doc)
    assert json.loads(target.read_text(encoding="utf-8")) == doc
    assert list(target.parent.glob(".*.tmp")) == []


def test_atomic_publisher_rejects_invalid_snapshot_without_writing(tmp_path: Path) -> None:
    target = tmp_path / "snapshot.json"
    doc = _valid_snapshot()
    doc["authority"] = "PPL_AUTHORITY"

    with pytest.raises(ValueError, match="closed schema"):
        publish_research_lab_snapshot(target, doc)

    assert not target.exists()


def test_reader_returns_exact_validated_snapshot(tmp_path: Path) -> None:
    target = tmp_path / "snapshot.json"
    doc = _valid_snapshot()
    publish_research_lab_snapshot(target, doc)

    result = ResearchLabSnapshotReader(path=target).read()

    assert result.ok is True
    assert result.snapshot == doc


def test_reader_missing_is_structured_unavailable(tmp_path: Path) -> None:
    result = ResearchLabSnapshotReader(path=tmp_path / "missing.json").read()
    assert result.ok is False
    assert result.error_code == "RESEARCH_LAB_SNAPSHOT_MISSING"


def test_reader_malformed_json_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "bad.json"
    target.write_text("{bad", encoding="utf-8")

    result = ResearchLabSnapshotReader(path=target).read()

    assert result.ok is False
    assert result.error_code == "RESEARCH_LAB_MALFORMED_JSON"


def test_reader_invalid_schema_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "snapshot.json"
    doc = _valid_snapshot()
    doc["domain"] = "paper_science"
    target.write_text(json.dumps(doc), encoding="utf-8")

    result = ResearchLabSnapshotReader(path=target).read()

    assert result.ok is False
    assert result.error_code == "RESEARCH_LAB_INVALID_SCHEMA"


def test_api_research_lab_route_returns_validated_snapshot(tmp_path: Path) -> None:
    target = tmp_path / "snapshot.json"
    doc = _valid_snapshot()
    publish_research_lab_snapshot(target, doc)
    api_app.configure_research_lab_reader(path=target)

    client = TestClient(api_app.app)
    response = client.get("/api/operator/v1/research-lab")

    assert response.status_code == 200
    assert response.json() == doc


def test_api_research_lab_route_missing_returns_503(tmp_path: Path) -> None:
    api_app.configure_research_lab_reader(path=tmp_path / "missing.json")
    client = TestClient(api_app.app)

    response = client.get("/api/operator/v1/research-lab")

    assert response.status_code == 503
    assert response.json()["error_code"] == "RESEARCH_LAB_SNAPSHOT_MISSING"


def test_research_lab_route_has_no_mutating_methods() -> None:
    route = next(
        route
        for route in api_app.app.routes
        if getattr(route, "path", None) == "/api/operator/v1/research-lab"
    )
    methods = getattr(route, "methods", set()) or set()
    assert methods == {"GET"}


def test_research_reader_source_has_no_jsonl_or_engine_access() -> None:
    import observability.operator_api.research_lab_reader as reader_mod

    source = Path(reader_mod.__file__).read_text(encoding="utf-8")
    lowered = source.lower()

    assert ".jsonl" not in lowered
    assert "paper_trades" not in lowered
    assert "research_data" not in lowered
    assert "research_replay" not in lowered
    assert "research_diag" not in lowered
    assert "research_candidate" not in lowered


def test_research_api_read_does_not_modify_presentation_artifact(tmp_path: Path) -> None:
    target = tmp_path / "snapshot.json"
    publish_research_lab_snapshot(target, _valid_snapshot())
    before = target.read_bytes()
    before_mtime = target.stat().st_mtime_ns

    api_app.configure_research_lab_reader(path=target)
    client = TestClient(api_app.app)
    assert client.get("/api/operator/v1/research-lab").status_code == 200

    assert target.read_bytes() == before
    assert target.stat().st_mtime_ns == before_mtime
