from dataclasses import dataclass


@dataclass
class Signal:
    symbol: str
    direction: str  # "buy" or "sell"
    confidence: float  # 0.0 to 1.0
