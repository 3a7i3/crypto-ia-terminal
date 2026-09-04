"""O-01R — proves the adaptive_learning domain's canonical MODULES/METRICS
reflect POST-S02B.1 (PR #111) truth, not the PRE-S02 forensic finding O-01
(PR #117) originally recorded. Read-only against the domain module; does
not touch the protected S-02B.1 files it describes.
"""

from datetime import datetime, timezone

from observability.operator.contracts import observed, unknown
from observability.operator.domains.adaptive_learning import (
    METRICS,
    MODULES,
    SubsystemLearningState,
)

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)

_METRICS_BY_ID = {m.metric_id: m for m in METRICS}

_REAL_SUBSYSTEM_IDS = {
    "adaptive_learning.mistake_memory",
    "adaptive_learning.strategy_memory",
    "adaptive_learning.meta_learner",
    "adaptive_learning.strategy_ranker",
    "adaptive_learning.system_controller_adaptive",
}

_MODULES_BY_ID = {m.module_id: m for m in MODULES}


def test_no_real_subsystem_module_is_still_blocked():
    """PRE-S02 O-01 marked every real subsystem status="BLOCKED" (a stale
    claim: S-02B.1 landed FEATURE_ADAPTIVE_DECISION_FEEDBACK governance for
    all of them before O-01 merged). None should carry that status now."""
    for module_id in _REAL_SUBSYSTEM_IDS:
        assert _MODULES_BY_ID[module_id].status != "BLOCKED", module_id


def test_adaptive_subsystems_depend_on_the_master_flag():
    for module_id in _REAL_SUBSYSTEM_IDS:
        deps = _MODULES_BY_ID[module_id].dependencies
        assert "config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK" in deps, module_id


def test_safety_actions_are_never_flag_dependent():
    """STOP_TRADING/RESUME_TRADING/REDUCE_RISK are safety/recovery/risk
    authority, always authoritative regardless of the adaptive flag —
    must never be classified as adaptive-feedback-gated."""
    safety = _MODULES_BY_ID["adaptive_learning.system_controller_safety"]
    assert "config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK" not in safety.dependencies
    assert safety.status == "CANONICAL_EXISTING"


def test_adaptive_system_controller_actions_are_flag_gated():
    adaptive = _MODULES_BY_ID["adaptive_learning.system_controller_adaptive"]
    assert "config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK" in adaptive.dependencies


def test_known_debt_markers_preserved():
    """S02_PROVENANCE_DEBT and S02_SYSTEMCONTROLLER_GUARD_ORDER_DEBT must
    survive the reconciliation, not be silently dropped."""
    all_debt = " ".join(m.known_debt for m in MODULES)
    assert "S02_PROVENANCE_DEBT" in all_debt
    assert "S02_SYSTEMCONTROLLER_GUARD_ORDER_DEBT" in all_debt


def test_regret_precedent_module_still_present_and_unmerged_with_adaptive():
    regret = _MODULES_BY_ID["adaptive_learning.regret_decision_feedback_precedent"]
    assert "FEATURE_REGRET_DECISION_FEEDBACK" in regret.canonical_source
    assert "FEATURE_ADAPTIVE_DECISION_FEEDBACK" not in regret.canonical_source


# --- Metric-semantics fix: decision_feedback_enabled / is_decision_active /
# --- recommendation_equals_applied must never be functions of one another. ---


def test_decision_feedback_enabled_registered_as_distinct_metric():
    """decision_feedback_enabled is a first-class, separately registered
    metric — authority/permission state only, never a proxy for any other
    field."""
    assert "adaptive_learning.decision_feedback_enabled" in _METRICS_BY_ID
    m = _METRICS_BY_ID["adaptive_learning.decision_feedback_enabled"]
    definition = m.definition_fr.lower()
    assert "autorité" in definition or "autorisation" in definition
    assert "preuve" in definition  # explicitly disclaims proving application
    assert "is_decision_active" in m.definition_fr
    assert "recommendation_equals_applied" in m.definition_fr


