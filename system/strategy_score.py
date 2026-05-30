"""
strategy_score.py — Score composite de stratégie 0-100 (P12-C6).

Pondération :
  25% Sharpe Ratio
  25% Sortino Ratio
  20% Profit Factor
  15% Max Drawdown
  15% Expectancy

Résultat :
  StrategyGrade: S / A / B / C / D / F

Usage :
    scorer = StrategyScorer()
    score, grade = scorer.score(metrics)
    print(f"Score: {score}/100 — Grade: {grade}")
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from system.strategy_metrics import StrategyMetrics


class StrategyGrade(str, Enum):
    S = "S"  # 90-100 : exceptionnel
    A = "A"  # 75-89  : excellent
    B = "B"  # 60-74  : bon
    C = "C"  # 45-59  : passable
    D = "D"  # 30-44  : faible
    F = "F"  # 0-29   : à rejeter


@dataclass
class StrategyScoreResult:
    total: float  # [0, 100]
    grade: StrategyGrade

    # Contributions détaillées
    sharpe_pts: float = 0.0
    sortino_pts: float = 0.0
    profit_factor_pts: float = 0.0
    drawdown_pts: float = 0.0
    expectancy_pts: float = 0.0

    def summary(self) -> str:
        return (
            f"score={self.total:.1f}/100 grade={self.grade} "
            f"(sharpe={self.sharpe_pts:.1f} sortino={self.sortino_pts:.1f} "
            f"pf={self.profit_factor_pts:.1f} dd={self.drawdown_pts:.1f} "
            f"exp={self.expectancy_pts:.1f})"
        )


# ── Seuils de normalisation ────────────────────────────────────────────────────
# Chaque métrique est normalisée vers [0, max_pts].
# Valeurs de référence basées sur la littérature de trading algorithmique.

_SHARPE_EXCELLENT = 2.0  # Sharpe >= 2 → 100% des pts Sharpe
_SHARPE_GOOD = 1.0
_SHARPE_MIN = 0.0  # seuil zéro

_SORTINO_EXCELLENT = 3.0
_SORTINO_GOOD = 1.5
_SORTINO_MIN = 0.0

_PF_EXCELLENT = 2.0  # Profit Factor >= 2 → excellent
_PF_GOOD = 1.5
_PF_MIN = 1.0  # PF < 1 → nul

_DD_EXCELLENT = 5.0  # Max DD <= 5% → parfait
_DD_GOOD = 15.0
_DD_MAX = 50.0  # DD >= 50% → 0 pts

_EXP_EXCELLENT = 0.5  # Expectancy >= 0.5% par trade
_EXP_GOOD = 0.1
_EXP_MIN = 0.0


class StrategyScorer:
    """
    Calcule un score composite de stratégie [0, 100].

    Utilise StrategyMetrics comme input (sortie de StrategyAnalyzer.compute()).
    """

    # Pondérations (doivent sommer à 100)
    _WEIGHTS = {
        "sharpe": 25.0,
        "sortino": 25.0,
        "profit_factor": 20.0,
        "drawdown": 15.0,
        "expectancy": 15.0,
    }

    def score(self, metrics: StrategyMetrics) -> StrategyScoreResult:
        """Retourne le score composite et la note."""
        sharpe_pts = self._score_sharpe(metrics.sharpe_ratio)
        sortino_pts = self._score_sortino(metrics.sortino_ratio)
        pf_pts = self._score_profit_factor(metrics.profit_factor)
        dd_pts = self._score_drawdown(metrics.max_drawdown_pct)
        exp_pts = self._score_expectancy(metrics.expectancy)

        total = (
            sharpe_pts * self._WEIGHTS["sharpe"] / 100
            + sortino_pts * self._WEIGHTS["sortino"] / 100
            + pf_pts * self._WEIGHTS["profit_factor"] / 100
            + dd_pts * self._WEIGHTS["drawdown"] / 100
            + exp_pts * self._WEIGHTS["expectancy"] / 100
        )

        total = round(max(0.0, min(100.0, total)), 2)

        result = StrategyScoreResult(
            total=total,
            grade=self._grade(total),
            sharpe_pts=round(sharpe_pts, 2),
            sortino_pts=round(sortino_pts, 2),
            profit_factor_pts=round(pf_pts, 2),
            drawdown_pts=round(dd_pts, 2),
            expectancy_pts=round(exp_pts, 2),
        )
        return result

    def grade(self, score: float) -> StrategyGrade:
        return self._grade(score)

    # ── Normalisation par métrique ────────────────────────────────────────────

    @staticmethod
    def _score_sharpe(sharpe: float) -> float:
        """[0, 100] depuis le Sharpe ratio."""
        if sharpe >= _SHARPE_EXCELLENT:
            return 100.0
        if sharpe <= _SHARPE_MIN:
            return 0.0
        if sharpe >= _SHARPE_GOOD:
            ratio = (sharpe - _SHARPE_GOOD) / (_SHARPE_EXCELLENT - _SHARPE_GOOD)
            return 50.0 + ratio * 50.0
        ratio = (sharpe - _SHARPE_MIN) / (_SHARPE_GOOD - _SHARPE_MIN)
        return ratio * 50.0

    @staticmethod
    def _score_sortino(sortino: float) -> float:
        if sortino >= _SORTINO_EXCELLENT:
            return 100.0
        if sortino <= _SORTINO_MIN:
            return 0.0
        if sortino >= _SORTINO_GOOD:
            ratio = (sortino - _SORTINO_GOOD) / (_SORTINO_EXCELLENT - _SORTINO_GOOD)
            return 50.0 + ratio * 50.0
        ratio = (sortino - _SORTINO_MIN) / (_SORTINO_GOOD - _SORTINO_MIN)
        return ratio * 50.0

    @staticmethod
    def _score_profit_factor(pf: float) -> float:
        if pf == float("inf") or pf >= _PF_EXCELLENT:
            return 100.0
        if pf <= _PF_MIN:
            return 0.0
        if pf >= _PF_GOOD:
            ratio = (pf - _PF_GOOD) / (_PF_EXCELLENT - _PF_GOOD)
            return 50.0 + ratio * 50.0
        ratio = (pf - _PF_MIN) / (_PF_GOOD - _PF_MIN)
        return ratio * 50.0

    @staticmethod
    def _score_drawdown(dd: float) -> float:
        """Score inversé : drawdown faible → score élevé."""
        if dd <= _DD_EXCELLENT:
            return 100.0
        if dd >= _DD_MAX:
            return 0.0
        if dd <= _DD_GOOD:
            ratio = (dd - _DD_EXCELLENT) / (_DD_GOOD - _DD_EXCELLENT)
            return 100.0 - ratio * 50.0
        ratio = (dd - _DD_GOOD) / (_DD_MAX - _DD_GOOD)
        return 50.0 - ratio * 50.0

    @staticmethod
    def _score_expectancy(exp: float) -> float:
        if exp >= _EXP_EXCELLENT:
            return 100.0
        if exp <= _EXP_MIN:
            return max(0.0, 50.0 + exp * 100.0)
        if exp >= _EXP_GOOD:
            ratio = (exp - _EXP_GOOD) / (_EXP_EXCELLENT - _EXP_GOOD)
            return 50.0 + ratio * 50.0
        ratio = (exp - _EXP_MIN) / (_EXP_GOOD - _EXP_MIN)
        return ratio * 50.0

    @staticmethod
    def _grade(score: float) -> StrategyGrade:
        if score >= 90:
            return StrategyGrade.S
        if score >= 75:
            return StrategyGrade.A
        if score >= 60:
            return StrategyGrade.B
        if score >= 45:
            return StrategyGrade.C
        if score >= 30:
            return StrategyGrade.D
        return StrategyGrade.F
