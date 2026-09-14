"""Durable append-only JSONL store for PPL ``LedgerEvent`` records.

PPL-02B scope is deliberately narrow: storage, canonical serialization,
event identity, per-epoch ordering, corruption detection, and deterministic
reload.  This module has no PAPER runtime wiring and contains no position or
financial projection logic.  Replay remains the responsibility of
``paper_trading.paper_portfolio_ledger.project``.

The caller must provide an explicit root directory.  The store has no
production default, environment lookup, singleton, or import-time I/O.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from paper_trading.ledger_events import LedgerEvent, LedgerEventType, Side

_SCHEMA_VERSION = 1
_TOP_LEVEL_FIELDS = frozenset(
    {
        "event_id",
        "paper_epoch_id",
        "sequence",
        "event_type",
        "timestamp",
        "trade_id",
        "decision_id",
        "payload",
        "schema_version",
    }
)
_PAYLOAD_FIELDS = {
    LedgerEventType.EPOCH_CREATED: frozenset(
        {"initial_virtual_capital", "code_sha", "config_snapshot_hash"}
    ),
    LedgerEventType.POSITION_OPENED: frozenset(
        {"symbol", "side", "principal", "entry_price", "entry_fee"}
    ),
    LedgerEventType.POSITION_CLOSED: frozenset({"exit_price", "exit_fee"}),
    LedgerEventType.POSITION_UNRESOLVED: frozenset({"reason"}),
    LedgerEventType.RECOVERY_COMPLETED: frozenset(
        {"restored_count", "unresolved_count"}
    ),
}
_EPOCH_FILENAME_RE = re.compile(r"^[0-9a-f]{64}\.jsonl$")


class EventStoreError(Exception):
    """Base class for deterministic PPL durable-store contract failures."""


class EpochNotFoundError(EventStoreError):
    """The requested epoch has no durable event file."""


class EventSerializationError(EventStoreError):
    """An in-memory event cannot be represented by the frozen wire schema."""


class StoreCorruptionError(EventStoreError):
    """Persisted bytes violate the durable-store contract."""


class EventDeserializationError(StoreCorruptionError):
    """A persisted JSON record cannot become a supported ``LedgerEvent``."""


class UnsupportedSchemaVersionError(EventStoreError):
    """An event uses a schema version unsupported by PPL-02B."""


class EventIdentityCollisionError(EventStoreError):
    """An ``event_id`` was reused for a different canonical event."""


class StoreEpochMismatchError(EventStoreError):
    """An event, requested stream, or physical epoch partition disagrees."""


class StoreSequenceRegressionError(EventStoreError):
    """A new or persisted event regresses/duplicates sequence ordering."""


class StoreSequenceGapError(EventStoreError):
    """A new or persisted event skips an expected sequence number."""


class AppendStatus(str, Enum):
    """Closed result vocabulary for a completed append attempt."""

    APPENDED = "APPENDED"
    ALREADY_EXISTS = "ALREADY_EXISTS"


@dataclass(frozen=True)
class AppendResult:
    """Deterministic append outcome; both states guarantee no hidden write."""

    status: AppendStatus
    event_id: str
    paper_epoch_id: str
    sequence: int


@dataclass(frozen=True)
class _StoredEvent:
    event: LedgerEvent
    canonical_line: bytes
    path: Path
    record_number: int


class _DuplicateJSONKey(ValueError):
    pass


def _epoch_digest(paper_epoch_id: str) -> str:
    return hashlib.sha256(paper_epoch_id.encode("utf-8")).hexdigest()


def _require_epoch_id(paper_epoch_id: Any) -> str:
    if not isinstance(paper_epoch_id, str) or not paper_epoch_id:
        raise StoreEpochMismatchError("paper_epoch_id must be a non-empty string")
    return paper_epoch_id


def _jsonable(value: Any, *, location: str) -> Any:
    """Convert recursively-frozen domain payloads to strict JSON values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EventSerializationError(f"{location} must be finite, got {value!r}")
        return value
    if isinstance(value, Mapping):
        converted: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise EventSerializationError(
                    f"{location} contains non-string mapping key {key!r}"
                )
            converted[key] = _jsonable(child, location=f"{location}.{key}")
        return converted
    if isinstance(value, (list, tuple)):
        return [
            _jsonable(child, location=f"{location}[{index}]")
            for index, child in enumerate(value)
        ]
    raise EventSerializationError(
        f"{location} contains unsupported value type {type(value).__name__}"
    )


