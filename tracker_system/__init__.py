"""tracker_system — structured trade tracking and analytics package.

Legacy flat modules remain in place for compatibility.
New code should prefer the structured subpackages:
core, engine, analytics, backtesting, storage, dashboard, config.
"""

from tracker_system.config.settings import (
	DASHBOARD_FILE,
	LOGS_DIR,
	OPEN_POSITIONS_FILE,
	OPTIMIZER_FILE,
	TRADES_LOG_FILE,
)

__all__ = [
	"LOGS_DIR",
	"TRADES_LOG_FILE",
	"OPEN_POSITIONS_FILE",
	"OPTIMIZER_FILE",
	"DASHBOARD_FILE",
]
