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

Canonical accounting model (ratified PPL-01R, hardened PPL-02A-R1):

    OPEN:
        available_cash    -= principal + entry_fee
        reserved_principal += principal
        fees_paid          += entry_fee

    CLOSE (normal, known outcome):
        gross_pnl = DERIVED by this module from principal/side/entry_price
                    (known from the matching OPEN) and the CLOSE event's
                    exit_price — never a caller-supplied, independently
                    trusted value (MASTER finding R1-G: one authority only).
            LONG:  gross_pnl = principal * (exit_price - entry_price) / entry_price
            SHORT: gross_pnl = principal * (entry_price - exit_price) / entry_price

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
`test_entry_fee_charged_exactly_once`, and the explicit regression test
reproducing the confirmed MexcSimulator double-charge defect from PPL-01R's
ENTRY_FEE_DEFECT_VERDICT).

MARK COVERAGE CONTRACT (PPL-02A-R1, MASTER finding R1-A): `equity()` never
substitutes zero for a missing/invalid mark price. If every open position
has a valid (finite, positive) mark, "mark coverage" is complete and
`certified_equity`/`equity` are numbers. If ANY open position lacks a valid
mark, coverage is incomplete and both are `None` — UNKNOWN != ZERO applies
to mark-to-market exactly as it does to realized PnL. With zero open
positions, coverage is trivially complete and unrealized PnL is legitimately
0.0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, FrozenSet, Mapping, Optional, Sequence

from paper_trading.ledger_events import LedgerEvent, LedgerEventType, Side
from paper_trading.paper_epoch import PaperEpoch, PaperEpochStatus


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


class NonFiniteValueError(LedgerReplayError):
    """A financial field was NaN, +/-Inf, or otherwise not a real number."""


class InvalidSideError(LedgerReplayError):
    """A POSITION_OPENED payload carried a side outside {LONG, SHORT}."""


# ── Numeric validation — fail closed on NaN/Inf (MASTER finding R1-D) ─────


def _finite(name: str, value: Any, *, positive: bool = False, non_negative: bool = False) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise NonFiniteValueError(f"{name} must be a real number, got {value!r}")
    if math.isnan(value) or math.isinf(value):
        raise NonFiniteValueError(f"{name} must be finite, got {value!r}")
    value = float(value)
    if positive and value <= 0:
        raise IllegalTransitionError(f"{name} must be > 0, got {value!r}")
    if non_negative and value < 0:
        raise IllegalTransitionError(f"{name} must be >= 0, got {value!r}")
    return value


def _valid_mark_price(price: Any) -> bool:
    if not isinstance(price, (int, float)) or isinstance(price, bool):
        return False
    if math.isnan(price) or math.isinf(price):
        return False
    return price > 0


def _finite_derived(name: str, value: float) -> float:
    """Validate a DERIVED arithmetic result stays finite (PPL-02A-R2).

    R1's `_finite()` validates event *inputs*. Finite inputs do not
    guarantee a finite *result* — `(exit_price - entry_price) / entry_price`
    on two ordinary finite floats can still overflow to +/-inf, and any
    finite quantity combined with it (gross_pnl, trade_realized_pnl,
    available_cash, realized_pnl, fees_paid, unrealized PnL, equity) then
    silently carries that infinity forward. This helper closes that gap:
    every derived quantity is checked before it is folded into published
    state or returned to a caller. Never clamps, never substitutes zero or
    a maximum value — fails closed with `NonFiniteValueError`.
    """
    if math.isnan(value) or math.isinf(value):
        raise NonFiniteValueError(
            f"derived {name} is not finite ({value!r}) — arithmetic "
            "overflow on otherwise-finite inputs"
        )
    return value


# ── State ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OpenPositionState:
    trade_id: str
    symbol: str
    side: Side
    principal: float
    entry_price: float
    entry_fee: float
    opened_sequence: int


@dataclass(frozen=True)
class UnresolvedPositionState:
    trade_id: str
    symbol: str
    side: Side
    principal: float
    entry_price: float
    entry_fee: float
    reason: str
    unresolved_sequence: int


@dataclass(frozen=True)
class EquityBreakdown:
    """Mark-to-market snapshot. Never persisted, always freshly computed.

    `certified_equity` and `equity` are `None` whenever `mark_coverage_complete`
    is `False` — a missing or invalid mark price for even one open position
    means total unrealized PnL is UNKNOWN, not zero, and no equity figure is
    presented as if it were exact (MASTER finding R1-A). `unpriced_trade_ids`
    names exactly which open positions lack a valid mark.
    """

    available_cash: float
    reserved_principal: float
    known_unrealized_pnl: float
    unresolved_capital: float
    mark_coverage_complete: bool
    unpriced_trade_ids: FrozenSet[str]
    certified_equity: Optional[float]
    equity: Optional[float]


