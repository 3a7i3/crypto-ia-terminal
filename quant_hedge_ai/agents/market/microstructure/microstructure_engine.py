"""
microstructure_engine.py — Market Microstructure Orchestrator

Agrège l'analyse order book, spread, et flow pour produire
un rapport de microstructure complet utilisable par le signal engine.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MicrostructureReport:
    symbol: str
    timestamp: float

    # Signaux clés
    directional_pressure: float = 0.0   # [-1,+1]
    imbalance: float = 0.0              # [-1,+1]
    spoofing_score: float = 0.0         # [0,1]
    spread_bps: float = 0.0
    liquidity_quality: float = 1.0      # [0,1] : 1 = liquidité excellente
    execution_risk: float = 0.0         # [0,1] : risque d'exécution adverse

    # Contexte
    has_bid_wall: bool = False
    has_ask_wall: bool = False
    spread_widening: bool = False
    regime_microstructure: str = "normal"  # "accumulation", "distribution", "squeeze", "normal"

    def is_favorable_for_long(self) -> bool:
        return (
            self.directional_pressure > 0.2
            and self.execution_risk < 0.5
            and not self.spread_widening
        )

    def is_favorable_for_short(self) -> bool:
        return (
            self.directional_pressure < -0.2
            and self.execution_risk < 0.5
            and not self.spread_widening
        )

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


class MicrostructureEngine:
    """
    Orchestre l'analyse complète de microstructure pour tous les symboles.
    Produit un MicrostructureReport exploitable par le pipeline de signal.
    """

    def __init__(self, orderbook_analyzer=None, spread_predictor=None, exchange=None) -> None:
        self._ob_analyzer = orderbook_analyzer
        self._spread_predictor = spread_predictor
        self._exchange = exchange
        self._last_reports: dict[str, MicrostructureReport] = {}

    def analyze(self, symbol: str, orderbook: dict | None = None) -> MicrostructureReport:
        """
        Analyse complète de microstructure pour un symbole.
        Récupère l'orderbook si non fourni et exchange disponible.
        """
        report = MicrostructureReport(symbol=symbol, timestamp=time.time())

        # Fetch orderbook si nécessaire
        if orderbook is None and self._exchange:
            try:
                orderbook = self._exchange.fetch_order_book(symbol, limit=50)
            except Exception as exc:
                logger.debug("[MicrostructureEngine] ob fetch error: %s", exc)

        if orderbook and self._ob_analyzer:
            ob_signal = self._ob_analyzer.analyze(symbol, orderbook)
            report.directional_pressure = ob_signal.directional_pressure
            report.imbalance = ob_signal.imbalance
            report.spoofing_score = ob_signal.spoofing_score
            report.spread_bps = ob_signal.spread_bps
            report.spread_widening = ob_signal.spread_widening
            report.has_bid_wall = ob_signal.nearest_bid_wall_pct > 0
            report.has_ask_wall = ob_signal.nearest_ask_wall_pct > 0

            # Qualité de liquidité
            total_depth = ob_signal.bid_depth_usd + ob_signal.ask_depth_usd
            if total_depth > 0:
                depth_score = min(total_depth / 500_000, 1.0)     # 500k USD = liquidité excellente
                spread_score = max(0.0, 1.0 - ob_signal.spread_bps / 20.0)  # >20bps = mauvais
                report.liquidity_quality = (depth_score + spread_score) / 2

            # Risque d'exécution
            report.execution_risk = self._compute_execution_risk(ob_signal)

            # Régime microstructure
            report.regime_microstructure = self._classify_regime(ob_signal)

        # Prédiction spread si disponible
        if self._spread_predictor:
            predicted_spread = self._spread_predictor.predict(symbol)
            if predicted_spread:
                report.spread_bps = predicted_spread

        self._last_reports[symbol] = report
        return report

    def get_last(self, symbol: str) -> MicrostructureReport | None:
        return self._last_reports.get(symbol)

    def analyze_all(self, symbols: list[str]) -> dict[str, MicrostructureReport]:
        return {s: self.analyze(s) for s in symbols}

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _compute_execution_risk(self, ob_signal) -> float:
        """Score de risque d'exécution adverse [0,1]."""
        risk = 0.0
        # Spread élevé = risque
        risk += min(ob_signal.spread_bps / 50.0, 0.4)
        # Spoofing = risque
        risk += ob_signal.spoofing_score * 0.3
        # Spread qui s'élargit = risque
        if ob_signal.spread_widening:
            risk += 0.3
        return min(risk, 1.0)

    def _classify_regime(self, ob_signal) -> str:
        """Classifie le régime microstructure."""
        if ob_signal.imbalance > 0.4 and not ob_signal.spread_widening:
            return "accumulation"
        if ob_signal.imbalance < -0.4 and not ob_signal.spread_widening:
            return "distribution"
        if ob_signal.spread_widening and ob_signal.spoofing_score > 0.3:
            return "squeeze"
        return "normal"
