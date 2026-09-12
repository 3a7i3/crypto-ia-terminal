"""paper_trading/ledger_events.py — Ledger event envelope/model (PPL-02A).

Pure domain model. No filesystem, no JSONL, no fsync — persistence is
explicitly out of scope for PPL-02A (belongs to PPL-02B, per the mission
contract). This module only defines the *shape* of events that a future
durable event-sourced PaperPortfolioLedger would append and replay.

`event_id` != `trade_id`:
  - `event_id` uniquely identifies this one envelope (one occurrence of one
    fact happening once).
  - `trade_id` correlates the OPEN/CLOSE/UNRESOLVED events that describe the
    lifecycle of a single position, and one trade_id appears in exactly one
    POSITION_OPENED event, followed by exactly one terminal event
    (POSITION_CLOSED or POSITION_UNRESOLVED).

`sequence` is monotonically increasing within one `paper_epoch_id`, starting
at 1, with no gaps and no regressions — enforced by the projection in
`paper_portfolio_ledger.py`, not by this module (this module only carries
the data; `paper_portfolio_ledger.project()` is where the ordering contract
is actually checked).

Event types are deliberately minimal — no speculative events beyond what
PPL-01R's RESTART_RECOVERY_CONTRACT and EVENT_SOURCING_CONTRACT required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional


class LedgerEventType(str, Enum):
    """Minimal event vocabulary for the PAPER portfolio ledger."""

    EPOCH_CREATED = "EPOCH_CREATED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    POSITION_UNRESOLVED = "POSITION_UNRESOLVED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"


# Event types that describe a fact about one specific trade lifecycle and
# therefore require a non-empty `trade_id`.
_TRADE_SCOPED_EVENT_TYPES = frozenset(
    {
        LedgerEventType.POSITION_OPENED,
        LedgerEventType.POSITION_CLOSED,
        LedgerEventType.POSITION_UNRESOLVED,
    }
)


@dataclass(frozen=True)
class LedgerEvent:
    """One immutable, durable-intent fact in the PAPER portfolio ledger.

    `payload` carries event-type-specific fields as a plain mapping — kept
    untyped here deliberately so this envelope stays stable while payload
    shapes are validated by the projection layer that actually interprets
    them (`paper_portfolio_ledger.py`), matching the "evaluate what the
    current architecture actually requires" instruction rather than
    over-specifying payload dataclasses this mission doesn't need yet.
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
        if self.sequence < 1:
            raise ValueError("sequence must be >= 1")
        if self.event_type in _TRADE_SCOPED_EVENT_TYPES and not self.trade_id:
            raise ValueError(
                f"{self.event_type.value} requires a non-empty trade_id"
            )
        if self.event_type is LedgerEventType.EPOCH_CREATED and self.trade_id:
            raise ValueError("EPOCH_CREATED must not carry a trade_id")


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
            "side": side,
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
    gross_pnl: float,
    exit_fee: float,
    decision_id: Optional[str] = None,
    schema_version: int = 1,
) -> LedgerEvent:
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
            "gross_pnl": gross_pnl,
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
