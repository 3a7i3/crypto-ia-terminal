"""
Market Universe Ranker — sélection des actifs les plus tradables.

Score composite sur 6 critères :
    Volume 24h             30%
    Liquidité orderbook    25%
    Spread moyen           15%
    Volatilité exploitable 15%
    Corrélation portfolio  10%
    Fiabilité exchange      5%

Usage :
    ranker = MarketUniverseRanker()
    scores = ranker.rank(["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"])
    # → [RankEntry(symbol="BTC/USDT", score=82, ...), ...]
    ranker.print_report(scores)
"""

from __future__ import annotations

import math
import statistics
import time
from dataclasses import dataclass, field
from typing import Optional

# Poids des critères (somme = 1.0)
_WEIGHTS = {
    "volume": 0.30,
    "liquidity": 0.25,
    "spread": 0.15,
    "volatility": 0.15,
    "correlation": 0.10,
    "reliability": 0.05,
}

# Premier batch recommandé
BATCH_1 = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT", "DOGE/USDT"]
BATCH_2 = ["LINK/USDT", "AVAX/USDT", "SUI/USDT", "HYPE/USDT"]


@dataclass
class RankEntry:
    symbol: str
    score: float
    details: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def __repr__(self) -> str:
        return f"RankEntry({self.symbol} score={self.score:.1f})"


