"""
multi_exchange_feed.py — Collecte de données live depuis plusieurs exchanges.

Endpoints publics uniquement — aucune clé API requise.
Exchanges : Binance, Bybit, OKX, MEXC, Hyperliquid

Sortie : databases/multi_exchange_snapshot.json (lu par les dashboards)

Usage:
    python multi_exchange_feed.py
    FEED_INTERVAL=60 python multi_exchange_feed.py
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

INTERVAL = int(os.getenv("FEED_INTERVAL", "30"))
BASE = Path(__file__).parent
OUT = BASE / "databases" / "multi_exchange_snapshot.json"
TIMEOUT = 8

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [FEED] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Fetchers par exchange ──────────────────────────────────────────────────────


def fetch_binance(symbols: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for sym in symbols:
        try:
            r = requests.get(
                "https://api.binance.com/api/v3/ticker/24hr",
                params={"symbol": sym},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            d = r.json()
            out[sym] = {
                "price": float(d["lastPrice"]),
                "change_24h_pct": float(d["priceChangePercent"]),
                "volume_24h": float(d["quoteVolume"]),
                "high_24h": float(d["highPrice"]),
                "low_24h": float(d["lowPrice"]),
                "bid": float(d["bidPrice"]),
                "ask": float(d["askPrice"]),
            }
        except Exception as e:
            log.debug(f"Binance {sym}: {e}")
    return out


def fetch_bybit(symbols: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for sym in symbols:
        try:
            r = requests.get(
                "https://api.bybit.com/v5/market/tickers",
                params={"category": "spot", "symbol": sym},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            items = r.json().get("result", {}).get("list", [])
            if not items:
                continue
            d = items[0]
            out[sym] = {
                "price": float(d["lastPrice"]),
                "change_24h_pct": float(d.get("price24hPcnt", 0)) * 100,
                "volume_24h": float(d.get("turnover24h", 0)),
                "high_24h": float(d.get("highPrice24h", 0)),
                "low_24h": float(d.get("lowPrice24h", 0)),
                "bid": float(d.get("bid1Price", 0)),
                "ask": float(d.get("ask1Price", 0)),
            }
        except Exception as e:
            log.debug(f"Bybit {sym}: {e}")
    return out


def fetch_okx(symbols: list[str]) -> dict[str, dict]:
    _MAP = {
        "BTCUSDT": "BTC-USDT",
        "ETHUSDT": "ETH-USDT",
        "SOLUSDT": "SOL-USDT",
        "DOGEUSDT": "DOGE-USDT",
    }
    out: dict[str, dict] = {}
    for sym in symbols:
        inst = _MAP.get(sym)
        if not inst:
            continue
        try:
            r = requests.get(
                "https://www.okx.com/api/v5/market/ticker",
                params={"instId": inst},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            items = r.json().get("data", [])
            if not items:
                continue
            d = items[0]
            out[sym] = {
                "price": float(d["last"]),
                "change_24h_pct": float(d.get("change24h", 0)) * 100,
                "volume_24h": float(d.get("volCcy24h", 0)),
                "high_24h": float(d.get("high24h", 0)),
                "low_24h": float(d.get("low24h", 0)),
                "bid": float(d.get("bidPx", 0)),
                "ask": float(d.get("askPx", 0)),
            }
        except Exception as e:
            log.debug(f"OKX {sym}: {e}")
    return out


def fetch_mexc(symbols: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for sym in symbols:
        try:
            r = requests.get(
                "https://api.mexc.com/api/v3/ticker/24hr",
                params={"symbol": sym},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            d = r.json()
            out[sym] = {
                "price": float(d["lastPrice"]),
                "change_24h_pct": float(d["priceChangePercent"]),
                "volume_24h": float(d["quoteVolume"]),
                "high_24h": float(d["highPrice"]),
                "low_24h": float(d["lowPrice"]),
                "bid": float(d.get("bidPrice", 0)),
                "ask": float(d.get("askPrice", 0)),
            }
        except Exception as e:
            log.debug(f"MEXC {sym}: {e}")
    return out


def fetch_hyperliquid(symbols: list[str]) -> dict[str, dict]:
    _BASE = {
        "BTCUSDT": "BTC",
        "ETHUSDT": "ETH",
        "SOLUSDT": "SOL",
        "DOGEUSDT": "DOGE",
    }
    out: dict[str, dict] = {}
    try:
        r = requests.post(
            "https://api.hyperliquid.xyz/info",
            json={"type": "allMids"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        mids = r.json()
        for sym in symbols:
            base = _BASE.get(sym)
            if base and base in mids:
                price = float(mids[base])
                out[sym] = {
                    "price": price,
                    "change_24h_pct": None,
                    "volume_24h": None,
                    "high_24h": None,
                    "low_24h": None,
                    "bid": None,
                    "ask": None,
                }
    except Exception as e:
        log.debug(f"Hyperliquid: {e}")
    return out


# ── Collecte complète ──────────────────────────────────────────────────────────

FETCHERS = [
    ("binance", fetch_binance),
    ("bybit", fetch_bybit),
    ("okx", fetch_okx),
    ("mexc", fetch_mexc),
    ("hyperliquid", fetch_hyperliquid),
]


def collect() -> dict:
    snapshot: dict[str, dict] = {sym: {} for sym in SYMBOLS}
    ok_exchanges = 0

    for exchange_name, fetcher in FETCHERS:
        try:
            data = fetcher(SYMBOLS)
            if data:
                ok_exchanges += 1
            for sym, vals in data.items():
                snapshot[sym][exchange_name] = vals
        except Exception as e:
            log.warning(f"{exchange_name} fetch error: {e}")

    # Calcul spread inter-exchange pour chaque symbole
    spreads: dict[str, dict] = {}
    for sym, ex_data in snapshot.items():
        prices = {ex: d["price"] for ex, d in ex_data.items() if d.get("price")}
        if len(prices) >= 2:
            vals = list(prices.values())
            spread_pct = (max(vals) - min(vals)) / min(vals) * 100
            spreads[sym] = {
                "min_price": min(vals),
                "max_price": max(vals),
                "spread_pct": round(spread_pct, 4),
                "cheapest": min(prices, key=prices.get),
                "most_expensive": max(prices, key=prices.get),
            }

    return {
        "ts": time.time(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "exchanges_ok": ok_exchanges,
        "total_exchanges": len(FETCHERS),
        "symbols": snapshot,
        "spreads": spreads,
    }


def run() -> None:
    log.info(
        f"Multi-exchange feed démarré — {len(FETCHERS)} exchanges, {INTERVAL}s interval"
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    while True:
        t0 = time.time()
        try:
            data = collect()
            OUT.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            elapsed = round(time.time() - t0, 1)
            log.info(
                f"{data['exchanges_ok']}/{data['total_exchanges']} exchanges | "
                f"{len(data['spreads'])} spreads | {elapsed}s"
            )
        except Exception as e:
            log.error(f"Collect error: {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    run()
