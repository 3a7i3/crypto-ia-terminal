"""
SymbolStability — scoring de tradabilité d'un symbole à partir de son OHLCV.

Score composite 0-100 :
    body_ratio  35 pts  qualité directionnelle (|close-open| / range, moins de mèches)
    vol_cv      25 pts  homogénéité du volume (flux régulier = price discovery propre)
    atr_score   20 pts  volatilité dans la fenêtre optimale (0.5 %–2 % par bougie 1h)
    trend_r2    20 pts  clarté de la tendance (R² régression linéaire sur les clôtures)

Plus le score est élevé, plus le symbole est "propre" à trader :
  80-100  Conditions optimales — entries techniques précises
  60-79   Bonnes conditions — signal fiable avec confirmation
  40-59   Conditions moyennes — attendre setup plus clair
  0-39    Bruit / structure cassée — éviter les entrées directionnelles

Régimes retournés :
    flat        ATR < 0.3 % — pas de momentum, range trop serré
    trending    R² ≥ 0.65 — tendance claire, trend-following efficace
    directional bougies propres (body_ratio ≥ 0.50) mais pas de tendance soutenue
    ranging     oscillation dans un range (body_ratio < 0.40, R² < 0.50)
    noisy       ATR élevé + bougies peu directionnelles — éviter
"""

from __future__ import annotations

import math
from typing import TypedDict

# Tier map — priorité de catégorie pour le tri (tier bas = plus prioritaire)
SYMBOL_TIERS: dict[str, int] = {
    # Tier 1 — Core majors
    "BTC/USDT": 1,
    "ETH/USDT": 1,
    "SOL/USDT": 1,
    "BNB/USDT": 1,
    "XRP/USDT": 1,
    "ADA/USDT": 1,
    "DOGE/USDT": 1,
    "TON/USDT": 1,
    # Tier 2 — L1/L2 infrastructure
    "AVAX/USDT": 2,
    "SUI/USDT": 2,
    "NEAR/USDT": 2,
    "APT/USDT": 2,
    "ARB/USDT": 2,
    "OP/USDT": 2,
    "ATOM/USDT": 2,
    "DOT/USDT": 2,
    "HBAR/USDT": 2,
    "FTM/USDT": 2,
    "SEI/USDT": 2,
    "STX/USDT": 2,
    # Tier 3 — DeFi / protocoles
    "LINK/USDT": 3,
    "AAVE/USDT": 3,
    "UNI/USDT": 3,
    "INJ/USDT": 3,
    "LDO/USDT": 3,
    "PENDLE/USDT": 3,
    "ENA/USDT": 3,
    "JUP/USDT": 3,
    "EIGEN/USDT": 3,
    "ONDO/USDT": 3,
    # Tier 4 — IA / narratives
    "TAO/USDT": 4,
    "FET/USDT": 4,
    "RENDER/USDT": 4,
    "WLD/USDT": 4,
    "PYTH/USDT": 4,
    "JTO/USDT": 4,
    "W/USDT": 4,
    "STRK/USDT": 4,
    # Tier 5 — Meme / high-beta
    "PEPE/USDT": 5,
    "WIF/USDT": 5,
    "BONK/USDT": 5,
    "FLOKI/USDT": 5,
    "SHIB/USDT": 5,
    "NEIRO/USDT": 5,
    "MEME/USDT": 5,
    "HYPE/USDT": 5,
    # Tier 6 — Stress / diversification
    "LTC/USDT": 6,
    "BCH/USDT": 6,
    "TIA/USDT": 6,
    "IMX/USDT": 6,
}


class SymbolStability(TypedDict):
    score: float  # 0-100 composite
    tier: int  # 1-6 (6 = inconnu)
    regime: str  # flat / trending / directional / ranging / noisy
    body_ratio: float  # 0-1, qualité directionnelle des bougies
    vol_cv: float  # coefficient variation volume (>0, bas = stable)
    atr_pct: float  # ATR% (pourcentage du prix)
    trend_r2: float  # 0-1, clarté de tendance (R²)
    n_candles: int  # nombre de bougies utilisées


def _atr_score(atr_pct: float) -> float:
    """Score 0-1 sur la plage ATR% idéale pour 1h. Optimum : 0.5-2%."""
    if atr_pct < 0.003:
        return 0.2  # trop flat
    if atr_pct < 0.005:
        return 0.2 + (atr_pct - 0.003) / 0.002 * 0.8  # montée rapide vers idéal
    if atr_pct <= 0.02:
        return 1.0  # fenêtre optimale
    if atr_pct <= 0.05:
        return 1.0 - (atr_pct - 0.02) / 0.03 * 0.8  # dégradation progressive
    return 0.1  # très erratique