class MarketUniverseRanker:
    """
    Évalue et classe les actifs par tradabilité.
    Utilise LiveExchangeReader pour les données live,
    avec fallback sur données synthétiques si exchange indisponible.
    """

    # Seuils de référence pour la normalisation
    _VOL_REF_USD = 500_000_000.0  # 500M USD → score 100 volume
    _LIQ_REF_USD = 1_000_000.0  # 1M USD profondeur 10 niveaux → score 100
    _SPREAD_MAX_PCT = 0.30  # 0.30% spread → score 0
    _SPREAD_PERFECT_PCT = 0.01  # 0.01% spread → score 100
    _VOL_DAILY_REF_PCT = 3.0  # 3% volatilité/jour → score 100

    def __init__(self, reader=None) -> None:
        self._reader = reader  # LiveExchangeReader, injecté ou None

    # ── API principale ────────────────────────────────────────────────────────

    def rank(
        self,
        symbols: list[str],
        existing_positions: Optional[list[str]] = None,
        top_n: Optional[int] = None,
    ) -> list[RankEntry]:
        existing_positions = existing_positions or []
        entries = []
        for sym in symbols:
            try:
                entry = self._score_symbol(sym, existing_positions)
                entries.append(entry)
            except Exception as exc:
                entries.append(
                    RankEntry(
                        symbol=sym,
                        score=0.0,
                        details={"error": str(exc)},
                    )
                )
        entries.sort(key=lambda e: e.score, reverse=True)
        if top_n:
            entries = entries[:top_n]
        return entries

    def print_report(self, entries: list[RankEntry]) -> None:
        print(f"\n{'─'*55}")
        print(f"{'MARKET UNIVERSE RANKER':^55}")
        print(f"{'─'*55}")
        print(
            f"{'#':<3} {'Symbole':<12} {'Score':>6}  {'Vol':>5} {'Liq':>5} "
            f"{'Sprd':>5} {'Vola':>5} {'Corr':>5} {'Rel':>5}"
        )
        print(f"{'─'*55}")
        for i, e in enumerate(entries, 1):
            d = e.details
            print(
                f"{i:<3} {e.symbol:<12} {e.score:>6.1f}  "
                f"{d.get('volume', 0):>5.0f} "
                f"{d.get('liquidity', 0):>5.0f} "
                f"{d.get('spread', 0):>5.0f} "
                f"{d.get('volatility', 0):>5.0f} "
                f"{d.get('correlation', 0):>5.0f} "
                f"{d.get('reliability', 0):>5.0f}"
            )
        print(f"{'─'*55}\n")

    # ── Scoring par critère ───────────────────────────────────────────────────

    def _score_symbol(self, symbol: str, existing_positions: list[str]) -> RankEntry:
        details: dict[str, float] = {}

        if self._reader is not None:
            try:
                ticker = self._reader.fetch_ticker(symbol)
                ob = self._reader.fetch_order_book(symbol, depth=20)
                ohlcv = self._reader.fetch_ohlcv(symbol, "1d", limit=14)
            except Exception:
                ticker = ob = ohlcv = None
        else:
            ticker = ob = ohlcv = None

        details["volume"] = self._score_volume(ticker)
        details["liquidity"] = self._score_liquidity(ob)
        details["spread"] = self._score_spread(ticker, ob)
        details["volatility"] = self._score_volatility(ohlcv)
        details["correlation"] = self._score_correlation(symbol, existing_positions)
        details["reliability"] = self._score_reliability(ticker, ob)

        score = sum(details[k] * _WEIGHTS[k] for k in _WEIGHTS)
        return RankEntry(
            symbol=symbol,
            score=round(score, 2),
            details={k: round(v, 1) for k, v in details.items()},
        )

    def _score_volume(self, ticker) -> float:
        if ticker is None:
            return 50.0
        vol = ticker.volume_24h
        if vol <= 0:
            return 0.0
        return min(
            100.0, (math.log10(vol + 1) / math.log10(self._VOL_REF_USD + 1)) * 100.0
        )

    def _score_liquidity(self, ob) -> float:
        if ob is None:
            return 50.0
        depth = (ob.depth_bid_usd + ob.depth_ask_usd) / 2.0
        return min(100.0, depth / self._LIQ_REF_USD * 100.0)

    def _score_spread(self, ticker, ob) -> float:
        spread = None
        if ob is not None and ob.spread_pct > 0:
            spread = ob.spread_pct
        elif ticker is not None:
            spread = ticker.spread_pct
        if spread is None or spread <= 0:
            return 50.0
        if spread <= self._SPREAD_PERFECT_PCT:
            return 100.0
        if spread >= self._SPREAD_MAX_PCT:
            return 0.0
        return max(
            0.0,
            100.0
            * (
                1.0
                - (spread - self._SPREAD_PERFECT_PCT)
                / (self._SPREAD_MAX_PCT - self._SPREAD_PERFECT_PCT)
            ),
        )

    def _score_volatility(self, ohlcv: Optional[list]) -> float:
        if not ohlcv or len(ohlcv) < 3:
            return 50.0
        daily_ranges = [
            abs(c["high"] - c["low"]) / c["close"] * 100.0
            for c in ohlcv
            if c["close"] > 0
        ]
        if not daily_ranges:
            return 50.0
        avg_range = statistics.mean(daily_ranges)
        return min(100.0, avg_range / self._VOL_DAILY_REF_PCT * 100.0)

    def _score_correlation(self, symbol: str, existing: list[str]) -> float:
        if not existing:
            return 100.0
        highly_correlated = {
            frozenset(["BTC/USDT", "ETH/USDT"]): 0.85,
            frozenset(["ETH/USDT", "BNB/USDT"]): 0.80,
            frozenset(["SOL/USDT", "AVAX/USDT"]): 0.75,
            frozenset(["BTC/USDT", "SOL/USDT"]): 0.70,
        }
        max_corr = 0.0
        for ex in existing:
            pair = frozenset([symbol, ex])
            corr = highly_correlated.get(pair, 0.40)
            max_corr = max(max_corr, corr)
        return round((1.0 - max_corr) * 100.0, 1)

    def _score_reliability(self, ticker, ob) -> float:
        if ticker is None and ob is None:
            return 0.0
        score = 100.0
        if ticker is None:
            score -= 50.0
        elif ticker.volume_24h == 0:
            score -= 30.0
        if ob is None:
            score -= 50.0
        elif not ob.bids or not ob.asks:
            score -= 30.0
        return max(0.0, score)


# ── CLI rapide ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Market Universe Ranker")
    parser.add_argument(
        "--exchange",
        default=None,
        help="Exchange ccxt (défaut: LIVE_READER_EXCHANGE ou binance)",
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=BATCH_1 + BATCH_2,
        help="Symboles à évaluer",
    )
    parser.add_argument("--top", type=int, default=None, help="Afficher N premiers")
    parser.add_argument(
        "--no-live",
        action="store_true",
        help="Scoring heuristique sans appel exchange",
    )
    args = parser.parse_args()

    reader = None
    if not args.no_live:
        try:
            from infra.live_exchange_reader import LiveExchangeReader

            reader = LiveExchangeReader(exchange_id=args.exchange)
            ping = reader.ping()
            print(
                f"Exchange : {ping['exchange']} — {ping['status']} "
                f"({ping.get('latency_ms', '?')}ms)"
            )
        except Exception as e:
            print(f"[WARN] Exchange indisponible ({e}) — scoring heuristique")

    ranker = MarketUniverseRanker(reader=reader)
    results = ranker.rank(args.symbols, top_n=args.top)
    ranker.print_report(results)
