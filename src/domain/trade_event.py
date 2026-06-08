"""
src/domain/trade_event.py — Événement de trade canonique.

Source de vérité unique pour tout PnL dans le système.
Aucun module externe ne recalcule le PnL : il le lit depuis TradeEvent.

Invariants :
  - net_pnl_usd = gross_pnl_usd - fees_usd - slippage_usd  (propriété dérivée)
  - opened_at et closed_at doivent être timezone-aware UTC
  - Immuable (frozen=True) — aucun consommateur ne peut modifier l'événement

Champs de connaissance (fondateurs de la knowledge base) :
  - regime      : contexte marché au moment de l'exécution — enum strict
  - signal_score: pouvoir prédictif du moteur de scoring — float ou None
                  Le producteur définit l'échelle. Aucune borne imposée.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class MarketRegime(str, Enum):
    UNKNOWN = "unknown"
    TRENDING = "trending"
    SIDEWAYS = "sideways"
    VOLATILE = "volatile"


@dataclass(frozen=True)
class TradeEvent:
    # ── Identité ──────────────────────────────────────────────────────────────
    trade_id: str  # unique par trade — clé de jointure cross-système
    run_id: str  # lie le trade à une session d'exécution
    strategy_id: str  # stratégie qui a produit le signal
    symbol: str

    # ── Exécution ─────────────────────────────────────────────────────────────
    side: str  # "buy" | "sell"
    entry_price: float
    exit_price: float
    quantity: float
    execution_mode: str  # "backtest" | "paper" | "live"

    # ── Coût décomposé (traçable individuellement) ────────────────────────────
    gross_pnl_usd: float  # (exit - entry) * qty * side_sign
    fees_usd: float  # frais de courtage (entry + exit)
    slippage_usd: float  # coût de slippage (entry + exit)

    # ── Temporel — UTC obligatoire ────────────────────────────────────────────
    opened_at: datetime
    closed_at: datetime

    # ── Knowledge base — champs fondateurs ───────────────────────────────────
    regime: MarketRegime = MarketRegime.UNKNOWN
    signal_score: Optional[float] = None  # échelle définie par le producteur

    def __post_init__(self) -> None:
        for name, dt in (("opened_at", self.opened_at), ("closed_at", self.closed_at)):
            if dt.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware (UTC required)")
            if dt.utcoffset().total_seconds() != 0:
                raise ValueError(f"{name} must be UTC (got offset {dt.utcoffset()})")

    # ── Invariant PnL (propriété dérivée — ne peut pas être violé) ───────────

    @property
    def net_pnl_usd(self) -> float:
        """net = gross - fees - slippage. Toujours. Partout. Sans exception."""
        return self.gross_pnl_usd - self.fees_usd - self.slippage_usd

    @property
    def total_cost_usd(self) -> float:
        """Coût total de friction : fees + slippage."""
        return self.fees_usd + self.slippage_usd

    @property
    def hold_seconds(self) -> float:
        """Durée de détention en secondes."""
        return (self.closed_at - self.opened_at).total_seconds()
