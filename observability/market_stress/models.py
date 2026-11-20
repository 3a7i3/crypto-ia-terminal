"""Caller-supplied identity and observations. Nothing here is inferred from a ticker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import re
from typing import Optional

from observability.venue_quote_comparison import InstrumentKey

# Open vocabulary on purpose: a venue is admitted by an explicit, reviewed binding,
# not by an entry in a closed code table. Adding an exchange needs no code change here.
VENUE_ID = re.compile(r"[a-z][a-z0-9_]{1,30}")
NATIVE_SYMBOL = re.compile(r"[A-Za-z0-9@.:/_-]{1,80}")
PRICE_KINDS = ("BOOK_MID", "LAST_TRADE", "MARK")
TIMESTAMP_KINDS = ("MATCHING_ENGINE", "BOOK_PUBLICATION", "TICKER_PUBLICATION")
OI_UNITS = ("BASE", "QUOTE", "CONTRACTS")
DERIVATIVE_KINDS = ("PERPETUAL_LINEAR", "PERPETUAL_INVERSE", "FUTURE_LINEAR", "FUTURE_INVERSE")


@dataclass(frozen=True)
class StressBinding:
    """One native market of one venue for one instrument, declared by the provider."""

    venue: str
    native_symbol: str
    instrument: InstrumentKey
    mapping_id: str
    mapping_sha256: str


@dataclass(frozen=True)
class Sample:
    """A past observation of the same leg, in the same price kind and OI unit."""

    at: datetime
    price: Decimal | str | None = None
    open_interest: Decimal | str | None = None


@dataclass(frozen=True)
class TradeTape:
    """Executed-trade instants for one leg. Exchange time only; see metrics.timing."""

    events: tuple  # ((timestamp_ms:int, quantity_base:Decimal|str), ...)
    resolution_ms: int
    timestamp_kind: str
    window_start: datetime
    window_end: datetime
    tape_sha256: str


@dataclass(frozen=True)
class LegObservation:
    binding: StressBinding
    observed_at: Optional[datetime]
    received_at: datetime
    observer_clock_id: str
    timestamp_kind: str
    price: Decimal | str | None = None
    price_kind: str = "MARK"
    index_price: Decimal | str | None = None
    funding_rate: Decimal | str | None = None  # signed fraction per funding interval
    funding_interval_s: Optional[int] = None
    next_funding_at: Optional[datetime] = None
    open_interest: Decimal | str | None = None
    open_interest_unit: Optional[str] = None
    contract_size_base: Decimal | str | None = None
    expiry_at: Optional[datetime] = None
    payload_sha256: Optional[str] = None
    samples: tuple = ()
    tape: Optional[TradeTape] = None
    failure: Optional[str] = None
