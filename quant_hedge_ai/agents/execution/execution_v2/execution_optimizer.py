"""
execution_optimizer.py — Liquidity-Aware Execution Planning

Détermine la meilleure stratégie d'exécution pour un ordre :
- Taker immédiat (urgent)
- Maker (patient, économise le spread)
- TWAP (découpage temporel)
- Liquidity-split (découpage en taille)
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ExecutionStrategy(str, Enum):
    TAKER_IMMEDIATE = "taker_immediate"     # ordre market immédiat
    MAKER_LIMIT = "maker_limit"             # limit au bid/ask
    TWAP = "twap"                           # découpage temporel
    LIQUIDITY_SPLIT = "liquidity_split"     # découpage en taille


@dataclass
class ExecutionChunk:
    size_usd: float
    delay_seconds: float
    strategy: ExecutionStrategy
    price_limit: float | None = None


@dataclass
class ExecutionPlan:
    symbol: str
    side: str
    total_size_usd: float
    strategy: ExecutionStrategy
    chunks: list[ExecutionChunk] = field(default_factory=list)
    estimated_slippage_bps: float = 0.0
    estimated_cost_usd: float = 0.0
    urgency_score: float = 0.5              # [0,1] : 1 = exécuter maintenant
    notes: str = ""

    def total_chunks(self) -> int:
        return len(self.chunks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "total_size_usd": self.total_size_usd,
            "strategy": self.strategy.value,
            "n_chunks": self.total_chunks(),
            "estimated_slippage_bps": self.estimated_slippage_bps,
            "estimated_cost_usd": self.estimated_cost_usd,
            "urgency_score": self.urgency_score,
            "notes": self.notes,
        }


class ExecutionOptimizer:
    """
    Génère un plan d'exécution optimal selon les conditions de marché.

    Critères de décision :
    - signal_urgency: 0 = patient, 1 = urgent
    - liquidité disponible (depth)
    - spread (coût du taker)
    - volatilité (fenêtre d'opportunité courte si haute vol)
    - taille relative à la liquidité
    """

    TWAP_MAX_SIZE_USD = 50_000      # seuil pour déclencher TWAP
    SPLIT_RATIO = 0.03              # ne pas dépasser 3% de la liquidité en 1 ordre

    def __init__(self, slippage_predictor=None) -> None:
        self._slippage_predictor = slippage_predictor

    def plan(
        self,
        symbol: str,
        side: str,
        size_usd: float,
        signal_urgency: float = 0.5,
        spread_bps: float = 5.0,
        liquidity_depth_usd: float = 500_000.0,
        atr_pct: float = 0.01,
        ob_imbalance: float = 0.0,
    ) -> ExecutionPlan:
        """Construit le plan d'exécution optimal."""

        # Estimation slippage
        slippage_bps = spread_bps * 0.5
        if self._slippage_predictor:
            est = self._slippage_predictor.predict(
                symbol, side, size_usd, spread_bps, ob_imbalance, atr_pct, liquidity_depth_usd
            )
            slippage_bps = est.predicted_slippage_bps

        # Choix de stratégie
        size_ratio = size_usd / max(liquidity_depth_usd, 1.0)
        strategy = self._choose_strategy(signal_urgency, spread_bps, size_usd, size_ratio, atr_pct)

        # Construction des chunks
        chunks = self._build_chunks(strategy, size_usd, liquidity_depth_usd, signal_urgency)

        plan = ExecutionPlan(
            symbol=symbol,
            side=side,
            total_size_usd=size_usd,
            strategy=strategy,
            chunks=chunks,
            estimated_slippage_bps=slippage_bps,
            estimated_cost_usd=size_usd * slippage_bps / 10000.0,
            urgency_score=signal_urgency,
            notes=self._explain(strategy, spread_bps, size_ratio, signal_urgency),
        )
        return plan

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _choose_strategy(
        self,
        urgency: float,
        spread_bps: float,
        size_usd: float,
        size_ratio: float,
        atr_pct: float,
    ) -> ExecutionStrategy:
        # Ordre trop gros → split ou TWAP
        if size_ratio > self.SPLIT_RATIO:
            if urgency > 0.7:
                return ExecutionStrategy.LIQUIDITY_SPLIT
            return ExecutionStrategy.TWAP

        # Signal urgent → taker immédiat
        if urgency > 0.8:
            return ExecutionStrategy.TAKER_IMMEDIATE

        # Spread faible et basse volatilité → maker pour économiser
        if spread_bps < 5.0 and atr_pct < 0.015:
            return ExecutionStrategy.MAKER_LIMIT

        # Taille élevée et patience possible → TWAP
        if size_usd > self.TWAP_MAX_SIZE_USD and urgency < 0.5:
            return ExecutionStrategy.TWAP

        return ExecutionStrategy.TAKER_IMMEDIATE

    def _build_chunks(
        self,
        strategy: ExecutionStrategy,
        size_usd: float,
        liquidity_depth_usd: float,
        urgency: float,
    ) -> list[ExecutionChunk]:
        if strategy == ExecutionStrategy.TAKER_IMMEDIATE:
            return [ExecutionChunk(size_usd=size_usd, delay_seconds=0, strategy=strategy)]

        if strategy == ExecutionStrategy.MAKER_LIMIT:
            return [ExecutionChunk(size_usd=size_usd, delay_seconds=0, strategy=strategy)]

        if strategy == ExecutionStrategy.TWAP:
            n_chunks = min(max(2, math.ceil(size_usd / 10_000)), 10)
            chunk_size = size_usd / n_chunks
            interval = max(30.0, (1.0 - urgency) * 300.0)
            return [
                ExecutionChunk(size_usd=chunk_size, delay_seconds=i * interval, strategy=strategy)
                for i in range(n_chunks)
            ]

        if strategy == ExecutionStrategy.LIQUIDITY_SPLIT:
            max_chunk = liquidity_depth_usd * self.SPLIT_RATIO
            n_chunks = max(2, math.ceil(size_usd / max_chunk))
            chunk_size = size_usd / n_chunks
            return [
                ExecutionChunk(size_usd=chunk_size, delay_seconds=i * 5.0, strategy=strategy)
                for i in range(n_chunks)
            ]

        return [ExecutionChunk(size_usd=size_usd, delay_seconds=0, strategy=ExecutionStrategy.TAKER_IMMEDIATE)]

    def _explain(self, strategy: ExecutionStrategy, spread_bps: float, size_ratio: float, urgency: float) -> str:
        if strategy == ExecutionStrategy.TWAP:
            return f"TWAP: ordre trop grand ({size_ratio:.1%} liquidité), découpé dans le temps"
        if strategy == ExecutionStrategy.MAKER_LIMIT:
            return f"Maker: spread faible ({spread_bps:.1f}bps), économise le crossing"
        if strategy == ExecutionStrategy.LIQUIDITY_SPLIT:
            return f"Split: taille élevée ({size_ratio:.1%} liquidité) + urgence {urgency:.1%}"
        return f"Taker immédiat: urgence {urgency:.1%}"
