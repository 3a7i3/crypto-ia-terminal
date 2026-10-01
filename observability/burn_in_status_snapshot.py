"""APP-UNIFY-01 U2 — passive BurnInStatusSnapshot producer.

The producer owns the read boundary to the active PAPER PPL epoch and frozen
burn-in configuration.  It never appends to PPL, never creates a PPL lock,
never imports advisor_loop/execution/risk/sizing/exchange code, and publishes
only one atomic presentation JSON artifact.

The Operator API consumes that artifact later; it never reads PPL JSONL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from observability.burn_in_status_contract import (
    AUTHORITY,
    DOMAIN,
    MODE,
    PRODUCT,
    SCHEMA_VERSION,
    validate_burn_in_status_snapshot,
)
from paper_trading import durable_event_store as ppl_wire
from paper_trading.ledger_events import LedgerEvent, LedgerEventType, Side
from paper_trading.paper_portfolio_ledger import project
from scripts import burn_in_experiment_config_freeze as burn_freeze


class BurnInStatusError(RuntimeError):
    """Fail-closed source/projection error."""


DEFAULT_PATH = Path(
    os.getenv("BURN_IN_STATUS_SNAPSHOT_PATH", "databases/burn_in_status_snapshot.json")
)
DEFAULT_STORE_ROOT = Path(
    os.getenv("PPL_AUTHORITY_STORE_ROOT", "databases/ppl_authority")
)
DEFAULT_INTERVAL_S = 30.0

_CONFIG_PARAMETER_MAP = {
    "PB_MAX_POSITIONS": "pb_max_positions",
    "PAPER_PORTFOLIO_BRAIN_LEVEL": "paper_portfolio_brain_level",
    "MEXC_SIM_MAX_POSITION_USD": "mexc_sim_max_position_usd",
    "MEXC_SIM_MAX_AGE_H": "mexc_sim_max_age_h",
    "PAPER_LIFECYCLE_AUTHORITY": "paper_lifecycle_authority",
}


def _utc(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> float:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise BurnInStatusError(f"invalid UTC timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise BurnInStatusError(f"UTC timestamp lacks timezone: {value!r}")
    return parsed.astimezone(timezone.utc).timestamp()


def _finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BurnInStatusError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise BurnInStatusError(f"{name} must be finite")
    return number


def _require_regular_non_symlink(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise BurnInStatusError(f"required source missing: {path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise BurnInStatusError(f"source must be a regular non-symlink file: {path}")


def _epoch_path(store_root: Path, paper_epoch_id: str) -> Path:
    digest = hashlib.sha256(paper_epoch_id.encode("utf-8")).hexdigest()
    return Path(store_root) / "epochs" / f"{digest}.jsonl"


def read_stable_epoch(
    store_root: Path,
    paper_epoch_id: str,
    *,
    attempts: int = 3,
) -> tuple[Path, bytes, tuple[LedgerEvent, ...]]:
    """Read one stable append-only epoch boundary without touching store locks."""

    if not isinstance(paper_epoch_id, str) or not paper_epoch_id:
        raise BurnInStatusError("paper_epoch_id is required")
    if attempts < 1:
        raise BurnInStatusError("attempts must be >= 1")

    path = _epoch_path(store_root, paper_epoch_id)
    _require_regular_non_symlink(path)

    raw: Optional[bytes] = None
    for _ in range(attempts):
        before = path.stat()
        candidate = path.read_bytes()
        after = path.stat()
        if (
            before.st_size == after.st_size == len(candidate)
            and before.st_mtime_ns == after.st_mtime_ns
            and candidate
            and candidate.endswith(b"\n")
        ):
            raw = candidate
            break
    if raw is None:
        raise BurnInStatusError("PPL epoch changed while reading or lacks a complete final record")

    events: list[LedgerEvent] = []
    expected_sequence = 1
    seen: set[str] = set()
    for record_number, line in enumerate(raw.splitlines(keepends=True), 1):
        if not line.endswith(b"\n") or not line[:-1].strip():
            raise BurnInStatusError(f"incomplete/blank PPL record {record_number}")
        try:
            event = ppl_wire._decode_record(
                line[:-1],
                source=path,
                record_number=record_number,
            )
            canonical = ppl_wire._canonical_line(event)
        except Exception as exc:
            raise BurnInStatusError(
                f"invalid PPL record {record_number}: {exc}"
            ) from exc
        if canonical != line:
            raise BurnInStatusError(f"non-canonical PPL record {record_number}")
        if event.paper_epoch_id != paper_epoch_id:
            raise BurnInStatusError(f"PPL epoch mismatch at record {record_number}")
        if event.sequence != expected_sequence:
            raise BurnInStatusError(
                f"PPL sequence mismatch at record {record_number}: "
                f"got {event.sequence}, expected {expected_sequence}"
            )
        if event.event_id in seen:
            raise BurnInStatusError(f"duplicate PPL event_id={event.event_id!r}")
        seen.add(event.event_id)
        events.append(event)
        expected_sequence += 1

    # The canonical projector is the semantic admission gate.
    project(tuple(events))
    return path, raw, tuple(events)


def _read_config_document(path: Path) -> Mapping[str, Any]:
    _require_regular_non_symlink(path)
    try:
        doc = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=ppl_wire._object_without_duplicate_keys,
            parse_constant=ppl_wire._reject_json_constant,
        )
    except Exception as exc:
        raise BurnInStatusError(f"invalid burn-in config document: {exc}") from exc
    if not isinstance(doc, dict):
        raise BurnInStatusError("burn-in config document must be a JSON object")
    return doc


def _frozen_config_projection(
    config_document: Mapping[str, Any],
    *,
    paper_epoch_id: str,
    source_code_sha: str,
    config_snapshot_hash: str,
) -> dict[str, Any]:
    stored_hash = config_document.get("snapshot_sha256")
    if not isinstance(stored_hash, str):
        raise BurnInStatusError("burn-in config snapshot_sha256 missing")
    payload = dict(config_document)
    payload.pop("snapshot_sha256", None)
    actual_hash = burn_freeze.snapshot_sha256(payload)
    if actual_hash != stored_hash:
        raise BurnInStatusError("burn-in config internal hash mismatch")
    if config_document.get("snapshot_schema") != burn_freeze.SNAPSHOT_SCHEMA:
        raise BurnInStatusError("burn-in config schema mismatch")
    if config_document.get("paper_epoch_id") != paper_epoch_id:
        raise BurnInStatusError("burn-in config/PPL epoch mismatch")
    if config_document.get("runtime_source_sha") != source_code_sha:
        raise BurnInStatusError("burn-in config/PPL source SHA mismatch")
    if stored_hash != config_snapshot_hash:
        raise BurnInStatusError("burn-in config/PPL config hash mismatch")

    parameters = config_document.get("parameters")
    if not isinstance(parameters, dict):
        raise BurnInStatusError("burn-in config parameters missing")

    projection = {
        "snapshot_schema": burn_freeze.SNAPSHOT_SCHEMA,
        "snapshot_sha256": stored_hash,
        "runtime_source_sha": source_code_sha,
    }
    for source_name, presentation_name in _CONFIG_PARAMETER_MAP.items():
        record = parameters.get(source_name)
        if not isinstance(record, dict) or "value" not in record:
            raise BurnInStatusError(
                f"required frozen material parameter missing: {source_name}"
            )
        value = record["value"]
        if isinstance(value, bool) or value is None:
            raise BurnInStatusError(
                f"invalid frozen material parameter value: {source_name}"
            )
        text = str(value).strip()
        if not text:
            raise BurnInStatusError(
                f"blank frozen material parameter value: {source_name}"
            )
        projection[presentation_name] = text
    return projection


def _scientific_t0(value_utc: Optional[str], source: Optional[str]) -> dict[str, Any]:
    if value_utc is None and source is None:
        return {"status": "NOT_AVAILABLE", "value_utc": None, "source": None}
    if not value_utc or not source:
        raise BurnInStatusError(
            "scientific_t0_utc and scientific_t0_source must be supplied together"
        )
    _parse_utc(value_utc)
    return {"status": "PRESENT", "value_utc": value_utc, "source": source}


def _deadline_state(
    *,
    now: float,
    timeout_at: Optional[float],
    recovery_eligible_until: Optional[float],
) -> str:
    if timeout_at is None or recovery_eligible_until is None:
        return "NOT_AVAILABLE"
    timeout = _finite("timeout_at", timeout_at)
    recovery = _finite("recovery_eligible_until", recovery_eligible_until)
    if now < timeout:
        return "BEFORE_TIMEOUT"
    if now <= recovery:
        return "RECOVERY_WINDOW"
    return "RECOVERY_EXPIRED"


def _gross_pnl(
    *,
    principal: float,
    side: Side,
    entry_price: float,
    exit_price: float,
) -> float:
    if side is Side.LONG:
        gross = principal * (exit_price - entry_price) / entry_price
    else:
        gross = principal * (entry_price - exit_price) / entry_price
    return _finite("gross_pnl_usd", gross)


def build_burn_in_status_snapshot(
    *,
    events: Sequence[LedgerEvent],
    config_document: Mapping[str, Any],
    ppl_stream_sha256: str,
    now_fn=time.time,
    scientific_t0_utc: Optional[str] = None,
    scientific_t0_source: Optional[str] = None,
) -> dict[str, Any]:
    if not events:
        raise BurnInStatusError("PPL event stream is empty")
    if not isinstance(ppl_stream_sha256, str) or len(ppl_stream_sha256) != 64:
        raise BurnInStatusError("ppl_stream_sha256 must be a SHA-256 hex string")

    state = project(tuple(events))
    if state.epoch is None or state.paper_epoch_id is None:
        raise BurnInStatusError("PPL stream has no projected epoch")

    now = _finite("generated_at", now_fn())
    if now < state.epoch.created_at:
        raise BurnInStatusError("snapshot generation precedes epoch creation")

    frozen_config = _frozen_config_projection(
        config_document,
        paper_epoch_id=state.paper_epoch_id,
        source_code_sha=state.epoch.code_sha,
        config_snapshot_hash=state.epoch.config_snapshot_hash,
    )

    counts = Counter(event.event_type.value for event in events)
    event_counts = {
        event_type.value: int(counts[event_type.value])
        for event_type in LedgerEventType
    }

    open_events: dict[str, LedgerEvent] = {}
    terminal_events: dict[str, LedgerEvent] = {}
    for event in events:
        if event.event_type is LedgerEventType.POSITION_OPENED:
            assert event.trade_id is not None
            open_events[event.trade_id] = event
        elif event.event_type in {
            LedgerEventType.POSITION_CLOSED,
            LedgerEventType.POSITION_UNRESOLVED,
        }:
            assert event.trade_id is not None
            terminal_events[event.trade_id] = event

    history: list[dict[str, Any]] = []
    closed_net_total = 0.0
    for trade_id, opened in open_events.items():
        payload = opened.payload
        side = Side(str(payload["side"]))
        principal = _finite("principal", payload["principal"])
        entry_price = _finite("entry_price", payload["entry_price"])
        entry_fee = _finite("entry_fee", payload["entry_fee"])
        terminal = terminal_events.get(trade_id)

        base = {
            "trade_id": trade_id,
            "open_decision_id": opened.decision_id,
            "terminal_decision_id": terminal.decision_id if terminal else None,
            "symbol": str(payload["symbol"]),
            "side": side.value,
            "principal_usd": principal,
            "entry_price": entry_price,
            "entry_fee_usd": entry_fee,
            "opened_sequence": opened.sequence,
            "opened_at_utc": _utc(opened.timestamp),
        }

        if terminal is None:
            history.append(
                {
                    **base,
                    "status": "OPEN",
                    "terminal_sequence": None,
                    "terminal_at_utc": None,
                    "exit_price": None,
                    "exit_fee_usd": None,
                    "gross_pnl_usd": None,
                    "net_realized_pnl_usd": None,
                    "unresolved_reason": None,
                    "duration_seconds": None,
                }
            )
            continue

        duration = _finite("duration_seconds", terminal.timestamp - opened.timestamp)
        if duration < 0:
            raise BurnInStatusError(f"terminal event predates OPEN for trade_id={trade_id}")

        if terminal.event_type is LedgerEventType.POSITION_CLOSED:
            exit_price = _finite("exit_price", terminal.payload["exit_price"])
            exit_fee = _finite("exit_fee", terminal.payload["exit_fee"])
            gross = _gross_pnl(
                principal=principal,
                side=side,
                entry_price=entry_price,
                exit_price=exit_price,
            )
            net = _finite("net_realized_pnl_usd", gross - entry_fee - exit_fee)
            closed_net_total = _finite(
                "closed_net_total",
                closed_net_total + net,
            )
            history.append(
                {
                    **base,
                    "status": "CLOSED",
                    "terminal_sequence": terminal.sequence,
                    "terminal_at_utc": _utc(terminal.timestamp),
                    "exit_price": exit_price,
                    "exit_fee_usd": exit_fee,
                    "gross_pnl_usd": gross,
                    "net_realized_pnl_usd": net,
                    "unresolved_reason": None,
                    "duration_seconds": duration,
                }
            )
        else:
            reason = terminal.payload.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                raise BurnInStatusError(
                    f"UNRESOLVED lifecycle lacks reason for trade_id={trade_id}"
                )
            history.append(
                {
                    **base,
                    "status": "UNRESOLVED",
                    "terminal_sequence": terminal.sequence,
                    "terminal_at_utc": _utc(terminal.timestamp),
                    "exit_price": None,
                    "exit_fee_usd": None,
                    "gross_pnl_usd": None,
                    "net_realized_pnl_usd": None,
                    "unresolved_reason": reason,
                    "duration_seconds": duration,
                }
            )

    if not math.isclose(
        closed_net_total,
        state.realized_pnl,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise BurnInStatusError(
            "lifecycle history realized PnL does not reconcile with canonical PPL projection"
        )

    history.sort(key=lambda row: row["opened_sequence"], reverse=True)

    open_rows: list[dict[str, Any]] = []
    for trade_id, position in state.open_positions.items():
        opened = open_events[trade_id]
        age = _finite("age_seconds", now - position.opened_at)
        if age < 0:
            raise BurnInStatusError(
                f"snapshot generation precedes OPEN for trade_id={trade_id}"
            )
        open_rows.append(
            {
                "trade_id": trade_id,
                "decision_id": opened.decision_id,
                "symbol": position.symbol,
                "side": position.side.value,
                "principal_usd": position.principal,
                "entry_price": position.entry_price,
                "entry_fee_usd": position.entry_fee,
                "opened_sequence": position.opened_sequence,
                "opened_at_utc": _utc(position.opened_at),
                "age_seconds": age,
                "tp_price": position.tp_price,
                "sl_price": position.sl_price,
                "timeout_at_utc": (
                    _utc(position.timeout_at)
                    if position.timeout_at is not None
                    else None
                ),
                "recovery_eligible_until_utc": (
                    _utc(position.recovery_eligible_until)
                    if position.recovery_eligible_until is not None
                    else None
                ),
                "deadline_state": _deadline_state(
                    now=now,
                    timeout_at=position.timeout_at,
                    recovery_eligible_until=position.recovery_eligible_until,
                ),
            }
        )
    open_rows.sort(key=lambda row: row["opened_sequence"], reverse=True)

    last = events[-1]
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "product": PRODUCT,
        "domain": DOMAIN,
        "authority": AUTHORITY,
        "mode": MODE,
        "generated_at_utc": _utc(now),
        "source_updated_at_utc": _utc(last.timestamp),
        "paper_epoch_id": state.paper_epoch_id,
        "epoch_created_at_utc": _utc(state.epoch.created_at),
        "source_code_sha": state.epoch.code_sha,
        "config_snapshot_hash": state.epoch.config_snapshot_hash,
        "ppl_stream_sha256": ppl_stream_sha256,
        "scientific_t0": _scientific_t0(
            scientific_t0_utc,
            scientific_t0_source,
        ),
        "event_count": len(events),
        "last_sequence": state.last_sequence,
        "event_counts": event_counts,
        "lifecycle_counts": {
            "open": len(state.open_positions),
            "closed": len(state.closed_trade_ids),
            "unresolved": len(state.unresolved_positions),
            "total": len(open_events),
        },
        "last_event": {
            "sequence": last.sequence,
            "event_type": last.event_type.value,
            "timestamp_utc": _utc(last.timestamp),
            "trade_id": last.trade_id,
            "decision_id": last.decision_id,
        },
        "open_lifecycles": open_rows,
        "lifecycle_history": history,
        "history_order": "OPEN_SEQUENCE_DESC",
        "frozen_config": frozen_config,
        "finalization": {
            "state": "NOT_AVAILABLE",
            "reason": "NO_GOVERNED_FINALIZATION_ARTIFACT_SUPPLIED",
        },
    }
    if not validate_burn_in_status_snapshot(snapshot):
        raise BurnInStatusError("producer output failed its closed presentation contract")
    return snapshot


def build_from_sources(
    *,
    store_root: Path,
    paper_epoch_id: str,
    config_path: Path,
    now_fn=time.time,
    scientific_t0_utc: Optional[str] = None,
    scientific_t0_source: Optional[str] = None,
) -> dict[str, Any]:
    _, raw, events = read_stable_epoch(store_root, paper_epoch_id)
    config_document = _read_config_document(config_path)
    return build_burn_in_status_snapshot(
        events=events,
        config_document=config_document,
        ppl_stream_sha256=hashlib.sha256(raw).hexdigest(),
        now_fn=now_fn,
        scientific_t0_utc=scientific_t0_utc,
        scientific_t0_source=scientific_t0_source,
    )


def write_burn_in_status_snapshot(
    path: Path = DEFAULT_PATH,
    *,
    store_root: Path,
    paper_epoch_id: str,
    config_path: Path,
    now_fn=time.time,
    scientific_t0_utc: Optional[str] = None,
    scientific_t0_source: Optional[str] = None,
) -> dict[str, Any]:
    snapshot = build_from_sources(
        store_root=Path(store_root),
        paper_epoch_id=paper_epoch_id,
        config_path=Path(config_path),
        now_fn=now_fn,
        scientific_t0_utc=scientific_t0_utc,
        scientific_t0_source=scientific_t0_source,
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        snapshot,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=2,
    )
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, target)
    return snapshot


def publish_once(
    path: Path,
    *,
    store_root: Path,
    paper_epoch_id: str,
    config_path: Path,
    scientific_t0_utc: Optional[str] = None,
    scientific_t0_source: Optional[str] = None,
) -> bool:
    try:
        write_burn_in_status_snapshot(
            path,
            store_root=store_root,
            paper_epoch_id=paper_epoch_id,
            config_path=config_path,
            scientific_t0_utc=scientific_t0_utc,
            scientific_t0_source=scientific_t0_source,
        )
        return True
    except Exception as exc:
        print(f"[BurnInStatusSnapshot] publish failed: {exc}", file=sys.stderr, flush=True)
        return False


def _default_config_path(store_root: Path, paper_epoch_id: str) -> Path:
    explicit = os.getenv("BURN_IN_CONFIG_SNAPSHOT_PATH")
    if explicit:
        return Path(explicit)
    return Path(store_root) / f"{paper_epoch_id}.burn-in-experiment-config.json"


def _publish_args(args: argparse.Namespace) -> dict[str, Any]:
    epoch = args.epoch or os.getenv("PPL_AUTHORITY_EPOCH_ID")
    if not epoch:
        raise BurnInStatusError("--epoch or PPL_AUTHORITY_EPOCH_ID is required")
    store_root = Path(args.store_root)
    config_path = Path(args.config_path) if args.config_path else _default_config_path(
        store_root, epoch
    )
    t0 = args.scientific_t0_utc or os.getenv("BURN_IN_SCIENTIFIC_T0_UTC")
    t0_source = args.scientific_t0_source or os.getenv("BURN_IN_SCIENTIFIC_T0_SOURCE")
    return {
        "path": Path(args.path),
        "store_root": store_root,
        "paper_epoch_id": epoch,
        "config_path": config_path,
        "scientific_t0_utc": t0,
        "scientific_t0_source": t0_source,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--path", default=str(DEFAULT_PATH))
    parser.add_argument("--store-root", default=str(DEFAULT_STORE_ROOT))
    parser.add_argument("--epoch", default=None)
    parser.add_argument("--config-path", default=None)
    parser.add_argument("--scientific-t0-utc", default=None)
    parser.add_argument("--scientific-t0-source", default=None)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S)
    args = parser.parse_args(argv)

    try:
        kwargs = _publish_args(args)
    except BurnInStatusError as exc:
        print(f"[BurnInStatusSnapshot] {exc}", file=sys.stderr)
        return 2

    if args.once:
        return 0 if publish_once(**kwargs) else 1
    if not math.isfinite(args.interval) or args.interval <= 0:
        print("[BurnInStatusSnapshot] --interval must be finite and > 0", file=sys.stderr)
        return 2
    while True:
        publish_once(**kwargs)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BurnInStatusError",
    "DEFAULT_PATH",
    "DEFAULT_STORE_ROOT",
    "build_burn_in_status_snapshot",
    "build_from_sources",
    "read_stable_epoch",
    "write_burn_in_status_snapshot",
]
