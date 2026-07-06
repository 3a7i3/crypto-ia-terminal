"""Health API — snapshot-only mapping from SystemSnapshot."""
from __future__ import annotations

from datetime import datetime, timezone

from visualization.api.models import HealthSnapshot
from visualization.api.system_snapshot_source import (
    load_system_snapshot_dict,
    load_system_snapshot_meta,
    parse_iso_dt,
)


def _bool_score(values: list[bool]) -> float:
    if not values:
        return 0.0
    return round(sum(1 for v in values if v) / len(values) * 100.0, 1)


def load_health_snapshot() -> HealthSnapshot:
    snap = load_system_snapshot_dict()
    meta = load_system_snapshot_meta()
    ts = parse_iso_dt(meta.get("timestamp_utc")) or datetime.now(timezone.utc)

    health = snap.get("health", {})
    portfolio = snap.get("portfolio", {})
    decision = snap.get("ai_decision", {})
    market = snap.get("market", {})
    block_stats = snap.get("block_stats", {})

    observer_pct = _bool_score(
        [
            bool(health.get("api", False)),
            bool(health.get("database", False)),
            bool(health.get("telegram", False)),
        ]
    )
    dataset_pct = 100.0 if bool(health.get("market", False)) else 0.0
    knowledge_pct = float(decision.get("brain_score_pct", 0.0) or 0.0)

    session_counts = dict(block_stats.get("session", []))
    observed_events = sum(int(v) for v in session_counts.values())
    evidence_pct = float(min(observed_events, 100))

    capital_usd = float(portfolio.get("paper_equity", 0.0) or 0.0)
    capital_pct = 100.0 if capital_usd > 0 else 0.0
    drift_pct = round(float(market.get("exchange_uptime_pct", 0.0) or 0.0), 1)

    reason_code = decision.get("reason_code")
    reason_text = decision.get("reason_text")
    top_root_cause = reason_code or reason_text or None

    return HealthSnapshot(
        ts=ts,
        observer_pct=observer_pct,
        dataset_pct=dataset_pct,
        knowledge_pct=knowledge_pct,
        evidence_pct=evidence_pct,
        capital_pct=capital_pct,
        drift_pct=drift_pct,
        system_state="NORMAL" if bool(health.get("strategy", False)) else "DEGRADED",
        trading_enabled=(decision.get("state") == "ACTIVE"),
        capital_usd=round(capital_usd, 4),
        n_trades=0,
        win_rate_pct=0.0,
        profit_factor=0.0,
        last_heartbeat_at=ts,
        heartbeat_age_seconds=max((datetime.now(timezone.utc) - ts).total_seconds(), 0.0),
        top_root_cause=top_root_cause,
        top_root_cause_pct=None,
    )