def _require_number(value: Any, *, field: str, error_type: type[Exception]) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise error_type(f"{field} must be a JSON number, got {value!r}")
    try:
        finite = math.isfinite(value)
    except (TypeError, OverflowError) as exc:
        raise error_type(f"{field} is outside the supported numeric range") from exc
    if not finite:
        raise error_type(f"{field} must be finite, got {value!r}")


def _require_string(value: Any, *, field: str, error_type: type[Exception]) -> None:
    if not isinstance(value, str):
        raise error_type(f"{field} must be a string, got {value!r}")


def _validate_payload(
    event_type: LedgerEventType,
    payload: Mapping[str, Any],
    *,
    error_type: type[Exception],
) -> None:
    expected_fields = _PAYLOAD_FIELDS[event_type]
    actual_fields = frozenset(payload)
    if actual_fields != expected_fields:
        missing = sorted(expected_fields - actual_fields)
        extra = sorted(actual_fields - expected_fields)
        raise error_type(
            f"{event_type.value} payload fields mismatch: "
            f"missing={missing}, extra={extra}"
        )

    if event_type is LedgerEventType.EPOCH_CREATED:
        _require_number(
            payload["initial_virtual_capital"],
            field="payload.initial_virtual_capital",
            error_type=error_type,
        )
        _require_string(
            payload["code_sha"], field="payload.code_sha", error_type=error_type
        )
        _require_string(
            payload["config_snapshot_hash"],
            field="payload.config_snapshot_hash",
            error_type=error_type,
        )
    elif event_type is LedgerEventType.POSITION_OPENED:
        _require_string(
            payload["symbol"], field="payload.symbol", error_type=error_type
        )
        _require_string(payload["side"], field="payload.side", error_type=error_type)
        if payload["side"] not in {Side.LONG.value, Side.SHORT.value}:
            raise error_type(
                f"payload.side must be canonical LONG or SHORT, got {payload['side']!r}"
            )
        for field in ("principal", "entry_price", "entry_fee"):
            _require_number(
                payload[field], field=f"payload.{field}", error_type=error_type
            )
    elif event_type is LedgerEventType.POSITION_CLOSED:
        for field in ("exit_price", "exit_fee"):
            _require_number(
                payload[field], field=f"payload.{field}", error_type=error_type
            )
    elif event_type is LedgerEventType.POSITION_UNRESOLVED:
        _require_string(
            payload["reason"], field="payload.reason", error_type=error_type
        )
    elif event_type is LedgerEventType.RECOVERY_COMPLETED:
        for field in ("restored_count", "unresolved_count"):
            value = payload[field]
            if not isinstance(value, int) or isinstance(value, bool):
                raise error_type(f"payload.{field} must be an integer, got {value!r}")


def _event_to_record(event: LedgerEvent) -> dict[str, Any]:
    if not isinstance(event, LedgerEvent):
        raise EventSerializationError(
            f"event must be LedgerEvent, got {type(event).__name__}"
        )
    if not isinstance(event.event_id, str) or not event.event_id:
        raise EventSerializationError("event_id must be a non-empty string")
    _require_epoch_id(event.paper_epoch_id)
    if not isinstance(event.sequence, int) or isinstance(event.sequence, bool):
        raise EventSerializationError("sequence must be an integer, not boolean")
    if event.sequence < 1:
        raise EventSerializationError("sequence must be >= 1")
    if not isinstance(event.event_type, LedgerEventType):
        raise EventSerializationError(
            f"event_type must be LedgerEventType, got {event.event_type!r}"
        )
    _require_number(
        event.timestamp, field="timestamp", error_type=EventSerializationError
    )
    if event.trade_id is not None and not isinstance(event.trade_id, str):
        raise EventSerializationError("trade_id must be a string or null")
    if event.decision_id is not None and not isinstance(event.decision_id, str):
        raise EventSerializationError("decision_id must be a string or null")
    if event.schema_version != _SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            f"unsupported schema_version={event.schema_version!r}; "
            f"supported={_SCHEMA_VERSION}"
        )

    payload = _jsonable(event.payload, location="payload")
    if not isinstance(payload, dict):
        raise EventSerializationError("payload must be a mapping")
    _validate_payload(event.event_type, payload, error_type=EventSerializationError)

    return {
        "event_id": event.event_id,
        "paper_epoch_id": event.paper_epoch_id,
        "sequence": event.sequence,
        "event_type": event.event_type.value,
        "timestamp": event.timestamp,
        "trade_id": event.trade_id,
        "decision_id": event.decision_id,
        "payload": payload,
        "schema_version": event.schema_version,
    }


