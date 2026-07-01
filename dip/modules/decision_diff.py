"""
dip/modules/decision_diff.py — D11 Decision Diff Engine.

Compare deux décisions côte-à-côte et identifie les différences
dans le pipeline, les seuils, les résultats et les métriques.

Passif: lit uniquement les données DIP existantes.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

from dip.core.store import DIPStore
from dip.core.types import LayerStatus, now_us
from dip.modules.causal_tree import get_causal_tree_engine
from dip.modules.decision_graph import DecisionGraph, get_graph_engine
from dip.modules.explainability import get_explainability_engine

# ── Types ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LayerDiff:
    layer: str
    status_a: str
    status_b: str
    confidence_a: float
    confidence_b: float
    confidence_delta: float
    status_changed: bool
    reason_a: str
    reason_b: str


@dataclass(frozen=True)
class MetricDiff:
    metric: str
    value_a: float
    value_b: float
    delta: float
    delta_pct: float


@dataclass(frozen=True)
class ContextDiff:
    field: str
    value_a: str
    value_b: str
    changed: bool


@dataclass(frozen=True)
class DecisionDiff:
    diff_id: str
    packet_id_a: str
    packet_id_b: str
    context_diffs: tuple[ContextDiff, ...]
    layer_diffs: tuple[LayerDiff, ...]
    metric_diffs: tuple[MetricDiff, ...]
    divergence_layer: Optional[str]
    outcome_changed: bool
    status_a: str
    status_b: str
    explainability_diff: Optional[MetricDiff]
    summary: str
    created_at_us: int


@dataclass(frozen=True)
class DiffReport:
    total_diffs: int
    layer_changes: int
    outcome_changed: bool
    most_divergent_layer: Optional[str]
    context_changes: tuple[str, ...]
    key_differences: tuple[str, ...]


# ── Engine ─────────────────────────────────────────────────────────────────────


class DecisionDiffEngine:
    """D11 — Comparaison side-by-side de deux décisions."""

    def __init__(self) -> None:
        self._store = DIPStore.instance()
        self._graph_engine = get_graph_engine()
        self._causal_engine = get_causal_tree_engine()
        self._exp_engine = get_explainability_engine()

    def diff(self, packet_id_a: str, packet_id_b: str) -> Optional[DecisionDiff]:
        row_a = self._store.get_decision(packet_id_a)
        row_b = self._store.get_decision(packet_id_b)
        if not row_a or not row_b:
            return None

        graph_a = self._graph_engine.get_graph(packet_id_a)
        graph_b = self._graph_engine.get_graph(packet_id_b)
        if not graph_a or not graph_b:
            return None

        context_diffs = self._diff_context(row_a, row_b)
        layer_diffs = self._diff_layers(graph_a, graph_b)
        metric_diffs = self._diff_metrics(graph_a, graph_b)
        exp_diff = self._diff_explainability(row_a, row_b)

        status_a = row_a.get("status", "?")
        status_b = row_b.get("status", "?")
        outcome_changed = status_a != status_b

        # Trouver la couche de divergence (première couche avec statut différent)
        divergence_layer = next(
            (ld.layer for ld in layer_diffs if ld.status_changed), None
        )

        # Résumé textuel
        parts = []
        if outcome_changed:
            parts.append(f"Résultat différent: {status_a} → {status_b}")
        if divergence_layer:
            parts.append(f"Divergence à '{divergence_layer}'")
        ctx_changes = [cd.field for cd in context_diffs if cd.changed]
        if ctx_changes:
            parts.append(f"Contexte: {', '.join(ctx_changes)}")
        summary = "; ".join(parts) if parts else "Aucune différence significative"

        return DecisionDiff(
            diff_id=f"diff_{packet_id_a[:8]}_{packet_id_b[:8]}_{now_us()}",
            packet_id_a=packet_id_a,
            packet_id_b=packet_id_b,
            context_diffs=tuple(context_diffs),
            layer_diffs=tuple(layer_diffs),
            metric_diffs=tuple(metric_diffs),
            divergence_layer=divergence_layer,
            outcome_changed=outcome_changed,
            status_a=status_a,
            status_b=status_b,
            explainability_diff=exp_diff,
            summary=summary,
            created_at_us=now_us(),
        )

    def get_report(self, diff: DecisionDiff) -> DiffReport:
        layer_changes = sum(1 for ld in diff.layer_diffs if ld.status_changed)
        most_divergent = max(
            diff.layer_diffs,
            key=lambda ld: abs(ld.confidence_delta),
            default=None,
        )
        key_differences = []
        if diff.outcome_changed:
            key_differences.append(f"Résultat: {diff.status_a} → {diff.status_b}")
        for ld in diff.layer_diffs:
            if ld.status_changed:
                key_differences.append(f"{ld.layer}: {ld.status_a} → {ld.status_b}")

        return DiffReport(
            total_diffs=len(diff.layer_diffs) + len(diff.context_diffs),
            layer_changes=layer_changes,
            outcome_changed=diff.outcome_changed,
            most_divergent_layer=most_divergent.layer if most_divergent else None,
            context_changes=tuple(cd.field for cd in diff.context_diffs if cd.changed),
            key_differences=tuple(key_differences[:10]),
        )

    def find_most_similar(
        self, packet_id: str, top_k: int = 5
    ) -> list[tuple[str, float]]:
        """Retourne les packet_ids les plus similaires par score de similarité des graphs."""
        row = self._store.get_decision(packet_id)
        if not row:
            return []
        graph = self._graph_engine.get_graph(packet_id)
        if not graph:
            return []

        rows = self._store.get_decisions(symbol=row.get("symbol"), limit=200)
        scores: list[tuple[str, float]] = []
        for r in rows:
            if r["packet_id"] == packet_id:
                continue
            other_graph = self._graph_engine.get_graph(r["packet_id"])
            if not other_graph:
                continue
            sim = self._graph_similarity(graph, other_graph)
            scores.append((r["packet_id"], sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def _diff_context(self, row_a: dict, row_b: dict) -> list[ContextDiff]:
        fields = ["symbol", "direction", "regime", "personality"]
        diffs = []
        for f in fields:
            va = str(row_a.get(f, ""))
            vb = str(row_b.get(f, ""))
            diffs.append(ContextDiff(field=f, value_a=va, value_b=vb, changed=va != vb))
        return diffs

    def _diff_layers(
        self, graph_a: DecisionGraph, graph_b: DecisionGraph
    ) -> list[LayerDiff]:
        nodes_a = {n.layer: n for n in graph_a.nodes}
        nodes_b = {n.layer: n for n in graph_b.nodes}
        all_layers = list(
            dict.fromkeys(
                [n.layer for n in graph_a.nodes] + [n.layer for n in graph_b.nodes]
            )
        )
        diffs = []
        for layer in all_layers:
            na = nodes_a.get(layer)
            nb = nodes_b.get(layer)
            sa = na.status.value if na else "N/A"
            sb = nb.status.value if nb else "N/A"
            ca = na.confidence_after if na else 0.0
            cb = nb.confidence_after if nb else 0.0
            diffs.append(
                LayerDiff(
                    layer=layer,
                    status_a=sa,
                    status_b=sb,
                    confidence_a=ca,
                    confidence_b=cb,
                    confidence_delta=round(cb - ca, 4),
                    status_changed=sa != sb,
                    reason_a=na.reasoning if na else "",
                    reason_b=nb.reasoning if nb else "",
                )
            )
        return diffs

    def _diff_metrics(
        self, graph_a: DecisionGraph, graph_b: DecisionGraph
    ) -> list[MetricDiff]:
        diffs = []
        _bc_a = float(sum(1 for n in graph_a.nodes if n.status == LayerStatus.BLOCKED))
        _bc_b = float(sum(1 for n in graph_b.nodes if n.status == LayerStatus.BLOCKED))
        m_pairs = [
            (
                "confidence_start",
                graph_a.metrics.confidence_start,
                graph_b.metrics.confidence_start,
            ),
            (
                "confidence_end",
                graph_a.metrics.confidence_end,
                graph_b.metrics.confidence_end,
            ),
            ("depth", float(graph_a.metrics.depth), float(graph_b.metrics.depth)),
            ("blocked_count", _bc_a, _bc_b),
        ]
        for name, va, vb in m_pairs:
            delta = vb - va
            delta_pct = (delta / va * 100) if va != 0 else 0.0
            diffs.append(
                MetricDiff(
                    metric=name,
                    value_a=round(va, 4),
                    value_b=round(vb, 4),
                    delta=round(delta, 4),
                    delta_pct=round(delta_pct, 2),
                )
            )
        return diffs

    def _diff_explainability(self, row_a: dict, row_b: dict) -> Optional[MetricDiff]:
        sa = row_a.get("explainability_score")
        sb = row_b.get("explainability_score")
        if sa is None or sb is None:
            return None
        va, vb = float(sa), float(sb)
        delta = vb - va
        return MetricDiff(
            metric="explainability_score",
            value_a=round(va, 4),
            value_b=round(vb, 4),
            delta=round(delta, 4),
            delta_pct=round((delta / va * 100) if va != 0 else 0.0, 2),
        )

    def _graph_similarity(self, ga: DecisionGraph, gb: DecisionGraph) -> float:
        """Similarité Jaccard sur les couches traversées."""
        la = {n.layer for n in ga.nodes}
        lb = {n.layer for n in gb.nodes}
        if not la and not lb:
            return 1.0
        intersection = len(la & lb)
        union = len(la | lb)
        return round(intersection / union if union > 0 else 0.0, 4)


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[DecisionDiffEngine] = None
_engine_lock = threading.Lock()


def get_diff_engine() -> DecisionDiffEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = DecisionDiffEngine()
    return _engine
