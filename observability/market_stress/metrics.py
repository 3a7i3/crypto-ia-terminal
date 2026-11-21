"""Pure descriptive metrics in exact Decimal. No score, no threshold, no verdict.

Every function returns a closed dict whose ``status`` is AVAILABLE or NOT_AVAILABLE
with a typed reason: a missing input is never a zero (UNKNOWN != 0).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext

PRECISION = 50
SECONDS_PER_YEAR = 365 * 86_400
# Pre-registered, not tuned. Changing any value is a new contract version.
WINDOWS_S = (3_600, 14_400, 86_400)
TIMING_SCAN = ((60, 1_000), (300, 1_000), (900, 500), (900, 1_000), (900, 2_000), (900, 5_000), (3_600, 1_000))
HISTOGRAM_PERIOD_S = 900
HISTOGRAM_BIN_MS = 1_000
TIMING_MIN_EVENTS = 1_000
TIMING_MAX_EVENTS = 500_000
RESOLUTIONS_MS = (1, 10, 100, 1_000)
FUNDING_REFERENCE_INTERVAL_S = 28_800  # 8 h, display normalisation only


def number(value, *, positive=False, signed=False):
    """Exact finite Decimal from str/int/Decimal; None when absent or invalid."""
    if isinstance(value, bool) or not isinstance(value, (Decimal, str, int)):
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite() or abs(d.adjusted()) > 30 or len(d.as_tuple().digits) > 50:
        return None
    if positive and d <= 0:
        return None
    if not signed and d < 0:
        return None
    return d


def fixed(value, places):
    return format(value, "." + str(places) + "f")


def refused(reason, **empty):
    return {"status": "NOT_AVAILABLE", "reason": reason, **empty}


def ratio_bps(value, reference):
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return (value - reference) / reference * 10_000


def premium(mark, index):
    """Derivative price versus its venue index price, in bps. Both from one observation."""
    m, i = number(mark, positive=True), number(index, positive=True)
    if m is None or i is None:
        return refused("MARK_OR_INDEX_MISSING", bps=None)
    return {"status": "AVAILABLE", "reason": None, "bps": fixed(ratio_bps(m, i), 6)}


def basis(derivative_price, spot_price):
    """Derivative price versus a spot reference of the same base and quote, in bps."""
    d, s = number(derivative_price, positive=True), number(spot_price, positive=True)
    if d is None or s is None:
        return refused("DERIVATIVE_OR_SPOT_MISSING", bps=None, annualized_pct=None)
    return {"status": "AVAILABLE", "reason": None, "bps": fixed(ratio_bps(d, s), 6), "annualized_pct": None}


def annualized_basis(bps, expiry_at, as_of):
    """Simple (non-compounded) annualisation of a dated future's basis."""
    if expiry_at is None:
        return None, "PERPETUAL_HAS_NO_EXPIRY"
    seconds = (expiry_at - as_of).total_seconds()
    if seconds <= 0:
        return None, "EXPIRED_OR_EXPIRING"
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return fixed(Decimal(bps) / 100 * Decimal(SECONDS_PER_YEAR) / Decimal(str(seconds)), 6), None


def funding(rate, interval_s, next_funding_at, as_of):
    """Native funding rate plus two labelled linear conversions (8 h and per year)."""
    r = number(rate, signed=True)
    if r is None:
        return refused("FUNDING_RATE_MISSING", rate=None, interval_s=None, next_funding_utc=None,
                       rate_8h_equivalent=None, annualized_simple_pct=None)
    if isinstance(interval_s, bool) or not isinstance(interval_s, int) or not 60 <= interval_s <= 86_400:
        return refused("FUNDING_INTERVAL_UNKNOWN", rate=None, interval_s=None, next_funding_utc=None,
                       rate_8h_equivalent=None, annualized_simple_pct=None)
    if next_funding_at is not None and next_funding_at <= as_of:
        return refused("NEXT_FUNDING_IN_PAST", rate=None, interval_s=None, next_funding_utc=None,
                       rate_8h_equivalent=None, annualized_simple_pct=None)
    with localcontext() as ctx:
        ctx.prec = PRECISION
        eq8 = r * FUNDING_REFERENCE_INTERVAL_S / interval_s
        yearly = r * SECONDS_PER_YEAR / interval_s * 100
    return {"status": "AVAILABLE", "reason": None, "rate": fixed(r, 10), "interval_s": interval_s,
            "next_funding_utc": None if next_funding_at is None else next_funding_at,
            "rate_8h_equivalent": fixed(eq8, 10), "annualized_simple_pct": fixed(yearly, 6)}


def open_interest(value, unit, price, contract_size_base):
    """Open interest as published, plus a quote-currency notional only when exact."""
    v = number(value)
    if v is None:
        return refused("OPEN_INTEREST_MISSING", value=None, unit=None, notional_quote=None)
    if unit not in ("BASE", "QUOTE", "CONTRACTS"):
        return refused("OPEN_INTEREST_UNIT_UNKNOWN", value=None, unit=None, notional_quote=None)
    p = number(price, positive=True)
    notional, reason = None, None
    with localcontext() as ctx:
        ctx.prec = PRECISION
        if unit == "QUOTE":
            notional = v
        elif p is None:
            reason = "PRICE_MISSING_FOR_NOTIONAL"
        elif unit == "BASE":
            notional = v * p
        else:
            size = number(contract_size_base, positive=True)
            if size is None:
                reason = "CONTRACT_SIZE_UNKNOWN"
            else:
                notional = v * size * p
    return {"status": "AVAILABLE", "reason": reason, "value": format(v, "f"), "unit": unit,
            "notional_quote": None if notional is None else fixed(notional, 8)}


def _sign(value):
    return "UP" if value > 0 else "DOWN" if value < 0 else "FLAT"


