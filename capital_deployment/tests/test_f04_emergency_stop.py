"""
capital_deployment/tests/test_f04_emergency_stop.py — F-04 Emergency Stop (F-06)

Tests de certification :
  - 8 critères définis (EmergencyCriteria enum)
  - check() retourne None sur métriques normales
  - drawdown > seuil+50% déclenche DRAWDOWN_EXCEEDED
  - 3 erreurs consécutives déclenchent CONSECUTIVE_TECH_ERRORS
  - api_key_compromised déclenche API_KEY_COMPROMISED
  - exchange_down_s > 300 déclenche EXCHANGE_CONNECTION_LOST
  - > 3 suspensions/h déclenchent ANOMALY_SUSPENSIONS
  - blackbox_inaccessible > 2 cycles déclenche BLACKBOX_INACCESSIBLE
  - invalid_signature_detected déclenche INVALID_SIGNATURE
  - killswitch_triggered déclenche KILLSWITCH_TRIGGERED
  - halt_fn appelé lors du premier trigger
  - reset() efface l'état actif mais préserve l'historique
  - trigger_stop() déclenche halt manuel
  - check_all() retourne plusieurs triggers simultanés

Total : 14 tests
"""

from __future__ import annotations

import time

import pytest

from capital_deployment.emergency_stop_manager import (
    EmergencyCriteria,
    EmergencyStopManager,
    EmergencyTrigger,
)


def _safe_metrics() -> dict:
    """Métriques parfaitement sûres — aucun critère déclenché."""
    return {
        "current_drawdown": 0.01,  # 1% < seuil F-01 (2% * 1.5 = 3%)
        "consecutive_tech_errors": 0,
        "api_key_compromised": False,
        "exchange_down_s": 0.0,
        "new_anomaly_suspensions": 0,
        "blackbox_inaccessible_cycles": 0,
        "invalid_signature_detected": False,
        "killswitch_triggered": False,
    }


class TestCriteriaEnum:
    def test_eight_criteria_defined(self):
        """EmergencyCriteria contient exactement 8 valeurs."""
        assert len(EmergencyCriteria) == 8

    def test_all_criteria_names_present(self):
        """Les 8 noms de critères attendus sont présents."""
        names = {c.value for c in EmergencyCriteria}
        expected = {
            "drawdown_exceeded",
            "consecutive_tech_errors",
            "api_key_compromised",
            "exchange_connection_lost",
            "anomaly_suspensions",
            "blackbox_inaccessible",
            "invalid_signature",
            "killswitch_triggered",
        }
        assert names == expected


class TestNoFalsePositives:
    def test_no_trigger_on_safe_metrics(self):
        """Pas de trigger sur des métriques sûres."""
        mgr = EmergencyStopManager(phase="F-01")
        trigger = mgr.check(_safe_metrics())
        assert trigger is None
        assert not mgr.is_emergency_active()


