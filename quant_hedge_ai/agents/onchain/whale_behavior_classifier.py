"""
whale_behavior_classifier.py — Whale Behavior Taxonomy

Classifie le comportement des baleines (grands wallets) en patterns
reconnus : accumulation, distribution, rotation, neutre.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class WhaleBehavior(str, Enum):
    ACCUMULATION = "accumulation"       # achats réguliers, outflow exchange
    DISTRIBUTION = "distribution"       # ventes, inflow exchange massif
    ROTATION = "rotation"               # mouvement inter-assets
    HODL = "hodl"                       # pas de mouvement significatif
    SQUEEZE = "squeeze"                 # liquidations forcées
    NEUTRAL = "neutral"


@dataclass
class WhaleSignal:
    symbol: str
    timestamp: float
    behavior: WhaleBehavior = WhaleBehavior.NEUTRAL
    confidence: float = 0.5             # [0,1]
    score: float = 0.0                  # [-1,+1] : -1 distrib, +1 accum
    large_tx_count: int = 0
    dominant_direction: str = "neutral" # "buy", "sell", "neutral"
    message: str = ""

    def is_bullish(self) -> bool:
        return self.behavior in (WhaleBehavior.ACCUMULATION,) and self.score > 0.3

    def is_bearish(self) -> bool:
        return self.behavior in (WhaleBehavior.DISTRIBUTION, WhaleBehavior.SQUEEZE) and self.score < -0.3


class WhaleBehaviorClassifier:
    """
    Classifie le comportement des baleines à partir des données on-chain.
    Combine : exchange flows, large transactions, dormancy, OI changes.
    """

    # Seuils
    LARGE_TX_THRESHOLD_USD = 500_000    # transaction "baleine" > 500k USD
    ACCUMULATION_RATIO = 0.3            # outflow > inflow de 30%
    DISTRIBUTION_RATIO = -0.3           # inflow > outflow de 30%

    def __init__(self) -> None:
        self._history: dict[str, list[WhaleSignal]] = {}

    def classify(self, symbol: str, onchain_data) -> WhaleSignal:
        """
        Classifie le comportement baleine depuis les données on-chain.
        onchain_data: OnChainData ou dict compatible.
        """
        if hasattr(onchain_data, '__dict__'):
            inflow = onchain_data.exchange_inflow_usd
            outflow = onchain_data.exchange_outflow_usd
            large_tx = onchain_data.large_tx_count
            whale_in = onchain_data.whale_inflow_usd
            whale_out = onchain_data.whale_outflow_usd
            dormancy = onchain_data.dormancy_flow
            supply_profit = onchain_data.supply_in_profit_pct
        else:
            inflow = float(onchain_data.get("exchange_inflow_usd", 0))
            outflow = float(onchain_data.get("exchange_outflow_usd", 0))
            large_tx = int(onchain_data.get("large_tx_count", 0))
            whale_in = float(onchain_data.get("whale_inflow_usd", 0))
            whale_out = float(onchain_data.get("whale_outflow_usd", 0))
            dormancy = float(onchain_data.get("dormancy_flow", 0))
            supply_profit = float(onchain_data.get("supply_in_profit_pct", 0.5))

        total_flow = inflow + outflow
        flow_ratio = (outflow - inflow) / total_flow if total_flow > 0 else 0.0

        score = self._compute_score(flow_ratio, large_tx, whale_out, whale_in, dormancy, supply_profit)
        behavior = self._map_behavior(score, flow_ratio, dormancy)
        direction = "buy" if score > 0.1 else "sell" if score < -0.1 else "neutral"
        confidence = min(abs(score) * 1.5, 1.0)

        sig = WhaleSignal(
            symbol=symbol,
            timestamp=time.time(),
            behavior=behavior,
            confidence=confidence,
            score=score,
            large_tx_count=large_tx,
            dominant_direction=direction,
            message=self._describe(behavior, flow_ratio, large_tx),
        )

        self._history.setdefault(symbol, []).append(sig)
        if len(self._history[symbol]) > 100:
            self._history[symbol] = self._history[symbol][-100:]

        return sig

    def trend(self, symbol: str, n: int = 5) -> str:
        """Tendance sur les n derniers signaux."""
        hist = self._history.get(symbol, [])[-n:]
        if not hist:
            return "unknown"
        avg_score = sum(s.score for s in hist) / len(hist)
        if avg_score > 0.2:
            return "accumulation"
        if avg_score < -0.2:
            return "distribution"
        return "neutral"

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _compute_score(
        self, flow_ratio: float, large_tx: int, whale_out: float,
        whale_in: float, dormancy: float, supply_profit: float
    ) -> float:
        score = flow_ratio * 0.4
        if large_tx > 10:
            whale_total = whale_in + whale_out
            if whale_total > 0:
                score += (whale_out - whale_in) / whale_total * 0.3
        score -= dormancy * 0.15
        if supply_profit > 0.75:
            score += 0.1
        elif supply_profit < 0.25:
            score -= 0.1
        return max(-1.0, min(1.0, score))

    def _map_behavior(self, score: float, flow_ratio: float, dormancy: float) -> WhaleBehavior:
        if score > self.ACCUMULATION_RATIO:
            return WhaleBehavior.ACCUMULATION
        if score < self.DISTRIBUTION_RATIO:
            if dormancy > 0.5:
                return WhaleBehavior.DISTRIBUTION
            return WhaleBehavior.DISTRIBUTION
        if abs(score) < 0.1:
            return WhaleBehavior.HODL
        return WhaleBehavior.NEUTRAL

    def _describe(self, behavior: WhaleBehavior, flow_ratio: float, large_tx: int) -> str:
        if behavior == WhaleBehavior.ACCUMULATION:
            return f"Baleines accumulent ({large_tx} large tx, outflow net +{flow_ratio:.1%})"
        if behavior == WhaleBehavior.DISTRIBUTION:
            return f"Baleines distribuent ({large_tx} large tx, inflow net {flow_ratio:.1%})"
        if behavior == WhaleBehavior.HODL:
            return "Baleines inactives (HODL)"
        return "Comportement baleine neutre"
