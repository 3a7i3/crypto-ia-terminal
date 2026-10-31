"""Eight pure native snapshot decoders. Inputs are bytes, not URLs or clients."""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from observability.venue_quote_comparison import Quote, _instrument_known
from .models import Binding, Decoded, ENDPOINTS

MAX_PAYLOAD_BYTES = 512_000
SPOT_ONLY = {"mexc", "kraken", "bitfinex", "kucoin", "coinbase_exchange"}


def validate_binding(binding):
    if not isinstance(binding, Binding) or binding.venue not in ENDPOINTS:
        raise ValueError("UNSUPPORTED_VENUE")
    if not re.fullmatch(r"[A-Za-z0-9@.:/_-]{1,80}", binding.native_symbol):
        raise ValueError("INVALID_NATIVE_SYMBOL")
    if not _instrument_known(binding.instrument):
        raise ValueError("UNRESOLVED_INSTRUMENT")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", binding.mapping_id):
        raise ValueError("MISSING_MAPPING_ID")
    if not re.fullmatch(r"[a-f0-9]{64}", binding.mapping_sha256):
        raise ValueError("MISSING_MAPPING_HASH")
    if binding.venue in SPOT_ONLY and binding.instrument.market_kind != "SPOT":
        raise ValueError("UNSUPPORTED_PRODUCT_FOR_ENDPOINT")
    if binding.venue == "bitfinex" and not binding.native_symbol.startswith("t"):
        raise ValueError("FUNDING_OR_RAW_BOOK_NOT_SUPPORTED")


def aware(value):
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def number(value, *, zero=False):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("INEXACT_OR_INVALID_NUMBER")
    try:
        d = Decimal(value)
    except (ValueError, InvalidOperation):
        raise ValueError("INVALID_DECIMAL") from None
    if (
        not d.is_finite()
        or d < 0
        or (not zero and d == 0)
        or abs(d.adjusted()) > 30
        or len(d.as_tuple().digits) > 50
    ):
        raise ValueError("INVALID_DECIMAL_RANGE")
    return d


def strict_json(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_PAYLOAD_BYTES:
        raise ValueError("BOUNDED_BYTES_REQUIRED")

    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("DUPLICATE_NATIVE_FIELD")
            out[k] = v
        return out

    def constant(_):
        raise ValueError("NONFINITE_JSON")

    try:
        return json.loads(
            raw.decode("utf-8"),
            parse_float=Decimal,
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("MALFORMED_NATIVE_JSON") from None


def millis(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (str, int))
        or not str(value).isdigit()
    ):
        raise ValueError("INVALID_NATIVE_TIMESTAMP")
    try:
        return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
            milliseconds=int(value)
        )
    except (OverflowError, ValueError):
        raise ValueError("INVALID_NATIVE_TIMESTAMP") from None


def instant(value):
    if not isinstance(value, str) or not re.search(r"(Z|[+-]\d{2}:\d{2})$", value):
        raise ValueError("INVALID_NATIVE_TIMESTAMP")
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("INVALID_NATIVE_TIMESTAMP") from None
    if not aware(d):
        raise ValueError("INVALID_NATIVE_TIMESTAMP")
    return d.astimezone(timezone.utc)


def best(levels, bid):
    if not isinstance(levels, list) or len(levels) > 5000:
        raise ValueError("INVALID_SNAPSHOT_LEVELS")
    parsed, seen = [], set()
    for row in levels:
        if not isinstance(row, list) or len(row) < 2:
            raise ValueError("INVALID_SNAPSHOT_LEVEL")
        price, size = number(row[0]), number(row[1], zero=True)
        if price in seen:
            raise ValueError("DUPLICATE_SNAPSHOT_PRICE_LEVEL")
        seen.add(price)
        if size > 0:
            parsed.append((price, size))
    if not parsed:
        return None, None
    return (max if bid else min)(parsed, key=lambda p: p[0])


def unavailable(
    binding,
    *,
    received_at=None,
    clock_id="",
    reason="SOURCE_NOT_SUPPLIED",
    payload_sha256=None,
):
    validate_binding(binding)
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,79}", reason):
        raise ValueError("INVALID_FAILURE_REASON")
    if received_at is not None and not aware(received_at):
        raise ValueError("INVALID_RECEIPT_CLOCK")
    q = Quote(
        binding.venue,
        binding.native_symbol,
        binding.instrument,
        None,
        None,
        None,
        received_at,
        clock_id,
    )
    return Decoded(
        binding, q, payload_sha256, "REQUEST_CONTEXT", None, "NOT_AVAILABLE", reason
    )


