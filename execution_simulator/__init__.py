"""execution_simulator — Simulation realiste d'execution d'ordres."""

from execution_simulator.config import (
    binance_spot_simulator,
    binance_usdt_futures_simulator,
    conservative_simulator,
)
from execution_simulator.models import MarketSnapshot, OrderIntent, SimulatedFill
from execution_simulator.simulator import ExecutionSimulator, FeeModel

__all__ = [
    "OrderIntent",
    "MarketSnapshot",
    "SimulatedFill",
    "ExecutionSimulator",
    "FeeModel",
    "binance_usdt_futures_simulator",
    "binance_spot_simulator",
    "conservative_simulator",
]
