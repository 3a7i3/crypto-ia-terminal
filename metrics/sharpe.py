"""Canonical Sharpe ratio primitive — source unique pour tout le repo.

Toute nouvelle implementation doit utiliser cette fonction. Les sites qui
recalculent Sharpe inline sont progressivement migres pour deleguer ici.
Voir le PR d'unification pour l'audit complet des divergences historiques.

Convention (fixe) :
- ddof=1 (sample stdev, comme numpy.std(bias=False) et pandas)
- RF divise par periods_per_year AVANT soustraction au mean
  (excess-return periodique, forme academique standard)
- Annualisation via * sqrt(periods_per_year)
- Retourne 0.0 (jamais None) quand donnees insuffisantes ou dispersion nulle
"""
from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

__all__ = ["sharpe"]


def sharpe(
    returns: Sequence[float],
    *,
    rf_annual: float = 0.0,
    periods_per_year: float = 252.0,
) -> float:
    """Ratio de Sharpe annualise.

    Args:
        returns: Serie de rendements periodiques bruts. Passer les rendements
            eux-memes, PAS des excess-returns (la fonction soustrait rf).
        rf_annual: Taux sans risque annuel (ex. 0.02 pour 2%). Default 0.
        periods_per_year: Nombre de periodes par an pour l'annualisation.
            Conventions typiques : 252 (daily), 8760 (hourly), 12 (monthly),
            1 (per-trade sans annualisation). Default 252.

    Returns:
        Sharpe annualise (float). Retourne 0.0 (jamais None) quand :
            - len(returns) < 2 (echantillon insuffisant pour stdev)
            - stdev <= 0 (aucune dispersion, degenere)
    """
    if len(returns) < 2:
        return 0.0
    mu = statistics.mean(returns)
    sigma = statistics.stdev(returns)
    if sigma <= 0:
        return 0.0
    return (mu - rf_annual / periods_per_year) / sigma * math.sqrt(periods_per_year)