@dataclass(frozen=True)
class PaperPortfolioState:
    """Immutable projection result. Every mutation returns a new instance.

    `open_positions` and `unresolved_positions` are exposed as
    `MappingProxyType` read-only views (MASTER finding R1-C): a caller
    cannot mutate them, and internal replay logic never mutates a
    previously-published mapping in place — every transition builds a new
    dict and wraps it in a fresh `MappingProxyType` before it becomes part
    of the (also frozen) state.
    """

    paper_epoch_id: Optional[str] = None
    epoch: Optional[PaperEpoch] = None
    available_cash: float = 0.0
    reserved_principal: float = 0.0
    unresolved_capital: float = 0.0
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    open_positions: Mapping[str, OpenPositionState] = field(
        default_factory=lambda: MappingProxyType({})
    )
    unresolved_positions: Mapping[str, UnresolvedPositionState] = field(
        default_factory=lambda: MappingProxyType({})
    )
    closed_trade_ids: frozenset = field(default_factory=frozenset)
    last_sequence: int = 0
    seen_event_ids: frozenset = field(default_factory=frozenset)
    restored_count_total: int = 0
    unresolved_count_total: int = 0

    def equity(self, mark_prices: Optional[Mapping[str, float]] = None) -> EquityBreakdown:
        """Compute mark-to-market equity. Pure query, not part of replay.

        `mark_prices` maps symbol -> current price. A position whose symbol
        is missing from `mark_prices`, or whose price is not finite and
        positive, makes mark coverage incomplete for the whole snapshot —
        `certified_equity` and `equity` become `None` rather than silently
        treating that position's unrealized PnL as zero.
        """
        mark_prices = mark_prices or {}
        known_unrealized = 0.0
        unpriced: list = []
        for trade_id, pos in self.open_positions.items():
            price = mark_prices.get(pos.symbol)
            if not _valid_mark_price(price):
                # Missing/invalid mark: coverage is incomplete. This is
                # distinct from an arithmetic overflow below on an
                # otherwise-valid mark — a missing mark never raises, it
                # only ever degrades mark_coverage_complete/equity to None.
                unpriced.append(trade_id)
                continue
            if pos.side is Side.LONG:
                gross_pct = (price - pos.entry_price) / pos.entry_price
            else:
                gross_pct = (pos.entry_price - price) / pos.entry_price
            gross_pct = _finite_derived("mark-to-market gross_pct", gross_pct)
            position_unrealized_pnl = _finite_derived(
                "position unrealized_pnl", pos.principal * gross_pct
            )
            known_unrealized = _finite_derived(
                "known_unrealized_pnl", known_unrealized + position_unrealized_pnl
            )

        mark_coverage_complete = not unpriced
        if mark_coverage_complete:
            certified_equity = _finite_derived(
                "certified_equity",
                self.available_cash + self.reserved_principal + known_unrealized,
            )
            equity_value = _finite_derived(
                "equity", certified_equity + self.unresolved_capital
            )
        else:
            certified_equity = None
            equity_value = None

        return EquityBreakdown(
            available_cash=self.available_cash,
            reserved_principal=self.reserved_principal,
            known_unrealized_pnl=known_unrealized,
            unresolved_capital=self.unresolved_capital,
            mark_coverage_complete=mark_coverage_complete,
            unpriced_trade_ids=frozenset(unpriced),
            certified_equity=certified_equity,
            equity=equity_value,
        )


# ── Pure projection ─────────────────────────────────────────────────────


