"""
dip/modules/explainability.py — D08 Explainability Score Engine.

Calcule un score d'explicabilité (0.0→1.0) pour chaque décision, mesurant
à quel point la décision est compréhensible par un humain.

5 dimensions pondérées:
  1. Path Simplicity       (0.20) — profondeur du pipeline
  2. Causal Clarity        (0.25) — clarté de l'arbre causal
  3. Threshold Stability   (0.20) — stabilité des seuils
  4. Historical Consistency(0.20) — cohérence avec l'historique
  5. Reasoning Readability (0.15) — lisibilité des raisonnements

Grades A+→F conformes à la spec.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from dip.core.store import DIPStore, LRUCache
from dip.core.types import now_us
from dip.modules.causal_tree import CausalTree, get_causal_tree_engine
from dip.modules.decision_graph import DecisionGraph, get_graph_engine

if TYPE_CHECKING:
    from observability.decision_observation import DecisionObservation


# ── Grade scale ───────────────────────────────────────────────────────────────

_GRADE_SCALE = [
    ("A+", 0.95, 1.01),
    ("A", 0.90, 0.95),
    ("A-", 0.85, 0.90),
    ("B+", 0.80, 0.85),
    ("B", 0.75, 0.80),
    ("B-", 0.70, 0.75),
    ("C+", 0.65, 0.70),
    ("C", 0.60, 0.65),
    ("C-", 0.55, 0.60),
    ("D", 0.50, 0.55),
    ("F", 0.00, 0.50),
]


def _grade(score: float) -> str:
    for g, low, high in _GRADE_SCALE:
        if low <= score < high:
            return g
    return "F"


# ── Types ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DimensionScore:
    dimension: str
    score: float
    weight: float
    detail: str


@dataclass(frozen=True)
class ExplainabilityRecommendation:
    dimension: str
    recommendation: str
    priority: str  # LOW, MEDIUM, HIGH, CRITICAL
    estimated_impact: float


@dataclass(frozen=True)
class ExplainabilityScore:
    explainability_id: str
    packet_id: str
    global_score: float
    grade: str
    dimensions: tuple[DimensionScore, ...]
    recommendations: tuple[ExplainabilityRecommendation, ...]
    computed_at_us: int


@dataclass(frozen=True)
class LowExplainabilityReport:
    packet_id: str
    symbol: str
    direction: str
    global_score: float
    grade: str
    worst_dimension: str
    primary_recommendation: str


@dataclass(frozen=True)
class ExplainabilityTrend:
    layer: str
    period_days: int
    avg_score: float
    trend_direction: str
    sample_count: int


# ── Scorers ───────────────────────────────────────────────────────────────────


def _score_path_simplicity(graph: DecisionGraph) -> tuple[float, str]:
    """Plus le pipeline est court, plus il est simple à expliquer."""
    depth = graph.metrics.depth
    # 1-2 couches = 1.0, 12 couches = 0.5, >12 = diminue encore
    score = max(0.3, 1.0 - (depth - 1) * 0.045)
    return round(score, 3), f"{depth} couche(s) traversée(s)"


def _score_causal_clarity(tree: CausalTree) -> tuple[float, str]:
    """Plus l'arbre causal est simple (peu de branches), plus il est clair."""
    n_paths = len(tree.causal_paths)
    n_factors = len(tree.root_cause.contributing_factors)
    # 1 chemin, peu de facteurs = score élevé
    score = max(0.3, 1.0 - (n_paths - 1) * 0.15 - n_factors * 0.05)
    return (
        round(score, 3),
        f"{n_paths} chemin(s) causal(aux), {n_factors} facteur(s) contributif(s)",
    )


def _score_threshold_stability(graph: DecisionGraph) -> tuple[float, str]:
    """
    Mesure la stabilité des seuils: si les deltas de confiance sont cohérents
    (pas trop de variance entre couches), les seuils sont stables.
    """
    if not graph.edges:
        return 0.8, "aucune arête (pipeline trivial)"
    deltas = [abs(e.confidence_delta) for e in graph.edges]
    mean = sum(deltas) / len(deltas)
    variance = sum((d - mean) ** 2 for d in deltas) / len(deltas)
    # Faible variance = seuils stables
    score = max(0.4, 1.0 - min(1.0, variance * 10))
    return round(score, 3), f"variance des deltas={variance:.4f}"


