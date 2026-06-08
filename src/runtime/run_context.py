import time
import uuid
from dataclasses import dataclass, field


@dataclass
class RunContext:
    strategy_id: str
    market_state: dict = field(default_factory=dict)
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "strategy_id": self.strategy_id,
            "market_state": self.market_state,
            "timestamp": self.timestamp,
        }
