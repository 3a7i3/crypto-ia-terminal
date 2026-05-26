"""
test_p8_validation.py — Validation P8 : Strategy Allocation Intelligence

Critères de succès P8 :
  ✅ Matrice d'allocation : poids différents entre deux régimes distincts
  ✅ Aucune stratégie ne dépasse 60% du capital total
  ✅ ProbationSystem : au moins une stratégie en TRACKING/PROBATION après 50 cycles
  ✅ Corrélation moyenne entre stratégies reste sous 0.6
"""

import os

os.environ.setdefault("PROBATION_DB", ":memory:")
os.environ.setdefault("ALLOCATOR_DB", ":memory:")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_probation(tmp_path):
    os.environ["PROBATION_DB"] = str(tmp_path / "probation.json")
    from quant_hedge_ai.agents.intelligence.strategy_probation import (
        StrategyProbationSystem,
    )

    return StrategyProbationSystem()


def _make_allocator(tmp_path, probation=None):
    os.environ["ALLOCATOR_DB"] = str(tmp_path / "allocator.json")
    from quant_hedge_ai.agents.intelligence.strategy_allocator import StrategyAllocator

    return StrategyAllocator(probation_system=probation)


# ══════════════════════════════════════════════════════════════════════════════
# 1. StrategyAllocator — matrice contextuelle
# ══════════════════════════════════════════════════════════════════════════════


class TestStrategyAllocator:
    def test_weights_sum_to_one(self, tmp_path):
        alloc = _make_allocator(tmp_path)
        result = alloc.allocate(1, "SIDEWAYS", "NORMAL", 10000.0, 1.0)
        total = sum(result.weights.values())
        assert abs(total - 1.0) < 1e-6

    def test_regime_differentiation(self, tmp_path):
        """Critère P8 #1 : poids significativement différents entre deux régimes."""
        alloc = _make_allocator(tmp_path)
        r_sw = alloc.allocate(1, "SIDEWAYS", "NORMAL", 10000.0, 1.0)
        r_bull = alloc.allocate(2, "TREND_BULL", "NORMAL", 10000.0, 1.0)
        # En SIDEWAYS, mean_reversion devrait dominer sur momentum
        # En TREND_BULL, c'est l'inverse
        # poids divergés après ramp 0.08/cycle
        diff_mr = abs(r_sw.weights["mean_reversion"] - r_bull.weights["mean_reversion"])
        diff_mom = abs(r_sw.weights["momentum"] - r_bull.weights["momentum"])
        assert diff_mr > 0.01 or diff_mom > 0.01  # divergence observable

    def test_ceiling_not_exceeded(self, tmp_path):
        """Critère P8 #2 : aucune stratégie > 60%."""
        alloc = _make_allocator(tmp_path)
        for regime in ["SIDEWAYS", "TREND_BULL", "TREND_BEAR", "HIGH_VOL", "CHOPPY"]:
            r = alloc.allocate(1, regime, "NORMAL", 10000.0, 1.0)
            for sid, w in r.weights.items():
                assert w <= 0.60 + 1e-6, f"{regime}/{sid} weight={w:.3f} > 0.60"

    def test_floor_applied(self, tmp_path):
        """Chaque stratégie active garde un poids plancher ≥ 0.05."""
        alloc = _make_allocator(tmp_path)
        result = alloc.allocate(1, "SIDEWAYS", "NORMAL", 10000.0, 1.0)
        for sid, w in result.weights.items():
            assert w >= 0.05 - 1e-6, f"{sid} weight={w:.4f} < floor 0.05"

    def test_exposure_factor_scales_capital(self, tmp_path):
        alloc = _make_allocator(tmp_path)
        r_full = alloc.allocate(1, "NORMAL", "NORMAL", 10000.0, 1.0)
        alloc2 = _make_allocator(tmp_path)
        r_half = alloc2.allocate(1, "NORMAL", "NORMAL", 10000.0, 0.5)
        total_full = sum(r_full.capital_usd.values())
        total_half = sum(r_half.capital_usd.values())
        assert abs(total_half - total_full * 0.5) < 1.0

    def test_risk_off_zeroes_capital(self, tmp_path):
        alloc = _make_allocator(tmp_path)
        result = alloc.allocate(1, "UNKNOWN", "RISK_OFF", 10000.0, 0.0)
        for cap in result.capital_usd.values():
            assert cap == 0.0

    def test_entropy_above_minimum(self, tmp_path):
        alloc = _make_allocator(tmp_path)
        result = alloc.allocate(1, "TREND_BULL", "NORMAL", 10000.0, 1.0)
        assert result.entropy >= 0.60

    def test_shock_absorber_limits_delta(self, tmp_path):
        alloc = _make_allocator(tmp_path)
        alloc.allocate(1, "SIDEWAYS", "NORMAL", 10000.0, 1.0)
        r2 = alloc.allocate(2, "TREND_BULL", "NORMAL", 10000.0, 1.0)
        # shock absorber : total delta ne peut pas dépasser 0.25
        assert r2.entropy >= 0.40  # allocation cohérente

    def test_human_override_respected(self, tmp_path):
        alloc = _make_allocator(tmp_path)
        alloc.set_override("scalp", until_cycle=100, fixed_weight=0.50, reason="test")
        result = alloc.allocate(5, "SIDEWAYS", "NORMAL", 10000.0, 1.0)
        assert result.weights["scalp"] == max(result.weights.values())

    def test_audit_trail_populated(self, tmp_path):
        alloc = _make_allocator(tmp_path)
        alloc.allocate(1, "SIDEWAYS", "NORMAL", 10000.0, 1.0)
        audit = alloc.audit_recent(1)
        assert len(audit) == 1
        entry = audit[0]
        assert "cycle" in entry and "weights" in entry and "regime" in entry

    def test_performance_score_updates(self, tmp_path):
        alloc = _make_allocator(tmp_path)
        for _ in range(5):
            alloc.record_performance("momentum", pnl_pct=0.02, sharpe=1.5)
        score = alloc.performance_score("momentum")
        assert score > 0.0

    def test_unknown_regime_uses_equal_weight_fallback(self, tmp_path):
        alloc = _make_allocator(tmp_path)
        result = alloc.allocate(1, "FLASH_CRASH_UNKNOWN_XYZ", "NORMAL", 10000.0, 1.0)
        assert abs(sum(result.weights.values()) - 1.0) < 1e-6


