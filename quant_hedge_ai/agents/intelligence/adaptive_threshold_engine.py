"""
adaptive_threshold_engine.py — Contrôle PID du seuil adaptatif.

Calcule un delta de seuil via un contrôle PID simplifié :

    integral = clip(EWMA(regret_delta), [-5, +5])   # terme I
    damped   = prev_delta + clip(integral - prev, damping_max)  # terme D
    delta_out = P + damped                            # terme P : régime ajust.

PID mapping :
  P = ajustement régime immédiat (SIDEWAYS → −4, TREND → +2, …)
  I = EWMA des deltas passés avec decay = 0.85 (bornée ±5, anti-windup)
  D = damping max ±1/cycle (frein si variation trop rapide)

Usage dans advisor_loop.py :
    ate = AdaptiveThresholdEngine()
    delta = ate.update(regime, regret_delta)   # appel chaque cycle
    gate.set_adaptive_delta(delta)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Ajustement par régime (terme P)
_REGIME_ADJ: dict[str, int] = {
    "sideways": -4,
    "RANGE": -4,
    "bull_trend": +2,
    "TREND_BULL": +2,
    "bear_trend": +2,
    "TREND_BEAR": +2,
    "high_volatility_regime": +3,
    "VOLATILE": +3,
    "choppy": -2,
    "CHOPPY": -2,
    "flash_crash": +999,  # inviolable
    "unknown": 0,
    "UNKNOWN": 0,
}


@dataclass
class ATEState:
    cycle: int = 0
    integral: float = 0.0  # terme I (EWMA borné)
    current_delta: int = 0  # delta appliqué au dernier cycle
    last_raw_regret: int = 0


class AdaptiveThresholdEngine:
    """
    Calcule un delta de seuil via PID.

    Le delta retourné est passé à GlobalRiskGate.set_adaptive_delta().
    Le gate applique ensuite ce delta sur le min_score de base (il garde la
    logique de régime dans _effective_min_score via MarketRegimeClassifier).

    Paramètres :
        ewma_alpha      : poids du cycle courant dans l'EWMA (decay = 1−alpha)
        damping_max     : variation max du delta par cycle
        integral_clamp  : bornes anti-windup sur le terme I
    """

    def __init__(
        self,
        ewma_alpha: float = 0.15,
        damping_max: float = 1.0,
        integral_clamp: tuple[int, int] = (-5, 5),
    ) -> None:
        self._alpha = ewma_alpha
        self._damping = damping_max
        self._clamp = integral_clamp
        self._state = ATEState()

    # ── API ───────────────────────────────────────────────────────────────────

    def update(self, regime: str, regret_delta: int = 0) -> int:
        """
        Met à jour le PID et retourne le delta entier à appliquer au gate.

        Args:
            regime       : régime courant détecté par l'advisor
            regret_delta : sortie de RegretEngine.get_threshold_delta()

        Returns:
            Delta entier à passer à gate.set_adaptive_delta()
        """
        s = self._state
        s.cycle += 1
        s.last_raw_regret = regret_delta

        # Flash crash : forcer résistance maximale
        if "flash" in regime.lower():
            s.current_delta = 20
            return 20

        # ── Terme I : EWMA lissée + anti-windup ──────────────────────────────
        s.integral = self._alpha * regret_delta + (1.0 - self._alpha) * s.integral
        s.integral = max(float(self._clamp[0]), min(float(self._clamp[1]), s.integral))

        # ── Terme D : damping ─────────────────────────────────────────────────
        target = round(s.integral)
        delta_change = target - s.current_delta
        delta_change = max(-self._damping, min(self._damping, delta_change))
        new_delta = round(s.current_delta + delta_change)

        if new_delta != s.current_delta:
            logger.debug(
                "[ATE] Cycle %d | régime=%s | raw=%+d | integral=%.2f"
                " | delta %+d → %+d",
                s.cycle,
                regime,
                regret_delta,
                s.integral,
                s.current_delta,
                new_delta,
            )

        s.current_delta = new_delta
        return new_delta

    def snapshot(self) -> dict:
        s = self._state
        return {
            "cycle": s.cycle,
            "integral": round(s.integral, 3),
            "current_delta": s.current_delta,
            "last_raw_regret": s.last_raw_regret,
        }

    def reset(self) -> None:
        """Réinitialisation complète — ex: après changement de régime brutal."""
        self._state = ATEState()
        logger.info("[ATE] État réinitialisé")
