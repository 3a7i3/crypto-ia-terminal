"""
regime_transition_smoother.py — Rampe linéaire lors des transitions de régime.

Lors d'un changement de régime, les paramètres (SL factor, threshold base,
aggressiveness) ne basculent pas instantanément.
Ils suivent une rampe linéaire sur N cycles :

    value(t) = old + (new - old) * min(t / ramp_duration, 1.0)

La rampe est réinitialisée si le régime change à nouveau pendant la transition.

Usage :
    smoother = RegimeTransitionSmoother(ramp_cycles=4)

    # Chaque cycle :
    smoother.update(detected_regime)
    sl_factor = smoother.smooth_float(old_sl, new_sl)  # interpolé
    threshold  = smoother.smooth_int(old_thr, new_thr)

    # Infos :
    smoother.in_transition     # True si rampe en cours
    smoother.progress          # 0.0 → 1.0
    smoother.snapshot()        # dict pour logs/dashboard
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class _RampState:
    active: bool = False
    from_regime: str = ""
    to_regime: str = ""
    elapsed: int = 0
    duration: int = 4
    progress: float = 0.0


class RegimeTransitionSmoother:
    """
    Lisse les transitions de régime via une rampe linéaire.

    Empêche les oscillations comportementales lors des changements de régime
    en interpolant progressivement les paramètres sur N cycles.
    """

    def __init__(self, ramp_cycles: int | None = None, safe_mode: bool = False) -> None:
        self._ramp = ramp_cycles or int(os.getenv("REGIME_RAMP_CYCLES", "4"))
        self._state = _RampState(duration=self._ramp)
        self._current: str = "unknown"
        self._safe_mode = safe_mode

    # ── API ───────────────────────────────────────────────────────────────────

    @property
    def in_transition(self) -> bool:
        return self._state.active

    @property
    def progress(self) -> float:
        return self._state.progress

    @property
    def current_regime(self) -> str:
        return self._current

    def update(self, new_regime: str) -> None:
        """
        Appeler une fois par cycle avec le régime détecté.

        Si le régime change : démarre (ou réinitialise) la rampe.
        Si la rampe est active : avance d'un cycle.
        """
        s = self._state

        if self._safe_mode:
            self._current = new_regime
            s.active = False
            return

        if new_regime != self._current:
            if s.active:
                logger.debug(
                    "[RegimeSmoother] Transition interrompue (%s → %s) —"
                    " nouvelle cible: %s",
                    s.from_regime,
                    s.to_regime,
                    new_regime,
                )
            s.from_regime = self._current
            s.to_regime = new_regime
            s.elapsed = 0
            s.progress = 0.0
            s.active = True
            s.duration = self._ramp
            logger.info(
                "[RegimeSmoother] %s → %s (rampe %d cycles)",
                s.from_regime,
                new_regime,
                self._ramp,
            )
            self._current = new_regime

        elif s.active:
            s.elapsed += 1
            s.progress = min(s.elapsed / s.duration, 1.0)
            if s.progress >= 1.0:
                s.active = False
                logger.debug("[RegimeSmoother] Rampe terminée → %s", self._current)

    def smooth_float(self, old_val: float, new_val: float) -> float:
        """Interpole une valeur flottante selon la progression de la rampe."""
        if not self._state.active:
            return new_val
        t = self._state.progress
        return old_val + (new_val - old_val) * t

    def smooth_int(self, old_val: int, new_val: int) -> int:
        """Interpole une valeur entière selon la progression de la rampe."""
        return round(self.smooth_float(float(old_val), float(new_val)))

    def snapshot(self) -> dict:
        s = self._state
        return {
            "in_transition": s.active,
            "from_regime": s.from_regime,
            "to_regime": s.to_regime,
            "current_regime": self._current,
            "progress_pct": round(s.progress * 100),
            "elapsed_cycles": s.elapsed,
            "ramp_duration": s.duration,
        }