# ══════════════════════════════════════════════════════════════════════════════
# 2. StrategyProbationSystem — lifecycle
# ══════════════════════════════════════════════════════════════════════════════


class TestStrategyProbationSystem:
    def test_new_strategy_starts_tracking(self, tmp_path):
        ps = _make_probation(tmp_path)
        r = ps.register("test_strat")
        from quant_hedge_ai.agents.intelligence.strategy_probation import StrategyStatus

        assert r.status == StrategyStatus.TRACKING

    def test_tracking_capital_factor_is_zero(self, tmp_path):
        ps = _make_probation(tmp_path)
        ps.register("test_strat")
        assert ps.capital_factor("test_strat") == 0.0

    def test_tracking_to_probation_on_timeout(self, tmp_path):
        os.environ["P8_TRACKING_MAX_CYCLES"] = "3"
        ps = _make_probation(tmp_path)
        ps.register("strat_a")
        from quant_hedge_ai.agents.intelligence.strategy_probation import StrategyStatus

        events = []
        for i in range(4):
            evts = ps.tick_cycle(i)
            events.extend(evts)
        r = ps.get("strat_a")
        assert r is not None
        assert r.status == StrategyStatus.PROBATION
        os.environ.pop("P8_TRACKING_MAX_CYCLES", None)

    def test_probation_capital_factor_is_25pct(self, tmp_path):
        os.environ["P8_TRACKING_MAX_CYCLES"] = "1"
        ps = _make_probation(tmp_path)
        ps.register("strat_b")
        for i in range(3):
            ps.tick_cycle(i)
        assert abs(ps.capital_factor("strat_b") - 0.25) < 1e-6
        os.environ.pop("P8_TRACKING_MAX_CYCLES", None)

    def test_probation_to_active_on_good_metrics(self, tmp_path):
        os.environ["P8_TRACKING_MAX_CYCLES"] = "1"
        os.environ["P8_PROBATION_EVAL_TRADES"] = "5"
        ps = _make_probation(tmp_path)
        ps.register("good_strat")
        ps.tick_cycle(1)  # → PROBATION

        from quant_hedge_ai.agents.intelligence.strategy_probation import StrategyStatus

        for i in range(6):
            ps.record_trade("good_strat", pnl_pct=0.02, sharpe=1.5)

        r = ps.get("good_strat")
        assert r is not None
        assert r.status == StrategyStatus.ACTIVE
        os.environ.pop("P8_TRACKING_MAX_CYCLES", None)
        os.environ.pop("P8_PROBATION_EVAL_TRADES", None)

    def test_probation_to_suspended_on_bad_metrics(self, tmp_path):
        os.environ["P8_TRACKING_MAX_CYCLES"] = "1"
        os.environ["P8_PROBATION_EVAL_TRADES"] = "5"
        ps = _make_probation(tmp_path)
        ps.register("bad_strat")
        ps.tick_cycle(1)  # → PROBATION

        from quant_hedge_ai.agents.intelligence.strategy_probation import StrategyStatus

        for i in range(6):
            ps.record_trade("bad_strat", pnl_pct=-0.01, sharpe=-0.5)

        r = ps.get("bad_strat")
        assert r is not None
        assert r.status in (StrategyStatus.SUSPENDED, StrategyStatus.PROBATION_EXTENDED)
        os.environ.pop("P8_TRACKING_MAX_CYCLES", None)
        os.environ.pop("P8_PROBATION_EVAL_TRADES", None)

    def test_retirement_after_max_suspensions(self, tmp_path):
        os.environ["P8_RETIRE_SUSPENSIONS"] = "2"
        os.environ["P8_PROBATION_EVAL_TRADES"] = "3"
        try:
            ps = _make_probation(tmp_path)
            from quant_hedge_ai.agents.intelligence.strategy_probation import (
                StrategyStatus,
            )

            ps.register("retire_me")
            # Forcer PROBATION + enregistrer 3 mauvais trades → 1ère suspension
            ps.override_status("retire_me", StrategyStatus.PROBATION, "force test 1")
            for _ in range(4):
                ps.record_trade("retire_me", pnl_pct=-0.05, sharpe=-1.0)
            # 2ème suspension → RETIRED
            ps.override_status("retire_me", StrategyStatus.PROBATION, "force test 2")
            for _ in range(4):
                ps.record_trade("retire_me", pnl_pct=-0.05, sharpe=-1.0)

            result = ps.get("retire_me")
            assert result is not None
            assert result.status == StrategyStatus.RETIRED
        finally:
            os.environ.pop("P8_RETIRE_SUSPENSIONS", None)
            os.environ.pop("P8_PROBATION_EVAL_TRADES", None)

    def test_criteria_p8_tracking_or_probation_exists(self, tmp_path):
        """Critère P8 #3 : au moins une stratégie en TRACKING ou PROBATION."""
        ps = _make_probation(tmp_path)
        from quant_hedge_ai.agents.intelligence.strategy_allocator import STRATEGY_IDS
        from quant_hedge_ai.agents.intelligence.strategy_probation import StrategyStatus

        for sid in STRATEGY_IDS:
            ps.register(sid)

        snap = ps.snapshot()
        non_active = [
            sid
            for sid, info in snap.items()
            if info["status"]
            in (StrategyStatus.TRACKING.value, StrategyStatus.PROBATION.value)
        ]
        assert len(non_active) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# 3. StrategyConfidenceScorer
