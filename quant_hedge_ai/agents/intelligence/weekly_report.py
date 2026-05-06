"""
weekly_report.py — Rapport hebdomadaire automatisé du système.

Agrège :
  - Statistiques de trading (PnL, win rate, drawdown max)
  - Évolution de la mémoire stratégique (meilleurs régimes, stratégies blacklistées)
  - Résumé de l'activité de l'EventBus (incidents, alertes, cycles d'évolution)
  - Conseils d'amélioration générés par AIAdvisor

Sortie : dict structuré + texte formaté pour Telegram/Slack.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WeeklyStats:
    """Statistiques brutes d'une semaine."""

    period_start: datetime = field(default_factory=lambda: datetime.now() - timedelta(days=7))
    period_end: datetime = field(default_factory=datetime.now)
    n_trades: int = 0
    wins: int = 0
    losses: int = 0
    neutrals: int = 0
    total_pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    best_trade_pct: float = 0.0
    worst_trade_pct: float = 0.0
    n_signals_generated: int = 0
    n_blacklists: int = 0
    n_evolution_cycles: int = 0
    best_regime: str = "unknown"
    worst_regime: str = "unknown"
    active_strategies: list[str] = field(default_factory=list)
    blacklisted_strategies: list[str] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        total = self.wins + self.losses
        return round(self.wins / total, 3) if total > 0 else 0.0

    @property
    def avg_pnl_pct(self) -> float:
        total = self.wins + self.losses + self.neutrals
        return round(self.total_pnl_pct / total, 3) if total > 0 else 0.0


