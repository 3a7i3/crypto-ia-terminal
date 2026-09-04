"""Blocker B remediation (independent review, O01_REMEDIATION_REQUIRED §3):
DomainSnapshot.to_dict() previously serialized only the generic spine and
silently dropped every domain-specific field a subclass added. The fix is
at the shared contract layer (DomainSnapshot.to_dict() now walks
dataclasses.fields(self), which includes inherited + subclass fields) —
these tests prove it holds for every one of the 11 domains, that nested
ObservedValue/PercentageMetric/dataclass/mapping/sequence fields survive,
and that the result is genuinely JSON-serializable with the stdlib
encoder alone.
"""

import json
from dataclasses import fields
from datetime import datetime, timezone

import pytest

from observability.operator.contracts import (
    DomainSnapshot,
    FreshnessStatus,
    PercentageMetric,
    observed,
    unavailable,
    unknown,
)
from observability.operator.domains.adaptive_learning import (
    SubsystemLearningState,
    compose_adaptive_learning_state_snapshot,
)
from observability.operator.domains.attrition import compose_attrition_snapshot
from observability.operator.domains.data_freshness import DatasetFreshness, compose_data_freshness_snapshot
from observability.operator.domains.decision_pipeline import StageObservation, compose_decision_pipeline_snapshot
from observability.operator.domains.disk_io import StorageBucket, compose_disk_io_snapshot
from observability.operator.domains.execution_state import compose_execution_state_snapshot
from observability.operator.domains.market_state import compose_market_state_snapshot
from observability.operator.domains.operator_summary import compose_operator_summary
from observability.operator.domains.portfolio_state import compose_portfolio_state_snapshot
from observability.operator.domains.regret_state import compose_regret_state_snapshot
from observability.operator.domains.system_health import compose_system_health_snapshot

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def _system_health():
    return compose_system_health_snapshot(
        observed_at_utc=NOW,
        boot_alive=observed(True),
        health_score=observed(87.5),
        health_level=observed("HEALTHY"),
        exchange_connectivity_healthy=observed(True),
        exchange_latency_ms=observed(42.0),
        module_statuses={"advisor_loop": "HEALTHY"},
        freshness=FreshnessStatus.FRESH,
        status="OK",
        degraded_reasons=("none",),
    )


def _market_state():
    return compose_market_state_snapshot(
        observed_at_utc=NOW,
        regime=observed("TRENDING"),
        regime_confidence=unavailable(),
        exchange_latency_ms=observed(10.0),
        exchange_uptime_pct=observed(99.9),
        universe_size=unknown(),
        instruments_with_valid_data=observed(135),
        freshness=FreshnessStatus.FRESH,
        status="OK",
    )


def _decision_pipeline():
    stage = StageObservation(
        stage_id="risk_gate",
        label_fr="Contrôle de risque",
        status="BLOCKED",
        input_count=observed(12),
        output_count=observed(9),
        rejection_count=observed(3),
        reason=observed("drawdown_ok=False"),
    )
    return compose_decision_pipeline_snapshot(
        observed_at_utc=NOW,
        stages=[stage],
        trade_allowed=observed(False),
        first_blocker=observed("risk_gate"),
        freshness=FreshnessStatus.FRESH,
        status="OK",
    )


def _attrition():
    return compose_attrition_snapshot(
        observed_at_utc=NOW,
        by_layer_breakdown={"risk_gate": 4, "meta_strategy": 16},
        dominant_blocker="meta_strategy",
        rejection_rate_over_rejections=PercentageMetric(
            numerator=4, denominator=20, numerator_label="refus risque", denominator_label="refus totaux"
        ),
        execution_ratio=PercentageMetric(
            numerator=5, denominator=25, numerator_label="exécutés", denominator_label="exécutés + refusés"
        ),
        freshness=FreshnessStatus.FRESH,
        status="OK",
    )


def _portfolio_state():
    return compose_portfolio_state_snapshot(
        observed_at_utc=NOW,
        paper_equity_usd=observed(1000.0),
        paper_open_positions_count=observed(3),
        paper_unrealized_pnl_usd=observed(-12.5),
        paper_realized_pnl_usd=observed(50.0),
        real_account_equity_usd=unavailable(),
        real_account_free_usd=unavailable(),
        real_account_stale=observed(False),
        freshness=FreshnessStatus.FRESH,
        status="OK",
    )


