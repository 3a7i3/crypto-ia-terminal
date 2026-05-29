"""
risk_limits.py — Limites de risque absolues et immuables (P5.4).

Ces constantes NE PEUVENT PAS être overridées par des variables d'environnement.
Elles constituent le filet de sécurité final avant le capital réel.

Pour modifier ces limites, il faut modifier ce fichier ET faire une revue de code.
C'est intentionnel — une variable d'env peut être mal configurée, ces constantes non.

Hiérarchie des gardes :
  1. HARD LIMITS (ce fichier)  — jamais dépassées, peu importe le signal
  2. PortfolioBrain checks      — exposition, corrélation, concentration
  3. RateLimiter                — 10 ordres/s Binance
  4. OrderValidator             — LOT_SIZE, MIN_NOTIONAL, PERCENT_PRICE
  5. KillSwitch                 — safe mode si drawdown critique

Usage :
    from risk_limits import HARD_LIMITS, check_hard_limits, HardLimitBreached

    check_hard_limits(
        order_size_usd=150.0,
        capital_usd=10_000.0,
        current_drawdown_pct=-8.5,
        open_positions=2,
    )  # lève HardLimitBreached si une limite est franchie
"""

from __future__ import annotations

from dataclasses import dataclass

# ══════════════════════════════════════════════════════════════════════════════
# LIMITES ABSOLUES — NE PAS MODIFIER SANS REVUE DE CODE
# ══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class _HardLimits:
    """Constantes immuables. frozen=True interdit toute modification au runtime."""

    # Taille d'ordre
    MAX_ORDER_USD: float = 200.0  # jamais plus de $200 par ordre
    MAX_ORDER_PCT_CAPITAL: float = 5.0  # jamais plus de 5% du capital par ordre

    # Positions ouvertes simultanées
    MAX_OPEN_POSITIONS: int = 4  # max 4 positions en même temps

    # Drawdown
    MAX_DRAWDOWN_PCT: float = 20.0  # arrêt total si drawdown > 20%
    PAUSE_DRAWDOWN_PCT: float = 10.0  # pause trading si drawdown > 10%

    # Capital minimum
    MIN_CAPITAL_USD: float = 500.0  # refus d'opérer sous $500

    # Concentration par symbole
    MAX_SYMBOL_EXPOSURE_PCT: float = 15.0  # max 15% du capital sur un seul symbole

    # Levier
    MAX_LEVERAGE: int = 10  # jamais plus de 10x levier

    # Pertes consécutives
    MAX_CONSECUTIVE_LOSSES: int = 5  # pause forcée après 5 pertes consécutives


HARD_LIMITS = _HardLimits()


# ══════════════════════════════════════════════════════════════════════════════
# Vérification
# ══════════════════════════════════════════════════════════════════════════════


class HardLimitBreached(Exception):
    """Une limite absolue a été franchie — ordre refusé."""

    def __init__(self, limit: str, value: float, threshold: float) -> None:
        self.limit = limit
        self.value = value
        self.threshold = threshold
        super().__init__(
            f"HARD LIMIT '{limit}': valeur={value:.4g} > seuil={threshold:.4g} — ordre refusé"
        )


def check_hard_limits(
    order_size_usd: float,
    capital_usd: float,
    current_drawdown_pct: float,
    open_positions: int,
    consecutive_losses: int = 0,
    leverage: int = 1,
    symbol_exposure_usd: float = 0.0,
) -> None:
    """
    Vérifie toutes les limites absolues.

    Lève HardLimitBreached dès la première limite franchie.
    Appeler AVANT tout envoi d'ordre à l'exchange.

    Parameters
    ----------
    order_size_usd      : taille de l'ordre en USD
    capital_usd         : capital disponible actuel
    current_drawdown_pct: drawdown courant (négatif ou nul, ex: -8.5)
    open_positions      : nombre de positions actuellement ouvertes
    consecutive_losses  : nombre de pertes consécutives en cours
    leverage            : levier demandé pour cet ordre
    symbol_exposure_usd : exposition déjà ouverte sur ce symbole
    """
    L = HARD_LIMITS

    # Capital minimum
    if capital_usd < L.MIN_CAPITAL_USD:
        raise HardLimitBreached("MIN_CAPITAL_USD", capital_usd, L.MIN_CAPITAL_USD)

    # Taille absolue
    if order_size_usd > L.MAX_ORDER_USD:
        raise HardLimitBreached("MAX_ORDER_USD", order_size_usd, L.MAX_ORDER_USD)

    # Taille relative au capital
    order_pct = order_size_usd / capital_usd * 100.0
    if order_pct > L.MAX_ORDER_PCT_CAPITAL:
        raise HardLimitBreached(
            "MAX_ORDER_PCT_CAPITAL", order_pct, L.MAX_ORDER_PCT_CAPITAL
        )

    # Drawdown total — arrêt complet
    dd = abs(current_drawdown_pct)
    if dd >= L.MAX_DRAWDOWN_PCT:
        raise HardLimitBreached("MAX_DRAWDOWN_PCT", dd, L.MAX_DRAWDOWN_PCT)

    # Drawdown partiel — pause
    if dd >= L.PAUSE_DRAWDOWN_PCT:
        raise HardLimitBreached("PAUSE_DRAWDOWN_PCT", dd, L.PAUSE_DRAWDOWN_PCT)

    # Positions simultanées
    if open_positions >= L.MAX_OPEN_POSITIONS:
        raise HardLimitBreached(
            "MAX_OPEN_POSITIONS", float(open_positions), float(L.MAX_OPEN_POSITIONS)
        )

    # Levier
    if leverage > L.MAX_LEVERAGE:
        raise HardLimitBreached("MAX_LEVERAGE", float(leverage), float(L.MAX_LEVERAGE))

    # Concentration symbole
    total_symbol_exposure = symbol_exposure_usd + order_size_usd
    symbol_pct = total_symbol_exposure / capital_usd * 100.0
    if symbol_pct > L.MAX_SYMBOL_EXPOSURE_PCT:
        raise HardLimitBreached(
            "MAX_SYMBOL_EXPOSURE_PCT", symbol_pct, L.MAX_SYMBOL_EXPOSURE_PCT
        )

    # Pertes consécutives
    if consecutive_losses >= L.MAX_CONSECUTIVE_LOSSES:
        raise HardLimitBreached(
            "MAX_CONSECUTIVE_LOSSES",
            float(consecutive_losses),
            float(L.MAX_CONSECUTIVE_LOSSES),
        )


def limits_summary() -> dict:
    """Retourne les limites actives sous forme de dict (pour dashboard)."""
    L = HARD_LIMITS
    return {
        "max_order_usd": L.MAX_ORDER_USD,
        "max_order_pct_capital": L.MAX_ORDER_PCT_CAPITAL,
        "max_open_positions": L.MAX_OPEN_POSITIONS,
        "max_drawdown_pct": L.MAX_DRAWDOWN_PCT,
        "pause_drawdown_pct": L.PAUSE_DRAWDOWN_PCT,
        "min_capital_usd": L.MIN_CAPITAL_USD,
        "max_symbol_exposure_pct": L.MAX_SYMBOL_EXPOSURE_PCT,
        "max_leverage": L.MAX_LEVERAGE,
        "max_consecutive_losses": L.MAX_CONSECUTIVE_LOSSES,
    }
