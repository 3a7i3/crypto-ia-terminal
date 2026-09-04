from datetime import datetime, timezone

from observability.operator.contracts import FreshnessStatus, PercentageMetric, observed, unavailable, unknown
from observability.operator.domains.adaptive_learning import (
    MODULES as ADAPTIVE_LEARNING_MODULES,
    SubsystemLearningState,
    compose_adaptive_learning_state_snapshot,
)
from observability.operator.domains.attrition import compose_attrition_snapshot
from observability.operator.domains.data_freshness import DatasetFreshness, compose_data_freshness_snapshot
from observability.operator.domains.decision_pipeline import (
    STAGE_LABELS_FR,
    PIPELINE_STAGES,
    StageObservation,
    compose_decision_pipeline_snapshot,
)
from observability.operator.domains.portfolio_state import compose_portfolio_state_snapshot
from observability.operator.domains.regret_state import compose_regret_state_snapshot
from observability.operator.domains.system_health import compose_system_health_snapshot

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def test_system_health_snapshot_roundtrips_observed_values():
    snap = compose_system_health_snapshot(
        observed_at_utc=NOW,
        boot_alive=observed(True),
        health_score=observed(87.5),
        health_level=observed("HEALTHY"),
        exchange_connectivity_healthy=observed(True),
        exchange_latency_ms=observed(42.0),
        module_statuses={"advisor_loop": "HEALTHY"},
        freshness=FreshnessStatus.FRESH,
        status="OK",
    )
    assert snap.domain == "system_health"
    assert snap.boot_alive.value is True
    assert snap.module_statuses == {"advisor_loop": "HEALTHY"}
    d = snap.to_dict()
    assert d["domain"] == "system_health"


def test_decision_pipeline_stage_rejects_unknown_stage_id():
    import pytest

    with pytest.raises(ValueError):
        StageObservation(
            stage_id="not_a_stage",
            label_fr="x",
            status="PASSED",
            input_count=observed(1),
            output_count=observed(1),
            rejection_count=observed(0),
            reason=unknown(),
        )


def test_all_pipeline_stages_have_french_labels():
    for stage_id in PIPELINE_STAGES:
        assert STAGE_LABELS_FR[stage_id].strip()


def test_decision_pipeline_snapshot_composes_stage_list():
    stage = StageObservation(
        stage_id="risk_gate",
        label_fr=STAGE_LABELS_FR["risk_gate"],
        status="BLOCKED",
        input_count=observed(12),
        output_count=observed(9),
        rejection_count=observed(3),
        reason=observed("drawdown_ok=False"),
    )
    snap = compose_decision_pipeline_snapshot(
        observed_at_utc=NOW,
        stages=[stage],
        trade_allowed=observed(False),
        first_blocker=observed("risk_gate"),
        freshness=FreshnessStatus.FRESH,
        status="OK",
    )
    assert len(snap.stages) == 1
    assert snap.stages[0].rejection_count.value == 3


def test_attrition_percentage_metric_has_explicit_numerator_denominator():
    pct = PercentageMetric(
        numerator=4,
        denominator=20,
        numerator_label="refus attribués à la couche risque",
        denominator_label="total des enregistrements de refus dans la fenêtre",
    )
    snap = compose_attrition_snapshot(
        observed_at_utc=NOW,
        by_layer_breakdown={"risk_gate": 4, "meta_strategy": 16},
        dominant_blocker="meta_strategy",
        rejection_rate_over_rejections=pct,
        execution_ratio=PercentageMetric(
            numerator=5, denominator=25, numerator_label="exécutés", denominator_label="exécutés + refusés"
        ),
        freshness=FreshnessStatus.FRESH,
        status="OK",
    )
    assert snap.rejection_rate_over_rejections.pct == 20.0
    assert snap.by_layer_breakdown["meta_strategy"] == 16


