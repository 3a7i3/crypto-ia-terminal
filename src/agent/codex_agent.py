from src.agent.strategy_interface import StrategyInterface
from src.domain.signal import Signal
from src.risk.kill_switch import KillSwitch


class CodexAgent:
    def __init__(self, strategy: StrategyInterface, kill_switch: KillSwitch):
        self.strategy = strategy
        self.kill_switch = kill_switch

    def on_market(self, market_data: dict) -> "Signal | None":
        if self.kill_switch.engaged:
            return None
        signal = self.strategy.generate_signal(market_data)
        if signal is None:
            return None
        if signal.confidence < 0.6:
            return None
        return signal
