import uuid
from datetime import datetime, timezone

import pytest

from src.domain.trade_event import MarketRegime, TradeEvent
from src.risk.live_gate import LiveGate

_UTC = timezone.utc
_T0 = datetime(2025, 1, 1, tzinfo=_UTC)


def make_trades(n: int, pnl_per_trade: float, win_fraction: float) -> list[TradeEvent]:
    trades = []
    wins = int(n * win_fraction)
    for i in range(n):
        pnl = pnl_per_trade if i < wins else -pnl_per_trade
        trades.append(
            TradeEvent(
                trade_id=str(uuid.uuid4()),
                run_id="test-run",
                strategy_id="TEST",
                symbol="BTC",
                side="buy",
                entry_price=100.0,
                exit_price=100.0 + pnl,
                quantity=1.0,
                execution_mode="backtest",
                gross_pnl_usd=pnl,
                fees_usd=0.0,
                slippage_usd=0.0,
                opened_at=_T0,
                closed_at=_T0,
                regime=MarketRegime.SIDEWAYS,
                signal_score=None,
            )
        )
    return trades


def test_blocked_zero_trades():
    gate = LiveGate()
    assert gate.evaluate([]) == "BLOCKED"


def test_blocked_insufficient_trades():
    gate = LiveGate()
    trades = make_trades(n=10, pnl_per_trade=10.0, win_fraction=0.6)
    assert gate.evaluate(trades) == "BLOCKED"


def test_blocked_negative_pnl():
    gate = LiveGate()
    trades = make_trades(n=50, pnl_per_trade=10.0, win_fraction=0.3)
    assert gate.evaluate(trades) == "BLOCKED"


def test_blocked_low_win_rate():
    gate = LiveGate()
    # 20 wins of +100, 30 losses of -1 => total +1970, win_rate 0.40
    wins = make_trades(n=20, pnl_per_trade=100.0, win_fraction=1.0)
    losses = make_trades(n=30, pnl_per_trade=1.0, win_fraction=0.0)
    assert gate.evaluate(wins + losses) == "BLOCKED"


def test_approved():
    gate = LiveGate()
    trades = make_trades(n=50, pnl_per_trade=10.0, win_fraction=0.6)
    assert gate.evaluate(trades) == "APPROVED"


def test_exactly_min_trades_positive():
    gate = LiveGate()
    trades = make_trades(n=50, pnl_per_trade=5.0, win_fraction=0.5)
    assert gate.evaluate(trades) == "APPROVED"
