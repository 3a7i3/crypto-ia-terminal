"""
trade_postmortem.py — Analyse post-trade pour apprentissage automatique.

Pour chaque trade fermé, analyse :
  - PnL réalisé vs attendu
  - Qualité du signal d'entrée (score, régime, confirmation MTF)
  - Écart entre Sharpe mémorisé et performance réelle

Résultats :
  - Blackliste les combinaisons stratégie+régime perdantes
  - Sauvegarde les statistiques dans StrategyMemoryStore
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_LOSS_THRESHOLD_PCT: float = -2.0   # PnL % en-dessous duquel c'est une perte
_MIN_TRADES_FOR_BLACKLIST: int = 3   # N pertes consécutives pour blacklister


@dataclass
class TradeRecord:
    """Représente un trade fermé avec son contexte d'entrée."""

    symbol: str
    action: str                  # BUY | SELL
    entry_price: float
    exit_price: float
    size: float
    regime: str
    strategy_name: str
    entry_score: int = 0
    entry_signal_confirmed: bool = False
    entry_strength: float = 0.0
    timestamp_open: float = field(default_factory=time.time)
    timestamp_close: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    @property
    def pnl(self) -> float:
        if self.action == "BUY":
            return (self.exit_price - self.entry_price) * self.size
        return (self.entry_price - self.exit_price) * self.size

    @property
    def pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        if self.action == "BUY":
            return (self.exit_price - self.entry_price) / self.entry_price * 100
        return (self.entry_price - self.exit_price) / self.entry_price * 100

    @property
    def is_loss(self) -> bool:
        return self.pnl_pct < _LOSS_THRESHOLD_PCT

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "size": self.size,
            "pnl": round(self.pnl, 4),
            "pnl_pct": round(self.pnl_pct, 4),
            "regime": self.regime,
            "strategy_name": self.strategy_name,
            "entry_score": self.entry_score,
            "entry_signal_confirmed": self.entry_signal_confirmed,
            "is_loss": self.is_loss,
        }


@dataclass
class PostmortemReport:
    """Résultat d'une analyse post-trade."""

    trade: TradeRecord
    verdict: str                         # "win" | "loss" | "neutral"
    root_cause: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    blacklisted: bool = False
    blacklist_key: str = ""

    def as_dict(self) -> dict:
        return {
            "trade": self.trade.as_dict(),
            "verdict": self.verdict,
            "root_cause": self.root_cause,
            "recommendations": self.recommendations,
            "blacklisted": self.blacklisted,
            "blacklist_key": self.blacklist_key,
        }


