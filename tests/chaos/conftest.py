"""Shared fixtures for all chaos tests."""

from __future__ import annotations

import pytest

from quant_hedge_ai.agents.execution.order_deduplicator import OrderDeduplicator
from quant_hedge_ai.agents.execution.paper_trading_engine import PaperTradingEngine
from quant_hedge_ai.agents.execution.position_manager import (
    Position,
    PositionManager,
    PositionSide,
)


@pytest.fixture
def dedup() -> OrderDeduplicator:
    return OrderDeduplicator(window_seconds=30.0)


@pytest.fixture
def paper_engine() -> PaperTradingEngine:
    return PaperTradingEngine(initial_balance=100_000.0, persist=False)


@pytest.fixture
def position_manager() -> PositionManager:
    return PositionManager(exchange=None, paper_mode=True)


def make_long(
    symbol: str = "BTC/USDT",
    entry: float = 50_000.0,
    qty: float = 0.1,
) -> Position:
    return Position(
        symbol=symbol,
        side=PositionSide.LONG,
        entry_price=entry,
        size_usd=qty * entry,
        qty=qty,
        use_atr=False,
        tp_pct=0.04,
        sl_pct=0.02,
    )
