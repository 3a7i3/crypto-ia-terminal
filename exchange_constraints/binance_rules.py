"""
exchange_constraints/binance_rules.py — Regles Binance USDT-M Futures.

BINANCE_FUTURES_SYMBOLS : snapshot statique (2024-Q4), 10 symboles les plus liquides.
get_symbol_info(symbol)  : acces rapide par symbole (KeyError si inconnu).
refresh_from_exchange()  : rafraichit le dict depuis l'API Binance en live.

Usage recommande :
  - Dev/backtest : utiliser BINANCE_FUTURES_SYMBOLS directement.
  - Production   : appeler refresh_from_exchange() au demarrage puis toutes les 24h.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib.error import URLError
from urllib.request import urlopen

from exchange_constraints.models import SymbolInfo
from exchange_constraints.precision_rules import compute_precision_from_step

log = logging.getLogger(__name__)

_EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
_REQUEST_TIMEOUT_S = 10


def _make(
    symbol: str,
    base: str,
    quote: str,
    step_size: float,
    min_qty: float,
    max_qty: float,
    tick_size: float,
    min_notional: float,
    percent_price_up: float = 1.05,
    percent_price_down: float = 0.95,
    leverage_max: int = 125,
    market_step_size: Optional[float] = None,
    market_min_qty: Optional[float] = None,
    market_max_qty: Optional[float] = None,
) -> SymbolInfo:
    return SymbolInfo(
        symbol=symbol,
        base_asset=base,
        quote_asset=quote,
        step_size=step_size,
        min_qty=min_qty,
        max_qty=max_qty,
        tick_size=tick_size,
        min_notional=min_notional,
        percent_price_up=percent_price_up,
        percent_price_down=percent_price_down,
        leverage_max=leverage_max,
        market_step_size=market_step_size,
        market_min_qty=market_min_qty,
        market_max_qty=market_max_qty,
        price_precision=compute_precision_from_step(tick_size),
        qty_precision=compute_precision_from_step(step_size),
        is_active=True,
    )


BINANCE_FUTURES_SYMBOLS: dict[str, SymbolInfo] = {
    "BTCUSDT": _make(
        "BTCUSDT", "BTC", "USDT", 0.001, 0.001, 1000.0, 0.1, 5.0, leverage_max=125
    ),
    "ETHUSDT": _make(
        "ETHUSDT", "ETH", "USDT", 0.001, 0.001, 10000.0, 0.01, 5.0, leverage_max=100
    ),
    "BNBUSDT": _make(
        "BNBUSDT", "BNB", "USDT", 0.01, 0.01, 10000.0, 0.01, 5.0, leverage_max=75
    ),
    "SOLUSDT": _make(
        "SOLUSDT", "SOL", "USDT", 0.1, 0.1, 100000.0, 0.001, 5.0, leverage_max=50
    ),
    "XRPUSDT": _make(
        "XRPUSDT", "XRP", "USDT", 1.0, 1.0, 10000000.0, 0.0001, 5.0, leverage_max=50
    ),
    "ADAUSDT": _make(
        "ADAUSDT", "ADA", "USDT", 1.0, 1.0, 10000000.0, 0.0001, 5.0, leverage_max=50
    ),
    "DOGEUSDT": _make(
        "DOGEUSDT", "DOGE", "USDT", 1.0, 1.0, 10000000.0, 0.00001, 5.0, leverage_max=50
    ),
    "AVAXUSDT": _make(
        "AVAXUSDT", "AVAX", "USDT", 0.1, 0.1, 100000.0, 0.01, 5.0, leverage_max=50
    ),
    "LINKUSDT": _make(
        "LINKUSDT", "LINK", "USDT", 0.01, 0.01, 1000000.0, 0.001, 5.0, leverage_max=50
    ),
    "MATICUSDT": _make(
        "MATICUSDT", "MATIC", "USDT", 1.0, 1.0, 10000000.0, 0.0001, 5.0, leverage_max=50
    ),
}


def get_symbol_info(symbol: str) -> SymbolInfo:
    """
    Retourne le SymbolInfo pour un symbole.
    Leve KeyError si le symbole est inconnu — pas de fallback silencieux.
    """
    sym = symbol.upper()
    if sym not in BINANCE_FUTURES_SYMBOLS:
        raise KeyError(
            f"Symbol '{sym}' not found. "
            f"Available: {sorted(BINANCE_FUTURES_SYMBOLS.keys())}"
        )
    return BINANCE_FUTURES_SYMBOLS[sym]


# ---------------------------------------------------------------------------
# Live refresh depuis l'API Binance
# ---------------------------------------------------------------------------


def _parse_filter(filters: list[dict], filter_type: str) -> dict:
    return next((f for f in filters if f["type"] == filter_type), {})


def _symbol_from_api(s: dict[str, Any]) -> Optional[SymbolInfo]:
    """Construit un SymbolInfo depuis un element de l'API exchangeInfo."""
    try:
        symbol = s["symbol"]
        base = s["baseAsset"]
        quote = s["quoteAsset"]
        filters = s.get("filters", [])

        lot = _parse_filter(filters, "LOT_SIZE")
        price_f = _parse_filter(filters, "PRICE_FILTER")
        notional = _parse_filter(filters, "MIN_NOTIONAL")
        pct_price = _parse_filter(filters, "PERCENT_PRICE")
        mkt_lot = _parse_filter(filters, "MARKET_LOT_SIZE")

        step_size = float(lot.get("stepSize", 0.001))
        tick_size = float(price_f.get("tickSize", 0.01))

        return SymbolInfo(
            symbol=symbol,
            base_asset=base,
            quote_asset=quote,
            step_size=step_size,
            min_qty=float(lot.get("minQty", step_size)),
            max_qty=float(lot.get("maxQty", 1000.0)),
            tick_size=tick_size,
            min_notional=float(notional.get("notional", 5.0)),
            percent_price_up=float(pct_price.get("multiplierUp", 1.05)),
            percent_price_down=float(pct_price.get("multiplierDown", 0.95)),
            leverage_max=125,
            market_step_size=float(mkt_lot["stepSize"]) if mkt_lot else None,
            market_min_qty=float(mkt_lot["minQty"]) if mkt_lot else None,
            market_max_qty=float(mkt_lot["maxQty"]) if mkt_lot else None,
            price_precision=compute_precision_from_step(tick_size),
            qty_precision=compute_precision_from_step(step_size),
            is_active=s.get("status", "TRADING") == "TRADING",
        )
    except (KeyError, ValueError, TypeError) as exc:
        log.warning("Failed to parse symbol %s: %s", s.get("symbol", "?"), exc)
        return None