def _execution_state():
    return compose_execution_state_snapshot(
        observed_at_utc=NOW,
        mode=observed("paper"),
        paper_trading_enabled=observed(True),
        live_trading_confirmed=observed(False),
        orders_attempted=observed(10),
        orders_accepted=observed(9),
        orders_rejected=observed(1),
        last_execution_utc=observed(NOW),
        freshness=FreshnessStatus.FRESH,
        status="OK",
    )


def _data_freshness():
    dataset = DatasetFreshness(
        dataset_id="regret_v2",
        source_dataset="databases/regret/regret_horizons_*.jsonl",
        source_producer="observability.regret_scheduler",
        last_event_utc=observed(NOW),
        last_valid_event_utc=observed(NOW),
        age_seconds=observed(30.0),
        expected_cadence_s=3600.0,
        freshness_threshold_s=3600.0,
        stale_threshold_s=7200.0,
        freshness_status=FreshnessStatus.FRESH,
    )
    return compose_data_freshness_snapshot(
        observed_at_utc=NOW,
        datasets={"regret_v2": dataset},
        freshness=FreshnessStatus.FRESH,
        status="OK",
    )


def _regret_state():
    return compose_regret_state_snapshot(
        observed_at_utc=NOW,
        v2_active=observed(True),
        canonical_horizon=observed("1h"),
        last_event_utc=observed(NOW),
        last_canonical_evaluated_utc=observed(NOW),
        canonical_freshness=FreshnessStatus.FRESH,
        pending_candidate_count=observed(0),
        horizon_status_counts={"EVALUATED": 10, "PENDING": 2},
        malformed_count=observed(0),
        decision_feedback_enabled=observed(False),
        status="OK",
    )


def _adaptive_learning():
    subsystem = SubsystemLearningState(
        subsystem_id="mistake_memory",
        is_observation_active=observed(True),
        is_learning_active=unknown(),
        is_decision_active=observed(True),
        recommendation_count=unknown(),
        applied_count=unknown(),
        recommendation_equals_applied=observed(True),
        decision_feedback_enabled=unavailable(),
        memory_state_provenance=observed("databases/mistake_memory.jsonl"),
        last_update_utc=observed(NOW),
    )
    return compose_adaptive_learning_state_snapshot(
        observed_at_utc=NOW,
        subsystems={"mistake_memory": subsystem},
        freshness=FreshnessStatus.UNKNOWN,
        status="ATTENTION_REQUIRED",
    )


def _disk_io():
    bucket = StorageBucket(name="databases", allocated_bytes=1024, logical_bytes=900, regular_file_count=42)
    return compose_disk_io_snapshot(
        observed_at_utc=NOW,
        total_bytes=observed(1_000_000_000),
        used_bytes=observed(400_000_000),
        free_bytes=observed(600_000_000),
        utilization_pct=observed(40.0),
        attributed_bytes=observed(380_000_000),
        residual_bytes=unknown(),
        buckets=[bucket],
        last_attribution_snapshot_utc=observed(NOW),
        growth_comparable=observed(False),
        freshness=FreshnessStatus.STALE,
        status="DEGRADED",
    )


def _operator_summary():
    return compose_operator_summary(observed_at_utc=NOW, system_health=_system_health())


ALL_DOMAIN_SNAPSHOTS = {
    "system_health": _system_health,
    "market_state": _market_state,
    "decision_pipeline": _decision_pipeline,
    "attrition": _attrition,
    "portfolio_state": _portfolio_state,
    "execution_state": _execution_state,
    "data_freshness": _data_freshness,
    "regret_state": _regret_state,
    "adaptive_learning": _adaptive_learning,
    "disk_io": _disk_io,
    "operator_summary": _operator_summary,
}


@pytest.mark.parametrize("domain_id, build", ALL_DOMAIN_SNAPSHOTS.items(), ids=list(ALL_DOMAIN_SNAPSHOTS))
def test_to_dict_contains_every_dataclass_field_for_every_domain(domain_id, build):
    snapshot = build()
    expected_field_names = {f.name for f in fields(snapshot)}
    actual_keys = set(snapshot.to_dict().keys())
    assert actual_keys == expected_field_names, (
        f"{domain_id}: to_dict() keys {actual_keys} != declared dataclass fields {expected_field_names}"
    )


@pytest.mark.parametrize("domain_id, build", ALL_DOMAIN_SNAPSHOTS.items(), ids=list(ALL_DOMAIN_SNAPSHOTS))
def test_to_dict_contains_generic_spine_for_every_domain(domain_id, build):
    snapshot = build()
    d = snapshot.to_dict()
    for spine_field in {f.name for f in fields(DomainSnapshot)}:
        assert spine_field in d, f"{domain_id}: missing spine field {spine_field!r}"


