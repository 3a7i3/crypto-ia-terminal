"""Local copies of three small, already-reviewed helpers, pinned to their originals by a test.

The pilot deliberately imports nothing from the Flux core package: collection is not
Flux admission, and an existing repository test keeps every other consumer of that
package out. The copies are: strict JSON (duplicate keys, JSON numbers with a
fraction and non-finite constants refused), exact RFC 3339 'Z' to integer
nanoseconds, and the exact-decimal arithmetic context. ``tests/flux_collection_pilot/
test_pinned_copies.py`` compares each with its original on a differential corpus.
"""

from calendar import timegm
from datetime import datetime, timezone
from decimal import (Clamped, Context, DivisionByZero, Inexact, InvalidOperation, Overflow, Rounded,
                     Subnormal, Underflow, localcontext)
from functools import wraps
import json
import re

MAX_MESSAGE_BYTES = 512_000
SIDES = {"bid": "bids", "offer": "asks"}
_RFC3339 = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?Z")


class Refusal(ValueError):
    """Stable reason code in the message text."""


def parse_rfc3339_ns(text):
    if not isinstance(text, str):
        raise Refusal("TIME_NOT_TEXT")
    m = _RFC3339.fullmatch(text)
    if not m:
        raise Refusal("TIME_FORMAT_REFUSED")
    y, mo, d, h, mi, s = (int(x) for x in m.groups()[:6])
    try:
        moment = datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)
    except ValueError:
        raise Refusal("TIME_VALUE_REFUSED") from None
    fraction = (m.group(7) or "").ljust(9, "0")
    return timegm(moment.timetuple()) * 1_000_000_000 + int(fraction or "0")


def strict_json(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_MESSAGE_BYTES:
        raise Refusal("BOUNDED_BYTES_REQUIRED")

    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise Refusal("DUPLICATE_NATIVE_FIELD")
            out[k] = v
        return out

    def constant(_):
        raise Refusal("NONFINITE_JSON")

    def no_float(_):
        raise Refusal("JSON_NUMBER_FRACTION_REFUSED")

    try:
        return json.loads(raw.decode("utf-8"), parse_float=no_float, object_pairs_hook=pairs, parse_constant=constant)
    except Refusal:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise Refusal("INVALID_JSON") from None


EXACT = Context(
    prec=1000, Emax=999999, Emin=-999999, rounding="ROUND_HALF_EVEN", capitals=1, clamp=0, flags=[],
    traps=[Inexact, Rounded, InvalidOperation, DivisionByZero, Overflow, Underflow, Subnormal, Clamped],
)


def exact(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        with localcontext(EXACT):
            return fn(*args, **kwargs)

    return wrapper
