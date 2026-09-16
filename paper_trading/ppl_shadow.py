"""PPL-02D non-authoritative SHADOW projection for MEXC_SIM PAPER facts.

The module is deliberately downstream of legacy simulation semantics. It never
places/closes an order and never reads ``paper_trades.jsonl`` as runtime input.
A configured shadow stream receives immutable OPEN/CLOSE facts, persists them
through the existing PPL-02B ``DurableEventStore``, and replays the complete
PPL projection after every successful append.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from paper_trading.durable_event_store import (
    AppendResult,
    AppendStatus,
    DurableEventStore,
    EpochNotFoundError,
)
from paper_trading.ledger_events import (
    LedgerEvent,
    LedgerEventType,
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
    normalize_side,
)
from paper_trading.paper_portfolio_ledger import PaperPortfolioState, project

_MANIFEST_SCHEMA_VERSION = 1
_SHADOW_DOMAIN = "PPL-02D-SHADOW-V1"
_NUMERIC_ABS_TOL = 1e-9
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "paper_epoch_id",
        "created_at",
        "initial_virtual_capital",
        "code_sha",
        "config_snapshot_hash",
    }
)


class ShadowStatus(str, Enum):
    OFF = "OFF"
    WAITING_CLEAN_BOUNDARY = "WAITING_CLEAN_BOUNDARY"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"


class PPLShadowError(Exception):
    """Base class for PPL-02D SHADOW failures."""


class ShadowConfigError(PPLShadowError):
    pass


class ShadowManifestError(ShadowConfigError):
    pass


class ShadowReconciliationError(PPLShadowError):
    pass


class ShadowIdentityCollisionError(PPLShadowError):
    pass


class _DuplicateJSONKey(ValueError):
    pass


def _require_finite(
    name: str,
    value: Any,
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be a real number, got {value!r}")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    if positive and value <= 0:
        raise ValueError(f"{name} must be > 0, got {value!r}")
    if non_negative and value < 0:
        raise ValueError(f"{name} must be >= 0, got {value!r}")
    return value


def _same_number(left: float, right: float) -> bool:
    return math.isclose(
        float(left),
        float(right),
        rel_tol=0.0,
        abs_tol=_NUMERIC_ABS_TOL,
    )


def _pairs_without_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKey(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r}")


@dataclass(frozen=True)
class ShadowEpochManifest:
    paper_epoch_id: str
    created_at: float
    initial_virtual_capital: float
    code_sha: str
    config_snapshot_hash: str
    schema_version: int = _MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.paper_epoch_id, str) or not self.paper_epoch_id.strip():
            raise ValueError("paper_epoch_id must be a non-empty string")
        if not isinstance(self.code_sha, str) or not self.code_sha.strip():
            raise ValueError("code_sha must be a non-empty string")
        if (
            not isinstance(self.config_snapshot_hash, str)
            or not self.config_snapshot_hash.strip()
        ):
            raise ValueError("config_snapshot_hash must be a non-empty string")
        if self.schema_version != _MANIFEST_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported manifest schema_version={self.schema_version!r}; "
                f"supported={_MANIFEST_SCHEMA_VERSION}"
            )
        object.__setattr__(
            self,
            "created_at",
            _require_finite("created_at", self.created_at),
        )
        object.__setattr__(
            self,
            "initial_virtual_capital",
            _require_finite(
                "initial_virtual_capital",
                self.initial_virtual_capital,
                positive=True,
            ),
        )


@dataclass(frozen=True)
class ShadowLegacyPosition:
    trade_id: str
    symbol: str
    side: str
    principal: float
    entry_price: float
    entry_fee: float

    def __post_init__(self) -> None:
        if not self.trade_id:
            raise ValueError("trade_id must be non-empty")
        if not self.symbol:
            raise ValueError("symbol must be non-empty")
        normalize_side(self.side)
        object.__setattr__(
            self,
            "principal",
            _require_finite("principal", self.principal, positive=True),
        )
        object.__setattr__(
            self,
            "entry_price",
            _require_finite("entry_price", self.entry_price, positive=True),
        )
        object.__setattr__(
            self,
            "entry_fee",
            _require_finite("entry_fee", self.entry_fee, non_negative=True),
        )


@dataclass(frozen=True)
class ShadowOpenFact(ShadowLegacyPosition):
    timestamp: float = 0.0
    decision_id: Optional[str] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(
            self,
            "timestamp",
            _require_finite("timestamp", self.timestamp),
        )
        if self.decision_id is not None and (
            not isinstance(self.decision_id, str) or not self.decision_id
        ):
            raise ValueError("decision_id must be a non-empty string or None")


@dataclass(frozen=True)
class ShadowCloseFact:
    trade_id: str
    exit_price: float
    exit_fee: float
    timestamp: float
    decision_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.trade_id:
            raise ValueError("trade_id must be non-empty")
        object.__setattr__(
            self,
            "exit_price",
            _require_finite("exit_price", self.exit_price, positive=True),
        )
        object.__setattr__(
            self,
            "exit_fee",
            _require_finite("exit_fee", self.exit_fee, non_negative=True),
        )
        object.__setattr__(
            self,
            "timestamp",
            _require_finite("timestamp", self.timestamp),
        )
        if self.decision_id is not None and (
            not isinstance(self.decision_id, str) or not self.decision_id
        ):
            raise ValueError("decision_id must be a non-empty string or None")


@dataclass(frozen=True)
class ShadowRuntimeSnapshot:
    status: ShadowStatus
    paper_epoch_id: str
    event_count: int
    last_sequence: int
    last_error: Optional[str]


def load_shadow_manifest(path: os.PathLike[str] | str) -> ShadowEpochManifest:
    manifest_path = Path(path)
    try:
        info = manifest_path.lstat()
    except FileNotFoundError as exc:
        raise ShadowManifestError(f"shadow manifest not found: {manifest_path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ShadowManifestError(
            f"shadow manifest must be a regular non-symlink file: {manifest_path}"
        )
    try:
        raw = manifest_path.read_bytes()
        text = raw.decode("utf-8", errors="strict")
        data = json.loads(
            text,
            object_pairs_hook=_pairs_without_duplicates,
            parse_constant=_reject_json_constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _DuplicateJSONKey,
        ValueError,
    ) as exc:
        raise ShadowManifestError(
            f"invalid shadow manifest {manifest_path}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise ShadowManifestError("shadow manifest top-level JSON must be an object")
    actual = frozenset(data)
    if actual != _MANIFEST_FIELDS:
        raise ShadowManifestError(
            "shadow manifest fields mismatch: "
            f"missing={sorted(_MANIFEST_FIELDS - actual)}, "
            f"extra={sorted(actual - _MANIFEST_FIELDS)}"
        )
    try:
        return ShadowEpochManifest(
            paper_epoch_id=data["paper_epoch_id"],
            created_at=data["created_at"],
            initial_virtual_capital=data["initial_virtual_capital"],
            code_sha=data["code_sha"],
            config_snapshot_hash=data["config_snapshot_hash"],
            schema_version=data["schema_version"],
        )
    except (TypeError, ValueError) as exc:
        raise ShadowManifestError(f"invalid shadow manifest values: {exc}") from exc


def build_shadow_runtime_from_env(
    environ: Optional[Mapping[str, str]] = None,
) -> Optional["PPLShadowRuntime"]:
    env = os.environ if environ is None else environ
    manifest_path = str(env.get("PPL_SHADOW_MANIFEST", "") or "").strip()
    store_root = str(env.get("PPL_SHADOW_STORE_ROOT", "") or "").strip()
    if not manifest_path and not store_root:
        return None
    if not manifest_path or not store_root:
        raise ShadowConfigError(
            "PPL_SHADOW_MANIFEST and PPL_SHADOW_STORE_ROOT must be supplied together"
        )
    manifest = load_shadow_manifest(manifest_path)
    root = Path(store_root)
    if root.exists() and root.is_symlink():
        raise ShadowConfigError(
            f"PPL_SHADOW_STORE_ROOT must not be a symlink: {root}"
        )
    return PPLShadowRuntime(manifest=manifest, store=DurableEventStore(root))


def _event_id(
    paper_epoch_id: str,
    event_type: LedgerEventType,
    trade_id: str,
) -> str:
    canonical = "\x1f".join(
        (_SHADOW_DOMAIN, paper_epoch_id, event_type.value, trade_id)
    ).encode("utf-8")
    return f"ppl02d-{hashlib.sha256(canonical).hexdigest()}"


def _same_event(left: LedgerEvent, right: LedgerEvent) -> bool:
    return (
        left.event_id == right.event_id
        and left.paper_epoch_id == right.paper_epoch_id
        and left.sequence == right.sequence
        and left.event_type is right.event_type
        and _same_number(left.timestamp, right.timestamp)
        and left.trade_id == right.trade_id
        and left.decision_id == right.decision_id
        and dict(left.payload) == dict(right.payload)
        and left.schema_version == right.schema_version
    )


class PPLShadowRuntime:
    """Fail-closed, non-authoritative PPL shadow writer/projector."""

    def __init__(
        self,
        *,
        manifest: ShadowEpochManifest,
        store: DurableEventStore,
    ) -> None:
        self.manifest = manifest
        self.store = store
        self.status = ShadowStatus.WAITING_CLEAN_BOUNDARY
        self.last_error: Optional[str] = None
        self._events: tuple[LedgerEvent, ...] = ()
        self._projection: Optional[PaperPortfolioState] = None
        self._lock = threading.RLock()

    @property
    def events(self) -> tuple[LedgerEvent, ...]:
        with self._lock:
            return self._events

    @property
    def projection(self) -> Optional[PaperPortfolioState]:
        with self._lock:
            return self._projection

    def snapshot(self) -> ShadowRuntimeSnapshot:
        with self._lock:
            return ShadowRuntimeSnapshot(
                status=self.status,
                paper_epoch_id=self.manifest.paper_epoch_id,
                event_count=len(self._events),
                last_sequence=self._events[-1].sequence if self._events else 0,
                last_error=self.last_error,
            )

    def bind_legacy_state(
        self,
        *,
        available_capital: float,
        open_positions: Sequence[ShadowLegacyPosition],
    ) -> bool:
        """Activate/recover one explicit shadow epoch against MEXC_SIM state."""
        with self._lock:
            if self.status is ShadowStatus.DEGRADED:
                return False
            try:
                capital = _require_finite(
                    "available_capital",
                    available_capital,
                    non_negative=True,
                )
                legacy_positions = tuple(open_positions)
                try:
                    events = self.store.load_epoch(self.manifest.paper_epoch_id)
                except EpochNotFoundError:
                    if legacy_positions:
                        self.status = ShadowStatus.WAITING_CLEAN_BOUNDARY
                        self.last_error = (
                            "first activation requires zero MEXC_SIM open positions; "
                            f"observed={len(legacy_positions)}"
                        )
                        return False
                    if not _same_number(
                        capital,
                        self.manifest.initial_virtual_capital,
                    ):
                        raise ShadowReconciliationError(
                            "first-activation capital mismatch: "
                            f"legacy={capital!r} "
                            f"manifest={self.manifest.initial_virtual_capital!r}"
                        )
                    epoch_event = make_epoch_created_event(
                        event_id=_event_id(
                            self.manifest.paper_epoch_id,
                            LedgerEventType.EPOCH_CREATED,
                            "__EPOCH__",
                        ),
                        paper_epoch_id=self.manifest.paper_epoch_id,
                        sequence=1,
                        timestamp=self.manifest.created_at,
                        initial_virtual_capital=self.manifest.initial_virtual_capital,
                        code_sha=self.manifest.code_sha,
                        config_snapshot_hash=self.manifest.config_snapshot_hash,
                        schema_version=self.manifest.schema_version,
                    )
                    self.store.append(self.manifest.paper_epoch_id, epoch_event)
                    events = self.store.load_epoch(self.manifest.paper_epoch_id)

                state = self._validate_and_project(events)
                self._reconcile_open_positions(state, legacy_positions)
                self._events = events
                self._projection = state
                self.status = ShadowStatus.ACTIVE
                self.last_error = None
                return True
            except Exception as exc:
                self._degrade(exc)
                return False

    def observe_open(self, fact: ShadowOpenFact) -> Optional[AppendResult]:
        with self._lock:
            if self.status is not ShadowStatus.ACTIVE:
                return None
            try:
                if fact.timestamp < self.manifest.created_at - _NUMERIC_ABS_TOL:
                    raise ShadowReconciliationError(
                        "OPEN timestamp predates explicit shadow epoch creation"
                    )
                event_id = _event_id(
                    self.manifest.paper_epoch_id,
                    LedgerEventType.POSITION_OPENED,
                    fact.trade_id,
                )

                def _build(sequence: int) -> LedgerEvent:
                    return make_position_opened_event(
                        event_id=event_id,
                        paper_epoch_id=self.manifest.paper_epoch_id,
                        sequence=sequence,
                        timestamp=fact.timestamp,
                        trade_id=fact.trade_id,
                        symbol=fact.symbol,
                        side=fact.side,
                        principal=fact.principal,
                        entry_price=fact.entry_price,
                        entry_fee=fact.entry_fee,
                        decision_id=fact.decision_id,
                        schema_version=self.manifest.schema_version,
                    )

                return self._append_semantic(event_id, _build)
            except Exception as exc:
                self._degrade(exc)
                return None

    def observe_close(self, fact: ShadowCloseFact) -> Optional[AppendResult]:
        with self._lock:
            if self.status is not ShadowStatus.ACTIVE:
                return None
            try:
                if fact.timestamp < self.manifest.created_at - _NUMERIC_ABS_TOL:
                    raise ShadowReconciliationError(
                        "CLOSE timestamp predates explicit shadow epoch creation"
                    )
                event_id = _event_id(
                    self.manifest.paper_epoch_id,
                    LedgerEventType.POSITION_CLOSED,
                    fact.trade_id,
                )

                def _build(sequence: int) -> LedgerEvent:
                    return make_position_closed_event(
                        event_id=event_id,
                        paper_epoch_id=self.manifest.paper_epoch_id,
                        sequence=sequence,
                        timestamp=fact.timestamp,
                        trade_id=fact.trade_id,
                        exit_price=fact.exit_price,
                        exit_fee=fact.exit_fee,
                        decision_id=fact.decision_id,
                        schema_version=self.manifest.schema_version,
                    )

                return self._append_semantic(event_id, _build)
            except Exception as exc:
                self._degrade(exc)
                return None

    def _append_semantic(self, event_id: str, builder) -> AppendResult:
        # Refresh first so retry/restart/concurrent append is evaluated against
        # the exact durable stream before assigning a new sequence.
        events = self.store.load_epoch(self.manifest.paper_epoch_id)
        state = self._validate_and_project(events)
        self._events = events
        self._projection = state

        existing = next(
            (event for event in events if event.event_id == event_id),
            None,
        )
        if existing is not None:
            candidate = builder(existing.sequence)
            if not _same_event(existing, candidate):
                raise ShadowIdentityCollisionError(
                    f"event_id={event_id!r} already exists with different "
                    "semantic facts"
                )
            return AppendResult(
                status=AppendStatus.ALREADY_EXISTS,
                event_id=existing.event_id,
                paper_epoch_id=existing.paper_epoch_id,
                sequence=existing.sequence,
            )

        sequence = events[-1].sequence + 1
        event = builder(sequence)
        result = self.store.append(self.manifest.paper_epoch_id, event)

        refreshed = self.store.load_epoch(self.manifest.paper_epoch_id)
        refreshed_state = self._validate_and_project(refreshed)
        self._events = refreshed
        self._projection = refreshed_state
        return result

    def _validate_and_project(
        self,
        events: Sequence[LedgerEvent],
    ) -> PaperPortfolioState:
        if not events:
            raise ShadowReconciliationError("configured shadow epoch is empty")
        birth = events[0]
        if birth.event_type is not LedgerEventType.EPOCH_CREATED:
            raise ShadowReconciliationError(
                "shadow epoch does not start with EPOCH_CREATED"
            )
        if birth.paper_epoch_id != self.manifest.paper_epoch_id:
            raise ShadowReconciliationError("shadow epoch id disagrees with manifest")
        if birth.schema_version != self.manifest.schema_version:
            raise ShadowReconciliationError("shadow epoch schema disagrees with manifest")
        if not _same_number(birth.timestamp, self.manifest.created_at):
            raise ShadowReconciliationError(
                "shadow epoch created_at disagrees with manifest"
            )
        payload = birth.payload
        if not _same_number(
            float(payload["initial_virtual_capital"]),
            self.manifest.initial_virtual_capital,
        ):
            raise ShadowReconciliationError(
                "shadow epoch initial_virtual_capital disagrees with manifest"
            )
        if payload["code_sha"] != self.manifest.code_sha:
            raise ShadowReconciliationError("shadow epoch code_sha disagrees with manifest")
        if payload["config_snapshot_hash"] != self.manifest.config_snapshot_hash:
            raise ShadowReconciliationError(
                "shadow epoch config_snapshot_hash disagrees with manifest"
            )
        return project(events)

    def _reconcile_open_positions(
        self,
        state: PaperPortfolioState,
        legacy_positions: Sequence[ShadowLegacyPosition],
    ) -> None:
        legacy_by_id: dict[str, ShadowLegacyPosition] = {}
        for position in legacy_positions:
            if position.trade_id in legacy_by_id:
                raise ShadowReconciliationError(
                    f"duplicate legacy trade_id={position.trade_id!r} "
                    "during restart reconciliation"
                )
            legacy_by_id[position.trade_id] = position

        ppl_ids = set(state.open_positions)
        legacy_ids = set(legacy_by_id)
        if ppl_ids != legacy_ids:
            raise ShadowReconciliationError(
                "open-position identity mismatch: "
                f"ppl_only={sorted(ppl_ids - legacy_ids)}, "
                f"legacy_only={sorted(legacy_ids - ppl_ids)}"
            )

        for trade_id, ppl_position in state.open_positions.items():
            legacy = legacy_by_id[trade_id]
            if ppl_position.symbol != legacy.symbol:
                raise ShadowReconciliationError(
                    f"symbol mismatch for trade_id={trade_id!r}"
                )
            if ppl_position.side is not normalize_side(legacy.side):
                raise ShadowReconciliationError(
                    f"side mismatch for trade_id={trade_id!r}"
                )
            comparisons = (
                ("principal", ppl_position.principal, legacy.principal),
                ("entry_price", ppl_position.entry_price, legacy.entry_price),
                ("entry_fee", ppl_position.entry_fee, legacy.entry_fee),
            )
            for field, ppl_value, legacy_value in comparisons:
                if not _same_number(ppl_value, legacy_value):
                    raise ShadowReconciliationError(
                        f"{field} mismatch for trade_id={trade_id!r}: "
                        f"ppl={ppl_value!r} legacy={legacy_value!r}"
                    )

    def _degrade(self, exc: Exception) -> None:
        self.status = ShadowStatus.DEGRADED
        self.last_error = f"{type(exc).__name__}: {exc}"