def compute_stability(series: list[dict], symbol: str = "") -> SymbolStability:
    """
    Calcule le score de stabilité/tradabilité d'un symbole.

    Args:
        series:  liste de bougies OHLCV (champs open/high/low/close/volume)
        symbol:  symbole CCXT (ex : "BTC/USDT") pour lookup tier

    Returns:
        SymbolStability avec score 0-100 et métadonnées de marché.
    """
    n = len(series)
    if n < 5:
        return SymbolStability(
            score=0.0,
            tier=SYMBOL_TIERS.get(symbol, 6),
            regime="flat",
            body_ratio=0.0,
            vol_cv=1.0,
            atr_pct=0.0,
            trend_r2=0.0,
            n_candles=n,
        )

    # Utilise les 50 dernières bougies pour refléter les conditions actuelles
    window = series[-50:]
    nw = len(window)

    closes = [c["close"] for c in window]
    opens = [c["open"] for c in window]
    highs = [c["high"] for c in window]
    lows = [c["low"] for c in window]
    volumes = [c["volume"] for c in window]

    # ── 1. Body ratio ────────────────────────────────────────────────────────
    body_ratios: list[float] = []
    for i in range(nw):
        candle_range = highs[i] - lows[i]
        if candle_range > 0:
            body_ratios.append(abs(closes[i] - opens[i]) / candle_range)
    body_ratio = sum(body_ratios) / len(body_ratios) if body_ratios else 0.0

    # ── 2. Volume consistency (coefficient de variation) ─────────────────────
    vol_mean = sum(volumes) / nw
    if vol_mean > 0 and nw > 1:
        vol_variance = sum((v - vol_mean) ** 2 for v in volumes) / nw
        vol_cv = math.sqrt(vol_variance) / vol_mean
    else:
        vol_cv = 1.0

    # ── 3. ATR% normalisé (14 périodes ou fenêtre dispo) ────────────────────
    atr_period = min(14, nw - 1)
    true_ranges: list[float] = []
    for i in range(1, nw):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)
    if true_ranges and closes[-1] > 0:
        atr = sum(true_ranges[-atr_period:]) / atr_period
        atr_pct = atr / closes[-1]
    else:
        atr_pct = 0.0

    # ── 4. Trend clarity — R² régression linéaire sur clôtures ──────────────
    trend_r2 = 0.0
    if nw >= 10:
        x_mean = (nw - 1) / 2.0
        y_mean = sum(closes) / nw
        ss_xx = sum((i - x_mean) ** 2 for i in range(nw))
        ss_xy = sum((i - x_mean) * (closes[i] - y_mean) for i in range(nw))
        ss_yy = sum((c - y_mean) ** 2 for c in closes)
        if ss_xx > 0 and ss_yy > 0:
            trend_r2 = min(1.0, (ss_xy**2) / (ss_xx * ss_yy))

    # ── Score composite ──────────────────────────────────────────────────────
    vol_score = max(0.0, 1.0 - vol_cv / 2.0)  # CV=0 → 1.0 ; CV=2 → 0.0
    score = (
        body_ratio * 35.0
        + vol_score * 25.0
        + _atr_score(atr_pct) * 20.0
        + trend_r2 * 20.0
    )
    score = max(0.0, min(100.0, score))

    # ── Régime ───────────────────────────────────────────────────────────────
    if atr_pct < 0.003:
        regime = "flat"
    elif trend_r2 >= 0.65 and atr_pct >= 0.003:
        regime = "trending"
    elif atr_pct > 0.04 and body_ratio < 0.40:
        regime = "noisy"
    elif body_ratio >= 0.50:
        regime = "directional"
    else:
        regime = "ranging"

    return SymbolStability(
        score=round(score, 1),
        tier=SYMBOL_TIERS.get(symbol, 6),
        regime=regime,
        body_ratio=round(body_ratio, 3),
        vol_cv=round(vol_cv, 3),
        atr_pct=round(atr_pct * 100, 3),  # stocké en %, plus lisible
        trend_r2=round(trend_r2, 3),
        n_candles=nw,
    )


def sort_by_tradability(
    symbols: list[str],
    stability_map: dict[str, SymbolStability],
) -> list[str]:
    """
    Trie une liste de symboles du plus au moins tradable.

    Clé de tri : (score DESC, tier ASC).
    Les symboles absents de stability_map gardent leur ordre relatif.
    """

    def _key(sym: str) -> tuple[float, int]:
        st = stability_map.get(sym)
        if st is None:
            return (-50.0, 9)
        return (-st["score"], st["tier"])

    return sorted(symbols, key=_key)
