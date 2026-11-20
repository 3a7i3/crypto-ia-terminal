"""Pure decoders of public last-trade responses already provided as bytes.

No transport, scheduler, credential or file is created here. Each decoder is
bound to the symbol actually requested; a response that cannot be tied to that
request is refused rather than reassigned.

Endpoints decoded (shape only, no call is made):
- MEXC Spot V3 ``GET /api/v3/trades?symbol=<SYMBOL>`` (JSON list, no symbol echo)
- Kraken ``GET /0/public/Trades?pair=<PAIR>`` (``result`` keyed by native pair)
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import ROUND_FLOOR, Decimal, InvalidOperation

from .instruments import EVIDENCE_KINDS, Binding

MAX_BYTES = 512_000
MAX_TRADES = 1000
_DECIMAL = re.compile(r"\d{1,20}(?:\.\d{1,20})?")
MEXC_ENDPOINT = "spot.v3.trades"
KRAKEN_ENDPOINT = "public.Trades"


def strict_json(raw: bytes):
    """Bounded UTF-8 JSON; duplicate keys, NaN/Infinity refused; floats as Decimal."""
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_BYTES:
        raise ValueError("payload missing or too large")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate field")
            out[key] = value
        return out

    def constant(_):
        raise ValueError("non-finite number")

    return json.loads(
        bytes(raw).decode("utf-8"),
        object_pairs_hook=pairs,
        parse_constant=constant,
        parse_float=Decimal,
    )


def payload_sha256(raw: bytes) -> str:
    return hashlib.sha256(bytes(raw)).hexdigest()


def _price(value) -> str:
    if not isinstance(value, str) or not _DECIMAL.fullmatch(value):
        raise ValueError("invalid decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid decimal") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError("decimal must be positive")
    return value


def _ms(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("invalid millisecond timestamp")
    return value


def _context(binding, requested, received_ms, evidence_kind, venue):
    if not isinstance(binding, Binding) or binding.venue != venue:
        raise ValueError("binding venue mismatch")
    if requested != binding.native_symbol:
        raise ValueError("response not tied to the requested symbol")
    _ms(received_ms)
    if evidence_kind not in EVIDENCE_KINDS:
        raise ValueError("invalid evidence kind")


def _record(binding, provider, price, qty, side, trade_ms, trade_id,
            native_time, received_ms, digest, identity_evidence, evidence_kind):
    if trade_ms > received_ms + 86_400_000:
        # Gross impossibility is a decoding error; smaller leads stay data and
        # are classified CLOCK_INCONSISTENT by the composite.
        raise ValueError("trade time far ahead of receipt")
    return {
        "venue": binding.venue,
        "provider": provider,
        "native_symbol": binding.native_symbol,
        "price": price,
        "qty": qty,
        "side": side,
        "trade_ms": trade_ms,
        "native_time": native_time,
        "trade_id": trade_id,
        "received_ms": received_ms,
        "payload_sha256": digest,
        "identity_evidence": identity_evidence,
        "evidence_kind": evidence_kind,
    }


def decode_mexc_trades(raw, *, binding, requested_symbol, received_ms,
                       evidence_kind, provider="mexc"):
    """MEXC returns no symbol: identity comes from the request context only."""
    _context(binding, requested_symbol, received_ms, evidence_kind, "mexc")
    body = strict_json(raw)
    if not isinstance(body, list) or len(body) > MAX_TRADES:
        raise ValueError("MEXC trades must be a bounded list")
    digest = payload_sha256(raw)
    out = []
    for item in body:
        if not isinstance(item, dict):
            raise ValueError("invalid MEXC trade")
        for field in ("price", "qty", "time", "isBuyerMaker"):
            if field not in item:
                raise ValueError("missing MEXC trade field")
        if not isinstance(item["isBuyerMaker"], bool):
            raise ValueError("invalid MEXC side")
        raw_id = item.get("id")
        if raw_id is None:
            trade_id = None
        elif isinstance(raw_id, (str, int)) and not isinstance(raw_id, bool):
            trade_id = str(raw_id)
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", trade_id):
                raise ValueError("invalid MEXC trade id")
        else:
            raise ValueError("invalid MEXC trade id")
        trade_ms = _ms(item["time"])
        out.append(_record(
            binding, provider, _price(item["price"]), _price(item["qty"]),
            "sell" if item["isBuyerMaker"] else "buy", trade_ms, trade_id,
            str(trade_ms), received_ms, digest, "REQUEST_CONTEXT", evidence_kind,
        ))
    return out


def decode_kraken_trades(raw, *, binding, requested_pair, received_ms,
                         evidence_kind, provider="kraken"):
    """Kraken echoes the native pair key; it must be exactly the bound key."""
    _context(binding, requested_pair, received_ms, evidence_kind, "kraken")
    body = strict_json(raw)
    if not isinstance(body, dict) or set(body) != {"error", "result"}:
        raise ValueError("invalid Kraken envelope")
    if body["error"] != []:
        raise ValueError("Kraken returned an error")
    result = body["result"]
    if not isinstance(result, dict) or set(result) != {binding.response_key, "last"}:
        raise ValueError("Kraken response key does not match the requested pair")
    rows = result[binding.response_key]
    if not isinstance(rows, list) or len(rows) > MAX_TRADES:
        raise ValueError("Kraken trades must be a bounded list")
    digest = payload_sha256(raw)
    out = []
    for row in rows:
        if not isinstance(row, list) or len(row) not in (6, 7):
            raise ValueError("invalid Kraken trade row")
        price, volume, seconds, side, _order_type, _misc = row[:6]
        if not isinstance(seconds, (Decimal, int)) or isinstance(seconds, bool):
            raise ValueError("invalid Kraken trade time")
        seconds = Decimal(seconds)
        if not seconds.is_finite() or seconds < 0:
            raise ValueError("invalid Kraken trade time")
        if side not in ("b", "s"):
            raise ValueError("invalid Kraken side")
        trade_id = None
        if len(row) == 7:
            if isinstance(row[6], bool) or not isinstance(row[6], int) or row[6] < 0:
                raise ValueError("invalid Kraken trade id")
            trade_id = str(row[6])
        trade_ms = int((seconds * 1000).to_integral_value(rounding=ROUND_FLOOR))
        out.append(_record(
            binding, provider, _price(price), _price(volume),
            "buy" if side == "b" else "sell", trade_ms, trade_id,
            format(seconds, "f"), received_ms, digest, "NATIVE_KEY_ECHO",
            evidence_kind,
        ))
    return out


def poll_record(binding, *, provider, requested_ms, received_ms, status,
                reason=None, payload=None):
    """One request attempt. A failed read is FETCH_ERROR, never an empty source."""
    _ms(requested_ms)
    _ms(received_ms)
    if received_ms < requested_ms:
        raise ValueError("receipt before request")
    if status not in ("OK", "FETCH_ERROR"):
        raise ValueError("invalid poll status")
    if (status == "OK") != (reason is None):
        raise ValueError("FETCH_ERROR requires a reason, OK forbids one")
    return {
        "venue": binding.venue,
        "native_symbol": binding.native_symbol,
        "provider": provider,
        "requested_ms": requested_ms,
        "received_ms": received_ms,
        "status": status,
        "reason": reason,
        "payload_sha256": None if payload is None else payload_sha256(payload),
    }