@pytest.mark.parametrize("domain_id, build", ALL_DOMAIN_SNAPSHOTS.items(), ids=list(ALL_DOMAIN_SNAPSHOTS))
def test_to_dict_is_json_dumpable_with_stdlib_encoder_only(domain_id, build):
    snapshot = build()
    serialized = json.dumps(snapshot.to_dict())
    assert isinstance(serialized, str)
    round_tripped = json.loads(serialized)
    assert round_tripped["domain"] == domain_id


# --- Explicit named checks for the domains the remediation brief calls out ---


def test_system_health_snapshot_serializes_domain_specific_fields():
    d = _system_health().to_dict()
    assert d["boot_alive"] == {"value": True, "semantics": "PRESENT"}
    assert d["health_score"] == {"value": 87.5, "semantics": "PRESENT"}
    assert d["module_statuses"] == {"advisor_loop": "HEALTHY"}
    assert d["degraded_reasons"] == ["none"]


def test_market_state_snapshot_serializes_domain_specific_fields():
    d = _market_state().to_dict()
    assert d["regime"] == {"value": "TRENDING", "semantics": "PRESENT"}
    assert d["regime_confidence"] == {"value": None, "semantics": "UNAVAILABLE"}
    assert d["universe_size"] == {"value": None, "semantics": "UNKNOWN"}


def test_decision_pipeline_snapshot_serializes_nested_stage_dataclass():
    d = _decision_pipeline().to_dict()
    assert d["stages"] == [
        {
            "stage_id": "risk_gate",
            "label_fr": "Contrôle de risque",
            "status": "BLOCKED",
            "input_count": {"value": 12, "semantics": "PRESENT"},
            "output_count": {"value": 9, "semantics": "PRESENT"},
            "rejection_count": {"value": 3, "semantics": "PRESENT"},
            "reason": {"value": "drawdown_ok=False", "semantics": "PRESENT"},
        }
    ]
    assert d["trade_allowed"] == {"value": False, "semantics": "FALSE"}


def test_portfolio_state_snapshot_keeps_paper_and_real_fields_distinct_when_serialized():
    d = _portfolio_state().to_dict()
    assert d["paper_equity_usd"] == {"value": 1000.0, "semantics": "PRESENT"}
    assert d["real_account_equity_usd"] == {"value": None, "semantics": "UNAVAILABLE"}
    assert "paper" not in str(d["real_account_equity_usd"]).lower()


def test_regret_state_snapshot_serializes_horizon_counts_and_freshness():
    d = _regret_state().to_dict()
    assert d["horizon_status_counts"] == {"EVALUATED": 10, "PENDING": 2}
    assert d["canonical_freshness"] == "FRESH"
    assert d["freshness"] == "FRESH"


def test_adaptive_learning_snapshot_serializes_nested_subsystem_dataclass():
    d = _adaptive_learning().to_dict()
    subsystem = d["subsystems"]["mistake_memory"]
    assert subsystem["subsystem_id"] == "mistake_memory"
    assert subsystem["is_learning_active"] == {"value": None, "semantics": "UNKNOWN"}
    assert subsystem["is_decision_active"] == {"value": True, "semantics": "PRESENT"}
    assert subsystem["last_update_utc"] == {"value": "2026-09-03T12:00:00+00:00", "semantics": "PRESENT"}


def test_operator_summary_serializes_component_list_and_attention_items():
    d = _operator_summary().to_dict()
    assert isinstance(d["components"], list)
    domains_present = {c["domain"] for c in d["components"]}
    assert "system_health" in domains_present
    assert "market_state" in domains_present  # present as UNAVAILABLE, not silently dropped
    assert isinstance(d["attention_items"], list)
    assert all(isinstance(item, str) for item in d["attention_items"])


def test_attrition_snapshot_serializes_percentage_metric_with_derived_pct():
    d = _attrition().to_dict()
    assert d["rejection_rate_over_rejections"] == {
        "numerator": 4,
        "denominator": 20,
        "numerator_label": "refus risque",
        "denominator_label": "refus totaux",
        "pct": 20.0,
    }


def test_disk_io_snapshot_serializes_nested_bucket_dataclass():
    d = _disk_io().to_dict()
    assert d["buckets"] == [
        {"name": "databases", "allocated_bytes": 1024, "logical_bytes": 900, "regular_file_count": 42}
    ]
