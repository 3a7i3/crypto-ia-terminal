"""PPL-02E-R3 — append-only PPL -> legacy compatibility projection.

The target JSONL is no longer lifecycle authority in PPL_AUTHORITY mode.  This
projector exists only so research/analytics/notification consumers can continue
reading a familiar corpus while retaining explicit PPL provenance.

Existing legacy bytes are never rewritten.  Projection is idempotent by a
stable projection_id derived from the durable PPL event identity.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from paper_trading.ledger_events import LedgerEvent, LedgerEventType, Side
from paper_trading.paper_portfolio_ledger import project


_PROJECTION_DOMAIN = "PPL-02E-R3-COMPAT-V1"
_PROJECTION_SCHEMA_VERSION = 1
_LEGACY_READER_SCHEMA_VERSION = 5


class CompatibilityProjectionError(RuntimeError):
    """Compatibility projection cannot be proven safe/idempotent."""


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _projection_id(event: LedgerEvent) -> str:
    raw = (
        f"{_PROJECTION_DOMAIN}\0{event.paper_epoch_id}\0"
        f"{event.event_id}\0{_PROJECTION_SCHEMA_VERSION}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _base_row(
    event: LedgerEvent,
    *,
    event_name: str,
    symbol: str,
    side: str,
    price: float | None,
    size_usd: float,
    evidence_status: str,
    missing_fields: Sequence[str],
) -> dict[str, Any]:
    return {
        "event": event_name,
        "trade_id": event.trade_id or "",
        "ts": event.timestamp,
        "ts_iso": _iso(event.timestamp),
        "symbol": symbol,
        "side": side,
        "price": price,
        "size_usd": size_usd,
        "mode": "paper",
        "schema_version": _LEGACY_READER_SCHEMA_VERSION,
        "regime": "unknown",
        "score": 0,
        "score_bin": "",
        "order_id": "",
        "exit_price": None,
        "pnl_usd": None,
        "pnl_pct": None,
        "reason": "",
        "duration_s": None,
        "mae_pct": None,
        "mfe_pct": None,
        "market_context": None,
        "decision_context": None,
        "runtime_config_version": "",
        "tp_price": None,
        "sl_price": None,
        "fee_entry_usd": None,
        "pnl_fee_evidence_incomplete": False,
        "source_authority": "PPL",
        "paper_epoch_id": event.paper_epoch_id,
        "ppl_event_id": event.event_id,
        "projection_id": _projection_id(event),
        "projection_schema_version": _PROJECTION_SCHEMA_VERSION,
        "evidence_status": evidence_status,
        "missing_evidence_fields": ",".join(sorted(missing_fields)),
    }


def _gross_pct(side: Side, entry_price: float, exit_price: float) -> float:
    if side is Side.LONG:
        value = (exit_price - entry_price) / entry_price
    else:
        value = (entry_price - exit_price) / entry_price
    if not math.isfinite(value):
        raise CompatibilityProjectionError("derived compatibility gross_pct is non-finite")
    return value


def build_compatibility_rows(events: Sequence[LedgerEvent]) -> tuple[dict[str, Any], ...]:
    """Build deterministic legacy-shaped rows from one validated v2 PPL epoch."""

    state = project(events)
    if state.epoch is None or state.epoch.schema_version != 2:
        raise CompatibilityProjectionError(
            "PPL compatibility projection requires one replay-complete schema-v2 epoch"
        )

    opens: dict[str, LedgerEvent] = {}
    rows: list[dict[str, Any]] = []

    for event in events:
        if event.event_type is LedgerEventType.POSITION_OPENED:
            assert event.trade_id is not None
            opens[event.trade_id] = event
            row = _base_row(
                event,
                event_name="OPEN",
                symbol=str(event.payload["symbol"]),
                side=str(event.payload["side"]).lower(),
                price=float(event.payload["entry_price"]),
                size_usd=float(event.payload["principal"]),
                evidence_status="PARTIAL_METADATA",
                missing_fields=(
                    "score",
                    "regime",
                    "market_context",
                    "decision_context",
                    "runtime_config_version",
                ),
            )
            row["tp_price"] = float(event.payload["tp_price"])
            row["sl_price"] = float(event.payload["sl_price"])
            row["fee_entry_usd"] = float(event.payload["entry_fee"])
            rows.append(row)
            continue

        if event.event_type not in {
            LedgerEventType.POSITION_CLOSED,
            LedgerEventType.POSITION_UNRESOLVED,
        }:
            continue

        assert event.trade_id is not None
        opened = opens.get(event.trade_id)
        if opened is None:
            raise CompatibilityProjectionError(
                f"trade_id={event.trade_id!r} resolution has no prior OPEN"
            )

        side = Side(str(opened.payload["side"]))
        principal = float(opened.payload["principal"])
        entry_price = float(opened.payload["entry_price"])
        entry_fee = float(opened.payload["entry_fee"])
        symbol = str(opened.payload["symbol"])
        duration = event.timestamp - opened.timestamp
        if duration < 0 or not math.isfinite(duration):
            raise CompatibilityProjectionError(
                f"trade_id={event.trade_id!r} has invalid duration"
            )

        if event.event_type is LedgerEventType.POSITION_CLOSED:
            exit_price = float(event.payload["exit_price"])
            exit_fee = float(event.payload["exit_fee"])
            gross_pct = _gross_pct(side, entry_price, exit_price)
            pnl_usd = principal * gross_pct - entry_fee - exit_fee
            if not math.isfinite(pnl_usd):
                raise CompatibilityProjectionError(
                    f"trade_id={event.trade_id!r} has non-finite derived PnL"
                )
            row = _base_row(
                event,
                event_name="CLOSE",
                symbol=symbol,
                side=side.value.lower(),
                price=exit_price,
                size_usd=principal,
                evidence_status="PARTIAL_METADATA",
                missing_fields=("reason", "mae_pct", "mfe_pct"),
            )
            row["exit_price"] = exit_price
            row["pnl_usd"] = round(pnl_usd, 4)
            # Preserve legacy recorder semantics: pnl_pct is gross price return.
            row["pnl_pct"] = round(gross_pct, 6)
            row["duration_s"] = round(duration, 1)
            rows.append(row)
        else:
            reason = str(event.payload["reason"])
            row = _base_row(
                event,
                event_name="CLOSE",
                symbol=symbol,
                side=side.value.lower(),
                price=None,
                size_usd=principal,
                evidence_status="UNRESOLVED",
                missing_fields=(
                    "exit_price",
                    "pnl_usd",
                    "pnl_pct",
                    "mae_pct",
                    "mfe_pct",
                ),
            )
            row["reason"] = f"ppl_unresolved:{reason}"
            row["duration_s"] = round(duration, 1)
            rows.append(row)

    return tuple(rows)


def _read_existing_projection_ids(raw: bytes) -> dict[str, tuple[str, str]]:
    found: dict[str, tuple[str, str]] = {}
    if not raw:
        return found
    if not raw.endswith(b"\n"):
        raise CompatibilityProjectionError(
            "compatibility target has a truncated/non-newline-terminated final record"
        )
    for number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except Exception as exc:
            raise CompatibilityProjectionError(
                f"compatibility target record {number} is invalid JSON"
            ) from exc
        projection_id = record.get("projection_id")
        if not projection_id:
            continue
        identity = (
            str(record.get("paper_epoch_id") or ""),
            str(record.get("ppl_event_id") or ""),
        )
        previous = found.get(str(projection_id))
        if previous is not None and previous != identity:
            raise CompatibilityProjectionError(
                f"projection_id collision at target record {number}"
            )
        found[str(projection_id)] = identity
    return found


def project_ppl_to_legacy_jsonl(
    events: Sequence[LedgerEvent],
    target_path: str | Path,
) -> int:
    """Append only missing PPL compatibility rows and return append count."""

    rows = build_compatibility_rows(events)
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            stream.seek(0)
            raw = stream.read()
            existing = _read_existing_projection_ids(raw)
            appended = 0
            for row in rows:
                projection_id = str(row["projection_id"])
                identity = (str(row["paper_epoch_id"]), str(row["ppl_event_id"]))
                if projection_id in existing:
                    if existing[projection_id] != identity:
                        raise CompatibilityProjectionError(
                            f"projection_id={projection_id} identity collision"
                        )
                    continue
                encoded = json.dumps(
                    row,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8") + b"\n"
                stream.seek(0, os.SEEK_END)
                stream.write(encoded)
                existing[projection_id] = identity
                appended += 1
            if appended:
                stream.flush()
                os.fsync(stream.fileno())
            return appended
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


__all__ = [
    "CompatibilityProjectionError",
    "build_compatibility_rows",
    "project_ppl_to_legacy_jsonl",
]
