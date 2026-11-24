"""Synthetic official-shape catalogues for Scanner V1 tests (invented values only)."""
import json

T0 = 1_795_400_000_000


def mexc_spot(*pairs, overrides=None):
    """pairs: (base, quote) or (base, quote, status, allowed)."""
    symbols = []
    for p in pairs:
        base, quote, status, allowed = (*p, "1", True)[:4] if len(p) == 2 else p
        symbols.append({"symbol": base + quote, "baseAsset": base, "quoteAsset": quote,
                        "status": status, "isSpotTradingAllowed": allowed, "fullName": "fixture"})
    body = {"timezone": "CST", "serverTime": T0, "symbols": symbols}
    body.update(overrides or {})
    return json.dumps(body).encode()


def mexc_perp(*entries):
    """entries: (base, quote) or dict overrides merged on the default linear perpetual."""
    data = []
    for e in entries:
        if isinstance(e, tuple):
            e = {"baseCoin": e[0], "quoteCoin": e[1]}
        row = {"state": 0, "futureType": 1, "isHidden": False, "apiAllowed": True}
        row.update(e)
        row.setdefault("settleCoin", row["quoteCoin"])
        row.setdefault("symbol", f"{row['baseCoin']}_{row['quoteCoin']}")
        data.append(row)
    return json.dumps({"success": True, "code": 0, "data": data}).encode()


KRAKEN_ASSETS = {"XXBT": "XBT", "XXDG": "XDG", "ZUSD": "USD", "USDT": "USDT", "USDC": "USDC",
                 "SOL": "SOL", "ATOM": "ATOM", "XETH": "ETH", "ADA": "ADA", "BTC": "BTC"}


def kraken_assets(extra=None):
    assets = dict(KRAKEN_ASSETS, **(extra or {}))
    return json.dumps({"error": [], "result": {k: {"aclass": "currency", "altname": v, "decimals": 8}
                                               for k, v in assets.items()}}).encode()


def kraken_pairs(*entries):
    """entries: (base_key, quote_key) or (base_key, quote_key, status) or dict."""
    result = {}
    for e in entries:
        if isinstance(e, tuple):
            e = {"base": e[0], "quote": e[1], "status": e[2] if len(e) > 2 else "online"}
        b, q = KRAKEN_ASSETS.get(e["base"], e["base"]), KRAKEN_ASSETS.get(e["quote"], e["quote"])
        row = {"altname": b + q, "wsname": f"{b}/{q}", "base": e["base"], "quote": e["quote"], "status": "online"}
        row.update(e)
        result[e.get("key", row["altname"])] = {k: v for k, v in row.items() if k != "key"}
    return json.dumps({"error": [], "result": result}).encode()


def kraken_perp(*entries):
    """entries: (base, quote) or dict overrides on a PF_ linear perpetual."""
    rows = []
    for e in entries:
        if isinstance(e, tuple):
            e = {"base": e[0], "quote": e[1]}
        row = {"type": "flexible_futures", "tradeable": True, "suspended": False, "isExpired": False,
               "postOnly": False, "contractSize": 1}
        row.update(e)
        row.setdefault("symbol", f"PF_{row['base']}{row['quote']}")
        row.setdefault("pair", f"{row['base']}:{row['quote']}")
        rows.append(row)
    return json.dumps({"result": "success", "instruments": rows, "serverTime": "2026-11-23T00:00:00Z"}).encode()


def documents(ms=None, mp=None, kp=None, ka=None, kf=None, received=T0):
    def doc(raw):
        if isinstance(raw, str):
            return {"raw": None, "received_ms": received, "error": raw}
        return {"raw": raw, "received_ms": received, "error": None}
    return {
        "mexc_spot_exchange_info": doc(ms if ms is not None else mexc_spot(("BTC", "USDT"))),
        "mexc_contract_detail": doc(mp if mp is not None else mexc_perp(("BTC", "USDT"))),
        "kraken_asset_pairs": doc(kp if kp is not None else kraken_pairs(("XXBT", "USDT"))),
        "kraken_assets": doc(ka if ka is not None else kraken_assets()),
        "kraken_futures_instruments": doc(kf if kf is not None else kraken_perp(("BTC", "USDT"))),
    }
