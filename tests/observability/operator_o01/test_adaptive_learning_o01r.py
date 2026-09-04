"""O-01R — proves the adaptive_learning domain's canonical MODULES/METRICS
reflect POST-S02B.1 (PR #111) truth, not the PRE-S02 forensic finding O-01
(PR #117) originally recorded. Read-only against the domain module; does
not touch the protected S-02B.1 files it describes.
"""

from observability.operator.domains.adaptive_learning import MODULES

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