def _canonical_line(event: LedgerEvent) -> bytes:
    record = _event_to_record(event)
    try:
        encoded = json.dumps(
            record,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise EventSerializationError(
            f"canonical JSON serialization failed: {exc}"
        ) from exc
    return encoded + b"\n"


def _object_without_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKey(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r}")


def _record_to_event(record: Any, *, source: Path, record_number: int) -> LedgerEvent:
    context = f"{source}:record {record_number}"
    if not isinstance(record, dict):
        raise EventDeserializationError(f"{context}: top-level JSON must be an object")
    actual_fields = frozenset(record)
    if actual_fields != _TOP_LEVEL_FIELDS:
        missing = sorted(_TOP_LEVEL_FIELDS - actual_fields)
        extra = sorted(actual_fields - _TOP_LEVEL_FIELDS)
        raise EventDeserializationError(
            f"{context}: top-level fields mismatch: missing={missing}, extra={extra}"
        )

    event_id = record["event_id"]
    paper_epoch_id = record["paper_epoch_id"]
    sequence = record["sequence"]
    event_type_raw = record["event_type"]
    timestamp = record["timestamp"]
    trade_id = record["trade_id"]
    decision_id = record["decision_id"]
    payload = record["payload"]
    schema_version = record["schema_version"]

    if not isinstance(event_id, str) or not event_id:
        raise EventDeserializationError(
            f"{context}: event_id must be a non-empty string"
        )
    if not isinstance(paper_epoch_id, str) or not paper_epoch_id:
        raise EventDeserializationError(
            f"{context}: paper_epoch_id must be a non-empty string"
        )
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise EventDeserializationError(f"{context}: sequence must be an integer >= 1")
    if not isinstance(event_type_raw, str):
        raise EventDeserializationError(f"{context}: event_type must be a string")
    try:
        event_type = LedgerEventType(event_type_raw)
    except ValueError as exc:
        raise EventDeserializationError(
            f"{context}: unsupported event_type={event_type_raw!r}"
        ) from exc
    _require_number(
        timestamp,
        field=f"{context}: timestamp",
        error_type=EventDeserializationError,
    )
    if trade_id is not None and not isinstance(trade_id, str):
        raise EventDeserializationError(f"{context}: trade_id must be a string or null")
    if decision_id is not None and not isinstance(decision_id, str):
        raise EventDeserializationError(
            f"{context}: decision_id must be a string or null"
        )
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise EventDeserializationError(f"{context}: schema_version must be an integer")
    if schema_version != _SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            f"{context}: unsupported schema_version={schema_version!r}; "
            f"supported={_SCHEMA_VERSION}"
        )
    if not isinstance(payload, dict):
        raise EventDeserializationError(f"{context}: payload must be an object")
    _validate_payload(event_type, payload, error_type=EventDeserializationError)

    try:
        return LedgerEvent(
            event_id=event_id,
            paper_epoch_id=paper_epoch_id,
            sequence=sequence,
            event_type=event_type,
            timestamp=timestamp,
            trade_id=trade_id,
            decision_id=decision_id,
            payload=payload,
            schema_version=schema_version,
        )
    except (TypeError, ValueError) as exc:
        raise EventDeserializationError(
            f"{context}: LedgerEvent validation failed: {exc}"
        ) from exc


def _decode_record(
    raw_record: bytes, *, source: Path, record_number: int
) -> LedgerEvent:
    context = f"{source}:record {record_number}"
    try:
        text = raw_record.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise EventDeserializationError(f"{context}: invalid UTF-8") from exc
    try:
        record = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (_DuplicateJSONKey, json.JSONDecodeError, ValueError) as exc:
        raise EventDeserializationError(f"{context}: invalid JSON: {exc}") from exc
    return _record_to_event(record, source=source, record_number=record_number)


