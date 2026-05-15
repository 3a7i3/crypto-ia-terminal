"""
market_data/metrics/orderbook.py — Metriques statiques du carnet d'ordres.

Toutes les fonctions sont pures (pas d'etat, entree = NormalizedOrderBook).
Utiles pour calculer un vecteur de features a chaque snapshot.

Metriques :
  imbalance(book, levels)        -> [-1, +1] desequilibre buy/sell
  weighted_mid(book, levels)     -> prix mid pondere par les volumes
  spread_metrics(book)           -> spread absolu, bps, relatif
  depth_profile(book, levels)    -> volumes cumulatifs par cote
  wall_detection(book, z_thresh) -> niveaux anormalement grands (murs)
  book_pressure(book, pct_range) -> volume dans les X% autour du mid
  skew(book, levels)             -> ratio asymetrique bid/ask (>1 = bid dominant)
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Optional

from market_data.models import NormalizedOrderBook


@dataclass
class SpreadMetrics:
    absolute: float  # ask - bid
    bps: float  # spread / bid * 10000
    mid: float  # (bid + ask) / 2
    weighted_mid: float  # mid pondere par volumes


@dataclass
class WallLevel:
    side: str  # "bid" | "ask"
    price: float
    size_usd: float
    z_score: float  # combien d'ecarts-types au-dessus de la moyenne


@dataclass
class DepthProfile:
    bid_volumes: list[float]  # volume cumulatif USDT par niveau (bid)
    ask_volumes: list[float]  # volume cumulatif USDT par niveau (ask)
    total_bid_usd: float
    total_ask_usd: float
    imbalance: float  # (bid - ask) / (bid + ask)


def imbalance(book: NormalizedOrderBook, levels: int = 5) -> float:
    """
    Desequilibre du carnet : (bid_depth - ask_depth) / (bid_depth + ask_depth).
    Range [-1, +1] : +1 = acheteurs dominant, -1 = vendeurs dominant.
    """
    return book.imbalance(levels)


def weighted_mid(book: NormalizedOrderBook, levels: int = 5) -> Optional[float]:
    """
    Prix mid pondere par les volumes (meilleur estimateur du "fair value").
    Formule : (sum(bid_p * bid_s) + sum(ask_p * ask_s)) / (sum(bid_s) + sum(ask_s))
    """
    total_s = 0.0
    total_ps = 0.0
    for p, s in book.bids[:levels]:
        total_s += s
        total_ps += p * s
    for p, s in book.asks[:levels]:
        total_s += s
        total_ps += p * s
    if total_s == 0:
        return book.mid_price
    return total_ps / total_s


def spread_metrics(book: NormalizedOrderBook) -> Optional[SpreadMetrics]:
    """Calcule les metriques de spread."""
    if not book.best_bid or not book.best_ask:
        return None
    mid = (book.best_bid + book.best_ask) / 2.0
    w_mid = weighted_mid(book, levels=3) or mid
    return SpreadMetrics(
        absolute=book.best_ask - book.best_bid,
        bps=book.spread_bps or 0.0,
        mid=mid,
        weighted_mid=w_mid,
    )


def depth_profile(book: NormalizedOrderBook, levels: int = 10) -> DepthProfile:
    """Volume USDT cumulatif par niveau de chaque cote."""
    bid_vols = []
    ask_vols = []
    cumul = 0.0
    for p, s in book.bids[:levels]:
        cumul += p * s
        bid_vols.append(cumul)
    cumul = 0.0
    for p, s in book.asks[:levels]:
        cumul += p * s
        ask_vols.append(cumul)
    total_b = bid_vols[-1] if bid_vols else 0.0
    total_a = ask_vols[-1] if ask_vols else 0.0
    total = total_b + total_a
    imb = (total_b - total_a) / total if total > 0 else 0.0
    return DepthProfile(
        bid_volumes=bid_vols,
        ask_volumes=ask_vols,
        total_bid_usd=total_b,
        total_ask_usd=total_a,
        imbalance=imb,
    )


def wall_detection(
    book: NormalizedOrderBook,
    levels: int = 20,
    z_thresh: float = 2.0,
) -> list[WallLevel]:
    """
    Detecte les niveaux anormalement grands (murs potentiels).
    Un mur = niveau dont le volume est > moyenne + z_thresh * ecart-type.

    Utile pour detecter :
      - spoofing (murs qui disparaissent rapidement)
      - vraies zones de support/resistance liquides
    """
    all_levels = [("bid", p, p * s) for p, s in book.bids[:levels]] + [
        ("ask", p, p * s) for p, s in book.asks[:levels]
    ]
    if len(all_levels) < 3:
        return []

    usd_vols = [v for _, _, v in all_levels]
    mean = statistics.mean(usd_vols)
    stdev = statistics.stdev(usd_vols) if len(usd_vols) > 1 else 1.0
    if stdev == 0:
        return []

    walls = []
    for side, price, vol_usd in all_levels:
        z = (vol_usd - mean) / stdev
        if z >= z_thresh:
            walls.append(WallLevel(side=side, price=price, size_usd=vol_usd, z_score=z))
    walls.sort(key=lambda w: w.z_score, reverse=True)
    return walls


def book_pressure(
    book: NormalizedOrderBook,
    pct_range: float = 0.5,
) -> dict[str, float]:
    """
    Volume en USDT dans les X% autour du mid price.
    pct_range=0.5 -> considera les niveaux a moins de 0.5% du mid.

    Retourne {"bid_usd": ..., "ask_usd": ..., "imbalance": ...}
    Utile pour mesurer la "pression immediate" sur le prix courant.
    """
    mid = book.mid_price
    if not mid:
        return {"bid_usd": 0.0, "ask_usd": 0.0, "imbalance": 0.0}

    threshold = mid * pct_range / 100.0
    bid_usd = sum(p * s for p, s in book.bids if p >= mid - threshold)
    ask_usd = sum(p * s for p, s in book.asks if p <= mid + threshold)
    total = bid_usd + ask_usd
    imb = (bid_usd - ask_usd) / total if total > 0 else 0.0
    return {"bid_usd": bid_usd, "ask_usd": ask_usd, "imbalance": imb}


def skew(book: NormalizedOrderBook, levels: int = 5) -> float:
    """
    Ratio bid_depth / ask_depth.
    >1.0 : bid dominant (acheteurs), <1.0 : ask dominant (vendeurs).
    """
    b = book.bid_depth(levels)
    a = book.ask_depth(levels)
    if a == 0:
        return float("inf") if b > 0 else 1.0
    return b / a


def features_vector(book: NormalizedOrderBook) -> dict[str, float]:
    """
    Vecteur de features complet du book pour le ML.
    Retourne un dict de floats directement utilisables comme features.
    """
    sp = spread_metrics(book)
    dp5 = depth_profile(book, 5)
    dp10 = depth_profile(book, 10)
    pr = book_pressure(book, 0.5)
    walls = wall_detection(book, 20, 2.0)

    return {
        "imbalance_5": imbalance(book, 5),
        "imbalance_10": imbalance(book, 10),
        "skew_5": skew(book, 5),
        "spread_bps": book.spread_bps or 0.0,
        "weighted_mid": weighted_mid(book, 5) or 0.0,
        "bid_depth_5_usd": dp5.total_bid_usd,
        "ask_depth_5_usd": dp5.total_ask_usd,
        "bid_depth_10_usd": dp10.total_bid_usd,
        "ask_depth_10_usd": dp10.total_ask_usd,
        "pressure_imbal": pr["imbalance"],
        "pressure_bid_usd": pr["bid_usd"],
        "pressure_ask_usd": pr["ask_usd"],
        "n_walls": float(len(walls)),
        "max_wall_z": walls[0].z_score if walls else 0.0,
    }
