from src.domain.order import Order
from src.domain.position import Position


class ExecutionRouter:
    def __init__(self, sim_engine):
        self.sim_engine = sim_engine
        self.mode = "sim"

    def execute(self, order: Order, price: float) -> Position:
        return self.sim_engine.place_order(order, price)
