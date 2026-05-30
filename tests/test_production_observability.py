"""
P12-B — Production Observability.

Tests de la couche métriques, score de santé et alerting.

B1 — MetricsCollector (latences, mémoire, trading, fiabilité)
B2 — HealthScore (score composite, niveaux, breakdown)
B3 — AlertEngine (règles par défaut, seuils, persistance JSONL)
B4 — Intégration (cycle complet : collect → score → alert)
"""

from __future__ import annotations

import json
import time

import pytest

from observability.alerting import AlertEngine, AlertRule, AlertSeverity
from observability.health_score import HealthLevel, HealthScore
from observability.metrics_collector import MetricsCollector, MetricsSnapshot

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_collector(capital: float = 10_000.0, **kwargs) -> MetricsCollector:
    return MetricsCollector(
        capital_fn=lambda: capital,
        equity_fn=lambda: capital,
        positions_fn=lambda: 0,
        initial_capital=capital,
        **kwargs,
    )


def _clean_snap(**overrides) -> MetricsSnapshot:
    """Snapshot sain par défaut, surchargeable."""
    snap = MetricsSnapshot(
        cycle_duration_ms=50.0,
        decision_latency_ms=10.0,
        execution_latency_ms=20.0,
        reconciliation_latency_ms=5.0,
        memory_mb=200.0,
        cpu_percent=15.0,
        capital=10_000.0,
        equity=10_000.0,
        drawdown_pct=0.0,
        open_positions=1,
        error_rate=0.0,
        exception_count=0,
        reconciliation_failures=0,
        boot_gate_cleared=True,
        health_score=100.0,
    )
    for k, v in overrides.items():
        setattr(snap, k, v)
    return snap


# ══════════════════════════════════════════════════════════════════════════════
# B1 — MetricsCollector
# ══════════════════════════════════════════════════════════════════════════════


