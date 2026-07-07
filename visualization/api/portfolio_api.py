"""Portfolio API — snapshot-only mapping from SystemSnapshot."""
from __future__ import annotations

from datetime import datetime, timezone

from visualization.api.models import PortfolioSnapshot
from visualization.api.system_snapshot_source import (
    load_system_snapshot_dict,
    load_system_snapshot_meta,
    parse_iso_dt,
)


def load_portfolio_snapshot() -> PortfolioSnapshot:
    snap = load_system_snapshot_dict()
    meta = load_system_snapshot_meta()
    ts = parse_iso_dt(meta.get("timestamp_utc")) or datetime.now(timezone.utc)
    portfolio = snap.get("portfolio", {})

    return PortfolioSnapshot(
        ts=ts,
        n_trades=0,
        n_wins=0,
        n_losses=0,
        win_rate_pct=0.0,
        profit_factor=0.0,
        expectancy_pct=0.0,
        max_drawdown_pct=0.0,
        sharpe=0.0,
        total_pnl_usd=float(portfolio.get("open_pnl_usd", 0.0) or 0.0),
        avg_pnl_usd=0.0,
        avg_duration_h=0.0,
        capital_usd=float(portfolio.get("paper_equity", 0.0) or 0.0),
        trade_history=[],
    )
