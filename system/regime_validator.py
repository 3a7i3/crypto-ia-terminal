"""
regime_validator.py — Validation par régime de marché (P12-C5).

Calcule les métriques séparément pour chaque régime :
  BULL, BEAR, RANGE, HIGH_VOL, LOW_VOL

Si les trades ont un champ `regime`, il est utilisé directement.
Sinon, un classifieur simple (basé sur le P&L cumulatif et la volatilité)
assigne automatiquement un régime à chaque trade.

Usage :
    validator = RegimeValidator()
    report = validator.validate(trades)
    for regime, metrics in report.by_regime.items():
        print(regime, metrics.sharpe_ratio, metrics.win_rate)
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from system.strategy_metrics import StrategyAnalyzer, StrategyMetrics, Trade

_KNOWN_REGIMES = {"BULL", "BEAR", "RANGE", "HIGH_VOL", "LOW_VOL", "UNKNOWN"}


@dataclass
class RegimeReport:
    total_trades: int = 0
    regimes_found: list[str] = field(default_factory=list)
    by_regime: dict[str, StrategyMetrics] = field(default_factory=dict)
    trade_counts_by_regime: dict[str, int] = field(default_factory=dict)

    # Régime le plus performant (Sharpe)
    best_regime: str = ""
    worst_regime: str = ""

    # Dispersion : la stratégie est-elle robuste entre régimes ?
    sharpe_spread: float = 0.0  # max - min Sharpe entre régimes

    def summary(self) -> str:
        parts = []
        for r, m in self.by_regime.items():
            parts.append(
                f"{r}(n={self.trade_counts_by_regime.get(r, 0)} "
                f"wr={m.win_rate:.0%} sh={m.sharpe_ratio:.2f})"
            )
        return " | ".join(parts) if parts else "NO_DATA"


class RegimeValidator:
    """
    Calcule les métriques par régime de marché.

    Si les trades ont un régime explicite (trade.regime != 'UNKNOWN'),
    il est utilisé. Sinon, un classifieur automatique est appliqué.

    initial_capital : capital de départ pour les métriques de drawdown.
    """

    def __init__(self, initial_capital: float = 10_000.0) -> None:
        self._analyzer = StrategyAnalyzer(initial_capital=initial_capital)

    def validate(self, trades: list[Trade]) -> RegimeReport:
        report = RegimeReport(total_trades=len(trades))

        if not trades:
            return report

        # Assigner les régimes si non définis
        labeled = self._label_regimes(trades)

        # Grouper par régime
        groups: dict[str, list[Trade]] = {}
        for t in labeled:
            groups.setdefault(t.regime, []).append(t)

        report.regimes_found = sorted(groups.keys())

        sharpes: dict[str, float] = {}
        for regime, group in groups.items():
            if not group:
                continue
            metrics = self._analyzer.compute(group)
            report.by_regime[regime] = metrics
            report.trade_counts_by_regime[regime] = len(group)
            sharpes[regime] = metrics.sharpe_ratio

        if sharpes:
            best = max(sharpes, key=sharpes.get)
            worst = min(sharpes, key=sharpes.get)
            report.best_regime = best
            report.worst_regime = worst
            report.sharpe_spread = sharpes[best] - sharpes[worst]

        return report

    # ── Classification automatique ────────────────────────────────────────────

    def _label_regimes(self, trades: list[Trade]) -> list[Trade]:
        """
        Si tous les trades ont déjà un régime connu, les retourne tels quels.
        Sinon, applique une classification basique par rolling window.
        """
        already_labeled = all(t.regime in _KNOWN_REGIMES - {"UNKNOWN"} for t in trades)
        if already_labeled:
            return trades

        return self._auto_label(trades)

    @staticmethod
    def _auto_label(trades: list[Trade]) -> list[Trade]:
        """
        Classifieur automatique basé sur :
        - Direction du P&L (BULL si tendance positive, BEAR si négative)
        - Volatilité locale (HIGH_VOL vs LOW_VOL)
        - Magnitude des P&L (RANGE si faibles mouvements)
        """
        labeled = []
        window = 10  # fenêtre glissante

        returns = [t.pnl_pct for t in trades]

        for i, t in enumerate(trades):
            start = max(0, i - window + 1)
            local_returns = returns[start : i + 1]

            if len(local_returns) < 3:
                regime = "RANGE"
            else:
                mean_r = statistics.mean(local_returns)
                try:
                    vol = statistics.stdev(local_returns)
                except statistics.StatisticsError:
                    vol = 0.0

                # Seuils empiriques
                vol_q75 = 1.5  # % de rendement comme seuil de haute vol

                if vol > vol_q75:
                    regime = "HIGH_VOL"
                elif vol < vol_q75 * 0.3:
                    regime = "LOW_VOL"
                elif mean_r > 0.1:
                    regime = "BULL"
                elif mean_r < -0.1:
                    regime = "BEAR"
                else:
                    regime = "RANGE"

            labeled.append(
                Trade(
                    pnl=t.pnl,
                    pnl_pct=t.pnl_pct,
                    duration_s=t.duration_s,
                    ts=t.ts,
                    regime=regime,
                )
            )

        return labeled
