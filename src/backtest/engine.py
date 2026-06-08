import time

from src.analytics.regime_detector import RegimeDetector
from src.backtest.metrics import max_drawdown, total_pnl, win_rate
from src.domain.order import Order
from src.domain.trade_event import TradeEvent
from src.runtime.run_context import RunContext

_regime_detector = RegimeDetector()


class BacktestEngine:
    def __init__(
        self, agent, router, data_feed, portfolio, run_context: RunContext | None = None
    ):
        self.agent = agent
        self.router = router
        self.data_feed = data_feed
        self.portfolio = portfolio
        self.run_context = run_context
        self._trades: list[TradeEvent] = []
        self._equity_curve: list[float] = []

    def run(self) -> dict:
        self._trades = []
        self._equity_curve = []
        self.data_feed.reset()

        ctx = self.run_context or RunContext(strategy_id="unknown")
        pending_close: dict | None = None

        while True:
            candle = self.data_feed.next()

            if pending_close is not None and candle is not None:
                symbol = pending_close["symbol"]
                if symbol in self.portfolio.positions:
                    close_meta = {
                        "run_id": ctx.run_id,
                        "strategy_id": ctx.strategy_id,
                        "execution_mode": "backtest",
                    }
                    result = self.router.sim_engine.close_position(
                        symbol, candle["close"], metadata=close_meta
                    )
                    if result is not None:
                        self._trades.append(result)
                pending_close = None

            if candle is None:
                break

            ctx.market_state = {
                k: candle[k] for k in ("close", "volume") if k in candle
            }
            signal = self.agent.on_market(candle)

            if signal is not None:
                order_meta = {
                    "run_id": ctx.run_id,
                    "strategy_id": ctx.strategy_id,
                    "confidence": signal.confidence,
                    "market_state": dict(ctx.market_state),
                    "timestamp": time.time(),
                }
                order = Order(
                    symbol=signal.symbol,
                    side=signal.direction,
                    size=1.0,
                    metadata=order_meta,
                )
                self.router.execute(order, candle["close"])
                pending_close = {"symbol": signal.symbol}

            equity = self.portfolio.mark_to_market(
                {candle.get("symbol", "BTC"): candle["close"]}
            )
            self._equity_curve.append(equity)

        pnl = total_pnl(self._trades)
        wr = win_rate(self._trades)
        mdd = max_drawdown(self._equity_curve)

        all_candles = self.data_feed.candles
        regime_metrics = _regime_detector.metrics(all_candles)

        return {
            "run_id": ctx.run_id,
            "strategy_id": ctx.strategy_id,
            "regime": regime_metrics["regime"],
            "regime_atr": regime_metrics["atr_pct"],
            "regime_slope": regime_metrics["slope"],
            "total_trades": len(self._trades),
            "final_balance": self.portfolio.balance,
            "total_pnl": pnl,
            "win_rate": wr,
            "max_drawdown": mdd,
            "trades": self._trades,
        }