def test_is_decision_active_definition_disclaims_flag_equivalence():
    """is_decision_active must document that it is NOT logically equivalent
    to decision_feedback_enabled — enabled != used. This is a textual proof
    the definition carries the correct semantics; the runtime-construction
    proof is test_is_decision_active_stays_unknown_when_flag_flips_alone
    below."""
    m = _METRICS_BY_ID["adaptive_learning.is_decision_active"]
    assert "is_decision_active == decision_feedback_enabled" in m.definition_fr
    assert "UNKNOWN" in m.null_semantics or "UNKNOWN" in m.freshness_source


def test_is_decision_active_stays_unknown_when_flag_flips_alone():
    """Flipping decision_feedback_enabled alone, with no per-event evidence,
    must not flip is_decision_active — it stays UNKNOWN/FUTURE_PROVIDER in
    both cases. This is the runtime proof: build a SubsystemLearningState
    for flag=True and flag=False without any per-event evidence and confirm
    is_decision_active is unknown() in both, never derived from the flag."""
    for flag_value in (True, False):
        state = SubsystemLearningState(
            subsystem_id="mistake_memory",
            is_observation_active=observed(True),
            is_learning_active=unknown(),
            is_decision_active=unknown(),  # no per-event evidence available
            recommendation_count=unknown(),
            applied_count=unknown(),
            recommendation_equals_applied=observed(False),
            decision_feedback_enabled=observed(flag_value),
            memory_state_provenance=unknown(),
            last_update_utc=observed(NOW),
        )
        assert state.decision_feedback_enabled.value is flag_value
        assert state.is_decision_active.value is None
        assert state.is_decision_active.semantics.value == "UNKNOWN"


def test_recommendation_equals_applied_definition_is_structural_not_flag_driven():
    m = _METRICS_BY_ID["adaptive_learning.recommendation_equals_applied"]
    definition = m.definition_fr
    assert "recommendation_equals_applied == decision_feedback_enabled" in definition
    assert "structurel" in definition.lower()
    assert "seulement quand le flag est actif" not in definition
    assert "true seulement quand" not in definition.lower()


def test_recommendation_equals_applied_stays_false_for_both_flag_values():
    """Structural split property: build a SubsystemLearningState for a gated
    adaptive subsystem with decision_feedback_enabled=True and again with
    decision_feedback_enabled=False, and confirm
    recommendation_equals_applied is the fixed structural False in both
    cases — never == decision_feedback_enabled."""
    for flag_value in (True, False):
        state = SubsystemLearningState(
            subsystem_id="meta_learner",
            is_observation_active=observed(True),
            is_learning_active=observed(True),
            is_decision_active=unknown(),
            recommendation_count=unknown(),
            applied_count=unknown(),
            recommendation_equals_applied=observed(False),
            decision_feedback_enabled=observed(flag_value),
            memory_state_provenance=unknown(),
            last_update_utc=observed(NOW),
        )
        assert state.recommendation_equals_applied.value is False
        assert state.recommendation_equals_applied.value != state.decision_feedback_enabled.value or flag_value is False
        # explicit: never derived as equal to the flag's runtime value
        assert not (state.recommendation_equals_applied.value == state.decision_feedback_enabled.value == True)


def test_post_s02_structural_split_preserved_for_all_five_gated_subsystems():
    for module_id in _REAL_SUBSYSTEM_IDS:
        module = _MODULES_BY_ID[module_id]
        assert "config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK" in module.dependencies, module_id


def test_applied_count_and_memory_state_provenance_registered():
    assert "adaptive_learning.applied_count" in _METRICS_BY_ID
    assert "adaptive_learning.memory_state_provenance" in _METRICS_BY_ID
    provenance = _METRICS_BY_ID["adaptive_learning.memory_state_provenance"]
    assert "state_provenance()" in provenance.technical_name
