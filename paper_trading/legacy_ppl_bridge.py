"""Read-only, deterministic bridge from legacy PAPER JSONL to PPL events.

PPL-02C preserves evidence.  It never writes, repairs, normalizes, or silently
skips the legacy source.  A PPL import plan is emitted only when the complete
captured snapshot can be represented without inventing missing financial
facts.  Runtime wiring and authority promotion are deliberately absent.
"""

from __future__ import annotations

import errno
import hashlib
import json
import math
import os
import stat
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from paper_trading.durable_event_store import AppendResult, DurableEventStore
from paper_trading.ledger_events import (
    LedgerEvent,
    LedgerEventType,
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
    make_position_unresolved_event,
    normalize_side,
)
from paper_trading.paper_portfolio_ledger import LedgerReplayError, project

BRIDGE_SCHEMA_VERSION = 1
_SUPPORTED_LEGACY_SCHEMAS = frozenset({1, 2, 3, 4, 5})
_PAPER_MODES = frozenset({"paper", "futures_demo"})
_READ_CHUNK_BYTES = 1024 * 1024


class LegacyBridgeError(Exception):
    """Base class for PPL-02C bridge failures."""


class LegacySourceNotFoundError(LegacyBridgeError):
    """The explicitly selected legacy source does not exist."""


class LegacySourceCorruptionError(LegacyBridgeError):
    """The complete source snapshot cannot be parsed or trusted."""


class LegacySourceChangedError(LegacyBridgeError):
    """The legacy source changed or was replaced during capture."""


class LegacyImportContextError(LegacyBridgeError):
    """Explicit import context is absent, malformed, or for other bytes."""


class LegacyImportBlockedError(LegacyBridgeError):
    """At least one lifecycle cannot be represented without assumptions."""


class LegacyLifecycleStatus(str, Enum):
    IMPORTABLE = "IMPORTABLE"
    IMPORTABLE_AS_UNRESOLVED = "IMPORTABLE_AS_UNRESOLVED"
    UNRESOLVED = "UNRESOLVED"
    REJECTED = "REJECTED"


class LegacyImportPlanStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class LegacyContextProvenance(str, Enum):
    EXTERNALLY_EVIDENCED = "EXTERNALLY_EVIDENCED"


class LegacyReasonCode(str, Enum):
    MISSING_ENTRY_FEE = "MISSING_ENTRY_FEE"
    MISSING_EXIT_FEE = "MISSING_EXIT_FEE"
    FEE_EVIDENCE_INCOMPLETE = "FEE_EVIDENCE_INCOMPLETE"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"
    INVALID_MODE = "INVALID_MODE"
    INVALID_SIDE = "INVALID_SIDE"
    INVALID_FIELD = "INVALID_FIELD"
    DUPLICATE_OPEN = "DUPLICATE_OPEN"
    DUPLICATE_CLOSE = "DUPLICATE_CLOSE"
    ORPHAN_CLOSE = "ORPHAN_CLOSE"
    CLOSE_BEFORE_OPEN = "CLOSE_BEFORE_OPEN"
    TIMESTAMP_REGRESSION = "TIMESTAMP_REGRESSION"
    GLOBAL_TIMESTAMP_REGRESSION = "GLOBAL_TIMESTAMP_REGRESSION"
    LIFECYCLE_FIELD_MISMATCH = "LIFECYCLE_FIELD_MISMATCH"
    AMBIGUOUS_EXIT_FEE = "AMBIGUOUS_EXIT_FEE"
    REPORTED_PNL_CONFLICT = "REPORTED_PNL_CONFLICT"


@dataclass(frozen=True)
class LegacySourceProvenance:
    """Content identity for one stable, bounded legacy source capture."""

    source_label: str
    sha256: str
    byte_length: int
    line_count: int


@dataclass(frozen=True)
class LegacyLifecycleAssessment:
    """Deterministic evidence classification for one legacy trade ID."""

    trade_id: str
    open_line_number: int | None
    close_line_number: int | None
    status: LegacyLifecycleStatus
    reason_codes: tuple[LegacyReasonCode, ...] = ()


