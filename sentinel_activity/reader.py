"""Local read-only projection, fixed-watermark pagination; no HTTP route."""

from pathlib import Path

from sentinel_activity.canonical import LedgerError, pure_int, require
from sentinel_activity.contracts import identifier
from sentinel_activity.integrity import report
from sentinel_activity.store import ActivityStore

CURSOR_FIELDS = {"ledger_id", "watermark", "head_hash", "after", "filters"}


def read_page(root: Path, *, limit: int = 100, cursor: dict | None = None,
              quest_id: str | None = None, actor_id: str | None = None,
              correlation_id: str | None = None) -> dict:
    require(pure_int(limit, 1, 100), "CURSOR_INVALID")
    filters = {"quest_id": quest_id, "actor_id": actor_id, "correlation_id": correlation_id}
    require(all(v is None or identifier(v) for v in filters.values()), "CURSOR_INVALID")
    try:
        meta, events, _ = ActivityStore(root).snapshot()
    except LedgerError as exc:
        return {"status": exc.code, "events": None, "next_cursor": None,
                "completeness": "UNKNOWN", "authenticity": "NOT_PROVEN"}
    result = report(meta, events)
    if cursor is None:
        watermark = len(events)
        head = events[-1]["integrity"]["event_hash"] if events else "GENESIS"
        after = 0
    else:
        require(type(cursor) is dict and set(cursor) == CURSOR_FIELDS, "CURSOR_INVALID")
        require(cursor["ledger_id"] == meta["ledger_id"] and cursor["filters"] == filters, "CURSOR_INVALID")
        watermark, after, head = cursor["watermark"], cursor["after"], cursor["head_hash"]
        require(pure_int(watermark, 0, len(events)) and pure_int(after, 0, watermark), "CURSOR_INVALID")
        expected_head = events[watermark - 1]["integrity"]["event_hash"] if watermark else "GENESIS"
        require(head == expected_head, "CURSOR_INVALID")
    matches = [e for e in events if after < e["sequence"] <= watermark and
               all(value is None or e[key] == value for key, value in filters.items())]
    page = matches[:limit]
    next_cursor = None
    if len(matches) > limit:
        next_cursor = {"ledger_id": meta["ledger_id"], "watermark": watermark, "head_hash": head,
                       "after": page[-1]["sequence"], "filters": filters}
    result.update(events=page, next_cursor=next_cursor,
                  snapshot_watermark=watermark, snapshot_head_hash=head, filter_match_count=len(matches))
    return result
