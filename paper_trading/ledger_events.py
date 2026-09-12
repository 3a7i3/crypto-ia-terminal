"""paper_trading/ledger_events.py — Ledger event envelope/model (PPL-02A).

Pure domain model. No filesystem, no JSONL, no fsync — persistence is
explicitly out of scope for PPL-02A (belongs to PPL-02B, per the mission
contract). This module only defines the *shape* of events that a future
durable event-sourced PaperPortfolioLedger would append and replay.

`event_id` != `trade_id` (PPL-02A-R1, MASTER finding R1-B): this is not
merely a naming convention, it is an ENFORCED domain invariant. A
trade-scoped event whose `event_id` equals its `trade_id` is rejected at
construction (`__post_init__`) — see `test_event_id_equal_to_trade_id_is_rejected`.
`event_id` uniquely identifies this one envelope (one occurrence of one fact
happening once); `trade_id` correlates the OPEN/CLOSE/UNRESOLVED events that
describe the lifecycle of a single position.

`sequence` is monotonically increasing within one `paper_epoch_id`, starting
at 1, with no gaps and no regressions — enforced by the projection in
`paper_portfolio_ledger.py`, not by this module (this module only carries
the data; `paper_portfolio_ledger.project()` is where the ordering contract
is actually checked).

STREAM PARTITION CONTRACT (PPL-02A-R1, MASTER finding R1-J): one projected
event stream == one `paper_epoch_id`. `project()` accepts exactly one
scientific epoch per call; a second `EPOCH_CREATED` in the same stream is
rejected. A future durable store may hold multiple epochs, but PPL-02B must
partition/select a single epoch's events before calling `project()`.

PNL AUTHORITY (PPL-02A-R1, MASTER finding R1-G): `POSITION_CLOSED` carries
only `exit_price` and `exit_fee` as durable facts — `gross_pnl` is NOT part
of this event's payload. It is derived by the projection
(`paper_portfolio_ledger.py`) from `principal`, `side`, `entry_price`
(all known from the matching `POSITION_OPENED`) and `exit_price`. There is
exactly one authority for the trade's gross PnL, and it is the projection,
not the event stream — this makes a contradictory event (e.g. a LONG
recording a price gain but a negative `gross_pnl`) structurally impossible.

Event types are deliberately minimal — no speculative events beyond what
PPL-01R's RESTART_RECOVERY_CONTRACT and EVENT_SOURCING_CONTRACT required.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional


class LedgerEventType(str, Enum):
    """Minimal event vocabulary for the PAPER portfolio ledger."""

    EPOCH_CREATED = "EPOCH_CREATED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    POSITION_UNRESOLVED = "POSITION_UNRESOLVED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"


class Side(str, Enum):
    """Canonical PPL domain trade direction — a closed vocabulary.

    Only LONG/SHORT are valid stored/canonical values (MASTER finding
    R1-E). Callers using exchange-style BUY/SELL vocabulary must normalize
    through `normalize_side()` before an event reaches this module — an
    unrecognized string is never silently treated as SHORT (or as anything
    else); it fails closed.
    """

    LONG = "LONG"
    SHORT = "SHORT"


_SIDE_ALIASES = {
    "LONG": Side.LONG,
    "BUY": Side.LONG,
    "SHORT": Side.SHORT,
    "SELL": Side.SHORT,
}


def normalize_side(raw: str) -> Side:
    """Map an exchange-style or canonical side string to `Side`.

    Fails closed: any string not in the explicit alias table (case-
    insensitive) raises `ValueError` rather than being inferred as one
    side or the other.
    """
    if not isinstance(raw, str):
        raise ValueError(f"side must be a string, got {raw!r}")
    normalized = _SIDE_ALIASES.get(raw.strip().upper())
    if normalized is None:
        raise ValueError(
            f"unrecognized side {raw!r}; expected one of "
            f"{sorted(_SIDE_ALIASES)}"
        )
    return normalized


# Event types that describe a fact about one specific trade lifecycle and
# therefore require a non-empty `trade_id`.
_TRADE_SCOPED_EVENT_TYPES = frozenset(
    {
        LedgerEventType.POSITION_OPENED,
        LedgerEventType.POSITION_CLOSED,
        LedgerEventType.POSITION_UNRESOLVED,
    }
)


def _require_finite(name: str, value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be a real number, got {value!r}")
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return float(value)


def _deep_freeze(value: Any) -> Any:
    """Recursively freeze plain dict/list payload contents.

    Defensive copy at the construction boundary: mutating a dict the
    caller passed in after constructing the event must not affect the
    event, and the event's own `payload` must not be mutable by the
    caller afterward either (MASTER finding R1-C).
    """
    if isinstance(value, Mapping):
        return MappingProxyType({k: _deep_freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class LedgerEvent:
    """One immutable, durable-intent fact in the PAPER portfolio ledger.

    `payload` carries event-type-specific fields as an immutable mapping
    (`MappingProxyType`, recursively applied to any nested dict/list at
    construction time via `_deep_freeze`) — kept untyped here deliberately
    so this envelope stays stable while payload shapes are validated by the
    projection layer that actually interprets them
    (`paper_portfolio_ledger.py`).
    """

    event_id: str
    paper_epoch_id: str
    sequence: int
    event_type: LedgerEventType
    timestamp: float
    trade_id: Optional[str]
    decision_id: Optional[str]
    payload: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id must be non-empty")
        if not self.paper_epoch_id:
            raise ValueError("paper_epoch_id must be non-empty")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool):
            raise ValueError(f"sequence must be an int, got {self.sequence!r}")
        if self.sequence < 1:
            raise ValueError("sequence must be >= 1")
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool):
            raise ValueError(f"schema_version must be an int, got {self.schema_version!r}")
        if self.schema_version < 1:
            raise ValueError("schema_version must be >= 1")
        timestamp = _require_finite("timestamp", self.timestamp)
        object.__setattr__(self, "timestamp", timestamp)

        if self.event_type in _TRADE_SCOPED_EVENT_TYPES:
            if not self.trade_id:
                raise ValueError(
                    f"{self.event_type.value} requires a non-empty trade_id"
                )
            if self.event_id == self.trade_id:
                raise ValueError(
                    "event_id must not equal trade_id "
                    f"(got both = {self.event_id!r}) — event_id identifies "
                    "this one envelope, trade_id correlates a position's "
                    "OPEN/CLOSE/UNRESOLVED lifecycle; they are never the "
                    "same identifier"
                )
        if self.event_type is LedgerEventType.EPOCH_CREATED and self.trade_id:
            raise ValueError("EPOCH_CREATED must not carry a trade_id")

        object.__setattr__(self, "payload", _deep_freeze(self.payload))


def make_epoch_created_event(
    *,
    event_id: str,
    paper_epoch_id: str,
    sequence: int,
    timestamp: float,
    initial_virtual_capital: float,
    code_sha: str,
    config_snapshot_hash: str,
    decision_id: Optional[str] = None,
    schema_version: int = 1,
) -> LedgerEvent:
    """Build the durable EPOCH_CREATED event.

    For EPOCH_CREATED, `timestamp` IS the epoch's `created_at` by
    definition — there is no separate `created_at` payload field, avoiding
    two authorities for the same moment. `paper_portfolio_ledger.project()`
    reconstructs a complete `PaperEpoch` from exactly this event.
    """
    return LedgerEvent(
        event_id=event_id,
        paper_epoch_id=paper_epoch_id,
        sequence=sequence,
        event_type=LedgerEventType.EPOCH_CREATED,
        timestamp=timestamp,
        trade_id=None,
        decision_id=decision_id,
        payload={
            "initial_virtual_capital": initial_virtual_capital,
            "code_sha": code_sha,
            "config_snapshot_hash": config_snapshot_hash,
        },
        schema_version=schema_version,
    )


def make_epoch_created_event_from_epoch(
    epoch,
    *,
    event_id: str,
    sequence: int,
    decision_id: Optional[str] = None,
) -> LedgerEvent:
    """Build EPOCH_CREATED directly from a `PaperEpoch` domain object.

    Preferred construction path per the PAPER_EPOCH_ID_CONTRACT: a caller
    builds a `PaperEpoch` through explicit intent
    (`paper_epoch.create_paper_epoch`), then derives the durable event from
    it, rather than duplicating the epoch's fields by hand.
    """
    return make_epoch_created_event(
        event_id=event_id,
        paper_epoch_id=epoch.paper_epoch_id,
        sequence=sequence,
        timestamp=epoch.created_at,
        initial_virtual_capital=epoch.initial_virtual_capital,
        code_sha=epoch.code_sha,
        config_snapshot_hash=epoch.config_snapshot_hash,
        decision_id=decision_id,
        schema_version=epoch.schema_version,
    )


def make_position_opened_event(
    *,
    event_id: str,
    paper_epoch_id: str,
    sequence: int,
    timestamp: float,
    trade_id: str,
    symbol: str,
    side: str,
    principal: float,
    entry_price: float,
    entry_fee: float,
    decision_id: Optional[str] = None,
    schema_version: int = 1,
) -> LedgerEvent:
    canonical_side = normalize_side(side)
    return LedgerEvent(
        event_id=event_id,
        paper_epoch_id=paper_epoch_id,
        sequence=sequence,
        event_type=LedgerEventType.POSITION_OPENED,
        timestamp=timestamp,
        trade_id=trade_id,
        decision_id=decision_id,
        payload={
            "symbol": symbol,
            "side": canonical_side.value,
            "principal": principal,
            "entry_price": entry_price,
            "entry_fee": entry_fee,
        },
        schema_version=schema_version,
    )


def make_position_closed_event(
    *,
    event_id: str,
    paper_epoch_id: str,
    sequence: int,
    timestamp: float,
    trade_id: str,
    exit_price: float,
    exit_fee: float,
    decision_id: Optional[str] = None,
    schema_version: int = 1,
) -> LedgerEvent:
    """POSITION_CLOSED durable facts: `exit_price` and `exit_fee` only.

    `gross_pnl` is deliberately NOT a payload field (MASTER finding R1-G):
    it is derived by the projection from `principal`/`side`/`entry_price`
    (known from the matching OPEN) and `exit_price`, so there is exactly
    one authority for a trade's gross PnL and a contradictory event (e.g.
    a price gain paired with a hand-supplied loss) cannot be constructed.
    """
    return LedgerEvent(
        event_id=event_id,
        paper_epoch_id=paper_epoch_id,
        sequence=sequence,
        event_type=LedgerEventType.POSITION_CLOSED,
        timestamp=timestamp,
        trade_id=trade_id,
        decision_id=decision_id,
        payload={
            "exit_price": exit_price,
            "exit_fee": exit_fee,
        },
        schema_version=schema_version,
    )


def make_position_unresolved_event(
    *,
    event_id: str,
    paper_epoch_id: str,
    sequence: int,
    timestamp: float,
    trade_id: str,
    reason: str,
    decision_id: Optional[str] = None,
    schema_version: int = 1,
) -> LedgerEvent:
    """A position whose financial outcome cannot be established.

    Per PPL-01R's UNKNOWN_PNL_CONTRACT: this is a RESOLUTION-of-recovery
    event, never a fabricated close. Its principal moves from
    reserved_principal to unresolved_capital, never to available_cash, and
    it contributes no realized_pnl (known or zero) whatsoever.
    """
    return LedgerEvent(
        event_id=event_id,
        paper_epoch_id=paper_epoch_id,
        sequence=sequence,
        event_type=LedgerEventType.POSITION_UNRESOLVED,
        timestamp=timestamp,
        trade_id=trade_id,
        decision_id=decision_id,
        payload={"reason": reason},
        schema_version=schema_version,
    )


def make_recovery_completed_event(
    *,
    event_id: str,
    paper_epoch_id: str,
    sequence: int,
    timestamp: float,
    restored_count: int,
    unresolved_count: int,
    decision_id: Optional[str] = None,
    schema_version: int = 1,
) -> LedgerEvent:
    return LedgerEvent(
        event_id=event_id,
        paper_epoch_id=paper_epoch_id,
        sequence=sequence,
        event_type=LedgerEventType.RECOVERY_COMPLETED,
        timestamp=timestamp,
        trade_id=None,
        decision_id=decision_id,
        payload={
            "restored_count": restored_count,
            "unresolved_count": unresolved_count,
        },
        schema_version=schema_version,
    )