class TestB1MetricsCollector:
    """Collecte correcte de toutes les métriques."""

    # ── Context managers ──────────────────────────────────────────────────────

    def test_measure_cycle_records_latency(self):
        """measure_cycle() enregistre une latence > 0."""
        collector = _make_collector()
        with collector.measure_cycle():
            time.sleep(0.05)  # 50ms — mesurable sur Windows (tick ~15ms)
        snap = collector.snapshot()
        assert snap.cycle_duration_ms > 0.0

    def test_measure_decision_records_latency(self):
        collector = _make_collector()
        with collector.measure_decision():
            time.sleep(0.05)
        snap = collector.snapshot()
        assert snap.decision_latency_ms > 0.0

    def test_measure_execution_records_latency(self):
        collector = _make_collector()
        with collector.measure_execution():
            time.sleep(0.05)
        snap = collector.snapshot()
        assert snap.execution_latency_ms > 0.0

    def test_measure_reconciliation_records_latency(self):
        collector = _make_collector()
        with collector.measure_reconciliation():
            time.sleep(0.05)
        snap = collector.snapshot()
        assert snap.reconciliation_latency_ms > 0.0

    def test_context_manager_records_even_on_exception(self):
        """La latence est capturée même si le bloc lève une exception."""
        collector = _make_collector()
        try:
            with collector.measure_cycle():
                time.sleep(0.05)
                raise ValueError("simulated")
        except ValueError:
            pass
        snap = collector.snapshot()
        assert snap.cycle_duration_ms > 0.0

    # ── Compteurs ─────────────────────────────────────────────────────────────

    def test_record_exception_increments_count(self):
        collector = _make_collector()
        collector.record_exception()
        collector.record_exception()
        snap = collector.snapshot()
        assert snap.exception_count == 2

    def test_record_reconciliation_failure_increments(self):
        collector = _make_collector()
        collector.record_reconciliation_failure()
        snap = collector.snapshot()
        assert snap.reconciliation_failures == 1

    def test_set_boot_gate_cleared(self):
        collector = _make_collector()
        assert not collector.snapshot().boot_gate_cleared

        collector.set_boot_gate_cleared(True)
        assert collector.snapshot().boot_gate_cleared

        collector.set_boot_gate_cleared(False)
        assert not collector.snapshot().boot_gate_cleared

    # ── Trading metrics ────────────────────────────────────────────────────────

    def test_capital_from_callback(self):
        capital_val = [10_000.0]
        collector = MetricsCollector(
            capital_fn=lambda: capital_val[0],
            initial_capital=10_000.0,
        )
        snap = collector.snapshot()
        assert snap.capital == 10_000.0

        capital_val[0] = 9_500.0
        snap2 = collector.snapshot()
        assert snap2.capital == 9_500.0

    def test_drawdown_computed_from_peak(self):
        """drawdown_pct = (peak - equity) / peak × 100."""
        equity_val = [10_000.0]
        collector = MetricsCollector(
            capital_fn=lambda: equity_val[0],
            equity_fn=lambda: equity_val[0],
            initial_capital=10_000.0,
        )
        # Pas de drawdown au départ
        snap = collector.snapshot()
        assert snap.drawdown_pct == 0.0

        # Baisse à 9000
        equity_val[0] = 9_000.0
        snap2 = collector.snapshot()
        assert abs(snap2.drawdown_pct - 10.0) < 0.01

    def test_drawdown_non_negative(self):
        """drawdown_pct ne peut pas être négatif."""
        equity_val = [10_000.0]
        collector = MetricsCollector(
            equity_fn=lambda: equity_val[0],
            initial_capital=10_000.0,
        )
        equity_val[0] = 11_000.0  # gain
        snap = collector.snapshot()
        assert snap.drawdown_pct >= 0.0

    def test_peak_equity_updated_on_new_high(self):
        """Le peak est mis à jour quand equity monte."""
        equity_val = [10_000.0]
        collector = MetricsCollector(
            equity_fn=lambda: equity_val[0],
            initial_capital=10_000.0,
        )
        equity_val[0] = 12_000.0
        collector.snapshot()  # peak → 12k

        equity_val[0] = 10_000.0
        snap = collector.snapshot()
        assert abs(snap.drawdown_pct - (2_000 / 12_000 * 100)) < 0.01

    # ── Error rate ─────────────────────────────────────────────────────────────

    def test_error_rate_increases_with_exceptions(self):
        collector = MetricsCollector(window_s=60.0)
        for _ in range(10):
            collector.record_exception()
        snap = collector.snapshot()
        # 10 erreurs / 1 min fenêtre = 10 err/min
        assert snap.error_rate > 0.0

    def test_error_rate_zero_without_exceptions(self):
        collector = _make_collector()
        snap = collector.snapshot()
        assert snap.error_rate == 0.0

    # ── Reset ─────────────────────────────────────────────────────────────────

    def test_reset_counters(self):
        collector = _make_collector()
        collector.record_exception()
        collector.record_reconciliation_failure()
        collector.reset_counters()
        snap = collector.snapshot()
        assert snap.exception_count == 0
        assert snap.reconciliation_failures == 0
        assert snap.error_rate == 0.0

    # ── JSONL flush ───────────────────────────────────────────────────────────

    def test_flush_to_jsonl_creates_file(self, tmp_path):
        collector = _make_collector()
        path = tmp_path / "metrics.jsonl"
        collector.flush_to_jsonl(path)
        assert path.exists()

    def test_flush_to_jsonl_valid_json(self, tmp_path):
        collector = _make_collector()
        path = tmp_path / "metrics.jsonl"
        collector.flush_to_jsonl(path)
        line = path.read_text().strip()
        data = json.loads(line)
        assert "ts" in data
        assert "capital" in data
        assert "drawdown_pct" in data

    def test_flush_to_jsonl_appends(self, tmp_path):
        collector = _make_collector()
        path = tmp_path / "metrics.jsonl"
        collector.flush_to_jsonl(path)
        collector.flush_to_jsonl(path)
        lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2

    def test_snapshot_has_timestamp(self):
        collector = _make_collector()
        snap = collector.snapshot()
        assert snap.ts <= time.time()
        assert snap.ts > time.time() - 5


# ══════════════════════════════════════════════════════════════════════════════
# B2 — HealthScore
# ══════════════════════════════════════════════════════════════════════════════


