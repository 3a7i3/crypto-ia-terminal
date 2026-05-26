"""
test_p9_validation.py — Validation P9 Meta Governance

Critères de succès :
  1. Dérive simulée détectée (threshold poussé à 80 pendant 30 cycles)
  2. Suspension activée sur anomalie (TRADE_SPIKE, SCORE_DROP, etc.)
  3. Sharpe glissant accessible et cohérent
  4. 0 faux positif BDD sur 100 cycles en régime stable
"""

from quant_hedge_ai.agents.intelligence.behavioral_drift_detector import (
    BehavioralDriftDetector,
)
from quant_hedge_ai.agents.intelligence.performance_supervisor import (
    PerformanceSupervisor,
)
from quant_hedge_ai.agents.intelligence.self_monitoring_loop import SelfMonitoringLoop
from quant_hedge_ai.agents.risk.anomaly_governance import AnomalyGovernance, AnomalyType
from quant_hedge_ai.agents.risk.portfolio_intelligence import PortfolioIntelligence
from quant_hedge_ai.agents.risk.system_health_monitor import (
    ComponentStatus,
    SystemHealthMonitor,
)

# ── P9.1 SystemHealthMonitor ──────────────────────────────────────────────────


class TestSystemHealthMonitor:
    def test_initial_green(self):
        hm = SystemHealthMonitor()
        hm.record("comp_a", latency_ms=10.0)
        assert hm.get_status("comp_a").status == ComponentStatus.GREEN

    def test_yellow_on_latency(self):
        hm = SystemHealthMonitor()
        hm.record("comp_a", latency_ms=600.0)
        assert hm.get_status("comp_a").status == ComponentStatus.YELLOW

    def test_red_on_critical_latency(self):
        hm = SystemHealthMonitor()
        hm.record("comp_a", latency_ms=2500.0)
        assert hm.get_status("comp_a").status == ComponentStatus.RED

    def test_red_on_critical_cb(self):
        hm = SystemHealthMonitor()
        hm.record("comp_a", cb_state="DEGRADED")
        assert hm.get_status("comp_a").status == ComponentStatus.RED

    def test_yellow_escalation_to_red(self, monkeypatch):
        monkeypatch.setenv("P9_YELLOW_ESCALATION_CYCLES", "3")
        hm = SystemHealthMonitor()
        hm.record("comp_a", latency_ms=600.0)
        for _ in range(3):
            hm.tick_cycle()
        assert hm.get_status("comp_a").status == ComponentStatus.RED

    def test_overall_health_worst_wins(self):
        hm = SystemHealthMonitor()
        hm.record("a", latency_ms=10.0)
        hm.record("b", latency_ms=2500.0)
        assert hm.overall_health() == ComponentStatus.RED

    def test_error_rate_tracking(self):
        hm = SystemHealthMonitor()
        for _ in range(10):
            hm.record("comp_a", latency_ms=10.0)
        for _ in range(5):
            hm.record("comp_a", latency_ms=10.0, error=True)
        c = hm.get_status("comp_a")
        assert c.error_rate > 0.20
        assert c.status == ComponentStatus.RED

    def test_summary_structure(self):
        hm = SystemHealthMonitor()
        hm.record("a", latency_ms=50.0)
        s = hm.summary()
        assert "overall" in s
        assert "components" in s

    def test_recent_events(self):
        hm = SystemHealthMonitor()
        hm.record("a", latency_ms=10.0)
        hm.record("a", latency_ms=600.0)
        events = hm.recent_events(5)
        assert len(events) >= 1

    def test_unknown_component_returns_none(self):
        hm = SystemHealthMonitor()
        assert hm.get_status("nonexistent") is None


# ── P9.2 BehavioralDriftDetector ─────────────────────────────────────────────


