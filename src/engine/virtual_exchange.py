import uuid
from datetime import datetime, timezone

from src.domain.order import Order
from src.domain.position import Position
from src.domain.trade_event import MarketRegime, TradeEvent

_EPOCH_UTC = datetime.fromtimestamp(0, tz=timezone.utc)


class VirtualExchange:
    def __init__(self, portfolio, event_bus=None):
        self.portfolio = portfolio
        self._bus = event_bus

    def place_order(self, order: Order, price: float) -> Position:
        side = "long" if order.side == "buy" else "short"
        position = Position(
            symbol=order.symbol,
            size=order.size,
            entry_price=price,
            side=side,
            opened_at=datetime.now(timezone.utc),
        )
        self.portfolio.positions[order.symbol] = position

        if self._bus:
            self._bus.emit(
                {
                    "type": "TRADE_OPENED",
                    "symbol": order.symbol,
                    "side": side,
                    "price": price,
                    "size": order.size,
                    **order.metadata,
                }
            )

        return position

    def close_position(
        self,
        symbol: str,
        price: float,
        metadata: dict | None = None,
        fees_usd: float = 0.0,
        slippage_usd: float = 0.0,
    ) -> TradeEvent | None:
        position = self.portfolio.positions.pop(symbol, None)
        if position is None:
            return None

        m = metadata or {}

        if position.side == "long":
            gross_pnl = (price - position.entry_price) * position.size
            entry_side = "buy"
        else:
            gross_pnl = (position.entry_price - price) * position.size
            entry_side = "sell"

        self.portfolio.balance += gross_pnl

        trade = TradeEvent(
            trade_id=str(uuid.uuid4()),
            run_id=m.get("run_id", ""),
            strategy_id=m.get("strategy_id", ""),
            symbol=symbol,
            side=entry_side,
            entry_price=position.entry_price,
            exit_price=price,
            quantity=position.size,
            execution_mode=m.get("execution_mode", "backtest"),
            gross_pnl_usd=gross_pnl,
            fees_usd=fees_usd,
            slippage_usd=slippage_usd,
            opened_at=position.opened_at or _EPOCH_UTC,
            closed_at=datetime.now(timezone.utc),
            regime=(
                MarketRegime(m["regime"])
                if m.get("regime") in {e.value for e in MarketRegime}
                else MarketRegime.UNKNOWN
            ),
            signal_score=m.get("signal_score"),
        )

        if self._bus:
            self._bus.emit(
                {
                    "type": "TRADE_CLOSED",
                    "symbol": symbol,
                    "pnl": gross_pnl,
                    "closed": True,
                    "exit_price": price,
                    "trade_event": trade,  # B2: SSoT économique dans le bus
                    **(m),
                }
            )

        return trade
