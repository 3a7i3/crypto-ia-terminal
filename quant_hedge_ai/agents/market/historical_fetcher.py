"""
HistoricalDataFetcher — télécharge des années de données OHLCV via CCXT
avec pagination, retry et persistance SQLite.

Usage rapide :
    fetcher = HistoricalDataFetcher()
    candles = fetcher.fetch("BTC/USDT", timeframe="1h", years=2)
    print(f"{len(candles)} bougies récupérées")

Variables d'env :
    BINANCE_API_KEY / BINANCE_API_SECRET  — optionnels (données publiques sans clé)
    BINANCE_TESTNET                        — true pour testnet
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from observability.json_logger import get_logger
from quant_hedge_ai.agents.market.ohlcv_validator import validate_candles
from quant_hedge_ai.agents.market.retry_policy import retry_with_backoff

_log = get_logger("quant_hedge_ai.agents.market.historical_fetcher")
# Nombre de bougies par requête (max Binance = 1000, on prend 500 par sécurité)
_PAGE_SIZE = 500

_TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


class HistoricalDataFetcher:
    """
    Télécharge plusieurs années de bougies OHLCV par pagination CCXT.

    Algorithme :
        1. Calcule le timestamp de départ (now - years)
        2. Boucle en avançant de PAGE_SIZE bougies à chaque page
        3. Valide chaque page (filtre OHLCV corrompus)
        4. Sauvegarde en SQLite via MarketDatabase (optionnel)
        5. Respecte le rate limit de l'exchange
    """

    def __init__(self, exchange_id: str | None = None) -> None:
        self._exchange_id = (
            exchange_id
            or os.getenv("EXCHANGE_ID")
            or os.getenv("ACTIVE_EXCHANGE")
            or "binance"
        )
        self._exchange = None

    def _get_exchange(self):
        if self._exchange is not None:
            return self._exchange
        try:
            import ccxt

            config: dict = {"enableRateLimit": True}
            eid = self._exchange_id.lower()

            if eid == "gateio":
                api_key = os.getenv("GATEIO_API_KEY")
                api_secret = os.getenv("GATEIO_API_SECRET")
                if api_key and api_secret:
                    config["apiKey"] = api_key
                    config["secret"] = api_secret
                if os.getenv("GATEIO_TESTNET", "false").lower() == "true":
                    config["options"] = {"defaultType": "swap"}
            else:
                api_key = os.getenv("BINANCE_API_KEY")
                api_secret = os.getenv("BINANCE_API_SECRET")
                if api_key and api_secret:
                    config["apiKey"] = api_key
                    config["secret"] = api_secret

            self._exchange = getattr(ccxt, eid)(config)
            _log.info("[HistoricalFetcher] Exchange %s initialisé", eid)
        except Exception as exc:
            _log.error("[HistoricalFetcher] Impossible d'initialiser ccxt: %s", exc)
        return self._exchange

    def fetch(
        self,
        symbol: str,
        timeframe: str = "1h",
        years: float = 2.0,
        progress: bool = True,
    ) -> list[dict]:
        """
        Récupère `years` années de bougies OHLCV pour `symbol`.

        Retourne une liste de dicts triée par timestamp croissant.
        Retourne [] si l'exchange n'est pas accessible.
        """
        exchange = self._get_exchange()
        if exchange is None:
            _log.error("[HistoricalFetcher] Exchange non disponible")
            return []

        tf_sec = _TIMEFRAME_SECONDS.get(timeframe, 3600)
        total_candles = int(years * 365 * 24 * 3600 / tf_sec)
        since_ms = int((time.time() - years * 365 * 24 * 3600) * 1000)

        _log.info(
            "[HistoricalFetcher] Fetch %s %s — %.1f an(s) ≈ %d bougies depuis %s",
            symbol,
            timeframe,
            years,
            total_candles,
            datetime.fromtimestamp(since_ms / 1000, tz=timezone.utc).strftime(
                "%Y-%m-%d"
            ),
        )

        all_candles: list[dict] = []
        page = 0
        rate_limit = max(exchange.rateLimit / 1000, 0.1)

        while True:
            page += 1
            current_since = since_ms

            batch_raw = retry_with_backoff(
                lambda: exchange.fetch_ohlcv(
                    symbol, timeframe, since=current_since, limit=_PAGE_SIZE
                ),
                max_retries=3,
                base_delay=2.0,
                max_delay=30.0,
                label=f"fetch_ohlcv p{page} {symbol}",
            )

            if not batch_raw:
                _log.info("[HistoricalFetcher] Page %d vide — fin du fetch", page)
                break

            batch_dicts = [
                {
                    "symbol": symbol,
                    "timestamp": datetime.fromtimestamp(
                        ts / 1000, tz=timezone.utc
                    ).isoformat(),
                    "open": float(o),
                    "high": float(h),
                    "low": float(l),
                    "close": float(c),
                    "volume": float(v),
                    "source": "ccxt_live",
                }
                for ts, o, h, l, c, v in batch_raw
            ]

            clean, report = validate_candles(batch_dicts, symbol=symbol)
            all_candles.extend(clean)

            last_ts = batch_raw[-1][0]
            since_ms = last_ts + 1  # prochaine page commence après la dernière bougie

            if progress and page % 5 == 0:
                pct = len(all_candles) / max(total_candles, 1) * 100
                _log.info(
                    "[HistoricalFetcher] %s page %d — %d bougies (%.0f%%) — last: %s",
                    symbol,
                    page,
                    len(all_candles),
                    pct,
                    datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                )

            # Stop si la dernière bougie dépasse maintenant
            if last_ts >= int(time.time() * 1000):
                break

            # Stop si on a moins de PAGE_SIZE → dernière page
            if len(batch_raw) < _PAGE_SIZE:
                break

            # Respecter le rate limit
            time.sleep(rate_limit)

        # Dédupliquer par timestamp (au cas où les pages se chevauchent)
        seen: set[str] = set()
        unique: list[dict] = []
        for c in all_candles:
            key = c["timestamp"]
            if key not in seen:
                seen.add(key)
                unique.append(c)

        unique.sort(key=lambda c: c["timestamp"])

        _log.info(
            "[HistoricalFetcher] %s %s — %d bougies uniques récupérées (%.1f ans)",
            symbol,
            timeframe,
            len(unique),
            years,
        )
        return unique

    def fetch_and_save(
        self,
        symbols: list[str],
        timeframe: str = "1h",
        years: float = 2.0,
        db_path: str = "databases/market_data.sqlite",
    ) -> dict[str, int]:
        """
        Fetch + sauvegarde en SQLite pour chaque symbole.
        Retourne {symbol: nb_bougies_sauvegardées}.
        """
        from quant_hedge_ai.strategy_lab.market_db import MarketDatabase

        db = MarketDatabase(db_path=db_path)
        results: dict[str, int] = {}

        for symbol in symbols:
            candles = self.fetch(symbol, timeframe=timeframe, years=years)
            if not candles:
                results[symbol] = 0
                continue

            # Regrouper sous le format attendu par save_snapshot
            fake_market = {
                "candles": [candles[-1]],
                "history": {symbol: candles},
            }
            saved = db.save_snapshot(fake_market)
            results[symbol] = saved
            _log.info(
                "[HistoricalFetcher] %s → %d bougies sauvegardées",
                symbol,
                saved,
            )

        return results
