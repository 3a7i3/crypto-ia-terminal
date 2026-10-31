"""Offline comparison of explicitly normalised, timestamped market quotes.

No fetcher, credential, order, strategy, score or runtime integration exists here.
Canonical asset IDs must come from a separately reviewed instrument mapping.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext

UNRESOLVED = {"UNKNOWN", "UNRESOLVED", "NOT_AVAILABLE", ""}
MARKET_KINDS = {"SPOT", "PERPETUAL_LINEAR", "PERPETUAL_INVERSE", "FUTURE_LINEAR", "FUTURE_INVERSE"}


@dataclass(frozen=True)
class InstrumentKey:
    base_asset_id: str
    quote_asset_id: str
    market_kind: str
    settlement_asset_id: str
    contract_identity: str


@dataclass(frozen=True)
class Quote:
    venue: str
    venue_symbol: str
    instrument: InstrumentKey
    bid: Decimal | str | None
    ask: Decimal | str | None
    observed_at: datetime | None
    received_at: datetime
    observer_clock_id: str
    timestamp_kind: str = "UNRESOLVED"
    book_state: str = "UNRESOLVED"
    bid_size_base: Decimal | str | None = None
    ask_size_base: Decimal | str | None = None


def _decimal(value):
    if isinstance(value, bool) or not isinstance(value, (Decimal, str, int)):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result > 0 else None


def _aware(value):
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _ms(delta):
    micros = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
    return Decimal(micros) / 1000


def _fixed(value):
    return format(value, ".8f")


def _instrument_known(instrument):
    return (
        isinstance(instrument, InstrumentKey)
        and isinstance(instrument.market_kind, str)
        and instrument.market_kind in MARKET_KINDS
        and all(isinstance(v, str) and v.strip() and v.strip().upper() not in UNRESOLVED
                for v in asdict(instrument).values())
        and (instrument.market_kind != "SPOT" or instrument.contract_identity == "SPOT")
    )


def _policy(as_of, max_age_ms, max_skew_ms=None):
    if not _aware(as_of):
        raise ValueError("comparison clock must be timezone-aware")
    values = [max_age_ms] if max_skew_ms is None else [max_age_ms, max_skew_ms]
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in values):
        raise ValueError("quality limits must be explicit non-negative integer milliseconds")


def quote_metrics(quote, *, as_of, max_age_ms):
    """Internal bid/ask spread, with missing/stale/invalid states kept explicit."""
    _policy(as_of, max_age_ms)
    result = {
        "status": "NOT_AVAILABLE", "reason": None,
        "venue": quote.venue, "venue_symbol": quote.venue_symbol,
        "timestamp_kind": quote.timestamp_kind,
        "mid": None, "spread_bps": None, "event_age_ms": None,
        "bid_size_base": None, "ask_size_base": None,
    }

    def refused(reason):
        return {**result, "reason": reason}

    if not isinstance(quote.venue, str) or quote.venue.strip().upper() in UNRESOLVED:
        return refused("MISSING_VENUE")
    if quote.venue != quote.venue.strip().lower():
        return refused("NONCANONICAL_VENUE")
    if not isinstance(quote.venue_symbol, str) or quote.venue_symbol.strip().upper() in UNRESOLVED:
        return refused("MISSING_VENUE_SYMBOL")
    if not _instrument_known(quote.instrument):
        return refused("UNRESOLVED_INSTRUMENT")
    if quote.book_state not in ("SNAPSHOT", "SYNCHRONIZED"):
        return refused("BOOK_NOT_SYNCHRONIZED")
    bid, ask = _decimal(quote.bid), _decimal(quote.ask)
    if bid is None or ask is None:
        return refused("MISSING_OR_INVALID_SIDE")
    if ask < bid:
        return refused("CROSSED_BOOK")
    if quote.timestamp_kind not in ("MATCHING_ENGINE", "BOOK_PUBLICATION"):
        return refused("UNRESOLVED_TIMESTAMP_KIND")
    if not _aware(quote.observed_at):
        return refused("MISSING_EXCHANGE_TIMESTAMP")
    if not _aware(quote.received_at):
        return refused("MISSING_RECEIPT_TIMESTAMP")
    if not isinstance(quote.observer_clock_id, str) or not quote.observer_clock_id.strip():
        return refused("UNRESOLVED_OBSERVER_CLOCK")
    if quote.observed_at > quote.received_at or quote.received_at > as_of:
        return refused("FUTURE_OR_INCONSISTENT_CLOCK")
    age = _ms(as_of - quote.observed_at)
    result["event_age_ms"] = str(age)
    if age > max_age_ms:
        return refused("STALE")
    for field in ("bid_size_base", "ask_size_base"):
        value = getattr(quote, field)
        if value is not None:
            number = _decimal(value)
            if number is None:
                return refused("INVALID_BASE_SIZE")
            result[field] = str(number)
    with localcontext() as ctx:
        ctx.prec = 50
        mid = (bid + ask) / 2
        spread = (ask - bid) / mid * 10_000
    return {**result, "status": "AVAILABLE", "reason": None,
            "mid": str(mid), "spread_bps": _fixed(spread)}


def compare_quotes(reference, other, *, as_of, max_age_ms, max_skew_ms):
    """Price basis and gross BBO gaps; never an executable arbitrage verdict."""
    if max_skew_ms is None:
        raise ValueError("max_skew_ms must be explicit")
    _policy(as_of, max_age_ms, max_skew_ms)
    ref = quote_metrics(reference, as_of=as_of, max_age_ms=max_age_ms)
    alt = quote_metrics(other, as_of=as_of, max_age_ms=max_age_ms)
    result = {
        "schema_version": "1.0.0", "authority": "OBSERVATIONAL_TELEMETRY",
        "status": "NOT_AVAILABLE", "reason": None,
        "reference": ref, "other": alt,
        "event_skew_ms": None, "mid_basis_bps": None,
        "buy_reference_sell_other_gross_bps": None,
        "buy_other_sell_reference_gross_bps": None,
        "buy_reference_sell_other_top_size_base": None,
        "buy_other_sell_reference_top_size_base": None,
        "costs_funding_fx_included": False, "execution_authority": False,
    }

    def refused(reason):
        return {**result, "reason": reason}

    if ref["status"] != "AVAILABLE" or alt["status"] != "AVAILABLE":
        return refused("QUOTE_UNAVAILABLE")
    if reference.venue == other.venue:
        return refused("SAME_VENUE")
    if reference.instrument != other.instrument:
        return refused("DIFFERENT_INSTRUMENT")
    if reference.timestamp_kind != other.timestamp_kind:
        return refused("TIMESTAMP_KINDS_DIFFER")
    if reference.observer_clock_id != other.observer_clock_id:
        return refused("OBSERVER_CLOCKS_NOT_ALIGNED")
    skew = abs(_ms(reference.observed_at - other.observed_at))
    result["event_skew_ms"] = str(skew)
    if skew > max_skew_ms:
        return refused("EVENTS_NOT_SYNCHRONIZED")
    with localcontext() as ctx:
        ctx.prec = 50
        ref_mid, alt_mid = Decimal(ref["mid"]), Decimal(alt["mid"])
        bid_ref, ask_ref = _decimal(reference.bid), _decimal(reference.ask)
        bid_alt, ask_alt = _decimal(other.bid), _decimal(other.ask)
        result.update({
            "status": "AVAILABLE",
            "mid_basis_bps": _fixed((alt_mid - ref_mid) / ref_mid * 10_000),
            "buy_reference_sell_other_gross_bps": _fixed((bid_alt - ask_ref) / ask_ref * 10_000),
            "buy_other_sell_reference_gross_bps": _fixed((bid_ref - ask_alt) / ask_alt * 10_000),
        })
    for output, a, b in [
        ("buy_reference_sell_other_top_size_base", reference.ask_size_base, other.bid_size_base),
        ("buy_other_sell_reference_top_size_base", other.ask_size_base, reference.bid_size_base),
    ]:
        if a is not None and b is not None:
            result[output] = str(min(_decimal(a), _decimal(b)))
    return result
