"""
test_p7_validation.py — Critères P7 : RiskGovernor, CircuitBreaker, CapitalThrottle.

Critères obligatoires :
  - DEFENSIVE dans les 3 cycles suivant drawdown > 3%
  - Aucun trade en RISK_OFF
  - CircuitBreaker → DEGRADED après 5 échecs
  - CapitalThrottle réduit proportionnellement au drawdown
"""

import time

import pytest

from quant_hedge_ai.agents.risk.capital_throttle import CapitalThrottle
from quant_hedge_ai.agents.risk.exposure_manager import DynamicExposureManager
from quant_hedge_ai.agents.risk.risk_governor import RiskGovernor, RiskState
from supervision.circuit_breaker_robust import CBState, ComponentCircuitBreaker

# ─────────────────────────────────────────────────────────────────────────────
# RiskGovernor — transitions et hystérésis
# ─────────────────────────────────────────────────────────────────────────────


class TestRiskGovernorTransitions:
    def _gov(self) -> RiskGovernor:
        g = RiskGovernor()
        # Hystérésis réduite pour les tests
        g.MIN_CYCLES = 1
        return g

    def test_defensive_within_3_cycles_on_drawdown(self):
        """DEFENSIVE déclenché <= 3 cycles après drawdown > 3%."""
        gov = self._gov()
        reached_defensive = False
        for cycle in range(1, 5):
            snap = gov.update(cycle=cycle, drawdown_pct=0.04, consecutive_losses=0)
            if snap.state == "defensive":
                reached_defensive = True
                assert cycle <= 3, f"DEFENSIVE trop tardif (cycle {cycle})"
                break
        assert reached_defensive, "État DEFENSIVE jamais atteint"

    def test_risk_off_on_large_drawdown(self):
        """RISK_OFF déclenché si drawdown > 6%."""
        gov = self._gov()
        gov.MIN_CYCLES = 1
        # Passer d'abord par DEFENSIVE
        gov.update(cycle=1, drawdown_pct=0.04, consecutive_losses=0)
        snap = gov.update(cycle=2, drawdown_pct=0.07, consecutive_losses=0)
        assert snap.state == "risk_off"

    def test_risk_off_on_consecutive_losses(self):
        """RISK_OFF déclenché après 3 pertes consécutives depuis DEFENSIVE."""
        gov = self._gov()
        gov.update(cycle=1, drawdown_pct=0.04, consecutive_losses=0)
        snap = gov.update(cycle=2, drawdown_pct=0.04, consecutive_losses=3)
        assert snap.state == "risk_off"

    def test_no_new_trades_in_risk_off(self):
        """allow_new_trades = False en RISK_OFF."""
        gov = self._gov()
        gov.update(cycle=1, drawdown_pct=0.04, consecutive_losses=0)
        gov.update(cycle=2, drawdown_pct=0.07, consecutive_losses=0)
        assert gov.state == RiskState.RISK_OFF
        assert gov.allow_new_trades is False

    def test_risk_off_does_not_recover_on_missing_atr(self):
        """ATR absent ne doit pas compter comme volatilité revenue au calme."""
        gov = self._gov()
        gov.RISK_OFF_SAFE_CYCLES = 10
        gov.update(cycle=1, drawdown_pct=0.04, consecutive_losses=0)
        gov.update(cycle=2, drawdown_pct=0.07, consecutive_losses=0)
        snap = gov.update(cycle=3, drawdown_pct=0.0, consecutive_losses=0)
        assert snap.state == "risk_off"

    def test_aggressive_requires_known_calm_volatility(self):
        """Sans ATR connu, PnL positif seul ne suffit pas pour AGGRESSIVE."""
        gov = self._gov()
        gov.AGGRESSIVE_PNL_CYCLES = 2
        for cycle in range(1, 5):
            snap = gov.update(
                cycle=cycle,
                drawdown_pct=0.0,
                consecutive_losses=0,
                cycle_pnl_pct=0.01,
                regime="bull_trend",
            )
        assert snap.state == "normal"

    def test_hysteresis_min_cycles(self):
        """Pas de transition avant MIN_CYCLES cycles dans l'état."""
        gov = RiskGovernor()
        gov.MIN_CYCLES = 5
        # Cycle 1-4 avec drawdown élevé : pas encore de transition
        for c in range(1, 5):
            snap = gov.update(cycle=c, drawdown_pct=0.04, consecutive_losses=0)
            assert snap.state == "normal", f"Transition prématurée au cycle {c}"

    def test_size_multiplier_per_state(self):
        """size_multiplier conforme à la spec."""
        gov = self._gov()
        # NORMAL
        snap = gov.update(cycle=1, drawdown_pct=0.0, consecutive_losses=0)
        assert snap.size_multiplier == 1.0
        # DEFENSIVE
        gov.update(cycle=2, drawdown_pct=0.04, consecutive_losses=0)
        snap = gov.update(cycle=3, drawdown_pct=0.04, consecutive_losses=0)
        if snap.state == "defensive":
            assert snap.size_multiplier == 0.5

    def test_recovery_size_is_25pct(self):
        """RECOVERY → size_multiplier = 0.25."""
        gov = self._gov()
        gov._state = RiskState.RECOVERY
        gov._cycles_in_state = 10
        snap = gov.snapshot()
        assert snap.size_multiplier == 0.25

    def test_aggressive_size_is_120pct(self):
        """AGGRESSIVE → size_multiplier = 1.2."""
        gov = self._gov()
        gov._state = RiskState.AGGRESSIVE
        snap = gov.snapshot()
        assert snap.size_multiplier == 1.2

    def test_threshold_delta_risk_off(self):
        """RISK_OFF → threshold_delta = +15 (bloque tout)."""
        gov = self._gov()
        gov._state = RiskState.RISK_OFF
        assert gov.threshold_delta == 15

    def test_threshold_delta_recovery(self):
        """RECOVERY → threshold_delta = +3."""
        gov = self._gov()
        gov._state = RiskState.RECOVERY
        assert gov.threshold_delta == 3


