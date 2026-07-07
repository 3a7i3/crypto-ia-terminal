"""Pipeline API — snapshot-only mapping from SystemSnapshot."""
from __future__ import annotations

from datetime import datetime, timezone

from visualization.api.models import PipelineSnapshot
from visualization.api.system_snapshot_source import (
    load_system_snapshot_dict,
    load_system_snapshot_meta,
    parse_iso_dt,
)


def load_pipeline_snapshot() -> PipelineSnapshot:
    snap = load_system_snapshot_dict()
    meta = load_system_snapshot_meta()
    ts = parse_iso_dt(meta.get("timestamp_utc")) or datetime.now(timezone.utc)

    block_stats = snap.get("block_stats", {})
    cycle_counts = {
        str(k): int(v) for k, v in dict(block_stats.get("current_cycle", [])).items()
    }
    n_refused = sum(cycle_counts.values())

    decision = snap.get("ai_decision", {})
    n_traded = 1 if decision.get("state") == "ACTIVE" else 0
    n_signals = n_refused + n_traded

    market = snap.get("market", {})
    regime = str(market.get("regime", "unknown") or "unknown")
    regime_distribution = {regime: n_signals} if n_signals > 0 else {}
    portfolio = snap.get("portfolio", {})

    return PipelineSnapshot(
        ts=ts,
        n_signals=n_signals,
        n_traded=n_traded,
        n_refused=n_refused,
        refusal_breakdown=cycle_counts,
        regime_distribution=regime_distribution,
        capital_usd=float(portfolio.get("paper_equity", 0.0) or 0.0),
        cycle=int(meta.get("cycle", 0) or 0),
    )
