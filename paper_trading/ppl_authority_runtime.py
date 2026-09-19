"""PPL-02E-R4 — authoritative PAPER runtime and cutover contract.

The runtime is event-sourced and durable-first.  It never reads legacy
paper_trades.jsonl as lifecycle truth.  Legacy bytes are referenced only by the
cutover manifest's immutable boundary fingerprint and by the R3 compatibility
projector after PPL commits.

No automatic fallback to legacy exists.
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
from typing import Mapping, Optional

from paper_trading.durable_event_store import (
    AppendResult,
    DurableEventStore,
    EpochNotFoundError,
)
from paper_trading.ledger_events import (
    LedgerEvent,
    LedgerEventType,
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
    make_position_unresolved_event,
)
from paper_trading.paper_portfolio_ledger import PaperPortfolioState, project
from paper_trading.ppl_compatibility import project_ppl_to_legacy_jsonl
from paper_trading.ppl_recovery import (
    RestartDisposition,
    plan_restart_recovery,
)


_MANIFEST_SCHEMA_VERSION = 1
_PPL_EVENT_SCHEMA_VERSION = 2
_EPOCH_ROLE = "PPL_AUTHORITY_TRANSITION"
_EVENT_DOMAIN = "PPL-02E-R4-AUTHORITY-V1"
_MANIFEST_FIELDS = frozenset(
    {
        "manifest_schema_version",
        "paper_epoch_id",
        "created_at",
        "initial_virtual_capital",
        "code_sha",
        "config_snapshot_hash",
        "legacy_boundary_sha256",
        "legacy_event_count",
        "predecessor_shadow_epoch_id",
        "epoch_role",
        "ppl_event_schema_version",
    }
)


class PPLAuthorityRuntimeError(RuntimeError):
    pass


class AuthorityManifestError(PPLAuthorityRuntimeError):
    pass


class AuthorityRuntimeStatus(str, Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"


class RollbackDisposition(str, Enum):
    SAFE_BEFORE_FIRST_LIFECYCLE_EVENT = "SAFE_BEFORE_FIRST_LIFECYCLE_EVENT"
    BLOCKED_RECONCILIATION_REQUIRED = "BLOCKED_RECONCILIATION_REQUIRED"


@dataclass(frozen=True)
class AuthorityEpochManifest:
    paper_epoch_id: str
    created_at: float
    initial_virtual_capital: float
    code_sha: str
    config_snapshot_hash: str
    legacy_boundary_sha256: str
    legacy_event_count: int
    predecessor_shadow_epoch_id: str
    epoch_role: str = _EPOCH_ROLE
    ppl_event_schema_version: int = _PPL_EVENT_SCHEMA_VERSION
    manifest_schema_version: int = _MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "paper_epoch_id",
            "code_sha",
            "config_snapshot_hash",
            "legacy_boundary_sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.predecessor_shadow_epoch_id, str):
            raise ValueError("predecessor_shadow_epoch_id must be a string")
        if (
            self.predecessor_shadow_epoch_id
            and self.predecessor_shadow_epoch_id == self.paper_epoch_id
        ):
            raise ValueError("authority epoch must differ from predecessor SHADOW epoch")
        if self.epoch_role != _EPOCH_ROLE:
            raise ValueError(f"epoch_role must be {_EPOCH_ROLE!r}")
        if self.ppl_event_schema_version != _PPL_EVENT_SCHEMA_VERSION:
            raise ValueError("authoritative PPL event schema must be v2")
        if self.manifest_schema_version != _MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported authority manifest schema")
        if (
            not isinstance(self.legacy_event_count, int)
            or isinstance(self.legacy_event_count, bool)
            or self.legacy_event_count < 0
        ):
            raise ValueError("legacy_event_count must be a non-negative integer")
        for name in ("created_at", "initial_virtual_capital"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{name} must be numeric")
            value = float(value)
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
            if name == "initial_virtual_capital" and value <= 0:
                raise ValueError("initial_virtual_capital must be > 0")
            object.__setattr__(self, name, value)


@dataclass(frozen=True)
class CutoverQuiescence:
    legacy_open_positions: int
    legacy_pending_orders: int
    legacy_transitions_in_flight: int
    legacy_process_stopped: bool

    @property
    def quiescent(self) -> bool:
        return (
            self.legacy_process_stopped
            and self.legacy_open_positions == 0
            and self.legacy_pending_orders == 0
            and self.legacy_transitions_in_flight == 0
        )


@dataclass(frozen=True)
class AuthorityRuntimeView:
    status: AuthorityRuntimeStatus
    paper_epoch_id: str
    last_error: Optional[str]
    projection: PaperPortfolioState
    events: tuple[LedgerEvent, ...]


def _count_nonempty_lines(raw: bytes) -> int:
    return sum(bool(line.strip()) for line in raw.splitlines())


def build_cutover_manifest(
    *,
    paper_epoch_id: str,
    created_at: float,
    initial_virtual_capital: float,
    code_sha: str,
    config_snapshot_hash: str,
    legacy_log_bytes: bytes,
    quiescence: CutoverQuiescence,
    predecessor_shadow_epoch_id: str = "",
) -> AuthorityEpochManifest:
    """Create an in-memory authority manifest only from a proven clean boundary."""

    if not quiescence.quiescent:
        raise AuthorityManifestError(
            "cutover requires stopped legacy process, zero open positions, "
            "zero pending orders and zero lifecycle transition in flight"
        )
    return AuthorityEpochManifest(
        paper_epoch_id=paper_epoch_id,
        created_at=created_at,
        initial_virtual_capital=initial_virtual_capital,
        code_sha=code_sha,
        config_snapshot_hash=config_snapshot_hash,
        legacy_boundary_sha256=hashlib.sha256(legacy_log_bytes).hexdigest(),
        legacy_event_count=_count_nonempty_lines(legacy_log_bytes),
        predecessor_shadow_epoch_id=predecessor_shadow_epoch_id,
    )


def write_authority_manifest(
    path: os.PathLike[str] | str,
    manifest: AuthorityEpochManifest,
) -> None:
    """Write one explicit cutover manifest; existing files are never replaced."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "manifest_schema_version": manifest.manifest_schema_version,
        "paper_epoch_id": manifest.paper_epoch_id,
        "created_at": manifest.created_at,
        "initial_virtual_capital": manifest.initial_virtual_capital,
        "code_sha": manifest.code_sha,
        "config_snapshot_hash": manifest.config_snapshot_hash,
        "legacy_boundary_sha256": manifest.legacy_boundary_sha256,
        "legacy_event_count": manifest.legacy_event_count,
        "predecessor_shadow_epoch_id": manifest.predecessor_shadow_epoch_id,
        "epoch_role": manifest.epoch_role,
        "ppl_event_schema_version": manifest.ppl_event_schema_version,
    }
    encoded = (
        json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            target.unlink()
        except OSError:
            pass
        raise


def load_authority_manifest(path: os.PathLike[str] | str) -> AuthorityEpochManifest:
    target = Path(path)
    try:
        info = target.lstat()
    except FileNotFoundError as exc:
        raise AuthorityManifestError(f"authority manifest not found: {target}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise AuthorityManifestError("authority manifest must be a regular non-symlink file")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AuthorityManifestError(f"invalid authority manifest: {exc}") from exc
    if not isinstance(data, dict) or frozenset(data) != _MANIFEST_FIELDS:
        raise AuthorityManifestError("authority manifest fields mismatch")
    try:
        return AuthorityEpochManifest(
            paper_epoch_id=data["paper_epoch_id"],
            created_at=data["created_at"],
            initial_virtual_capital=data["initial_virtual_capital"],
            code_sha=data["code_sha"],
            config_snapshot_hash=data["config_snapshot_hash"],
            legacy_boundary_sha256=data["legacy_boundary_sha256"],
            legacy_event_count=data["legacy_event_count"],
            predecessor_shadow_epoch_id=data["predecessor_shadow_epoch_id"],
            epoch_role=data["epoch_role"],
            ppl_event_schema_version=data["ppl_event_schema_version"],
            manifest_schema_version=data["manifest_schema_version"],
        )
    except (TypeError, ValueError) as exc:
        raise AuthorityManifestError(f"invalid authority manifest values: {exc}") from exc


def _event_id(epoch_id: str, event_type: LedgerEventType, trade_id: str) -> str:
    raw = "\x1f".join((_EVENT_DOMAIN, epoch_id, event_type.value, trade_id))
    return f"ppl02e-{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


class PPLAuthorityRuntime:
    """Single authoritative durable PAPER lifecycle writer."""

    def __init__(
        self,
        *,
        manifest: AuthorityEpochManifest,
        store: DurableEventStore,
        compatibility_path: str | Path | None = None,
    ) -> None:
        self.manifest = manifest
        self.store = store
        self.compatibility_path = (
            Path(compatibility_path) if compatibility_path else None
        )
        self.status = AuthorityRuntimeStatus.READY
        self.last_error: Optional[str] = None
        self._events: tuple[LedgerEvent, ...] = ()
        self._projection = PaperPortfolioState()
        self._lock = threading.RLock()

    @staticmethod
    def _assert_projection_matches(
        durable: PaperPortfolioState,
        validated: PaperPortfolioState,
    ) -> None:
        """Prove the durable replay matches the state validated pre-append."""
        if durable != validated:
            raise PPLAuthorityRuntimeError(
                "durable PPL projection differs from the prospectively "
                "validated projection"
            )

    def _append_semantically_validated(self, event: LedgerEvent) -> AppendResult:
        """Validate the prospective lifecycle state before the durability boundary.

        Existing event ids retain the DurableEventStore's exact-event idempotence
        contract.  A genuinely new event is projected in-memory first; semantic
        rejection therefore happens before append/fsync and cannot poison the
        authoritative epoch.
        """

        existing = next(
            (stored for stored in self._events if stored.event_id == event.event_id),
            None,
        )
        if existing is None:
            validated_projection = project(self._events + (event,))
        else:
            # The store remains authoritative for canonical identity collision
            # detection.  For an exact retry, the current replay is already the
            # prospectively validated state.
            validated_projection = self._projection

        result = self.store.append(self.manifest.paper_epoch_id, event)
        self._reload()
        self._assert_projection_matches(self._projection, validated_projection)
        return result

    def _reload(self) -> None:
        events = self.store.load_epoch(self.manifest.paper_epoch_id)
        state = project(events)
        if state.epoch is None:
            raise PPLAuthorityRuntimeError("authority epoch projection is empty")
        if state.epoch.schema_version != _PPL_EVENT_SCHEMA_VERSION:
            raise PPLAuthorityRuntimeError("authority epoch is not schema v2")
        if state.paper_epoch_id != self.manifest.paper_epoch_id:
            raise PPLAuthorityRuntimeError("authority epoch id mismatch")
        if state.epoch.initial_virtual_capital != self.manifest.initial_virtual_capital:
            raise PPLAuthorityRuntimeError("authority initial capital mismatch")
        if state.epoch.code_sha != self.manifest.code_sha:
            raise PPLAuthorityRuntimeError("authority code_sha mismatch")
        if state.epoch.config_snapshot_hash != self.manifest.config_snapshot_hash:
            raise PPLAuthorityRuntimeError("authority config hash mismatch")
        self._events = events
        self._projection = state

    def bind(self, *, now: float) -> PaperPortfolioState:
        """Create/replay the explicit authority epoch and resolve expired recovery."""

        with self._lock:
            try:
                try:
                    self.store.load_epoch(self.manifest.paper_epoch_id)
                except EpochNotFoundError:
                    event = make_epoch_created_event(
                        event_id=_event_id(
                            self.manifest.paper_epoch_id,
                            LedgerEventType.EPOCH_CREATED,
                            "epoch",
                        ),
                        paper_epoch_id=self.manifest.paper_epoch_id,
                        sequence=1,
                        timestamp=self.manifest.created_at,
                        initial_virtual_capital=self.manifest.initial_virtual_capital,
                        code_sha=self.manifest.code_sha,
                        config_snapshot_hash=self.manifest.config_snapshot_hash,
                        schema_version=_PPL_EVENT_SCHEMA_VERSION,
                    )
                    self._append_semantically_validated(event)

                self._reload()
                plan = plan_restart_recovery(self._projection, now=now)
                for item in plan.positions:
                    if item.disposition is not RestartDisposition.UNRESOLVED_REQUIRED:
                        continue
                    sequence = self._events[-1].sequence + 1
                    event = make_position_unresolved_event(
                        event_id=_event_id(
                            self.manifest.paper_epoch_id,
                            LedgerEventType.POSITION_UNRESOLVED,
                            item.trade_id,
                        ),
                        paper_epoch_id=self.manifest.paper_epoch_id,
                        sequence=sequence,
                        timestamp=float(now),
                        trade_id=item.trade_id,
                        reason="recovery_window_expired",
                        schema_version=_PPL_EVENT_SCHEMA_VERSION,
                    )
                    self._append_semantically_validated(event)

                self.status = AuthorityRuntimeStatus.READY
                self.last_error = None
                return self._projection
            except Exception as exc:
                self.status = AuthorityRuntimeStatus.DEGRADED
                self.last_error = str(exc)
                raise

    def commit_open(
        self,
        *,
        trade_id: str,
        symbol: str,
        side: str,
        principal: float,
        entry_price: float,
        entry_fee: float,
        opened_at: float,
        tp_price: float,
        sl_price: float,
        timeout_at: float,
        recovery_eligible_until: float,
        decision_id: Optional[str],
    ) -> AppendResult:
        with self._lock:
            self._reload()
            event_id = _event_id(
                self.manifest.paper_epoch_id,
                LedgerEventType.POSITION_OPENED,
                trade_id,
            )
            existing = next((ev for ev in self._events if ev.event_id == event_id), None)
            sequence = (
                existing.sequence
                if existing is not None
                else self._events[-1].sequence + 1
            )
            event = make_position_opened_event(
                event_id=event_id,
                paper_epoch_id=self.manifest.paper_epoch_id,
                sequence=sequence,
                timestamp=opened_at,
                trade_id=trade_id,
                symbol=symbol,
                side=side,
                principal=principal,
                entry_price=entry_price,
                entry_fee=entry_fee,
                decision_id=decision_id,
                schema_version=_PPL_EVENT_SCHEMA_VERSION,
                tp_price=tp_price,
                sl_price=sl_price,
                timeout_at=timeout_at,
                recovery_eligible_until=recovery_eligible_until,
            )
            return self._append_semantically_validated(event)

    def commit_close(
        self,
        *,
        trade_id: str,
        exit_price: float,
        exit_fee: float,
        closed_at: float,
        decision_id: Optional[str],
    ) -> AppendResult:
        with self._lock:
            self._reload()
            event_id = _event_id(
                self.manifest.paper_epoch_id,
                LedgerEventType.POSITION_CLOSED,
                trade_id,
            )
            existing = next((ev for ev in self._events if ev.event_id == event_id), None)
            sequence = (
                existing.sequence
                if existing is not None
                else self._events[-1].sequence + 1
            )
            event = make_position_closed_event(
                event_id=event_id,
                paper_epoch_id=self.manifest.paper_epoch_id,
                sequence=sequence,
                timestamp=closed_at,
                trade_id=trade_id,
                exit_price=exit_price,
                exit_fee=exit_fee,
                decision_id=decision_id,
                schema_version=_PPL_EVENT_SCHEMA_VERSION,
            )
            return self._append_semantically_validated(event)

    def sync_compatibility(self) -> int:
        with self._lock:
            if self.compatibility_path is None:
                return 0
            self._reload()
            return project_ppl_to_legacy_jsonl(
                self._events,
                self.compatibility_path,
            )

    def consistent_view(self) -> AuthorityRuntimeView:
        with self._lock:
            self._reload()
            return AuthorityRuntimeView(
                status=self.status,
                paper_epoch_id=self.manifest.paper_epoch_id,
                last_error=self.last_error,
                projection=self._projection,
                events=self._events,
            )

    def rollback_disposition(self) -> RollbackDisposition:
        with self._lock:
            self._reload()
            if len(self._events) == 1:
                return RollbackDisposition.SAFE_BEFORE_FIRST_LIFECYCLE_EVENT
            return RollbackDisposition.BLOCKED_RECONCILIATION_REQUIRED


def configured_rollback_disposition(
    environ: Optional[Mapping[str, str]] = None,
) -> Optional[RollbackDisposition]:
    """Inspect configured authority epoch without creating or modifying it."""

    env = os.environ if environ is None else environ
    configured = [
        bool(str(env.get("PPL_AUTHORITY_MANIFEST", "") or "").strip()),
        bool(str(env.get("PPL_AUTHORITY_STORE_ROOT", "") or "").strip()),
        bool(str(env.get("PPL_AUTHORITY_EPOCH_ID", "") or "").strip()),
    ]
    if not any(configured):
        return None
    if not all(configured):
        raise AuthorityManifestError(
            "partial PPL authority configuration is not a valid rollback state"
        )
    runtime = build_authority_runtime_from_env(env)
    try:
        events = runtime.store.load_epoch(runtime.manifest.paper_epoch_id)
    except EpochNotFoundError:
        return RollbackDisposition.SAFE_BEFORE_FIRST_LIFECYCLE_EVENT
    if len(events) <= 1:
        return RollbackDisposition.SAFE_BEFORE_FIRST_LIFECYCLE_EVENT
    return RollbackDisposition.BLOCKED_RECONCILIATION_REQUIRED

def build_authority_runtime_from_env(
    environ: Optional[Mapping[str, str]] = None,
) -> PPLAuthorityRuntime:
    env = os.environ if environ is None else environ
    manifest_path = str(env.get("PPL_AUTHORITY_MANIFEST", "") or "").strip()
    store_root = str(env.get("PPL_AUTHORITY_STORE_ROOT", "") or "").strip()
    compatibility_path = str(env.get("PAPER_TRADE_LOG", "") or "").strip()
    epoch_env = str(env.get("PPL_AUTHORITY_EPOCH_ID", "") or "").strip()
    if not manifest_path or not store_root or not epoch_env:
        raise AuthorityManifestError(
            "PPL_AUTHORITY_MANIFEST, PPL_AUTHORITY_STORE_ROOT and "
            "PPL_AUTHORITY_EPOCH_ID are all required"
        )
    manifest = load_authority_manifest(manifest_path)
    if epoch_env != manifest.paper_epoch_id:
        raise AuthorityManifestError(
            "PPL_AUTHORITY_EPOCH_ID does not match authority manifest"
        )
    root = Path(store_root)
    if root.exists() and root.is_symlink():
        raise AuthorityManifestError("PPL_AUTHORITY_STORE_ROOT must not be a symlink")
    return PPLAuthorityRuntime(
        manifest=manifest,
        store=DurableEventStore(root),
        compatibility_path=compatibility_path or None,
    )


__all__ = [
    "AuthorityEpochManifest",
    "AuthorityManifestError",
    "AuthorityRuntimeStatus",
    "CutoverQuiescence",
    "PPLAuthorityRuntime",
    "PPLAuthorityRuntimeError",
    "RollbackDisposition",
    "build_authority_runtime_from_env",
    "configured_rollback_disposition",
    "build_cutover_manifest",
    "load_authority_manifest",
    "write_authority_manifest",
]