class TestB2HealthScore:
    """Score composite calculé correctement depuis un snapshot."""

    def test_perfect_score_on_clean_snapshot(self):
        scorer = HealthScore()
        snap = _clean_snap(memory_mb=0.0)  # pas de données mémoire → max pts
        score = scorer.compute(snap)
        assert score == 100.0

    def test_healthy_score_on_typical_snapshot(self):
        """Snapshot nominal → HEALTHY (>= 75)."""
        scorer = HealthScore()
        snap = _clean_snap()
        score = scorer.compute(snap)
        assert score >= 75.0
        assert scorer.level(score) in (HealthLevel.HEALTHY, HealthLevel.PERFECT)

    def test_drawdown_reduces_score(self):
        scorer = HealthScore()
        snap_ok = _clean_snap(drawdown_pct=0.0)
        snap_dd = _clean_snap(drawdown_pct=12.0)
        assert scorer.compute(snap_dd) < scorer.compute(snap_ok)

    def test_critical_drawdown_and_blocked_gate_degraded(self):
        """Drawdown critique + boot gate bloqué → score DEGRADED (< 75)."""
        scorer = HealthScore()
        # drawdown=20% : -15 pts trading ; boot_gate=False : -15 pts exchange
        snap = _clean_snap(drawdown_pct=20.0, boot_gate_cleared=False)
        score = scorer.compute(snap)
        assert score < 75.0, f"Attendu < 75, obtenu {score}"

    def test_high_memory_reduces_score(self):
        scorer = HealthScore()
        snap_low = _clean_snap(memory_mb=100.0)
        snap_high = _clean_snap(memory_mb=900.0)
        assert scorer.compute(snap_high) < scorer.compute(snap_low)

    def test_critical_memory_zero_pts(self):
        """Mémoire >= 1GB → 0 pts mémoire."""
        scorer = HealthScore()
        snap = _clean_snap(memory_mb=1200.0)
        bd = scorer.breakdown(snap)
        assert bd.memory == 0.0

    def test_error_rate_reduces_score(self):
        scorer = HealthScore()
        snap_ok = _clean_snap(error_rate=0.0)
        snap_err = _clean_snap(error_rate=6.0)
        assert scorer.compute(snap_err) < scorer.compute(snap_ok)

    def test_boot_gate_blocked_reduces_score(self):
        scorer = HealthScore()
        snap_cleared = _clean_snap(boot_gate_cleared=True)
        snap_blocked = _clean_snap(boot_gate_cleared=False)
        assert scorer.compute(snap_blocked) < scorer.compute(snap_cleared)

    def test_high_latency_reduces_score(self):
        scorer = HealthScore()
        snap_fast = _clean_snap(cycle_duration_ms=50.0)
        snap_slow = _clean_snap(cycle_duration_ms=3_000.0)
        assert scorer.compute(snap_slow) < scorer.compute(snap_fast)

    def test_level_mapping(self):
        scorer = HealthScore()
        assert scorer.level(100.0) == HealthLevel.PERFECT
        assert scorer.level(90.0) == HealthLevel.HEALTHY
        assert scorer.level(75.0) == HealthLevel.HEALTHY
        assert scorer.level(74.9) == HealthLevel.DEGRADED
        assert scorer.level(50.0) == HealthLevel.DEGRADED
        assert scorer.level(49.9) == HealthLevel.CRITICAL
        assert scorer.level(0.0) == HealthLevel.CRITICAL

    def test_score_bounded_0_100(self):
        """Le score est toujours dans [0, 100]."""
        scorer = HealthScore()
        for snap in [
            _clean_snap(),
            _clean_snap(drawdown_pct=100.0, error_rate=100.0, memory_mb=2000.0),
            _clean_snap(memory_mb=0.0, drawdown_pct=0.0),
        ]:
            score = scorer.compute(snap)
            assert 0.0 <= score <= 100.0, f"Score hors bornes: {score}"

    def test_breakdown_sums_to_total(self):
        """La somme des composantes = total."""
        scorer = HealthScore()
        snap = _clean_snap(drawdown_pct=3.0, memory_mb=400.0, error_rate=0.5)
        bd = scorer.breakdown(snap)
        computed = (
            bd.memory + bd.reliability + bd.exchange + bd.trading + bd.performance
        )
        assert abs(computed - bd.total) < 0.01

    def test_reconciliation_failure_affects_exchange_score(self):
        scorer = HealthScore()
        snap_ok = _clean_snap(reconciliation_failures=0)
        snap_fail = _clean_snap(reconciliation_failures=2)
        bd_ok = scorer.breakdown(snap_ok)
        bd_fail = scorer.breakdown(snap_fail)
        assert bd_fail.exchange < bd_ok.exchange

    def test_multiple_issues_compound(self):
        """Plusieurs problèmes simultanés → score très bas."""
        scorer = HealthScore()
        snap = _clean_snap(
            drawdown_pct=15.0,
            memory_mb=900.0,
            error_rate=6.0,
            boot_gate_cleared=False,
            cycle_duration_ms=3000.0,
        )
        score = scorer.compute(snap)
        assert score < 50.0, f"Score trop élevé avec de multiples problèmes: {score}"


# ══════════════════════════════════════════════════════════════════════════════
# B3 — AlertEngine
# ══════════════════════════════════════════════════════════════════════════════