# ─────────────────────────────────────────────────────────────────────────────
# VolatilityEmergencyMode
# ─────────────────────────────────────────────────────────────────────────────


class TestVolatilityEmergency:
    def test_emergency_triggered_at_3x_atr(self):
        """VolatilityEmergencyMode se déclenche si ATR > 3× médiane."""
        gov = RiskGovernor()
        gov.MIN_CYCLES = 1
        # Peupler l'historique ATR avec médiane = 0.01
        for i in range(1, 20):
            gov.update(
                cycle=i, drawdown_pct=0.0, consecutive_losses=0, atr_current=0.01
            )
        # ATR à 3.5× = 0.035
        snap = gov.update(
            cycle=20, drawdown_pct=0.0, consecutive_losses=0, atr_current=0.035
        )
        assert snap.vol_emergency is True
        assert snap.allow_new_trades is False

    def test_emergency_cooldown_after_return(self):
        """VolatilityEmergencyMode tient au moins VOL_EMERGENCY_COOLDOWN cycles."""
        gov = RiskGovernor()
        gov.MIN_CYCLES = 1
        gov.VOL_EMERGENCY_COOLDOWN = 3
        for i in range(1, 20):
            gov.update(
                cycle=i, drawdown_pct=0.0, consecutive_losses=0, atr_current=0.01
            )
        # Déclencher
        gov.update(cycle=20, drawdown_pct=0.0, consecutive_losses=0, atr_current=0.05)
        # Retour sous seuil — doit rester actif pendant cooldown
        for c in range(21, 24):
            snap = gov.update(
                cycle=c, drawdown_pct=0.0, consecutive_losses=0, atr_current=0.01
            )
            assert snap.vol_emergency is True, f"Emergency levée trop tôt (cycle {c})"


# ─────────────────────────────────────────────────────────────────────────────
# CircuitBreaker — progression HEALTHY → UNSTABLE → DEGRADED → DISABLED
# ─────────────────────────────────────────────────────────────────────────────


class TestCircuitBreaker:
    def _failing_fn(self):
        raise RuntimeError("simulated failure")

    def _ok_fn(self):
        return "ok"

    def test_degraded_after_5_failures(self):
        """CircuitBreaker → DEGRADED après 5 échecs consécutifs."""
        cb = ComponentCircuitBreaker("test_comp", fallback=None)
        for _ in range(5):
            cb.call(self._failing_fn)
            cb._backoff_until = 0.0
        assert cb.state == CBState.DEGRADED

    def test_disabled_after_10_failures(self):
        """CircuitBreaker → DISABLED après 10 échecs (via _on_failure direct)."""
        cb = ComponentCircuitBreaker("test_comp", fallback=None)
        for _ in range(10):
            cb._on_failure()
        assert cb.state == CBState.DISABLED

    def test_unstable_after_2_failures(self):
        """CircuitBreaker → UNSTABLE après 2 échecs."""
        cb = ComponentCircuitBreaker("test_comp")
        for _ in range(2):
            cb.call(self._failing_fn)
        assert cb.state == CBState.UNSTABLE

    def test_healthy_after_recovery(self):
        """Retour à HEALTHY après N succès depuis UNSTABLE (1 succès par 1 failure)."""
        cb = ComponentCircuitBreaker("test_comp")
        cb.call(self._failing_fn)
        cb.call(self._failing_fn)
        assert cb.state == CBState.UNSTABLE
        # Il faut autant de succès que de failures pour revenir à 0
        cb._backoff_until = 0.0
        cb.call(self._ok_fn)
        cb._backoff_until = 0.0
        cb.call(self._ok_fn)
        assert cb.state == CBState.HEALTHY

    def test_unstable_backoff_returns_fallback_without_retry(self):
        """UNSTABLE respecte le backoff au lieu de rappeler la fonction."""
        cb = ComponentCircuitBreaker("test_comp", fallback="fb")
        cb.call(self._failing_fn)
        cb.call(self._failing_fn)
        assert cb.state == CBState.UNSTABLE
        result = cb.call(self._ok_fn)
        assert result == "fb"
        assert cb.state == CBState.UNSTABLE

    def test_fallback_returned_in_degraded(self):
        """Fallback retourné en état DEGRADED (sans tentative recovery)."""
        cb = ComponentCircuitBreaker("test_comp", fallback={"healthy": False})
        # Forcer DEGRADED
        cb._state = CBState.DEGRADED
        cb._failures = 5
        cb._last_recovery_ts = time.time()  # block recovery
        result = cb.call(self._ok_fn)
        assert result == {"healthy": False}

    def test_no_retry_until_backoff_expired_in_degraded(self):
        """En DEGRADED, les appels retournent fallback sans appeler la fonction."""
        cb = ComponentCircuitBreaker("test_comp", fallback="fb")
        cb._state = CBState.DEGRADED
        cb._failures = 5
        cb._last_recovery_ts = time.time()  # recovery pas encore éligible
        result = cb.call(self._ok_fn)
        assert result == "fb"


