"""
multi_timeframe_scanner.py — Fetche les bougies sur plusieurs timeframes.

Utilise le MarketScanner existant (CCXT + fallback synthétique) pour chaque TF.
Conçu pour être utilisé en complément du scan principal (1h déjà en cache) :
  fetch_higher_timeframes() retourne uniquement 4h + 1d pour éviter la double requête 1h.
"""

from __future__ import annotations

import logging
import time

from quant_hedge_ai.agents.market.market_scanner import MarketScanner

logger = logging.getLogger(__name__)

# Timeframes disponibles par ordre croissant
HIGHER_TFS: list[str] = ["4h", "1d"]

# Nombre de bougies par timeframe (suffisant pour les indicateurs)
_TF_LIMIT: dict[str, int] = {
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
        self._scanners: dict[str, MarketScanner] = {
            tf: MarketScanner(
                symbols=self.symbols,
                timeframe=tf,
                limit=_TF_LIMIT.get(tf, 50),
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
            logger.debug("[MTF] Cache hit (cycle=%d)", cycle)
            return self._cache

        result: dict[str, dict[str, list[dict]]] = {sym: {} for sym in self.symbols}
        for tf, scanner in self._scanners.items():
            market = scanner.scan()
            for sym in self.symbols:
                candles = (
                    market.get("history", {}).get(sym)
                    or market.get("candles", {}).get(sym)
                    or []
                )
                result[sym][tf] = candles
                logger.info(
                    "[MTF] %s/%s — %d bougies (source=%s)",
                    sym,
                    tf,
                    len(candles),
                    candles[0].get("source", "?") if candles else "empty",
                )

        self._cache = result
        self._last_scan_cycle = cycle
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