def project(events: Sequence[LedgerEvent]) -> PaperPortfolioState:
    """Deterministic, side-effect-free replay: events -> PaperPortfolioState.

    STREAM PARTITION CONTRACT (MASTER finding R1-J): one call to `project()`
    accepts exactly one scientific epoch. The first event must be
    EPOCH_CREATED; every subsequent event must carry the same
    `paper_epoch_id`; a second EPOCH_CREATED is rejected
    (`IllegalTransitionError`). A future durable store holding multiple
    epochs must partition/select a single epoch's events before calling
    this function — `project()` itself never crosses epochs silently.

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
                "EPOCH_CREATED may only appear as the first event of a "
                "projected stream — one project() call == one paper_epoch_id"
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
    initial_virtual_capital = _finite(
        "initial_virtual_capital", event.payload["initial_virtual_capital"], positive=True
    )
    code_sha = str(event.payload["code_sha"])
    config_snapshot_hash = str(event.payload["config_snapshot_hash"])

    # PAPER EPOCH AUTHORITY CONTRACT: reconstruct the complete PaperEpoch
    # domain object purely from this one durable event — no external file
    # or side channel is required during replay (MASTER finding R1-K).
    epoch = PaperEpoch(
        paper_epoch_id=event.paper_epoch_id,
        created_at=event.timestamp,
        initial_virtual_capital=initial_virtual_capital,
        status=PaperEpochStatus.ACTIVE,
        code_sha=code_sha,
        config_snapshot_hash=config_snapshot_hash,
        schema_version=event.schema_version,
    )

    return replace(
        state,
        paper_epoch_id=event.paper_epoch_id,
        epoch=epoch,
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

    raw_side = event.payload["side"]
    try:
        side = Side(raw_side)
    except ValueError as exc:
        raise InvalidSideError(
            f"invalid side {raw_side!r} in POSITION_OPENED payload for "
            f"trade_id={trade_id!r}"
        ) from exc

    principal = _finite("principal", event.payload["principal"], positive=True)
    entry_price = _finite("entry_price", event.payload["entry_price"], positive=True)
    entry_fee = _finite("entry_fee", event.payload["entry_fee"], non_negative=True)

    new_available_cash = _finite_derived(
        "available_cash", state.available_cash - principal - entry_fee
    )
    if new_available_cash < 0:
        raise NegativeCashError(
            f"OPEN {trade_id!r} would drive available_cash negative: "
            f"{state.available_cash} - {principal} - {entry_fee} = "
            f"{new_available_cash}"
        )
    new_reserved_principal = _finite_derived(
        "reserved_principal", state.reserved_principal + principal
    )
    new_fees_paid = _finite_derived("fees_paid", state.fees_paid + entry_fee)

    pos = OpenPositionState(
        trade_id=trade_id,
        symbol=str(event.payload["symbol"]),
        side=side,
        principal=principal,
        entry_price=entry_price,
        entry_fee=entry_fee,
        opened_sequence=event.sequence,
    )
    new_open_positions = dict(state.open_positions)
    new_open_positions[trade_id] = pos

    return replace(
        state,
        available_cash=new_available_cash,
        reserved_principal=new_reserved_principal,
        fees_paid=new_fees_paid,
        open_positions=MappingProxyType(new_open_positions),
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

    exit_price = _finite("exit_price", event.payload["exit_price"], positive=True)
    exit_fee = _finite("exit_fee", event.payload["exit_fee"], non_negative=True)

    # PNL AUTHORITY: gross_pnl is DERIVED here, never trusted from the event
    # payload (MASTER finding R1-G) — the event carries only exit_price and
    # exit_fee as durable facts. PPL-02A-R2: every derived quantity below is
    # separately checked for finiteness — finite inputs do not guarantee a
    # finite result (e.g. division by a very small entry_price can overflow).
    if pos.side is Side.LONG:
        gross_pct = (exit_price - pos.entry_price) / pos.entry_price
    else:
        gross_pct = (pos.entry_price - exit_price) / pos.entry_price
    gross_pct = _finite_derived("gross_pct", gross_pct)

    gross_pnl = _finite_derived("gross_pnl", pos.principal * gross_pct)

    trade_realized_pnl = _finite_derived(
        "trade_realized_pnl", gross_pnl - pos.entry_fee - exit_fee
    )

    new_available_cash = _finite_derived(
        "available_cash", state.available_cash + pos.principal + gross_pnl - exit_fee
    )
    if new_available_cash < 0:
        raise NegativeCashError(
            f"CLOSE {trade_id!r} would drive available_cash negative: "
            f"{state.available_cash} + {pos.principal} + {gross_pnl} - "
            f"{exit_fee} = {new_available_cash}"
        )
    new_reserved_principal = _finite_derived(
        "reserved_principal", state.reserved_principal - pos.principal
    )
    new_fees_paid = _finite_derived("fees_paid", state.fees_paid + exit_fee)
    new_realized_pnl = _finite_derived(
        "realized_pnl", state.realized_pnl + trade_realized_pnl
    )

    new_open_positions = dict(state.open_positions)
    del new_open_positions[trade_id]

    return replace(
        state,
        available_cash=new_available_cash,
        reserved_principal=new_reserved_principal,
        fees_paid=new_fees_paid,
        realized_pnl=new_realized_pnl,
        open_positions=MappingProxyType(new_open_positions),
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

    new_reserved_principal = _finite_derived(
        "reserved_principal", state.reserved_principal - pos.principal
    )
    new_unresolved_capital = _finite_derived(
        "unresolved_capital", state.unresolved_capital + pos.principal
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
        reserved_principal=new_reserved_principal,
        unresolved_capital=new_unresolved_capital,
        # realized_pnl deliberately untouched: outcome stays UNKNOWN, never 0.
        open_positions=MappingProxyType(new_open_positions),
        unresolved_positions=MappingProxyType(new_unresolved),
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
