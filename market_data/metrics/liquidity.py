"""
market_data/metrics/liquidity.py — Indicateur unique de liquidite (LiquidityScore).

Composite pur, sans etat, calcule uniquement a partir d'un
NormalizedOrderBook. Aucune influence sur les decisions de trading
(ADR-0007) : cet indicateur est un observateur strictement passif,
utilisable pour la telemetrie, le monitoring et le tableau de bord.

Formule
-------
Score = 100 * (
    w_tight * tightness(spread_bps)
  + w_depth * depth(usd within +/- pct of mid)
  + w_resil * resilience(slippage_bps @ notional)
  + w_bal   * balance(imbalance)
)

Chaque sous-metrique est bornee dans [0, 1] :
  tightness  = exp(-spread_bps / K_TIGHT)               (spread serre = 1)
  depth      = min(depth_usd / DEPTH_REF_USD, 1)         (book epais = 1)
  resilience = 1 / (1 + slippage_bps / K_RESIL)          (peu d'impact = 1)
  balance    = 1 - min(|imbalance|, 1)                   (equilibre = 1)

Tier
----
>= 80 : excellent  |  60-80 : healthy   |  40-60 : thin
20-40 : fragile    |  < 20  : toxic

Les constantes par defaut correspondent a un book perp USDT liquide
(BTC/ETH major). Elles sont ajustables via LiquidityConfig, jamais
codees en dur dans une couche decisionnelle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Optional

from market_data.models import NormalizedOrderBook

Tier = Literal["excellent", "healthy", "thin", "fragile", "toxic", "empty"]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiquidityConfig:
    """Parametres du score. Ajustables mais jamais utilises par un decideur."""

    # Poids de la moyenne composite (somme = 1.0)
    w_tightness: float = 0.30
    w_depth: float = 0.30
    w_resilience: float = 0.30
    w_balance: float = 0.10

    # Normalisation des sous-metriques
    k_tight_bps: float = 20.0           # spread ou tightness ~= 0.37
    depth_pct: float = 0.5              # depth mesuree +/- 0.5% du mid
    depth_ref_usd: float = 500_000.0    # depth cible pour saturer a 1.0
    k_resil_bps: float = 50.0           # slippage ou resilience = 0.5
    slippage_notional_usd: float = 10_000.0  # notionnel test pour slippage
    imbalance_levels: int = 5

    def __post_init__(self) -> None:
        total = self.w_tightness + self.w_depth + self.w_resilience + self.w_balance
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(
                f"LiquidityConfig: la somme des poids doit valoir 1.0 (obtenu {total:.4f})"
            )


DEFAULT_CONFIG = LiquidityConfig()


# ---------------------------------------------------------------------------
# Sortie
# ---------------------------------------------------------------------------


@dataclass
class LiquiditySnapshot:
    """Instantane complet, serialisable en JSON."""

    exchange: str
    symbol: str
    timestamp_ms: int

    # Sous-metriques brutes
    spread_bps: float
    depth_usd: float          # bid+ask $ dans +/- depth_pct% du mid
    bid_depth_usd: float
    ask_depth_usd: float
    slippage_buy_bps: float   # cout d'achat de slippage_notional_usd
    slippage_sell_bps: float  # cout de vente de slippage_notional_usd
    imbalance: float          # imbalance sur imbalance_levels premiers niveaux

    # Sous-scores normalises [0, 1]
    tightness: float
    depth: float
    resilience: float
    balance: float

    # Composite
    score: float              # 0..100
    tier: Tier
    filled_buy: bool          # True si le notional test a ete entierement absorbe
    filled_sell: bool

    config: LiquidityConfig = field(repr=False)

    def as_dict(self) -> dict:
        import dataclasses

        d = dataclasses.asdict(self)
        # config compact pour eviter le bruit dans les logs
        d["config"] = {
            "depth_pct": self.config.depth_pct,
            "depth_ref_usd": self.config.depth_ref_usd,
            "slippage_notional_usd": self.config.slippage_notional_usd,
            "k_tight_bps": self.config.k_tight_bps,
            "k_resil_bps": self.config.k_resil_bps,
        }
        return d


# ---------------------------------------------------------------------------
# Sous-metriques
# ---------------------------------------------------------------------------


def _slippage_bps(
    levels: list[tuple[float, float]],
    mid: float,
    notional_usd: float,
    side: str,
) -> tuple[float, bool]:
    """
    Cout de slippage pour consommer `notional_usd` a `side` ("buy"/"sell").

    `levels` doivent etre tries dans le sens de consommation :
      buy  -> asks croissants
      sell -> bids decroissants

    Retourne (slippage_bps signe positif, filled).
    Si le book est trop mince pour couvrir le notional, on rend le cout
    marginal sur ce qui a ete rempli et filled=False.
    """
    if mid <= 0 or notional_usd <= 0 or not levels:
        return math.inf, False

    remaining_usd = notional_usd
    consumed_usd = 0.0
    base_total = 0.0

    for price, size in levels:
        if price <= 0 or size <= 0:
            continue
        level_usd = price * size
        take_usd = min(level_usd, remaining_usd)
        base_total += take_usd / price
        consumed_usd += take_usd
        remaining_usd -= take_usd
        if remaining_usd <= 1e-9:
            break

    if consumed_usd <= 0 or base_total <= 0:
        return math.inf, False

    avg_fill_price = consumed_usd / base_total
    if side == "buy":
        # on paie plus cher que le mid -> slippage positif
        slip = (avg_fill_price - mid) / mid * 10_000.0
    else:
        # on vend moins cher que le mid
        slip = (mid - avg_fill_price) / mid * 10_000.0

    filled = remaining_usd <= 1e-6
    return max(slip, 0.0), filled


def _depth_within_pct(
    book: NormalizedOrderBook, pct: float
) -> tuple[float, float]:
    """Volume USD sur bids et asks a moins de `pct`% du mid."""
    mid = book.mid_price
    if not mid or mid <= 0:
        return 0.0, 0.0
    band = mid * pct / 100.0
    bid_usd = sum(p * s for p, s in book.bids if p >= mid - band)
    ask_usd = sum(p * s for p, s in book.asks if p <= mid + band)
    return bid_usd, ask_usd


# ---------------------------------------------------------------------------
# Score composite
# ---------------------------------------------------------------------------


def _tier(score: float) -> Tier:
    if score >= 80:
        return "excellent"
    if score >= 60:
        return "healthy"
    if score >= 40:
        return "thin"
    if score >= 20:
        return "fragile"
    return "toxic"


def _empty_snapshot(
    book: NormalizedOrderBook, cfg: LiquidityConfig
) -> LiquiditySnapshot:
    return LiquiditySnapshot(
        exchange=book.exchange,
        symbol=book.symbol,
        timestamp_ms=book.timestamp_ms,
        spread_bps=math.inf,
        depth_usd=0.0,
        bid_depth_usd=0.0,
        ask_depth_usd=0.0,
        slippage_buy_bps=math.inf,
        slippage_sell_bps=math.inf,
        imbalance=0.0,
        tightness=0.0,
        depth=0.0,
        resilience=0.0,
        balance=0.0,
        score=0.0,
        tier="empty",
        filled_buy=False,
        filled_sell=False,
        config=cfg,
    )


def liquidity_score(
    book: NormalizedOrderBook,
    config: Optional[LiquidityConfig] = None,
) -> LiquiditySnapshot:
    """
    Calcule l'indicateur unique de liquidite pour un snapshot de carnet.

    Fonction pure : entree = book, sortie = LiquiditySnapshot.
    Ne persiste rien, ne declenche rien.
    """
    cfg = config or DEFAULT_CONFIG

    mid = book.mid_price
    spread_bps = book.spread_bps
    if mid is None or spread_bps is None or spread_bps < 0:
        return _empty_snapshot(book, cfg)

    bid_usd, ask_usd = _depth_within_pct(book, cfg.depth_pct)
    depth_usd = bid_usd + ask_usd

    slip_buy, filled_buy = _slippage_bps(
        book.asks, mid, cfg.slippage_notional_usd, "buy"
    )
    slip_sell, filled_sell = _slippage_bps(
        book.bids, mid, cfg.slippage_notional_usd, "sell"
    )

    imb = book.imbalance(cfg.imbalance_levels)

    tightness = math.exp(-max(spread_bps, 0.0) / max(cfg.k_tight_bps, 1e-9))
    depth = min(depth_usd / max(cfg.depth_ref_usd, 1e-9), 1.0)
    # penalise le pire cote — un book asymetrique dans un sens n'est pas liquide dans l'autre
    worst_slip = max(slip_buy, slip_sell)
    resilience = 1.0 / (1.0 + worst_slip / max(cfg.k_resil_bps, 1e-9))
    balance = 1.0 - min(abs(imb), 1.0)

    # Books trop minces pour absorber le notionnel test -> plafond resilience
    if not (filled_buy and filled_sell):
        resilience = min(resilience, 0.15)

    score = 100.0 * (
        cfg.w_tightness * tightness
        + cfg.w_depth * depth
        + cfg.w_resilience * resilience
        + cfg.w_balance * balance
    )
    score = max(0.0, min(100.0, score))

    return LiquiditySnapshot(
        exchange=book.exchange,
        symbol=book.symbol,
        timestamp_ms=book.timestamp_ms,
        spread_bps=spread_bps,
        depth_usd=depth_usd,
        bid_depth_usd=bid_usd,
        ask_depth_usd=ask_usd,
        slippage_buy_bps=slip_buy,
        slippage_sell_bps=slip_sell,
        imbalance=imb,
        tightness=tightness,
        depth=depth,
        resilience=resilience,
        balance=balance,
        score=score,
        tier=_tier(score),
        filled_buy=filled_buy,
        filled_sell=filled_sell,
        config=cfg,
    )