def refresh_from_exchange(
    symbols: Optional[list[str]] = None,
    timeout_s: int = _REQUEST_TIMEOUT_S,
) -> dict[str, SymbolInfo]:
    """
    Rafraichit BINANCE_FUTURES_SYMBOLS depuis l'API Binance live.

    symbols : liste de symboles a rafraichir (None = tous les USDT perps actifs).
    Retourne le dict mis a jour. Leve RuntimeError si l'API est injoignable.

    En production, appeler au demarrage et toutes les 24h.
    """
    global BINANCE_FUTURES_SYMBOLS

    target = {s.upper() for s in symbols} if symbols else None

    try:
        with urlopen(_EXCHANGE_INFO_URL, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode())
    except URLError as exc:
        raise RuntimeError(f"Cannot reach Binance API: {exc}") from exc

    updated: dict[str, SymbolInfo] = {}
    for s in data.get("symbols", []):
        sym = s.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        if s.get("contractType") not in ("PERPETUAL", None):
            continue
        if target and sym not in target:
            continue
        info = _symbol_from_api(s)
        if info is not None:
            updated[sym] = info

    if not updated:
        raise RuntimeError("refresh_from_exchange: no symbols parsed from API response")

    BINANCE_FUTURES_SYMBOLS.update(updated)
    log.info(
        "exchange_constraints: refreshed %d symbols from Binance API", len(updated)
    )
    return BINANCE_FUTURES_SYMBOLS