@dataclass(frozen=True)
class _LegacyRecord:
    line_number: int
    line_sha256: str
    data: Mapping[str, Any] = field(repr=False)


@dataclass(frozen=True)
class LegacyBridgeSnapshot:
    """Immutable inspection result; contains every parsed physical record."""

    provenance: LegacySourceProvenance
    open_count: int
    close_count: int
    schema_counts: tuple[tuple[str, int], ...]
    assessments: tuple[LegacyLifecycleAssessment, ...]
    _records: tuple[_LegacyRecord, ...] = field(repr=False)

    @property
    def status(self) -> LegacyImportPlanStatus:
        if any(
            item.status
            in {LegacyLifecycleStatus.UNRESOLVED, LegacyLifecycleStatus.REJECTED}
            for item in self.assessments
        ):
            return LegacyImportPlanStatus.BLOCKED
        return LegacyImportPlanStatus.READY


@dataclass(frozen=True)
class LegacyImportContext:
    """Externally evidenced epoch facts; every field is explicit, no defaults."""

    expected_source_sha256: str
    paper_epoch_id: str
    epoch_created_at: float
    initial_virtual_capital: float
    code_sha: str
    config_snapshot_hash: str
    provenance: LegacyContextProvenance

    def __post_init__(self) -> None:
        digest = self.expected_source_sha256
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise LegacyImportContextError(
                "expected_source_sha256 must be a lowercase SHA-256 digest"
            )
        if not isinstance(self.paper_epoch_id, str) or not self.paper_epoch_id:
            raise LegacyImportContextError("paper_epoch_id must be non-empty")
        _context_number("epoch_created_at", self.epoch_created_at)
        capital = _context_number(
            "initial_virtual_capital", self.initial_virtual_capital
        )
        if capital <= 0:
            raise LegacyImportContextError(
                "initial_virtual_capital must be greater than zero"
            )
        if not isinstance(self.code_sha, str) or not self.code_sha:
            raise LegacyImportContextError("code_sha must be non-empty")
        if (
            not isinstance(self.config_snapshot_hash, str)
            or not self.config_snapshot_hash
        ):
            raise LegacyImportContextError("config_snapshot_hash must be non-empty")
        if self.provenance is not LegacyContextProvenance.EXTERNALLY_EVIDENCED:
            raise LegacyImportContextError(
                "legacy epoch context must be explicitly EXTERNALLY_EVIDENCED"
            )


@dataclass(frozen=True)
class LegacyImportPlan:
    provenance: LegacySourceProvenance
    context: LegacyImportContext
    status: LegacyImportPlanStatus
    assessments: tuple[LegacyLifecycleAssessment, ...]
    events: tuple[LedgerEvent, ...]


class _DuplicateJSONKey(ValueError):
    pass


def _context_number(name: str, value: Any) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise LegacyImportContextError(f"{name} must be a finite real number")
    return float(value)