class TestBehavioralDriftDetector:
    def _make_stable_detector(self, n_stable: int = 60) -> BehavioralDriftDetector:
        bdd = BehavioralDriftDetector()
        for i in range(n_stable):
            bdd.record(
                cycle=i,
                threshold_used=70.0,
                score=65.0,
                signal_generated=True,
                refused=False,
            )
        return bdd

    def test_no_drift_in_stable_regime(self):
        """Critère 4 : 0 faux positif sur 100 cycles stables."""
        bdd = BehavioralDriftDetector()
        alert_count = 0
        for i in range(100):
            bdd.record(
                cycle=i,
                threshold_used=70.0,
                score=65.0,
                signal_generated=True,
                refused=False,
            )
            report = bdd.check(regime="sideways")
            if report.drifting:
                alert_count += 1
        assert alert_count == 0, f"Faux positifs: {alert_count}"

    def test_drift_detected_on_threshold_push(self):
        """Critère 1 : threshold poussé à 80 pendant 30 cycles → détecté."""
        bdd = BehavioralDriftDetector()
        for i in range(50):
            bdd.record(
                cycle=i,
                threshold_used=70.0,
                score=65.0,
                signal_generated=True,
                refused=False,
            )
        detected = False
        for i in range(50, 80):
            bdd.record(
                cycle=i,
                threshold_used=80.0,
                score=65.0,
                signal_generated=True,
                refused=False,
            )
            report = bdd.check(regime="sideways")
            if report.drifting:
                detected = True
                break
        assert detected, "Dérive threshold non détectée"

    def test_meta_confidence_grows(self):
        bdd = BehavioralDriftDetector()
        c0 = bdd._meta_confidence()
        for i in range(25):
            bdd.record(
                cycle=i,
                threshold_used=70.0,
                score=65.0,
                signal_generated=True,
                refused=False,
            )
        assert bdd._meta_confidence() > c0

    def test_meta_confidence_max_is_one(self):
        bdd = BehavioralDriftDetector()
        for i in range(60):
            bdd.record(
                cycle=i,
                threshold_used=70.0,
                score=65.0,
                signal_generated=True,
                refused=False,
            )
        assert bdd._meta_confidence() == 1.0

    def test_alert_frequency_property(self):
        bdd = self._make_stable_detector()
        # force some alerts by injecting drift
        for i in range(60, 80):
            bdd.record(
                cycle=i,
                threshold_used=90.0,
                score=10.0,
                signal_generated=False,
                refused=True,
            )
            bdd.check()
        assert bdd.alert_frequency >= 0.0

    def test_cooldown_prevents_burst(self):
        bdd = BehavioralDriftDetector()
        for i in range(50):
            bdd.record(
                cycle=i,
                threshold_used=70.0,
                score=65.0,
                signal_generated=True,
                refused=False,
            )
        # inject drift
        for i in range(50, 65):
            bdd.record(
                cycle=i,
                threshold_used=90.0,
                score=65.0,
                signal_generated=True,
                refused=False,
            )
        alerts = sum(1 for i in range(50, 65) if bdd.check().drifting)
        assert alerts <= 3, "Cooldown ne limite pas les alertes"

    def test_loose_regime_more_tolerant(self):
        bdd = BehavioralDriftDetector()
        for i in range(50):
            bdd.record(
                cycle=i,
                threshold_used=70.0,
                score=65.0,
                signal_generated=True,
                refused=False,
            )
        for i in range(50, 60):
            bdd.record(
                cycle=i,
                threshold_used=74.0,
                score=65.0,
                signal_generated=True,
                refused=False,
            )
        report_tight = bdd.check(regime="sideways")
        report_loose = bdd.check(regime="HIGH_VOL")
        # loose regime should be equal or less drifting
        tight_sigma = max((m.sigma_distance for m in report_tight.metrics), default=0)
        loose_sigma = max((m.sigma_distance for m in report_loose.metrics), default=0)
        assert tight_sigma >= loose_sigma or not report_tight.drifting

    def test_snapshot_structure(self):
        bdd = BehavioralDriftDetector()
        snap = bdd.snapshot()
        assert "cycle_count" in snap
        assert "alert_count" in snap


# ── P9.3 SelfMonitoringLoop ────────────────────────────────────────────────────


