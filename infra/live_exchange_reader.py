"""
Phase 1 — Connexion exchange réel en lecture seule.

Expose uniquement les méthodes de lecture (OHLCV, tickers, orderbook, balance).
Aucune méthode d'ordre n'est disponible — la sécurité est structurelle.

Variables d'env :
    LIVE_READER_EXCHANGE   : identifiant ccxt (défaut: binance)
    LIVE_READER_API_KEY    : optionnel — pour fetch_balance() sur compte réel
    LIVE_READER_API_SECRET : optionnel

Usage :
    reader = LiveExchangeReader()
    ticker = reader.fetch_ticker("BTC/USDT")
    ohlcv  = reader.fetch_ohlcv("SOL/USDT", "1h", limit=100)
    ob     = reader.fetch_order_book("ETH/USDT", depth=20)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

_LOG_PREFIX = "[LiveExchangeReader]"


@dataclass
class Ticker:
    symbol: str
    bid: float
    ask: float
    last: float
    volume_24h: float
    spread_pct: float
    timestamp: float = field(default_factory=time.time)

    @classmethod
    def from_ccxt(cls, symbol: str, raw: dict) -> "Ticker":
        bid = float(raw.get("bid") or 0.0)
        ask = float(raw.get("ask") or 0.0)
        last = float(raw.get("last") or raw.get("close") or 0.0)
        vol = float(raw.get("quoteVolume") or raw.get("baseVolume") or 0.0)
        spread = (ask - bid) / ask * 100.0 if ask > 0 else 0.0
        return cls(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=last,
            volume_24h=vol,
            spread_pct=round(spread, 4),
        )


@dataclass
class OrderBook:
    symbol: str
    bids: list  # [[price, qty], ...]
    asks: list
    timestamp: float = field(default_factory=time.time)

    @property
    def mid_price(self) -> float:
        if not self.bids or not self.asks:
            return 0.0
        return (self.bids[0][0] + self.asks[0][0]) / 2.0

    @property
    def spread_pct(self) -> float:
        if not self.bids or not self.asks:
            return 0.0
        bid, ask = self.bids[0][0], self.asks[0][0]
        return (ask - bid) / ask * 100.0 if ask > 0 else 0.0

    @property
    def depth_bid_usd(self) -> float:
        return sum(p * q for p, q in self.bids[:10])

    @property
    def depth_ask_usd(self) -> float:
        return sum(p * q for p, q in self.asks[:10])


class LiveExchangeReader:
    """
    Accès read-only à un exchange réel via ccxt.
    Les données publiques (OHLCV, tickers, orderbooks) ne nécessitent aucune clé API.
    fetch_balance() nécessite des clés — ne jamais activer permission withdrawal.
    """

    def __init__(
        self,
        exchange_id: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        self._exchange_id = (
            exchange_id or os.getenv("LIVE_READER_EXCHANGE", "binance")
        ).lower()
        self._api_key = api_key or os.getenv("LIVE_READER_API_KEY", "")
        self._api_secret = api_secret or os.getenv("LIVE_READER_API_SECRET", "")
        self._exchange = self._build_exchange()
        self._markets_loaded = False

    # ── Initialisation ────────────────────────────────────────────────────────

    def _build_exchange(self):
        try:
            import ccxt

            config: dict = {"enableRateLimit": True}
            if self._api_key:
                config["apiKey"] = self._api_key
            if self._api_secret:
                config["secret"] = self._api_secret

            cls = getattr(ccxt, self._exchange_id, None)
            if cls is None:
                raise ValueError(f"Exchange inconnu : {self._exchange_id}")
            return cls(config)
        except ImportError as exc:
            raise ImportError("ccxt requis : pip install ccxt") from exc

    def _ensure_markets(self) -> None:
        if not self._markets_loaded:
            self._exchange.load_markets()
            self._markets_loaded = True

    # ── API publique — lecture seule ──────────────────────────────────────────

    def fetch_ticker(self, symbol: str) -> Ticker:
        self._ensure_markets()
        raw = self._exchange.fetch_ticker(symbol)
        return Ticker.from_ccxt(symbol, raw)

    def fetch_tickers(self, symbols: list[str]) -> dict[str, Ticker]:
        self._ensure_markets()
        raw_all = self._exchange.fetch_tickers(symbols)
        return {
            sym: Ticker.from_ccxt(sym, raw)
            for sym, raw in raw_all.items()
            if sym in symbols
        }

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
        since: Optional[int] = None,
    ) -> list[dict]:
        self._ensure_markets()
        raw = self._exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
        return [
            {
                "ts": int(c[0]),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
            }
            for c in raw
        ]

    def fetch_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        self._ensure_markets()
        raw = self._exchange.fetch_order_book(symbol, limit=depth)
        return OrderBook(
            symbol=symbol,
            bids=raw.get("bids", []),
            asks=raw.get("asks", []),
        )

    def fetch_balance(self) -> dict:
        """Requiert des clés API. Ne pas activer permission withdrawal."""
        if not self._api_key:
            return {}
        return self._exchange.fetch_balance()

    # ── Diagnostic ────────────────────────────────────────────────────────────

    def ping(self) -> dict:
        """Vérifie la connectivité. Retourne latence et exchange actif."""
        t0 = time.perf_counter()
        try:
            self._exchange.fetch_time()
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            return {
                "exchange": self._exchange_id,
                "status": "OK",
                "latency_ms": latency_ms,
                "authenticated": bool(self._api_key),
            }
        except Exception as exc:
            return {
                "exchange": self._exchange_id,
                "status": "ERROR",
                "error": str(exc),
                "authenticated": False,
            }

    @property
    def exchange_id(self) -> str:
        return self._exchange_id