class TestB3AlertEngine:
    """Règles d'alerte déclenchées sur les bons seuils."""

    def test_no_alerts_on_clean_snapshot(self):
        engine = AlertEngine()
        snap = _clean_snap()
        alerts = engine.check(snap)
        assert alerts == []

    def test_drawdown_alert_triggered(self):
        engine = AlertEngine()
        snap = _clean_snap(drawdown_pct=15.0)
        alerts = engine.check(snap)
        names = [a.rule for a in alerts]
        assert "DRAWDOWN" in names

    def test_drawdown_alert_severity_critical(self):
        engine = AlertEngine()
        snap = _clean_snap(drawdown_pct=15.0)
        alerts = {a.rule: a for a in engine.check(snap)}
        assert alerts["DRAWDOWN"].severity == AlertSeverity.CRITICAL

    def test_memory_alert_triggered(self):
        engine = AlertEngine()
        snap = _clean_snap(memory_mb=900.0)
        alerts = engine.check(snap)
        names = [a.rule for a in alerts]
        assert "MEMORY" in names

    def test_error_rate_alert_triggered(self):
        engine = AlertEngine()
        snap = _clean_snap(error_rate=5.0)
        alerts = engine.check(snap)
        names = [a.rule for a in alerts]
        assert "ERROR_RATE" in names

    def test_reconcile_failure_alert_triggered(self):
        engine = AlertEngine()
        snap = _clean_snap(reconciliation_failures=1)
        alerts = engine.check(snap)
        names = [a.rule for a in alerts]
        assert "RECONCILE_FAILURE" in names

    def test_boot_blocked_alert_triggered(self):
        engine = AlertEngine()
        snap = _clean_snap(boot_gate_cleared=False)
        alerts = engine.check(snap)
        names = [a.rule for a in alerts]
        assert "BOOT_BLOCKED" in names

    def test_high_latency_alert_triggered(self):
        engine = AlertEngine()
        snap = _clean_snap(cycle_duration_ms=3_000.0)
        alerts = engine.check(snap)
        names = [a.rule for a in alerts]
        assert "HIGH_LATENCY" in names

    def test_exception_count_alert_triggered(self):
        engine = AlertEngine()
        snap = _clean_snap(exception_count=10)
        alerts = engine.check(snap)
        names = [a.rule for a in alerts]
        assert "EXCEPTION_COUNT" in names

    def test_no_alert_below_drawdown_threshold(self):
        """9% drawdown < 10% seuil → pas d'alerte DRAWDOWN."""
        engine = AlertEngine()
        snap = _clean_snap(drawdown_pct=9.0)
        alerts = engine.check(snap)
        names = [a.rule for a in alerts]
        assert "DRAWDOWN" not in names

    def test_multiple_alerts_fired_simultaneously(self):
        engine = AlertEngine()
        snap = _clean_snap(
            drawdown_pct=15.0,
            memory_mb=900.0,
            reconciliation_failures=1,
        )
        alerts = engine.check(snap)
        names = [a.rule for a in alerts]
        assert "DRAWDOWN" in names
        assert "MEMORY" in names
        assert "RECONCILE_FAILURE" in names

    def test_disable_rule_prevents_alert(self):
        engine = AlertEngine()
        engine.disable_rule("DRAWDOWN")
        snap = _clean_snap(drawdown_pct=20.0)
        alerts = engine.check(snap)
        names = [a.rule for a in alerts]
        assert "DRAWDOWN" not in names

    def test_reenable_rule_fires_again(self):
        engine = AlertEngine()
        engine.disable_rule("DRAWDOWN")
        engine.enable_rule("DRAWDOWN")
        snap = _clean_snap(drawdown_pct=20.0)
        alerts = engine.check(snap)
        names = [a.rule for a in alerts]
        assert "DRAWDOWN" in names

    def test_total_fired_count(self):
        engine = AlertEngine()
        engine.check(_clean_snap(drawdown_pct=15.0))
        engine.check(_clean_snap(drawdown_pct=15.0))
        assert engine.total_fired() >= 2

    def test_custom_rule_added(self):
        engine = AlertEngine()
        custom = AlertRule(
            name="CAPITAL_ZERO",
            severity=AlertSeverity.CRITICAL,
            condition=lambda s: s.capital <= 0,
            message_fn=lambda s: "Capital épuisé",
            value_fn=lambda s: s.capital,
            threshold=0.0,
        )
        engine.add_rule(custom)
        snap = _clean_snap(capital=0.0)
        alerts = engine.check(snap)
        names = [a.rule for a in alerts]
        assert "CAPITAL_ZERO" in names

    def test_alert_persisted_to_jsonl(self, tmp_path):
        path = tmp_path / "alerts.jsonl"
        engine = AlertEngine(alert_path=path, persist=True)
        engine.check(_clean_snap(drawdown_pct=15.0))
        assert path.exists()
        data = json.loads(path.read_text().strip())
        assert data["rule"] == "DRAWDOWN"

    def test_alert_jsonl_valid_schema(self, tmp_path):
        path = tmp_path / "alerts.jsonl"
        engine = AlertEngine(alert_path=path, persist=True)
        engine.check(_clean_snap(drawdown_pct=15.0))
        data = json.loads(path.read_text().strip())
        for key in ("rule", "severity", "message", "value", "threshold", "ts"):
            assert key in data, f"Clé manquante dans alert JSONL: {key}"

    def test_alert_not_persisted_by_default(self, tmp_path):
        path = tmp_path / "alerts.jsonl"
        engine = AlertEngine(alert_path=path, persist=False)
        engine.check(_clean_snap(drawdown_pct=15.0))
        assert not path.exists()

    def test_rule_names_list(self):
        engine = AlertEngine()
        names = engine.rule_names()
        assert "DRAWDOWN" in names
        assert "BOOT_BLOCKED" in names
        assert len(names) >= 7

    def test_check_never_raises_on_bad_snapshot(self):
        """check() ne lève jamais même avec un snapshot avec des valeurs extrêmes."""
        engine = AlertEngine()
        snap = MetricsSnapshot()  # tout à zéro
        try:
            engine.check(snap)
        except Exception as exc:
            pytest.fail(f"check() a levé: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# B4 — Integration
# ══════════════════════════════════════════════════════════════════════════════


class TestB4Integration:
    """Cycle complet : collect → score → alert."""

    def test_full_cycle_healthy(self):
        """Système sain : score > 75, aucune alerte."""
        collector = _make_collector(capital=10_000.0)
        scorer = HealthScore()
        engine = AlertEngine()

        collector.set_boot_gate_cleared(True)
        with collector.measure_cycle():
            time.sleep(0.001)

        snap = collector.snapshot()
        snap.health_score = scorer.compute(snap)
        alerts = engine.check(snap)

        assert snap.health_score >= 75.0
        assert alerts == []

    def test_full_cycle_with_drawdown_triggers_alert(self):
        """Drawdown → alerte DRAWDOWN + score réduit."""
        equity_val = [10_000.0]
        collector = MetricsCollector(
            equity_fn=lambda: equity_val[0],
            initial_capital=10_000.0,
        )
        scorer = HealthScore()
        engine = AlertEngine()

        collector.set_boot_gate_cleared(True)
        collector.snapshot()  # peak = 10k

        equity_val[0] = 8_500.0  # drawdown 15%
        snap = collector.snapshot()
        snap.health_score = scorer.compute(snap)
        alerts = engine.check(snap)

        assert snap.drawdown_pct > 10.0
        assert snap.health_score < 100.0
        fired = [a.rule for a in alerts]
        assert "DRAWDOWN" in fired

    def test_full_cycle_exception_chain(self):
        """N exceptions → error_rate élevé → alerte ERROR_RATE."""
        collector = MetricsCollector(window_s=60.0)
        scorer = HealthScore()
        engine = AlertEngine()

        collector.set_boot_gate_cleared(True)
        for _ in range(20):
            collector.record_exception()

        snap = collector.snapshot()
        snap.health_score = scorer.compute(snap)
        alerts = engine.check(snap)

        assert snap.exception_count == 20
        assert snap.error_rate > 0.0

        fired = [a.rule for a in alerts]
        assert "EXCEPTION_COUNT" in fired

    def test_jsonl_snapshot_round_trip(self, tmp_path):
        """Snapshot flushed → rechargeable et cohérent."""
        collector = _make_collector(capital=9_500.0)
        path = tmp_path / "metrics.jsonl"
        collector.flush_to_jsonl(path)

        data = json.loads(path.read_text().strip())
        assert data["capital"] == 9_500.0
        assert "health_score" in data
        assert "ts" in data

    def test_metrics_snapshot_to_dict_complete(self):
        """to_dict() contient tous les champs attendus."""
        snap = _clean_snap()
        d = snap.to_dict()
        for key in (
            "ts",
            "cycle_duration_ms",
            "decision_latency_ms",
            "execution_latency_ms",
            "reconciliation_latency_ms",
            "memory_mb",
            "cpu_percent",
            "capital",
            "equity",
            "drawdown_pct",
            "open_positions",
            "error_rate",
            "exception_count",
            "reconciliation_failures",
            "boot_gate_cleared",
            "health_score",
        ):
            assert key in d, f"Champ manquant dans snapshot: {key}"
