# backtest_launcher.py
class BacktestLauncher:
    def __init__(self, backtest_engine):
        self.backtest_engine = backtest_engine

    def run(self, strategy, data):
        """
        Simule un backtest : calcule le nombre de BUY et HOLD dans les signaux.
        Retourne un dict de métriques simples.
        """
        signals = strategy.build(data)
        n_buy = signals.count("BUY")
        n_hold = signals.count("HOLD")
        return {"n_buy": n_buy, "n_hold": n_hold, "total": len(signals)}
