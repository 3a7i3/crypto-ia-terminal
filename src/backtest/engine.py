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
        # A signal observed at close[i] may only mutate the simulated portfolio
        # at open[i+1].  There is deliberately no time-based pending_close:
        # lifecycle exits are caused by an opposite strategy signal, while an
        # open position that survives to the dataset boundary is liquidated at
        # the final observed close.
        pending_open: dict | None = None
        last_prices: dict[str, float] = {}

        def close_position(symbol: str, price: float) -> None:
            close_meta = {
                "run_id": ctx.run_id,
                "strategy_id": ctx.strategy_id,
                "execution_mode": "backtest",
            }
            result = self.router.sim_engine.close_position(
                symbol, price, metadata=close_meta
            )
            if result is not None:
                self._trades.append(result)

        while True:
            candle = self.data_feed.next()
            if candle is None:
                break

            symbol = candle.get("symbol", "BTC")
            last_prices[symbol] = candle["close"]

            if pending_open is not None:
                order = pending_open["order"]
                order_symbol = pending_open["symbol"]
                execution_px = candle.get("open", candle["close"])
                desired_side = "long" if order.side == "buy" else "short"
                existing = self.portfolio.positions.get(order_symbol)

                if existing is not None and existing.side != desired_side:
                    # Reversal: close the old position and open the new one at
                    # the same next-bar open.  Both actions use only information
                    # that was available after the preceding bar closed.
                    close_position(order_symbol, execution_px)
                    existing = None

                if existing is None:
                    self.router.execute(order, execution_px)

                # A same-side repeated signal is idempotent for this simple
                # one-position-per-symbol engine; it must never overwrite the
                # existing Position and reset its entry price.
                pending_open = None

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
                pending_open = {"symbol": signal.symbol, "order": order}

            equity = self.portfolio.mark_to_market({symbol: candle["close"]})
            self._equity_curve.append(equity)

        # Reports contain realized trades only.  A position still open at the
        # finite dataset boundary is therefore liquidated at the last observed
        # close for its own symbol.  No synthetic price is invented.
        for symbol in list(self.portfolio.positions):
            if symbol in last_prices:
                close_position(symbol, last_prices[symbol])

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
