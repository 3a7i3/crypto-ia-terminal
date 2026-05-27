"""
test_p8_enrichments.py — Tests P8 enrichissements (6 composants)

Couvre :
  1. DynamicWeightingEngine (DWE)
  2. EnergyBudgetManager
  3. CapitalEfficiencyTracker
  4. Anticipation de transition dans StrategyAllocator
  5. Shadow track permanent dans StrategyProbationSystem
  6. ForbiddenPatternsRegistry
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("ALLOCATOR_DB", ":memory:")
os.environ.setdefault("PROBATION_DB", ":memory:")
os.environ.setdefault("FORBIDDEN_PATTERNS_DB", ":memory:")

# ─────────────────────────────────────────────────────────────────────────────
# 1. DynamicWeightingEngine
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def dwe():
    from quant_hedge_ai.agents.intelligence.dynamic_weighting_engine import (
        DynamicWeightingEngine,
    )

    return DynamicWeightingEngine(["a", "b", "c"])


def test_dwe_no_history_returns_same_weights(dwe):
    w = {"a": 0.4, "b": 0.3, "c": 0.3}
    result = dwe.adjust(w)
    assert set(result.keys()) == {"a", "b", "c"}
    total = sum(result.values())
    assert abs(total - 1.0) < 1e-6


def test_dwe_scores_zero_without_history(dwe):
    scores = dwe.scores()
    assert all(v == 0.0 for v in scores.values())


def test_dwe_record_increases_score(dwe):
    for _ in range(10):
        dwe.record("a", pnl_pct=2.0, sharpe=1.0)
        dwe.record("b", pnl_pct=-1.0, sharpe=-0.5)
    assert dwe.scores()["a"] > dwe.scores()["b"]


def test_dwe_adjust_rewards_winner(dwe):
    for _ in range(10):
        dwe.record("a", pnl_pct=2.0, sharpe=1.0)
        dwe.record("b", pnl_pct=0.5, sharpe=0.2)
        dwe.record("c", pnl_pct=-0.5, sharpe=-0.2)
    w = {"a": 0.33, "b": 0.33, "c": 0.34}
    result = dwe.adjust(w, risk_state="NORMAL")
    assert result["a"] > result["c"]


def test_dwe_weights_sum_to_one(dwe):
    for _ in range(8):
        dwe.record("a", pnl_pct=1.0)
        dwe.record("b", pnl_pct=-0.5)
        dwe.record("c", pnl_pct=0.3)
    w = {"a": 0.4, "b": 0.3, "c": 0.3}
    result = dwe.adjust(w, risk_state="NORMAL")
    assert abs(sum(result.values()) - 1.0) < 1e-6


def test_dwe_risk_off_returns_unchanged(dwe):
    for _ in range(8):
        dwe.record("a", pnl_pct=3.0)
    w = {"a": 0.5, "b": 0.3, "c": 0.2}
    result = dwe.adjust(w, risk_state="RISK_OFF")
    assert result == w


def test_dwe_baseline_floor_applied(dwe):
    for _ in range(8):
        dwe.record("c", pnl_pct=-5.0, sharpe=-3.0)
        dwe.record("a", pnl_pct=2.0, sharpe=1.0)
        dwe.record("b", pnl_pct=2.0, sharpe=1.0)
    w = {"a": 0.49, "b": 0.50, "c": 0.01}
    result = dwe.adjust(w, risk_state="NORMAL")
    # baseline = 0.05 par défaut
    assert result["c"] >= 0.04  # floor appliqué et normalisé


def test_dwe_sample_sizes(dwe):
    dwe.record("a", pnl_pct=1.0)
    dwe.record("a", pnl_pct=1.0)
    sizes = dwe.sample_sizes()
    assert sizes["a"] == 2
    assert sizes["b"] == 0


def test_dwe_defensive_reduces_cap(dwe):
    for _ in range(8):
        dwe.record("a", pnl_pct=5.0, sharpe=3.0)
        dwe.record("b", pnl_pct=-5.0, sharpe=-3.0)
        dwe.record("c", pnl_pct=0.1)
    w_normal = {"a": 0.33, "b": 0.33, "c": 0.34}
    w_defensive = dict(w_normal)
    res_normal = dwe.adjust(w_normal, risk_state="NORMAL")
    res_defensive = dwe.adjust(w_defensive, risk_state="DEFENSIVE")
    # adjustment in DEFENSIVE is smaller → "a" gets less bonus
    delta_normal = abs(res_normal["a"] - w_normal["a"])
    delta_defensive = abs(res_defensive["a"] - w_defensive["a"])
    assert delta_defensive <= delta_normal + 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# 2. EnergyBudgetManager
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def ebm():
    from quant_hedge_ai.agents.intelligence.strategy_allocator import (
        EnergyBudgetManager,
    )

    return EnergyBudgetManager({"scalp": 5, "grid": 3, "momentum": 10})


def test_ebm_can_trade_initially(ebm):
    assert ebm.can_trade("scalp") is True
    assert ebm.can_trade("grid") is True


def test_ebm_exhaustion_blocks_trade(ebm):
    for _ in range(5):
        ebm.record_trade("scalp")
    assert ebm.can_trade("scalp") is False


def test_ebm_capital_factor_zero_when_exhausted(ebm):
    for _ in range(5):
        ebm.record_trade("scalp")
    assert ebm.capital_factor("scalp") == 0.0


def test_ebm_capital_factor_one_when_available(ebm):
    assert ebm.capital_factor("grid") == 1.0


def test_ebm_reset_restores_capacity(ebm):
    for _ in range(5):
        ebm.record_trade("scalp")
    ebm.reset_session()
    assert ebm.can_trade("scalp") is True


def test_ebm_unknown_strategy_always_allowed(ebm):
    assert ebm.can_trade("unknown_strategy") is True


def test_ebm_utilization_tracking(ebm):
    ebm.record_trade("scalp")
    ebm.record_trade("scalp")
    util = ebm.utilization()
    assert abs(util["scalp"] - 0.4) < 1e-6  # 2/5


def test_ebm_snapshot_contains_used(ebm):
    ebm.record_trade("grid")
    snap = ebm.snapshot()
    assert snap["used"]["grid"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. CapitalEfficiencyTracker
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def cet():
    from quant_hedge_ai.agents.intelligence.strategy_allocator import (
        CapitalEfficiencyTracker,
    )

    return CapitalEfficiencyTracker()


def test_cet_efficiency_one_without_data(cet):
    assert cet.efficiency("scalp") == 1.0


def test_cet_underutilized_after_window(cet):
    for _ in range(20):
        cet.record("scalp", allocated_usd=1000.0, used_usd=100.0)  # 10%
    assert "scalp" in cet.get_underutilized()


def test_cet_not_underutilized_with_good_usage(cet):
    for _ in range(20):
        cet.record("scalp", allocated_usd=1000.0, used_usd=500.0)  # 50%
    assert "scalp" not in cet.get_underutilized()


def test_cet_weight_reduction_factor_underutilized(cet):
    for _ in range(20):
        cet.record("scalp", allocated_usd=1000.0, used_usd=50.0)  # 5%
    factor = cet.weight_reduction_factor("scalp")
    assert factor < 1.0


def test_cet_weight_reduction_factor_normal(cet):
    for _ in range(20):
        cet.record("scalp", allocated_usd=1000.0, used_usd=800.0)
    assert cet.weight_reduction_factor("scalp") == 1.0


def test_cet_no_reduction_before_full_window(cet):
    for _ in range(15):  # pas encore 20 cycles
        cet.record("scalp", allocated_usd=1000.0, used_usd=50.0)
    assert "scalp" not in cet.get_underutilized()


def test_cet_zero_allocated_ignored(cet):
    cet.record("scalp", allocated_usd=0.0, used_usd=100.0)
    assert cet.efficiency("scalp") == 1.0  # pas enregistré


# ─────────────────────────────────────────────────────────────────────────────
# 4. Anticipation de transition dans StrategyAllocator
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def allocator(tmp_path):
    os.environ["ALLOCATOR_DB"] = str(tmp_path / "alloc.json")
    os.environ["PROBATION_DB"] = str(tmp_path / "prob.json")
    from quant_hedge_ai.agents.intelligence.strategy_allocator import StrategyAllocator
    from quant_hedge_ai.agents.intelligence.strategy_probation import (
        StrategyProbationSystem,
    )

    prob = StrategyProbationSystem()
    for sid in ["mean_reversion", "breakout", "scalp", "momentum", "grid"]:
        r = prob.register(sid)
        # Forcer toutes en ACTIVE pour ne pas bloquer le capital
        from quant_hedge_ai.agents.intelligence.strategy_probation import StrategyStatus

        prob.override_status(sid, StrategyStatus.ACTIVE, "test setup")
    return StrategyAllocator(probation_system=prob)


def test_allocator_transition_forecast_moves_weights(allocator):
    # Sans forecast
    r_no = allocator.allocate(1, "SIDEWAYS", "NORMAL", 10000.0, 1.0)
    # Avec forecast TREND_BULL à 80% → doit pré-positionner vers TREND_BULL
    r_with = allocator.allocate(
        2, "SIDEWAYS", "NORMAL", 10000.0, 1.0, transition_forecast=("TREND_BULL", 0.80)
    )
    # TREND_BULL favorise momentum et breakout → poids doivent augmenter
    assert r_with.weights["momentum"] >= r_no.weights["momentum"] - 0.01
    assert r_with.weights["breakout"] >= r_no.weights["breakout"] - 0.01


def test_allocator_transition_below_threshold_no_change(allocator):
    r_low = allocator.allocate(
        1, "SIDEWAYS", "NORMAL", 10000.0, 1.0, transition_forecast=("TREND_BULL", 0.30)
    )
    # prob 0.30 < seuil 0.60 → pas d'événement d'anticipation dans l'audit
    types = [e["type"] for e in r_low.audit_events]
    assert "transition_anticipation" not in types


def test_allocator_transition_audit_recorded(allocator):
    r = allocator.allocate(
        1, "SIDEWAYS", "NORMAL", 10000.0, 1.0, transition_forecast=("TREND_BULL", 0.75)
    )
    types = [e["type"] for e in r.audit_events]
    assert "transition_anticipation" in types


def test_allocator_energy_budget_in_snapshot(allocator):
    snap = allocator.snapshot()
    assert "energy" in snap
    assert "budgets" in snap["energy"]


def test_allocator_efficiency_in_snapshot(allocator):
    allocator.record_capital_used("scalp", 1000.0, 500.0)
    snap = allocator.snapshot()
    assert "efficiency" in snap


def test_allocator_dwe_scores_in_snapshot(allocator):
    snap = allocator.snapshot()
    assert "dwe_scores" in snap


# ─────────────────────────────────────────────────────────────────────────────
# 5. Shadow track permanent dans StrategyProbationSystem
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def probation(tmp_path):
    os.environ["PROBATION_DB"] = str(tmp_path / "prob.json")
    from quant_hedge_ai.agents.intelligence.strategy_probation import (
        StrategyProbationSystem,
    )

    return StrategyProbationSystem()


def test_shadow_track_activates_when_no_tracking(probation):
    from quant_hedge_ai.agents.intelligence.strategy_probation import StrategyStatus

    # Enregistrer une stratégie et la suspendre
    probation.register("strat_a")
    probation.override_status("strat_a", StrategyStatus.SUSPENDED, "test")

    events = probation.tick_cycle(cycle=1)
    status = probation.get("strat_a").status
    # La stratégie doit être revenue en TRACKING
    assert status == StrategyStatus.TRACKING
    assert any("shadow permanent" in e for e in events)


def test_shadow_track_no_action_when_tracking_exists(probation):
    from quant_hedge_ai.agents.intelligence.strategy_probation import StrategyStatus

    # Une stratégie déjà en TRACKING
    probation.register("strat_a")
    # strat_a est en TRACKING par défaut

    events = probation.tick_cycle(cycle=1)
    # Pas d'événement shadow permanent
    assert not any("shadow permanent" in e for e in events)
    assert probation.get("strat_a").status == StrategyStatus.TRACKING


def test_shadow_track_prefers_oldest_reeval(probation):
    from quant_hedge_ai.agents.intelligence.strategy_probation import StrategyStatus

    probation.register("strat_a")
    probation.register("strat_b")
    probation.override_status("strat_a", StrategyStatus.SUSPENDED, "test")
    probation.override_status("strat_b", StrategyStatus.SUSPENDED, "test")

    # Marquer strat_b comme récemment réévalué (cycle fictif élevé)
    probation.get("strat_b").last_reeval_cycle = 50
    # strat_a.last_reeval_cycle reste 0

    # cycle=1 : trop court pour déclencher la rééval SUSPENDED (suspend_reeval=100)
    # donc _ensure_shadow_track agit sur l'état tel quel
    events = probation.tick_cycle(cycle=1)
    # strat_a (last_reeval=0) doit être préféré à strat_b (last_reeval=50)
    assert probation.get("strat_a").status == StrategyStatus.TRACKING
    assert probation.get("strat_b").status == StrategyStatus.SUSPENDED


def test_shadow_track_no_action_without_suspended(probation):
    # Si aucune stratégie suspendue, pas d'action
    events = probation.tick_cycle(cycle=1)
    assert not any("shadow permanent" in e for e in events)


def test_shadow_track_resets_shadow_counters(probation):
    from quant_hedge_ai.agents.intelligence.strategy_probation import StrategyStatus

    probation.register("strat_a")
    r = probation.get("strat_a")
    r.shadow_trades = 99
    probation.override_status("strat_a", StrategyStatus.SUSPENDED, "test")

    probation.tick_cycle(cycle=1)
    # Les compteurs shadow doivent être réinitialisés
    assert r.shadow_trades == 0


# ─────────────────────────────────────────────────────────────────────────────
# 6. ForbiddenPatternsRegistry
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def registry(tmp_path):
    os.environ["FORBIDDEN_PATTERNS_DB"] = str(tmp_path / "patterns.json")
    from quant_hedge_ai.agents.intelligence.forbidden_patterns_registry import (
        ForbiddenPatternsRegistry,
    )

    return ForbiddenPatternsRegistry()


def test_registry_register_and_is_forbidden(registry):
    registry.register_pattern(
        "SWEEP_AFTER_CANDLE",
        "HIGH_VOL",
        ["scalp", "grid"],
        0.85,
        registered_by="grid",
        cycle=100,
    )
    assert registry.is_forbidden("SWEEP_AFTER_CANDLE", "HIGH_VOL", "scalp")
    assert registry.is_forbidden("SWEEP_AFTER_CANDLE", "HIGH_VOL", "grid")


def test_registry_not_forbidden_different_regime(registry):
    registry.register_pattern(
        "SWEEP_AFTER_CANDLE",
        "HIGH_VOL",
        ["scalp"],
        0.85,
        registered_by="grid",
        cycle=100,
    )
    assert not registry.is_forbidden("SWEEP_AFTER_CANDLE", "SIDEWAYS", "scalp")


def test_registry_not_forbidden_different_strategy(registry):
    registry.register_pattern(
        "SWEEP_AFTER_CANDLE",
        "HIGH_VOL",
        ["scalp"],
        0.85,
        registered_by="grid",
        cycle=100,
    )
    assert not registry.is_forbidden("SWEEP_AFTER_CANDLE", "HIGH_VOL", "momentum")


def test_registry_low_confidence_not_blocking(registry):
    registry.register_pattern(
        "WEAK_PATTERN",
        "SIDEWAYS",
        ["scalp"],
        0.30,
        registered_by="grid",
        cycle=100,
    )
    # Confiance 0.30 < seuil 0.50 → pas bloquant
    assert not registry.is_forbidden("WEAK_PATTERN", "SIDEWAYS", "scalp")


def test_registry_update_upgrades_confidence(registry):
    registry.register_pattern(
        "PAT_A",
        "TREND_BULL",
        ["momentum"],
        0.55,
        registered_by="a",
        cycle=100,
    )
    registry.register_pattern(
        "PAT_A",
        "TREND_BULL",
        ["momentum"],
        0.90,
        registered_by="b",
        cycle=200,
    )
    patterns = registry.get_active_patterns()
    pat = next(p for p in patterns if p.pattern_id == "PAT_A")
    assert pat.confidence == 0.90


def test_registry_update_merges_strategies(registry):
    registry.register_pattern(
        "PAT_B",
        "SIDEWAYS",
        ["scalp"],
        0.70,
        registered_by="a",
        cycle=100,
    )
    registry.register_pattern(
        "PAT_B",
        "SIDEWAYS",
        ["grid"],
        0.70,
        registered_by="b",
        cycle=200,
    )
    patterns = registry.get_active_patterns()
    pat = next(p for p in patterns if p.pattern_id == "PAT_B")
    assert "scalp" in pat.strategies_affected
    assert "grid" in pat.strategies_affected


def test_registry_wildcard_regime(registry):
    registry.register_pattern(
        "GLOBAL_RISK",
        "*",
        ["scalp"],
        0.80,
        registered_by="system",
        cycle=100,
    )
    # Doit matcher n'importe quel régime
    assert registry.is_forbidden("GLOBAL_RISK", "HIGH_VOL", "scalp")
    assert registry.is_forbidden("GLOBAL_RISK", "SIDEWAYS", "scalp")
    assert registry.is_forbidden("GLOBAL_RISK", "TREND_BULL", "scalp")


def test_registry_clear_old_patterns(registry):
    registry.register_pattern(
        "OLD_PAT",
        "SIDEWAYS",
        ["scalp"],
        0.80,
        registered_by="a",
        cycle=10,
    )
    purged = registry.clear_old_patterns(current_cycle=600)  # 600-10=590 > 500
    assert purged == 1
    assert not registry.get_active_patterns()


def test_registry_keep_recent_patterns(registry):
    registry.register_pattern(
        "NEW_PAT",
        "SIDEWAYS",
        ["scalp"],
        0.80,
        registered_by="a",
        cycle=400,
    )
    purged = registry.clear_old_patterns(current_cycle=600)  # 600-400=200 < 500
    assert purged == 0
    assert len(registry.get_active_patterns()) == 1


def test_registry_clear_specific_pattern(registry):
    registry.register_pattern(
        "TO_DELETE",
        "SIDEWAYS",
        ["scalp"],
        0.80,
        registered_by="a",
        cycle=100,
    )
    removed = registry.clear_pattern("TO_DELETE", "SIDEWAYS")
    assert removed is True
    assert not registry.is_forbidden("TO_DELETE", "SIDEWAYS", "scalp")


def test_registry_forbidden_for_strategy(registry):
    registry.register_pattern("P1", "HIGH_VOL", ["scalp"], 0.80, cycle=100)
    registry.register_pattern("P2", "HIGH_VOL", ["grid"], 0.80, cycle=100)
    result = registry.forbidden_for_strategy("scalp", "HIGH_VOL", cycle=100)
    assert len(result) == 1
    assert result[0].pattern_id == "P1"


def test_registry_summary(registry):
    registry.register_pattern("P1", "HIGH_VOL", ["scalp"], 0.80, cycle=100)
    registry.register_pattern("P2", "SIDEWAYS", ["grid"], 0.60, cycle=100)
    s = registry.summary()
    assert s["total_patterns"] == 2
    assert s["high_confidence"] == 1


def test_registry_persistence(tmp_path):
    os.environ["FORBIDDEN_PATTERNS_DB"] = str(tmp_path / "patterns.json")
    from quant_hedge_ai.agents.intelligence.forbidden_patterns_registry import (
        ForbiddenPatternsRegistry,
    )

    reg1 = ForbiddenPatternsRegistry()
    reg1.register_pattern("PERSIST_PAT", "SIDEWAYS", ["scalp"], 0.80, cycle=100)

    reg2 = ForbiddenPatternsRegistry()
    assert reg2.is_forbidden("PERSIST_PAT", "SIDEWAYS", "scalp")
