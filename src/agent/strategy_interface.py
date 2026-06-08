from src.domain.signal import Signal


class StrategyInterface:
    def generate_signal(self, market_data: dict) -> "Signal | None":
        raise NotImplementedError
