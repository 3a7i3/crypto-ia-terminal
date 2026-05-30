"""
strategy_metrics.py — Métriques de performance fondamentales (P12-C1).

Métriques calculées :
  Total Return, Win Rate, Avg Win/Loss, Profit Factor, Expectancy,
  Max Drawdown, Recovery Factor, Sharpe Ratio, Sortino Ratio, CAGR.

Usage :
    trades = [Trade(pnl=50.0, pnl_pct=0.5), Trade(pnl=-20.0, pnl_pct=-0.2)]
    equity = [10000, 10050, 10030]
    analyzer = StrategyAnalyzer(initial_capital=10000.0)
    metrics = analyzer.compute(trades, equity)
    print(metrics.sharpe_ratio, metrics.expectancy)
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Optional


@dataclass
class Trade:
    pnl: float  # P&L absolu en USD
    pnl_pct: float  # rendement % (ex: 0.5 = +0.5%)
    duration_s: float = 0.0
    ts: float = 0.0
    regime: str = "UNKNOWN"  # BULL / BEAR / RANGE / HIGH_VOL / LOW_VOL


@dataclass
class StrategyMetrics:
    # Volume
    total_trades: int = 0
    win_trades: int = 0
    loss_trades: int = 0

    # Taux
    win_rate: float = 0.0  # [0, 1]
    loss_rate: float = 0.0

    # Tailles moyennes
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0  # valeur positive (magnitude)

    # Ratios de qualité
    profit_factor: float = 0.0  # Σwins / |Σlosses|
    expectancy: float = 0.0  # P(W)·ĀW + P(L)·ĀL

    # Rendement
    total_return_pct: float = 0.0
    cagr: Optional[float] = None

    # Risque
    max_drawdown_pct: float = 0.0
    recovery_factor: float = 0.0  # total_return / max_drawdown

    # Risque ajusté
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0

    # Flags
    is_viable: bool = False  # expectancy > 0 et profit_factor > 1

    def summary(self) -> str:
        return (
            f"trades={self.total_trades} wr={self.win_rate:.1%} "
            f"pf={self.profit_factor:.2f} exp={self.expectancy:.4f} "
            f"sharpe={self.sharpe_ratio:.2f} sortino={self.sortino_ratio:.2f} "
            f"mdd={self.max_drawdown_pct:.1f}%"
        )


class StrategyAnalyzer:
    """
    Calcule les métriques de performance à partir d'une liste de trades.

    initial_capital : capital de départ (pour drawdown % et CAGR)
    risk_free       : taux sans risque annualisé (défaut 0)
    annual_factor   : facteur d'annualisation des ratios (252 = daily, 52 = weekly)
    """

    def __init__(
        self,
        initial_capital: float = 10_000.0,
        risk_free: float = 0.0,
        annual_factor: float = 252.0,
    ) -> None:
        self._initial = initial_capital
        self._rf = risk_free
        self._af = annual_factor

    def compute(
        self,
        trades: list[Trade],
        equity_curve: Optional[list[float]] = None,
    ) -> StrategyMetrics:
        """
        Calcule toutes les métriques.

        trades      : liste de Trade (ordre chronologique)
        equity_curve: valeurs d'equity pour le calcul du drawdown
                      (si None, reconstruit depuis initial_capital + pnl cumulatif)
        """
        if not trades:
            return StrategyMetrics()

        m = StrategyMetrics()
        m.total_trades = len(trades)

        returns = [t.pnl_pct for t in trades]
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]

        m.win_trades = len(wins)
        m.loss_trades = len(losses)
        m.win_rate = m.win_trades / m.total_trades if m.total_trades else 0.0
        m.loss_rate = 1.0 - m.win_rate

        m.avg_win_pct = statistics.mean(wins) if wins else 0.0
        m.avg_loss_pct = abs(statistics.mean(losses)) if losses else 0.0

        # Profit Factor
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        m.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Expectancy = P(W) * AvgWin + P(L) * AvgLoss (AvgLoss négatif)
        avg_loss_signed = -m.avg_loss_pct
        m.expectancy = m.win_rate * m.avg_win_pct + m.loss_rate * avg_loss_signed

        # Total return
        m.total_return_pct = sum(returns)

        # CAGR si timestamps disponibles
        if trades[0].ts > 0 and trades[-1].ts > trades[0].ts:
            days = (trades[-1].ts - trades[0].ts) / 86_400
            total_ret = 1.0 + m.total_return_pct / 100.0
            if total_ret > 0 and days > 0:
                m.cagr = (total_ret ** (365.0 / days) - 1) * 100

        # Equity curve
        if equity_curve is None:
            equity_curve = self._build_equity_curve(trades)

        m.max_drawdown_pct = self._max_drawdown(equity_curve)

        # Recovery Factor
        if m.max_drawdown_pct > 0:
            m.recovery_factor = abs(m.total_return_pct) / m.max_drawdown_pct
        else:
            m.recovery_factor = float("inf") if m.total_return_pct > 0 else 0.0

        # Sharpe = (mean_r - rf) / std_r * sqrt(N)
        if len(returns) >= 2:
            mean_r = statistics.mean(returns)
            std_r = statistics.stdev(returns)
            if std_r > 0:
                m.sharpe_ratio = (
                    (mean_r - self._rf / self._af) / std_r * math.sqrt(self._af)
                )

        # Sortino = mean_r / downside_std * sqrt(N)
        if len(returns) >= 2:
            mean_r = statistics.mean(returns)
            neg_returns = [r for r in returns if r < 0]
            if neg_returns:
                downside_std = math.sqrt(
                    sum(r**2 for r in neg_returns) / len(neg_returns)
                )
                if downside_std > 0:
                    m.sortino_ratio = mean_r / downside_std * math.sqrt(self._af)

        m.is_viable = m.expectancy > 0 and m.profit_factor > 1.0

        return m

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _build_equity_curve(self, trades: list[Trade]) -> list[float]:
        curve = [self._initial]
        equity = self._initial
        for t in trades:
            equity += t.pnl
            curve.append(equity)
        return curve

    @staticmethod
    def _max_drawdown(equity: list[float]) -> float:
        """Drawdown maximal (%) depuis le pic le plus récent."""
        if len(equity) < 2:
            return 0.0
        peak = equity[0]
        max_dd = 0.0
        for e in equity:
            if e > peak:
                peak = e
            if peak > 0:
                dd = (peak - e) / peak * 100
                if dd > max_dd:
                    max_dd = dd
        return round(max_dd, 6)