class WeeklyReportAgent:
    """
    Génère le rapport hebdomadaire à partir des données disponibles.

    Usage:
        agent = WeeklyReportAgent(postmortem=pm, memory_store=mem)
        report = agent.generate()
        print(report.text_summary)
    """

    def __init__(
        self,
        postmortem=None,
        memory_store=None,
        advisor=None,
    ) -> None:
        self._postmortem = postmortem
        self._memory = memory_store
        self._advisor = advisor

    # ── API principale ─────────────────────────────────────────────────────────

    def generate(self) -> "WeeklyReport":
        """Génère le rapport de la semaine écoulée."""
        stats = self._collect_stats()
        improvements = self._build_improvements(stats)
        text = self._format_text(stats, improvements)
        report = WeeklyReport(stats=stats, improvements=improvements, text_summary=text)
        self._emit_event(report)
        logger.info("[WeeklyReport] Rapport généré : %d trades, win_rate=%.1f%%",
                    stats.n_trades, stats.win_rate * 100)
        return report

    # ── Collecte des données ──────────────────────────────────────────────────

    def _collect_stats(self) -> WeeklyStats:
        stats = WeeklyStats()

        if self._postmortem is not None:
            summary = self._postmortem.summary()
            stats.n_trades = summary.get("n_trades", 0)
            stats.wins = summary.get("wins", 0)
            stats.losses = summary.get("losses", 0)
            stats.neutrals = stats.n_trades - stats.wins - stats.losses
            stats.n_blacklists = summary.get("total_blacklists", 0)

            # Récupère PnL et meilleur/pire trade depuis les rapports
            reports = getattr(self._postmortem, "_all_reports", [])
            if reports:
                pnls = [r.trade.pnl_pct for r in reports]
                stats.total_pnl_pct = round(sum(pnls), 3)
                stats.best_trade_pct = round(max(pnls), 3)
                stats.worst_trade_pct = round(min(pnls), 3)
                stats.max_drawdown_pct = round(abs(min((p for p in pnls if p < 0), default=0.0)), 3)

                # Régimes
                regime_wins: dict[str, int] = {}
                regime_losses: dict[str, int] = {}
                for r in reports:
                    reg = r.trade.regime
                    if r.verdict == "win":
                        regime_wins[reg] = regime_wins.get(reg, 0) + 1
                    elif r.verdict == "loss":
                        regime_losses[reg] = regime_losses.get(reg, 0) + 1
                if regime_wins:
                    stats.best_regime = max(regime_wins, key=lambda k: regime_wins[k])
                if regime_losses:
                    stats.worst_regime = max(regime_losses, key=lambda k: regime_losses[k])

                stats.blacklisted_strategies = list({
                    r.trade.strategy_name for r in reports if r.blacklisted
                })

        if self._memory is not None:
            try:
                payload = self._memory._read()
                regimes = payload.get("regimes", {})
                stats.active_strategies = list(regimes.keys())
                stats.n_evolution_cycles = len(payload.get("regime_history", []))
            except Exception as exc:
                logger.debug("[WeeklyReport] Erreur lecture mémoire: %s", exc)

        return stats

    def _build_improvements(self, stats: WeeklyStats) -> list[str]:
        improvements: list[str] = []

        if stats.win_rate < 0.5 and stats.n_trades >= 5:
            improvements.append(
                f"Win rate de {stats.win_rate:.0%} — revoir les critères d'entrée "
                f"(augmenter SIGNAL_MIN_SCORE ou min_strength MTF)."
            )

        if stats.max_drawdown_pct > 10.0:
            improvements.append(
                f"Drawdown max de {stats.max_drawdown_pct:.1f}% — "
                f"activer le GlobalRiskGate ou réduire la taille des positions."
            )

        if stats.n_blacklists > 0:
            strats = ", ".join(stats.blacklisted_strategies[:3])
            improvements.append(
                f"{stats.n_blacklists} stratégie(s) blacklistée(s) cette semaine "
                f"({strats}) — éviter ces combinaisons stratégie/régime."
            )

        if stats.worst_regime not in ("unknown", "") and stats.losses > 0:
            improvements.append(
                f"Régime le plus défavorable : {stats.worst_regime}. "
                f"Envisager de désactiver le trading en {stats.worst_regime}."
            )

        if stats.avg_pnl_pct > 2.0:
            improvements.append(
                f"Performance solide (PnL moyen {stats.avg_pnl_pct:.2f}%) — "
                f"envisager d'augmenter progressivement la taille des positions."
            )

        if not improvements:
            improvements.append(
                "Aucun signal d'alarme cette semaine. "
                "Continuer à monitorer les régimes de marché."
            )

        return improvements

    def _format_text(self, stats: WeeklyStats, improvements: list[str]) -> str:
        period = f"{stats.period_start.strftime('%d/%m')} → {stats.period_end.strftime('%d/%m/%Y')}"
        win_emoji = "✅" if stats.win_rate >= 0.5 else "⚠️"
        pnl_emoji = "📈" if stats.total_pnl_pct >= 0 else "📉"

        lines = [
            f"📊 RAPPORT HEBDOMADAIRE — {period}",
            "─" * 40,
            f"Trades : {stats.n_trades} | Wins : {stats.wins} | Losses : {stats.losses}",
            f"{win_emoji} Win rate : {stats.win_rate:.1%}",
            f"{pnl_emoji} PnL total : {stats.total_pnl_pct:+.2f}%  |  Moy : {stats.avg_pnl_pct:+.2f}%",
            f"Meilleur trade : {stats.best_trade_pct:+.2f}%  |  Pire : {stats.worst_trade_pct:+.2f}%",
            f"Drawdown max : {stats.max_drawdown_pct:.1f}%",
            f"Meilleur régime : {stats.best_regime}  |  Pire : {stats.worst_regime}",
        ]

        if stats.blacklisted_strategies:
            lines.append(f"🚫 Blacklistées : {', '.join(stats.blacklisted_strategies)}")

        lines += [
            "─" * 40,
            "💡 AMÉLIORATIONS SUGGÉRÉES",
        ]
        for i, imp in enumerate(improvements, 1):
            lines.append(f"  {i}. {imp}")

        return "\n".join(lines)

    def _emit_event(self, report: "WeeklyReport") -> None:
        try:
            from event_bus.bus import EventBus
            from event_bus.events import EvolutionCycleEvent
            EventBus.get().emit(
                EvolutionCycleEvent(
                    cycle=0,
                    generation=0,
                    regime="weekly_report",
                    candidates_tested=report.stats.n_trades,
                    best_sharpe=report.stats.win_rate * 3.0,
                    avg_sharpe=report.stats.avg_pnl_pct / 100,
                    saved_to_memory=0,
                    source="weekly_report_agent",
                )
            )
        except Exception:
            pass


@dataclass
class WeeklyReport:
    """Résultat complet d'un rapport hebdomadaire."""

    stats: WeeklyStats
    improvements: list[str]
    text_summary: str
    generated_at: datetime = field(default_factory=datetime.now)

    def as_dict(self) -> dict[str, Any]:
        s = self.stats
        return {
            "period_start": s.period_start.isoformat(),
            "period_end": s.period_end.isoformat(),
            "n_trades": s.n_trades,
            "win_rate": s.win_rate,
            "total_pnl_pct": s.total_pnl_pct,
            "avg_pnl_pct": s.avg_pnl_pct,
            "max_drawdown_pct": s.max_drawdown_pct,
            "best_trade_pct": s.best_trade_pct,
            "worst_trade_pct": s.worst_trade_pct,
            "best_regime": s.best_regime,
            "worst_regime": s.worst_regime,
            "blacklisted_strategies": s.blacklisted_strategies,
            "improvements": self.improvements,
            "generated_at": self.generated_at.isoformat(),
        }
