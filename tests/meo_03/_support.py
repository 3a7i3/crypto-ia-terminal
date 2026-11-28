"""SYNTHETIC helpers for MEO-03 tests: invented reports, never provider output."""

T0 = 1_795_128_000_000_000_000  # ns, a 5-minute boundary
MIN = 60_000_000_000
WIN = 5 * MIN


def bar(i, status="OBSERVED", *, o="100", c="100", buy="0", sell="0", unk="0", tc=1, cvd="0", seg=0, start=T0):
    lo = start + i * MIN
    if status == "NOT_COVERED":
        return {"start_ns": str(lo), "end_ns": str(lo + MIN), "status": status, "trade_count": None,
                "open": None, "close": None, "buy_volume": None, "sell_volume": None, "unknown_volume": None,
                "delta_base": None, "delta_base_bounds": None, "cvd_base": None, "cvd_base_bounds": None,
                "segment": None}
    if status == "OBSERVED_ZERO":
        o = c = None
        tc = 0
    d = str(__import__("decimal").Decimal(buy) - __import__("decimal").Decimal(sell))
    return {"start_ns": str(lo), "end_ns": str(lo + MIN), "status": status, "trade_count": tc, "open": o,
            "close": c, "buy_volume": buy, "sell_volume": sell, "unknown_volume": unk, "delta_base": d,
            "delta_base_bounds": [d, d], "cvd_base": cvd, "cvd_base_bounds": [cvd, cvd], "segment": seg}


def window(k, bars, *, status="COVERED", transport=True, trades=None, volume=None, bounds=None):
    lo = T0 + k * WIN
    w = {"start_ns": str(lo), "end_ns": str(lo + WIN), "status": status,
         "transport_continuous_if_native_aligned": transport, "bars": bars,
         "totals": None, "side_coverage": None, "delta_300s": None}
    if status == "COVERED":
        w["totals"] = {"trade_count": trades if trades is not None else sum(b["trade_count"] for b in bars),
                       "volume_base": volume}
        w["delta_300s"] = {"status": "EXACT" if bounds[0] == bounds[1] else "BOUNDED",
                           "delta_base": bounds[0] if bounds[0] == bounds[1] else None,
                           "delta_base_bounds": bounds}
    return w


def report(windows, *, ack=T0, kind="SYNTHETIC", synthetic=True):
    return {"schema": "meo-01-trades-report/1", "evidence_kind": kind, "synthetic": synthetic,
            "subscription": {"acknowledged": ack is not None, "acknowledged_receipt_ns": None if ack is None else str(ack),
                             "refused": 0, "snapshot": True},
            "source": {"events_sha256": "e" * 64, "frames_sha256": "f" * 64, "capture_code_digest": "c" * 64},
            "flow": {"venue": "kraken", "instrument": "BTC/USDT"}, "windows": windows}


def simple(k, *, first="100", last="101", buy="2", sell="1", unk="0", bounds=None, tc=(1, 1), transport=True,
           seg=0, cvd=("0", "0")):
    """One covered window: two observed minutes (first/last prices) and three zero minutes."""
    from decimal import Decimal as D
    start = T0 + k * WIN
    bars = [bar(0, o=first, c=first, buy=buy, sell="0", tc=tc[0], cvd=cvd[0], seg=seg, start=start),
            bar(1, o=last, c=last, buy="0", sell=sell, unk=unk, tc=tc[1], cvd=cvd[1], seg=seg, start=start)]
    bars += [bar(i, "OBSERVED_ZERO", cvd=cvd[1], seg=seg, start=start) for i in (2, 3, 4)]
    vol = str(D(buy) + D(sell) + D(unk))
    if bounds is None:
        d = str(D(buy) - D(sell))
        bounds = [d, d]
    return window(k, bars, transport=transport, volume=vol, bounds=bounds)
