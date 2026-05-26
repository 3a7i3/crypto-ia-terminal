"""
market_data/connectors/base.py — Interface abstraite commune pour tous les connecteurs.

Chaque connecteur doit implementer :
  fetch_trades(symbol, limit)     -> list[NormalizedTrade]     REST snapshot
  fetch_orderbook(symbol, depth)  -> NormalizedOrderBook       REST snapshot
  fetch_candles(symbol, tf, limit)-> list[NormalizedCandle]    REST snapshot
  stream_trades(symbol)           -> AsyncGenerator             WebSocket live
  stream_orderbook(symbol)        -> AsyncGenerator             WebSocket live

Les methodes fetch_* sont synchrones (utilisables sans asyncio).
Les methodes stream_* sont des generateurs asynchrones.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional

from market_data.models import (
    MarketEvent,
    NormalizedCandle,
    NormalizedOrderBook,
    NormalizedTrade,
)
from observability.json_logger import get_logger

_log = get_logger("market_data.connectors.base")


class BaseConnector(ABC):
    """
    Interface commune pour Binance, Hyperliquid, MEXC.

    exchange_name : identifiant (ex: "binance")
    base_url      : URL de base de l'API REST
    ws_url        : URL de base WebSocket
    """

    exchange_name: str = "unknown"
    base_url: str = ""
    ws_url: str = ""

    def __init__(self, timeout_s: int = 10) -> None:
        self.timeout_s = timeout_s
        self._log = get_logger(f"market_data.{self.exchange_name}")

    # ------------------------------------------------------------------
    # REST (synchrone)
    # ------------------------------------------------------------------

    @abstractmethod
    def fetch_trades(self, symbol: str, limit: int = 100) -> list[NormalizedTrade]:
        """Retourne les derniers trades pour un symbole (REST snapshot)."""

    @abstractmethod
    def fetch_orderbook(self, symbol: str, depth: int = 20) -> NormalizedOrderBook:
        """Retourne le carnet d'ordres courant (REST snapshot)."""

    @abstractmethod
    def fetch_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 100,
        start_ms: Optional[int] = None,
        end_ms: Optional[int] = None,
    ) -> list[NormalizedCandle]:
        """Retourne les chandelles OHLCV (REST snapshot ou historique)."""

    # ------------------------------------------------------------------
    # WebSocket (asynchrone)
    # ------------------------------------------------------------------

    @abstractmethod
    async def stream_trades(self, symbol: str) -> AsyncGenerator[NormalizedTrade, None]:
        """Generateur asynchrone de trades en temps reel."""
        # impl: yield NormalizedTrade(...)

    @abstractmethod
    async def stream_orderbook(
        self, symbol: str, depth: int = 20
    ) -> AsyncGenerator[NormalizedOrderBook, None]:
        """Generateur asynchrone d'updates du book."""

    # ------------------------------------------------------------------
    # Utilitaires communs
    # ------------------------------------------------------------------

    def normalize_symbol(self, raw_symbol: str) -> str:
        """
        Normalise un symbole vers le format interne (ex: "BTC/USDT" -> "BTCUSDT").
        Peut etre surcharge par chaque connecteur si besoin.
        """
        return raw_symbol.replace("/", "").upper()

    def _get_json(self, url: str, params: Optional[dict] = None) -> dict | list:
        """Appel REST synchrone avec urllib (pas de dependances externes)."""
        import json
        from urllib.error import HTTPError, URLError
        from urllib.parse import urlencode
        from urllib.request import Request, urlopen

        full_url = url
        if params:
            full_url = f"{url}?{urlencode(params)}"

        req = Request(full_url, headers={"Accept": "application/json"})
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as exc:
            self._log.error(
                "HTTP %d on %s: %s", exc.code, full_url, exc.read().decode()[:200]
            )
            raise
        except URLError as exc:
            self._log.error("URLError on %s: %s", full_url, exc)
            raise
