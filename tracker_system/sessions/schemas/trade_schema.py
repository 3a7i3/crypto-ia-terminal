from __future__ import annotations

REQUIRED_TRADE_FIELDS = [
    "timestamp",
    "symbol",
    "side",
    "entry_price",
    "exit_price",
    "pnl_usd",
    "pnl_pct",
    "regime",
    "score",
]

OPTIONAL_TRADE_FIELDS = [
    "size",
    "fee_usd",
    "r_multiple",
    "decision_id",
    "drawdown",
    "mfe_pct",
    "mae_pct",
    "quality",  # VALIDATED / LUCKY / UNLUCKY / MISTAKE
]

MAX_POSITION_SIZE_USD = 100_000.0
PNL_COHERENCE_TOLERANCE = 0.05  # 5% tolerance for pnl recalculation
