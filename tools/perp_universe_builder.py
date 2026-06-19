"""
PerpUniverseBuilder — découverte dynamique des paires perp MEXC tradables.

Effectue un fetch_tickers() batch (1 seul appel API) puis filtre et score
chaque paire selon des critères adaptés au trading perpetuel.

Support multi-quote : USDT, USDC, USDT1 — permet un univers de 200-400+ paires
scannées dont les top N sont retenus après scoring composite.

Critères de disqualification (filtres hard):
    - Quote non dans ALLOWED_QUOTES (USDT, USDC, USDT1 par défaut)
    - Volume 24h < MIN_VOL_USD
    - Spread bid/ask > MAX_SPREAD_PCT
    - Prix last <= 0

Score composite:
    Volume     40 %  — profondeur / liquidité de marché
    Spread     30 %  — coût de transaction effectif
    Volatilité 20 %  — exploitabilité du signal (range journalier)
    Fiabilité  10 %  — qualité des données tick

Variables d'env:
    PERP_BUILDER_EXCHANGE       défaut mexc
    PERP_BUILDER_MIN_VOL_USD    défaut 2_000_000  (2M USD — couvre 100+ paires)
    PERP_BUILDER_MAX_SPREAD_PCT défaut 0.50
    PERP_BUILDER_TOP_N          défaut 100
    PERP_BUILDER_QUOTES         défaut USDT,USDC
    PERP_BUILDER_USE_SWAP       défaut false  (true = requête marché swap/perp)
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PerpCandidate:
    symbol: str
    score: float
    vol_24h_usd: float
    spread_pct: float
    last_price: float
    high_24h: float = 0.0
    low_24h: float = 0.0
    details: dict = field(default_factory=dict)
    scanned_at: float = field(default_factory=time.time)

    def __repr__(self) -> str:
        return (
            f"PerpCandidate({self.symbol} score={self.score:.1f} "
            f"vol=${self.vol_24h_usd/1e6:.1f}M spread={self.spread_pct:.4f}%)"
        )


class PerpUniverseBuilder:
    """
    Construit dynamiquement un univers de paires perp qualifiées
    en interrogeant l'exchange (MEXC par défaut) via CCXT.

    Usage minimal:
        builder = PerpUniverseBuilder()
        top50 = builder.symbols()          # retourne list[str]
        report = builder.discover()        # retourne list[PerpCandidate]
        builder.print_report(report)

    Usage avec paramètres:
        builder = PerpUniverseBuilder(exchange_id="mexc")
        candidates = builder.discover(top_n=100, min_vol_usd=2_000_000)
        syms = [c.symbol for c in candidates]
    """

    # ── Seuils configurables via env ─────────────────────────────────────────
    MIN_VOL_USD: float = float(os.getenv("PERP_BUILDER_MIN_VOL_USD", "2000000"))
    MAX_SPREAD_PCT: float = float(os.getenv("PERP_BUILDER_MAX_SPREAD_PCT", "0.50"))
    DEFAULT_TOP_N: int = int(os.getenv("PERP_BUILDER_TOP_N", "100"))

    # Quotes acceptées (USDT, USDC, USDT1)
    _DEFAULT_QUOTES: frozenset[str] = frozenset(
        q.strip().upper()
        for q in os.getenv("PERP_BUILDER_QUOTES", "USDT,USDC").split(",")
        if q.strip()
    )

    # Références de normalisation
    _VOL_REF = 500_000_000.0  # 500M USD → score vol 100
    _SPREAD_PERFECT = 0.01  # ≤0.01% → score spread 100
    _SPREAD_MAX = 0.30  # ≥0.30% → score spread 0
    _DAILY_RANGE_REF = 3.0  # 3% range/jour → score vola 100

    WEIGHTS = {
        "volume": 0.40,
        "spread": 0.30,
        "volatility": 0.20,
        "reliability": 0.10,
    }

    def __init__(self, exchange_id: Optional[str] = None) -> None:
        self._exchange_id = (
            exchange_id or os.getenv("PERP_BUILDER_EXCHANGE", "mexc")
        ).lower()
        self._use_swap = os.getenv("PERP_BUILDER_USE_SWAP", "false").lower() == "true"
        self._exchange = None
        # Quotes acceptées — peut être écrasé par PerpUniverseService
        self._allowed_quotes: frozenset[str] = self._DEFAULT_QUOTES

    # ── API principale ────────────────────────────────────────────────────────

    def discover(
        self,
        top_n: Optional[int] = None,
        min_vol_usd: Optional[float] = None,
        max_spread_pct: Optional[float] = None,
    ) -> list[PerpCandidate]:
        """
        Découvre et classe les paires qualifiées.
        Retourne une liste triée par score décroissant, taille top_n.
        """
        top_n = top_n or self.DEFAULT_TOP_N
        min_vol = min_vol_usd if min_vol_usd is not None else self.MIN_VOL_USD
        max_spread = (
            max_spread_pct if max_spread_pct is not None else self.MAX_SPREAD_PCT
        )

        exch = self._get_exchange()
        exch.load_markets()

        # Un seul appel API — fetch_tickers() retourne tous les marchés actifs
        all_tickers = exch.fetch_tickers()

        candidates: list[PerpCandidate] = []
        for sym, raw in all_tickers.items():
            if not self._is_eligible_symbol(sym):
                continue

            last = float(raw.get("last") or 0.0)
            if last <= 0:
                continue

            bid = float(raw.get("bid") or 0.0)
            ask = float(raw.get("ask") or 0.0)
            spread = (ask - bid) / ask * 100.0 if ask > 0 else 999.0

            vol = self._extract_vol_usd(raw, last)
            if vol < min_vol:
                continue
            if spread > max_spread:
                continue

            high = float(raw.get("high") or 0.0)
            low = float(raw.get("low") or 0.0)

            details = {
                "volume_score": round(self._score_vol(vol), 1),
                "spread_score": round(self._score_spread(spread), 1),
                "volatility_score": round(self._score_volatility(high, low, last), 1),
                "reliability_score": round(self._score_reliability(raw), 1),
            }
            score = sum(
                details[k] * self.WEIGHTS[k.replace("_score", "")] for k in details
            )

            candidates.append(
                PerpCandidate(
                    symbol=sym,
                    score=round(score, 2),
                    vol_24h_usd=vol,
                    spread_pct=round(spread, 4),
                    last_price=last,
                    high_24h=high,
                    low_24h=low,
                    details=details,
                )
            )

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:top_n]

    def symbols(self, top_n: Optional[int] = None, **kwargs) -> list[str]:
        """Retourne la liste des symboles qualifiés (format CCXT BTC/USDT)."""
        return [c.symbol for c in self.discover(top_n=top_n, **kwargs)]

    def save(self, candidates: list[PerpCandidate], path: str) -> None:
        """Sérialise les candidats en JSON."""
        data = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "exchange": self._exchange_id,
            "count": len(candidates),
            "min_vol_usd": self.MIN_VOL_USD,
            "max_spread_pct": self.MAX_SPREAD_PCT,
            "symbols": [c.symbol for c in candidates],
            "candidates": [
                {
                    "symbol": c.symbol,
                    "score": c.score,
                    "vol_24h_usd": round(c.vol_24h_usd, 0),
                    "spread_pct": c.spread_pct,
                    "last_price": c.last_price,
                    **c.details,
                }
                for c in candidates
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # ── Rapport texte ─────────────────────────────────────────────────────────

    def print_report(self, candidates: list[PerpCandidate]) -> None:
        header = f"PERP UNIVERSE — TOP {len(candidates)} ({self._exchange_id.upper()})"
        w = 74
        print(f"\n{'═'*w}")
        print(f"{header:^{w}}")
        print(f"{'═'*w}")
        print(
            f"{'#':<4} {'Symbol':<14} {'Score':>6}  {'Vol(M$)':>8}  "
            f"{'Spread%':>7}  {'Price':>12}  {'V':>5} {'S':>5} {'V2':>5} {'R':>5}"
        )
        print(f"{'─'*w}")
        for i, c in enumerate(candidates, 1):
            d = c.details
            print(
                f"{i:<4} {c.symbol:<14} {c.score:>6.1f}  "
                f"{c.vol_24h_usd/1e6:>8.1f}  "
                f"{c.spread_pct:>7.4f}  "
                f"{c.last_price:>12.6g}  "
                f"{d.get('vol_score', 0):>5.0f} "
                f"{d.get('spread_score', 0):>5.0f} "
                f"{d.get('volatility_score', 0):>5.0f} "
                f"{d.get('reliability_score', 0):>5.0f}"
            )
        print(f"{'═'*w}")
        print(f"  V=Volume  S=Spread  V2=Volatilité  R=Fiabilité")
        print(
            f"  Min vol: ${self.MIN_VOL_USD/1e6:.1f}M  Max spread: {self.MAX_SPREAD_PCT}%\n"  # noqa: E501
        )

    # ── Internals ─────────────────────────────────────────────────────────────

    def _get_exchange(self):
        if self._exchange is None:
            try:
                import ccxt
            except ImportError as exc:
                raise ImportError("ccxt requis : pip install ccxt") from exc

            cls = getattr(ccxt, self._exchange_id, None)
            if cls is None:
                raise ValueError(f"Exchange inconnu : {self._exchange_id}")

            config: dict = {"enableRateLimit": True}
            if self._use_swap:
                config["options"] = {"defaultType": "swap"}
            self._exchange = cls(config)
        return self._exchange

    def _is_eligible_symbol(self, sym: str) -> bool:
        """
        Garde les paires dont la quote currency est dans _allowed_quotes.
        Exemples valides : BTC/USDT, ETH/USDC, SOL/USDT1, BTC/USDT:USDT
        Exemples exclus  : BTC-240329 (livraison), BTC/BTC (inverse), ETH/BTC
        """
        # Exclure options, livraisons trimestrielles, indices
        if any(x in sym for x in ["-", "PERP/"]):
            return False
        # Extraire la quote currency
        if "/" not in sym:
            return False
        quote_part = sym.split("/")[1]
        # CCXT perp format: "BTC/USDT:USDT" → quote = "USDT:USDT" → base quote = "USDT"
        quote = quote_part.split(":")[0].upper()
        return quote in self._allowed_quotes

    def _extract_vol_usd(self, raw: dict, last: float) -> float:
        """Extrait le volume 24h en USD depuis le ticker brut."""
        # quoteVolume = volume directement en USDT (préféré)
        qvol = float(raw.get("quoteVolume") or 0.0)
        if qvol > 0:
            return qvol
        # baseVolume × last = approximation en USD
        bvol = float(raw.get("baseVolume") or 0.0)
        return bvol * last if bvol > 0 else 0.0

    def _score_vol(self, vol: float) -> float:
        if vol <= 0:
            return 0.0
        return min(100.0, math.log10(vol + 1) / math.log10(self._VOL_REF + 1) * 100.0)

    def _score_spread(self, spread: float) -> float:
        if spread <= self._SPREAD_PERFECT:
            return 100.0
        if spread >= self._SPREAD_MAX:
            return 0.0
        return max(
            0.0,
            100.0
            * (
                1.0
                - (spread - self._SPREAD_PERFECT)
                / (self._SPREAD_MAX - self._SPREAD_PERFECT)
            ),
        )

    def _score_volatility(self, high: float, low: float, last: float) -> float:
        if last <= 0 or high <= low:
            return 50.0
        daily_range_pct = (high - low) / last * 100.0
        return min(100.0, daily_range_pct / self._DAILY_RANGE_REF * 100.0)

    def _score_reliability(self, raw: dict) -> float:
        score = 100.0
        if not raw.get("bid") or float(raw.get("bid") or 0) <= 0:
            score -= 30.0
        if not raw.get("ask") or float(raw.get("ask") or 0) <= 0:
            score -= 30.0
        if not raw.get("last") or float(raw.get("last") or 0) <= 0:
            score -= 40.0
        return max(0.0, score)


# ── CLI rapide ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="PerpUniverseBuilder — scan paires MEXC"
    )
    parser.add_argument("--exchange", default=None, help="Exchange CCXT (défaut: mexc)")
    parser.add_argument("--top", type=int, default=50, help="Top N paires à retenir")
    parser.add_argument(
        "--min-vol", type=float, default=None, help="Volume min 24h en USD (défaut: 5M)"
    )
    parser.add_argument(
        "--max-spread", type=float, default=None, help="Spread max en %% (défaut: 0.30)"
    )
    parser.add_argument("--save", default=None, help="Chemin JSON pour sauvegarder")
    parser.add_argument(
        "--symbols-only", action="store_true", help="Affiche uniquement les symboles"
    )
    args = parser.parse_args()

    builder = PerpUniverseBuilder(exchange_id=args.exchange)
    t0 = time.perf_counter()
    candidates = builder.discover(
        top_n=args.top,
        min_vol_usd=args.min_vol,
        max_spread_pct=args.max_spread,
    )
    elapsed = time.perf_counter() - t0
    print(f"Scan terminé en {elapsed:.1f}s — {len(candidates)} paires qualifiées")

    if args.symbols_only:
        for c in candidates:
            print(c.symbol)
    else:
        builder.print_report(candidates)

    if args.save:
        builder.save(candidates, args.save)
        print(f"Sauvegardé → {args.save}")
