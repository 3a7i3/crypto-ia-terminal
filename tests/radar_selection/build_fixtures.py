"""Builder of the four SYNTHETIC Radar R0 universes (invented values only).

    python -m tests.radar_selection.build_fixtures            # rewrite the JSON files
    python -m tests.radar_selection.build_fixtures --check    # compare, write nothing

The committed files under ``observability/radar_selection/fixtures/`` are the
exact output of this script (checked by ``test_fixtures_are_reproducible``).
Catalogue bodies keep the official public shapes read by
``observability.scanner_universe.catalogues``. Prices, spreads, volumes,
costs and L2 statuses are invented; none of them describes a real market.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "observability" / "radar_selection" / "fixtures"
T0 = 1_795_600_000_000          # window start (synthetic)
STEP = 60_000
POINTS = 30
NOW = T0 + (POINTS - 1) * STEP + 30_000
COST_NOTE = "SYNTHETIC_ESTIMATE_R0 : ordre de grandeur inventé, non mesuré"

KRAKEN_ASSETS = {"XXBT": "XBT", "XXDG": "XDG", "ZUSD": "USD", "USDT": "USDT", "USDC": "USDC",
                 "XETH": "ETH", "SOL": "SOL", "ATOM": "ATOM", "ADA": "ADA", "DOT": "DOT"}


# ------------------------------------------------------------- catalogues

def mexc_spot(pairs):
    return {"timezone": "CST", "serverTime": T0, "symbols": [
        {"symbol": b + q, "baseAsset": b, "quoteAsset": q, "status": st, "isSpotTradingAllowed": True,
         "fullName": "fixture"} for b, q, st in pairs]}


def mexc_perp(rows):
    data = []
    for r in rows:
        row = {"state": 0, "futureType": 1, "isHidden": False, "apiAllowed": True}
        row.update(r)
        row.setdefault("settleCoin", row["quoteCoin"])
        row.setdefault("symbol", f"{row['baseCoin']}_{row['quoteCoin']}")
        data.append(row)
    return {"success": True, "code": 0, "data": data}


def kraken_assets():
    return {"error": [], "result": {k: {"aclass": "currency", "altname": v, "decimals": 8}
                                    for k, v in KRAKEN_ASSETS.items()}}


def kraken_pairs(rows):
    result = {}
    for r in rows:
        b, q = KRAKEN_ASSETS[r["base"]], KRAKEN_ASSETS[r["quote"]]
        row = {"altname": b + q, "wsname": f"{b}/{q}", "base": r["base"], "quote": r["quote"], "status": "online"}
        row.update({k: v for k, v in r.items() if k != "key"})
        result[r.get("key", row["altname"])] = row
    return {"error": [], "result": result}


def kraken_perp(rows):
    out = []
    for r in rows:
        row = {"type": "flexible_futures", "tradeable": True, "suspended": False, "isExpired": False,
               "postOnly": False, "contractSize": 1}
        row.update(r)
        row.setdefault("symbol", f"PF_{row['base']}{row['quote']}")
        row.setdefault("pair", f"{row['base']}:{row['quote']}")
        out.append(row)
    return {"result": "success", "instruments": out, "serverTime": "2026-11-24T00:00:00Z"}


def cat(body, received=NOW - 120_000, error=None):
    return {"received_ms": None if error else received, "error": error, "body": None if error else body}


BASE_MEXC_SPOT = [("BTC", "USDT", "1"), ("ETH", "USDT", "1"), ("SOL", "USDT", "1"), ("ATOM", "USDT", "1"),
                  ("ADA", "USDT", "1"), ("DOGE", "USDT", "1"), ("PEPE", "USDT", "1"), ("USDC", "USDT", "1")]
BASE_MEXC_PERP = [{"baseCoin": "BTC", "quoteCoin": "USDT"}, {"baseCoin": "ETH", "quoteCoin": "USDT"},
                  {"baseCoin": "SOL", "quoteCoin": "USDT"}, {"baseCoin": "DOGE", "quoteCoin": "USDT"}]
BASE_KRAKEN_SPOT = [{"base": "XXBT", "quote": "USDT"}, {"base": "XXBT", "quote": "ZUSD", "key": "XXBTZUSD"},
                    {"base": "XETH", "quote": "USDT"}, {"base": "SOL", "quote": "USDT"},
                    {"base": "ATOM", "quote": "USDT"}, {"base": "ADA", "quote": "USDT"},
                    {"base": "XXDG", "quote": "USDT"}, {"base": "USDC", "quote": "USDT"}]
BASE_KRAKEN_PERP = [{"base": "XBT", "quote": "USD"}, {"base": "ETH", "quote": "USD"},
                    {"base": "SOL", "quote": "USD"}]


def catalogues(ms=BASE_MEXC_SPOT, mp=BASE_MEXC_PERP, ks=BASE_KRAKEN_SPOT, kp=BASE_KRAKEN_PERP,
               mp_error=None, kp_received=NOW - 120_000):
    return {
        "mexc_spot_exchange_info": cat(mexc_spot(ms)),
        "mexc_contract_detail": cat(mexc_perp(mp), error=mp_error),
        "kraken_asset_pairs": cat(kraken_pairs(ks)),
        "kraken_assets": cat(kraken_assets()),
        "kraken_futures_instruments": cat(kraken_perp(kp), received=kp_received),
    }


# ------------------------------------------------------------- observations

def fmt(d: Decimal) -> str:
    return str(d.quantize(Decimal("1e-12")).normalize().__format__("f"))


class Samples(list):
    """Sample list that remembers the price kind it was generated for."""

    kind = "LAST_TRADE"


def series(price, amp_bps, *, missing=(), half_spread_bps="1", bbo=True, kind="LAST_TRADE",
           null_t=(), shift_last=0, swap_t=None, crossed_at=None, mid_bad_at=None, seed=1):
    """30 one-minute samples; returns follow a fixed pattern scaled by amp_bps."""
    p = Decimal(price)
    out = []
    for k in range(POINTS):
        if k:
            step = ((k * 7 + seed * 3) % 11) - 5           # -5..5, deterministic
            p = p * (1 + Decimal(amp_bps) * Decimal(step) / Decimal(5) / Decimal(10_000))
        if k in missing:
            continue
        t = T0 + k * STEP - 1_000
        hs = p * Decimal(half_spread_bps) / Decimal(10_000)
        bid, ask = (fmt(p - hs), fmt(p + hs)) if bbo else (None, None)
        price_s = fmt(p)
        if kind == "MID_BBO" and bbo:
            price_s = format(((Decimal(bid) + Decimal(ask)) / 2).normalize(), "f")
        if crossed_at == k:
            bid, ask = ask, bid
        if mid_bad_at == k:
            price_s = fmt(p * Decimal("1.01"))
        out.append({"t_ms": None if k in null_t else t, "price": price_s, "bid": bid, "ask": ask})
    out = Samples(out)
    out.kind = kind
    if shift_last:
        for s in out:
            if s["t_ms"] is not None:
                s["t_ms"] -= shift_last
    if swap_t is not None:
        a, b = swap_t
        out[a]["t_ms"], out[b]["t_ms"] = out[b]["t_ms"], out[a]["t_ms"]
    return out


def cost(kib, basis="ESTIMATED", provenance=COST_NOTE, storage="40", partial=False):
    return {"basis": basis, "provenance": provenance, "network_kib_s": kib,
            "cpu_pct": None if partial else "3", "memory_mib": None if partial else "60",
            "storage_mib_h": storage, "connections": 1, "rate_limit_note": "SYNTHETIC : limite non qualifiée"}


NO_COST = object()


def obs(venue, mtype, native, samples, *, kind=None, trades=500, l2=None, c=None,
        declared=(None, None), ref=None, dataset="X"):
    return {"venue": venue, "market_type": mtype, "native_symbol": native,
            "declared_base": declared[0], "declared_quote": declared[1],
            "evidence_ref": ref or f"SYN:{dataset}:{venue}:{mtype}:{native}",
            "price_kind": kind or samples.kind, "window": {"start_ms": T0 - 1_000 + 1_000, "step_ms": STEP, "points": POINTS},
            "samples": samples,
            "activity": None if trades is None else {"kind": "TRADE_COUNT_WINDOW", "value": trades,
                                                     "evidence_ref": f"SYN:{dataset}:trades:{native}"},
            "l2": l2, "cost": None if c is NO_COST else c if c is not None else cost("120")}


L2_KRAKEN_COMPAT = {"status": "TECHNICALLY_COMPATIBLE",
                    "evidence_ref": "SOURCE:bbo_pilot Kraken WS v2 book depth 10 + CRC32 (compatibilité technique, aucune intégrité prouvée)",
                    "depth_levels": 10, "depth_quote_10bps": None}


def l2_verified(dataset, native, bid="250000", ask="240000"):
    return {"status": "VERIFIED", "evidence_ref": f"SYN:{dataset}:l2-proof:{native}", "depth_levels": 10,
            "depth_quote_10bps": {"bid": bid, "ask": ask}}


def fixture(dataset_id, description, cats, observations, *, previous=None, access=None):
    return {
        "fixture_schema": "radar-fixture/1.0.0",
        "dataset_id": dataset_id,
        "description": description,
        "evidence_kind": "SYNTHETIC",
        "evaluation_time_ms": NOW,
        "policy": {"venues": ["kraken", "mexc"], "market_types": ["SPOT", "PERPETUAL"],
                   "quotes": ["USD", "USDT"], "asset_classes": ["CRYPTO"], "deny": []},
        "catalogues": cats,
        "source_access": access or {m: {"state": "ACCESSIBLE", "reason": None}
                                    for m in ("KRAKEN_PERPETUAL", "KRAKEN_SPOT", "MEXC_PERPETUAL", "MEXC_SPOT")},
        "previous_universe": previous,
        "observations": observations,
    }


# ------------------------------------------------------------- the four universes

def calm():
    d = "R0-SYN-01-CALM"
    o = lambda *a, **k: obs(*a, dataset=d, **k)  # noqa: E731
    return fixture(d, "Univers calme, données correctes et complètes (SYNTHETIC).", catalogues(), [
        o("kraken", "SPOT", "XBTUSDT", series("91000", "1.2", seed=1), l2=L2_KRAKEN_COMPAT, trades=2400, c=cost("80")),
        o("kraken", "SPOT", "XBTUSD", series("91010", "1.1", seed=2), trades=3100, c=cost("80")),
        o("kraken", "SPOT", "ETHUSDT", series("3100", "1.6", seed=3, half_spread_bps="1.5"), trades=1500),
        o("kraken", "SPOT", "SOLUSDT", series("140", "2.5", seed=4, half_spread_bps="3"), trades=600),
        o("kraken", "SPOT", "ATOMUSDT", series("6.2", "3", seed=5, half_spread_bps="6"), trades=120, c=cost("40")),
        o("kraken", "SPOT", "ADAUSDT", series("0.61", "2.8", seed=6, half_spread_bps="4"), trades=150, c=cost("40")),
        o("kraken", "SPOT", "XDGUSDT", series("0.16", "6", seed=7, half_spread_bps="5"), trades=300),
        o("kraken", "PERPETUAL", "PF_XBTUSD", series("91050", "1.3", seed=8, kind="MARK", half_spread_bps="0.5"),
          trades=5200, l2=l2_verified(d, "PF_XBTUSD"), c=cost("300")),
        o("kraken", "PERPETUAL", "PF_ETHUSD", series("3102", "1.7", seed=9, kind="MARK"), trades=2100, c=cost("250")),
        o("kraken", "PERPETUAL", "PF_SOLUSD", series("140.2", "2.2", seed=10, kind="MARK", half_spread_bps="2"), trades=800),
        o("mexc", "SPOT", "BTCUSDT", series("90990", "1.2", seed=11, half_spread_bps="0.4"), trades=9000, c=cost("150")),
        o("mexc", "SPOT", "ETHUSDT", series("3099", "1.5", seed=12, half_spread_bps="0.6"), trades=6000),
        o("mexc", "SPOT", "SOLUSDT", series("139.9", "2.4", seed=13, half_spread_bps="1"), trades=3000),
        o("mexc", "SPOT", "ATOMUSDT", series("6.21", "3.2", seed=14, half_spread_bps="5"), trades=400),
        o("mexc", "SPOT", "ADAUSDT", series("0.611", "3", seed=15, half_spread_bps="3"), trades=700),
        o("mexc", "SPOT", "DOGEUSDT", series("0.161", "7", seed=16, half_spread_bps="2"), trades=2500),
        o("mexc", "SPOT", "PEPEUSDT", series("0.00001", "9", seed=17, half_spread_bps="8"), trades=1800),
        o("mexc", "PERPETUAL", "BTC_USDT", series("91020", "1.3", seed=18, kind="MARK", half_spread_bps="0.3"),
          trades=12000, c=cost("400", basis="MEASURED", provenance="SYNTHETIC_MEASUREMENT_FIXTURE : mesure inventée pour tester la distinction")),
        o("mexc", "PERPETUAL", "ETH_USDT", series("3101", "1.6", seed=19, kind="MARK", half_spread_bps="0.4"), trades=8000),
        o("mexc", "PERPETUAL", "SOL_USDT", series("140.1", "2.3", seed=20, kind="MARK", half_spread_bps="0.8"), trades=4000),
        o("mexc", "PERPETUAL", "DOGE_USDT", series("0.1612", "6.5", seed=21, kind="MARK", half_spread_bps="1"), trades=3500),
    ])


def volatile():
    d = "R0-SYN-02-VOLATILE"
    o = lambda *a, **k: obs(*a, dataset=d, **k)  # noqa: E731
    return fixture(d, "Univers volatil, données correctes (SYNTHETIC).", catalogues(), [
        o("kraken", "SPOT", "XBTUSDT", series("88000", "28", seed=1, half_spread_bps="2"), l2=L2_KRAKEN_COMPAT, trades=8000),
        o("kraken", "SPOT", "XBTUSD", series("88010", "27", seed=2, half_spread_bps="2"), trades=9000),
        o("kraken", "SPOT", "ETHUSDT", series("2900", "40", seed=3, half_spread_bps="3"), trades=5000),
        o("kraken", "SPOT", "SOLUSDT", series("120", "55", seed=4, half_spread_bps="6"), trades=3000),
        o("kraken", "SPOT", "ATOMUSDT", series("5.4", "70", seed=5, half_spread_bps="12"), trades=900),
        o("kraken", "SPOT", "ADAUSDT", series("0.55", "4", seed=6, half_spread_bps="4"), trades=400),
        o("kraken", "PERPETUAL", "PF_XBTUSD", series("88050", "30", seed=7, kind="MARK", half_spread_bps="1"),
          trades=15000, l2=l2_verified(d, "PF_XBTUSD"), c=cost("600")),
        o("kraken", "PERPETUAL", "PF_ETHUSD", series("2905", "42", seed=8, kind="MARK", half_spread_bps="1.5"), trades=7000),
        o("kraken", "PERPETUAL", "PF_SOLUSD", series("120.5", "12", seed=9, kind="MARK", half_spread_bps="2"), trades=2500),
        o("mexc", "SPOT", "BTCUSDT", series("87990", "29", seed=10, half_spread_bps="0.8"), trades=30000, c=cost("450")),
        o("mexc", "SPOT", "ETHUSDT", series("2899", "41", seed=11, half_spread_bps="1"), trades=20000),
        o("mexc", "SPOT", "SOLUSDT", series("119.8", "56", seed=12, half_spread_bps="2"), trades=12000),
        o("mexc", "SPOT", "DOGEUSDT", series("0.14", "80", seed=13, half_spread_bps="3"), trades=15000),
        o("mexc", "SPOT", "PEPEUSDT", series("0.000008", "120", seed=14, half_spread_bps="15"), trades=9000),
        o("mexc", "SPOT", "ADAUSDT", series("0.551", "1.5", seed=15, half_spread_bps="2"), trades=900),
        o("mexc", "PERPETUAL", "BTC_USDT", series("88020", "31", seed=16, kind="MARK", half_spread_bps="0.5"), trades=60000, c=cost("700")),
        o("mexc", "PERPETUAL", "ETH_USDT", series("2902", "43", seed=17, kind="MARK", half_spread_bps="0.6"), trades=40000),
        o("mexc", "PERPETUAL", "SOL_USDT", series("120.2", "57", seed=18, kind="MARK", half_spread_bps="1"), trades=20000),
        o("mexc", "PERPETUAL", "DOGE_USDT", series("0.1402", "82", seed=19, kind="MARK", half_spread_bps="1.5"), trades=25000),
    ])


def gaps():
    d = "R0-SYN-03-ACTIVE-GAPS"
    o = lambda *a, **k: obs(*a, dataset=d, **k)  # noqa: E731
    previous = [
        {"market_id": "kraken:spot:BTC/USDT", "native_symbol": "XBTUSDT", "contract_type": "SPOT", "settlement_asset": None},
        {"market_id": "kraken:spot:ETH/USDT", "native_symbol": "ETHUSDT", "contract_type": "SPOT", "settlement_asset": None},
        {"market_id": "mexc:spot:BTC/USDT", "native_symbol": "BTCUSDT", "contract_type": "SPOT", "settlement_asset": None},
        {"market_id": "mexc:spot:LUNA/USDT", "native_symbol": "LUNAUSDT", "contract_type": "SPOT", "settlement_asset": None},
        {"market_id": "mexc:perp:BTC/USDT", "native_symbol": "BTC_USDT", "contract_type": "LINEAR_PERPETUAL", "settlement_asset": "BTC"},
        {"market_id": "kraken:perp:BTC/USD", "native_symbol": "PF_XBTUSD", "contract_type": "LINEAR_PERPETUAL", "settlement_asset": "USD"},
    ]
    ms = BASE_MEXC_SPOT + [("WIF", "USDT", "1")]
    access = {"KRAKEN_PERPETUAL": {"state": "ACCESSIBLE", "reason": None},
              "KRAKEN_SPOT": {"state": "ACCESSIBLE", "reason": None},
              "MEXC_PERPETUAL": {"state": "DEGRADED", "reason": "SYNTHETIC_HTTP_429_BACKOFF"},
              "MEXC_SPOT": {"state": "ACCESSIBLE", "reason": None}}
    return fixture(d, "Univers actif avec lacunes : trous, source ancienne, horodatages et BBO manquants, "
                      "marché retiré et ajouté (SYNTHETIC).", catalogues(ms=ms), [
        o("kraken", "SPOT", "XBTUSDT", series("92000", "9", seed=1, missing=(4, 5, 17)), l2=L2_KRAKEN_COMPAT, trades=4000),
        o("kraken", "SPOT", "XBTUSD", series("92010", "9", seed=2, missing=tuple(range(8, 20))), trades=4200),
        o("kraken", "SPOT", "ETHUSDT", series("3200", "12", seed=3, missing=tuple(range(2, 20))), trades=2000),
        o("kraken", "SPOT", "SOLUSDT", series("150", "14", seed=4, shift_last=900_000), trades=1500),
        o("kraken", "SPOT", "ATOMUSDT", series("6.8", "11", seed=5, null_t=(3,)), trades=300),
        o("kraken", "SPOT", "ADAUSDT", series("0.65", "10", seed=6, bbo=False), trades=500),
        o("kraken", "PERPETUAL", "PF_XBTUSD", series("92050", "10", seed=7, kind="MARK", missing=(10,)),
          trades=9000, l2={**l2_verified(d, "PF_XBTUSD"), "depth_quote_10bps": {"bid": "300000", "ask": None}}),
        o("kraken", "PERPETUAL", "PF_ETHUSD", series("3205", "13", seed=8, kind="MARK"), trades=None),
        o("mexc", "SPOT", "BTCUSDT", series("91990", "9", seed=9, half_spread_bps="0.5"), trades=20000, c=NO_COST),
        o("mexc", "SPOT", "ETHUSDT", series("3199", "12", seed=10, half_spread_bps="0.7", missing=(0, 29)), trades=12000),
        o("mexc", "SPOT", "SOLUSDT", series("149.8", "15", seed=11, half_spread_bps="1"), trades=8000,
          c=cost("90", partial=True)),
        o("mexc", "SPOT", "WIFUSDT", series("2.1", "35", seed=12, half_spread_bps="6"), trades=6000),
        o("mexc", "SPOT", "DOGEUSDT", series("0.17", "4", seed=13, half_spread_bps="1.5"), trades=7000),
        o("mexc", "PERPETUAL", "BTC_USDT", series("92020", "9", seed=14, kind="MARK", half_spread_bps="0.4"), trades=30000),
        o("mexc", "PERPETUAL", "SOL_USDT", series("150.1", "16", seed=15, kind="MARK", half_spread_bps="0.9",
                                                    missing=(1, 2, 3, 4, 5)), trades=9000),
    ], previous=previous, access=access)


def incoherent():
    d = "R0-SYN-04-INCOHERENT"
    o = lambda *a, **k: obs(*a, dataset=d, **k)  # noqa: E731
    ks = BASE_KRAKEN_SPOT + [{"base": "DOT", "quote": "USDT", "wsname": "DOT/USD"}]
    kp = BASE_KRAKEN_PERP + [{"symbol": "PI_XBTUSD", "type": "futures_inverse", "base": "XBT", "quote": "USD"},
                             {"symbol": "PF_ADAUSD", "type": "mystery_futures", "base": "ADA", "quote": "USD"}]
    access = {"KRAKEN_SPOT": {"state": "ACCESSIBLE", "reason": None},
              "MEXC_SPOT": {"state": "ACCESSIBLE", "reason": None},
              "MEXC_PERPETUAL": {"state": "UNAVAILABLE", "reason": "SYNTHETIC_TRANSPORT_ERROR"}}
    return fixture(d, "Univers à identité ou source incohérente : conflits d'identité, carnet croisé, "
                      "horodatages désordonnés, doublons, catalogue indisponible ou ancien (SYNTHETIC).",
                   catalogues(ks=ks, kp=kp, mp_error="SYNTHETIC_TRANSPORT_ERROR", kp_received=NOW - 3_600_000), [
        o("kraken", "SPOT", "XBTUSDT", series("91000", "2", seed=1), l2=L2_KRAKEN_COMPAT, trades=2000),
        o("kraken", "SPOT", "XBTUSD", series("91000", "2", seed=2), declared=("BTC", "USDT"), trades=2000),
        o("kraken", "SPOT", "ETHUSDT", series("3100", "3", seed=3, crossed_at=7), trades=900),
        o("kraken", "SPOT", "SOLUSDT", series("140", "3", seed=4, swap_t=(5, 6)), trades=700),
        o("kraken", "SPOT", "ADAUSDT", series("0.6", "3", seed=5, kind="MID_BBO", mid_bad_at=9), trades=300),
        o("kraken", "SPOT", "ATOMUSDT", series("6.2", "4", seed=6), trades=200),
        o("kraken", "SPOT", "ATOMUSDT", series("6.3", "4", seed=7), trades=210, ref=f"SYN:{d}:duplicate:ATOMUSDT"),
        o("kraken", "SPOT", "DOTUSDT", series("4.1", "4", seed=8), trades=100),
        o("kraken", "PERPETUAL", "PF_XBTUSD", series("91050", "2", seed=9, kind="MARK"), trades=5000),
        o("kraken", "PERPETUAL", "PF_ETHUSD", series("3101", "3", seed=10, kind="MARK"), trades=1000),
        o("mexc", "SPOT", "BTCUSDT", series("90990", "2", seed=11, half_spread_bps="0.4"), trades=9000),
        o("mexc", "SPOT", "ETHUSDT", series("3099", "3", seed=12, half_spread_bps="0.6"), declared=("ETH", "USDC"), trades=6000),
        o("mexc", "SPOT", "SOLUSDT", series("139.9", "18", seed=13, half_spread_bps="1"), trades=3000),
        o("mexc", "SPOT", "DOGEUSDT", series("0.16", "6", seed=14, half_spread_bps="2"), trades=2000),
        o("mexc", "SPOT", "GHOSTUSDT", series("1.0", "5", seed=15), trades=10),
        o("mexc", "PERPETUAL", "BTC_USDT", series("91020", "2", seed=16, kind="MARK"), trades=12000),
    ], access=access)


FIXTURES = {
    "r0_syn_01_calm.json": calm,
    "r0_syn_02_volatile.json": volatile,
    "r0_syn_03_active_gaps.json": gaps,
    "r0_syn_04_incoherent.json": incoherent,
}


def render(builder) -> bytes:
    return (json.dumps(builder(), indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def main(argv=None) -> int:
    check = "--check" in (argv if argv is not None else sys.argv[1:])
    status = 0
    for name, builder in FIXTURES.items():
        data = render(builder)
        path = OUT / name
        if check:
            same = path.exists() and path.read_bytes() == data
            print(f"{name}: {'OK' if same else 'DIFFERENT'}")
            status |= 0 if same else 1
        else:
            OUT.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            print(f"{name}: {len(data)} bytes")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
