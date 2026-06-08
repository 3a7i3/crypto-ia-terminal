from src.backtest.metrics import total_pnl, win_rate


class LiveGate:
    def __init__(self):
        self.min_trades = 50
        self.min_win_rate = 0.45

    def evaluate(self, trades: list) -> str:
        if len(trades) < self.min_trades:
            return "BLOCKED"
        if total_pnl(trades) < 0:
            return "BLOCKED"
        if win_rate(trades) < self.min_win_rate:
            return "BLOCKED"
        return "APPROVED"
