"""
monitor/degradation_tracker.py — Detection precoce de degradation de performance OOS.

Deux methodes complementaires :
  1. Z-score glissant  : compare la performance recente (window folds) a la baseline
     (tous les folds precedents). Alert si z < threshold.
  2. Test de Mann-Kendall : detecte une tendance monotone declinante sur toute la serie.
     Non-parametrique — robuste aux distributions non-normales.

Niveaux de severite :
  "warning"  : signal faible, surveiller (z < -1.5 ou p_value < 0.15)
  "critical" : degradation probable, envisager d'arreter la strategie
               (z < -2.5 ou trend p_value < 0.05 + win_rate < floor)

Usage :
    tracker = DegradationTracker(window=5)
    for fold_idx, metrics in enumerate(oos_results):
        events = tracker.record(fold_idx, metrics)
        for e in events:
            print(e.severity, e.message)

    if tracker.is_degrading:
        print("Strategie en degradation — stopper ou recalibrer")
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Optional

from metrics.oos_metrics import OOSMetrics

# ---------------------------------------------------------------------------
# Statistiques non-parametriques
# ---------------------------------------------------------------------------


def _norm_cdf(z: float) -> float:
    """CDF de la loi normale standard via math.erfc (sans scipy)."""
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def _mann_kendall(data: list[float]) -> tuple[float, float]:
    """
    Test de Mann-Kendall sur une serie temporelle.

    Retourne (tau, p_value) ou :
      tau ∈ [-1, 1]  — negatif = tendance declinante
      p_value ∈ [0, 1] — p_value < 0.05 → tendance significative

    Requiert au moins 3 points (retourne (0.0, 1.0) sinon).
    """
    n = len(data)
    if n < 3:
        return 0.0, 1.0

    # Statistique S
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            diff = data[j] - data[i]
            if diff > 0:
                s += 1
            elif diff < 0:
                s -= 1

    # Variance (formule exacte, sans ties)
    var_s = n * (n - 1) * (2 * n + 5) / 18.0

    # Statistique Z normalisee (correction de continuite)
    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0

    # p-value bilateral
    p_value = 2.0 * (1.0 - _norm_cdf(abs(z)))

    # Tau de Kendall normalise
    n_pairs = n * (n - 1) / 2.0
    tau = s / n_pairs if n_pairs > 0 else 0.0

    return tau, p_value


# ---------------------------------------------------------------------------
# DegradationEvent
# ---------------------------------------------------------------------------


@dataclass
class DegradationEvent:
    """
    Alerte de degradation emise par DegradationTracker.

    metric          : metrique concernee ("sharpe" | "win_rate" | "drawdown")
    severity        : "warning" | "critical"
    current_value   : valeur du fold courant
    baseline_value  : moyenne de reference (folds precedents)
    z_score         : ecart en nombre d'ecarts-types (negatif = sous la baseline)
    trend_tau       : tau Mann-Kendall (negatif = tendance declinante)
    trend_p_value   : p-value du test MK (< 0.05 = tendance significative)
    """

    detected_at_fold: int
    metric: str
    severity: str
    current_value: float
    baseline_value: float
    z_score: float
    trend_tau: float
    trend_p_value: float
    message: str

    def as_dict(self) -> dict:
        return {
            "detected_at_fold": self.detected_at_fold,
            "metric": self.metric,
            "severity": self.severity,
            "current_value": round(self.current_value, 4),
            "baseline_value": round(self.baseline_value, 4),
            "z_score": round(self.z_score, 4),
            "trend_tau": round(self.trend_tau, 4),
            "trend_p_value": round(self.trend_p_value, 4),
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# DegradationTracker
# ---------------------------------------------------------------------------


class DegradationTracker:
    """
    Surveille la stabilite des performances OOS fold par fold.

    Parametres :
      window               : nombre de folds recents pour le z-score glissant
      sharpe_z_warning     : seuil z-score pour un warning Sharpe (ex : -1.5)
      sharpe_z_critical    : seuil z-score pour un critical Sharpe (ex : -2.5)
      winrate_floor        : win rate minimum en-dessous duquel → warning (ex : 0.35)
      winrate_floor_crit   : win rate minimum critique (ex : 0.25)
      mk_alpha_warning     : seuil p-value Mann-Kendall pour warning (ex : 0.15)
      mk_alpha_critical    : seuil p-value Mann-Kendall pour critical (ex : 0.05)
    """

    def __init__(
        self,
        window: int = 5,
        sharpe_z_warning: float = -1.5,
        sharpe_z_critical: float = -2.5,
        winrate_floor: float = 0.35,
        winrate_floor_crit: float = 0.25,
        mk_alpha_warning: float = 0.15,
        mk_alpha_critical: float = 0.05,
    ) -> None:
        self.window = window
        self.sharpe_z_warning = sharpe_z_warning
        self.sharpe_z_critical = sharpe_z_critical
        self.winrate_floor = winrate_floor
        self.winrate_floor_crit = winrate_floor_crit
        self.mk_alpha_warning = mk_alpha_warning
        self.mk_alpha_critical = mk_alpha_critical

        self._history: list[OOSMetrics] = []
        self._all_events: list[DegradationEvent] = []

    # ------------------------------------------------------------------

    def record(self, fold_index: int, metrics: OOSMetrics) -> list[DegradationEvent]:
        """
        Enregistre les metriques du fold et retourne les evenements de degradation
        detectes (liste vide si tout va bien).
        """
        self._history.append(metrics)
        events: list[DegradationEvent] = []

        n = len(self._history)
        if n < 3:
            return events  # pas assez de donnees pour analyser

        sharpes = [m.sharpe_ratio for m in self._history]
        winrates = [m.win_rate for m in self._history]

        # --- Z-score glissant (Sharpe) ---
        baseline_sharpes = sharpes[:-1]  # tous sauf le dernier
        if len(baseline_sharpes) >= 2:
            baseline_mean = statistics.mean(baseline_sharpes)
            baseline_std = statistics.stdev(baseline_sharpes)
            current = sharpes[-1]
            if baseline_std > 0:
                z = (current - baseline_mean) / baseline_std
            elif current < baseline_mean:
                # std=0 mais chute reelle : z proportionnel a l'ecart absolu
                z = (current - baseline_mean) / max(abs(baseline_mean), 0.1)
            else:
                z = 0.0
            if z != 0.0:
                sev = None
                if z <= self.sharpe_z_critical:
                    sev = "critical"
                elif z <= self.sharpe_z_warning:
                    sev = "warning"
                if sev:
                    ev = DegradationEvent(
                        detected_at_fold=fold_index,
                        metric="sharpe",
                        severity=sev,
                        current_value=sharpes[-1],
                        baseline_value=baseline_mean,
                        z_score=z,
                        trend_tau=0.0,
                        trend_p_value=1.0,
                        message=(
                            f"Sharpe {sev}: fold {fold_index} Sharpe={sharpes[-1]:.3f} "
                            f"est {abs(z):.1f}σ sous la baseline ({baseline_mean:.3f})"
                        ),
                    )
                    events.append(ev)

        # --- Mann-Kendall sur Sharpe ---
        tau, p_val = _mann_kendall(sharpes)
        if tau < 0:  # tendance declinante
            sev = None
            if p_val <= self.mk_alpha_critical:
                sev = "critical"
            elif p_val <= self.mk_alpha_warning:
                sev = "warning"
            if sev:
                ev = DegradationEvent(
                    detected_at_fold=fold_index,
                    metric="sharpe_trend",
                    severity=sev,
                    current_value=sharpes[-1],
                    baseline_value=statistics.mean(sharpes[:-1]),
                    z_score=0.0,
                    trend_tau=tau,
                    trend_p_value=p_val,
                    message=(
                        f"Tendance Sharpe declinante {sev} "
                        f"(tau={tau:.3f}, p={p_val:.3f}) sur {n} folds"
                    ),
                )
                events.append(ev)

        # --- Win rate floor ---
        current_wr = winrates[-1]
        if current_wr < self.winrate_floor_crit:
            sev = "critical"
        elif current_wr < self.winrate_floor:
            sev = "warning"
        else:
            sev = None
        if sev:
            ev = DegradationEvent(
                detected_at_fold=fold_index,
                metric="win_rate",
                severity=sev,
                current_value=current_wr,
                baseline_value=statistics.mean(winrates[:-1]),
                z_score=0.0,
                trend_tau=0.0,
                trend_p_value=1.0,
                message=(
                    f"Win rate {sev}: {current_wr:.1%} "
                    f"sous le seuil {'critique' if sev == 'critical' else 'warning'} "
                    f"({self.winrate_floor_crit if sev == 'critical' else self.winrate_floor:.0%})"
                ),
            )
            events.append(ev)

        self._all_events.extend(events)
        return events

    # ------------------------------------------------------------------

    @property
    def is_degrading(self) -> bool:
        """True si au moins un evenement critique a ete emis."""
        return any(e.severity == "critical" for e in self._all_events)

    @property
    def all_events(self) -> list[DegradationEvent]:
        return list(self._all_events)

    def summary(self) -> dict:
        n_warn = sum(1 for e in self._all_events if e.severity == "warning")
        n_crit = sum(1 for e in self._all_events if e.severity == "critical")
        sharpes = [m.sharpe_ratio for m in self._history]
        return {
            "n_folds_recorded": len(self._history),
            "n_warnings": n_warn,
            "n_critical": n_crit,
            "is_degrading": self.is_degrading,
            "last_sharpe": round(sharpes[-1], 4) if sharpes else None,
            "mean_sharpe": (
                round(statistics.mean(sharpes), 4) if len(sharpes) >= 2 else None
            ),
            "mk_tau": (
                round(_mann_kendall(sharpes)[0], 4) if len(sharpes) >= 3 else None
            ),
        }

    def reset(self) -> None:
        self._history.clear()
        self._all_events.clear()
