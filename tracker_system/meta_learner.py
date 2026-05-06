"""
meta_learner.py — Couche méta-apprentissage contextuel

Phase 1 : choisit la stratégie d'exit (exit_type + paramètres) selon le contexte.
Phase 2 : strategy + exit (à venir).
Phase 3 : risk sizing (à venir).

Algorithme :
  1. Calcule un score de similarité pour chaque entrée mémoire vs contexte courant.
  2. Garde les entrées avec score ≥ threshold (défaut 1).
  3. Parmi les candidates, retourne la décision avec le meilleur Sharpe.
  4. Si aucun candidat → None (fallback aux paramètres par défaut).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tracker_system.meta_memory import MetaMemory, DEFAULT_PATH

VOLATILITY_BUCKETS = ["low", "medium", "high"]


def _volatility_bucket(vol: float) -> str:
    """Bucketise la volatilité (fraction, ex. 0.015 → 1.5%)."""
    if vol < 0.01:
        return "low"
    if vol < 0.025:
        return "medium"
    return "high"


def _similarity(ctx_a: dict, ctx_b: dict) -> int:
    """Score de similarité 0–2 entre deux contextes."""
    score = 0
    if ctx_a.get("regime") == ctx_b.get("regime"):
        score += 1
    if ctx_a.get("volatility_bucket") == ctx_b.get("volatility_bucket"):
        score += 1
    return score


class MetaLearner:
    """
    Sélectionne la meilleure configuration d'exit selon le contexte de marché.

    Usage :
        learner = MetaLearner()
        decision = learner.find_best({"regime": "bull_trend", "volatility": 0.015})
        # → {"exit_type": "tp_sl", "tp": 0.02, "sl": 0.01, "trail_pct": None}
        # → None si aucun historique compatible
    """

    def __init__(self, memory_path: Path = DEFAULT_PATH) -> None:
        self.memory = MetaMemory(path=memory_path)

    # ── Recherche ─────────────────────────────────────────────────────────────

    def _build_context(self, raw: dict) -> dict:
        """Normalise un contexte brut (ajoute volatility_bucket si absent)."""
        ctx = dict(raw)
        if "volatility_bucket" not in ctx and "volatility" in ctx:
            ctx["volatility_bucket"] = _volatility_bucket(ctx.pop("volatility"))
        elif "volatility" in ctx:
            ctx.pop("volatility")
        return ctx

    def find_best(self, context: dict, min_similarity: int = 1) -> dict | None:
        """
        Retourne la meilleure décision pour le contexte donné.
        `min_similarity` : score minimum pour être candidat (0=tous, 1=même régime, 2=exact).
        """
        ctx = self._build_context(context)

        candidates: list[tuple[int, dict]] = []
        for entry in self.memory.all():
            sim = _similarity(ctx, entry["context"])
            if sim >= min_similarity:
                candidates.append((sim, entry))

        if not candidates:
            return None

        # Trie par similarité décroissante, puis par Sharpe décroissant
        candidates.sort(key=lambda x: (x[0], x[1]["performance"].get("sharpe", 0.0)),
                        reverse=True)

        # Si plusieurs candidates avec même similarité → meilleur Sharpe
        top_sim = candidates[0][0]
        top = [e for s, e in candidates if s == top_sim]
        best = max(top, key=lambda e: e["performance"].get("sharpe", 0.0))
        return dict(best["decision"])

    # ── Apprentissage ─────────────────────────────────────────────────────────

    def learn(
        self,
        context: dict,
        decision: dict,
        performance: dict,
    ) -> None:
        """Enregistre le résultat d'une stratégie dans un contexte donné."""
        ctx = self._build_context(context)
        self.memory.add(ctx, decision, performance)

    # ── Chargement depuis backtester ──────────────────────────────────────────

    def ingest_backtest(self, backtest_results: dict) -> int:
        """
        Ingère les résultats d'auto_backtester.run_backtest() dans la mémoire.

        backtest_results[regime]["best"] → décision
        Calcule une performance synthétique à partir des métriques du backtester.

        Retourne le nombre d'entrées ajoutées/mises à jour.
        """
        count = 0
        for key, data in backtest_results.items():
            if key.startswith("_"):
                continue
            best = data.get("best", {})
            if not best:
                continue

            regime = key
            exit_type = best.get("type", "tp_sl")

            decision: dict[str, Any] = {"exit_type": exit_type}
            if exit_type in ("tp_sl", "hybrid"):
                decision["tp"] = best.get("tp")
                decision["sl"] = best.get("sl")
            if exit_type in ("trailing", "hybrid"):
                decision["trail_pct"] = best.get("trail_pct")

            win_rate = best.get("win_rate", 0.0)
            avg_pnl  = best.get("avg", 0.0)
            n        = best.get("n", 0)
            sharpe   = (avg_pnl * win_rate * 10) if win_rate > 0 else 0.0

            performance = {
                "sharpe":   round(sharpe, 4),
                "win_rate": round(win_rate, 4),
                "avg_pnl":  round(avg_pnl, 6),
                "n_trades": n,
            }

            # Contexte : régime seulement (volatility_bucket inconnu à ce stade)
            context = {"regime": regime, "volatility_bucket": "unknown"}
            self.learn(context, decision, performance)
            count += 1

        return count

    # ── Affichage ─────────────────────────────────────────────────────────────

    def summary(self) -> str:
        lines = [f"MetaLearner — {len(self.memory)} entrées en mémoire"]
        for entry in self.memory.all():
            ctx  = entry["context"]
            dec  = entry["decision"]
            perf = entry["performance"]
            lines.append(
                f"  [{ctx.get('regime','?')} / {ctx.get('volatility_bucket','?')}] "
                f"→ {dec.get('exit_type','?')} "
                f"| Sharpe={perf.get('sharpe',0):.3f} "
                f"WR={perf.get('win_rate',0):.0%} "
                f"n={perf.get('n_trades',0)}"
            )
        return "\n".join(lines)