def test_portfolio_state_never_mixes_paper_and_real_fields():
    snap = compose_portfolio_state_snapshot(
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
    assert snap.paper_equity_usd.value == 1000.0
    assert snap.real_account_equity_usd.value is None
    assert snap.real_account_equity_usd.semantics.value == "UNAVAILABLE"


def test_regret_state_freshness_is_the_canonical_evaluated_clock_not_last_write():
    snap = compose_regret_state_snapshot(
        observed_at_utc=NOW,
        v2_active=observed(True),
        canonical_horizon=observed("1h"),
        last_event_utc=observed(NOW),
        last_canonical_evaluated_utc=unknown(),
        canonical_freshness=FreshnessStatus.UNKNOWN,
        pending_candidate_count=observed(0),
        horizon_status_counts={"EVALUATED": 10, "PENDING": 2},
        malformed_count=observed(0),
        decision_feedback_enabled=observed(False),
        status="DEGRADED",
    )
    assert snap.freshness == FreshnessStatus.UNKNOWN
    assert snap.last_event_utc.value == NOW
    assert snap.last_canonical_evaluated_utc.semantics.value == "UNKNOWN"


def test_data_freshness_dataset_carries_its_own_thresholds():
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
    snap = compose_data_freshness_snapshot(
        observed_at_utc=NOW,
        datasets={"regret_v2": dataset},
        freshness=FreshnessStatus.FRESH,
        status="OK",
    )
    assert snap.datasets["regret_v2"].freshness_status == FreshnessStatus.FRESH


# --- POST-S-02 integration: adaptive_learning must distinguish SAFETY
# AUTHORITY from ADAPTIVE AUTHORITY as two separate module entries
# (mission §8) — never one opaque "adaptive action" state. ---


def test_adaptive_learning_modules_separate_safety_from_adaptive_authority():
    module_ids = {m.module_id for m in ADAPTIVE_LEARNING_MODULES}
    assert "adaptive_learning.system_controller_safety" in module_ids
    assert "adaptive_learning.system_controller_adaptive" in module_ids


def test_system_controller_safety_module_is_never_described_as_gated():
    safety = next(
        m for m in ADAPTIVE_LEARNING_MODULES if m.module_id == "adaptive_learning.system_controller_safety"
    )
    assert "config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK" not in safety.dependencies
    assert "gated" not in safety.known_debt.lower() or "jamais gated" in safety.known_debt.lower()


def test_system_controller_adaptive_module_declares_the_gating_dependency():
    adaptive = next(
        m for m in ADAPTIVE_LEARNING_MODULES if m.module_id == "adaptive_learning.system_controller_adaptive"
    )
    assert "config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK" in adaptive.dependencies


def test_adaptive_learning_covers_strategy_ranker_post_s02():
    module_ids = {m.module_id for m in ADAPTIVE_LEARNING_MODULES}
    assert "adaptive_learning.strategy_ranker" in module_ids


def test_compose_adaptive_learning_state_snapshot_with_full_post_s02_subsystem_set():
    def _subsystem(subsystem_id: str, is_decision_active) -> SubsystemLearningState:
        return SubsystemLearningState(
            subsystem_id=subsystem_id,
            is_observation_active=observed(True),
            is_learning_active=observed(True),
            is_decision_active=is_decision_active,
            recommendation_count=unknown(),
            applied_count=unknown(),
            recommendation_equals_applied=observed(False),
            decision_feedback_enabled=observed(False),
            memory_state_provenance=observed({"subsystem": subsystem_id}),
            last_update_utc=observed(NOW),
        )

    subsystems = {
        "mistake_memory": _subsystem("mistake_memory", observed(False)),
        "meta_learner": _subsystem("meta_learner", observed(False)),
        "strategy_memory": _subsystem("strategy_memory", observed(False)),
        "strategy_ranker": _subsystem("strategy_ranker", observed(False)),
        "system_controller_safety": _subsystem("system_controller_safety", observed(True)),
        "system_controller_adaptive": _subsystem("system_controller_adaptive", observed(False)),
    }
    snap = compose_adaptive_learning_state_snapshot(
        observed_at_utc=NOW,
        subsystems=subsystems,
        freshness=FreshnessStatus.FRESH,
        status="OK",
    )
    assert snap.subsystems["system_controller_safety"].is_decision_active.value is True
    assert snap.subsystems["system_controller_adaptive"].is_decision_active.value is False
    assert snap.subsystems["mistake_memory"].recommendation_equals_applied.value is False
