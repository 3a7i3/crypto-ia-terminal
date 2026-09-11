"""
order_authorization.py — Pre-network order authorization boundary
(O-02W-PRE-T1-E REM-A, docs/contracts/O-02W-PRE-T1-E_ORDER_CYCLE_SAFETY.md).

Single typed boundary that every source-reachable exchange-mutation path
(`ExecutionEngine._place_live_order` / `create_futures_order`,
`PositionManager._send_close_order`) must call and obey BEFORE its first
network mutation call.

Scope (REM-A only — see docs/adr/0019-pre-network-order-authorization.md):
  - reject invalid/non-finite/non-positive amounts (no substitution)
  - never let precision normalization or minimum-notional handling enlarge
    the authorized amount/notional
  - verify BUY uses available quote balance, SELL uses available base
    balance — never scientific capital, never fabricated
  - fail closed on missing/malformed metadata or balance
  - fail closed on any denied trading authority

Explicitly OUT OF SCOPE (reserved for REM-B/REM-C): clientOrderId /
deterministic order identity, durable intent-before-network journaling,
retry/reconciliation, partial-fill state machines, PendingOrderTracker
activation. This module does not implement any of those and callers must
not infer they exist from its presence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from enum import Enum
from typing import Optional


class DenialReason(str, Enum):
    """Closed vocabulary — every denial MUST use exactly one of these."""

    INVALID_AMOUNT = "INVALID_AMOUNT"
    NON_FINITE_AMOUNT = "NON_FINITE_AMOUNT"
    NON_POSITIVE_AMOUNT = "NON_POSITIVE_AMOUNT"
    ABOVE_AUTHORIZED_EXPOSURE = "ABOVE_AUTHORIZED_EXPOSURE"
    BELOW_MIN_NOTIONAL = "BELOW_MIN_NOTIONAL"
    PRECISION_COLLAPSE = "PRECISION_COLLAPSE"
    PRECISION_WOULD_INCREASE_EXPOSURE = "PRECISION_WOULD_INCREASE_EXPOSURE"
    INSUFFICIENT_QUOTE_BALANCE = "INSUFFICIENT_QUOTE_BALANCE"
    INSUFFICIENT_BASE_BALANCE = "INSUFFICIENT_BASE_BALANCE"
    BALANCE_UNAVAILABLE = "BALANCE_UNAVAILABLE"
    AUTHORITY_DENIED = "AUTHORITY_DENIED"
    UNSUPPORTED_MARKET_SEMANTICS = "UNSUPPORTED_MARKET_SEMANTICS"
    METADATA_UNAVAILABLE = "METADATA_UNAVAILABLE"


@dataclass(frozen=True)
class OrderAuthorizationResult:
    """Explicit, immutable pre-network authorization outcome.

    A bare boolean is never sufficient — every field here is required so a
    caller (or a test) can prove exactly what was authorized/denied and why,
    without re-deriving it from logs.
    """

    authorized: bool
    symbol: str
    side: str  # "buy" | "sell"
    requested_amount: float  # USD notional as requested by the caller
    authorized_max_amount: float  # USD ceiling this request may not exceed
    normalized_amount: float  # USD notional after precision normalization
    normalized_qty: float  # base-asset quantity after precision normalization
    authorized_max_notional: float
    denial_reason: Optional[DenialReason]
    balance_source: Optional[str]
    precision_amount: Optional[float]
    min_notional: Optional[float]
    detail: str = ""


def _to_finite_positive_decimal(value, allow_zero: bool = False) -> Optional[Decimal]:
    """Best-effort conversion honoring fail-closed semantics.

    Returns None (caller must treat as invalid/unavailable) if `value` is
    missing, malformed, non-finite, or non-positive (unless allow_zero).
    """
    if value is None:
        return None
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    if f < 0 or (f == 0 and not allow_zero):
        return None
    try:
        return Decimal(str(f))
    except (InvalidOperation, ValueError):
        return None


def _deny(
    *,
    symbol: str,
    side: str,
    requested_amount,
    authorized_max_amount: float,
    reason: DenialReason,
    balance_source: Optional[str] = None,
    precision_amount: Optional[float] = None,
    min_notional: Optional[float] = None,
    detail: str = "",
) -> OrderAuthorizationResult:
    try:
        req = float(requested_amount)
        if math.isnan(req) or math.isinf(req):
            req = 0.0
    except (TypeError, ValueError):
        req = 0.0
    return OrderAuthorizationResult(
        authorized=False,
        symbol=symbol,
        side=side,
        requested_amount=req,
        authorized_max_amount=authorized_max_amount,
        normalized_amount=0.0,
        normalized_qty=0.0,
        authorized_max_notional=authorized_max_amount,
        denial_reason=reason,
        balance_source=balance_source,
        precision_amount=precision_amount,
        min_notional=min_notional,
        detail=detail,
    )


def authorize_order(
    *,
    symbol: str,
    side: str,
    requested_amount,
    price,
    amount_precision,
    min_notional,
    authorized_max_amount: Optional[float] = None,
    available_quote_balance=None,
    available_base_balance=None,
    balance_error: bool = False,
    balance_source: str = "unknown",
    authority_denied: bool = False,
    authority_reason: str = "",
    market_semantics_supported: bool = True,
) -> OrderAuthorizationResult:
    """The single pre-network authorization boundary.

    `requested_amount` and `price` are accepted as-is (any type) so callers
    can pass through whatever a caller/strategy produced — validation, not
    substitution, is this function's entire job. `requested_amount` is a USD
    notional (matches ExecutionEngine's existing `size` semantics); for
    PositionManager close orders callers pass the position's base quantity
    valued at current price (see call site docstrings).

    `authorized_max_amount` is the explicit ceiling this request may not
    exceed (e.g. an already-decided position/order size). If omitted, the
    requested amount is its own ceiling — this function never widens intent,
    only ever narrows or rejects it.
    """
    side_norm = str(side).strip().lower() if isinstance(side, str) else ""
    if side_norm not in ("buy", "sell"):
        return _deny(
            symbol=symbol,
            side=str(side),
            requested_amount=requested_amount,
            authorized_max_amount=float(authorized_max_amount or 0.0),
            reason=DenialReason.UNSUPPORTED_MARKET_SEMANTICS,
            detail=f"unsupported side: {side!r}",
        )

    if not market_semantics_supported:
        return _deny(
            symbol=symbol,
            side=side_norm,
            requested_amount=requested_amount,
            authorized_max_amount=float(authorized_max_amount or 0.0),
            reason=DenialReason.UNSUPPORTED_MARKET_SEMANTICS,
            detail="market semantics not provably safe for this path",
        )

    # ── 1. Authority — fail closed, checked before spending any effort on
    #      the rest of the pipeline (Correction E). ─────────────────────────
    if authority_denied:
        return _deny(
            symbol=symbol,
            side=side_norm,
            requested_amount=requested_amount,
            authorized_max_amount=float(authorized_max_amount or 0.0),
            reason=DenialReason.AUTHORITY_DENIED,
            detail=authority_reason or "trading authority denied",
        )

    # ── 2. Amount validity (Correction A) ───────────────────────────────────
    if requested_amount is None:
        return _deny(
            symbol=symbol,
            side=side_norm,
            requested_amount=requested_amount,
            authorized_max_amount=float(authorized_max_amount or 0.0),
            reason=DenialReason.INVALID_AMOUNT,
            detail="amount missing",
        )
    try:
        amount_f = float(requested_amount)
    except (TypeError, ValueError):
        return _deny(
            symbol=symbol,
            side=side_norm,
            requested_amount=requested_amount,
            authorized_max_amount=float(authorized_max_amount or 0.0),
            reason=DenialReason.INVALID_AMOUNT,
            detail=f"amount not numeric: {requested_amount!r}",
        )
    if math.isnan(amount_f) or math.isinf(amount_f):
        return _deny(
            symbol=symbol,
            side=side_norm,
            requested_amount=requested_amount,
            authorized_max_amount=float(authorized_max_amount or 0.0),
            reason=DenialReason.NON_FINITE_AMOUNT,
            detail=f"amount non-finite: {amount_f}",
        )
    if amount_f <= 0:
        return _deny(
            symbol=symbol,
            side=side_norm,
            requested_amount=amount_f,
            authorized_max_amount=float(authorized_max_amount or 0.0),
            reason=DenialReason.NON_POSITIVE_AMOUNT,
            detail=f"amount not positive: {amount_f}",
        )

    ceiling = amount_f if authorized_max_amount is None else float(authorized_max_amount)
    if ceiling <= 0 or math.isnan(ceiling) or math.isinf(ceiling):
        return _deny(
            symbol=symbol,
            side=side_norm,
            requested_amount=amount_f,
            authorized_max_amount=0.0,
            reason=DenialReason.INVALID_AMOUNT,
            detail=f"invalid authorized ceiling: {authorized_max_amount!r}",
        )
    if amount_f > ceiling:
        return _deny(
            symbol=symbol,
            side=side_norm,
            requested_amount=amount_f,
            authorized_max_amount=ceiling,
            reason=DenialReason.ABOVE_AUTHORIZED_EXPOSURE,
            detail=f"requested {amount_f} exceeds authorized max {ceiling}",
        )

    # ── 3. Metadata (Correction B/C) — fail closed if absent/malformed ─────
    price_dec = _to_finite_positive_decimal(price)
    if price_dec is None:
        return _deny(
            symbol=symbol,
            side=side_norm,
            requested_amount=amount_f,
            authorized_max_amount=ceiling,
            reason=DenialReason.METADATA_UNAVAILABLE,
            detail=f"invalid/unavailable price: {price!r}",
        )
    precision_dec = _to_finite_positive_decimal(amount_precision)
    if precision_dec is None:
        return _deny(
            symbol=symbol,
            side=side_norm,
            requested_amount=amount_f,
            authorized_max_amount=ceiling,
            reason=DenialReason.METADATA_UNAVAILABLE,
            detail=f"invalid/unavailable amount precision: {amount_precision!r}",
        )
    min_notional_dec = _to_finite_positive_decimal(min_notional, allow_zero=True)
    if min_notional_dec is None:
        return _deny(
            symbol=symbol,
            side=side_norm,
            requested_amount=amount_f,
            authorized_max_amount=ceiling,
            reason=DenialReason.METADATA_UNAVAILABLE,
            detail=f"invalid/unavailable min notional: {min_notional!r}",
            precision_amount=float(precision_dec),
        )

    # ── 4. Precision normalization — conservative, never enlarges exposure
    #      (Correction C). Always floor towards zero, using exact Decimal
    #      arithmetic so binary-float artifacts cannot create a phantom
    #      increase. ────────────────────────────────────────────────────────
    authorized_amount_dec = Decimal(str(ceiling))
    raw_qty = Decimal(str(amount_f)) / price_dec
    step = precision_dec
    normalized_qty = (raw_qty / step).to_integral_value(rounding=ROUND_DOWN) * step
    if normalized_qty < 0:
        normalized_qty = Decimal("0")
    normalized_notional = normalized_qty * price_dec

    if normalized_notional > authorized_amount_dec:
        # Defensive: floor-rounding should never do this, but the boundary
        # must refuse rather than trust the arithmetic blindly.
        return _deny(
            symbol=symbol,
            side=side_norm,
            requested_amount=amount_f,
            authorized_max_amount=ceiling,
            reason=DenialReason.PRECISION_WOULD_INCREASE_EXPOSURE,
            detail=(
                f"normalized notional {normalized_notional} exceeds authorized "
                f"{authorized_amount_dec}"
            ),
            precision_amount=float(precision_dec),
            min_notional=float(min_notional_dec),
        )

    if normalized_qty <= 0:
        return _deny(
            symbol=symbol,
            side=side_norm,
            requested_amount=amount_f,
            authorized_max_amount=ceiling,
            reason=DenialReason.PRECISION_COLLAPSE,
            detail=f"amount {amount_f} collapses to zero at precision step {step}",
            precision_amount=float(precision_dec),
            min_notional=float(min_notional_dec),
        )

    # ── 5. Minimum notional — reject, never amplify (Correction B) ─────────
    if normalized_notional < min_notional_dec:
        return _deny(
            symbol=symbol,
            side=side_norm,
            requested_amount=amount_f,
            authorized_max_amount=ceiling,
            reason=DenialReason.BELOW_MIN_NOTIONAL,
            detail=(
                f"normalized notional {normalized_notional} < min notional "
                f"{min_notional_dec}"
            ),
            precision_amount=float(precision_dec),
            min_notional=float(min_notional_dec),
        )

    # ── 6. Balance — correct executable asset per side (Correction D) ──────
    if balance_error:
        return _deny(
            symbol=symbol,
            side=side_norm,
            requested_amount=amount_f,
            authorized_max_amount=ceiling,
            reason=DenialReason.BALANCE_UNAVAILABLE,
            balance_source=balance_source,
            precision_amount=float(precision_dec),
            min_notional=float(min_notional_dec),
            detail="balance fetch reported an error",
        )

    if side_norm == "buy":
        quote_dec = _to_finite_positive_decimal(available_quote_balance, allow_zero=True)
        if quote_dec is None:
            return _deny(
                symbol=symbol,
                side=side_norm,
                requested_amount=amount_f,
                authorized_max_amount=ceiling,
                reason=DenialReason.BALANCE_UNAVAILABLE,
                balance_source=balance_source,
                precision_amount=float(precision_dec),
                min_notional=float(min_notional_dec),
                detail=f"invalid/missing quote balance: {available_quote_balance!r}",
            )
        if quote_dec < normalized_notional:
            return _deny(
                symbol=symbol,
                side=side_norm,
                requested_amount=amount_f,
                authorized_max_amount=ceiling,
                reason=DenialReason.INSUFFICIENT_QUOTE_BALANCE,
                balance_source=balance_source,
                precision_amount=float(precision_dec),
                min_notional=float(min_notional_dec),
                detail=f"quote balance {quote_dec} < required {normalized_notional}",
            )
    else:  # sell
        base_dec = _to_finite_positive_decimal(available_base_balance, allow_zero=True)
        if base_dec is None:
            return _deny(
                symbol=symbol,
                side=side_norm,
                requested_amount=amount_f,
                authorized_max_amount=ceiling,
                reason=DenialReason.BALANCE_UNAVAILABLE,
                balance_source=balance_source,
                precision_amount=float(precision_dec),
                min_notional=float(min_notional_dec),
                detail=f"invalid/missing base balance: {available_base_balance!r}",
            )
        if base_dec < normalized_qty:
            return _deny(
                symbol=symbol,
                side=side_norm,
                requested_amount=amount_f,
                authorized_max_amount=ceiling,
                reason=DenialReason.INSUFFICIENT_BASE_BALANCE,
                balance_source=balance_source,
                precision_amount=float(precision_dec),
                min_notional=float(min_notional_dec),
                detail=f"base balance {base_dec} < required {normalized_qty}",
            )

    return OrderAuthorizationResult(
        authorized=True,
        symbol=symbol,
        side=side_norm,
        requested_amount=amount_f,
        authorized_max_amount=ceiling,
        normalized_amount=float(normalized_notional),
        normalized_qty=float(normalized_qty),
        authorized_max_notional=ceiling,
        denial_reason=None,
        balance_source=balance_source,
        precision_amount=float(precision_dec),
        min_notional=float(min_notional_dec),
        detail="authorized",
    )


def evaluate_trading_authority(
    *,
    paper_trading_enabled: bool,
    live_trading_confirmed: bool,
    exchange_present: bool,
    live_mode: bool,
    halted: bool = False,
    safe_mode: bool = False,
    kill_switch: bool = False,
    execution_mode_supported: bool = True,
) -> tuple[bool, str]:
    """Composes the trading-authority gates this repo already has (fail
    closed) into a single (allowed, reason) answer, used immediately before
    a mutation call. Documents the composition explicitly per Correction E
    rather than claiming one canonical authority module exists.

    Order of evaluation matters only for the human-readable reason; every
    listed condition is independently sufficient to deny.
    """
    if not execution_mode_supported:
        return False, "unsupported_execution_mode"
    if not exchange_present:
        return False, "missing_exchange"
    if not live_mode:
        return False, "not_in_live_mode"
    if paper_trading_enabled:
        return False, "blocked_by_paper_gate"
    if not live_trading_confirmed:
        return False, "live_trading_not_confirmed"
    if halted:
        return False, "session_halted"
    if safe_mode:
        return False, "safe_mode_active"
    if kill_switch:
        return False, "kill_switch_engaged"
    return True, "authorized"
