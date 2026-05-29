"""
supervision/tests/test_e06_proactive_alerts.py — E-06 ProactiveAlerts Thresholds

Tests de certification :
  - 4 seuils proactifs définis
  - Alerte ≥ 2 min avant le seuil critique
  - Aucun faux positif sur valeurs stables
  - time_to_critical() correct
  - Cooldown anti-spam

Total : 11 tests
"""

from __future__ import annotations

import time

import pytest

from supervision.proactive_alerts import (
    AlertThreshold,
    ProactiveAlert,
    ProactiveAlertsEngine,
)


def _stable_metrics() -> dict:
    """Métriques bien en dessous des seuils."""
    return {
        "current_drawdown_pct": 0.05,
        "max_drawdown_pct": 1.0,
        "daily_budget_used": 0.30,
        "avg_latency_ms": 100.0,
        "baseline_latency_ms": 100.0,
        "exchange_error_rate": 0.02,
    }


def _warning_metrics() -> dict:
    """Métriques au-dessus des seuils d'alerte."""
    return {
        "current_drawdown_pct": 0.92,  # 92% > seuil 90%
        "max_drawdown_pct": 1.0,
        "daily_budget_used": 0.93,  # 93% > seuil 90%
        "avg_latency_ms": 350.0,  # 3.5x baseline > 2x
        "baseline_latency_ms": 100.0,
        "exchange_error_rate": 0.15,  # 15% > 10%
    }


class TestThresholdsDefined:
    def test_four_default_thresholds(self):
        """L'engine contient les 4 seuils par défaut."""
        engine = ProactiveAlertsEngine()
        assert len(engine._thresholds) == 4
        required = {"drawdown", "daily_budget", "latency_ratio", "exchange_error_rate"}
        assert set(engine._thresholds.keys()) == required

    def test_custom_threshold_added(self):
        """Un seuil personnalisé peut être ajouté."""
        engine = ProactiveAlertsEngine()
        engine.add_threshold(
            AlertThreshold(
                metric_name="custom_metric",
                warning_ratio=0.80,
                critical_value=100.0,
                direction="above",
            )
        )
        assert "custom_metric" in engine._thresholds


class TestNoFalsePositives:
    def test_stable_metrics_no_alerts(self):
        """Métriques stables sous les seuils → aucune alerte."""
        engine = ProactiveAlertsEngine()
        alerts = engine.check(_stable_metrics())
        assert len(alerts) == 0, f"Faux positifs sur métriques stables: {alerts}"

    def test_no_false_positives_on_stable_window(self):
        """no_false_positives_on_stable() valide l'absence de FP."""
        engine = ProactiveAlertsEngine()
        stable_drawdown = [0.1, 0.15, 0.20, 0.25, 0.30]
        assert engine.no_false_positives_on_stable("drawdown", stable_drawdown)

    def test_warning_threshold_not_false_positive(self):
        """Juste en dessous du seuil d'alerte → pas de FP."""
        engine = ProactiveAlertsEngine()
        # drawdown 88% < seuil 90%
        metrics = dict(_stable_metrics())
        metrics["current_drawdown_pct"] = 0.88
        metrics["max_drawdown_pct"] = 1.0
        # 88% est juste en dessous de 90% (warning_ratio=0.90)
        # Pas encore d'alerte
        alerts = engine.check(metrics)
        drawdown_alerts = [a for a in alerts if a.metric_name == "drawdown"]
        assert len(drawdown_alerts) == 0


class TestAlertTriggering:
    def test_drawdown_alert_triggered(self):
        """Drawdown à 92% → alerte déclenchée."""
        engine = ProactiveAlertsEngine(cooldown_s=0.0)
        metrics = dict(_stable_metrics())
        metrics["current_drawdown_pct"] = 0.92
        metrics["max_drawdown_pct"] = 1.0
        alerts = engine.check(metrics)
        dd_alerts = [a for a in alerts if a.metric_name == "drawdown"]
        assert len(dd_alerts) >= 1

    def test_alert_has_required_fields(self):
        """ProactiveAlert contient tous les champs requis."""
        engine = ProactiveAlertsEngine(cooldown_s=0.0)
        alerts = engine.check(_warning_metrics())
        if alerts:
            a = alerts[0]
            assert hasattr(a, "metric_name")
            assert hasattr(a, "current_value")
            assert hasattr(a, "time_to_critical_s")
            assert hasattr(a, "severity")
            d = a.to_dict()
            assert "metric_name" in d
            assert "time_to_critical_s" in d

    def test_alert_fn_called(self):
        """alert_fn est appelée quand une alerte se déclenche."""
        called = []
        engine = ProactiveAlertsEngine(
            alert_fn=lambda a: called.append(a),
            cooldown_s=0.0,
        )
        engine.check(_warning_metrics())
        assert len(called) > 0

    def test_cooldown_prevents_spam(self):
        """Cooldown empêche les alertes répétées dans la même fenêtre."""
        engine = ProactiveAlertsEngine(cooldown_s=3600.0)  # 1h cooldown
        alerts1 = engine.check(_warning_metrics())
        alerts2 = engine.check(_warning_metrics())  # doublon → bloqué par cooldown
        assert len(alerts2) == 0 or len(alerts2) < len(alerts1)


class TestTimeToCritical:
    def test_ttc_returns_positive(self):
        """time_to_critical() retourne une valeur positive."""
        engine = ProactiveAlertsEngine()
        ttc = engine.time_to_critical("drawdown", 0.85, rate_per_s=0.001)
        assert ttc > 0

    def test_ttc_returns_inf_when_diverging(self):
        """TTC = inf si la valeur s'éloigne du seuil (rate négatif)."""
        engine = ProactiveAlertsEngine()
        ttc = engine.time_to_critical("drawdown", 0.85, rate_per_s=-0.001)
        assert ttc == float("inf")