class TestSelfMonitoringLoop:
    def test_nominal_score_is_high(self):
        sml = SelfMonitoringLoop()
        snap = sml.tick(
            cycle=1, health_monitor=None, drift_detector=None, rg_state="NORMAL"
        )
        assert snap.meta_health_score >= 0.9

    def test_level2_alert_on_low_score(self, monkeypatch):
        monkeypatch.setenv("P9_META_HEALTH_ALERT", "0.70")
        hm = SystemHealthMonitor()
        # All RED → health_score = 0.0 → meta < 0.70
        hm.record("a", latency_ms=2500.0)
        hm.record("b", latency_ms=2500.0)
        sml = SelfMonitoringLoop()
        snap = sml.tick(cycle=1, health_monitor=hm, drift_detector=None)
        assert snap.level2_alert

    def test_level2_count_increments(self, monkeypatch):
        monkeypatch.setenv("P9_META_HEALTH_ALERT", "0.70")
        hm = SystemHealthMonitor()
        hm.record("a", latency_ms=2500.0)
        sml = SelfMonitoringLoop()
        sml.tick(cycle=1, health_monitor=hm, drift_detector=None)
        sml.tick(cycle=2, health_monitor=hm, drift_detector=None)
        assert sml.level2_alert_count == 2

    def test_transition_stability_degrades_on_bursts(self):
        sml = SelfMonitoringLoop()
        states = [
            "NORMAL",
            "DEFENSIVE",
            "NORMAL",
            "DEFENSIVE",
            "NORMAL",
            "DEFENSIVE",
            "NORMAL",
            "DEFENSIVE",
            "NORMAL",
            "DEFENSIVE",
        ]
        for i, s in enumerate(states):
            snap = sml.tick(
                cycle=i, health_monitor=None, drift_detector=None, rg_state=s
            )
        assert snap.transition_stability < 1.0

    def test_stable_state_has_full_transition_stability(self):
        sml = SelfMonitoringLoop()
        for i in range(10):
            snap = sml.tick(
                cycle=i, health_monitor=None, drift_detector=None, rg_state="NORMAL"
            )
        assert snap.transition_stability == 1.0

    def test_summary_has_meta_health(self):
        sml = SelfMonitoringLoop()
        sml.tick(cycle=1, health_monitor=None, drift_detector=None)
        s = sml.summary()
        assert "meta_health_score" in s
        assert "level2_alerts_total" in s

    def test_bdd_stability_false_triggers_level2(self, monkeypatch):
        monkeypatch.setenv("P9_BDD_UNSTABLE_CYCLES", "1")
        monkeypatch.setenv("P9_BDD_FREQ_THRESHOLD", "0.0")

        class FakeBDD:
            alert_frequency = 999.0

        sml = SelfMonitoringLoop()
        snap = sml.tick(cycle=1, health_monitor=None, drift_detector=FakeBDD())
        assert not snap.bdd_stable
        assert snap.level2_alert

    def test_health_monitor_integration(self):
        hm = SystemHealthMonitor()
        hm.record("a", latency_ms=50.0)
        sml = SelfMonitoringLoop()
        snap = sml.tick(
            cycle=1, health_monitor=hm, drift_detector=None, rg_state="NORMAL"
        )
        assert snap.component_health_score == 1.0

    def test_health_monitor_red_degrades_score(self):
        hm = SystemHealthMonitor()
        hm.record("a", latency_ms=2500.0)
        sml = SelfMonitoringLoop()
        snap = sml.tick(cycle=1, health_monitor=hm, drift_detector=None)
        assert snap.component_health_score < 1.0


# ── P9.4 AnomalyGovernance ────────────────────────────────────────────────────