def _object_no_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKey(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r}")


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _metadata_signature(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_descriptor(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, _READ_CHUNK_BYTES)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _capture_source(path: Path) -> bytes:
    try:
        path_before = os.stat(path, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise LegacySourceNotFoundError(f"legacy source not found: {path}") from exc

    if stat.S_ISLNK(path_before.st_mode) or not stat.S_ISREG(path_before.st_mode):
        raise LegacySourceCorruptionError(
            f"legacy source must be a regular non-symlink file: {path}"
        )

    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as exc:
        raise LegacySourceChangedError(
            f"legacy source disappeared during capture: {path}"
        ) from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise LegacySourceCorruptionError(
                f"legacy source became a symlink during capture: {path}"
            ) from exc
        raise

    try:
        descriptor_before = os.fstat(descriptor)
        if not stat.S_ISREG(descriptor_before.st_mode):
            raise LegacySourceCorruptionError(
                f"opened legacy source is not a regular file: {path}"
            )
        raw = _read_descriptor(descriptor)
        descriptor_after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    try:
        path_after = os.stat(path, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise LegacySourceChangedError(
            f"legacy source disappeared during capture: {path}"
        ) from exc

    signatures = {
        _metadata_signature(path_before),
        _metadata_signature(descriptor_before),
        _metadata_signature(descriptor_after),
        _metadata_signature(path_after),
    }
    if len(signatures) != 1 or len(raw) != descriptor_after.st_size:
        raise LegacySourceChangedError(
            f"legacy source changed or was replaced during capture: {path}"
        )
    return raw


def _parse_records(raw: bytes) -> tuple[_LegacyRecord, ...]:
    if raw and not raw.endswith(b"\n"):
        raise LegacySourceCorruptionError(
            "legacy source is missing its final newline; tail is incomplete"
        )
    if not raw:
        raise LegacySourceCorruptionError("legacy source is empty")

    records: list[_LegacyRecord] = []
    for line_number, line in enumerate(raw[:-1].split(b"\n"), start=1):
        if not line.strip():
            raise LegacySourceCorruptionError(
                f"legacy source contains a blank record at line {line_number}"
            )
        try:
            text = line.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise LegacySourceCorruptionError(
                f"legacy source contains invalid UTF-8 at line {line_number}"
            ) from exc
        try:
            parsed = json.loads(
                text,
                object_pairs_hook=_object_no_duplicate_keys,
                parse_constant=_reject_json_constant,
            )
        except (_DuplicateJSONKey, json.JSONDecodeError, ValueError) as exc:
            raise LegacySourceCorruptionError(
                f"legacy source contains invalid JSON at line {line_number}: {exc}"
            ) from exc
        if not isinstance(parsed, dict):
            raise LegacySourceCorruptionError(
                f"legacy record {line_number} must be a JSON object"
            )
        records.append(
            _LegacyRecord(
                line_number=line_number,
                line_sha256=hashlib.sha256(line + b"\n").hexdigest(),
                data=_deep_freeze(parsed),
            )
        )
    return tuple(records)


def _finite_number(value: Any, *, positive: bool = False) -> float | None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        return None
    result = float(value)
    if positive and result <= 0:
        return None
    return result


def _explicit_fee(record: Mapping[str, Any], *names: str) -> tuple[str, float | None]:
    supplied = [(name, record[name]) for name in names if record.get(name) is not None]
    if not supplied:
        return "missing", None
    values: list[float] = []
    for _, raw in supplied:
        value = _finite_number(raw)
        if value is None or value < 0:
            return "invalid", None
        values.append(value)
    if len(values) > 1 and any(value != values[0] for value in values[1:]):
        return "ambiguous", None
    return "present", values[0]


def _schema_reason(record: Mapping[str, Any]) -> LegacyReasonCode | None:
    if "schema_version" not in record:
        return None
    schema = record["schema_version"]
    if (
        not isinstance(schema, int)
        or isinstance(schema, bool)
        or schema not in _SUPPORTED_LEGACY_SCHEMAS
    ):
        return LegacyReasonCode.UNSUPPORTED_SCHEMA
    return None


def _common_reasons(record: _LegacyRecord) -> set[LegacyReasonCode]:
    data = record.data
    reasons: set[LegacyReasonCode] = set()
    schema_reason = _schema_reason(data)
    if schema_reason:
        reasons.add(schema_reason)
    if data.get("mode") not in _PAPER_MODES:
        reasons.add(LegacyReasonCode.INVALID_MODE)
    if _finite_number(data.get("ts"), positive=True) is None:
        reasons.add(LegacyReasonCode.INVALID_FIELD)
    return reasons


def _open_reasons(record: _LegacyRecord) -> tuple[set[LegacyReasonCode], bool]:
    data = record.data
    rejected = _common_reasons(record)
    unresolved: set[LegacyReasonCode] = set()

    if not isinstance(data.get("symbol"), str) or not data.get("symbol"):
        rejected.add(LegacyReasonCode.INVALID_FIELD)
    if _finite_number(data.get("price"), positive=True) is None:
        rejected.add(LegacyReasonCode.INVALID_FIELD)
    if _finite_number(data.get("size_usd"), positive=True) is None:
        rejected.add(LegacyReasonCode.INVALID_FIELD)
    try:
        normalize_side(data.get("side"))
    except ValueError:
        rejected.add(LegacyReasonCode.INVALID_SIDE)

    fee_state, _ = _explicit_fee(data, "fee_entry_usd")
    if fee_state == "missing":
        unresolved.add(LegacyReasonCode.MISSING_ENTRY_FEE)
    elif fee_state != "present":
        rejected.add(LegacyReasonCode.INVALID_FIELD)

    return rejected | unresolved, bool(rejected)


def _close_reasons(record: _LegacyRecord) -> tuple[set[LegacyReasonCode], bool]:
    data = record.data
    rejected = _common_reasons(record)
    unresolved: set[LegacyReasonCode] = set()

    exit_price = data.get("exit_price")
    if exit_price is None:
        unresolved.add(LegacyReasonCode.UNKNOWN_OUTCOME)
    elif _finite_number(exit_price, positive=True) is None:
        rejected.add(LegacyReasonCode.INVALID_FIELD)

    fee_state, _ = _explicit_fee(data, "exit_fee", "fee_exit_usd")
    if fee_state == "missing":
        unresolved.add(LegacyReasonCode.MISSING_EXIT_FEE)
    elif fee_state == "ambiguous":
        rejected.add(LegacyReasonCode.AMBIGUOUS_EXIT_FEE)
    elif fee_state != "present":
        rejected.add(LegacyReasonCode.INVALID_FIELD)

    evidence_flag = data.get("pnl_fee_evidence_incomplete", False)
    if not isinstance(evidence_flag, bool):
        rejected.add(LegacyReasonCode.INVALID_FIELD)
    elif evidence_flag:
        unresolved.add(LegacyReasonCode.FEE_EVIDENCE_INCOMPLETE)

    if data.get("reason") == "expired_on_restore":
        unresolved.add(LegacyReasonCode.UNKNOWN_OUTCOME)

    pnl = data.get("pnl_usd")
    if pnl is not None and _finite_number(pnl) is None:
        rejected.add(LegacyReasonCode.INVALID_FIELD)

    return rejected | unresolved, bool(rejected)


def _lifecycle_mismatch(
    open_record: _LegacyRecord, close_record: _LegacyRecord
) -> bool:
    opened = open_record.data
    closed = close_record.data
    if closed.get("mode") != opened.get("mode"):
        return True
    if closed.get("symbol") not in (None, "") and closed.get("symbol") != opened.get(
        "symbol"
    ):
        return True
    if closed.get("side") not in (None, ""):
        try:
            if normalize_side(closed.get("side")) is not normalize_side(
                opened.get("side")
            ):
                return True
        except ValueError:
            return True
    close_size = closed.get("size_usd")
    return close_size is not None and close_size != opened.get("size_usd")


def _reported_pnl_conflicts(
    open_record: _LegacyRecord, close_record: _LegacyRecord
) -> bool:
    opened = open_record.data
    closed = close_record.data
    if (
        closed.get("pnl_fee_evidence_incomplete") is True
        or closed.get("reason") == "expired_on_restore"
        or closed.get("exit_price") is None
    ):
        return False
    reported = closed.get("pnl_usd")
    if reported is None:
        return False
    reported_value = _finite_number(reported)
    entry = _finite_number(opened.get("price"), positive=True)
    exit_price = _finite_number(closed.get("exit_price"), positive=True)
    principal = _finite_number(opened.get("size_usd"), positive=True)
    entry_state, entry_fee = _explicit_fee(opened, "fee_entry_usd")
    exit_state, exit_fee = _explicit_fee(closed, "exit_fee", "fee_exit_usd")
    if (
        reported_value is None
        or entry is None
        or exit_price is None
        or principal is None
        or entry_state != "present"
        or exit_state != "present"
        or entry_fee is None
        or exit_fee is None
    ):
        return False
    try:
        side = normalize_side(opened.get("side"))
    except ValueError:
        # INVALID_SIDE is already an explicit lifecycle rejection.  Do not
        # turn that reportable defect into an accidental inspection crash.
        return False
    if side.value == "LONG":
        gross_pct = (exit_price - entry) / entry
    else:
        gross_pct = (entry - exit_price) / entry
    expected = principal * gross_pct - entry_fee - exit_fee
    if not math.isfinite(expected):
        return True
    return round(expected, 4) != reported_value


def _assess_lifecycles(
    records: tuple[_LegacyRecord, ...],
) -> tuple[LegacyLifecycleAssessment, ...]:
    grouped: dict[str, list[_LegacyRecord]] = defaultdict(list)
    global_regressions: set[str] = set()
    prior_timestamp: float | None = None

    for record in records:
        trade_id = record.data.get("trade_id")
        if not isinstance(trade_id, str) or not trade_id:
            raise LegacySourceCorruptionError(
                f"legacy record {record.line_number} has no non-empty trade_id"
            )
        event = record.data.get("event")
        if event not in {"OPEN", "CLOSE"}:
            raise LegacySourceCorruptionError(
                f"legacy record {record.line_number} has unsupported event={event!r}"
            )
        timestamp = _finite_number(record.data.get("ts"), positive=True)
        if timestamp is not None:
            if prior_timestamp is not None and timestamp < prior_timestamp:
                global_regressions.add(trade_id)
            prior_timestamp = timestamp
        grouped[trade_id].append(record)

    assessments: list[LegacyLifecycleAssessment] = []
    for trade_id, lifecycle in grouped.items():
        opens = [record for record in lifecycle if record.data["event"] == "OPEN"]
        closes = [record for record in lifecycle if record.data["event"] == "CLOSE"]
        reasons: set[LegacyReasonCode] = set()
        rejected = False

        if not opens:
            reasons.add(LegacyReasonCode.ORPHAN_CLOSE)
            rejected = True
        if len(opens) > 1:
            reasons.add(LegacyReasonCode.DUPLICATE_OPEN)
            rejected = True
        if len(closes) > 1:
            reasons.add(LegacyReasonCode.DUPLICATE_CLOSE)
            rejected = True
        if lifecycle and lifecycle[0].data["event"] == "CLOSE":
            reasons.add(LegacyReasonCode.CLOSE_BEFORE_OPEN)
            rejected = True
        if trade_id in global_regressions:
            reasons.add(LegacyReasonCode.GLOBAL_TIMESTAMP_REGRESSION)
            rejected = True

        open_record = opens[0] if opens else None
        close_record = closes[0] if closes else None
        open_unresolved = False
        close_unresolved = False

        if open_record is not None:
            open_reasons, open_rejected = _open_reasons(open_record)
            reasons.update(open_reasons)
            rejected = rejected or open_rejected
            open_unresolved = LegacyReasonCode.MISSING_ENTRY_FEE in open_reasons

        if close_record is not None:
            close_reasons, close_rejected = _close_reasons(close_record)
            reasons.update(close_reasons)
            rejected = rejected or close_rejected
            close_unresolved = bool(
                close_reasons
                & {
                    LegacyReasonCode.MISSING_EXIT_FEE,
                    LegacyReasonCode.FEE_EVIDENCE_INCOMPLETE,
                    LegacyReasonCode.UNKNOWN_OUTCOME,
                }
            )

        if open_record is not None and close_record is not None:
            if close_record.line_number < open_record.line_number:
                reasons.add(LegacyReasonCode.CLOSE_BEFORE_OPEN)
                rejected = True
            open_ts = _finite_number(open_record.data.get("ts"), positive=True)
            close_ts = _finite_number(close_record.data.get("ts"), positive=True)
            if open_ts is not None and close_ts is not None and close_ts < open_ts:
                reasons.add(LegacyReasonCode.TIMESTAMP_REGRESSION)
                rejected = True
            if _lifecycle_mismatch(open_record, close_record):
                reasons.add(LegacyReasonCode.LIFECYCLE_FIELD_MISMATCH)
                rejected = True
            if _reported_pnl_conflicts(open_record, close_record):
                reasons.add(LegacyReasonCode.REPORTED_PNL_CONFLICT)
                rejected = True

        if rejected:
            status = LegacyLifecycleStatus.REJECTED
        elif open_unresolved:
            status = LegacyLifecycleStatus.UNRESOLVED
        elif close_unresolved:
            status = LegacyLifecycleStatus.IMPORTABLE_AS_UNRESOLVED
        else:
            status = LegacyLifecycleStatus.IMPORTABLE

        assessments.append(
            LegacyLifecycleAssessment(
                trade_id=trade_id,
                open_line_number=open_record.line_number if open_record else None,
                close_line_number=close_record.line_number if close_record else None,
                status=status,
                reason_codes=tuple(sorted(reasons, key=lambda item: item.value)),
            )
        )

    return tuple(
        sorted(
            assessments,
            key=lambda item: (
                item.open_line_number
                if item.open_line_number is not None
                else item.close_line_number or 0,
                item.trade_id,
            ),
        )
    )


def inspect_legacy_journal(
    source_path: os.PathLike[str] | str, *, source_label: str
) -> LegacyBridgeSnapshot:
    """Capture, parse, and classify one complete legacy source snapshot."""
    if not isinstance(source_label, str) or not source_label.strip():
        raise ValueError("source_label must be a non-empty explicit string")
    path = Path(source_path)
    raw = _capture_source(path)
    records = _parse_records(raw)
    assessments = _assess_lifecycles(records)
    event_counts = Counter(str(record.data["event"]) for record in records)
    schema_counts = Counter(
        "MISSING"
        if "schema_version" not in record.data
        else str(record.data["schema_version"])
        for record in records
    )
    return LegacyBridgeSnapshot(
        provenance=LegacySourceProvenance(
            source_label=source_label,
            sha256=hashlib.sha256(raw).hexdigest(),
            byte_length=len(raw),
            line_count=len(records),
        ),
        open_count=event_counts["OPEN"],
        close_count=event_counts["CLOSE"],
        schema_counts=tuple(sorted(schema_counts.items())),
        assessments=assessments,
        _records=records,
    )


def _domain_event_id(
    record: _LegacyRecord, event_type: LedgerEventType, *, source_label: str
) -> str:
    material = json.dumps(
        {
            "bridge_schema_version": BRIDGE_SCHEMA_VERSION,
            "domain": "ppl-02c-legacy-record",
            "event_type": event_type.value,
            "line_number": record.line_number,
            "line_sha256": record.line_sha256,
            "source_label": source_label,
        },
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    identity_digest = hashlib.sha256(material).hexdigest()
    return (
        f"legacy-v{BRIDGE_SCHEMA_VERSION}-line-{record.line_number}-"
        f"{record.line_sha256}-{identity_digest}"
    )


def _epoch_event_id(context: LegacyImportContext) -> str:
    material = json.dumps(
        {
            "bridge_schema_version": BRIDGE_SCHEMA_VERSION,
            "code_sha": context.code_sha,
            "config_snapshot_hash": context.config_snapshot_hash,
            "epoch_created_at": float(context.epoch_created_at),
            "initial_virtual_capital": float(context.initial_virtual_capital),
            "paper_epoch_id": context.paper_epoch_id,
            "provenance": context.provenance.value,
        },
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"legacy-epoch-{hashlib.sha256(material).hexdigest()}"


def build_legacy_import_plan(
    snapshot: LegacyBridgeSnapshot, context: LegacyImportContext
) -> LegacyImportPlan:
    """Build a complete deterministic plan, or an empty BLOCKED plan."""
    if context.expected_source_sha256 != snapshot.provenance.sha256:
        raise LegacyImportContextError(
            "explicit context source digest does not match inspected snapshot"
        )
    if snapshot.status is LegacyImportPlanStatus.BLOCKED:
        return LegacyImportPlan(
            provenance=snapshot.provenance,
            context=context,
            status=LegacyImportPlanStatus.BLOCKED,
            assessments=snapshot.assessments,
            events=(),
        )

    if snapshot._records:
        first_timestamp = min(float(record.data["ts"]) for record in snapshot._records)
        if context.epoch_created_at > first_timestamp:
            raise LegacyImportContextError(
                "epoch_created_at must not be later than legacy event timestamps"
            )

    assessments = {item.trade_id: item for item in snapshot.assessments}
    events: list[LedgerEvent] = [
        make_epoch_created_event(
            event_id=_epoch_event_id(context),
            paper_epoch_id=context.paper_epoch_id,
            sequence=1,
            timestamp=context.epoch_created_at,
            initial_virtual_capital=context.initial_virtual_capital,
            code_sha=context.code_sha,
            config_snapshot_hash=context.config_snapshot_hash,
        )
    ]

    for record in snapshot._records:
        data = record.data
        trade_id = str(data["trade_id"])
        assessment = assessments[trade_id]
        sequence = record.line_number + 1
        timestamp = float(data["ts"])

        if data["event"] == "OPEN":
            _, entry_fee = _explicit_fee(data, "fee_entry_usd")
            if entry_fee is None:
                raise LegacyImportContextError(
                    "READY snapshot invariant violated: OPEN entry fee is absent"
                )
            event = make_position_opened_event(
                event_id=_domain_event_id(
                    record,
                    LedgerEventType.POSITION_OPENED,
                    source_label=snapshot.provenance.source_label,
                ),
                paper_epoch_id=context.paper_epoch_id,
                sequence=sequence,
                timestamp=timestamp,
                trade_id=trade_id,
                symbol=str(data["symbol"]),
                side=str(data["side"]),
                principal=float(data["size_usd"]),
                entry_price=float(data["price"]),
                entry_fee=entry_fee,
                decision_id=None,
            )
        elif assessment.status is LegacyLifecycleStatus.IMPORTABLE_AS_UNRESOLVED:
            reason_codes = ",".join(item.value for item in assessment.reason_codes)
            event = make_position_unresolved_event(
                event_id=_domain_event_id(
                    record,
                    LedgerEventType.POSITION_UNRESOLVED,
                    source_label=snapshot.provenance.source_label,
                ),
                paper_epoch_id=context.paper_epoch_id,
                sequence=sequence,
                timestamp=timestamp,
                trade_id=trade_id,
                reason=f"legacy:{reason_codes}",
                decision_id=None,
            )
        else:
            _, exit_fee = _explicit_fee(data, "exit_fee", "fee_exit_usd")
            if exit_fee is None:
                raise LegacyImportContextError(
                    "READY snapshot invariant violated: CLOSE exit fee is absent"
                )
            event = make_position_closed_event(
                event_id=_domain_event_id(
                    record,
                    LedgerEventType.POSITION_CLOSED,
                    source_label=snapshot.provenance.source_label,
                ),
                paper_epoch_id=context.paper_epoch_id,
                sequence=sequence,
                timestamp=timestamp,
                trade_id=trade_id,
                exit_price=float(data["exit_price"]),
                exit_fee=exit_fee,
                decision_id=None,
            )
        events.append(event)

    try:
        project(events)
    except LedgerReplayError as exc:
        raise LegacyImportContextError(
            f"generated complete PPL replay is invalid: {exc}"
        ) from exc

    return LegacyImportPlan(
        provenance=snapshot.provenance,
        context=context,
        status=LegacyImportPlanStatus.READY,
        assessments=snapshot.assessments,
        events=tuple(events),
    )


def apply_legacy_import_plan(
    plan: LegacyImportPlan, store: DurableEventStore
) -> tuple[AppendResult, ...]:
    """Apply one READY offline plan through PPL-02B's durable append API."""
    if plan.status is not LegacyImportPlanStatus.READY or not plan.events:
        raise LegacyImportBlockedError(
            "legacy import plan is BLOCKED; target store was not touched"
        )
    return tuple(
        store.append(plan.context.paper_epoch_id, event) for event in plan.events
    )