class TradePostMortem:
    """
    Analyse les trades fermés et ajuste la mémoire stratégique.

    Usage:
        pm = TradePostMortem()
        report = pm.analyze(trade)
        # report.blacklisted indique si la stratégie a été bannie pour ce régime
    """

    def __init__(self, memory_store=None, signal_engine=None) -> None:
        self._memory = memory_store
        self._signal_engine = signal_engine
        self._loss_streaks: dict[str, int] = {}   # key: strategy+regime → count pertes consécutives
        self._all_reports: list[PostmortemReport] = []

    # ── API principale ─────────────────────────────────────────────────────────

    def analyze(self, trade: TradeRecord) -> PostmortemReport:
        """
        Analyse un trade fermé et retourne un rapport post-mortem.
        Peut déclencher une blacklist si trop de pertes consécutives.
        """
        verdict = self._classify(trade)
        causes = self._identify_root_cause(trade, verdict)
        recommendations = self._build_recommendations(trade, verdict, causes)

        blacklisted = False
        blacklist_key = ""

        if verdict == "loss":
            blacklist_key = f"{trade.strategy_name}::{trade.regime}"
            self._loss_streaks[blacklist_key] = self._loss_streaks.get(blacklist_key, 0) + 1

            if self._loss_streaks[blacklist_key] >= _MIN_TRADES_FOR_BLACKLIST:
                blacklisted = self._apply_blacklist(trade.strategy_name, trade.regime)
                if blacklisted:
                    self._loss_streaks[blacklist_key] = 0  # reset après blacklist
        else:
            # Une victoire réinitialise le compteur de pertes consécutives
            blacklist_key = f"{trade.strategy_name}::{trade.regime}"
            self._loss_streaks[blacklist_key] = 0

        report = PostmortemReport(
            trade=trade,
            verdict=verdict,
            root_cause=causes,
            recommendations=recommendations,
            blacklisted=blacklisted,
            blacklist_key=blacklist_key,
        )
        self._all_reports.append(report)
        self._emit_event(report)

        logger.info(
            "[Postmortem] %s %s → %s | PnL=%.2f%% | causes=%s | blacklisted=%s",
            trade.symbol, trade.action, verdict, trade.pnl_pct, causes, blacklisted,
        )
        return report

    def regime_stats(self, regime: str) -> dict:
        """Statistiques des trades pour un régime donné."""
        relevant = [r for r in self._all_reports if r.trade.regime == regime]
        if not relevant:
            return {"regime": regime, "n_trades": 0}

        wins = sum(1 for r in relevant if r.verdict == "win")
        losses = sum(1 for r in relevant if r.verdict == "loss")
        pnls = [r.trade.pnl_pct for r in relevant]
        avg_pnl = sum(pnls) / len(pnls)

        return {
            "regime": regime,
            "n_trades": len(relevant),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / len(relevant), 3),
            "avg_pnl_pct": round(avg_pnl, 3),
            "blacklisted_strategies": [
                r.blacklist_key for r in relevant if r.blacklisted
            ],
        }

    def strategy_stats(self, strategy_name: str) -> dict:
        """Statistiques d'une stratégie sur tous les régimes."""
        relevant = [r for r in self._all_reports if r.trade.strategy_name == strategy_name]
        if not relevant:
            return {"strategy": strategy_name, "n_trades": 0}

        wins = sum(1 for r in relevant if r.verdict == "win")
        losses = sum(1 for r in relevant if r.verdict == "loss")
        pnls = [r.trade.pnl_pct for r in relevant]

        return {
            "strategy": strategy_name,
            "n_trades": len(relevant),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / len(relevant), 3) if relevant else 0.0,
            "avg_pnl_pct": round(sum(pnls) / len(pnls), 3) if pnls else 0.0,
            "best_regime": self._best_regime_for(strategy_name),
            "worst_regime": self._worst_regime_for(strategy_name),
        }

    def summary(self) -> dict:
        """Résumé global de tous les trades analysés."""
        if not self._all_reports:
            return {"n_trades": 0}

        wins = sum(1 for r in self._all_reports if r.verdict == "win")
        losses = sum(1 for r in self._all_reports if r.verdict == "loss")
        blacklisted = sum(1 for r in self._all_reports if r.blacklisted)
        pnls = [r.trade.pnl_pct for r in self._all_reports]

        return {
            "n_trades": len(self._all_reports),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / len(self._all_reports), 3),
            "avg_pnl_pct": round(sum(pnls) / len(pnls), 3),
            "total_blacklists": blacklisted,
            "active_loss_streaks": {k: v for k, v in self._loss_streaks.items() if v > 0},
        }

    # ── Logique interne ───────────────────────────────────────────────────────

    def _classify(self, trade: TradeRecord) -> str:
        if trade.pnl_pct > 1.0:
            return "win"
        if trade.is_loss:
            return "loss"
        return "neutral"

    def _identify_root_cause(self, trade: TradeRecord, verdict: str) -> list[str]:
        causes: list[str] = []
        if verdict != "loss":
            return causes

        if not trade.entry_signal_confirmed:
            causes.append("signal_non_confirme")

        if trade.entry_score < 60:
            causes.append(f"score_entree_faible_{trade.entry_score}")

        if trade.regime in ("flash_crash", "high_volatility_regime"):
            causes.append(f"regime_defavorable_{trade.regime}")

        if trade.entry_strength < 0.5:
            causes.append(f"force_signal_faible_{trade.entry_strength:.2f}")

        if not causes:
            causes.append("cause_inconnue")

        return causes

    def _build_recommendations(
        self, trade: TradeRecord, verdict: str, causes: list[str]
    ) -> list[str]:
        recs: list[str] = []

        if "signal_non_confirme" in causes:
            recs.append("Exiger signal_confirmed=True avant entrée")

        if any("score_entree_faible" in c for c in causes):
            recs.append("Élever SIGNAL_MIN_SCORE (ex: 75)")

        if any("regime_defavorable" in c for c in causes):
            recs.append(f"Éviter le trading en régime {trade.regime}")

        if any("force_signal_faible" in c for c in causes):
            recs.append("Augmenter min_strength du MultiTimeframeSignal")

        if verdict == "win" and trade.entry_score >= 80:
            recs.append("Stratégie haute performance — augmenter la taille de position")

        return recs

    def _apply_blacklist(self, strategy_name: str, regime: str) -> bool:
        """Blackliste la stratégie pour ce régime dans la mémoire ET dans le moteur."""
        try:
            if self._memory is not None:
                self._memory.blacklist_regime(strategy_name, regime)

            if self._signal_engine is not None:
                self._signal_engine.blacklist_regime(regime)

            logger.warning(
                "[Postmortem] BLACKLIST %s pour régime %s (%d pertes consécutives)",
                strategy_name, regime, _MIN_TRADES_FOR_BLACKLIST,
            )
            return True
        except Exception as exc:
            logger.error("[Postmortem] Erreur blacklist: %s", exc)
            return False

    def _emit_event(self, report: PostmortemReport) -> None:
        try:
            from event_bus.bus import EventBus
            from event_bus.events import DrawdownAlertEvent
            if report.blacklisted:
                EventBus.get().emit(
                    DrawdownAlertEvent(
                        current_drawdown_pct=abs(report.trade.pnl_pct),
                        max_allowed_pct=abs(_LOSS_THRESHOLD_PCT),
                        symbol=report.trade.symbol,
                        action_taken=f"blacklist:{report.trade.strategy_name}:{report.trade.regime}",
                        source="trade_postmortem",
                    )
                )
        except Exception:
            pass

    def _best_regime_for(self, strategy_name: str) -> str:
        relevant = [
            r for r in self._all_reports
            if r.trade.strategy_name == strategy_name and r.verdict == "win"
        ]
        if not relevant:
            return "none"
        by_regime: dict[str, int] = {}
        for r in relevant:
            by_regime[r.trade.regime] = by_regime.get(r.trade.regime, 0) + 1
        return max(by_regime, key=lambda k: by_regime[k])

    def _worst_regime_for(self, strategy_name: str) -> str:
        relevant = [
            r for r in self._all_reports
            if r.trade.strategy_name == strategy_name and r.verdict == "loss"
        ]
        if not relevant:
            return "none"
        by_regime: dict[str, int] = {}
        for r in relevant:
            by_regime[r.trade.regime] = by_regime.get(r.trade.regime, 0) + 1
        return max(by_regime, key=lambda k: by_regime[k])
