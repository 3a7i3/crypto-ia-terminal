from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable

from market_data.liquidity_engine.config import LiquidityEngineConfig
from market_data.liquidity_engine.models import MarketEvent, TradeSizeLevel


@dataclass
class ClassifiedTrade:
    event: MarketEvent
    level: TradeSizeLevel
    threshold_large: float
    threshold_whale: float


class TradeFilter:
    def __init__(self, config: LiquidityEngineConfig) -> None:
        self._config = config
        self._history: dict[tuple[str, str], deque[float]] = defaultdict(
            lambda: deque(maxlen=5000)
        )

    def classify_trade(self, event: MarketEvent) -> ClassifiedTrade:
        key = (event.exchange.lower(), event.symbol.upper())
        self._history[key].append(event.notional_usd)

        large, whale = self._resolve_thresholds(event.exchange, event.symbol)
        if event.notional_usd >= whale:
            level = TradeSizeLevel.WHALE
        elif event.notional_usd >= large:
            level = TradeSizeLevel.LARGE
        else:
            level = TradeSizeLevel.NORMAL

        return ClassifiedTrade(
            event=event,
            level=level,
            threshold_large=large,
            threshold_whale=whale,
        )

    def _resolve_thresholds(self, exchange: str, symbol: str) -> tuple[float, float]:
        cfg = self._config.threshold_by_exchange_symbol
        ex = exchange.lower()
        sym = symbol.upper()

        large = self._config.large_trade_threshold_usd
        whale = self._config.whale_trade_threshold_usd

        if ex in cfg:
            if "*" in cfg[ex]:
                large = float(cfg[ex]["*"].get("large", large))
                whale = float(cfg[ex]["*"].get("whale", whale))
            if sym in cfg[ex]:
                large = float(cfg[ex][sym].get("large", large))
                whale = float(cfg[ex][sym].get("whale", whale))

        if self._config.dynamic_percentile is not None:
            dynamic = self._dynamic_threshold(ex, sym, self._config.dynamic_percentile)
            if dynamic is not None:
                large = max(large, dynamic)
                whale = max(whale, dynamic * 2.0)

        if whale < large:
            whale = large
        return large, whale

    def _dynamic_threshold(
        self, exchange: str, symbol: str, percentile: float
    ) -> float | None:
        values = list(self._history[(exchange, symbol)])
        if len(values) < self._config.dynamic_min_samples:
            return None
        return percentile_value(values, percentile)


def percentile_value(values: Iterable[float], percentile: float) -> float:
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return 0.0
    p = min(100.0, max(0.0, percentile)) / 100.0
    idx = int(math.ceil((len(ordered) - 1) * p))
    return ordered[idx]
