"""
trade_analysis/market_state.py — Classification de l'etat structurel du marche.

Synthetise les 3 dimensions (flow, liquidity, resistance) en un
etat lisible par l'humain :

  ACCUMULATION   : pression buy + forte absorption + prix stable
  DISTRIBUTION   : pression sell + forte absorption + prix stable
  ABSORPTION_BUY : acheteurs absorbes par vendeurs solides
  ABSORPTION_SELL: vendeurs absorbes par acheteurs solides
  FRAGILITY_UP   : faible resistance + pression haussiere
  FRAGILITY_DOWN : faible resistance + pression baissiere
  COMPRESSION    : forces opposees, range etroit
  EXPANSION      : mouvement rapide avec volume
  EXHAUSTION_BUY : pression acheteuse en declin
  EXHAUSTION_SELL: pression vendeuse en declin
  VACUUM_UP      : pas de resistance sell, liquidite vide au-dessus
  VACUUM_DOWN    : pas de resistance buy, liquidite vide en-dessous
  CONFLICT       : forces massives des deux cotes
  QUIET          : peu d'activite

Strictement passif (ADR-0007).
"""

from __future__ import annotations

from trade_analysis.models import (
    AggressiveFlow,
    LiquidityDynamics,
    MarketResistance,
    MarketStateLabel,
)


def classify_state(
    flow: AggressiveFlow,
    liquidity: LiquidityDynamics,
    resistance: MarketResistance,
    price_change_bps: float,
) -> tuple[MarketStateLabel, float, dict]:
    """
    Classifie l'etat du marche a partir des 3 dimensions.

    Returns :
        (label, confidence, components)
        components = dict des scores intermediaires pour audit.
    """
    scores: dict[MarketStateLabel, float] = {}
    components: dict[str, float] = {}

    pr = flow.pressure_ratio
    buy_accel = flow.buy_acceleration
    sell_accel = flow.sell_acceleration
    total_vol = flow.total_volume_usd

    absorption = resistance.absorption_ratio
    fragility = resistance.fragility_score
    disp_bps = resistance.price_displacement_bps

    canc_bid = liquidity.cancellation_rate_bid
    canc_ask = liquidity.cancellation_rate_ask
    ask_removed = liquidity.ask_removed_usd
    bid_removed = liquidity.bid_removed_usd

    components["pressure_ratio"] = pr
    components["absorption"] = absorption
    components["fragility"] = fragility
    components["displacement_bps"] = disp_bps
    components["canc_bid"] = canc_bid
    components["canc_ask"] = canc_ask

    is_quiet = total_vol < 5_000.0
    if is_quiet:
        scores[MarketStateLabel.QUIET] = 0.9
        best = max(scores, key=scores.get)
        return best, scores[best], components

    # --- ACCUMULATION: buy pressure + absorption + stable price ---
    if pr > 0.55 and absorption > 0.5 and abs(price_change_bps) < 10:
        s = min(pr, absorption) * 0.8
        if canc_ask > 0.3:
            s *= 0.7
        scores[MarketStateLabel.ACCUMULATION] = s

    # --- DISTRIBUTION: sell pressure + absorption + stable price ---
    if pr < 0.45 and absorption > 0.5 and abs(price_change_bps) < 10:
        s = min(1.0 - pr, absorption) * 0.8
        if canc_bid > 0.3:
            s *= 0.7
        scores[MarketStateLabel.DISTRIBUTION] = s

    # --- ABSORPTION_BUY: buyers being absorbed by strong sellers ---
    if pr > 0.55 and absorption > 0.6 and disp_bps < 3:
        scores[MarketStateLabel.ABSORPTION_BUY] = absorption * pr

    # --- ABSORPTION_SELL: sellers being absorbed by strong buyers ---
    if pr < 0.45 and absorption > 0.6 and disp_bps < 3:
        scores[MarketStateLabel.ABSORPTION_SELL] = absorption * (1.0 - pr)

    # --- FRAGILITY_UP: low resistance + buy pressure ---
    if fragility > 0.6 and pr > 0.55 and price_change_bps > 5:
        scores[MarketStateLabel.FRAGILITY_UP] = fragility * pr

    # --- FRAGILITY_DOWN: low resistance + sell pressure ---
    if fragility > 0.6 and pr < 0.45 and price_change_bps < -5:
        scores[MarketStateLabel.FRAGILITY_DOWN] = fragility * (1.0 - pr)

    # --- COMPRESSION: both sides active, tight range ---
    if 0.4 < pr < 0.6 and abs(price_change_bps) < 5 and total_vol > 20_000:
        s = (1.0 - abs(pr - 0.5) * 4) * (1.0 - min(abs(price_change_bps) / 5, 1.0))
        scores[MarketStateLabel.COMPRESSION] = max(s, 0.0)

    # --- EXPANSION: large displacement with volume ---
    if abs(price_change_bps) > 15 and total_vol > 30_000:
        s = min(abs(price_change_bps) / 50, 1.0) * min(total_vol / 100_000, 1.0)
        scores[MarketStateLabel.EXPANSION] = s

    # --- EXHAUSTION_BUY: buy pressure declining ---
    if buy_accel < -100 and pr > 0.5:
        s = min(abs(buy_accel) / 500, 1.0) * 0.7
        scores[MarketStateLabel.EXHAUSTION_BUY] = s

    # --- EXHAUSTION_SELL: sell pressure declining ---
    if sell_accel < -100 and pr < 0.5:
        s = min(abs(sell_accel) / 500, 1.0) * 0.7
        scores[MarketStateLabel.EXHAUSTION_SELL] = s

    # --- VACUUM_UP: ask liquidity disappearing ---
    if ask_removed > 50_000 and canc_ask > 0.6 and pr > 0.5:
        scores[MarketStateLabel.VACUUM_UP] = canc_ask * pr

    # --- VACUUM_DOWN: bid liquidity disappearing ---
    if bid_removed > 50_000 and canc_bid > 0.6 and pr < 0.5:
        scores[MarketStateLabel.VACUUM_DOWN] = canc_bid * (1.0 - pr)

    # --- CONFLICT: strong forces on both sides ---
    if (
        0.4 < pr < 0.6
        and total_vol > 50_000
        and flow.large_buy_count > 0
        and flow.large_sell_count > 0
    ):
        s = min(total_vol / 200_000, 1.0) * (1.0 - abs(pr - 0.5) * 4)
        scores[MarketStateLabel.CONFLICT] = max(s, 0.0)

    if not scores:
        scores[MarketStateLabel.QUIET] = 0.3

    best = max(scores, key=scores.get)
    confidence = scores[best]

    return best, min(confidence, 1.0), components
