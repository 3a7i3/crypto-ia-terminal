"""
metrics/oos_metrics.py — Metriques hors-echantillon (OOS).

Regle fondamentale : ces fonctions ne recoivent QUE des donnees de test.
Aucun parametre derive de l'ensemble d'entrainement ne doit entrer ici.
Toute normalisation, mean, std calculee ici est strictement OOS.

TradeResult  : une transaction avec son PnL et son regime de marche
OOSMetrics   : agregat de performance OOS (Sharpe, drawdown, WR, ...)
compute_oos_metrics : unique point d'entree pour calculer les metriques
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


@dataclass
class TradeResult:
    """
    Resultat d'un trade individuel tel qu'observe sur le test fold.

    pnl_pct : retour en % (ex : +1.5, -0.8, 0.0)
    regime  : regime de marche au moment du trade ("bull"|"bear"|"stable"|"volatile")
    """

    timestamp_ms: int
    pnl_pct: float
    side: str = "buy"  # "buy" | "sell"
    regime: str = "unknown"  # pour le calcul de stabilite inter-regimes

    @property
    def is_win(self) -> bool:
        return self.pnl_pct > 0

    @property
    def is_loss(self) -> bool:
        return self.pnl_pct < 0


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


@dataclass
class OOSMetrics:
    """
    Metriques de performance hors-echantillon sur un fold ou l'ensemble OOS.

    Toutes les valeurs sont calculees UNIQUEMENT sur les trades du test fold.
    max_drawdown_pct est negatif ou nul.
    """

    n_trades: int
    total_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float  # negatif (ex : -12.3 pour -12.3%)
    win_rate: float  # [0, 1]
    profit_factor: float  # gross_profit / gross_loss (inf si pas de pertes)
    avg_win_pct: float
    avg_loss_pct: float  # negatif ou 0
    expectancy_pct: float  # win_rate * avg_win + (1-win_rate) * avg_loss
    calmar_ratio: float  # total_return / abs(max_drawdown) — inf si dd=0

    @property
    def is_profitable(self) -> bool:
        return self.total_return_pct > 0 and self.profit_factor >= 1.0

    @property
    def risk_adjusted_score(self) -> float:
        """
        Score composite pour classement entre folds.
        Formule : Sharpe * (1 + WinRate) * PF / abs(MaxDD).
        Retourne 0 si les donnees sont insuffisantes.
        """
        if self.n_trades < 2 or self.max_drawdown_pct >= 0:
            return 0.0
        pf = max(self.profit_factor, 0.0)
        return (
            self.sharpe_ratio * (1.0 + self.win_rate) * pf / abs(self.max_drawdown_pct)
        )

    def as_dict(self) -> dict:
        return {
            "n_trades": self.n_trades,
            "total_return_pct": round(self.total_return_pct, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "win_rate": round(self.win_rate, 4),
            "profit_factor": (
                round(self.profit_factor, 4)
                if math.isfinite(self.profit_factor)
                else None
            ),
            "avg_win_pct": round(self.avg_win_pct, 4),
            "avg_loss_pct": round(self.avg_loss_pct, 4),
            "expectancy_pct": round(self.expectancy_pct, 4),
            "calmar_ratio": (
                round(self.calmar_ratio, 4)
                if math.isfinite(self.calmar_ratio)
                else None
            ),
            "is_profitable": self.is_profitable,
            "risk_adjusted_score": round(self.risk_adjusted_score, 4),
        }


# ---------------------------------------------------------------------------
# Calculs internes
# ---------------------------------------------------------------------------


def _max_drawdown(returns_pct: list[float]) -> float:
    """
    Drawdown max en % sur une serie de retours par trade.
    Retourne une valeur negative ou nulle.
    Calcule sur la courbe de capital compoundee (pas la courbe arithmetique).
    """
    if not returns_pct:
        return 0.0
    equity = 100.0
    peak = equity
    max_dd = 0.0
    for r in returns_pct:
        equity *= 1.0 + r / 100.0
        if equity > peak:
            peak = equity
        dd = (equity - peak) / peak * 100.0
        if dd < max_dd:
            max_dd = dd
    return max_dd


def _sharpe(
    returns_pct: list[float], annualization_factor: float, risk_free_rate: float
) -> float:
    """Sharpe annualise. Retourne 0.0 si std = 0 ou n < 2."""
    if len(returns_pct) < 2:
        return 0.0
    mu = statistics.mean(returns_pct)
    sigma = statistics.stdev(returns_pct)
    if sigma <= 0:
        return 0.0
    rf_per_trade = risk_free_rate / annualization_factor
    return (mu - rf_per_trade) / sigma * math.sqrt(annualization_factor)


def _sortino(
    returns_pct: list[float], annualization_factor: float, risk_free_rate: float
) -> float:
    """
    Sortino annualise : utilise l'ecart-type des retours negatifs uniquement.
    Retourne 0.0 si pas de retours negatifs (cas tout-gagnant → excellent).
    """
    if len(returns_pct) < 2:
        return 0.0
    mu = statistics.mean(returns_pct)
    rf_per_trade = risk_free_rate / annualization_factor
    downside_sq = [r**2 for r in returns_pct if r < 0]
    if not downside_sq:
        return float("inf") if mu > rf_per_trade else 0.0
    downside_dev = math.sqrt(statistics.mean(downside_sq))
    if downside_dev <= 0:
        return 0.0
    return (mu - rf_per_trade) / downside_dev * math.sqrt(annualization_factor)


# ---------------------------------------------------------------------------
# Point d'entree public
# ---------------------------------------------------------------------------


def compute_oos_metrics(
    trades: list[TradeResult],
    annualization_factor: float = 252.0,
    risk_free_rate: float = 0.0,
) -> OOSMetrics:
    """
    Calcule toutes les metriques OOS sur une liste de TradeResult.

    annualization_factor : 252 pour trades quotidiens, 365 pour crypto,
                           1 pour laisser les ratios en frequence naturelle.
    risk_free_rate       : taux annuel (ex : 0.04 pour 4%).

    Garantie : aucun parametre externe n'est utilise — 100% OOS.
    """
    n = len(trades)

    if n == 0:
        return OOSMetrics(
            n_trades=0,
            total_return_pct=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown_pct=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            avg_win_pct=0.0,
            avg_loss_pct=0.0,
            expectancy_pct=0.0,
            calmar_ratio=0.0,
        )

    returns = [t.pnl_pct for t in trades]

    # Retour total compoundé
    equity = 100.0
    for r in returns:
        equity *= 1.0 + r / 100.0
    total_return = equity - 100.0

    # Win/loss stats
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    win_rate = len(wins) / n
    avg_win = statistics.mean(wins) if wins else 0.0
    avg_loss = statistics.mean(losses) if losses else 0.0  # negatif

    # Profit factor
    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Expectancy
    expectancy = win_rate * avg_win + (1.0 - win_rate) * avg_loss

    # Drawdown
    max_dd = _max_drawdown(returns)

    # Ratios
    sharpe = _sharpe(returns, annualization_factor, risk_free_rate)
    sortino = _sortino(returns, annualization_factor, risk_free_rate)
    calmar = total_return / abs(max_dd) if max_dd < 0 else float("inf")

    return OOSMetrics(
        n_trades=n,
        total_return_pct=total_return,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown_pct=max_dd,
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_win_pct=avg_win,
        avg_loss_pct=avg_loss,
        expectancy_pct=expectancy,
        calmar_ratio=calmar,
    )
