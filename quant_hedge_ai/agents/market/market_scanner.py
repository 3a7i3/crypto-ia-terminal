from __future__ import annotations

import logging
import os
import random
import time
from datetime import datetime, timezone

from quant_hedge_ai.agents.market.ohlcv_validator import (
    is_series_fresh,
    validate_candles,
)
from quant_hedge_ai.agents.market.retry_policy import CircuitBreaker, retry_with_backoff

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

# TTL du cache en mémoire : pas de re-fetch si données < N secondes
_CACHE_TTL_SECONDS = float(os.getenv("MARKET_SCANNER_CACHE_TTL", "60"))


def _synthetic_series(symbol: str, n: int) -> list[dict]:
    """Génère une série OHLCV synthétique cohérente (random walk)."""
    ccxt_sym = _CCXT_SYMBOL_MAP.get(symbol, symbol)
    price = _SYNTHETIC_SEED.get(ccxt_sym, 1000.0) * random.uniform(0.90, 1.10)
    candles = []
    now_ms = int(time.time() * 1000)
    interval_ms = 3600 * 1000
    for i in range(n):
        ret = random.gauss(0.0001, 0.015)
        price = max(price * (1 + ret), 1e-9)
        o = price
        c = price * random.uniform(0.995, 1.005)
        h = max(o, c) * random.uniform(1.001, 1.01)
        low = min(o, c) * random.uniform(0.99, 0.999)
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
                "low": round(low, 6),
                "volume": round(v, 2),
                "source": "synthetic",
            }
        )
    return candles


class MarketScanner:
    """
    Fetche les vraies bougies OHLCV via CCXT (Binance).
    - Retry exponentiel (3 tentatives) sur échec réseau
    - Circuit breaker : après 3 échecs consécutifs, pause 60s avant de réessayer
    - Validation OHLCV : bougies corrompues filtrées automatiquement
    - Cache interne avec TTL : pas de re-fetch si données
      < MARKET_SCANNER_CACHE_TTL secondes
    - Fallback synthétique si toutes les tentatives échouent

    Variables d'environnement :
        MARKET_SCANNER_EXCHANGE    — exchange CCXT (défaut: binance)
        MARKET_SCANNER_TIMEFRAME   — timeframe OHLCV (défaut: 1h)
        MARKET_SCANNER_LIMIT       — bougies historiques (défaut: 200)
        MARKET_SCANNER_SYNTHETIC   — force le mode synthétique (défaut: false)
        MARKET_SCANNER_CACHE_TTL   — TTL cache en secondes (défaut: 60)
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

        # Cache interne : {symbol: [candle_dict, ...]}
        self._history: dict[str, list[dict]] = {}
        # Timestamp du dernier fetch réussi par symbole
        self._fetch_ts: dict[str, float] = {}

        # Circuit breaker global (partagé entre tous les symboles)
        self._circuit = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=float(os.getenv("MARKET_SCANNER_CB_RECOVERY", "60")),
            label="MarketScanner",
        )

        # Métriques de qualité des données
        self._stats: dict[str, int] = {"real": 0, "synthetic": 0, "cached": 0}

    # ------------------------------------------------------------------
    # Connexion exchange
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Fetch avec retry + circuit breaker + validation
    # ------------------------------------------------------------------

    def _fetch_series(self, symbol: str) -> list[dict] | None:
        """Fetch OHLCV avec retry exponentiel et circuit breaker."""
        if self._circuit.is_open:
            logger.debug("[MarketScanner] Circuit ouvert — skip fetch %s", symbol)
            return None

        exchange = self._get_exchange()
        if exchange is None:
            return None

        ccxt_sym = _CCXT_SYMBOL_MAP.get(symbol, symbol)

        def _do_fetch() -> list[dict]:
            ohlcvs = exchange.fetch_ohlcv(ccxt_sym, self._timeframe, limit=self._limit)
            if not ohlcvs:
                raise ValueError(f"fetch_ohlcv retourné vide pour {ccxt_sym}")
            series = [
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
                for ts, o, h, l, c, v in ohlcvs
            ]
            return series

        raw = self._circuit.call(
            lambda: retry_with_backoff(
                _do_fetch,
                max_retries=3,
                base_delay=1.0,
                max_delay=20.0,
                label=f"fetch_ohlcv {symbol}",
            )
        )

        if raw is None:
            return None

        # Validation des bougies
        clean, report = validate_candles(raw, symbol=symbol)
        if not clean:
            logger.warning(
                "[MarketScanner] %s : 0 bougies valides après validation", symbol
            )
            return None

        return clean

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def get_history(self, symbol: str) -> list[dict]:
        """Retourne la série historique en cache pour un symbole."""
        return self._history.get(symbol, [])

    def data_quality(self) -> dict:
        """Ratio de données réelles vs synthétiques depuis le démarrage."""
        total = sum(self._stats.values()) or 1
        return {
            "real": self._stats["real"],
            "synthetic": self._stats["synthetic"],
            "cached": self._stats["cached"],
            "real_ratio": round(self._stats["real"] / total, 3),
            "circuit_state": self._circuit.state,
        }

    def scan(self) -> dict:
        """
        Retourne :
          - 'candles'  : [dernière bougie par symbole]   → snapshot temps réel
          - 'history'  : {symbol: [liste complète]}       → pour le backtesting
        """
        snapshots: list[dict] = []
        history: dict[str, list[dict]] = {}
        now = time.time()

        for symbol in self.symbols:
            series = None

            # 1. Utiliser le cache si TTL non expiré
            last_fetch = self._fetch_ts.get(symbol, 0.0)
            cache_hit = (
                symbol in self._history
                and (now - last_fetch) < _CACHE_TTL_SECONDS
                and is_series_fresh(self._history[symbol])
            )

            if cache_hit:
                series = self._history[symbol]
                self._stats["cached"] += 1

            # 2. Fetch réseau (si pas forcé synthétique et circuit non ouvert)
            elif not self._force_synthetic:
                series = self._fetch_series(symbol)
                if series is not None:
                    self._fetch_ts[symbol] = now
                    self._stats["real"] += 1

            # 3. Fallback synthétique
            if series is None:
                series = _synthetic_series(symbol, self._limit)
                self._stats["synthetic"] += 1
                logger.debug("[MarketScanner] %s → données synthétiques", symbol)

            self._history[symbol] = series
            history[symbol] = series
            snapshots.append(series[-1])

        sources = {c["source"] for c in snapshots}
        quality = self.data_quality()
        logger.info(
            "[MarketScanner] %d symboles | source(s): %s | " "real=%.0f%% | circuit=%s",
            len(snapshots),
            sources,
            quality["real_ratio"] * 100,
            quality["circuit_state"],
        )
        return {"candles": snapshots, "history": history}