class TestAnomalyGovernance:
    def test_trade_spike_detected(self):
        """Critère 2 : détection → suspension activée."""
        gov = AnomalyGovernance()
        for c in range(20):
            anomalies = gov.detect(
                cycle=c,
                trades_this_cycle=5,
                avg_score=70.0,
                threshold_used=70.0,
                rg_state="NORMAL",
            )
        # spike massif
        anomalies = gov.detect(
            cycle=20,
            trades_this_cycle=500,
            avg_score=70.0,
            threshold_used=70.0,
            rg_state="NORMAL",
        )
        types = [a.anomaly_type for a in anomalies]
        assert AnomalyType.TRADE_SPIKE in types

    def test_trade_spike_triggers_execution_suspension(self):
        gov = AnomalyGovernance()
        for c in range(20):
            gov.detect(
                cycle=c,
                trades_this_cycle=5,
                avg_score=70.0,
                threshold_used=70.0,
                rg_state="NORMAL",
            )
        gov.detect(
            cycle=20,
            trades_this_cycle=500,
            avg_score=70.0,
            threshold_used=70.0,
            rg_state="NORMAL",
        )
        assert gov.is_suspended("execution", cycle=21)

    def test_suspension_expires(self, monkeypatch):
        monkeypatch.setenv("P9_SUSPENSION_CYCLES", "5")
        gov = AnomalyGovernance()
        for c in range(20):
            gov.detect(
                cycle=c,
                trades_this_cycle=5,
                avg_score=70.0,
                threshold_used=70.0,
                rg_state="NORMAL",
            )
        gov.detect(
            cycle=20,
            trades_this_cycle=500,
            avg_score=70.0,
            threshold_used=70.0,
            rg_state="NORMAL",
        )
        assert gov.is_suspended("execution", cycle=25)
        assert not gov.is_suspended("execution", cycle=26)

    def test_score_drop_detected(self):
        gov = AnomalyGovernance()
        for c in range(10):
            gov.detect(
                cycle=c,
                trades_this_cycle=3,
                avg_score=70.0,
                threshold_used=70.0,
                rg_state="NORMAL",
            )
        # two consecutive low-score cycles → recent_mean drops 30+ pts
        gov.detect(
            cycle=10,
            trades_this_cycle=3,
            avg_score=40.0,
            threshold_used=70.0,
            rg_state="NORMAL",
        )
        anomalies = gov.detect(
            cycle=11,
            trades_this_cycle=3,
            avg_score=40.0,
            threshold_used=70.0,
            rg_state="NORMAL",
        )
        types = [a.anomaly_type for a in anomalies]
        assert AnomalyType.SCORE_DROP in types

    def test_rg_burst_detected(self):
        gov = AnomalyGovernance()
        states = ["NORMAL", "DEFENSIVE", "NORMAL", "DEFENSIVE", "NORMAL", "DEFENSIVE"]
        all_anomalies = []
        for c, s in enumerate(states):
            all_anomalies.extend(
                gov.detect(
                    cycle=c,
                    trades_this_cycle=3,
                    avg_score=70.0,
                    threshold_used=70.0,
                    rg_state=s,
                )
            )
        types = [a.anomaly_type for a in all_anomalies]
        assert AnomalyType.RG_BURST in types

    def test_cooldown_prevents_repeat(self, monkeypatch):
        monkeypatch.setenv("P9_GOV_COOLDOWN", "5")
        gov = AnomalyGovernance()
        for c in range(20):
            gov.detect(
                cycle=c,
                trades_this_cycle=5,
                avg_score=70.0,
                threshold_used=70.0,
                rg_state="NORMAL",
            )
        gov.detect(
            cycle=20,
            trades_this_cycle=500,
            avg_score=70.0,
            threshold_used=70.0,
            rg_state="NORMAL",
        )
        # same spike next cycle: should be in cooldown
        anomalies = gov.detect(
            cycle=21,
            trades_this_cycle=500,
            avg_score=70.0,
            threshold_used=70.0,
            rg_state="NORMAL",
        )
        types = [a.anomaly_type for a in anomalies]
        assert AnomalyType.TRADE_SPIKE not in types

    def test_governance_entropy_uniform(self):
        """Entropie ≈ 1.0 si tous types représentés également."""
        from quant_hedge_ai.agents.risk.anomaly_governance import AnomalyRecord

        gov = AnomalyGovernance()
        types = list(AnomalyType)
        for i, atype in enumerate(types):
            gov._crisis_memory.append(
                AnomalyRecord(
                    anomaly_id=f"test_{i}",
                    anomaly_type=atype,
                    cycle=i,
                    description="test",
                    snapshot={},
                    suspended_until_cycle=i + 10,
                )
            )
        entropy = gov.governance_entropy()
        assert abs(entropy - 1.0) < 1e-6

    def test_governance_entropy_single_type_is_zero(self):
        from quant_hedge_ai.agents.risk.anomaly_governance import AnomalyRecord

        gov = AnomalyGovernance()
        for i in range(4):
            gov._crisis_memory.append(
                AnomalyRecord(
                    anomaly_id=f"test_{i}",
                    anomaly_type=AnomalyType.TRADE_SPIKE,
                    cycle=i,
                    description="test",
                    snapshot={},
                    suspended_until_cycle=i + 10,
                )
            )
        assert gov.governance_entropy() == 0.0

    def test_crisis_memory_capped(self, monkeypatch):
        monkeypatch.setenv("P9_GOV_CRISIS_MEMORY", "5")
        monkeypatch.setenv("P9_GOV_COOLDOWN", "0")
        gov = AnomalyGovernance()
        for c in range(30):
            gov.detect(
                cycle=c,
                trades_this_cycle=5 if c % 2 == 0 else 500,
                avg_score=70.0,
                threshold_used=70.0,
                rg_state="NORMAL",
            )
        assert len(gov.crisis_memory()) <= 5

    def test_summary_structure(self):
        gov = AnomalyGovernance()
        s = gov.summary()
        assert "total_interventions" in s
        assert "governance_entropy" in s