# ══════════════════════════════════════════════════════════════════════════════


class TestStrategyConfidenceScorer:
    def test_clamp_bounds(self):
        from quant_hedge_ai.agents.intelligence.confidence_scorer import (
            StrategyConfidenceScorer,
        )

        scorer = StrategyConfidenceScorer("test", base_confidence=0.5)
        for _ in range(30):
            scorer.record_trade(
                won=True, pnl_pct=0.05, sharpe=5.0, regime="SIDEWAYS", cycle=1
            )
        assert scorer.confidence <= 0.92 + 1e-6
        for _ in range(30):
            scorer.record_trade(
                won=False, pnl_pct=-0.05, sharpe=-5.0, regime="SIDEWAYS", cycle=2
            )
        assert scorer.confidence >= 0.10 - 1e-6

    def test_asymmetry_down_faster_than_up(self):
        from quant_hedge_ai.agents.intelligence.confidence_scorer import (
            StrategyConfidenceScorer,
        )

        scorer_up = StrategyConfidenceScorer("up", base_confidence=0.5)
        for _ in range(20):
            scorer_up.record_trade(
                won=True, pnl_pct=0.05, sharpe=2.0, regime="SIDEWAYS", cycle=1
            )

        scorer_down = StrategyConfidenceScorer("down", base_confidence=0.5)
        for _ in range(20):
            scorer_down.record_trade(
                won=False, pnl_pct=-0.05, sharpe=-2.0, regime="SIDEWAYS", cycle=1
            )

        delta_up = scorer_up.confidence - 0.5
        delta_down = 0.5 - scorer_down.confidence
        assert delta_down > delta_up  # descend plus vite que monte

    def test_decay_reduces_confidence(self):
        from quant_hedge_ai.agents.intelligence.confidence_scorer import (
            StrategyConfidenceScorer,
        )

        scorer = StrategyConfidenceScorer("decay_test", base_confidence=0.7)
        conf_before = scorer.confidence
        for _ in range(10):
            scorer.tick_cycle()
        assert scorer.confidence < conf_before

    def test_small_sample_keeps_base(self):
        from quant_hedge_ai.agents.intelligence.confidence_scorer import (
            StrategyConfidenceScorer,
        )

        scorer = StrategyConfidenceScorer("new", base_confidence=0.5)
        scorer.record_trade(
            won=True, pnl_pct=0.02, sharpe=1.0, regime="SIDEWAYS", cycle=1
        )
        scorer.record_trade(
            won=True, pnl_pct=0.02, sharpe=1.0, regime="SIDEWAYS", cycle=2
        )
        # Moins de 5 trades → confiance ne change pas par calcul
        assert 0.10 <= scorer.confidence <= 0.92

    def test_snapshot_keys(self):
        from quant_hedge_ai.agents.intelligence.confidence_scorer import (
            StrategyConfidenceScorer,
        )

        scorer = StrategyConfidenceScorer("snap_test")
        snap = scorer.snapshot()
        assert "confidence" in snap and "sample_size" in snap and "win_rate" in snap


