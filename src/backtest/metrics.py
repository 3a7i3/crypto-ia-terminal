import math

from src.domain.trade_event import TradeEvent


def win_rate(trades: list[TradeEvent]) -> float:
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.net_pnl_usd > 0)
    return wins / len(trades)


def total_pnl(trades: list[TradeEvent]) -> float:
    return float(sum(t.net_pnl_usd for t in trades))


def max_drawdown(equity_curve: list) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        dd = (peak - value) / peak if peak != 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd


def sharpe_ratio(returns: list, rfr: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    n = len(returns)
    mean = sum(returns) / n - rfr
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(variance) if variance > 0 else 0.0
    return mean / std if std != 0 else 0.0