# ── P9.5 PerformanceSupervisor ────────────────────────────────────────────────


class TestPerformanceSupervisor:
    def test_sharpe_returns_zero_with_no_data(self):
        ps = PerformanceSupervisor()
        assert ps.sharpe(20) == 0.0

    def test_sharpe_positive_on_winning_trades(self):
        """Critère 3 : Sharpe glissant accessible et cohérent."""
        import random

        rng = random.Random(42)
        ps = PerformanceSupervisor()
        for _ in range(30):
            ps.record_trade(pnl_pct=0.5 + rng.uniform(0, 0.3))
        assert ps.sharpe(20) > 0

    def test_sharpe_negative_on_losing_trades(self):
        import random

        rng = random.Random(42)
        ps = PerformanceSupervisor()
        for _ in range(30):
            ps.record_trade(pnl_pct=-0.5 - rng.uniform(0, 0.3))
        assert ps.sharpe(20) < 0

    def test_profit_factor_no_losses(self):
        ps = PerformanceSupervisor()
        for _ in range(10):
            ps.record_trade(pnl_pct=1.0)
        pf = ps.profit_factor()
        assert pf == float("inf") or pf > 10

    def test_profit_factor_balanced(self):
        ps = PerformanceSupervisor()
        for _ in range(10):
            ps.record_trade(pnl_pct=1.0)
            ps.record_trade(pnl_pct=-1.0)
        pf = ps.profit_factor()
        assert abs(pf - 1.0) < 0.01

    def test_max_drawdown_no_loss(self):
        ps = PerformanceSupervisor()
        for _ in range(10):
            ps.record_trade(pnl_pct=1.0)
        assert ps.max_drawdown() == 0.0

    def test_max_drawdown_with_loss(self):
        ps = PerformanceSupervisor()
        ps.record_trade(pnl_pct=10.0)
        ps.record_trade(pnl_pct=-5.0)
        ps.record_trade(pnl_pct=-5.0)
        dd = ps.max_drawdown()
        assert dd > 0.0

    def test_compare_shadow_zero_without_data(self):
        ps = PerformanceSupervisor()
        for _ in range(10):
            ps.record_trade(pnl_pct=1.0)  # no shadow
        assert ps.compare_shadow() == 0.0

    def test_compare_shadow_large_deviation(self):
        ps = PerformanceSupervisor()
        for _ in range(10):
            ps.record_trade(pnl_pct=0.1, shadow_pnl_pct=0.1)
        for _ in range(10):
            ps.record_trade(pnl_pct=5.0, shadow_pnl_pct=0.1)
        deviation = ps.compare_shadow()
        assert deviation > 0

    def test_snapshot_has_all_fields(self):
        import random

        rng = random.Random(7)
        ps = PerformanceSupervisor()
        for _ in range(30):
            ps.record_trade(
                pnl_pct=0.5 + rng.uniform(0, 0.4),
                shadow_pnl_pct=0.4 + rng.uniform(0, 0.2),
            )
        snap = ps.snapshot(cycle=30)
        assert snap.sharpe_20 != 0.0
        assert snap.profit_factor > 0

    def test_sharpe_warn_alert(self, monkeypatch):
        monkeypatch.setenv("P9_SHARPE_WARN", "999.0")
        ps = PerformanceSupervisor()
        for _ in range(25):
            ps.record_trade(pnl_pct=0.1)
        snap = ps.snapshot(cycle=1)
        assert any("Sharpe" in a for a in snap.alerts)

    def test_drawdown_warn_alert(self, monkeypatch):
        monkeypatch.setenv("P9_DD_WARN", "0.001")
        ps = PerformanceSupervisor()
        ps.record_trade(pnl_pct=5.0)
        for _ in range(10):
            ps.record_trade(pnl_pct=-1.0)
        snap = ps.snapshot(cycle=1)
        assert any("Drawdown" in a for a in snap.alerts)

    def test_summary_structure(self):
        ps = PerformanceSupervisor()
        s = ps.summary()
        assert "trade_count" in s
        assert "sharpe_20" in s


# ── P9.6 PortfolioIntelligence ────────────────────────────────────────────────


