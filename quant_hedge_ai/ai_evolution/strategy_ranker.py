"""
strategy_ranker.py — Self-Learning Strategy Ranking

Le bot note ses propres stratégies en temps réel selon :
  - Sharpe live (calculé sur les trades réels)
  - Win rate réel
  - Max drawdown observé
  - Performance par régime de marché
  - Robustesse Monte Carlo (si disponible)

Puis automatiquement :
  - Promeut les stratégies gagnantes (score élevé → utilisées plus souvent)
  - Rétrograde les perdantes (score faible → usage réduit → blacklist si seuil)
  - Oublie les stratégies stales (pas utilisées depuis N cycles)

Intégration :
    ranker = StrategyRanker()
    ranker.record_trade(strategy_name, regime, pnl_pct, sharpe, win_rate)
    top = ranker.top_strategies(regime, n=5)
    ranker.auto_demote()   # appelé à chaque cycle
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.ai_evolution.strategy_ranker")
_DB_PATH = Path(os.getenv("RANKER_DB", "databases/strategy_ranking.json"))


@dataclass
class StrategyScore:
    """Score cumulé d'une stratégie par régime."""

    name: str
    regime: str

    # Métriques cumulées
    trades: int = 0
    wins: int = 0
    total_pnl: float = 0.0
    total_sharpe: float = 0.0
    max_drawdown: float = 0.0  # pire drawdown observé (positif = bad)
    monte_carlo_survival: float = 1.0  # [0, 1] issu du stress test

    # Confiance progressive (décroissance exponentielle sur pertes consécutives)
    confidence_score: float = 1.0  # [0.1, 1.0] — multiplicateur de taille en probation
    probation_alerted: bool = False  # True si alerte 20-trades déjà envoyée

    # Méta
    first_seen: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    promoted: int = 0  # nb de fois promu
    demoted: int = 0  # nb de fois rétrogradé
    blacklisted: bool = False

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades > 0 else 0.0

    @property
    def avg_sharpe(self) -> float:
        return self.total_sharpe / self.trades if self.trades > 0 else 0.0

    @property
    def avg_pnl(self) -> float:
        return self.total_pnl / self.trades if self.trades > 0 else 0.0

    def composite_score(self) -> float:
        """
        Score composite [0, 100].

        Pondération :
          30% Sharpe moyen          (cap 3.0)
          25% Win rate              (0→1)
          20% PnL moyen par trade   (cap ±10%)
          15% Max drawdown penalty  (moins c'est bien)
          10% Monte Carlo survival  (0→1)
        """
        if self.trades < 3:
            return 0.0  # pas assez de données

        sharpe_score = min(1.0, self.avg_sharpe / 3.0) * 30
        wr_score = self.win_rate * 25
        pnl_score = min(1.0, max(-1.0, self.avg_pnl / 0.10)) * 10 + 10
        dd_score = max(0.0, 1.0 - self.max_drawdown / 0.10) * 15
        mc_score = self.monte_carlo_survival * 10

        return round(sharpe_score + wr_score + pnl_score + dd_score + mc_score, 2)

    def staleness_days(self) -> float:
        return (time.time() - self.last_used) / 86400

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "regime": self.regime,
            "trades": self.trades,
            "wins": self.wins,
            "total_pnl": round(self.total_pnl, 4),
            "total_sharpe": round(self.total_sharpe, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "monte_carlo": self.monte_carlo_survival,
            "first_seen": self.first_seen,
            "last_used": self.last_used,
            "promoted": self.promoted,
            "demoted": self.demoted,
            "blacklisted": self.blacklisted,
            "confidence_score": round(self.confidence_score, 4),
            "probation_alerted": self.probation_alerted,
            "composite": self.composite_score(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyScore":
        s = cls(name=d["name"], regime=d["regime"])
        s.trades = d.get("trades", 0)
        s.wins = d.get("wins", 0)
        s.total_pnl = d.get("total_pnl", 0.0)
        s.total_sharpe = d.get("total_sharpe", 0.0)
        s.max_drawdown = d.get("max_drawdown", 0.0)
        s.monte_carlo_survival = d.get("monte_carlo", 1.0)
        s.first_seen = d.get("first_seen", time.time())
        s.last_used = d.get("last_used", time.time())
        s.promoted = d.get("promoted", 0)
        s.demoted = d.get("demoted", 0)
        s.blacklisted = d.get("blacklisted", False)
        s.confidence_score = d.get("confidence_score", 1.0)
        s.probation_alerted = d.get("probation_alerted", False)
        return s


class StrategyRanker:
    """
    Système de notation auto-apprenant des stratégies.

    Cycle de vie d'une stratégie :
      NOUVEAU → EN_TEST (< 10 trades) → ACTIF → PROMU / RETROGRADE → BLACKLIST
    """

    PROMOTE_THRESHOLD = float(
        os.getenv("RANKER_PROMOTE_SCORE", "65")
    )  # score ≥ 65 → promu
    DEMOTE_THRESHOLD = float(
        os.getenv("RANKER_DEMOTE_SCORE", "30")
    )  # score ≤ 30 → rétrogradé
    BLACKLIST_DEMOTES = int(
        os.getenv("RANKER_BLACKLIST_DEMOTES", "3")
    )  # 3 rétrogradations → blacklist
    STALE_DAYS = float(os.getenv("RANKER_STALE_DAYS", "7"))  # inactif > 7j → oublié
    MIN_TRADES_RANK = int(os.getenv("RANKER_MIN_TRADES", "5"))  # min trades pour noter

    def __init__(self) -> None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._scores: dict[str, StrategyScore] = {}  # "name::regime" → StrategyScore
        self._events: list[dict] = []
        self._load()

    # ── Enregistrement résultats ───────────────────────────────────────────────

    def record_trade(
        self,
        strategy_name: str,
        regime: str,
        pnl_pct: float,
        sharpe: float = 0.0,
        drawdown: float = 0.0,
        monte_carlo: float = 1.0,
    ) -> StrategyScore:
        """
        Enregistre le résultat d'un trade terminé.
        Déclenche automatiquement promotion/rétrogradation si seuils atteints.
        """
        key = f"{strategy_name}::{regime}"
        score = self._scores.setdefault(
            key, StrategyScore(name=strategy_name, regime=regime)
        )

        score.trades += 1
        score.last_used = time.time()
        score.total_pnl += pnl_pct
        score.total_sharpe += sharpe
        score.max_drawdown = max(score.max_drawdown, drawdown)
        score.monte_carlo_survival = (
            score.monte_carlo_survival * 0.8 + monte_carlo * 0.2
        )
        is_win = pnl_pct > 0
        if is_win:
            score.wins += 1

        # Confidence EWMA : récupère lentement sur wins, dégrade vite sur losses
        # α=0.25 win → trend haussier sur confiance | α=0.40 loss → pénalité plus rapide
        alpha = 0.25 if is_win else 0.40
        score.confidence_score = max(
            0.1,
            min(
                1.0,
                alpha * (1.0 if is_win else 0.0)
                + (1.0 - alpha) * score.confidence_score,
            ),
        )

        composite = score.composite_score()
        _log.info(
            "[StrategyRanker] %s/%s — trade #%d pnl=%.2f%% composite=%.1f",
            strategy_name,
            regime,
            score.trades,
            pnl_pct * 100,
            composite,
        )

        # Auto-promotion / rétrogradation
        if score.trades >= self.MIN_TRADES_RANK:
            self._auto_rank(score)

        self._save()
        return score

    def record_monte_carlo(
        self, strategy_name: str, regime: str, survival_rate: float
    ) -> None:
        """Met à jour le score Monte Carlo d'une stratégie."""
        key = f"{strategy_name}::{regime}"
        score = self._scores.get(key)
        if score:
            score.monte_carlo_survival = survival_rate
            self._save()

    # ── Consultation ──────────────────────────────────────────────────────────

    def top_strategies(self, regime: str, n: int = 5) -> list[StrategyScore]:
        """Retourne les N meilleures stratégies pour un régime, non blacklistées."""
        candidates = [
            s
            for k, s in self._scores.items()
            if s.regime == regime
            and not s.blacklisted
            and s.trades >= self.MIN_TRADES_RANK
        ]
        return sorted(candidates, key=lambda s: s.composite_score(), reverse=True)[:n]

    def get_score(self, strategy_name: str, regime: str) -> Optional[StrategyScore]:
        return self._scores.get(f"{strategy_name}::{regime}")

    def best_sharpe(self, regime: str) -> float:
        """Retourne le meilleur Sharpe moyen pour un régime."""
        top = self.top_strategies(regime, n=3)
        if not top:
            return 0.0
        return max(s.avg_sharpe for s in top)

    def size_factor(self, strategy_name: str, regime: str) -> float:
        """
        Retourne un facteur [0.1, 1.5] à multiplier à la taille de base.
        Stratégies promues → facteur > 1.0
        Stratégies en probation → facteur réduit par confidence_score
        Stratégies rétrogradées → facteur < 1.0
        """
        score = self.get_score(strategy_name, regime)
        if score is None or score.trades < self.MIN_TRADES_RANK:
            return 1.0  # inconnu → taille neutre
        if score.blacklisted:
            return 0.0
        c = score.composite_score()
        if c >= self.PROMOTE_THRESHOLD:
            base = min(1.5, 1.0 + (c - self.PROMOTE_THRESHOLD) / 100)
        elif c <= self.DEMOTE_THRESHOLD:
            base = max(0.2, c / self.DEMOTE_THRESHOLD * 0.5)
        else:
            base = 1.0
        # Confidence decay : multiplie le facteur de base (zone probation uniquement)
        if score.confidence_score < 1.0:
            base = round(base * score.confidence_score, 3)
        return max(0.1, base)

    def leaderboard(self, n: int = 20) -> list[dict]:
        """Classement global toutes stratégies + régimes confondus."""
        all_scores = [s.to_dict() for s in self._scores.values() if not s.blacklisted]
        return sorted(all_scores, key=lambda d: d["composite"], reverse=True)[:n]

    def blacklisted(self) -> list[dict]:
        return [s.to_dict() for s in self._scores.values() if s.blacklisted]

    def full_report(self) -> dict:
        return {
            "total_strategies": len(self._scores),
            "blacklisted": sum(1 for s in self._scores.values() if s.blacklisted),
            "promoted": sum(1 for s in self._scores.values() if s.promoted > 0),
            "leaderboard": self.leaderboard(10),
            "events": self._events[-20:],
        }

    # ── Maintenance automatique ───────────────────────────────────────────────

    def check_probation_alerts(
        self,
        min_trades: int = 20,
        low_wr_threshold: float = 0.30,
    ) -> list[str]:
        """
        Retourne une liste d'alertes Telegram pour les stratégies en probation critique.

        Déclenchement : trades == min_trades ET win_rate < low_wr_threshold.
        N'alerte qu'une seule fois par stratégie (probation_alerted=True après).
        """
        alerts = []
        for score in self._scores.values():
            if score.blacklisted or score.probation_alerted:
                continue
            if score.trades < min_trades:
                continue
            if score.win_rate < low_wr_threshold:
                score.probation_alerted = True
                msg = (
                    f"PROBATION {score.name}/{score.regime}: "
                    f"{score.trades} trades WR={score.win_rate:.0%} "
                    f"PnL={score.total_pnl:.2%} confiance={score.confidence_score:.0%} "
                    f"— sous surveillance (blacklist à 3 rétrogradations)"
                )
                _log.warning("[StrategyRanker] %s", msg)
                alerts.append(msg)
        if alerts:
            self._save()
        return alerts

    def auto_demote(self) -> list[str]:
        """
        Appelé à chaque cycle. Oublie les stratégies stales.
        Retourne la liste des stratégies oubliées.
        """
        forgotten = []
        for key, score in list(self._scores.items()):
            if score.blacklisted:
                continue
            if (
                score.staleness_days() > self.STALE_DAYS
                and score.trades < self.MIN_TRADES_RANK
            ):
                del self._scores[key]
                forgotten.append(score.name)
                _log.info(
                    "[StrategyRanker] Oublié (stale): %s/%s", score.name, score.regime
                )
        if forgotten:
            self._save()
        return forgotten

    # ── Interne ──────────────────────────────────────────────────────────────

    def _auto_rank(self, score: StrategyScore) -> None:
        c = score.composite_score()
        if c >= self.PROMOTE_THRESHOLD and score.promoted == score.demoted:
            score.promoted += 1
            self._log_event("promoted", score, c)
            _log.info(
                "[StrategyRanker] PROMU: %s/%s (score=%.1f)",
                score.name,
                score.regime,
                c,
            )
        elif c <= self.DEMOTE_THRESHOLD:
            score.demoted += 1
            self._log_event("demoted", score, c)
            _log.warning(
                "[StrategyRanker] RETROGRADE: %s/%s (score=%.1f demotion #%d)",
                score.name,
                score.regime,
                c,
                score.demoted,
            )
            if score.demoted >= self.BLACKLIST_DEMOTES:
                score.blacklisted = True
                self._log_event("blacklisted", score, c)
                _log.error(
                    "[StrategyRanker] BLACKLIST: %s/%s", score.name, score.regime
                )

    def _log_event(self, event: str, score: StrategyScore, composite: float) -> None:
        self._events.append(
            {
                "ts": time.time(),
                "event": event,
                "strategy": score.name,
                "regime": score.regime,
                "composite": composite,
                "trades": score.trades,
                "win_rate": round(score.win_rate, 3),
                "avg_sharpe": round(score.avg_sharpe, 3),
            }
        )
        if len(self._events) > 500:
            self._events = self._events[-500:]

    def _load(self) -> None:
        if not _DB_PATH.exists():
            return
        try:
            data = json.loads(_DB_PATH.read_text(encoding="utf-8"))
            for d in data.get("scores", []):
                key = f"{d['name']}::{d['regime']}"
                self._scores[key] = StrategyScore.from_dict(d)
            self._events = data.get("events", [])
            _log.info("[StrategyRanker] Chargé: %d stratégies", len(self._scores))
        except Exception as exc:
            _log.warning("[StrategyRanker] Erreur chargement: %s", exc)

    def _save(self) -> None:
        try:
            data = {
                "scores": [s.to_dict() for s in self._scores.values()],
                "events": self._events[-200:],
            }
            _DB_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            _log.warning("[StrategyRanker] Erreur sauvegarde: %s", exc)
