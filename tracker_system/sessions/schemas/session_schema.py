from __future__ import annotations

SESSION_METADATA_SCHEMA = {
    "session_id": str,
    "start_time": str,
    "end_time": str,
    "duration_minutes": float,
    "git_commit": str,
    "mode": str,  # paper | live | backtest
    "market": str,
    "timeframe": str,
    "total_cycles": int,
    "system_version": str,
}

ALLOWED_MODES = {"paper", "live", "backtest"}
ALLOWED_REGIMES = {
    "trend",
    "momentum",
    "sideways",
    "range",
    "range_faible",
    "volatile",
    "unknown",
}
SYSTEM_VERSION = "V9.2"
