"""The pilot's local helper copies behave exactly like the Flux originals (differential)."""

from decimal import Decimal

import pytest

from observability.flux_collection_pilot import exactjson as xj
from observability.market_flow import exact as orig_exact, l2

TIMES = ["2026-11-05T08:00:00Z", "2026-11-05T08:00:00.1Z", "2026-11-05T08:00:00.123456789Z", "1970-01-01T00:00:00Z",
         "0001-01-01T00:00:00Z", "2026-13-01T00:00:00Z", "2026-02-30T00:00:00Z", "2026-11-05 08:00:00Z",
         "2026-11-05T08:00:00+00:00", "2026-11-05T08:00:00.1234567891Z", "", "x", None, 5, "2026-11-05T24:00:00Z"]
JSONS = [b'{"a":1}', b'{"a":1,"a":2}', b'{"a":1.5}', b'{"a":NaN}', b'{"a":Infinity}', b"{", b"", b"\xff", b'[1,2]',
         b'{"a":1e400}', b'{"a":10}', b'[' * 5000 + b']' * 5000, b'x' * 512_001, b'{"a":"' + b"x" * 100 + b'"}']


@pytest.mark.parametrize("t", TIMES)
def test_rfc3339_matches_the_original(t):
    def run(f, ref):
        try:
            return ("ok", f(t))
        except ref as e:
            return ("refused", str(e))
    assert run(xj.parse_rfc3339_ns, xj.Refusal) == run(l2.parse_rfc3339_ns, l2.L2Refusal)


@pytest.mark.parametrize("raw", JSONS)
def test_strict_json_matches_the_original(raw):
    def run(f, ref):
        try:
            return ("ok", f(raw))
        except ref as e:
            return ("refused", str(e))
    assert run(xj.strict_json, xj.Refusal) == run(l2._strict_json, l2.L2Refusal)


def test_constants_and_exact_context_match_the_original():
    assert (xj.MAX_MESSAGE_BYTES, xj.SIDES) == (l2.MAX_MESSAGE_BYTES, l2.SIDES)
    a, b = xj.EXACT, orig_exact.EXACT
    assert (a.prec, a.Emax, a.Emin, a.rounding, a.capitals, a.clamp) == (b.prec, b.Emax, b.Emin, b.rounding, b.capitals, b.clamp)
    assert {k for k, v in a.traps.items() if v} == {k for k, v in b.traps.items() if v}
    assert xj.exact(lambda: Decimal("1.5") * Decimal("2.5"))() == Decimal("3.75")
