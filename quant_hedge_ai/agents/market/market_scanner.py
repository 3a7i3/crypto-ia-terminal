from __future__ import annotations

import logging
import os
import random
import threading
import time
from datetime import datetime, timezone
from typing import Any

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
# Profiling fin du coût CCXT activé par MARKET_SCANNER_PROFILE=true
_PROFILE_ENABLED = os.getenv("MARKET_SCANNER_PROFILE", "false").lower() == "true"


def _timeframe_to_seconds(timeframe: str) -> float:
    unit = timeframe[-1].lower()
    try:
        value = int(timeframe[:-1])
    except ValueError:
        return 3600.0

    factors = {
        "m": 60.0,
        "h": 3600.0,
        "d": 86400.0,
    }
    return value * factors.get(unit, 3600.0)


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

    _exchange_pool: dict[tuple[str, bool], Any] = {}
    _exchange_pool_lock = threading.Lock()
    _exchange_call_locks: dict[tuple[str, bool], threading.Lock] = {}
    _exchange_markets_ready: dict[tuple[str, bool], threading.Event] = {}
    _exchange_market_preload_started: set[tuple[str, bool]] = set()
    # Session aging — monotonic timestamp of creation and consecutive transport-error counter.
    # _exchange_generation is bumped on invalidation so stale self._exchange refs self-heal.
    _exchange_created_at: dict[tuple[str, bool], float] = {}
    _exchange_transport_errors: dict[tuple[str, bool], int] = {}
    _exchange_generation: dict[tuple[str, bool], int] = {}

    def __init__(
        self,
        symbols: list[str] | None = None,
        exchange_id: str | None = None,
        timeframe: str | None = None,
        limit: int | None = None,
        max_retries: int | None = None,
        retry_base_delay: float | None = None,
        retry_max_delay: float | None = None,
    ) -> None:
        self.symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
        self._exchange_id = exchange_id or os.getenv(
            "MARKET_SCANNER_EXCHANGE", "binance"
        )
        self._timeframe = timeframe or os.getenv("MARKET_SCANNER_TIMEFRAME", "1h")
        self._limit = limit or int(os.getenv("MARKET_SCANNER_LIMIT", "200"))
        self._max_retries = max_retries if max_retries is not None else int(os.getenv("MARKET_SCANNER_MAX_RETRIES", "3"))
        self._retry_base_delay = (
            retry_base_delay if retry_base_delay is not None else float(os.getenv("MARKET_SCANNER_RETRY_BASE_DELAY", "1.0"))
        )
        self._retry_max_delay = (
            retry_max_delay if retry_max_delay is not None else float(os.getenv("MARKET_SCANNER_RETRY_MAX_DELAY", "20.0"))
        )
        self._timeframe_seconds = _timeframe_to_seconds(self._timeframe)
        self._freshness_seconds = float(
            os.getenv("MARKET_SCANNER_FRESHNESS_SECONDS", str(max(self._timeframe_seconds, 3600.0)))
        )
        self._allow_stale_cache = (
            os.getenv("MARKET_SCANNER_ALLOW_STALE_CACHE", "true").lower() == "true"
        )
        self._trace_timings = (
            os.getenv("MARKET_SCANNER_TRACE_TIMINGS", "false").lower() == "true"
        )
        self._profile = (
            os.getenv("MARKET_SCANNER_PROFILE", "false").lower() == "true"
        )
        # Accumulateur de profiling (réinitialisé à chaque scan via reset_profile())
        self._profile_data: dict[str, list[float]] = {
            "exchange_pool_lock_wait_ms": [],
            "exchange_create_ms": [],
            "exchange_call_lock_wait_ms": [],
            "fetch_ohlcv_http_ms": [],
            "retry_count": [],
            "parse_validate_ms": [],
        }
        self._force_synthetic = (
            os.getenv("MARKET_SCANNER_SYNTHETIC", "false").lower() == "true"
        )
        self._exchange = None
        # Generation tag — if the class-level session is replaced, self._exchange becomes stale;
        # _exchange_gen mismatch triggers a re-lookup without holding any lock.
        self._exchange_gen: int = -1

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

    def _exchange_key(self) -> tuple[str, bool]:
        return (
            self._exchange_id,
            os.getenv("BINANCE_TESTNET", "false").lower() == "true",
        )

    @classmethod
    def _get_exchange_call_lock(cls, key: tuple[str, bool]) -> threading.Lock:
        with cls._exchange_pool_lock:
            lock = cls._exchange_call_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                cls._exchange_call_locks[key] = lock
            return lock

    @classmethod
    def _get_exchange_markets_ready(cls, key: tuple[str, bool]) -> threading.Event:
        with cls._exchange_pool_lock:
            ready = cls._exchange_markets_ready.get(key)
            if ready is None:
                ready = threading.Event()
                cls._exchange_markets_ready[key] = ready
            return ready

    # ------------------------------------------------------------------
    # Session aging — TTL, transport-error invalidation, clean recreation
    # ------------------------------------------------------------------

    @classmethod
    def _invalidate_exchange_session(
        cls,
        key: tuple[str, bool],
        *,
        reason: str = "unknown",
    ) -> None:
        """
        Close and evict the shared exchange session for *key*, then bump
        _exchange_generation so every cached self._exchange reference
        self-heals on next _get_exchange() call (no thread / event leaks).
        """
        with cls._exchange_pool_lock:
            old = cls._exchange_pool.pop(key, None)
            if old is not None:
                try:
                    old.close()
                except Exception:
                    pass
            cls._exchange_created_at.pop(key, None)
            cls._exchange_transport_errors[key] = 0
            cls._exchange_generation[key] = cls._exchange_generation.get(key, 0) + 1
            # Replace the Event so any new waiters block on a fresh one;
            # the old event is garbage-collected — no lingering waiters because
            # _ensure_markets_loaded holds exchange_call_lock while it waits,
            # and invalidation is called only after that lock is released.
            cls._exchange_markets_ready.pop(key, None)
            cls._exchange_market_preload_started.discard(key)
        logger.info(
            "[MarketScanner] Session invalidée (raison=%s key=%s) — recréation au prochain fetch",
            reason, key,
        )

    @staticmethod
    def _is_transport_error(exc: Exception) -> bool:
        """Return True for CCXT transport-layer errors (network, timeout, etc.)."""
        transport_names = {
            "NetworkError", "RequestTimeout", "DDoSProtection",
            "ExchangeNotAvailable", "ExchangeError",
        }
        return any(cls.__name__ in transport_names for cls in type(exc).__mro__)

    def _check_session_ttl(self, key: tuple[str, bool]) -> None:
        """Invalidate the shared session if it has exceeded MARKET_SCANNER_SESSION_TTL_S."""
        ttl_s = float(os.getenv("MARKET_SCANNER_SESSION_TTL_S", str(4 * 3600)))
        created_at = self.__class__._exchange_created_at.get(key)
        if created_at is not None and time.monotonic() - created_at > ttl_s:
            logger.info(
                "[MarketScanner] Session TTL dépassé (%.1fh) — invalidation",
                ttl_s / 3600,
            )
            self.__class__._invalidate_exchange_session(key, reason="ttl")
            self._exchange = None
            self._exchange_gen = -1

    def _ensure_markets_loaded(
        self,
        exchange: Any,
        key: tuple[str, bool],
        *,
        source: str,
    ) -> None:
        markets_ready = self._get_exchange_markets_ready(key)
        if markets_ready.is_set():
            return

        started_at = time.perf_counter()
        exchange_lock = self._get_exchange_call_lock(key)
        with exchange_lock:
            if markets_ready.is_set():
                return
            exchange.load_markets()
            markets_ready.set()

        if self._trace_timings:
            logger.info(
                "[MarketScannerTiming] %s/%s load_markets %s en %.3fs",
                self._exchange_id,
                self._timeframe,
                source,
                time.perf_counter() - started_at,
            )

    def _start_markets_preload(self, exchange: Any, key: tuple[str, bool]) -> None:
        markets_ready = self._get_exchange_markets_ready(key)
        if markets_ready.is_set():
            return

        with self._exchange_pool_lock:
            if key in self._exchange_market_preload_started:
                return
            self._exchange_market_preload_started.add(key)

        def _preload_markets_bg() -> None:
            try:
                self._ensure_markets_loaded(exchange, key, source="background")
                logger.info("[MarketScanner] load_markets() precharge en background")
            except Exception as exc:
                with self._exchange_pool_lock:
                    self._exchange_market_preload_started.discard(key)
                logger.debug("[MarketScanner] load_markets() background: %s", exc)

        threading.Thread(
            target=_preload_markets_bg,
            daemon=True,
            name="MktScannerPreload",
        ).start()

    # ------------------------------------------------------------------
    # Connexion exchange
    # ------------------------------------------------------------------

    def _get_exchange(self):
        # ── Stale-reference check ─────────────────────────────────────────────
        # If the class-level session was invalidated (TTL or transport errors),
        # _exchange_generation was bumped; drop our cached reference so we
        # re-enter the pool-lookup branch below.
        if self._exchange is not None:
            key = self._exchange_key()
            if self._exchange_gen != self.__class__._exchange_generation.get(key, 0):
                self._exchange = None
                self._exchange_gen = -1

        if self._exchange is None:
            key = self._exchange_key()
            _t_pool_lock = time.perf_counter()
            started_at: float | None = None
            created_exchange = False
            try:
                with self._exchange_pool_lock:
                    _pool_lock_wait = (time.perf_counter() - _t_pool_lock) * 1000
                    if self._profile:
                        self._profile_data["exchange_pool_lock_wait_ms"].append(_pool_lock_wait)
                    shared_exchange = self._exchange_pool.get(key)
                    if shared_exchange is None:
                        started_at = time.perf_counter()
                        import ccxt

                        config: dict = {
                            "enableRateLimit": True,
                            "options": {
                                "defaultType": "spot",
                                # Désactivé : élimine un GET /api/v3/time extra (~200ms) au 1er appel.
                                # L'horloge serveur est considérée suffisamment précise sans resync.
                                "adjustForTimeDifference": os.getenv(
                                    "MARKET_SCANNER_ADJUST_TIME", "false"
                                ).lower() == "true",
                                # Taille du pool de connexions HTTP keep-alive (défaut CCXT = 1)
                                # Augmenter à N_SYMBOLS pour fetch parallèle sans attente socket
                                "connectionPoolSize": int(os.getenv(
                                    "MARKET_SCANNER_POOL_SIZE", "8"
                                )),
                            },
                        }
                        shared_exchange = getattr(ccxt, self._exchange_id)(config)
                        created_exchange = True
                        if key[1]:
                            shared_exchange.set_sandbox_mode(True)
                            logger.info("[MarketScanner] Mode TESTNET — donnees publiques")
                        self._exchange_pool[key] = shared_exchange
                        # Record TTL baseline and ensure generation entry exists.
                        self.__class__._exchange_created_at[key] = time.monotonic()
                        self.__class__._exchange_generation.setdefault(key, 0)
                    self._exchange_call_locks.setdefault(key, threading.Lock())
                    self._exchange_markets_ready.setdefault(key, threading.Event())
                    self._exchange = shared_exchange
                    # Capture generation inside the lock so we see the same value
                    # that was current when we took the reference.
                    self._exchange_gen = self.__class__._exchange_generation.get(key, 0)

                if created_exchange and started_at is not None:
                    _t_create_ms = (time.perf_counter() - started_at) * 1000
                    if self._profile:
                        self._profile_data["exchange_create_ms"].append(_t_create_ms)
                        logger.info(
                            "[MarketScannerProfile] exchange.__init__()=%.1fms pool_lock_wait=%.1fms",
                            _t_create_ms, _pool_lock_wait,
                        )
                if self._trace_timings and created_exchange and started_at is not None:
                    logger.info(
                        "[MarketScannerTiming] %s/%s exchange initialisé en %.3fs",
                        self._exchange_id,
                        self._timeframe,
                        time.perf_counter() - started_at,
                    )
                elif self._trace_timings:
                    logger.info(
                        "[MarketScannerTiming] %s/%s exchange partagé réutilisé",
                        self._exchange_id,
                        self._timeframe,
                    )

                if os.getenv("MARKET_SCANNER_PRELOAD_MARKETS", "false").lower() == "true":
                    self._start_markets_preload(self._exchange, key)
            except Exception as exc:
                logger.warning(
                    "Impossible d'initialiser CCXT (%s): %s", self._exchange_id, exc
                )

        # ── TTL check ─────────────────────────────────────────────────────────
        # Done outside the lock (non-blocking) after we have a live reference.
        # If TTL is exceeded, self._exchange is cleared; next call re-creates.
        if self._exchange is not None:
            self._check_session_ttl(self._exchange_key())

        return self._exchange

    # ------------------------------------------------------------------
    # Fetch avec retry + circuit breaker + validation
    # ------------------------------------------------------------------

    def _fetch_series(self, symbol: str, limit: int | None = None) -> list[dict] | None:
        """Fetch OHLCV avec retry exponentiel et circuit breaker."""
        if self._circuit.is_open:
            logger.debug("[MarketScanner] Circuit ouvert — skip fetch %s", symbol)
            return None

        exchange = self._get_exchange()
        if exchange is None:
            return None

        key = self._exchange_key()
        ccxt_sym = _CCXT_SYMBOL_MAP.get(symbol, symbol)
        exchange_lock = self._get_exchange_call_lock(key)
        markets_ready = self._get_exchange_markets_ready(key)
        fetch_limit = limit or self._limit

        if not markets_ready.is_set():
            preload_wait_ms = max(0.0, float(os.getenv("MARKET_SCANNER_PRELOAD_WAIT_MS", "250")))
            if preload_wait_ms > 0 and os.getenv("MARKET_SCANNER_PRELOAD_MARKETS", "false").lower() == "true":
                markets_ready.wait(preload_wait_ms / 1000.0)
            if not markets_ready.is_set():
                try:
                    self._ensure_markets_loaded(exchange, key, source="inline")
                except Exception as exc:
                    logger.debug("[MarketScanner] load_markets() inline: %s", exc)

        def _do_fetch() -> list[dict]:
            started_at = time.perf_counter()
            _t_lock_start = time.perf_counter()
            with exchange_lock:
                _lock_wait_ms = (time.perf_counter() - _t_lock_start) * 1000
                _t_http_start = time.perf_counter()
                ohlcvs = exchange.fetch_ohlcv(ccxt_sym, self._timeframe, limit=fetch_limit)
                _http_ms = (time.perf_counter() - _t_http_start) * 1000
            if self._profile:
                self._profile_data["exchange_call_lock_wait_ms"].append(_lock_wait_ms)
                self._profile_data["fetch_ohlcv_http_ms"].append(_http_ms)
                logger.info(
                    "[MarketScannerProfile] %s lock_wait=%.1fms http=%.1fms total=%.1fms",
                    symbol, _lock_wait_ms, _http_ms,
                    (time.perf_counter() - started_at) * 1000,
                )
            if self._trace_timings:
                logger.info(
                    "[MarketScannerTiming] %s/%s fetch_ohlcv en %.3fs (limit=%d)",
                    symbol,
                    self._timeframe,
                    time.perf_counter() - started_at,
                    fetch_limit,
                )
            if not ohlcvs:
                raise ValueError(f"fetch_ohlcv retourné vide pour {ccxt_sym}")
            _t_parse = time.perf_counter()
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
            if self._profile:
                self._profile_data["parse_validate_ms"].append(
                    (time.perf_counter() - _t_parse) * 1000
                )
            markets_ready.set()
            return series

        _transport_exc: Exception | None = None
        try:
            raw = self._circuit.call(
                lambda: retry_with_backoff(
                    _do_fetch,
                    max_retries=self._max_retries,
                    base_delay=self._retry_base_delay,
                    max_delay=self._retry_max_delay,
                    label=f"fetch_ohlcv {symbol}",
                )
            )
        except Exception as _exc:
            _transport_exc = _exc
            if self._is_transport_error(_exc):
                max_errors = int(os.getenv("MARKET_SCANNER_SESSION_MAX_ERRORS", "5"))
                with self.__class__._exchange_pool_lock:
                    current = self.__class__._exchange_transport_errors.get(key, 0) + 1
                    self.__class__._exchange_transport_errors[key] = current
                if current >= max_errors:
                    logger.warning(
                        "[MarketScanner] %d erreurs transport consécutives (%s) — session invalidée",
                        current, type(_exc).__name__,
                    )
                    self.__class__._invalidate_exchange_session(
                        key, reason=f"{current}x_{type(_exc).__name__}"
                    )
                    self._exchange = None
                    self._exchange_gen = -1
                else:
                    logger.debug(
                        "[MarketScanner] Erreur transport %d/%d: %s",
                        current, max_errors, type(_exc).__name__,
                    )
            raise

        # Reset transport-error counter on any successful fetch.
        if raw is not None and _transport_exc is None:
            if self.__class__._exchange_transport_errors.get(key, 0) > 0:
                with self.__class__._exchange_pool_lock:
                    self.__class__._exchange_transport_errors[key] = 0

        if raw is None:
            if self._profile:
                self._profile_data["retry_count"].append(float(self._max_retries))
            return None

        # Validation des bougies
        _t_val = time.perf_counter()
        clean, report = validate_candles(raw, symbol=symbol)
        if self._profile and self._profile_data["parse_validate_ms"]:
            # Ajoute le temps de validate_candles au dernier parse
            self._profile_data["parse_validate_ms"][-1] += (time.perf_counter() - _t_val) * 1000
        if not clean:
            logger.warning(
                "[MarketScanner] %s : 0 bougies valides après validation", symbol
            )
            return None

        return clean

    def _merge_incremental_series(
        self,
        existing_series: list[dict],
        latest_series: list[dict],
    ) -> list[dict]:
        merged_by_timestamp = {
            candle["timestamp"]: dict(candle)
            for candle in existing_series
        }
        for candle in latest_series:
            merged_by_timestamp[candle["timestamp"]] = dict(candle)
        merged = sorted(merged_by_timestamp.values(), key=lambda candle: candle["timestamp"])
        return merged[-self._limit :]

    def _refresh_series_incremental(self, symbol: str) -> list[dict] | None:
        latest_series = self._fetch_series(symbol, limit=min(2, self._limit))
        if latest_series is None:
            return None
        return self._merge_incremental_series(self._history.get(symbol, []), latest_series)

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def get_history(self, symbol: str) -> list[dict]:
        """Retourne la série historique en cache pour un symbole."""
        return self._history.get(symbol, [])

    def reset_profile(self) -> None:
        """Réinitialise les données de profiling (avant une nouvelle mesure)."""
        for key in self._profile_data:
            self._profile_data[key].clear()

    def get_profile_report(self) -> dict:
        """
        Retourne un rapport de profiling fin du coût CCXT.

        Activé par MARKET_SCANNER_PROFILE=true.

        Métriques :
            exchange_pool_lock_wait_ms  : attente pour accéder au pool partagé
            exchange_create_ms          : temps de création de l'objet exchange
            exchange_call_lock_wait_ms  : attente du verrou d'appel HTTP
            fetch_ohlcv_http_ms         : durée HTTP pure (sans lock wait)
            retry_count                 : nombre de retries déclenchés
            parse_validate_ms           : temps parse JSON + validate_candles
        """
        import statistics as _st

        def _agg(vals: list[float]) -> dict:
            if not vals:
                return {"n": 0, "mean_ms": 0.0, "max_ms": 0.0, "total_ms": 0.0}
            return {
                "n":        len(vals),
                "mean_ms":  round(_st.mean(vals), 2),
                "max_ms":   round(max(vals), 2),
                "total_ms": round(sum(vals), 2),
            }

        report = {k: _agg(v) for k, v in self._profile_data.items()}
        # Résumé lisible
        http_mean   = report["fetch_ohlcv_http_ms"]["mean_ms"]
        lock_mean   = report["exchange_call_lock_wait_ms"]["mean_ms"]
        create_mean = report["exchange_create_ms"]["mean_ms"]
        parse_mean  = report["parse_validate_ms"]["mean_ms"]
        total_est   = create_mean + lock_mean + http_mean + parse_mean
        report["_summary"] = {
            "estimated_cold_cost_ms":    round(total_est, 1),
            "pct_http":                  round(http_mean / max(total_est, 0.001) * 100, 1),
            "pct_lock_wait":             round(lock_mean / max(total_est, 0.001) * 100, 1),
            "pct_exchange_create":       round(create_mean / max(total_est, 0.001) * 100, 1),
            "pct_parse_validate":        round(parse_mean / max(total_est, 0.001) * 100, 1),
        }
        if self._profile:
            logger.info(
                "[MarketScannerProfile] Résumé — cold_cost≈%.1fms "
                "(http=%.0f%% lock=%.0f%% create=%.0f%% parse=%.0f%%)",
                total_est,
                report["_summary"]["pct_http"],
                report["_summary"]["pct_lock_wait"],
                report["_summary"]["pct_exchange_create"],
                report["_summary"]["pct_parse_validate"],
            )
        return report

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
        scan_started_at = time.perf_counter()

        for symbol in self.symbols:
            series = None
            has_history = symbol in self._history
            series_fresh = has_history and is_series_fresh(
                self._history[symbol], max_age_seconds=self._freshness_seconds
            )
            source_label = "synthetic"

            # 1. Utiliser le cache si TTL non expiré
            last_fetch = self._fetch_ts.get(symbol, 0.0)
            cache_hit = (
                has_history
                and (now - last_fetch) < _CACHE_TTL_SECONDS
                and series_fresh
            )
            stale_cache_hit = (
                has_history
                and self._allow_stale_cache
                and self._timeframe_seconds > 3600.0
                and series_fresh
            )

            if cache_hit:
                series = self._history[symbol]
                self._stats["cached"] += 1
                source_label = "cache"
            elif stale_cache_hit:
                series = self._history[symbol]
                self._stats["cached"] += 1
                source_label = "stale_cache"
                logger.debug(
                    "[MarketScanner] %s/%s → stale cache réutilisé (age fetch %.1fs)",
                    symbol,
                    self._timeframe,
                    now - last_fetch,
                )

            # 2. Fetch réseau (si pas forcé synthétique et circuit non ouvert)
            elif not self._force_synthetic:
                if has_history and self._timeframe_seconds <= 3600.0 and series_fresh:
                    series = self._refresh_series_incremental(symbol)
                    if series is not None:
                        self._fetch_ts[symbol] = now
                        self._stats["real"] += 1
                        source_label = "ccxt_incremental"
                if series is None:
                    series = self._fetch_series(symbol)
                if series is not None:
                    self._fetch_ts[symbol] = now
                    self._stats["real"] += 1
                    source_label = "ccxt_live" if source_label == "synthetic" else source_label

            # 3. Fallback synthétique
            if series is None:
                series = _synthetic_series(symbol, self._limit)
                self._stats["synthetic"] += 1
                logger.debug("[MarketScanner] %s → données synthétiques", symbol)
                source_label = "synthetic"

            self._history[symbol] = series
            history[symbol] = series
            snapshots.append(series[-1])
            if self._trace_timings:
                logger.info(
                    "[MarketScannerTiming] %s/%s source=%s candles=%d",
                    symbol,
                    self._timeframe,
                    source_label,
                    len(series),
                )

        sources = {c["source"] for c in snapshots}
        quality = self.data_quality()
        logger.info(
            "[MarketScanner] %d symboles | source(s): %s | " "real=%.0f%% | circuit=%s",
            len(snapshots),
            sources,
            quality["real_ratio"] * 100,
            quality["circuit_state"],
        )
        if self._trace_timings:
            logger.info(
                "[MarketScannerTiming] scan %s total en %.3fs pour %d symbole(s)",
                self._timeframe,
                time.perf_counter() - scan_started_at,
                len(self.symbols),
            )
        return {"candles": snapshots, "history": history}
