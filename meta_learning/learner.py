"""
Meta Learner — Cherche meilleure decision basee sur contexte passe
Algo: find similar context → retourne decision avec meilleure performance
"""

from typing import Any
from meta_learning.memory import MetaMemory
from meta_learning.similarity import SimilarityEngine


class MetaLearner:
    def __init__(self, memory: MetaMemory | None = None, similarity_engine: SimilarityEngine | None = None):
        self.memory = memory or MetaMemory()
        self.similarity_engine = similarity_engine or SimilarityEngine()

    def find_best_decision(self, context: dict[str, Any], min_score: float = 0.5) -> dict[str, Any] | None:
        """
        Trouve la meilleure decision passée pour un contexte similaire.

        Return:
            decision dict ou None si pas de match suffisant
        """
        candidates = [e.context for e in self.memory.get_all()]
        if not candidates:
            return None

        best_match_context, best_score = self.similarity_engine.find_best_match(context, candidates)
        if best_score < min_score:
            return None

        for entry in self.memory.get_all():
            if entry.context == best_match_context:
                perf = float(entry.performance.get("pnl_pct", 0.0))
                return {
                    "decision": entry.decision,
                    "performance": perf,
                    "similarity_score": best_score,
                }

        return None

    def get_best_by_regime(self, regime: str, top_n: int = 3) -> list[dict[str, Any]]:
        """
        Retourne top N decisions pour un regime.
        """
        entries = self.memory.get_by_regime(regime)
        if not entries:
            return []

        sorted_entries = sorted(
            entries,
            key=lambda e: float(e.performance.get("pnl_pct", 0.0)),
            reverse=True
        )
        return [
            {
                "decision": e.decision,
                "performance": e.performance,
            }
            for e in sorted_entries[:top_n]
        ]

    def learn_from_trade(
        self,
        context: dict[str, Any],
        decision: dict[str, Any],
        pnl_pct: float,
        pnl_usd: float | None = None,
    ) -> None:
        """
        Apprend d'un trade execute.
        """
        self.memory.add(
            context=context,
            decision=decision,
            performance={
                "pnl_pct": pnl_pct,
                "pnl_usd": pnl_usd or 0.0,
                "win": pnl_pct > 0,
            }
        )

    def get_stats(self, regime: str | None = None) -> dict[str, Any]:
        """
        Statistiques d'apprentissage.
        """
        entries = self.memory.get_by_regime(regime) if regime else self.memory.get_all()
        if not entries:
            return {}

        pnls = [float(e.performance.get("pnl_pct", 0.0)) for e in entries]
        wins = sum(1 for p in pnls if p > 0)
        total = len(pnls)

        return {
            "total": total,
            "winrate": wins / total if total else 0.0,
            "avg_pnl_pct": sum(pnls) / total if total else 0.0,
            "max_pnl_pct": max(pnls) if pnls else 0.0,
            "min_pnl_pct": min(pnls) if pnls else 0.0,
        }
