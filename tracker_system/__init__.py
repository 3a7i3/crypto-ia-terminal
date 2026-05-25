"""tracker_system — unified trade tracking and analytics package.

Public API (prefer these over deep subpackage imports):
  Trade lifecycle  : open_position, close_position, finalize_position
  Metrics          : compute_all_metrics
  Backtesting      : run_backtest
  Engine           : ExitEngine, build_exit_engine
"""

from tracker_system.analytics.metrics import compute_all_metrics
from tracker_system.backtesting.auto_backtester import run_backtest
from tracker_system.config.settings import (
    DASHBOARD_FILE,
    LOGS_DIR,
    OPEN_POSITIONS_FILE,
    OPTIMIZER_FILE,
    TRADES_LOG_FILE,
)
from tracker_system.core.trade_tracker import (
    close_position,
    finalize_position,
    open_position,
    update_positions,
)
from tracker_system.engine.exit_engine import ExitEngine
from tracker_system.engine.exit_factory import build_exit_engine

__all__ = [
    # Config
    "LOGS_DIR",
    "TRADES_LOG_FILE",
    "OPEN_POSITIONS_FILE",
    "OPTIMIZER_FILE",
    "DASHBOARD_FILE",
    # Trade lifecycle
    "open_position",
    "close_position",
    "finalize_position",
    "update_positions",
    # Analytics
    "compute_all_metrics",
    # Backtesting
    "run_backtest",
    # Engine
    "ExitEngine",
    "build_exit_engine",
]
