from src.domain.order import Order
from src.domain.position import Position
from src.domain.signal import Signal


class Simulator:
    def __init__(self, router, portfolio):
        self.router = router
        self.portfolio = portfolio
        self.trades_log: list[dict] = []

    def step(self, signal: Signal, price: float) -> Position | None:
        if signal.confidence < 0.6:
            return None

        symbol = signal.symbol

        # Close existing position if direction reversed
        if symbol in self.portfolio.positions:
            existing = self.portfolio.positions[symbol]
            current_side = "long" if signal.direction == "buy" else "short"
            if existing.side != current_side:
                result = self.router.sim_engine.close_position(symbol, price)
                if result is not None:
                    self.trades_log.append(result)

        order = Order(symbol=symbol, side=signal.direction, size=1.0)
        position = self.router.execute(order, price)
        return position