# ─────────────────────────────────────────────────────────────────────────────
# CapitalThrottle — réduction progressive + rampe
# ─────────────────────────────────────────────────────────────────────────────


class TestCapitalThrottle:
    def test_no_throttle_below_soft_dd(self):
        """factor = 1.0 si drawdown < 5%."""
        ct = CapitalThrottle()
        ct.update(1000.0)  # peak = 1000
        factor = ct.update(975.0)  # dd = 2.5%
        assert factor == 1.0

    def test_partial_throttle_at_7pct_dd(self):
        """factor < 1.0 à 7% de drawdown."""
        ct = CapitalThrottle()
        ct.update(1000.0)
        factor = ct.update(930.0)  # dd = 7%
        assert 0.0 < factor < 1.0

    def test_full_stop_at_10pct_dd(self):
        """factor = 0 (ou MIN_OPERATIONAL) à 10% drawdown."""
        ct = CapitalThrottle()
        ct.update(1000.0)
        factor = ct.update(900.0)  # dd = 10%
        assert factor == 0.0
        assert ct.allow_trades is False

    def test_progressive_reduction(self):
        """Réduction proportionnelle : 7% dd > 5% dd en termes de réduction."""
        ct7 = CapitalThrottle()
        ct7.update(1000.0)
        f7 = ct7.update(930.0)  # 7%

        ct5 = CapitalThrottle()
        ct5.update(1000.0)
        ct5.update(950.0)  # 5%
        f5 = ct5.update(950.0)

        assert f7 < f5, "7% drawdown doit réduire plus que 5%"

    def test_ramp_recovery(self):
        """factor remonte progressivement (pas instantanément) après amélioration."""
        ct = CapitalThrottle()
        ct.update(1000.0)
        ct.update(900.0)  # force throttle à 0
        f1 = ct.update(1000.0)  # capital revenu — ramp
        f2 = ct.update(1000.0)
        assert f2 > f1, "Récupération doit être progressive"
        assert f2 <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# DynamicExposureManager
# ─────────────────────────────────────────────────────────────────────────────


class TestDynamicExposureManager:
    def test_risk_off_blocks_all(self):
        """Aucune exposition autorisée en RISK_OFF."""
        dem = DynamicExposureManager(10000.0)
        ok, reason = dem.can_add_exposure(1.0, RiskState.RISK_OFF)
        assert ok is False
        assert "RISK_OFF" in reason

    def test_normal_allows_within_20pct(self):
        """Exposition autorisée jusqu'à 20% en NORMAL."""
        dem = DynamicExposureManager(10000.0)
        ok, _ = dem.can_add_exposure(1500.0, RiskState.NORMAL)
        assert ok is True

    def test_normal_blocks_above_20pct(self):
        """Exposition refusée si > 20% en NORMAL."""
        dem = DynamicExposureManager(10000.0)
        dem.record_open(1800.0)
        ok, _ = dem.can_add_exposure(500.0, RiskState.NORMAL)
        assert ok is False

    def test_record_open_close_balance(self):
        """record_open / record_close maintiennent le solde."""
        dem = DynamicExposureManager(10000.0)
        dem.record_open(500.0)
        dem.record_open(300.0)
        dem.record_close(200.0)
        assert dem.exposure_used == pytest.approx(600.0)
