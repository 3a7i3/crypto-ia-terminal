"""
multi_timeframe_scanner.py — Fetche les bougies sur plusieurs timeframes.

Utilise le MarketScanner existant (CCXT + fallback synthétique) pour chaque TF.
Conçu pour être utilisé en complément du scan principal (1h déjà en cache) :
  fetch_higher_timeframes() retourne uniquement 4h + 1d.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from observability.json_logger import get_logger
from quant_hedge_ai.agents.market.market_scanner import MarketScanner

_log = get_logger("quant_hedge_ai.agents.market.multi_timeframe_scanner")
# Timeframes disponibles par ordre croissant
HIGHER_TFS: list[str] = ["1m", "15m", "4h", "1d"]

# Nombre de bougies par timeframe (suffisant pour les indicateurs)
_TF_LIMIT: dict[str, int] = {
    "1m": 60,  # 60 × 1m = 1h — signal live quasi-temps-réel
    "15m": 96,  # 96 × 15m = 24h — réactivité intra-heure
    "4h": 60,
    "1d": 50,
}


class MultiTimeframeScanner:
    """
    Gère un scanner CCXT par timeframe (4h, 1d).
    Le 1h est géré par le MarketScanner principal — ne pas le refetcher.

    Usage:
        mtf = MultiTimeframeScanner(symbols=["BTC/USDT"])
        data = mtf.scan()          # {symbol: {"4h": [...], "1d": [...]}}
        mtf.merge_base(data, "BTC/USDT", candles_1h)  # ajoute "1h"
    """

    def __init__(
        self,
        symbols: list[str] | None = None,
        timeframes: list[str] | None = None,
        refresh_every: int = 4,  # cycles entre deux scans complets
    ) -> None:
        self.symbols = symbols or ["BTC/USDT"]
        self.timeframes = timeframes or HIGHER_TFS
        self._refresh_every = refresh_every
        self._trace_timings = (
            os.getenv(
                "MTF_SCAN_TRACE_TIMINGS",
                os.getenv("MARKET_SCANNER_TRACE_TIMINGS", "false"),
            ).lower()
            == "true"
        )
        self._max_workers = max(
            1, int(os.getenv("MTF_SCAN_MAX_WORKERS", str(len(self.timeframes) or 1)))
        )
        mtf_max_retries = int(os.getenv("MTF_SCAN_MAX_RETRIES", "1"))
        mtf_retry_base_delay = float(os.getenv("MTF_SCAN_RETRY_BASE_DELAY", "0.5"))
        mtf_retry_max_delay = float(os.getenv("MTF_SCAN_RETRY_MAX_DELAY", "2.0"))
        self._scanners: dict[str, MarketScanner] = {
            tf: MarketScanner(
                symbols=self.symbols,
                timeframe=tf,
                limit=_TF_LIMIT.get(tf, 50),
                max_retries=mtf_max_retries,
                retry_base_delay=mtf_retry_base_delay,
                retry_max_delay=mtf_retry_max_delay,
            )
            for tf in self.timeframes
        }
        self._cache: dict[str, dict[str, list[dict]]] = {}  # {symbol: {tf: candles}}
        self._last_scan_cycle: int = -999

    # ── API publique ──────────────────────────────────────────────────────────

    def scan(self, cycle: int = 0) -> dict[str, dict[str, list[dict]]]:
        """
        Fetche (ou retourne le cache) les candles pour chaque symbole + TF.
        Retourne : {symbol: {timeframe: [candles]}}
        """
        if abs(cycle - self._last_scan_cycle) < self._refresh_every and self._cache:
            _log.debug("[MTF] Cache hit (cycle=%d)", cycle)
            if self._trace_timings:
                _log.info("[MTFTiming] cache hit au cycle %d", cycle)
            return self._cache

        started_at = time.perf_counter()
        result: dict[str, dict[str, list[dict]]] = {sym: {} for sym in self.symbols}
        with ThreadPoolExecutor(
            max_workers=self._max_workers, thread_name_prefix="MTFScan"
        ) as executor:
            futures = {
                executor.submit(scanner.scan): tf
                for tf, scanner in self._scanners.items()
            }
            for future in as_completed(futures):
                tf = futures[future]
                try:
                    market = future.result()
                except Exception as exc:
                    _log.warning("[MTF] %s scan échoué: %s", tf, exc)
                    market = {"history": {}, "candles": {}}

                for sym in self.symbols:
                    candles = (
                        market.get("history", {}).get(sym)
                        or market.get("candles", {}).get(sym)
                        or []
                    )
                    result[sym][tf] = candles
                    _log.info(
                        "[MTF] %s/%s — %d bougies (source=%s)",
                        sym,
                        tf,
                        len(candles),
                        candles[0].get("source", "?") if candles else "empty",
                    )

        self._cache = result
        self._last_scan_cycle = cycle
        if self._trace_timings:
            _log.info(
                "[MTFTiming] scan total cycle=%d en %.3fs pour %d TF(s)",
                cycle,
                time.perf_counter() - started_at,
                len(self.timeframes),
            )
        return result

    @staticmethod
    def merge_base(
        mtf_data: dict[str, dict[str, list[dict]]],
        symbol: str,
        candles_1h: list[dict],
    ) -> dict[str, list[dict]]:
        """
        Ajoute les candles 1h (déjà fetché par le scanner principal) au dict MTF.
        Retourne : {"1h": [...], "4h": [...], "1d": [...]}
        """
        merged = dict(mtf_data.get(symbol, {}))
        merged["1h"] = candles_1h
        return merged
