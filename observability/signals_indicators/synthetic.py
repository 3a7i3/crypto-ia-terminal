"""Fixture SYNTHÉTIQUE déterministe du symbole de référence (BTC, 4 marchés).

Aucune valeur réelle : sert aux tests et à l'écran du Radar de signaux tant
qu'aucun collecteur réel n'existe. Usage :
  python -m observability.signals_indicators.synthetic OUT.json
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

from observability.signals_indicators.contract import INPUT_SCHEMA, REFERENCE_SYMBOL

TF_MS = 3_600_000
AS_OF_MS = 1_795_410_004_000  # 2026-11-23T05:00:04Z
LAST_OPEN_MS = AS_OF_MS - AS_OF_MS % TF_MS - TF_MS  # 04:00Z, dernière barre fermée


def _d(x: Decimal, q: str = "0.1") -> str:
    return format(x.quantize(Decimal(q)), "f")


def _bars(n: int, scale: Decimal, flow: bool, wiggle: int = 0) -> tuple[list, dict]:
    bars = []
    first = LAST_OPEN_MS - (n - 1) * TF_MS
    prev = None
    for i in range(n + 1):  # la dernière est la barre en cours
        k = 120 - n + i  # même trajectoire pour tous les marchés
        mid = Decimal(90_000 + 15 * k + ((k * 37 + wiggle) % 23 - 11) * 20) * scale
        o = prev if prev is not None else mid - Decimal(10)
        c = mid
        h = max(o, c) + Decimal(25 + (k * 7) % 30)
        low = min(o, c) - Decimal(20 + (k * 11) % 30)
        v = Decimal(150 + (k * 53) % 90) + Decimal((k % 5)) / 10
        bar = {"open_ms": first + i * TF_MS, "o": _d(o), "h": _d(h), "l": _d(low), "c": _d(c), "v": _d(v, "0.001")}
        if flow:
            buy = (v * Decimal(45 + (k * 13) % 11) / 100).quantize(Decimal("0.001"))
            bar["buy_v"] = _d(buy, "0.001")
            bar["sell_v"] = _d(v - buy, "0.001")
        bars.append(bar)
        prev = c
    return bars[:-1], bars[-1]


def _book(mid: Decimal, at_ms: int, skew: int) -> dict:
    bids = [[_d(mid - Decimal("0.5") - i, "0.1"), _d(Decimal(1 + (i + skew) % 4) / 2, "0.001")] for i in range(12)]
    asks = [[_d(mid + Decimal("0.5") + i, "0.1"), _d(Decimal(1 + (i * 3 + skew) % 5) / 2, "0.001")] for i in range(12)]
    return {"at_ms": at_ms, "bids": bids, "asks": asks}


def reference_input() -> dict:
    inst = REFERENCE_SYMBOL["instruments"]
    markets = {}
    plan = {
        # marché : (nb barres, échelle de prix, flux achat/vente, carnet frais ?, oscillation)
        "mexc_spot": (120, Decimal("1"), True, True, 0),
        "mexc_perp": (120, Decimal("1.0004"), True, True, 3),
        "kraken_spot": (120, Decimal("0.9999"), True, False, 5),
        "kraken_perp": (20, Decimal("1.0003"), False, True, 7),
    }
    for m, (n, scale, flow, fresh, wig) in plan.items():
        bars, forming = _bars(n, scale, flow, wig)
        mid = Decimal(bars[-1]["c"])
        book_at = AS_OF_MS - 2_000 if fresh else AS_OF_MS - 45_000
        entry = {**inst[m], "listed": True, "bars": bars, "forming": forming,
                 "book": _book(mid, book_at, wig)}
        if m.endswith("_perp"):
            base_oi = 8_000 if m == "mexc_perp" else 3_000
            entry["oi"] = [{"at_ms": LAST_OPEN_MS - TF_MS, "value": str(base_oi)},
                           {"at_ms": LAST_OPEN_MS, "value": str(base_oi + 152)}]
            entry["funding"] = [{"at_ms": AS_OF_MS - 4_000,
                                 "value": "0.0001" if m == "mexc_perp" else "0.00007"}]
        markets[m] = entry
    return {
        "schema": INPUT_SCHEMA,
        "fixture": "SYNTHETIC",
        "base": REFERENCE_SYMBOL["base"],
        "timeframe": "1h",
        "as_of_ms": AS_OF_MS,
        "markets": markets,
    }


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python -m observability.signals_indicators.synthetic OUT.json", file=sys.stderr)
        return 2
    Path(argv[0]).write_text(json.dumps(reference_input(), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
