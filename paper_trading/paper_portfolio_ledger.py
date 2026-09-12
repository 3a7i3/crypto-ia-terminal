"""paper_trading/paper_portfolio_ledger.py — Pure accounting core (PPL-02A).

`project(events) -> PaperPortfolioState` is a pure, deterministic,
side-effect-free replay function: same input events always produce
identical state, no filesystem access, no clock reads, no randomness.

Scope boundary (PPL-02A): this module implements ONLY the accounting/domain
core. It is not imported by, and does not import, any production runtime
path — `core/advisor_loop.py`, `infra/wallet_sync.py`,
`paper_trading/mexc_simulator.py`, execution, sizing, risk, PortfolioBrain,
Telegram, or dashboards are untouched and unaware this module exists.
Persistence (JSONL, fsync, SQLite) is explicitly deferred to PPL-02B.

Canonical accounting model (PPL-02A mission, mirroring PPL-01R's ratified
equations):

    OPEN:
        available_cash    -= principal + entry_fee
        reserved_principal += principal
        fees_paid          += entry_fee

    CLOSE (normal, known outcome):
        available_cash    += principal + gross_pnl - exit_fee
        reserved_principal -= principal
        fees_paid          += exit_fee
        trade_realized_pnl  = gross_pnl - entry_fee - exit_fee
        realized_pnl        += trade_realized_pnl

    UNRESOLVED (unknown outcome):
        reserved_principal -= principal
        unresolved_capital += principal
        # realized_pnl is NOT touched — the outcome stays unknown, never 0.
        # principal moves to unresolved_capital, never to available_cash.

Entry fee is charged exactly once (at OPEN, folded into `fees_paid` and into
`available_cash`'s debit) and appears exactly once more inside
`trade_realized_pnl`'s bookkeeping formula for reporting purposes only — it
is NOT re-debited from `available_cash` a second time at CLOSE (see
`equity()`/`test_entry_fee_charged_exactly_once`, and the explicit
regression test reproducing the confirmed MexcSimulator double-charge
defect from PPL-01R's ENTRY_FEE_DEFECT_VERDICT).

equity = available_cash + reserved_principal + unrealized_pnl + unresolved_capital
certified_equity = available_cash + reserved_principal + unrealized_pnl
    (i.e. equity with unresolved_capital carved out and reported separately
    — never silently folded into a single spendable number).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Mapping, Optional, Sequence, Set

from paper_trading.ledger_events import LedgerEvent, LedgerEventType


# ── Errors — fail closed, never silently repair malformed history ──────────


class LedgerReplayError(Exception):
    """Base class for all projection/replay violations."""


class DuplicateEventError(LedgerReplayError):
    pass


class SequenceGapError(LedgerReplayError):
    pass


class SequenceRegressionError(LedgerReplayError):
    pass


class EpochMismatchError(LedgerReplayError):
    pass


class DuplicateOpenError(LedgerReplayError):
    pass


class CloseWithoutOpenError(LedgerReplayError):
    pass


class DoubleCloseError(LedgerReplayError):
    pass


class IllegalTransitionError(LedgerReplayError):
    pass


class NegativeCashError(LedgerReplayError):
    pass


# ── State ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OpenPositionState:
    trade_id: str
    symbol: str
    side: str
    principal: float
    entry_price: float
    entry_fee: float
    opened_sequence: int


@dataclass(frozen=True)
class UnresolvedPositionState:
    trade_id: str
    symbol: str
    side: str
    principal: float
    entry_price: float
    entry_fee: float
    reason: str
    unresolved_sequence: int


@dataclass(frozen=True)
class EquityBreakdown:
    """Mark-to-market snapshot. Never persisted, always freshly computed."""

    available_cash: float
    reserved_principal: float
    unrealized_pnl: float
    unresolved_capital: float
    equity: float
    certified_equity: float


@dataclass(frozen=True)
class PaperPortfolioState:
    """Immutable projection result. Every mutation returns a new instance."""

    paper_epoch_id: Optional[str] = None
    available_cash: float = 0.0
    reserved_principal: float = 0.0
    unresolved_capital: float = 0.0
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    open_positions: Mapping[str, OpenPositionState] = field(default_factory=dict)
    unresolved_positions: Mapping[str, UnresolvedPositionState] = field(
        default_factory=dict
    )
    closed_trade_ids: frozenset = field(default_factory=frozenset)
    last_sequence: int = 0
    seen_event_ids: frozenset = field(default_factory=frozenset)
    restored_count_total: int = 0
    unresolved_count_total: int = 0

    def equity(self, mark_prices: Optional[Mapping[str, float]] = None) -> EquityBreakdown:
        """Compute mark-to-market equity. Pure query, not part of replay.

        `mark_prices` maps symbol -> current price. A position whose symbol
        is missing from `mark_prices` (or `mark_prices` is omitted
        entirely) contributes zero unrealized PnL for that position — its
        principal is still counted via `reserved_principal`, so equity is
        never understated to zero, only its live P&L component is
        unavailable.
        """
        mark_prices = mark_prices or {}
        unrealized = 0.0
        for pos in self.open_positions.values():
            price = mark_prices.get(pos.symbol)
            if price is None or price <= 0:
                continue
            if pos.side.upper() in ("BUY", "LONG"):
                gross_pct = (price - pos.entry_price) / pos.entry_price
            else:
                gross_pct = (pos.entry_price - price) / pos.entry_price
            unrealized += pos.principal * gross_pct

        certified_equity = self.available_cash + self.reserved_principal + unrealized
        equity = certified_equity + self.unresolved_capital
        return EquityBreakdown(
            available_cash=self.available_cash,
            reserved_principal=self.reserved_principal,
            unrealized_pnl=unrealized,
            unresolved_capital=self.unresolved_capital,
            equity=equity,
            certified_equity=certified_equity,
        )


# ── Pure projection ─────────────────────────────────────────────────────


def project(events: Sequence[LedgerEvent]) -> PaperPortfolioState:
    """Deterministic, side-effect-free replay: events -> PaperPortfolioState.

    Fails closed on any malformed/out-of-order history — raises a
    `LedgerReplayError` subclass rather than silently repairing or skipping
    the offending event. Same input list always produces identical output
    (no wall-clock reads, no randomness, no I/O).
    """
    state = PaperPortfolioState()

    for event in events:
        state = _apply(state, event)

    return state


def _apply(state: PaperPortfolioState, event: LedgerEvent) -> PaperPortfolioState:
    if event.event_id in state.seen_event_ids:
        raise DuplicateEventError(f"duplicate event_id={event.event_id!r}")

    if state.paper_epoch_id is None:
        if event.event_type is not LedgerEventType.EPOCH_CREATED:
            raise IllegalTransitionError(
                f"first event must be EPOCH_CREATED, got {event.event_type.value}"
            )
    else:
        if event.event_type is LedgerEventType.EPOCH_CREATED:
            raise IllegalTransitionError(
                "EPOCH_CREATED may only appear as the first event"
            )
        if event.paper_epoch_id != state.paper_epoch_id:
            raise EpochMismatchError(
                f"event paper_epoch_id={event.paper_epoch_id!r} != "
                f"state paper_epoch_id={state.paper_epoch_id!r}"
            )

    expected_sequence = state.last_sequence + 1
    if event.sequence < expected_sequence:
        raise SequenceRegressionError(
            f"sequence regression: got {event.sequence}, "
            f"expected {expected_sequence}"
        )
    if event.sequence > expected_sequence:
        raise SequenceGapError(
            f"sequence gap: got {event.sequence}, expected {expected_sequence}"
        )

    seen_event_ids = state.seen_event_ids | {event.event_id}

    if event.event_type is LedgerEventType.EPOCH_CREATED:
        return _apply_epoch_created(state, event, seen_event_ids)
    if event.event_type is LedgerEventType.POSITION_OPENED:
        return _apply_position_opened(state, event, seen_event_ids)
    if event.event_type is LedgerEventType.POSITION_CLOSED:
        return _apply_position_closed(state, event, seen_event_ids)
    if event.event_type is LedgerEventType.POSITION_UNRESOLVED:
        return _apply_position_unresolved(state, event, seen_event_ids)
    if event.event_type is LedgerEventType.RECOVERY_COMPLETED:
        return _apply_recovery_completed(state, event, seen_event_ids)

    raise IllegalTransitionError(f"unknown event_type={event.event_type!r}")


def _apply_epoch_created(
    state: PaperPortfolioState, event: LedgerEvent, seen_event_ids: frozenset
) -> PaperPortfolioState:
    initial_virtual_capital = float(event.payload["initial_virtual_capital"])
    if initial_virtual_capital <= 0:
        raise IllegalTransitionError("initial_virtual_capital must be > 0")

    return replace(
        state,
        paper_epoch_id=event.paper_epoch_id,
        available_cash=initial_virtual_capital,
        reserved_principal=0.0,
        unresolved_capital=0.0,
        realized_pnl=0.0,
        fees_paid=0.0,
        last_sequence=event.sequence,
        seen_event_ids=seen_event_ids,
    )


def _apply_position_opened(
    state: PaperPortfolioState, event: LedgerEvent, seen_event_ids: frozenset
) -> PaperPortfolioState:
    trade_id = event.trade_id
    assert trade_id is not None  # enforced by LedgerEvent.__post_init__

    if trade_id in state.open_positions:
        raise DuplicateOpenError(f"trade_id={trade_id!r} already open")
    if trade_id in state.closed_trade_ids or trade_id in state.unresolved_positions:
        raise IllegalTransitionError(
            f"trade_id={trade_id!r} already used by a prior trade lifecycle"
        )

    principal = float(event.payload["principal"])
    entry_fee = float(event.payload["entry_fee"])
    if principal <= 0:
        raise IllegalTransitionError("principal must be > 0")
    if entry_fee < 0:
        raise IllegalTransitionError("entry_fee must be >= 0")

    new_available_cash = state.available_cash - principal - entry_fee
    if new_available_cash < 0:
        raise NegativeCashError(
            f"OPEN {trade_id!r} would drive available_cash negative: "
            f"{state.available_cash} - {principal} - {entry_fee} = "
            f"{new_available_cash}"
        )

    pos = OpenPositionState(
        trade_id=trade_id,
        symbol=str(event.payload["symbol"]),
        side=str(event.payload["side"]),
        principal=principal,
        entry_price=float(event.payload["entry_price"]),
        entry_fee=entry_fee,
        opened_sequence=event.sequence,
    )
    new_open_positions = dict(state.open_positions)
    new_open_positions[trade_id] = pos

    return replace(
        state,
        available_cash=new_available_cash,
        reserved_principal=state.reserved_principal + principal,
        fees_paid=state.fees_paid + entry_fee,
        open_positions=new_open_positions,
        last_sequence=event.sequence,
        seen_event_ids=seen_event_ids,
    )


def _apply_position_closed(
    state: PaperPortfolioState, event: LedgerEvent, seen_event_ids: frozenset
) -> PaperPortfolioState:
    trade_id = event.trade_id
    assert trade_id is not None

    if trade_id in state.closed_trade_ids or trade_id in state.unresolved_positions:
        raise DoubleCloseError(f"trade_id={trade_id!r} already resolved")
    pos = state.open_positions.get(trade_id)
    if pos is None:
        raise CloseWithoutOpenError(f"CLOSE for trade_id={trade_id!r} with no OPEN")

    gross_pnl = float(event.payload["gross_pnl"])
    exit_fee = float(event.payload["exit_fee"])
    if exit_fee < 0:
        raise IllegalTransitionError("exit_fee must be >= 0")

    trade_realized_pnl = gross_pnl - pos.entry_fee - exit_fee

    new_available_cash = state.available_cash + pos.principal + gross_pnl - exit_fee
    if new_available_cash < 0:
        raise NegativeCashError(
            f"CLOSE {trade_id!r} would drive available_cash negative: "
            f"{state.available_cash} + {pos.principal} + {gross_pnl} - "
            f"{exit_fee} = {new_available_cash}"
        )

    new_open_positions = dict(state.open_positions)
    del new_open_positions[trade_id]

    return replace(
        state,
        available_cash=new_available_cash,
        reserved_principal=state.reserved_principal - pos.principal,
        fees_paid=state.fees_paid + exit_fee,
        realized_pnl=state.realized_pnl + trade_realized_pnl,
        open_positions=new_open_positions,
        closed_trade_ids=state.closed_trade_ids | {trade_id},
        last_sequence=event.sequence,
        seen_event_ids=seen_event_ids,
    )


def _apply_position_unresolved(
    state: PaperPortfolioState, event: LedgerEvent, seen_event_ids: frozenset
) -> PaperPortfolioState:
    trade_id = event.trade_id
    assert trade_id is not None

    if trade_id in state.closed_trade_ids or trade_id in state.unresolved_positions:
        raise IllegalTransitionError(f"trade_id={trade_id!r} already resolved")
    pos = state.open_positions.get(trade_id)
    if pos is None:
        raise IllegalTransitionError(
            f"POSITION_UNRESOLVED for trade_id={trade_id!r} with no OPEN"
        )

    new_open_positions = dict(state.open_positions)
    del new_open_positions[trade_id]

    new_unresolved = dict(state.unresolved_positions)
    new_unresolved[trade_id] = UnresolvedPositionState(
        trade_id=trade_id,
        symbol=pos.symbol,
        side=pos.side,
        principal=pos.principal,
        entry_price=pos.entry_price,
        entry_fee=pos.entry_fee,
        reason=str(event.payload.get("reason", "unknown")),
        unresolved_sequence=event.sequence,
    )

    return replace(
        state,
        reserved_principal=state.reserved_principal - pos.principal,
        unresolved_capital=state.unresolved_capital + pos.principal,
        # realized_pnl deliberately untouched: outcome stays UNKNOWN, never 0.
        open_positions=new_open_positions,
        unresolved_positions=new_unresolved,
        unresolved_count_total=state.unresolved_count_total + 1,
        last_sequence=event.sequence,
        seen_event_ids=seen_event_ids,
    )


def _apply_recovery_completed(
    state: PaperPortfolioState, event: LedgerEvent, seen_event_ids: frozenset
) -> PaperPortfolioState:
    restored_count = int(event.payload.get("restored_count", 0))
    return replace(
        state,
        restored_count_total=state.restored_count_total + restored_count,
        last_sequence=event.sequence,
        seen_event_ids=seen_event_ids,
    )
