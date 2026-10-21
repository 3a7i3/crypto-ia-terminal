"""J02 feed projection over read_page; presentation only, never an authority.

Every item is a verified J01 event re-shaped for display. Current display
rules (governance_tower.redaction) may conceal text that the frozen J01
profile admitted; the hashed event bytes and their integrity verdict are
unchanged. Status codes are passed through: an unreadable journal is never an
empty feed, and NO_DATA is not "no agent activity". References are inert text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from governance_tower.redaction import redact as display_redact
from sentinel_activity.canonical import LedgerError, canonical_bytes, strict_loads
from sentinel_activity.reader import read_page

FEED_VERSION = "sentinel-feed/0.1"
DISPLAY_RULES = "governance_tower.redaction/current"
MAX_TOKEN_CHARS = 2_048
_SUMMARY_FIELDS = ("status", "mode", "ledger_id", "event_count", "last_sequence", "head_hash",
                   "completeness", "authenticity", "anchor", "warnings", "snapshot_watermark",
                   "snapshot_head_hash", "filter_match_count")


def encode_cursor(cursor: dict | None) -> str | None:
    if cursor is None:
        return None
    return canonical_bytes(cursor, 1_024).hex()


def decode_cursor(token: Any) -> dict:
    """Opaque transport of read_page's structured cursor; read_page re-checks it."""
    if type(token) is not str or not 0 < len(token) <= MAX_TOKEN_CHARS:
        raise LedgerError("CURSOR_INVALID")
    if any(c not in "0123456789abcdef" for c in token) or len(token) % 2:
        raise LedgerError("CURSOR_INVALID")
    raw = bytes.fromhex(token)
    try:
        cursor = strict_loads(raw, 1_024)
    except LedgerError as exc:
        raise LedgerError("CURSOR_INVALID") from exc
    if type(cursor) is not dict or canonical_bytes(cursor, 1_024) != raw:
        raise LedgerError("CURSOR_INVALID")
    return cursor


def _display(value: Any, counter: list[int]) -> Any:
    if type(value) is str:
        text, count = display_redact(value)
        counter[0] += count
        return text
    if type(value) is list:
        return [_display(item, counter) for item in value]
    if type(value) is dict:
        return {key: _display(item, counter) for key, item in value.items()}
    return value


def _item(event: dict) -> dict:
    counter = [0]
    item = {
        "sequence": event["sequence"],
        "event_id": _display(event["event_id"], counter),
        "event_type": event["event_type"],
        "provenance": event["source_kind"],
        "recorded_at_utc": event["recorded_at_utc"],
        "occurred_at_utc": event["occurred_at_utc"],
        "occurred_at_status": "UNKNOWN" if event["occurred_at_utc"] is None else "DECLARED",
        "actor": _display({"id": event["actor_id"], "kind": event["actor_kind"],
                           "version": event["actor_version"]}, counter),
        "producer_id": _display(event["producer_id"], counter),
        "quest_id": _display(event["quest_id"], counter),
        "correlation_id": _display(event["correlation_id"], counter),
        "causation_event_id": _display(event["causation_event_id"], counter),
        "summary": _display(event["summary"], counter),
        "reason_declared": _display(event["reason_declared"], counter),
        "payload": _display(event["payload"], counter),
        "evidence_refs": _display(event["evidence_refs"], counter),
        "authorization_ref": _display(event["authorization_ref"], counter),
        "references_dereferenced": False,
        "event_hash": event["integrity"]["event_hash"],
        "previous_hash": event["integrity"]["previous_hash"],
    }
    item["display"] = {"rules": DISPLAY_RULES, "redactions": counter[0],
                       "hashed_event_unchanged": True}
    return item


def feed_page(root: Path, *, limit: int = 50, cursor_token: str | None = None,
              quest_id: str | None = None, actor_id: str | None = None,
              correlation_id: str | None = None) -> dict:
    """One verified page, newest-last order of the fixed snapshot.

    Errors are statuses, never exceptions or empty lists: items is None unless
    the whole stored journal was verified for this request.
    """
    base = {"feed_version": FEED_VERSION, "items": None, "next_cursor": None,
            "completeness": "UNKNOWN", "authenticity": "NOT_PROVEN", "page_limit": limit}
    try:
        cursor = None if cursor_token is None else decode_cursor(cursor_token)
        page = read_page(Path(root), limit=limit, cursor=cursor, quest_id=quest_id,
                         actor_id=actor_id, correlation_id=correlation_id)
    except LedgerError as exc:
        return {**base, "status": exc.code}
    if page.get("events") is None:
        return {**base, "status": page["status"]}
    result = {**base, **{key: page[key] for key in _SUMMARY_FIELDS}}
    result["items"] = [_item(event) for event in page["events"]]
    result["next_cursor"] = encode_cursor(page["next_cursor"])
    return result
