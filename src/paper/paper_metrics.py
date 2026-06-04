from dataclasses import dataclass, field
from typing import List


@dataclass
class PaperMetrics:
    initial_equity: float = 10_000.0
    equity: float = 10_000.0
    peak_equity: float = 10_000.0
    trades: List[float] = field(default_factory=list)
    enl_costs: List[float] = field(default_factory=list)
    hold_times: List[float] = field(default_factory=list)
    signal_count: int = 0

    def record_trade(
        self, pnl_net: float, enl_cost: float, hold_seconds: float
    ) -> None:
        self.trades.append(pnl_net)
        self.enl_costs.append(enl_cost)
        self.hold_times.append(hold_seconds)
        self.equity += pnl_net
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return sum(1 for t in self.trades if t > 0) / len(self.trades)

    @property
    def profit_factor(self) -> float:
        gross_win = sum(t for t in self.trades if t > 0)
        gross_loss = abs(sum(t for t in self.trades if t < 0))
        if gross_loss == 0:
            return float("inf") if gross_win > 0 else 0.0
        return gross_win / gross_loss

    @property
    def expectancy(self) -> float:
        return sum(self.trades) / len(self.trades) if self.trades else 0.0

    @property
    def max_drawdown_pct(self) -> float:
        if self.peak_equity == 0:
            return 0.0
        return (self.peak_equity - self.equity) / self.peak_equity * 100

    @property
    def avg_hold_hours(self) -> float:
        return (
            sum(self.hold_times) / len(self.hold_times) / 3600
            if self.hold_times
            else 0.0
        )

    @property
    def median_trade(self) -> float:
        if not self.trades:
            return 0.0
        s = sorted(self.trades)
        return s[len(s) // 2]

    @property
    def avg_enl_cost(self) -> float:
        return sum(self.enl_costs) / len(self.enl_costs) if self.enl_costs else 0.0

    def to_dict(self) -> dict:
        return {
            "initial_equity": self.initial_equity,
            "equity": self.equity,
            "peak_equity": self.peak_equity,
            "trades": list(self.trades),
            "enl_costs": list(self.enl_costs),
            "hold_times": list(self.hold_times),
            "signal_count": self.signal_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PaperMetrics":
        m = cls(
            initial_equity=data["initial_equity"],
            equity=data["equity"],
            peak_equity=data["peak_equity"],
        )
        m.trades = list(data.get("trades", []))
        m.enl_costs = list(data.get("enl_costs", []))
        m.hold_times = list(data.get("hold_times", []))
        m.signal_count = data.get("signal_count", 0)
        return m

    def summary(self) -> dict:
        return {
            "equity": round(self.equity, 2),
            "signal_count": self.signal_count,
            "trade_count": self.trade_count,
            "win_rate_pct": round(self.win_rate * 100, 1),
            "profit_factor": round(self.profit_factor, 3),
            "expectancy": round(self.expectancy, 2),
            "avg_trade": round(self.expectancy, 2),
            "median_trade": round(self.median_trade, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "avg_hold_hours": round(self.avg_hold_hours, 1),
            "avg_enl_cost": round(self.avg_enl_cost, 4),
        }
