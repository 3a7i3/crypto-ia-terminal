"""
exchange_constraints/binance_rules.py — Regles futures generiques (MEXC/spot perps).

FUTURES_SYMBOLS : snapshot statique des symboles supportes.
get_symbol_info(symbol)  : acces rapide par symbole (KeyError si inconnu).
refresh_from_exchange()  : no-op (MEXC mode — pas de refresh Binance fapi).

Alias de compatibilite : FUTURES_SYMBOLS = FUTURES_SYMBOLS.
"""

from __future__ import annotations

from typing import Optional

from exchange_constraints.models import SymbolInfo
from exchange_constraints.precision_rules import compute_precision_from_step
from observability.json_logger import get_logger

_log = get_logger("exchange_constraints.futures_rules")
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


FUTURES_SYMBOLS: dict[str, SymbolInfo] = {
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
    if sym not in FUTURES_SYMBOLS:
        raise KeyError(
            f"Symbol '{sym}' not found. " f"Available: {sorted(FUTURES_SYMBOLS.keys())}"
        )
    return FUTURES_SYMBOLS[sym]


# ---------------------------------------------------------------------------
# Alias de compatibilite ascendante
# ---------------------------------------------------------------------------

BINANCE_FUTURES_SYMBOLS = FUTURES_SYMBOLS


def refresh_from_exchange(
    symbols: Optional[list[str]] = None,
    timeout_s: int = _REQUEST_TIMEOUT_S,
) -> dict[str, SymbolInfo]:
    """No-op en mode MEXC — retourne le snapshot statique sans appel reseau."""
    _log.debug(
        "exchange_constraints: refresh desactive (mode MEXC — snapshot statique)"
    )
    return FUTURES_SYMBOLS