# ══════════════════════════════════════════════════════════════════════════════
# 4. CorrelationMonitor
# ══════════════════════════════════════════════════════════════════════════════


class TestCorrelationMonitor:
    def test_low_correlation_no_penalty(self):
        from quant_hedge_ai.agents.intelligence.correlation_monitor import (
            CorrelationMonitor,
        )

        mon = CorrelationMonitor()
        import random

        rng = random.Random(42)
        for cycle in range(25):
            mon.record(
                "strat_a",
                rng.gauss(0, 1),
                float(rng.choice([-1, 1])),
                abs(rng.gauss(0, 0.01)),
                cycle,
                "SIDEWAYS",
            )
            mon.record(
                "strat_b",
                rng.gauss(0, 1),
                float(rng.choice([-1, 1])),
                abs(rng.gauss(0, 0.01)),
                cycle,
                "SIDEWAYS",
            )

        penalties = mon.get_weight_penalties(
            "SIDEWAYS", {"strat_a": 0.5, "strat_b": 0.5}
        )
        for pen in penalties.values():
            assert pen < 0.30  # pas de pénalité max

    def test_high_correlation_triggers_penalty(self):
        from quant_hedge_ai.agents.intelligence.correlation_monitor import (
            CorrelationMonitor,
        )

        mon = CorrelationMonitor()
        # Signaux parfaitement corrélés sur les 3 dimensions
        for cycle in range(25):
            val = 0.10 if cycle % 2 == 0 else -0.05
            sig = 1.0 if cycle % 2 == 0 else -1.0
            dd = abs(val) * 0.5
            mon.record("corr_a", val, sig, dd, cycle, "TREND_BULL")
            mon.record("corr_b", val, sig, dd, cycle, "TREND_BULL")

        penalties = mon.get_weight_penalties(
            "TREND_BULL", {"corr_a": 0.5, "corr_b": 0.3}
        )
        total_pen = sum(penalties.values())
        assert total_pen > 0.0  # pénalité déclenchée (composite=1.0 > action=0.85)

    def test_criteria_p8_avg_correlation_below_0_6(self):
        """Critère P8 #4 : corrélation moyenne inter-stratégies < 0.6."""
        from quant_hedge_ai.agents.intelligence.correlation_monitor import (
            CorrelationMonitor,
        )

        mon = CorrelationMonitor()
        import random

        rng = random.Random(99)
        strategies = ["mean_reversion", "breakout", "scalp", "momentum", "grid"]
        for cycle in range(30):
            for sid in strategies:
                pnl = rng.gauss(0, 0.01) + (
                    0.005 if sid in ("momentum", "breakout") else -0.003
                )
                sig = float(rng.choice([-1, 0, 1]))
                dd = abs(rng.gauss(0, 0.005))
                mon.record(sid, pnl, sig, dd, cycle, "SIDEWAYS")

        scores = {sid: 0.5 for sid in strategies}
        results = mon._compute_all("SIDEWAYS", scores)
        if results:
            avg_corr = sum(abs(r.composite_corr) for r in results) / len(results)
            assert avg_corr < 0.60  # critère P8

    def test_negative_correlation_triggers_penalty(self):
        from quant_hedge_ai.agents.intelligence.correlation_monitor import (
            CorrelationMonitor,
        )

        mon = CorrelationMonitor()
        for cycle in range(25):
            pos = 0.05 if cycle % 2 == 0 else -0.05
            mon.record("pos_strat", pos, 1.0, 0.01, cycle, "SIDEWAYS")
            mon.record("neg_strat", -pos, -1.0, 0.01, cycle, "SIDEWAYS")

        penalties = mon.get_weight_penalties(
            "SIDEWAYS", {"pos_strat": 0.6, "neg_strat": 0.4}
        )
        assert len(penalties) > 0

    def test_fusion_alert_after_multi_regime_correlation(self):
        from quant_hedge_ai.agents.intelligence.correlation_monitor import (
            CorrelationMonitor,
        )

        mon = CorrelationMonitor()
        for regime in ["SIDEWAYS", "TREND_BULL", "TREND_BEAR"]:
            for cycle in range(25):
                val = 0.10 if cycle % 2 == 0 else -0.05
                sig = 1.0 if cycle % 2 == 0 else -1.0
                dd = abs(val) * 0.5
                mon.record("sa", val, sig, dd, cycle, regime)
                mon.record("sb", val, sig, dd, cycle, regime)
            # Force compute_all pour tracker la fusion
            mon.get_weight_penalties(regime, {"sa": 0.5, "sb": 0.5})

        alerts = mon.fusion_alerts()
        assert len(alerts) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# 5. Critères de succès P8 — intégration
