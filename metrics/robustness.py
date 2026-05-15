"""
metrics/robustness.py — KPIs de robustesse pour validation go/no-go P5.

Formules :
  ruin_probability()  : probabilité que le capital descende sous le seuil de ruine
  survival_score()    : score composite 0-100 de résistance du système
  robustness_report() : rapport complet go/no-go avec critères P5

Ruin probability — modèle Gambler's Ruin (analytique) :
  p_ruin = ((1-edge) / edge) ^ (capital / bet_size)
  où edge = win_rate - (1 - win_rate) * avg_loss / avg_win

Survival score — composite pondéré :
  40% Sharpe OOS ≥ 0.5
  25% Max drawdown ≤ 15%
  20% Win rate ≥ 45%
  15% Ruin probability ≤ 5%

Critère go/no-go P5 :
  survival_score ≥ 60  ET  ruin_probability ≤ 10%  ET  sharpe ≥ 0.3
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# ── Ruin Probability ──────────────────────────────────────────────────────────


def ruin_probability(
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
    capital_usd: float,
    bet_size_usd: float,
    ruin_threshold_pct: float = 50.0,
) -> float:
    """
    Probabilité de ruine via modèle Gambler's Ruin.

    win_rate         : taux de victoire [0, 1]
    avg_win_pct      : gain moyen par trade en % (positif)
    avg_loss_pct     : perte moyenne par trade en % (positif)
    capital_usd      : capital courant
    bet_size_usd     : taille de mise par trade
    ruin_threshold_pct : capital résiduel considéré comme ruine (défaut 50%)

    Retourne une probabilité ∈ [0, 1].
    """
    if win_rate <= 0 or win_rate >= 1:
        return 1.0 if win_rate <= 0 else 0.0
    if avg_win_pct <= 0 or avg_loss_pct <= 0:
        return 1.0

    loss_rate = 1.0 - win_rate
    # Edge normalisé : gain espéré par unité misée
    edge = win_rate * avg_win_pct - loss_rate * avg_loss_pct

    if edge <= 0:
        return 1.0  # jeu à somme négative — ruine certaine à long terme

    # Ratio odds (rapport gain/perte)
    odds_ratio = avg_win_pct / avg_loss_pct

    # Probabilité de succès ajustée
    p = win_rate
    q = loss_rate

    if abs(p * odds_ratio - q) < 1e-9:
        # Cas limite : random walk
        ruin_capital = capital_usd * (ruin_threshold_pct / 100.0)
        return ruin_capital / capital_usd

    # Nombre de "unités" avant ruine et objectif
    n_units = capital_usd / bet_size_usd
    ruin_units = n_units * (ruin_threshold_pct / 100.0)

    # Formule Gambler's Ruin généralisée
    ratio = q / (p * odds_ratio) if p * odds_ratio != 0 else float("inf")

    if ratio >= 1.0:
        return 1.0

    try:
        p_ruin = (ratio**ruin_units - ratio**n_units) / (1.0 - ratio**n_units)
        return max(0.0, min(1.0, p_ruin))
    except (OverflowError, ZeroDivisionError):
        return 0.0 if edge > 0 else 1.0


# ── Survival Score ────────────────────────────────────────────────────────────


def survival_score(
    sharpe: float,
    max_drawdown_pct: float,
    win_rate_pct: float,
    ruin_prob: float,
) -> float:
    """
    Score composite de survie du système [0, 100].

    Pondération :
      40% — Sharpe OOS (cible ≥ 0.5, parfait ≥ 1.5)
      25% — Max drawdown (cible ≤ 15%, parfait ≤ 5%)
      20% — Win rate (cible ≥ 45%, parfait ≥ 60%)
      15% — Ruin probability (cible ≤ 10%, parfait ≤ 1%)
    """

    def _sharpe_score(s: float) -> float:
        if s <= 0:
            return 0.0
        if s >= 1.5:
            return 100.0
        return min(100.0, s / 1.5 * 100.0)

    def _drawdown_score(dd: float) -> float:
        dd = abs(dd)
        if dd >= 30.0:
            return 0.0
        if dd <= 5.0:
            return 100.0
        return max(0.0, (30.0 - dd) / (30.0 - 5.0) * 100.0)

    def _winrate_score(wr: float) -> float:
        if wr <= 30.0:
            return 0.0
        if wr >= 65.0:
            return 100.0
        return max(0.0, (wr - 30.0) / (65.0 - 30.0) * 100.0)

    def _ruin_score(rp: float) -> float:
        rp_pct = rp * 100.0
        if rp_pct >= 25.0:
            return 0.0
        if rp_pct <= 1.0:
            return 100.0
        return max(0.0, (25.0 - rp_pct) / (25.0 - 1.0) * 100.0)

    score = (
        0.40 * _sharpe_score(sharpe)
        + 0.25 * _drawdown_score(max_drawdown_pct)
        + 0.20 * _winrate_score(win_rate_pct)
        + 0.15 * _ruin_score(ruin_prob)
    )
    return round(score, 1)


# ── Rapport complet ───────────────────────────────────────────────────────────


@dataclass
class RobustnessReport:
    """Rapport go/no-go complet pour validation P5."""

    sharpe: float
    max_drawdown_pct: float
    win_rate_pct: float
    n_trades: int
    avg_win_pct: float
    avg_loss_pct: float
    capital_usd: float
    bet_size_usd: float
    ruin_threshold_pct: float

    # Calculés
    ruin_probability: float = 0.0
    survival_score: float = 0.0
    go_no_go: str = "NO_GO"
    reasons: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.reasons is None:
            self.reasons = []
        self.ruin_probability = ruin_probability(
            win_rate=self.win_rate_pct / 100.0,
            avg_win_pct=self.avg_win_pct,
            avg_loss_pct=self.avg_loss_pct,
            capital_usd=self.capital_usd,
            bet_size_usd=self.bet_size_usd,
            ruin_threshold_pct=self.ruin_threshold_pct,
        )
        self.survival_score = survival_score(
            sharpe=self.sharpe,
            max_drawdown_pct=self.max_drawdown_pct,
            win_rate_pct=self.win_rate_pct,
            ruin_prob=self.ruin_probability,
        )
        self._evaluate()

    def _evaluate(self) -> None:
        self.reasons = []
        fails = []

        # Critères go/no-go P5
        if self.survival_score < 60:
            fails.append(f"survival_score={self.survival_score:.1f} < 60")
        if self.ruin_probability > 0.10:
            fails.append(f"ruin_prob={self.ruin_probability:.1%} > 10%")
        if self.sharpe < 0.3:
            fails.append(f"sharpe={self.sharpe:.2f} < 0.3")
        if self.n_trades < 30:
            fails.append(f"n_trades={self.n_trades} < 30 (pas assez de données)")
        if abs(self.max_drawdown_pct) > 25.0:
            fails.append(f"max_drawdown={self.max_drawdown_pct:.1f}% > 25%")

        # Avertissements (pas bloquants)
        if self.win_rate_pct < 40:
            self.reasons.append(f"⚠️  win_rate={self.win_rate_pct:.1f}% bas")
        if abs(self.max_drawdown_pct) > 15.0:
            self.reasons.append(f"⚠️  drawdown={self.max_drawdown_pct:.1f}% élevé")

        self.go_no_go = "GO" if not fails else "NO_GO"
        self.reasons = fails + self.reasons

    def as_dict(self) -> dict:
        return {
            "go_no_go": self.go_no_go,
            "survival_score": self.survival_score,
            "ruin_probability_pct": round(self.ruin_probability * 100, 2),
            "sharpe": round(self.sharpe, 3),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "win_rate_pct": round(self.win_rate_pct, 1),
            "n_trades": self.n_trades,
            "avg_win_pct": round(self.avg_win_pct, 3),
            "avg_loss_pct": round(self.avg_loss_pct, 3),
            "capital_usd": self.capital_usd,
            "bet_size_usd": self.bet_size_usd,
            "reasons": self.reasons,
        }

    def __str__(self) -> str:
        lines = [
            f"══ Robustness Report ══",
            f"  GO/NO-GO     : {self.go_no_go}",
            f"  Survival     : {self.survival_score:.1f}/100",
            f"  Ruin prob    : {self.ruin_probability:.1%}",
            f"  Sharpe OOS   : {self.sharpe:.3f}",
            f"  Max drawdown : {self.max_drawdown_pct:.1f}%",
            f"  Win rate     : {self.win_rate_pct:.1f}%",
            f"  N trades     : {self.n_trades}",
        ]
        if self.reasons:
            lines.append("  Raisons :")
            for r in self.reasons:
                lines.append(f"    • {r}")
        return "\n".join(lines)


def robustness_report(
    sharpe: float,
    max_drawdown_pct: float,
    win_rate_pct: float,
    n_trades: int,
    avg_win_pct: float,
    avg_loss_pct: float,
    capital_usd: float = 10_000.0,
    bet_size_usd: float = 500.0,
    ruin_threshold_pct: float = 50.0,
) -> RobustnessReport:
    """Factory — crée et évalue un RobustnessReport."""
    return RobustnessReport(
        sharpe=sharpe,
        max_drawdown_pct=max_drawdown_pct,
        win_rate_pct=win_rate_pct,
        n_trades=n_trades,
        avg_win_pct=avg_win_pct,
        avg_loss_pct=avg_loss_pct,
        capital_usd=capital_usd,
        bet_size_usd=bet_size_usd,
        ruin_threshold_pct=ruin_threshold_pct,
    )