class DurableEventStore:
    """Explicit-root, append-only, replayable PPL event store."""

    def __init__(self, root_dir: os.PathLike[str] | str) -> None:
        self._root = Path(root_dir)
        self._epochs_dir = self._root / "epochs"
        self._lock_path = self._root / ".ppl-event-store.lock"

    def append(self, expected_epoch_id: str, event: LedgerEvent) -> AppendResult:
        """Durably append one event or return exact-event idempotence.

        Native ``OSError`` failures from locking or the durability boundary
        propagate.  No success result is created before the file and, for a
        newly-created epoch file, its parent directory are synced.
        """
        expected_epoch_id = _require_epoch_id(expected_epoch_id)
        canonical_line = _canonical_line(event)
        if event.paper_epoch_id != expected_epoch_id:
            raise StoreEpochMismatchError(
                f"event paper_epoch_id={event.paper_epoch_id!r} != "
                f"expected_epoch_id={expected_epoch_id!r}"
            )

        self._ensure_directories()
        with self._lock(exclusive=True):
            epochs, identities = self._scan_store()

            existing = identities.get(event.event_id)
            if existing is not None:
                if existing.canonical_line == canonical_line:
                    self._durably_confirm_existing(existing.path)
                    return AppendResult(
                        status=AppendStatus.ALREADY_EXISTS,
                        event_id=event.event_id,
                        paper_epoch_id=event.paper_epoch_id,
                        sequence=event.sequence,
                    )
                raise EventIdentityCollisionError(
                    f"event_id={event.event_id!r} already identifies a "
                    "different canonical event"
                )

            epoch_events = epochs.get(expected_epoch_id, ())
            expected_sequence = (
                epoch_events[-1].event.sequence + 1 if epoch_events else 1
            )
            if event.sequence < expected_sequence:
                raise StoreSequenceRegressionError(
                    f"sequence regression for epoch={expected_epoch_id!r}: "
                    f"got {event.sequence}, expected {expected_sequence}"
                )
            if event.sequence > expected_sequence:
                raise StoreSequenceGapError(
                    f"sequence gap for epoch={expected_epoch_id!r}: "
                    f"got {event.sequence}, expected {expected_sequence}"
                )

            path = self._epoch_path(expected_epoch_id)
            newly_created = not path.exists()
            self._durable_append(path, canonical_line)
            if newly_created:
                self._fsync_directory(self._epochs_dir)

            return AppendResult(
                status=AppendStatus.APPENDED,
                event_id=event.event_id,
                paper_epoch_id=event.paper_epoch_id,
                sequence=event.sequence,
            )

    def load_epoch(self, paper_epoch_id: str) -> tuple[LedgerEvent, ...]:
        """Return one complete validated epoch in physical/sequence order.

        Any corruption fails the whole operation.  No valid prefix is ever
        returned and records are never sorted or repaired.
        """
        paper_epoch_id = _require_epoch_id(paper_epoch_id)
        path = self._epoch_path(paper_epoch_id)
        if not path.exists():
            raise EpochNotFoundError(
                f"no durable event history for epoch={paper_epoch_id!r}"
            )
        with self._lock(exclusive=False):
            epochs, _ = self._scan_store()
            stored = epochs.get(paper_epoch_id)
            if stored is None:
                raise EpochNotFoundError(
                    f"no durable event history for epoch={paper_epoch_id!r}"
                )
            return tuple(item.event for item in stored)

    def _epoch_path(self, paper_epoch_id: str) -> Path:
        return self._epochs_dir / f"{_epoch_digest(paper_epoch_id)}.jsonl"

    def _ensure_directories(self) -> None:
        missing_directories: list[Path] = []
        candidate = self._epochs_dir
        while not candidate.exists():
            missing_directories.append(candidate)
            parent = candidate.parent
            if parent == candidate:
                break
            candidate = parent

        self._epochs_dir.mkdir(parents=True, exist_ok=True)
        if self._epochs_dir.is_symlink() or not self._epochs_dir.is_dir():
            raise StoreCorruptionError(
                f"epoch store must be a real directory, not a symlink: "
                f"{self._epochs_dir}"
            )

        # Persist every directory entry created by mkdir(parents=True).  The
        # event file is synced later, but it is not durably reachable after a
        # crash unless each newly-created directory is also linked durably
        # from its parent.
        for directory in missing_directories:
            self._fsync_directory(directory.parent)

        if not missing_directories and not any(self._epochs_dir.iterdir()):
            # A previous first append may have created this empty hierarchy
            # and then reported a directory-sync failure.  On retry there is
            # no creation history left in memory, so reconfirm every ancestor
            # up to the filesystem root before an event can report success.
            directory = self._root
            while True:
                self._fsync_directory(directory)
                parent = directory.parent
                if parent == directory:
                    break
                directory = parent

    @contextmanager
    def _lock(self, *, exclusive: bool) -> Iterator[None]:
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        with self._lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), mode)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _scan_store(
        self,
    ) -> tuple[dict[str, tuple[_StoredEvent, ...]], dict[str, _StoredEvent]]:
        epochs: dict[str, tuple[_StoredEvent, ...]] = {}
        identities: dict[str, _StoredEvent] = {}
        if not self._epochs_dir.exists():
            return epochs, identities

        for path in sorted(self._epochs_dir.iterdir(), key=lambda item: item.name):
            if path.is_symlink() or not path.is_file():
                raise StoreCorruptionError(
                    f"unexpected non-regular-file entry in epoch store: {path}"
                )
            if not _EPOCH_FILENAME_RE.fullmatch(path.name):
                raise StoreCorruptionError(
                    f"unexpected epoch-store filename: {path.name!r}"
                )
            stored_events = self._read_epoch_file(path)
            epoch_id = stored_events[0].event.paper_epoch_id
            if epoch_id in epochs:
                raise StoreCorruptionError(
                    f"epoch={epoch_id!r} is represented by multiple files"
                )
            epochs[epoch_id] = stored_events
            for item in stored_events:
                prior = identities.get(item.event.event_id)
                if prior is not None:
                    raise StoreCorruptionError(
                        f"duplicate physical event_id={item.event.event_id!r} "
                        f"at {prior.path}:record {prior.record_number} and "
                        f"{item.path}:record {item.record_number}"
                    )
                identities[item.event.event_id] = item
        return epochs, identities

    def _read_epoch_file(self, path: Path) -> tuple[_StoredEvent, ...]:
        data = path.read_bytes()
        if not data:
            raise StoreCorruptionError(f"empty durable epoch file: {path}")
        if not data.endswith(b"\n"):
            raise StoreCorruptionError(
                f"durable epoch file lacks final newline: {path}"
            )

        events: list[_StoredEvent] = []
        epoch_id: str | None = None
        expected_sequence = 1
        seen_ids: set[str] = set()

        for record_number, raw_line in enumerate(data.splitlines(keepends=True), 1):
            if not raw_line.endswith(b"\n"):
                raise StoreCorruptionError(
                    f"{path}:record {record_number}: incomplete record"
                )
            raw_record = raw_line[:-1]
            if not raw_record.strip():
                raise StoreCorruptionError(
                    f"{path}:record {record_number}: blank record"
                )
            event = _decode_record(raw_record, source=path, record_number=record_number)
            canonical_line = _canonical_line(event)
            if raw_line != canonical_line:
                raise StoreCorruptionError(
                    f"{path}:record {record_number}: record is not in the "
                    "canonical PPL-02B JSON encoding"
                )

            if epoch_id is None:
                epoch_id = event.paper_epoch_id
                expected_name = f"{_epoch_digest(epoch_id)}.jsonl"
                if path.name != expected_name:
                    raise StoreEpochMismatchError(
                        f"{path}: filename does not match embedded "
                        f"paper_epoch_id={epoch_id!r}"
                    )
            elif event.paper_epoch_id != epoch_id:
                raise StoreEpochMismatchError(
                    f"{path}:record {record_number}: mixed epoch "
                    f"{event.paper_epoch_id!r}, expected {epoch_id!r}"
                )

            if event.event_id in seen_ids:
                raise StoreCorruptionError(
                    f"{path}:record {record_number}: duplicate physical "
                    f"event_id={event.event_id!r}"
                )
            seen_ids.add(event.event_id)

            if event.sequence < expected_sequence:
                raise StoreSequenceRegressionError(
                    f"{path}:record {record_number}: sequence regression: "
                    f"got {event.sequence}, expected {expected_sequence}"
                )
            if event.sequence > expected_sequence:
                raise StoreSequenceGapError(
                    f"{path}:record {record_number}: sequence gap: "
                    f"got {event.sequence}, expected {expected_sequence}"
                )
            expected_sequence += 1
            events.append(
                _StoredEvent(
                    event=event,
                    canonical_line=canonical_line,
                    path=path,
                    record_number=record_number,
                )
            )

        return tuple(events)

    @staticmethod
    def _durable_append(path: Path, line: bytes) -> None:
        with path.open("ab") as stream:
            written = stream.write(line)
            if written != len(line):
                raise OSError(
                    f"short write for {path}: wrote {written} of {len(line)} bytes"
                )
            stream.flush()
            os.fsync(stream.fileno())

    def _durably_confirm_existing(self, path: Path) -> None:
        """Re-establish durability before returning idempotent success.

        A prior append may have written visible bytes and then reported an
        ``fsync`` failure.  Seeing the canonical event on retry is therefore
        not enough: sync its file and parent directory before returning
        ``ALREADY_EXISTS``.
        """
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
        self._fsync_directory(self._epochs_dir)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


__all__ = [
    "AppendResult",
    "AppendStatus",
    "DurableEventStore",
    "EpochNotFoundError",
    "EventDeserializationError",
    "EventIdentityCollisionError",
    "EventSerializationError",
    "EventStoreError",
    "StoreCorruptionError",
    "StoreEpochMismatchError",
    "StoreSequenceGapError",
    "StoreSequenceRegressionError",
    "UnsupportedSchemaVersionError",
]
