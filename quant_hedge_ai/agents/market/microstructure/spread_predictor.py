"""
spread_predictor.py — Bid-Ask Spread Prediction

Prédit l'évolution du spread bid-ask à court terme (prochains cycles)
en utilisant un modèle de régression léger entraîné en ligne.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

import numpy as np

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.market.microstructure.spread_predictor")


class SpreadPredictor:
    """
    Prédit le spread bid-ask à partir de l'historique récent.
    Utilise une régression linéaire en ligne (OLS incremental) pour
    capturer les tendances de spread en temps réel.
    """

    WINDOW = 30  # taille de la fenêtre d'historique
    MIN_SAMPLES = 10  # minimum pour faire une prédiction

    def __init__(self) -> None:
        self._history: dict[str, deque] = defaultdict(lambda: deque(maxlen=self.WINDOW))
        self._models: dict[str, dict] = {}  # {symbol: {slope, intercept, last_fit}}

    def record(self, symbol: str, spread_bps: float) -> None:
        """Enregistre un spread observé."""
        self._history[symbol].append((time.time(), spread_bps))

    def predict(self, symbol: str, horizon: int = 1) -> float | None:
        """
        Prédit le spread dans `horizon` pas de temps.
        Retourne None si pas assez de données.
        """
        hist = list(self._history.get(symbol, []))
        if len(hist) < self.MIN_SAMPLES:
            return None

        # Extraire les spreads
        spreads = [s for _, s in hist]

        # Modèle AR(1) simple : spread_t+1 = alpha * spread_t + beta
        xs = np.array(spreads[:-1])
        ys = np.array(spreads[1:])

        if len(xs) < 3:
            return spreads[-1]  # fallback: dernier spread connu

        try:
            # Régression OLS (x, 1) → y
            X = np.column_stack([xs, np.ones(len(xs))])
            beta, *_ = np.linalg.lstsq(X, ys, rcond=None)
            slope, intercept = beta[0], beta[1]

            current = spreads[-1]
            predicted = slope * current + intercept

            # Clamp à des valeurs raisonnables
            predicted = max(0.1, min(predicted, 100.0))

            self._models[symbol] = {
                "slope": slope,
                "intercept": intercept,
                "last_fit": time.time(),
            }
            return predicted

        except Exception as exc:
            _log.debug("[SpreadPredictor] fit error for %s: %s", symbol, exc)
            return spreads[-1]

    def is_widening(self, symbol: str) -> bool:
        """True si le spread a tendance à s'élargir."""
        model = self._models.get(symbol)
        if model is None:
            return False
        hist = list(self._history.get(symbol, []))
        if len(hist) < 5:
            return False
        recent = [s for _, s in hist[-5:]]
        return recent[-1] > recent[0] * 1.2

    def spread_zscore(self, symbol: str) -> float:
        """Z-score du spread actuel par rapport à sa moyenne historique."""
        hist = list(self._history.get(symbol, []))
        if len(hist) < 5:
            return 0.0
        spreads = [s for _, s in hist]
        mean = sum(spreads) / len(spreads)
        std = (sum((s - mean) ** 2 for s in spreads) / len(spreads)) ** 0.5
        if std == 0:
            return 0.0
        return (spreads[-1] - mean) / std