def _score_historical_consistency(
    store: DIPStore,
    packet_id: str,
    symbol: str,
    status: str,
    limit: int = 50,
) -> tuple[float, str]:
    """
    Compare avec les décisions passées similaires (même symbole).
    Si la majorité ont le même résultat, la décision est cohérente.
    """
    rows = store.get_decisions(symbol=symbol, limit=limit)
    if len(rows) < 5:
        return 0.6, f"historique insuffisant ({len(rows)} décisions)"

    same_result = sum(1 for r in rows if r.get("status") == status)
    consistency = same_result / len(rows)
    return (
        round(consistency, 3),
        f"{same_result}/{len(rows)} décisions similaires avec même résultat",
    )


def _score_reasoning_readability(obs: "DecisionObservation") -> tuple[float, str]:
    """
    Mesure la lisibilité des raisonnements: les raisons doivent être courtes et claires.
    """
    # Compte les blockers avec une raison explicite
    explicit_reasons = sum(
        [
            1 if obs.meta_reason and obs.meta_reason != "OK" else 0,
            1 if obs.notrade_reason else 0,
            1 if obs.portfolio_reason else 0,
            1 if obs.mistake_reason else 0,
            1 if obs.override_reason else 0,
            1 if obs.arbitration_decision else 0,
        ]
    )
    total_blockers = len(obs.all_blockers)
    # Si tous les blockers ont une raison explicite = parfait
    if total_blockers == 0:
        return 0.85, "trade approuvé, pas de raison de rejet requise"
    ratio = min(1.0, explicit_reasons / total_blockers)
    score = 0.5 + ratio * 0.5
    return (
        round(score, 3),
        f"{explicit_reasons}/{total_blockers} blockers avec raison explicite",
    )


# ── Recommendations ───────────────────────────────────────────────────────────

_RECOMMENDATIONS: dict[str, str] = {
    "path_simplicity": (
        "Le pipeline est long. Envisager de regrouper les couches similaires "
        "ou de documenter leur séquence dans le CLAUDE.md."
    ),
    "causal_clarity": (
        "L'arbre causal a plusieurs branches. Documenter la règle de résolution "
        "de conflit entre couches pour améliorer la lisibilité."
    ),
    "threshold_stability": (
        "Les deltas de confiance entre couches varient beaucoup. "
        "Vérifier la calibration des seuils de chaque couche."
    ),
    "historical_consistency": (
        "La décision est atypique par rapport à l'historique. "
        "Vérifier si le contexte de marché a changé récemment."
    ),
    "reasoning_readability": (
        "Certaines couches bloquantes n'ont pas de raison explicite. "
        "Enrichir les messages de rejet pour améliorer l'auditabilité."
    ),
}


# ── Engine ─────────────────────────────────────────────────────────────────────


