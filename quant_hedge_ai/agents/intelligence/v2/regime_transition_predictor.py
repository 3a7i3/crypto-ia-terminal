"""
regime_transition_predictor.py — Regime Transition Probability Forecasting

Prédit la probabilité qu'un changement de régime se produise dans
les prochaines N heures, en combinant :
- la matrice de transition HMM
- les indicateurs de tension (vol, spread, OI)
- les patterns historiques de transition
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TransitionForecast:
    symbol: str
    timestamp: float

    current_regime: str = "unknown"
    current_confidence: float = 0.0

    # Probabilités de transition dans les prochaines 4h
    transition_prob_4h: float = 0.0     # probabilité de changer de régime
    most_likely_next: str = "unknown"   # régime le plus probable après transition
    next_prob: float = 0.0

    # Alertes
    regime_fragile: bool = False        # True si le régime actuel est instable
    breakout_imminent: bool = False     # True si forte prob transition range→trend
    crash_risk: bool = False            # True si transition vers high_vol imminente

    # Tensions
    tension_score: float = 0.0         # [0,1] niveau de tension pré-transition

    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


class RegimeTransitionPredictor:
    """
    Prédit les transitions de régime en combinant HMM + indicateurs de tension.
    """

    # Indicateurs de tension : seuils
    VOL_EXPANSION_THRESHOLD = 1.5   # atr x1.5 vs moyenne = tension
    FUNDING_EXTREME = 0.002         # funding > 0.2% = surchauffe
    OI_SPIKE = 1.3                  # OI +30% = tension

    def __init__(self, hmm_engine=None) -> None:
        self._hmm = hmm_engine
        self._regime_history: dict[str, deque] = {}
        self._tension_history: dict[str, deque] = {}

    def forecast(
        self,
        symbol: str,
        current_probs,          # RegimeProbabilities
        features: dict[str, float],
    ) -> TransitionForecast:
        """Prédit la probabilité et la nature de la prochaine transition."""
        fc = TransitionForecast(
            symbol=symbol,
            timestamp=time.time(),
            current_regime=current_probs.dominant,
            current_confidence=current_probs.confidence,
        )

        # Niveau de tension pré-transition
        fc.tension_score = self._compute_tension(features)

        # Probabilité de transition depuis la matrice HMM
        if self._hmm:
            trans_matrix = self._hmm.transition_matrix()
            if trans_matrix is not None:
                fc.transition_prob_4h = self._predict_transition_from_matrix(
                    trans_matrix, current_probs, n_steps=4
                )
                fc.most_likely_next, fc.next_prob = self._predict_next_regime(
                    trans_matrix, current_probs
                )
            else:
                fc.transition_prob_4h = self._heuristic_transition_prob(fc.tension_score, current_probs)
        else:
            fc.transition_prob_4h = self._heuristic_transition_prob(fc.tension_score, current_probs)

        # Alertes
        fc.regime_fragile = current_probs.is_transitioning(0.4) or fc.tension_score > 0.6
        fc.breakout_imminent = (
            current_probs.dominant == "chop"
            and fc.tension_score > 0.5
            and features.get("volume_ratio", 1.0) > 1.5
        )
        fc.crash_risk = (
            features.get("funding_rate", 0) > self.FUNDING_EXTREME
            and fc.tension_score > 0.7
            and current_probs.dominant in ("bull", "high_vol")
        )

        # Mise à jour historique
        key = symbol
        if key not in self._regime_history:
            self._regime_history[key] = deque(maxlen=50)
        self._regime_history[key].append(current_probs.dominant)

        fc.message = self._describe(fc)
        return fc

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _compute_tension(self, features: dict[str, float]) -> float:
        """Score de tension pré-transition [0,1]."""
        tension = 0.0
        atr = features.get("atr_pct", 0.01)
        funding = abs(features.get("funding_rate", 0))
        volume_ratio = features.get("volume_ratio", 1.0)
        liq_risk = features.get("liquidation_risk", 0)
        ob_imbalance = abs(features.get("ob_imbalance", 0))

        # Volatilité expansive
        if atr > 0.02:
            tension += min((atr - 0.02) / 0.02, 0.3)

        # Funding extrême
        if funding > self.FUNDING_EXTREME:
            tension += min(funding / 0.01, 0.25)

        # Volume anormal
        if volume_ratio > self.OI_SPIKE:
            tension += min((volume_ratio - 1.3) / 2.0, 0.2)

        # Risque de liquidation
        tension += liq_risk * 0.15

        # Déséquilibre order book extrême
        if ob_imbalance > 0.6:
            tension += 0.1

        return min(tension, 1.0)

    def _predict_transition_from_matrix(
        self,
        trans_matrix: np.ndarray,
        probs,
        n_steps: int = 4,
    ) -> float:
        """
        Calcule la probabilité de sortie du régime actuel dans n_steps.
        P(régime change) = 1 - P(même régime dans n_steps)
        """
        try:
            n = trans_matrix.shape[0]
            state_names = ["bull", "bear", "chop", "high_vol"]
            current_idx = state_names.index(probs.dominant) if probs.dominant in state_names else 0
            # Puissance de la matrice de transition
            trans_n = np.linalg.matrix_power(trans_matrix, n_steps)
            stay_prob = trans_n[current_idx, current_idx]
            return float(1.0 - stay_prob)
        except Exception:
            return self._heuristic_transition_prob(0.5, probs)

    def _predict_next_regime(self, trans_matrix: np.ndarray, probs) -> tuple[str, float]:
        """Identifie le régime le plus probable après une transition."""
        try:
            state_names = ["bull", "bear", "chop", "high_vol"]
            current_idx = state_names.index(probs.dominant) if probs.dominant in state_names else 0
            row = trans_matrix[current_idx].copy()
            row[current_idx] = 0    # exclure le régime actuel
            next_idx = int(np.argmax(row))
            return state_names[next_idx], float(row[next_idx] / max(row.sum(), 1e-10))
        except Exception:
            return "chop", 0.33

    def _heuristic_transition_prob(self, tension: float, probs) -> float:
        base = tension * 0.4
        fragility = 1.0 - probs.confidence
        return min(base + fragility * 0.3, 0.95)

    def _describe(self, fc: TransitionForecast) -> str:
        if fc.crash_risk:
            return f"ALERTE: Risque crash — funding extrême + tension {fc.tension_score:.0%}"
        if fc.breakout_imminent:
            return f"Breakout imminent depuis range (tension {fc.tension_score:.0%})"
        if fc.regime_fragile:
            return f"Régime {fc.current_regime} fragile — transition {fc.transition_prob_4h:.0%} probable 4h"
        return f"Régime {fc.current_regime} stable (confiance {fc.current_confidence:.0%})"
