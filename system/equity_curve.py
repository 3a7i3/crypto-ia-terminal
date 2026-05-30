"""
equity_curve.py — Analyse de la courbe d'equity (P12-C2).

Mesure :
  - Périodes de drawdown (durée, profondeur)
  - Temps sous l'eau (underwater)
  - Nouveaux sommets (new highs)
  - Temps de récupération après chaque drawdown

Usage :
    analyzer = EquityCurveAnalyzer()
    report = analyzer.analyze([10000, 10500, 9800, 10200, 11000])
    print(report.max_drawdown_pct, report.longest_underwater_bars)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DrawdownPeriod:
    peak_idx: int
    trough_idx: int
    recovery_idx: Optional[int]  # None si jamais récupéré
    peak_value: float
    trough_value: float
    drawdown_pct: float
    duration_bars: int  # peak → trough
    recovery_bars: Optional[int]  # trough → recovery (None si pas récupéré)

    @property
    def total_bars(self) -> int:
        """peak → recovery (ou fin de série si non récupéré)."""
        if self.recovery_bars is None:
            return self.duration_bars
        return self.duration_bars + self.recovery_bars


@dataclass
class EquityCurveReport:
    # Drawdown global
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_bars: int = 0
    avg_drawdown_pct: float = 0.0
    n_drawdown_periods: int = 0

    # Underwater
    longest_underwater_bars: int = 0
    avg_underwater_bars: float = 0.0
    pct_time_underwater: float = 0.0  # [0, 1]

    # Récupération
    avg_recovery_bars: Optional[float] = None
    max_recovery_bars: Optional[int] = None
    unrecovered_drawdowns: int = 0  # drawdowns non récupérés à la fin

    # Sommets
    n_new_highs: int = 0
    final_is_new_high: bool = False

    # Volatilité de l'equity
    equity_volatility_pct: float = 0.0  # std des rendements barre-à-barre

    # Détail
    drawdown_periods: list[DrawdownPeriod] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"mdd={self.max_drawdown_pct:.1f}% "
            f"underwater={self.longest_underwater_bars}bars "
            f"new_highs={self.n_new_highs} "
            f"unrecovered={self.unrecovered_drawdowns}"
        )


class EquityCurveAnalyzer:
    """
    Analyse complète d'une courbe d'equity.

    equity : liste de valeurs numériques, ordre chronologique.
    """

    def analyze(self, equity: list[float]) -> EquityCurveReport:
        report = EquityCurveReport()
        n = len(equity)

        if n < 2:
            return report

        # ── Rendements barre-à-barre ──────────────────────────────────────────
        returns = [
            (
                (equity[i] - equity[i - 1]) / equity[i - 1] * 100
                if equity[i - 1] != 0
                else 0.0
            )
            for i in range(1, n)
        ]
        if len(returns) >= 2:
            mean_r = sum(returns) / len(returns)
            variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
            report.equity_volatility_pct = math.sqrt(variance)

        # ── Nouveaux sommets ──────────────────────────────────────────────────
        peak = equity[0]
        n_highs = 0
        for i in range(1, n):
            if equity[i] > peak:
                peak = equity[i]
                n_highs += 1
        report.n_new_highs = n_highs
        report.final_is_new_high = equity[-1] >= max(equity)

        # ── Périodes de drawdown ──────────────────────────────────────────────
        periods: list[DrawdownPeriod] = []
        current_peak = equity[0]
        current_peak_idx = 0
        in_drawdown = False
        trough = equity[0]
        trough_idx = 0

        for i in range(1, n):
            e = equity[i]
            if not in_drawdown:
                if e < current_peak:
                    # Début de drawdown
                    in_drawdown = True
                    trough = e
                    trough_idx = i
                else:
                    current_peak = e
                    current_peak_idx = i
            else:
                if e < trough:
                    trough = e
                    trough_idx = i
                elif current_peak > 0 and e >= current_peak:
                    # Récupération complète
                    dd_pct = (current_peak - trough) / current_peak * 100
                    dur = trough_idx - current_peak_idx
                    rec = i - trough_idx
                    periods.append(
                        DrawdownPeriod(
                            peak_idx=current_peak_idx,
                            trough_idx=trough_idx,
                            recovery_idx=i,
                            peak_value=current_peak,
                            trough_value=trough,
                            drawdown_pct=round(dd_pct, 6),
                            duration_bars=dur,
                            recovery_bars=rec,
                        )
                    )
                    in_drawdown = False
                    current_peak = e
                    current_peak_idx = i

        # Drawdown non récupéré en fin de série
        if in_drawdown and current_peak > 0:
            dd_pct = (current_peak - trough) / current_peak * 100
            dur = trough_idx - current_peak_idx
            periods.append(
                DrawdownPeriod(
                    peak_idx=current_peak_idx,
                    trough_idx=trough_idx,
                    recovery_idx=None,
                    peak_value=current_peak,
                    trough_value=trough,
                    drawdown_pct=round(dd_pct, 6),
                    duration_bars=dur,
                    recovery_bars=None,
                )
            )

        report.drawdown_periods = periods
        report.n_drawdown_periods = len(periods)

        if periods:
            dds = [p.drawdown_pct for p in periods]
            report.max_drawdown_pct = max(dds)
            report.avg_drawdown_pct = sum(dds) / len(dds)
            report.max_drawdown_duration_bars = max(p.duration_bars for p in periods)

            # Récupérations
            recovered = [p for p in periods if p.recovery_bars is not None]
            report.unrecovered_drawdowns = len(periods) - len(recovered)
            if recovered:
                rec_bars = [p.recovery_bars for p in recovered]
                report.avg_recovery_bars = sum(rec_bars) / len(rec_bars)
                report.max_recovery_bars = max(rec_bars)

        # ── Temps sous l'eau ─────────────────────────────────────────────────
        # Nombre de barres où equity < pic historique courant
        peak_running = equity[0]
        underwater_bars = 0
        underwater_streak = 0
        max_streak = 0
        streaks = []

        for e in equity[1:]:
            if e < peak_running:
                underwater_bars += 1
                underwater_streak += 1
                max_streak = max(max_streak, underwater_streak)
            else:
                if underwater_streak > 0:
                    streaks.append(underwater_streak)
                underwater_streak = 0
                peak_running = e

        if underwater_streak > 0:
            streaks.append(underwater_streak)

        report.longest_underwater_bars = max_streak
        report.avg_underwater_bars = sum(streaks) / len(streaks) if streaks else 0.0
        report.pct_time_underwater = underwater_bars / (n - 1) if n > 1 else 0.0

        return report