class ExplainabilityScoreEngine:
    """D08 — Score d'explicabilité par décision."""

    _WEIGHTS = {
        "path_simplicity": 0.20,
        "causal_clarity": 0.25,
        "threshold_stability": 0.20,
        "historical_consistency": 0.20,
        "reasoning_readability": 0.15,
    }

    def __init__(self) -> None:
        self._graph_engine = get_graph_engine()
        self._causal_engine = get_causal_tree_engine()
        self._cache: LRUCache[ExplainabilityScore] = LRUCache(
            max_entries=10_000, ttl_seconds=86_400
        )
        self._store = DIPStore.instance()

    def on_observation(self, obs: "DecisionObservation") -> None:
        graph = self._graph_engine.get_graph(obs.packet_id)
        tree = self._causal_engine.build_causal_tree(obs.packet_id)
        if not graph or not tree:
            return
        score = self._compute(obs, graph, tree)
        self._cache.set(score.packet_id, score)
        self._persist(obs.packet_id, score)

    def compute_score(self, packet_id: str) -> Optional[ExplainabilityScore]:
        return self._cache.get(packet_id)

    def get_breakdown(self, packet_id: str) -> Optional[tuple[DimensionScore, ...]]:
        score = self.compute_score(packet_id)
        return score.dimensions if score else None

    def get_low_explainability_packets(
        self, hours: int = 168, threshold: float = 0.5
    ) -> list[LowExplainabilityReport]:
        start_us = now_us() - hours * 3_600_000_000
        rows = self._store.get_decisions(start_us=start_us, limit=10_000)
        reports = []
        for r in rows:
            score_val = r.get("explainability_score")
            if score_val is not None and float(score_val) < threshold:
                reports.append(
                    LowExplainabilityReport(
                        packet_id=r["packet_id"],
                        symbol=r.get("symbol", ""),
                        direction=r.get("direction", ""),
                        global_score=float(score_val),
                        grade=r.get("explainability_grade", "F"),
                        worst_dimension="unknown",
                        primary_recommendation="Voir détail du score.",
                    )
                )
        return sorted(reports, key=lambda x: x.global_score)

    def _compute(
        self,
        obs: "DecisionObservation",
        graph: DecisionGraph,
        tree: CausalTree,
    ) -> ExplainabilityScore:
        dims: list[DimensionScore] = []
        recs: list[ExplainabilityRecommendation] = []

        scores_raw = {}

        ps_score, ps_detail = _score_path_simplicity(graph)
        scores_raw["path_simplicity"] = ps_score
        dims.append(
            DimensionScore(
                "path_simplicity", ps_score, self._WEIGHTS["path_simplicity"], ps_detail
            )
        )

        cc_score, cc_detail = _score_causal_clarity(tree)
        scores_raw["causal_clarity"] = cc_score
        dims.append(
            DimensionScore(
                "causal_clarity", cc_score, self._WEIGHTS["causal_clarity"], cc_detail
            )
        )

        ts_score, ts_detail = _score_threshold_stability(graph)
        scores_raw["threshold_stability"] = ts_score
        dims.append(
            DimensionScore(
                "threshold_stability",
                ts_score,
                self._WEIGHTS["threshold_stability"],
                ts_detail,
            )
        )

        hc_score, hc_detail = _score_historical_consistency(
            self._store,
            obs.packet_id,
            obs.symbol,
            "APPROVED" if obs.trade_allowed else "REJECTED",
        )
        scores_raw["historical_consistency"] = hc_score
        dims.append(
            DimensionScore(
                "historical_consistency",
                hc_score,
                self._WEIGHTS["historical_consistency"],
                hc_detail,
            )
        )

        rr_score, rr_detail = _score_reasoning_readability(obs)
        scores_raw["reasoning_readability"] = rr_score
        dims.append(
            DimensionScore(
                "reasoning_readability",
                rr_score,
                self._WEIGHTS["reasoning_readability"],
                rr_detail,
            )
        )

        # Score global pondéré
        global_score = sum(scores_raw[k] * self._WEIGHTS[k] for k in scores_raw)
        global_score = round(max(0.0, min(1.0, global_score)), 4)

        # Recommendations pour dimensions < 0.7
        for k, s in scores_raw.items():
            if s < 0.70:
                priority = "HIGH" if s < 0.5 else ("MEDIUM" if s < 0.6 else "LOW")
                recs.append(
                    ExplainabilityRecommendation(
                        dimension=k,
                        recommendation=_RECOMMENDATIONS.get(
                            k, "Améliorer la lisibilité."
                        ),
                        priority=priority,
                        estimated_impact=round((0.70 - s) * self._WEIGHTS[k], 3),
                    )
                )

        exp_id = f"exp_{obs.packet_id}"
        return ExplainabilityScore(
            explainability_id=exp_id,
            packet_id=obs.packet_id,
            global_score=global_score,
            grade=_grade(global_score),
            dimensions=tuple(dims),
            recommendations=tuple(recs),
            computed_at_us=now_us(),
        )

    def _persist(self, packet_id: str, score: ExplainabilityScore) -> None:
        try:
            self._store._conn.execute(
                """UPDATE dip_decisions
                   SET explainability_score = ?, explainability_grade = ?
                   WHERE packet_id = ?""",
                (score.global_score, score.grade, packet_id),
            )
            self._store._conn.commit()
        except Exception:
            pass


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[ExplainabilityScoreEngine] = None
_engine_lock = threading.Lock()


def get_explainability_engine() -> ExplainabilityScoreEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = ExplainabilityScoreEngine()
    return _engine
