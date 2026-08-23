from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from market_data.liquidity_engine.config import LiquidityEngineConfig
from market_data.liquidity_engine.filters.trade_filter import ClassifiedTrade
from market_data.liquidity_engine.models import (
    LiquidityPocket,
    MarketEvent,
    TradeSizeLevel,
    WindowAggregation,
)


class LiquidityAggregator:
    def __init__(self, config: LiquidityEngineConfig) -> None:
        self._config = config
        self._windows = sorted(set(config.aggregation_windows))
        self._trades: dict[tuple[str, str], deque[ClassifiedTrade]] = defaultdict(deque)
        self._book_state: dict[tuple[str, str], dict] = {}
        self._pockets: dict[tuple[str, str, str, float], LiquidityPocket] = {}

    def ingest_trade(self, trade: ClassifiedTrade) -> None:
        key = (trade.event.exchange.lower(), trade.event.symbol.upper())
        self._trades[key].append(trade)
        self._evict_old_trades(key, now=trade.event.timestamp_received)
        self._update_pocket(trade.event)

    def ingest_orderbook(self, event: MarketEvent, bids: list, asks: list) -> None:
        key = (event.exchange.lower(), event.symbol.upper())
        self._book_state[key] = {
            "timestamp": event.timestamp_received,
            "bids": bids,
            "asks": asks,
        }

    def snapshot(self, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        results = []
        for key in list(self._trades.keys()):
            self._evict_old_trades(key, now)
            for window_s in self._windows:
                agg = self._build_window(key, window_s, now)
                if agg:
                    results.append(asdict(agg))
        pockets = [asdict(p) for p in self._active_pockets(now)]
        return {"windows": results, "pockets": pockets}

    def _evict_old_trades(self, key: tuple[str, str], now: datetime) -> None:
        keep_s = max(self._windows, default=60)
        cutoff = now - timedelta(seconds=keep_s)
        bucket = self._trades[key]
        while bucket and bucket[0].event.timestamp_received < cutoff:
            bucket.popleft()

    def _build_window(
        self, key: tuple[str, str], window_s: int, now: datetime
    ) -> WindowAggregation | None:
        exchange, symbol = key
        start = now - timedelta(seconds=window_s)
        trades = [
            t
            for t in self._trades.get(key, [])
            if t.event.timestamp_received >= start
        ]
        if not trades:
            return None

        buy = [t for t in trades if t.event.side == "BUY"]
        sell = [t for t in trades if t.event.side == "SELL"]
        total_volume = sum(t.event.quantity for t in trades)
        total_notional = sum(t.event.notional_usd for t in trades)
        buy_volume = sum(t.event.quantity for t in buy)
        sell_volume = sum(t.event.quantity for t in sell)
        buy_notional = sum(t.event.notional_usd for t in buy)
        sell_notional = sum(t.event.notional_usd for t in sell)

        large_count = sum(1 for t in trades if t.level == TradeSizeLevel.LARGE)
        whale_count = sum(1 for t in trades if t.level == TradeSizeLevel.WHALE)
        largest_trade = max(t.event.notional_usd for t in trades)
        avg_trade_size = total_notional / max(len(trades), 1)
        delta = buy_volume - sell_volume
        ratio = buy_volume / sell_volume if sell_volume > 0 else float("inf")

        bid_liq = ask_liq = spread = imbalance = 0.0
        depth: dict[str, float] = {}
        book = self._book_state.get(key)
        if book:
            bids = book.get("bids", [])
            asks = book.get("asks", [])
            bid_liq = sum(float(p) * float(q) for p, q in bids)
            ask_liq = sum(float(p) * float(q) for p, q in asks)
            denom = bid_liq + ask_liq
            imbalance = (bid_liq - ask_liq) / denom if denom > 0 else 0.0
            if bids and asks:
                spread = float(asks[0][0]) - float(bids[0][0])
            for lvl in (1, 3, 5, 10):
                depth[f"bid_depth_{lvl}"] = sum(
                    float(p) * float(q) for p, q in bids[:lvl]
                )
                depth[f"ask_depth_{lvl}"] = sum(
                    float(p) * float(q) for p, q in asks[:lvl]
                )

        return WindowAggregation(
            exchange=exchange,
            symbol=symbol,
            window_s=window_s,
            timestamp=now,
            total_volume=total_volume,
            total_notional=total_notional,
            buy_volume=buy_volume,
            sell_volume=sell_volume,
            buy_notional=buy_notional,
            sell_notional=sell_notional,
            large_trade_count=large_count,
            whale_trade_count=whale_count,
            largest_trade=largest_trade,
            average_trade_size=avg_trade_size,
            volume_delta=delta,
            buy_sell_ratio=ratio,
            bid_liquidity=bid_liq,
            ask_liquidity=ask_liq,
            bid_ask_imbalance=imbalance,
            spread=spread,
            depth_by_level=depth,
        )

    def _update_pocket(self, event: MarketEvent) -> None:
        if self._config.price_bucket_size <= 0:
            return
        bucket = round(event.price / self._config.price_bucket_size) * self._config.price_bucket_size
        key = (event.exchange.lower(), event.symbol.upper(), event.side, bucket)
        current = self._pockets.get(key)
        if current is None:
            self._pockets[key] = LiquidityPocket(
                exchange=event.exchange.lower(),
                symbol=event.symbol.upper(),
                price_level=bucket,
                volume=event.quantity,
                notional=event.notional_usd,
                side=event.side,
                first_seen=event.timestamp_received,
                last_seen=event.timestamp_received,
                event_count=1,
            )
            return
        current.volume += event.quantity
        current.notional += event.notional_usd
        current.last_seen = event.timestamp_received
        current.event_count += 1

    def _active_pockets(self, now: datetime) -> list[LiquidityPocket]:
        ttl = timedelta(seconds=self._config.pocket_time_window_s)
        min_notional = self._config.min_cluster_notional
        min_events = self._config.min_cluster_events
        valid = []
        for key, pocket in list(self._pockets.items()):
            if now - pocket.last_seen > ttl:
                del self._pockets[key]
                continue
            if pocket.notional >= min_notional and pocket.event_count >= min_events:
                valid.append(pocket)
        return sorted(valid, key=lambda p: p.notional, reverse=True)
