"""
slippage_predictor.py — ML Slippage Prediction Model

Prédit le slippage d'exécution attendu avant de passer un ordre,
en fonction de la taille, la liquidité, le spread et la volatilité.
Modèle : régression linéaire en ligne (OLS), entraîné sur l'historique réel.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

import numpy as np

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.execution.execution_v2.slippage_predictor")


@dataclass
class SlippageEstimate:
    symbol: str
    side: str  # "buy" / "sell"
    order_size_usd: float
    predicted_slippage_bps: float  # slippage prédit en bps
    predicted_slippage_pct: float  # en %
    confidence: float  # [0,1]
    cost_usd: float  # coût estimé en USD
    is_acceptable: bool  # True si < seuil max
    max_allowed_bps: float = 30.0


class SlippagePredictor:
    """
    Modèle de prédiction de slippage adaptatif.

    Features utilisées :
      - order_size_usd
      - spread_bps (microstructure)
      - ob_imbalance
      - atr_pct (volatilité)
      - liquidity_depth_usd
      - heure UTC (proxy pour liquidité temporelle)

    Entraîné en ligne sur chaque trade réel observé.
    """

    MAX_HISTORY = 500
    MIN_SAMPLES_FOR_MODEL = 20
    DEFAULT_SLIPPAGE_BPS = 5.0
    MAX_ACCEPTABLE_BPS = 30.0

    def __init__(self) -> None:
        self._training_data: deque = deque(maxlen=self.MAX_HISTORY)
        self._model_coefficients: np.ndarray | None = None
        self._last_fit: float = 0.0
        self._fit_interval: float = 300.0  # refitter toutes les 5min

    def predict(
        self,
        symbol: str,
        side: str,
        order_size_usd: float,
        spread_bps: float = 5.0,
        ob_imbalance: float = 0.0,
        atr_pct: float = 0.01,
        liquidity_depth_usd: float = 500_000.0,
    ) -> SlippageEstimate:
        """Prédit le slippage pour un ordre donné."""
        features = self._build_features(
            order_size_usd, spread_bps, ob_imbalance, atr_pct, liquidity_depth_usd, side
        )

        if (
            self._model_coefficients is not None
            and len(self._training_data) >= self.MIN_SAMPLES_FOR_MODEL
        ):
            predicted_bps = float(np.dot(features, self._model_coefficients))
            predicted_bps = max(0.1, predicted_bps)
            confidence = min(len(self._training_data) / 200.0, 0.95)
        else:
            # Heuristique avant d'avoir assez de données
            predicted_bps = self._heuristic_slippage(
                order_size_usd, spread_bps, liquidity_depth_usd
            )
            confidence = 0.3

        predicted_pct = predicted_bps / 10000.0
        cost_usd = order_size_usd * predicted_pct

        return SlippageEstimate(
            symbol=symbol,
            side=side,
            order_size_usd=order_size_usd,
            predicted_slippage_bps=predicted_bps,
            predicted_slippage_pct=predicted_pct,
            confidence=confidence,
            cost_usd=cost_usd,
            is_acceptable=predicted_bps <= self.MAX_ACCEPTABLE_BPS,
            max_allowed_bps=self.MAX_ACCEPTABLE_BPS,
        )

    def record_actual(
        self,
        order_size_usd: float,
        spread_bps: float,
        ob_imbalance: float,
        atr_pct: float,
        liquidity_depth_usd: float,
        side: str,
        actual_slippage_bps: float,
    ) -> None:
        """Enregistre un slippage réel observé pour entraîner le modèle."""
        features = self._build_features(
            order_size_usd, spread_bps, ob_imbalance, atr_pct, liquidity_depth_usd, side
        )
        self._training_data.append((features, actual_slippage_bps))

        now = time.time()
        if (
            now - self._last_fit > self._fit_interval
            and len(self._training_data) >= self.MIN_SAMPLES_FOR_MODEL
        ):
            self._fit_model()
            self._last_fit = now

    def _fit_model(self) -> None:
        """Entraîne le modèle OLS sur l'historique complet."""
        try:
            data = list(self._training_data)
            X = np.array([d[0] for d in data])
            y = np.array([d[1] for d in data])
            # OLS: β = (X'X)^-1 X'y
            coef, *_ = np.linalg.lstsq(X, y, rcond=None)
            self._model_coefficients = coef
            _log.debug("[SlippagePredictor] Modèle refitté sur %d samples", len(data))
        except Exception as exc:
            _log.warning("[SlippagePredictor] Fit error: %s", exc)

    def _build_features(
        self,
        order_size_usd: float,
        spread_bps: float,
        ob_imbalance: float,
        atr_pct: float,
        liquidity_depth_usd: float,
        side: str,
    ) -> np.ndarray:
        """Construit le vecteur de features normalisé."""
        size_ratio = order_size_usd / max(liquidity_depth_usd, 1.0)
        side_sign = 1.0 if side == "buy" else -1.0
        hour = time.localtime().tm_hour
        liquidity_period = abs(hour - 14) / 14.0  # 0=peak NY hours, 1=off hours

        return np.array(
            [
                size_ratio,
                spread_bps / 100.0,
                ob_imbalance * side_sign,
                atr_pct * 100.0,
                liquidity_period,
                1.0,  # biais
            ]
        )

    def _heuristic_slippage(
        self,
        order_size_usd: float,
        spread_bps: float,
        liquidity_depth_usd: float,
    ) -> float:
        """Estimation heuristique simple avant données suffisantes."""
        base = spread_bps * 0.5
        size_impact = (order_size_usd / max(liquidity_depth_usd, 1.0)) * 100
        return max(base + size_impact, self.DEFAULT_SLIPPAGE_BPS)
