"""Timeline API — assembles TimelineSnapshot from decision_packets_*.jsonl files."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from visualization.api.models import TimelineEvent, TimelineSnapshot

_ROOT = Path(__file__).resolve().parents[2]
_DB = _ROOT / "databases"
_MAX_EVENTS = 100


def _parse_dt(s: str | None) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def _primary_reason(reasoning: list) -> str:
    if not reasoning:
        return ""
    msg = reasoning[0].get("message", "") if isinstance(reasoning[0], dict) else ""
    return msg[:120]


def _load_all_packets() -> list[dict]:
    files = sorted(_DB.glob("decision_packets_*.jsonl"), reverse=True)
    packets: list[dict] = []
    for f in files:
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    packets.append(json.loads(line))
        except Exception:
            continue
        if len(packets) >= _MAX_EVENTS * 3:
            break
    return packets


def load_timeline_snapshot() -> TimelineSnapshot:
    raw = _load_all_packets()

    total = len(raw)
    n_trade = sum(1 for p in raw if p.get("event_category") == "TRADE")
    n_system = sum(1 for p in raw if p.get("event_category") == "SYSTEM")
    n_rejected = sum(1 for p in raw if p.get("lifecycle_state") == "REJECTED")
    n_executed = sum(
        1
        for p in raw
        if p.get("lifecycle_state") in ("EXECUTED", "EXECUTION_PENDING", "CLOSED")
    )

    # Keep TRADE packets first, then SIGNAL_GENERATED, then others — skip SYSTEM noise
    priority_order = {"TRADE": 0, "SIGNAL": 1, "EXECUTION_PENDING": 2}

    def sort_key(p: dict):
        cat = p.get("event_category", "")
        state = p.get("lifecycle_state", "")
        prio = 0 if cat == "TRADE" else (1 if state == "SIGNAL_GENERATED" else 2)
        return (prio, p.get("created_at", ""))

    candidates = [p for p in raw if p.get("event_category") != "SYSTEM"]
    if not candidates:
        candidates = raw

    candidates.sort(key=sort_key, reverse=True)

    events: list[TimelineEvent] = []
    for p in candidates[:_MAX_EVENTS]:
        events.append(
            TimelineEvent(
                packet_id=p.get("packet_id", "")[:8],
                ts=_parse_dt(p.get("created_at")),
                symbol=p.get("symbol", "?"),
                event_category=p.get("event_category") or "UNKNOWN",
                lifecycle_state=p.get("lifecycle_state", "?"),
                regime=p.get("regime") or "unknown",
                conviction=p.get("conviction") or "SKIP",
                reason=_primary_reason(p.get("reasoning", [])),
            )
        )

    return TimelineSnapshot(
        ts=datetime.now(timezone.utc),
        events=events,
        total_packets=total,
        n_trade=n_trade,
        n_system=n_system,
        n_rejected=n_rejected,
        n_executed=n_executed,
    )
