"""
dip/modules/decision_graph.py — D01 Decision Graph Engine.

Construit un DAG (graphe acyclique dirigé) pour chaque DecisionObservation,
modélisant la chaîne des couches décisionnelles traversées.

Input: DecisionObservation (via DIPObserver)
Output: DecisionGraph (DAG complet, métriques, chemin critique)

Adaptation architecturale:
  La spec assume des événements per-layer. Le bus existant émet une seule
  DecisionObservation par cycle avec tous les champs de toutes les couches.
  Le GraphBuilder reconstruit le DAG depuis ces champs consolidés.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from dip.core.store import DIPStore, LRUCache
from dip.core.types import (
    LAYER_DISPLAY,
    CausalType,
    DecisionStatus,
    LayerStatus,
    compute_hash,
)

if TYPE_CHECKING:
    from observability.decision_observation import DecisionObservation


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    layer: str
    display_name: str
    status: LayerStatus
    timestamp_us: int  # estimé: ts_obs + offset positionnel
    confidence_before: float
    confidence_after: float
    key_outputs: dict[str, Any]
    reasoning: str


@dataclass(frozen=True)
class GraphEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    weight: float  # confidence_after(target) - confidence_after(source)
    causal_type: CausalType
    confidence_delta: float


@dataclass(frozen=True)
class GraphMetrics:
    total_nodes: int
    total_edges: int
    depth: int
    rejection_layer: Optional[str]
    rejection_reason: Optional[str]
    confidence_start: float
    confidence_end: float
    total_duration_us: int  # estimé


@dataclass(frozen=True)
class LayerContribution:
    layer: str
    confidence_delta: float
    is_blocker: bool
    relative_impact: float  # |delta| / somme(|deltas|)


@dataclass(frozen=True)
class DecisionGraph:
    graph_id: str
    packet_id: str
    symbol: str
    direction: str
    created_at_us: int
    status: DecisionStatus
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    critical_path: tuple[str, ...]  # node_ids du chemin le plus impactant
    metrics: GraphMetrics
    hash: str


# ── Extraction des couches depuis DecisionObservation ─────────────────────────


def _extract_layer_data(obs: "DecisionObservation") -> list[dict[str, Any]]:
    """
    Reconstruit la séquence de couches depuis un DecisionObservation plat.
    Retourne une liste ordonnée de dicts {layer, status, confidence_after, outputs, reason}.
    """
    # Score de base normalisé 0→1
    base_confidence = obs.score / 100.0

    layers = []

    # Authority
    auth_ok = obs.authority_ok
    layers.append(
        {
            "layer": "authority",
            "status": LayerStatus.PASSED if auth_ok else LayerStatus.BLOCKED,
            "confidence_after": base_confidence if auth_ok else 0.0,
            "outputs": {"ok": auth_ok},
            "reason": "" if auth_ok else "authority_denied",
        }
    )

    # MetaStrategy
    meta_ok = obs.meta_allowed
    layers.append(
        {
            "layer": "meta_strategy",
            "status": LayerStatus.PASSED if meta_ok else LayerStatus.BLOCKED,
            "confidence_after": base_confidence if meta_ok else 0.0,
            "outputs": {
                "allowed": meta_ok,
                "reason": obs.meta_reason,
                "personality": obs.personality_name,
            },
            "reason": obs.meta_reason if not meta_ok else "",
        }
    )

    # Gate
    gate_ok = obs.gate_allowed
    layers.append(
        {
            "layer": "gate",
            "status": LayerStatus.PASSED if gate_ok else LayerStatus.BLOCKED,
            "confidence_after": base_confidence if gate_ok else 0.0,
            "outputs": {"allowed": gate_ok, "failed": obs.gate_failed},
            "reason": (
                (
                    _gf
                    if isinstance(_gf := obs.gate_failed, str)
                    else ", ".join(_gf or [])
                )
                if not gate_ok
                else ""
            ),
        }
    )

    # SelfAwareness
    aw_ok = obs.awareness_ok
    aw_conf = base_confidence * (
        0.9 if obs.awareness_level in ("CAUTION", "WARNING") else 1.0
    )
    layers.append(
        {
            "layer": "awareness",
            "status": LayerStatus.PASSED if aw_ok else LayerStatus.BLOCKED,
            "confidence_after": aw_conf if aw_ok else 0.0,
            "outputs": {"ok": aw_ok, "level": obs.awareness_level},
            "reason": f"awareness_level={obs.awareness_level}" if not aw_ok else "",
        }
    )

    # Conviction
    conv_ok = obs.conviction_ok
    conv_conf = aw_conf * (obs.conviction_size_factor or 1.0)
    conv_conf = max(0.0, min(1.0, conv_conf))
    layers.append(
        {
            "layer": "conviction",
            "status": LayerStatus.PASSED if conv_ok else LayerStatus.BLOCKED,
            "confidence_after": conv_conf if conv_ok else 0.0,
            "outputs": {
                "ok": conv_ok,
                "level": obs.conviction_level,
                "score": obs.conviction_score,
                "size_factor": obs.conviction_size_factor,
            },
            "reason": f"conviction_level={obs.conviction_level}" if not conv_ok else "",
        }
    )

    # NoTrade
    nt_ok = obs.notrade_ok
    layers.append(
        {
            "layer": "no_trade",
            "status": LayerStatus.PASSED if nt_ok else LayerStatus.BLOCKED,
            "confidence_after": conv_conf if nt_ok else 0.0,
            "outputs": {
                "ok": nt_ok,
                "reason": obs.notrade_reason,
                "rejection_score": obs.notrade_rejection_score,
            },
            "reason": obs.notrade_reason or "" if not nt_ok else "",
        }
    )

    # Portfolio Brain
    pb_ok = obs.portfolio_ok
    pb_conf = conv_conf * (obs.portfolio_size_factor or 1.0)
    pb_conf = max(0.0, min(1.0, pb_conf))
    layers.append(
        {
            "layer": "portfolio",
            "status": LayerStatus.PASSED if pb_ok else LayerStatus.BLOCKED,
            "confidence_after": pb_conf if pb_ok else 0.0,
            "outputs": {
                "ok": pb_ok,
                "reason": obs.portfolio_reason,
                "size_factor": obs.portfolio_size_factor,
            },
            "reason": obs.portfolio_reason or "" if not pb_ok else "",
        }
    )

    # Capital Allocation
    cae_ok = obs.cae_ok
    layers.append(
        {
            "layer": "capital_allocation",
            "status": LayerStatus.PASSED if cae_ok else LayerStatus.BLOCKED,
            "confidence_after": pb_conf if cae_ok else 0.0,
            "outputs": {
                "ok": cae_ok,
                "size_usd": obs.cae_size_usd,
                "kelly": obs.cae_kelly,
                "ev": obs.cae_ev,
            },
            "reason": "capital_allocation_failed" if not cae_ok else "",
        }
    )

    # Mistake Memory
    mm_ok = obs.mistake_ok
    layers.append(
        {
            "layer": "mistake_memory",
            "status": LayerStatus.PASSED if mm_ok else LayerStatus.BLOCKED,
            "confidence_after": pb_conf if mm_ok else 0.0,
            "outputs": {"ok": mm_ok, "reason": obs.mistake_reason},
            "reason": obs.mistake_reason or "" if not mm_ok else "",
        }
    )

    # Executive Override
    eo_ok = obs.override_ok
    eo_conf = pb_conf * (obs.override_size_factor or 1.0)
    eo_conf = max(0.0, min(1.0, eo_conf))
    layers.append(
        {
            "layer": "executive_override",
            "status": LayerStatus.PASSED if eo_ok else LayerStatus.BLOCKED,
            "confidence_after": eo_conf if eo_ok else 0.0,
            "outputs": {
                "ok": eo_ok,
                "level": obs.override_level,
                "size_factor": obs.override_size_factor,
                "reason": obs.override_reason,
            },
            "reason": obs.override_reason or "" if not eo_ok else "",
        }
    )

    # Threat Radar
    radar_ok = obs.radar_ok
    layers.append(
        {
            "layer": "threat_radar",
            "status": LayerStatus.PASSED if radar_ok else LayerStatus.BLOCKED,
            "confidence_after": eo_conf if radar_ok else 0.0,
            "outputs": {
                "ok": radar_ok,
                "level": obs.radar_level,
                "threat_count": obs.radar_threat_count,
            },
            "reason": f"radar_level={obs.radar_level}" if not radar_ok else "",
        }
    )

    # Arbitrator
    _PASS_DECISIONS = (None, "EXECUTE", "execute", "APPROVED", "approved")
    arb_blocked = obs.arbitration_decision not in _PASS_DECISIONS
    arb_conf = eo_conf if not arb_blocked else 0.0
    layers.append(
        {
            "layer": "arbitrator",
            "status": LayerStatus.BLOCKED if arb_blocked else LayerStatus.PASSED,
            "confidence_after": arb_conf,
            "outputs": {"decision": obs.arbitration_decision},
            "reason": obs.arbitration_decision or "" if arb_blocked else "",
        }
    )

    # Tronquer à la première couche bloquante (pas de couche après un BLOCKED)
    result = []
    for ldata in layers:
        result.append(ldata)
        if ldata["status"] == LayerStatus.BLOCKED:
            break

    return result


# ── Graph Builder ─────────────────────────────────────────────────────────────


class GraphBuilder:
    """Construit un DecisionGraph depuis un DecisionObservation."""

    @staticmethod
    def build(obs: "DecisionObservation") -> DecisionGraph:
        ts_base = int(obs.ts * 1_000_000)
        layer_data = _extract_layer_data(obs)

        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        prev_node_id: Optional[str] = None
        prev_confidence = 0.0

        for i, ld in enumerate(layer_data):
            node_id = f"n_{i:03d}"
            # Timestamp estimé: on espace de 10ms par couche (pas de données réelles)
            ts_node = ts_base + i * 10_000

            node = GraphNode(
                node_id=node_id,
                layer=ld["layer"],
                display_name=LAYER_DISPLAY.get(ld["layer"], ld["layer"]),
                status=ld["status"],
                timestamp_us=ts_node,
                confidence_before=prev_confidence,
                confidence_after=ld["confidence_after"],
                key_outputs=ld["outputs"],
                reasoning=ld["reason"],
            )
            nodes.append(node)

            if prev_node_id is not None:
                delta = ld["confidence_after"] - prev_confidence
                causal_type = (
                    CausalType.GATE
                    if ld["status"] == LayerStatus.BLOCKED
                    else (CausalType.REDUCE if delta < 0 else CausalType.TRANSFORM)
                )
                edge = GraphEdge(
                    edge_id=f"e_{i:03d}",
                    source_node_id=prev_node_id,
                    target_node_id=node_id,
                    weight=delta,
                    causal_type=causal_type,
                    confidence_delta=delta,
                )
                edges.append(edge)

            prev_node_id = node_id
            prev_confidence = ld["confidence_after"]

        # Chemin critique: nœuds avec le plus grand |delta| de confiance
        critical_path = GraphBuilder._critical_path(nodes, edges)

        # Couche de rejet
        rejection_layer = None
        rejection_reason = None
        for n in nodes:
            if n.status == LayerStatus.BLOCKED:
                rejection_layer = n.display_name
                rejection_reason = n.reasoning
                break

        status = (
            DecisionStatus.APPROVED if obs.trade_allowed else DecisionStatus.REJECTED
        )
        final_confidence = nodes[-1].confidence_after if nodes else 0.0

        metrics = GraphMetrics(
            total_nodes=len(nodes),
            total_edges=len(edges),
            depth=len(nodes),
            rejection_layer=rejection_layer,
            rejection_reason=rejection_reason,
            confidence_start=nodes[0].confidence_before if nodes else 0.0,
            confidence_end=final_confidence,
            total_duration_us=len(nodes) * 10_000,  # estimé
        )

        graph_id = f"graph_{obs.packet_id}"
        content = {
            "graph_id": graph_id,
            "packet_id": obs.packet_id,
            "status": status.value,
            "nodes": len(nodes),
            "edges": len(edges),
        }

        return DecisionGraph(
            graph_id=graph_id,
            packet_id=obs.packet_id,
            symbol=obs.symbol,
            direction=obs.side,
            created_at_us=ts_base,
            status=status,
            nodes=tuple(nodes),
            edges=tuple(edges),
            critical_path=tuple(critical_path),
            metrics=metrics,
            hash=compute_hash(content),
        )

    @staticmethod
    def _critical_path(nodes: list[GraphNode], edges: list[GraphEdge]) -> list[str]:
        """Retourne les node_ids ayant le plus grand impact absolu sur la confiance."""
        if not edges:
            return [n.node_id for n in nodes]

        # Impact absolu de chaque nœud (delta entrant + delta sortant)
        impact: dict[str, float] = {n.node_id: 0.0 for n in nodes}
        for e in edges:
            impact[e.target_node_id] += abs(e.confidence_delta)

        # Chemin linéaire trié par impact décroissant
        sorted_nodes = sorted(nodes, key=lambda n: impact[n.node_id], reverse=True)
        # On garde les top 50% (au moins 1)
        top_n = max(1, len(sorted_nodes) // 2)
        top_ids = {n.node_id for n in sorted_nodes[:top_n]}

        # Retourner dans l'ordre original du graphe
        return [n.node_id for n in nodes if n.node_id in top_ids]


# ── Engine principal ──────────────────────────────────────────────────────────


class DecisionGraphEngine:
    """
    D01 — Moteur de construction de graphes décisionnels.

    S'abonne au DIPObserver, construit un graph par observation,
    le stocke en cache LRU + SQLite.
    """

    def __init__(self) -> None:
        self._cache: LRUCache[DecisionGraph] = LRUCache(
            max_entries=10_000, ttl_seconds=86_400
        )
        self._store = DIPStore.instance()
        self._lock = threading.Lock()

    def on_observation(self, obs: "DecisionObservation") -> None:
        """Handler appelé par le DIPObserver pour chaque observation."""
        graph = GraphBuilder.build(obs)
        self._cache.set(graph.packet_id, graph)
        self._persist(graph)

    def get_graph(self, packet_id: str) -> Optional[DecisionGraph]:
        cached = self._cache.get(packet_id)
        if cached:
            return cached
        row = self._store.get_decision(packet_id)
        if row and row.get("graph_json"):
            return self._deserialize(row["graph_json"])
        return None

    def get_graph_metrics(self, packet_id: str) -> Optional[GraphMetrics]:
        graph = self.get_graph(packet_id)
        return graph.metrics if graph else None

    def get_critical_path(self, packet_id: str) -> list[GraphNode]:
        graph = self.get_graph(packet_id)
        if not graph:
            return []
        cp_ids = set(graph.critical_path)
        return [n for n in graph.nodes if n.node_id in cp_ids]

    def get_layer_contributions(self, packet_id: str) -> dict[str, LayerContribution]:
        graph = self.get_graph(packet_id)
        if not graph:
            return {}
        total_impact = sum(abs(e.confidence_delta) for e in graph.edges) or 1.0
        contribs: dict[str, LayerContribution] = {}
        for n in graph.nodes:
            incoming = [e for e in graph.edges if e.target_node_id == n.node_id]
            delta = sum(e.confidence_delta for e in incoming) if incoming else 0.0
            contribs[n.layer] = LayerContribution(
                layer=n.layer,
                confidence_delta=delta,
                is_blocker=n.status == LayerStatus.BLOCKED,
                relative_impact=abs(delta) / total_impact,
            )
        return contribs

    def get_graphs_by_symbol(
        self, symbol: str, limit: int = 100
    ) -> list[DecisionGraph]:
        rows = self._store.get_decisions(symbol=symbol, limit=limit)
        graphs = []
        for r in rows:
            if r.get("graph_json"):
                g = self._deserialize(r["graph_json"])
                if g:
                    graphs.append(g)
        return graphs

    def get_layer_rejection_stats(
        self, start_us: int, end_us: int, status: str = "REJECTED"
    ) -> dict[str, int]:
        rows = self._store.get_decisions(
            status=status, start_us=start_us, end_us=end_us, limit=10_000
        )
        stats: dict[str, int] = {}
        for r in rows:
            layer = r.get("root_cause_layer")
            if layer:
                stats[layer] = stats.get(layer, 0) + 1
        return dict(sorted(stats.items(), key=lambda x: x[1], reverse=True))

    def _persist(self, graph: DecisionGraph) -> None:
        try:
            self._store.upsert_decision(
                graph.packet_id,
                {
                    "packet_id": graph.packet_id,
                    "symbol": graph.symbol,
                    "direction": graph.direction,
                    "regime": None,  # ajouté par D03
                    "status": graph.status.value,
                    "created_at_us": graph.created_at_us,
                    "graph_json": self._serialize(graph),
                    "root_cause_layer": graph.metrics.rejection_layer,
                },
            )
        except Exception:
            pass

    def _serialize(self, graph: DecisionGraph) -> str:
        return json.dumps(
            {
                "graph_id": graph.graph_id,
                "packet_id": graph.packet_id,
                "symbol": graph.symbol,
                "direction": graph.direction,
                "created_at_us": graph.created_at_us,
                "status": graph.status.value,
                "nodes": [
                    {
                        "node_id": n.node_id,
                        "layer": n.layer,
                        "display_name": n.display_name,
                        "status": n.status.value,
                        "timestamp_us": n.timestamp_us,
                        "confidence_before": n.confidence_before,
                        "confidence_after": n.confidence_after,
                        "key_outputs": n.key_outputs,
                        "reasoning": n.reasoning,
                    }
                    for n in graph.nodes
                ],
                "edges": [
                    {
                        "edge_id": e.edge_id,
                        "source": e.source_node_id,
                        "target": e.target_node_id,
                        "weight": e.weight,
                        "causal_type": e.causal_type.value,
                        "confidence_delta": e.confidence_delta,
                    }
                    for e in graph.edges
                ],
                "critical_path": list(graph.critical_path),
                "metrics": {
                    "total_nodes": graph.metrics.total_nodes,
                    "total_edges": graph.metrics.total_edges,
                    "depth": graph.metrics.depth,
                    "rejection_layer": graph.metrics.rejection_layer,
                    "rejection_reason": graph.metrics.rejection_reason,
                    "confidence_start": graph.metrics.confidence_start,
                    "confidence_end": graph.metrics.confidence_end,
                    "total_duration_us": graph.metrics.total_duration_us,
                },
                "hash": graph.hash,
            }
        )

    def _deserialize(self, json_str: str) -> Optional[DecisionGraph]:
        try:
            d = json.loads(json_str)
            nodes = tuple(
                GraphNode(
                    node_id=n["node_id"],
                    layer=n["layer"],
                    display_name=n["display_name"],
                    status=LayerStatus(n["status"]),
                    timestamp_us=n["timestamp_us"],
                    confidence_before=n["confidence_before"],
                    confidence_after=n["confidence_after"],
                    key_outputs=n["key_outputs"],
                    reasoning=n["reasoning"],
                )
                for n in d["nodes"]
            )
            edges = tuple(
                GraphEdge(
                    edge_id=e["edge_id"],
                    source_node_id=e["source"],
                    target_node_id=e["target"],
                    weight=e["weight"],
                    causal_type=CausalType(e["causal_type"]),
                    confidence_delta=e["confidence_delta"],
                )
                for e in d["edges"]
            )
            m = d["metrics"]
            return DecisionGraph(
                graph_id=d["graph_id"],
                packet_id=d["packet_id"],
                symbol=d["symbol"],
                direction=d["direction"],
                created_at_us=d["created_at_us"],
                status=DecisionStatus(d["status"]),
                nodes=nodes,
                edges=edges,
                critical_path=tuple(d["critical_path"]),
                metrics=GraphMetrics(
                    total_nodes=m["total_nodes"],
                    total_edges=m["total_edges"],
                    depth=m["depth"],
                    rejection_layer=m["rejection_layer"],
                    rejection_reason=m["rejection_reason"],
                    confidence_start=m["confidence_start"],
                    confidence_end=m["confidence_end"],
                    total_duration_us=m["total_duration_us"],
                ),
                hash=d["hash"],
            )
        except Exception:
            return None


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[DecisionGraphEngine] = None
_engine_lock = threading.Lock()


def get_graph_engine() -> DecisionGraphEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = DecisionGraphEngine()
    return _engine
