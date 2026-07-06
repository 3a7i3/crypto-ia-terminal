"""Portfolio API — loads PortfolioSnapshot from burnin_v3.json + paper_trades.jsonl."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from visualization.api.models import PortfolioSnapshot

_ROOT = Path(__file__).resolve().parents[2]
_BURNIN = _ROOT / "cache" / "burn_in_reports" / "burnin_v3.json"
_PAPER_TRADES = _ROOT / "databases" / "paper_trades.jsonl"
_LIVE_SNAPSHOT = _ROOT / "databases" / "live_snapshot.json"


def _load_closed_trades() -> list[dict]:
    if not _PAPER_TRADES.exists():
        return []
    trades = []
    with _PAPER_TRADES.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("event") == "CLOSE" and obj.get("pnl_usd") is not None:
                    trades.append(obj)
            except Exception:
                continue
    return trades


def load_portfolio_snapshot() -> PortfolioSnapshot:
    burnin: dict = {}
    if _BURNIN.exists():
        burnin = json.loads(_BURNIN.read_text(encoding="utf-8"))

    capital_usd = 1000.0
    if _LIVE_SNAPSHOT.exists():
        live = json.loads(_LIVE_SNAPSHOT.read_text(encoding="utf-8"))
        capital_usd = live.get("capital", 1000.0)

    trades_data = burnin.get("trades", {})
    history = _load_closed_trades()

    return PortfolioSnapshot(
        ts=datetime.now(timezone.utc),
        n_trades=trades_data.get("count", len(history)),
        n_wins=trades_data.get("wins", 0),
        n_losses=trades_data.get("losses", 0),
        win_rate_pct=trades_data.get("win_rate_pct", 0.0),
        profit_factor=trades_data.get("profit_factor", 0.0),
        expectancy_pct=trades_data.get("expectancy_pct", 0.0),
        max_drawdown_pct=trades_data.get("max_drawdown_pct", 0.0),
        sharpe=trades_data.get("sharpe", 0.0),
        total_pnl_usd=trades_data.get("total_pnl_usd", 0.0),
        avg_pnl_usd=trades_data.get("avg_pnl_usd", 0.0),
        avg_duration_h=trades_data.get("avg_duration_h", 0.0),
        capital_usd=capital_usd,
        trade_history=history[-50:],  # Last 50 closed trades for charts
    )
