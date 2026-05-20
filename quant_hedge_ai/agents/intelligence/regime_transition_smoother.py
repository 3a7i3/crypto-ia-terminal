"""
regime_transition_smoother.py — Lissage court des paramètres régime-aware.

Stabilise les changements confirmés de régime en appliquant une petite rampe
sur les paramètres les plus sensibles :
  - threshold de score effectif
  - facteur SL basé sur l'ATR

Le changement de régime reste piloté par l'hystérésis existante
(_REGIME_STABILITY dans advisor_loop). Ce composant ne remplace pas cette
confirmation : il amortit uniquement la transition des paramètres.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass

from quant_hedge_ai.agents.intelligence.market_regime_classifier import (
    MarketRegimeClassifier,
)

_FLOAT_EPSILON = 1e-9


@dataclass(frozen=True)
class TransitionSnapshot:
    old_regime: str
    new_regime: str
    cycle_index: int
    smoothed_threshold: int
    target_threshold: int
    smoothed_sl_factor: float
    target_sl_factor: float
    remaining_transition_cycles: int
    transition_active: bool
    transition_started: bool
    transition_completed: bool

    def as_dict(self) -> dict:
        return asdict(self)


class RegimeTransitionSmoother:
    """Applique une rampe courte (3-5 cycles) sur threshold et SL factor."""

    def __init__(
        self,
        ramp_cycles: int | None = None,
        classifier: MarketRegimeClassifier | None = None,
    ) -> None:
        configured = ramp_cycles or int(os.getenv("REGIME_TRANSITION_RAMP_CYCLES", "4"))
        self._ramp_cycles = max(3, min(5, configured))
        self._classifier = classifier or MarketRegimeClassifier()

        self._initialized = False
        self._old_regime = "unknown"
        self._target_regime = "unknown"
        self._current_threshold = 70
        self._target_threshold = 70
        self._current_sl_factor = 1.5
        self._target_sl_factor = 1.5
        self._transition_remaining = 0
        self._start_threshold = 70
        self._start_sl_factor = 1.5

    def advance(
        self,
        target_regime: str,
        cycle_index: int,
        regret_delta: int = 0,
    ) -> TransitionSnapshot:
        target_threshold = self._classifier.effective_min_score(
            target_regime, delta=regret_delta
        )
        target_sl_factor = self._classifier.get_config(target_regime).sl_factor_atr

        if not self._initialized:
            self._initialized = True
            self._old_regime = target_regime
            self._target_regime = target_regime
            self._current_threshold = target_threshold
            self._target_threshold = target_threshold
            self._current_sl_factor = target_sl_factor
            self._target_sl_factor = target_sl_factor
            return TransitionSnapshot(
                old_regime=target_regime,
                new_regime=target_regime,
                cycle_index=cycle_index,
                smoothed_threshold=target_threshold,
                target_threshold=target_threshold,
                smoothed_sl_factor=round(target_sl_factor, 4),
                target_sl_factor=round(target_sl_factor, 4),
                remaining_transition_cycles=0,
                transition_active=False,
                transition_started=False,
                transition_completed=False,
            )

        transition_started = False
        transition_completed = False
        if (
            target_regime != self._target_regime
            or target_threshold != self._target_threshold
            or abs(target_sl_factor - self._target_sl_factor) > _FLOAT_EPSILON
        ):
            self._old_regime = self._target_regime
            self._target_regime = target_regime
            self._start_threshold = self._current_threshold
            self._start_sl_factor = self._current_sl_factor
            self._target_threshold = target_threshold
            self._target_sl_factor = target_sl_factor
            if (
                self._start_threshold == self._target_threshold
                and abs(self._start_sl_factor - self._target_sl_factor)
                <= _FLOAT_EPSILON
            ):
                self._transition_remaining = 0
            else:
                self._transition_remaining = self._ramp_cycles
                transition_started = True

        if self._transition_remaining > 0:
            completed_steps = self._ramp_cycles - self._transition_remaining + 1
            progress = completed_steps / self._ramp_cycles
            self._current_threshold = round(
                self._start_threshold
                + (self._target_threshold - self._start_threshold) * progress
            )
            self._current_sl_factor = (
                self._start_sl_factor
                + (self._target_sl_factor - self._start_sl_factor) * progress
            )
            self._transition_remaining -= 1
            if self._transition_remaining == 0:
                self._current_threshold = self._target_threshold
                self._current_sl_factor = self._target_sl_factor
                transition_completed = True

        return TransitionSnapshot(
            old_regime=self._old_regime,
            new_regime=self._target_regime,
            cycle_index=cycle_index,
            smoothed_threshold=int(self._current_threshold),
            target_threshold=int(self._target_threshold),
            smoothed_sl_factor=round(self._current_sl_factor, 4),
            target_sl_factor=round(self._target_sl_factor, 4),
            remaining_transition_cycles=self._transition_remaining,
            transition_active=self._transition_remaining > 0,
            transition_started=transition_started,
            transition_completed=transition_completed,
        )