class TestIndividualCriteria:
    def test_drawdown_exceeded(self):
        """Drawdown > phase_limit * 1.5 → DRAWDOWN_EXCEEDED."""
        mgr = EmergencyStopManager(phase="F-01")
        # F-01 limit = 2%, emergency = 3%. Injecter 5%.
        metrics = dict(_safe_metrics())
        metrics["current_drawdown"] = 0.05
        trigger = mgr.check(metrics)
        assert trigger is not None
        assert trigger.criteria == EmergencyCriteria.DRAWDOWN_EXCEEDED

    def test_consecutive_tech_errors(self):
        """3 erreurs consécutives → CONSECUTIVE_TECH_ERRORS."""
        mgr = EmergencyStopManager(phase="F-01")
        metrics = dict(_safe_metrics())
        metrics["consecutive_tech_errors"] = 3
        trigger = mgr.check(metrics)
        assert trigger is not None
        assert trigger.criteria == EmergencyCriteria.CONSECUTIVE_TECH_ERRORS

    def test_api_key_compromised(self):
        """api_key_compromised=True → API_KEY_COMPROMISED."""
        mgr = EmergencyStopManager(phase="F-01")
        metrics = dict(_safe_metrics())
        metrics["api_key_compromised"] = True
        trigger = mgr.check(metrics)
        assert trigger is not None
        assert trigger.criteria == EmergencyCriteria.API_KEY_COMPROMISED

    def test_exchange_connection_lost(self):
        """exchange_down_s > 300 → EXCHANGE_CONNECTION_LOST."""
        mgr = EmergencyStopManager(phase="F-01", max_exchange_downtime_s=300.0)
        metrics = dict(_safe_metrics())
        metrics["exchange_down_s"] = 301.0
        trigger = mgr.check(metrics)
        assert trigger is not None
        assert trigger.criteria == EmergencyCriteria.EXCHANGE_CONNECTION_LOST

    def test_anomaly_suspensions_exceeded(self):
        """Plus de 3 suspensions en 1h → ANOMALY_SUSPENSIONS."""
        mgr = EmergencyStopManager(phase="F-01", max_suspensions_per_hour=3)
        metrics = dict(_safe_metrics())
        metrics["new_anomaly_suspensions"] = 4  # 4 d'un coup
        trigger = mgr.check(metrics)
        assert trigger is not None
        assert trigger.criteria == EmergencyCriteria.ANOMALY_SUSPENSIONS

    def test_blackbox_inaccessible(self):
        """BlackBox inaccessible > 2 cycles → BLACKBOX_INACCESSIBLE."""
        mgr = EmergencyStopManager(phase="F-01", max_blackbox_inaccessible_cycles=2)
        metrics = dict(_safe_metrics())
        metrics["blackbox_inaccessible_cycles"] = 3
        trigger = mgr.check(metrics)
        assert trigger is not None
        assert trigger.criteria == EmergencyCriteria.BLACKBOX_INACCESSIBLE

    def test_invalid_signature(self):
        """invalid_signature_detected=True → INVALID_SIGNATURE."""
        mgr = EmergencyStopManager(phase="F-01")
        metrics = dict(_safe_metrics())
        metrics["invalid_signature_detected"] = True
        trigger = mgr.check(metrics)
        assert trigger is not None
        assert trigger.criteria == EmergencyCriteria.INVALID_SIGNATURE

    def test_killswitch_triggered(self):
        """killswitch_triggered=True → KILLSWITCH_TRIGGERED."""
        mgr = EmergencyStopManager(phase="F-01")
        metrics = dict(_safe_metrics())
        metrics["killswitch_triggered"] = True
        trigger = mgr.check(metrics)
        assert trigger is not None
        assert trigger.criteria == EmergencyCriteria.KILLSWITCH_TRIGGERED


class TestHaltBehavior:
    def test_halt_fn_called_on_first_trigger(self):
        """halt_fn est appelée lors du premier trigger."""
        called = []
        mgr = EmergencyStopManager(
            phase="F-01",
            halt_fn=lambda reason: called.append(reason),
        )
        metrics = dict(_safe_metrics())
        metrics["killswitch_triggered"] = True
        mgr.check(metrics)
        assert len(called) == 1

    def test_halt_fn_not_called_twice(self):
        """halt_fn n'est appelée qu'une seule fois même sur plusieurs checks."""
        called = []
        mgr = EmergencyStopManager(
            phase="F-01",
            halt_fn=lambda reason: called.append(reason),
        )
        metrics = dict(_safe_metrics())
        metrics["killswitch_triggered"] = True
        mgr.check(metrics)
        mgr.check(metrics)  # deuxième appel
        assert len(called) == 1  # halt_fn appelée une seule fois

    def test_trigger_stop_manual(self):
        """trigger_stop() déclenche un arrêt d'urgence manuel."""
        halted = []
        mgr = EmergencyStopManager(
            phase="F-02",
            halt_fn=lambda r: halted.append(r),
        )
        mgr.trigger_stop("operateur: maintenance")
        assert mgr.is_emergency_active()
        assert len(halted) == 1

    def test_reset_clears_active_preserves_history(self):
        """reset() efface l'état actif mais préserve l'historique."""
        mgr = EmergencyStopManager(phase="F-01")
        metrics = dict(_safe_metrics())
        metrics["killswitch_triggered"] = True
        mgr.check(metrics)
        assert mgr.is_emergency_active()
        mgr.reset()
        assert not mgr.is_emergency_active()
        assert len(mgr.active_triggers()) == 0
        assert len(mgr.history()) >= 1  # historique préservé

    def test_check_all_returns_multiple_triggers(self):
        """check_all() retourne plusieurs triggers simultanés."""
        mgr = EmergencyStopManager(phase="F-01")
        metrics = dict(_safe_metrics())
        metrics["killswitch_triggered"] = True
        metrics["api_key_compromised"] = True
        triggers = mgr.check_all(metrics)
        assert len(triggers) >= 2
        criteria_values = {t.criteria for t in triggers}
        assert EmergencyCriteria.KILLSWITCH_TRIGGERED in criteria_values
        assert EmergencyCriteria.API_KEY_COMPROMISED in criteria_values