def window(now_price, now_oi, samples, as_of, window_s, tolerance_ms):
    """Price and OI change versus the sample nearest as_of - window, within tolerance.

    Signs are reported without interpretation; the sample must be on the same price
    kind and OI unit as the live observation (the producer's declaration).
    """
    target = as_of.timestamp() * 1000 - window_s * 1000
    best, gap = None, None
    for s in samples:
        g = abs(s.at.timestamp() * 1000 - target)
        if g <= tolerance_ms and (gap is None or g < gap):
            best, gap = s, g
    empty = {"window_s": window_s, "sample_gap_ms": None, "price_change_bps": None, "price_sign": None,
             "oi_change_pct": None, "oi_sign": None}
    if best is None:
        return refused("NO_SAMPLE_AT_WINDOW_START", **empty)
    p0, p1 = number(best.price, positive=True), number(now_price, positive=True)
    o0, o1 = number(best.open_interest), number(now_oi)
    out = {**empty, "status": "AVAILABLE", "reason": None, "sample_gap_ms": int(gap)}
    with localcontext() as ctx:
        ctx.prec = PRECISION
        if p0 is not None and p1 is not None:
            d = ratio_bps(p1, p0)
            out["price_change_bps"], out["price_sign"] = fixed(d, 6), _sign(d)
        if o0 is not None and o1 is not None and o0 > 0:
            d = (o1 - o0) / o0 * 100
            out["oi_change_pct"], out["oi_sign"] = fixed(d, 6), _sign(d)
    if out["price_change_bps"] is None and out["oi_change_pct"] is None:
        return refused("SAMPLE_WITHOUT_PRICE_OR_OPEN_INTEREST", **empty)
    return out


def gap_bps(reference, other):
    r, o = number(reference, positive=True), number(other, positive=True)
    return None if r is None or o is None else fixed(ratio_bps(o, r), 6)


def _expected_cells(radius_ms, resolution_ms):
    return 2 * (radius_ms // resolution_ms) + 1


def timing(tape):
    """Concentration of trade instants around period boundaries, beside its baseline.

    Boundaries are multiples of the period since the UTC epoch (:00/:15/:30/:45 for
    900 s). ``expected_share`` is the share a uniform spread over the declared timestamp
    grid would put in the same window; ``placebo_share`` uses boundaries shifted by half
    a period. Bursty trading makes independence tests unsound, so no p-value is published.
    """
    from .models import TradeTape  # local: keep metrics importable on their own

    def unavailable(reason):
        return refused(reason, events=None, volume_base=None, histogram=None, scan=None)

    if not isinstance(tape, TradeTape):
        return unavailable("NO_TRADE_TAPE")
    if tape.timestamp_kind != "MATCHING_ENGINE":
        return unavailable("TIMESTAMP_KIND_NOT_MATCHING_ENGINE")
    if tape.resolution_ms not in RESOLUTIONS_MS:
        return unavailable("RESOLUTION_NOT_ADMITTED")
    n = len(tape.events)
    if n > TIMING_MAX_EVENTS:
        return unavailable("TAPE_TOO_LARGE")
    if n < TIMING_MIN_EVENTS:
        return unavailable("SAMPLE_TOO_SMALL")
    start_ms = int(tape.window_start.timestamp() * 1000)
    end_ms = int(tape.window_end.timestamp() * 1000)
    if end_ms <= start_ms:
        return unavailable("WINDOW_INVALID")
    res = tape.resolution_ms
    stamps, total = [], Decimal(0)
    for event in tape.events:
        if not isinstance(event, tuple) or len(event) != 2:
            return unavailable("EVENT_MALFORMED")
        t, q = event
        qty = number(q, positive=True)
        if isinstance(t, bool) or not isinstance(t, int) or qty is None:
            return unavailable("EVENT_MALFORMED")
        if not start_ms <= t < end_ms:
            return unavailable("EVENT_OUTSIDE_WINDOW")
        if t % res:
            return unavailable("TIMESTAMP_NOT_ON_DECLARED_RESOLUTION")
        stamps.append((t, qty))
        total += qty
    period_ms = HISTOGRAM_PERIOD_S * 1000
    bins = [0] * (period_ms // HISTOGRAM_BIN_MS)
    for t, _ in stamps:
        bins[(t % period_ms) // HISTOGRAM_BIN_MS] += 1
    scan = []
    with localcontext() as ctx:
        ctx.prec = PRECISION
        for period_s, radius_ms in TIMING_SCAN:
            p = period_s * 1000
            cells = Decimal(_expected_cells(radius_ms, res)) * res / p
            counts = [0, 0]
            volumes = [Decimal(0), Decimal(0)]
            for t, q in stamps:
                for k, shift in enumerate((0, p // 2)):
                    phase = (t + shift) % p
                    if min(phase, p - phase) <= radius_ms:
                        counts[k] += 1
                        volumes[k] += q
            row = {"period_s": period_s, "radius_ms": radius_ms, "expected_share": fixed(cells, 8)}
            for key, c, v in (("boundary", counts[0], volumes[0]), ("placebo", counts[1], volumes[1])):
                share, vshare = Decimal(c) / n, v / total
                row[key + "_events"] = c
                row[key + "_count_share"] = fixed(share, 8)
                row[key + "_count_lift"] = fixed(share / cells, 4)
                row[key + "_volume_share"] = fixed(vshare, 8)
                row[key + "_volume_lift"] = fixed(vshare / cells, 4)
            scan.append(row)
    return {"status": "AVAILABLE", "reason": None, "events": n, "volume_base": format(total, "f"),
            "histogram": {"period_s": HISTOGRAM_PERIOD_S, "bin_ms": HISTOGRAM_BIN_MS, "counts": bins},
            "scan": scan}
