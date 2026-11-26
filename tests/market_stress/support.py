"""Invented prices, funding, open interest and trade instants. No venue was contacted.

Venue names follow the first two venues of the roster (mexc, kraken) plus one
placeholder (exchange_c) to show that a further venue needs no code change.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from observability.market_stress.models import LegObservation, Sample, StressBinding, TradeTape
from observability.venue_quote_comparison import InstrumentKey

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
CLOCK = "SYNTHETIC_CLOCK"
SPOT = InstrumentKey("BTC", "USDT", "SPOT", "USDT", "SPOT")
PERP = InstrumentKey("BTC", "USDT", "PERPETUAL_LINEAR", "USDT", "BTCUSDT-PERP")
QUARTERLY = InstrumentKey("BTC", "USDT", "FUTURE_LINEAR", "USDT", "BTCUSDT-20261225")
SPOT_USD = InstrumentKey("BTC", "USD", "SPOT", "USD", "SPOT")
PERP_INVERSE = InstrumentKey("BTC", "USD", "PERPETUAL_INVERSE", "BTC", "BTCUSD-PERP")


def binding(venue, native, instrument):
    mapping = "SYNTHETIC-%s-%s-%s" % (venue, instrument.market_kind, native)
    return StressBinding(venue, native, instrument, mapping, hashlib.sha256(mapping.encode()).hexdigest())


def sha(name):
    return hashlib.sha256(name.encode()).hexdigest()


def samples(price, oi):
    """24 h, 4 h and 1 h ago: price and open interest both rising into the present."""
    out = []
    for hours, p, o in ((24, "0.97", "0.80"), (4, "0.99", "0.95"), (1, "1.001", "1.02")):
        out.append(Sample(NOW - timedelta(hours=hours), Decimal(price) * Decimal(p),
                          None if oi is None else Decimal(oi) * Decimal(o)))
    return tuple(out)


def tape(clustered=True, n=5000, resolution_ms=1):
    """Deterministic one-hour tape; with ``clustered`` ~12 % of trades sit on :00/:15/:30/:45."""
    start = NOW - timedelta(hours=1)
    base = int(start.timestamp() * 1000)
    events, state = [], 12345
    for i in range(n):
        state = (state * 1103515245 + 12345) % 2**31
        offset = (state % 3_600_000) // resolution_ms * resolution_ms
        if clustered and i % 8 == 0:
            quarter = (state % 4) * 900_000
            jitter = ((state >> 8) % 400) // resolution_ms * resolution_ms
            offset = (quarter + jitter) % 3_600_000
        events.append((base + offset - (base % resolution_ms), Decimal(1 + state % 5) / 100))
    events = tuple(sorted((t - (t % resolution_ms), q) for t, q in events))
    return TradeTape(events, resolution_ms, "MATCHING_ENGINE", start, NOW, sha("tape" + str(clustered)))


def observation(b, *, price, price_kind="MARK", index=None, funding=None, oi=None, unit="BASE", expiry=None,
                age_ms=200, kind="TICKER_PUBLICATION", hist=True, with_tape=False, contract=None, clock=CLOCK):
    observed = NOW - timedelta(milliseconds=age_ms)
    return LegObservation(
        b, observed, observed + timedelta(milliseconds=30), clock, kind, price=price, price_kind=price_kind,
        index_price=index, funding_rate=funding, funding_interval_s=None if funding is None else 28_800,
        next_funding_at=None if funding is None else NOW + timedelta(hours=3), open_interest=oi,
        open_interest_unit=None if oi is None else unit, contract_size_base=contract, expiry_at=expiry,
        payload_sha256=sha("payload" + b.venue + b.native_symbol),
        samples=samples(price, oi) if hist else (), tape=tape() if with_tape else None)


def roster():
    return [
        binding("mexc", "BTC_USDT", SPOT), binding("mexc", "BTC_USDT-PERP", PERP),
        binding("exchange_c", "BTCUSDT", PERP), binding("exchange_c", "BTCUSDT-1225", QUARTERLY),
        binding("kraken", "XBTUSD", SPOT_USD), binding("kraken", "PI_XBTUSD", PERP_INVERSE),
    ]


def pilot():
    b = roster()
    obs = [
        observation(b[0], price="100000", price_kind="BOOK_MID", hist=True),
        observation(b[1], price="100150", index="100020", funding="0.0001", oi="1500", with_tape=True),
        observation(b[2], price="100170", index="100030", funding="0.0003", oi="900", age_ms=60),
        observation(b[3], price="101500", index="100030", oi="400",
                    expiry=datetime(2026, 12, 25, 8, tzinfo=timezone.utc)),
        observation(b[4], price="99990", price_kind="BOOK_MID"),
        observation(b[5], price="100100", index="99995", funding="-0.00005", oi="80000000", unit="QUOTE"),
    ]
    return b, obs
