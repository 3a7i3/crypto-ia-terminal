"""
metrics/stability_score.py — Score de stabilite inter-regimes.

Mesure la constance des performances OOS a travers differents regimes de marche
(bull, bear, stable, volatile).

Un score proche de 1 signifie : "les performances sont homogenes quel que soit
le regime" — la strategie ne depend pas d'un regime particulier.
Un score proche de 0 signifie : "la strategie excelle dans un regime et
s'effondre dans les autres" — fragile.

Methode :
  Coefficient de Variation du Sharpe = std(sharpes) / abs(mean(sharpes))
  Stability = 1 / (1 + CV)   → [0, 1]
  Min-ratio = min_sharpe / max(mean_sharpe, 1e-9)  → penalty si un regime est tres mauvais
  Score final = Stability * clip(1 + min_ratio, 0, 1.5) / 1.5
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Optional

from metrics.oos_metrics import OOSMetrics


@dataclass
class RegimeStability:
    """
    Resultat du calcul de stabilite inter-regimes.

    stability_score  : [0, 1] — plus c'est haut, plus la strategie est stable
    sharpe_cv        : coefficient de variation du Sharpe (0 = parfaitement stable)
    min_regime_sharpe: pire Sharpe observe parmi tous les regimes
    worst_regime     : nom du regime avec le pire Sharpe
    best_regime      : nom du regime avec le meilleur Sharpe
    regime_count     : nombre de regimes evalues
    """

    stability_score: float
    sharpe_cv: float
    min_regime_sharpe: float
    max_regime_sharpe: float
    mean_regime_sharpe: float
    worst_regime: str
    best_regime: str
    regime_count: int
    regime_metrics: dict[str, OOSMetrics] = field(repr=False)

    @property
    def is_regime_stable(self) -> bool:
        """True si le score depasse 0.6 et que le pire regime est profitable."""
        return self.stability_score >= 0.6 and self.min_regime_sharpe > 0.0

    def as_dict(self) -> dict:
        return {
            "stability_score": round(self.stability_score, 4),
            "sharpe_cv": round(self.sharpe_cv, 4),
            "min_regime_sharpe": round(self.min_regime_sharpe, 4),
            "max_regime_sharpe": round(self.max_regime_sharpe, 4),
            "mean_regime_sharpe": round(self.mean_regime_sharpe, 4),
            "worst_regime": self.worst_regime,
            "best_regime": self.best_regime,
            "regime_count": self.regime_count,
            "is_regime_stable": self.is_regime_stable,
        }


def compute_stability_score(
    regime_metrics: dict[str, OOSMetrics],
    min_trades_per_regime: int = 3,
) -> RegimeStability:
    """
    Calcule le score de stabilite a partir des metriques par regime.

    regime_metrics     : dict regime_name -> OOSMetrics (calcule sur le fold OOS)
    min_trades_per_regime : regimes avec moins de trades sont ignores du calcul

    Retourne un RegimeStability. Si moins de 2 regimes valides, stability_score=1.0
    (pas assez de donnees pour penaliser).
    """
    # Filtrer les regimes avec assez de trades
    valid = {
        r: m for r, m in regime_metrics.items() if m.n_trades >= min_trades_per_regime
    }

    if len(valid) < 2:
        # Un seul regime : pas de comparaison possible
        only_metrics = next(iter(regime_metrics.values())) if regime_metrics else None
        sharpe = only_metrics.sharpe_ratio if only_metrics else 0.0
        regime_name = next(iter(regime_metrics.keys())) if regime_metrics else "unknown"
        return RegimeStability(
            stability_score=1.0,
            sharpe_cv=0.0,
            min_regime_sharpe=sharpe,
            max_regime_sharpe=sharpe,
            mean_regime_sharpe=sharpe,
            worst_regime=regime_name,
            best_regime=regime_name,
            regime_count=len(regime_metrics),
            regime_metrics=regime_metrics,
        )

    sharpes = {r: m.sharpe_ratio for r, m in valid.items()}
    sharpe_values = list(sharpes.values())

    mean_sharpe = statistics.mean(sharpe_values)
    std_sharpe = statistics.stdev(sharpe_values) if len(sharpe_values) > 1 else 0.0

    # CV = std / abs(mean)  — infinite si mean = 0
    if abs(mean_sharpe) < 1e-9:
        cv = float("inf") if std_sharpe > 0 else 0.0
    else:
        cv = std_sharpe / abs(mean_sharpe)

    # Score de base
    stability = 1.0 / (1.0 + cv) if math.isfinite(cv) else 0.0

    # Penalite si le pire regime est tres negatif relativement au meilleur
    min_sharpe = min(sharpe_values)
    max_sharpe = max(sharpe_values)
    worst = min(sharpes, key=sharpes.__getitem__)
    best = max(sharpes, key=sharpes.__getitem__)

    # Ajustement : si un regime est negatif, on penalise proportionnellement
    if min_sharpe < 0 and max_sharpe > 0:
        # Ratio = min / max  ∈ [-inf, 0) : pire le ratio, plus la penalite
        ratio = min_sharpe / max(max_sharpe, 1e-9)
        # clip ratio entre -1 et 0 pour la penalite
        penalty = max(-1.0, ratio)  # penalty ∈ [-1, 0]
        stability = stability * (1.0 + penalty * 0.5)  # reduce by up to 50%

    stability = max(0.0, min(1.0, stability))

    return RegimeStability(
        stability_score=stability,
        sharpe_cv=cv if math.isfinite(cv) else 999.0,
        min_regime_sharpe=min_sharpe,
        max_regime_sharpe=max_sharpe,
        mean_regime_sharpe=mean_sharpe,
        worst_regime=worst,
        best_regime=best,
        regime_count=len(valid),
        regime_metrics=regime_metrics,
    )
