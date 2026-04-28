from __future__ import annotations

import logging
import os
import random
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_CCXT_SYMBOL_MAP: dict[str, str] = {
    "BTCUSDT": "BTC/USDT",
    "ETHUSDT": "ETH/USDT",
    "SOLUSDT": "SOL/USDT",
    "BNBUSDT": "BNB/USDT",
    "ARBUSDT": "ARB/USDT",
    "DOGEUSDT": "DOGE/USDT",
    "BTC/USDT": "BTC/USDT",
    "ETH/USDT": "ETH/USDT",
    "SOL/USDT": "SOL/USDT",
    "BNB/USDT": "BNB/USDT",
    "ARB/USDT": "ARB/USDT",
}

_SYNTHETIC_SEED: dict[str, float] = {
    "BTC/USDT": 65_000,
    "ETH/USDT": 3_100,
    "SOL/USDT": 170,
    "BNB/USDT": 580,
    "ARB/USDT": 1.2,
    "DOGE/USDT": 0.15,
}


def _synthetic_series(symbol: str, n: int) -> list[dict]:
    """Génère une série OHLCV synthétique cohérente (random walk)."""
    ccxt_sym = _CCXT_SYMBOL_MAP.get(symbol, symbol)
    price = _SYNTHETIC_SEED.get(ccxt_sym, 1000.0) * random.uniform(0.90, 1.10)
    candles = []
    now_ms = int(time.time() * 1000)
    interval_ms = 3600 * 1000  # 1h par défaut
    for i in range(n):
        ret = random.gauss(0.0001, 0.015)
        price = max(price * (1 + ret), 1e-9)
        o = price
        c = price * random.uniform(0.995, 1.005)
        h = max(o, c) * random.uniform(1.001, 1.01)
        l = min(o, c) * random.uniform(0.99, 0.999)
        v = random.uniform(1_000, 500_000)
        candles.append(
            {
                "symbol": symbol,
                "timestamp": datetime.fromtimestamp(
                    (now_ms - (n - i) * interval_ms) / 1000, tz=timezone.utc
                ).isoformat(),
                "open": round(o, 6),
                "close": round(c, 6),
                "high": round(h, 6),
                "low": round(l, 6),
                "volume": round(v, 2),
                "source": "synthetic",
            }
        )
    return candles


class MarketScanner:
    """
    Fetche les vraies bougies OHLCV via CCXT (Binance public, sans clé API).
    - scan()        → snapshot 1 bougie par symbole (temps réel)
    - get_history() → série complète pour le backtesting

    Variables d'environnement :
        MARKET_SCANNER_EXCHANGE   — exchange CCXT (défaut: binance)
        MARKET_SCANNER_TIMEFRAME  — timeframe OHLCV (défaut: 1h)
        MARKET_SCANNER_LIMIT      — bougies historiques (défaut: 200)
        MARKET_SCANNER_SYNTHETIC  — force le mode synthétique (défaut: false)
    """

    def __init__(
        self,
        symbols: list[str] | None = None,
        exchange_id: str | None = None,
        timeframe: str | None = None,
        limit: int | None = None,
    ) -> None:
        self.symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
        self._exchange_id = exchange_id or os.getenv(
            "MARKET_SCANNER_EXCHANGE", "binance"
        )
        self._timeframe = timeframe or os.getenv("MARKET_SCANNER_TIMEFRAME", "1h")
        self._limit = limit or int(os.getenv("MARKET_SCANNER_LIMIT", "200"))
        self._force_synthetic = (
            os.getenv("MARKET_SCANNER_SYNTHETIC", "false").lower() == "true"
        )
        self._exchange = None
        self._last_error_ts: float = 0.0
        self._error_cooldown: float = 30.0
        # Cache interne : {symbol: [candle_dict, ...]} (200 bougies)
        self._history: dict[str, list[dict]] = {}

    def _get_exchange(self):
        if self._exchange is None:
            try:
                import ccxt

                config: dict = {"enableRateLimit": True}
                api_key = os.getenv("BINANCE_API_KEY")
                api_secret = os.getenv("BINANCE_API_SECRET")
                if api_key and api_secret:
                    config["apiKey"] = api_key
                    config["secret"] = api_secret
                    if os.getenv("BINANCE_TESTNET", "false").lower() == "true":
                        config["options"] = {"defaultType": "spot"}
                        config["urls"] = {
                            "api": {
                                "public": "https://testnet.binance.vision/api",
                                "private": "https://testnet.binance.vision/api",
                            }
                        }
                    logger.info("[MarketScanner] Clés API Binance chargées")
                self._exchange = getattr(ccxt, self._exchange_id)(config)
            except Exception as exc:
                logger.warning(
                    "Impossible d'initialiser CCXT (%s): %s", self._exchange_id, exc
                )
        return self._exchange

    def _fetch_series(self, symbol: str) -> list[dict] | None:
        """Fetche la série historique complète ou None si échec."""
        exchange = self._get_exchange()
        if exchange is None:
            return None
        ccxt_sym = _CCXT_SYMBOL_MAP.get(symbol, symbol)
        try:
            ohlcvs = exchange.fetch_ohlcv(ccxt_sym, self._timeframe, limit=self._limit)
            if not ohlcvs:
                return None
            series = []
            for ts, o, h, l, c, v in ohlcvs:
                series.append(
                    {
                        "symbol": symbol,
                        "timestamp": datetime.fromtimestamp(
                            ts / 1000, tz=timezone.utc
                        ).isoformat(),
                        "open": float(o),
                        "close": float(c),
                        "high": float(h),
                        "low": float(l),
                        "volume": float(v),
                        "source": "ccxt_live",
                    }
                )
            return series
        except Exception as exc:
            logger.warning(
                "[MarketScanner] Erreur CCXT %s: %s — bascule synthetic", symbol, exc
            )
            self._last_error_ts = time.time()
            return None

    def get_history(self, symbol: str) -> list[dict]:
        """Retourne la série historique (200 bougies) pour un symbole."""
        return self._history.get(symbol, [])

    def scan(self) -> dict:
        """
        Fetche la série complète, met à jour le cache interne, et retourne :
          - 'candles'  : [dernière bougie par symbole]   → snapshot temps réel
          - 'history'  : {symbol: [liste complète]}       → pour le backtesting
        """
        snapshots: list[dict] = []
        history: dict[str, list[dict]] = {}

        use_synthetic = self._force_synthetic or (
            time.time() - self._last_error_ts < self._error_cooldown
        )

        for symbol in self.symbols:
            series = None
            if not use_synthetic:
                series = self._fetch_series(symbol)
            if series is None:
                series = _synthetic_series(symbol, self._limit)

            self._history[symbol] = series
            history[symbol] = series
            snapshots.append(series[-1])  # dernière bougie = snapshot courant

        sources = {c["source"] for c in snapshots}
        logger.info(
            "[MarketScanner] %d symboles | %d bougies/sym | source(s): %s",
            len(snapshots),
            self._limit,
            sources,
        )
        return {"candles": snapshots, "history": history}
