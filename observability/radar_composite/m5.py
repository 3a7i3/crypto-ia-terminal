"""Offline synthetic replay of one closed UTC M5 interval."""
import json
import re
import sys
from decimal import Decimal, localcontext
from pathlib import Path

PERIOD = 300_000
STEP = 10_000
MAX_AGE = 5_000
SYMBOLS = {"mexc": "BTCUSDT", "okx": "BTC-USDT"}


def replay(packet):
    start = packet["start_ms"]
    if type(start) is not int or start < 0 or start % PERIOD:
        raise ValueError("expected UTC-aligned M5 start_ms")
    if packet["kind"] != "SYNTHETIC" or packet["version"] != 1:
        raise ValueError("expected synthetic fixture v1")
    slots = {}
    for row in packet["observations"]:
        slot = row["slot_ms"]
        venue = row["venue"]
        if (type(slot) is not int or not start <= slot < start + PERIOD
                or slot % STEP or venue not in SYMBOLS):
            raise ValueError("invalid grid position or venue")
        pair = slots.setdefault(slot, {})
        if venue in pair:
            raise ValueError("duplicate venue at grid position")
        if (row["symbol"] != SYMBOLS[venue] or row["market"] != "spot"
                or row["price_kind"] != "last_trade"):
            raise ValueError("incompatible instrument or price")
        raw = row["price"]
        if not isinstance(raw, str) or not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,8})?", raw):
            raise ValueError("invalid decimal price")
        price = Decimal(raw)
        event, received = row["trade_ms"], row["received_ms"]
        if (price <= 0 or type(event) is not int or type(received) is not int
                or event < 0 or not event <= received <= slot):
            raise ValueError("invalid price or event/receipt ordering")
        pair[venue] = (event, price)

    points = []
    gaps = []
    for slot in range(start, start + PERIOD, STEP):
        pair = slots.get(slot, {})
        reasons = {}
        for venue in SYMBOLS:
            if venue not in pair:
                reasons[venue] = "MISSING"
            elif slot - pair[venue][0] > MAX_AGE:
                reasons[venue] = "STALE_TRADE"
        if reasons:
            gaps.append({"slot_ms": slot, "excluded": reasons})
        else:
            with localcontext() as context:
                context.prec = 32
                value = (pair["mexc"][1] + pair["okx"][1]) / 2
            points.append({"slot_ms": slot, "price": format(value, "f")})

    candle = None
    if not gaps:
        prices = [Decimal(p["price"]) for p in points]
        candle = dict(zip(("open", "high", "low", "close"),
                          map(lambda p: format(p, "f"), (prices[0], max(prices), min(prices), prices[-1]))))
    return {"method": "cat.sampled-last.m5.v1", "kind": "SYNTHETIC",
            "instrument": "BTC/USDT spot", "venues": list(SYMBOLS),
            "start_ms": start, "end_exclusive_ms": start + PERIOD,
            "expected_points": PERIOD // STEP, "valid_points": len(points),
            "status": "INCOMPLETE" if gaps else "COMPLETE", "ohlc": candle,
            "samples": points, "gaps": gaps}


if __name__ == "__main__":
    print(json.dumps(replay(json.loads(Path(sys.argv[1]).read_text())), indent=2))