def decode_snapshot(
    binding,
    raw,
    *,
    requested_symbol,
    requested_market_kind,
    received_at,
    clock_id,
    requested_category=None,
):
    """Caller must preserve request identity and mapping; their claims are not certification."""
    validate_binding(binding)
    if (
        requested_symbol != binding.native_symbol
        or requested_market_kind != binding.instrument.market_kind
    ):
        raise ValueError("REQUEST_BINDING_MISMATCH")
    if not aware(received_at) or not isinstance(clock_id, str) or not clock_id.strip():
        raise ValueError("INVALID_RECEIPT_CLOCK")
    doc = strict_json(raw)
    venue = binding.venue
    stamp, kind, note, sequence, identity = (
        None,
        "UNRESOLVED",
        "BOOK_TIME_NOT_SUPPLIED",
        None,
        "REQUEST_CONTEXT",
    )
    try:
        if venue == "mexc":
            bids, asks = doc["bids"], doc["asks"]
            sequence = str(doc["lastUpdateId"])
        elif venue == "bybit":
            category = {
                "SPOT": "spot",
                "PERPETUAL_LINEAR": "linear",
                "FUTURE_LINEAR": "linear",
                "PERPETUAL_INVERSE": "inverse",
                "FUTURE_INVERSE": "inverse",
            }[binding.instrument.market_kind]
            if (
                requested_category != category
                or type(doc["retCode"]) is not int
                or doc["retCode"] != 0
            ):
                raise ValueError("BYBIT_CATEGORY_OR_RESPONSE_ERROR")
            d = doc["result"]
            if d["s"] != binding.native_symbol:
                raise ValueError("NATIVE_SYMBOL_MISMATCH")
            bids, asks = d["b"], d["a"]
            stamp, kind, note = (
                millis(d["ts"]),
                "BOOK_PUBLICATION",
                "SYSTEM_DATA_GENERATION_TS",
            )
            sequence, identity = str(d["u"]), "NATIVE_SYMBOL_ECHO"
        elif venue == "okx":
            if (
                doc["code"] != "0"
                or not isinstance(doc["data"], list)
                or len(doc["data"]) != 1
            ):
                raise ValueError("OKX_RESPONSE_ERROR")
            d = doc["data"][0]
            bids, asks = d["bids"], d["asks"]
            stamp, kind, note = (
                millis(d["ts"]),
                "BOOK_PUBLICATION",
                "ORDER_BOOK_GENERATION_TS",
            )
            sequence = str(d["seqId"]) if "seqId" in d else None
        elif venue == "kraken":
            if (
                doc["error"] != []
                or not isinstance(doc["result"], dict)
                or set(doc["result"]) != {binding.native_symbol}
            ):
                raise ValueError("KRAKEN_ERROR_OR_SYMBOL_MISMATCH")
            d = doc["result"][binding.native_symbol]
            bids, asks = d["bids"], d["asks"]
            note, identity = (
                "LEVEL_TIMES_ARE_NOT_A_BOOK_TIMESTAMP",
                "NATIVE_SYMBOL_ECHO",
            )
        elif venue == "bitfinex":
            if not isinstance(doc, list):
                raise ValueError("BITFINEX_RESPONSE_ERROR")
            bids, asks = [], []
            for row in doc:
                if (
                    not isinstance(row, list)
                    or len(row) != 3
                    or isinstance(row[1], bool)
                    or not isinstance(row[1], int)
                    or row[1] <= 0
                ):
                    raise ValueError("BITFINEX_NON_SNAPSHOT_OR_RAW_BOOK")
                if isinstance(row[2], bool) or not isinstance(
                    row[2], (Decimal, int, str)
                ):
                    raise ValueError("INEXACT_OR_INVALID_NUMBER")
                amount = Decimal(row[2])
                if not amount.is_finite() or amount == 0:
                    raise ValueError("INVALID_DECIMAL_RANGE")
                (bids if amount > 0 else asks).append([row[0], amount.copy_abs()])
        elif venue == "kucoin":
            if doc["code"] != "200000":
                raise ValueError("KUCOIN_RESPONSE_ERROR")
            d = doc["data"]
            bids, asks = (
                [[d["bestBid"], d["bestBidSize"]]],
                [[d["bestAsk"], d["bestAskSize"]]],
            )
            stamp, note, sequence = (
                millis(d["time"]),
                "NATIVE_TIME_SEMANTICS_UNRESOLVED",
                str(d["sequence"]),
            )
        elif venue == "coinbase_exchange":
            bids, asks = doc["bids"], doc["asks"]
            sequence = str(doc["sequence"])
            if "time" in doc:
                stamp, note = (
                    instant(doc["time"]),
                    "OPTIONAL_NATIVE_TIME_SEMANTICS_UNRESOLVED",
                )
        else:
            if doc["coin"] != binding.native_symbol or len(doc["levels"]) != 2:
                raise ValueError("HYPERLIQUID_SYMBOL_OR_LEVELS_MISMATCH")
            bids = [[r["px"], r["sz"]] for r in doc["levels"][0]]
            asks = [[r["px"], r["sz"]] for r in doc["levels"][1]]
            stamp, note, identity = (
                millis(doc["time"]),
                "NATIVE_TIME_SEMANTICS_UNRESOLVED",
                "NATIVE_SYMBOL_ECHO",
            )
        bid, bid_size = best(bids, True)
        ask, ask_size = best(asks, False)
    except (KeyError, TypeError, IndexError, InvalidOperation):
        raise ValueError("INVALID_NATIVE_SNAPSHOT_SHAPE") from None
    if sequence is not None and not re.fullmatch(r"\d{1,30}", sequence):
        raise ValueError("INVALID_NATIVE_SEQUENCE")
    # Derivative sizes may be contracts; never claim base units by relabelling them.
    if binding.instrument.market_kind != "SPOT":
        bid_size = ask_size = None
    q = Quote(
        venue,
        binding.native_symbol,
        binding.instrument,
        bid,
        ask,
        stamp,
        received_at,
        clock_id,
        kind,
        "SNAPSHOT",
        bid_size,
        ask_size,
    )
    return Decoded(
        binding, q, hashlib.sha256(raw).hexdigest(), identity, sequence, note
    )