class TestPortfolioIntelligence:
    def test_empty_portfolio(self):
        pi = PortfolioIntelligence()
        assert pi.concentration_by_exchange() == {}
        assert pi.net_exposure() == 0.0

    def test_single_position(self):
        pi = PortfolioIntelligence()
        pi.record_position("BTC/USDT", "binance", "momentum", "long", 1000.0)
        assert pi.concentration_by_exchange() == {"binance": 1.0}

    def test_concentration_by_exchange(self):
        pi = PortfolioIntelligence()
        pi.record_position("BTC/USDT", "binance", "momentum", "long", 7000.0)
        pi.record_position("ETH/USDT", "bybit", "scalp", "long", 3000.0)
        conc = pi.concentration_by_exchange()
        assert abs(conc["binance"] - 0.70) < 0.01
        assert abs(conc["bybit"] - 0.30) < 0.01

    def test_concentration_by_strategy(self):
        pi = PortfolioIntelligence()
        pi.record_position("BTC/USDT", "binance", "momentum", "long", 6000.0)
        pi.record_position("ETH/USDT", "binance", "scalp", "long", 4000.0)
        conc = pi.concentration_by_strategy()
        assert abs(conc["momentum"] - 0.60) < 0.01

    def test_net_exposure_long_only(self):
        pi = PortfolioIntelligence()
        pi.record_position("BTC/USDT", "binance", "m", "long", 1000.0)
        assert pi.net_exposure() == 1.0

    def test_net_exposure_short_only(self):
        pi = PortfolioIntelligence()
        pi.record_position("BTC/USDT", "binance", "m", "short", 1000.0)
        assert pi.net_exposure() == -1.0

    def test_net_exposure_balanced(self):
        pi = PortfolioIntelligence()
        pi.record_position("BTC/USDT", "binance", "m", "long", 5000.0)
        pi.record_position("ETH/USDT", "binance", "m", "short", 5000.0)
        assert pi.net_exposure() == 0.0

    def test_close_position(self):
        pi = PortfolioIntelligence()
        pi.record_position("BTC/USDT", "binance", "m", "long", 1000.0)
        assert pi.close_position("BTC/USDT")
        assert pi.position_count() == 0

    def test_close_nonexistent_returns_false(self):
        pi = PortfolioIntelligence()
        assert not pi.close_position("NONEXISTENT")

    def test_warn_alert_on_high_concentration(self, monkeypatch):
        monkeypatch.setenv("P9_CONC_WARN", "0.50")
        monkeypatch.setenv("P9_CONC_CRIT", "0.90")
        pi = PortfolioIntelligence()
        pi.record_position("BTC/USDT", "binance", "m", "long", 7000.0)
        pi.record_position("ETH/USDT", "bybit", "m", "long", 3000.0)
        alerts = pi.get_alerts()
        assert any("binance" in a for a in alerts)

    def test_critical_alert_on_very_high_concentration(self, monkeypatch):
        monkeypatch.setenv("P9_CONC_WARN", "0.50")
        monkeypatch.setenv("P9_CONC_CRIT", "0.70")
        pi = PortfolioIntelligence()
        pi.record_position("BTC/USDT", "binance", "m", "long", 8000.0)
        pi.record_position("ETH/USDT", "bybit", "m", "long", 2000.0)
        alerts = pi.get_alerts()
        assert any("CRITICAL" in a and "binance" in a for a in alerts)

    def test_expo_warn_alert(self, monkeypatch):
        monkeypatch.setenv("P9_EXPO_WARN", "0.50")
        pi = PortfolioIntelligence()
        pi.record_position("BTC/USDT", "binance", "m", "long", 8000.0)
        pi.record_position("ETH/USDT", "binance", "m", "short", 2000.0)
        alerts = pi.get_alerts()
        assert any("exposition" in a for a in alerts)

    def test_update_position(self):
        pi = PortfolioIntelligence()
        pi.record_position("BTC/USDT", "binance", "m", "long", 1000.0)
        pi.record_position("BTC/USDT", "binance", "m", "short", 2000.0)
        assert pi.position_count() == 1
        assert pi.get_position("BTC/USDT").side == "short"

    def test_summary_structure(self):
        pi = PortfolioIntelligence()
        s = pi.summary()
        assert "position_count" in s
        assert "net_exposure" in s
        assert "by_exchange" in s
