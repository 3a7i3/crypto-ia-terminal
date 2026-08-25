"""
trade_analysis/liquidity_tracker.py — Suivi de la dynamique de liquidite.

Repond a la question :
  "Ce qui disparait du book a-t-il ete consomme ou retire ?"

Observe :
  - Liquidite ajoutee vs retiree entre deux snapshots
  - Distinction retiree (annulee) vs consommee (executee)
  - Taux d'annulation par cote
  - Variation nette de liquidite

La distinction retiree/consommee est l'un des signaux les plus riches :
  - Retiree sans execution = potentiel spoofing ou perte de confiance
  - Consommee = vraie absorption de pression adverse

Strictement passif (ADR-0007).
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from market_data.models import NormalizedOrderBook, NormalizedTrade
from trade_analysis.models import LiquidityDynamics


class LiquidityTracker:
    """
    Compare les snapshots successifs du book pour mesurer
    les flux de liquidite.

    Le tracker utilise les trades recents pour distinguer
    la liquidite consommee (matched par un trade agressif) de la
    liquidite retiree (annulee par le maker).

    Usage :
        tracker = LiquidityTracker()
        # Feed trades as they arrive
        tracker.on_trade(trade)
        # Feed book snapshots periodically
        dynamics = tracker.on_book(book_snapshot)
    """

    def __init__(
        self,
        levels: int = 20,
        trade_window_ms: int = 5_000,
    ) -> None:
        self.levels = levels
        self.trade_window_ms = trade_window_ms
        self._prev_book: Optional[NormalizedOrderBook] = None
        self._recent_trades: deque[NormalizedTrade] = deque()

    def on_trade(self, trade: NormalizedTrade) -> None:
        self._recent_trades.append(trade)
        cutoff = trade.timestamp_ms - self.trade_window_ms
        while self._recent_trades and self._recent_trades[0].timestamp_ms < cutoff:
            self._recent_trades.popleft()

    def on_book(self, book: NormalizedOrderBook) -> Optional[LiquidityDynamics]:
        if self._prev_book is None:
            self._prev_book = book
            return None

        prev_bids = dict(self._prev_book.bids[: self.levels])
        prev_asks = dict(self._prev_book.asks[: self.levels])
        curr_bids = dict(book.bids[: self.levels])
        curr_asks = dict(book.asks[: self.levels])

        bid_added, bid_removed = self._diff_side(prev_bids, curr_bids)
        ask_added, ask_removed = self._diff_side(prev_asks, curr_asks)

        bid_consumed = 0.0
        ask_consumed = 0.0
        for t in self._recent_trades:
            val = t.price * t.size
            if t.side == "buy":
                ask_consumed += val
            else:
                bid_consumed += val

        bid_removed_net = max(0.0, bid_removed - bid_consumed)
        ask_removed_net = max(0.0, ask_removed - ask_consumed)

        canc_bid = (
            bid_removed_net / (bid_removed_net + bid_consumed)
            if (bid_removed_net + bid_consumed) > 0
            else 0.0
        )
        canc_ask = (
            ask_removed_net / (ask_removed_net + ask_consumed)
            if (ask_removed_net + ask_consumed) > 0
            else 0.0
        )

        net_change = (bid_added + ask_added) - (bid_removed + ask_removed)

        self._prev_book = book

        return LiquidityDynamics(
            timestamp_ms=book.timestamp_ms,
            bid_added_usd=bid_added,
            bid_removed_usd=bid_removed_net,
            ask_added_usd=ask_added,
            ask_removed_usd=ask_removed_net,
            bid_consumed_usd=bid_consumed,
            ask_consumed_usd=ask_consumed,
            cancellation_rate_bid=canc_bid,
            cancellation_rate_ask=canc_ask,
            net_liquidity_change_usd=net_change,
        )

    def _diff_side(
        self,
        prev: dict[float, float],
        curr: dict[float, float],
    ) -> tuple[float, float]:
        added = 0.0
        removed = 0.0
        all_prices = set(prev.keys()) | set(curr.keys())
        for price in all_prices:
            prev_size = prev.get(price, 0.0)
            curr_size = curr.get(price, 0.0)
            prev_usd = price * prev_size
            curr_usd = price * curr_size
            diff = curr_usd - prev_usd
            if diff > 0:
                added += diff
            elif diff < 0:
                removed += abs(diff)
        return added, removed