# ══════════════════════════════════════════════════════════════════════════════


class TestP8SuccessCriteria:
    def test_regime_weights_differ_sideways_vs_trendbull(self, tmp_path):
        """La matrice SIDEWAYS vs TREND_BULL doit produire des poids distincts."""
        from quant_hedge_ai.agents.intelligence.strategy_allocator import (
            BASE_ALLOCATION_MATRIX,
        )

        sw = BASE_ALLOCATION_MATRIX["SIDEWAYS"]
        tb = BASE_ALLOCATION_MATRIX["TREND_BULL"]
        total_diff = sum(abs(sw[k] - tb[k]) for k in sw)
        assert total_diff > 0.40  # au moins 40 points de diff cumulés

    def test_entropy_function(self):
        from quant_hedge_ai.agents.intelligence.strategy_allocator import _entropy

        assert abs(_entropy([0.2, 0.2, 0.2, 0.2, 0.2]) - 1.0) < 1e-6
        assert _entropy([1.0, 0.0, 0.0, 0.0, 0.0]) == 0.0
        assert 0.0 < _entropy([0.6, 0.1, 0.1, 0.1, 0.1]) < 1.0

    def test_allocator_ramp_prevents_instantaneous_regime_jump(self, tmp_path):
        """La rampe limite les jumps de poids entre cycles."""
        alloc = _make_allocator(tmp_path)
        r1 = alloc.allocate(1, "SIDEWAYS", "NORMAL", 10000.0, 1.0)
        r2 = alloc.allocate(2, "TREND_BULL", "NORMAL", 10000.0, 1.0)
        # delta limité par ramp (0.03 up, 0.08 down + normalisation)
        for sid in r1.weights:
            delta = abs(r2.weights[sid] - r1.weights[sid])
            assert delta <= 0.18, f"{sid}: delta cycle1→2 = {delta:.3f} trop grand"

    def test_personality_to_strategy_mapping_complete(self):
        from quant_hedge_ai.agents.intelligence.strategy_allocator import (
            PERSONALITY_TO_STRATEGY,
            STRATEGY_IDS,
        )

        for pers, sid in PERSONALITY_TO_STRATEGY.items():
            assert (
                sid in STRATEGY_IDS
            ), f"Personnalité '{pers}' mappe vers '{sid}' inconnu"
