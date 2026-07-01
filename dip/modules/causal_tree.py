"""
dip/modules/causal_tree.py — D03 Causal Tree Engine.

Construit l'arbre causal d'une décision: quelle couche a causé le résultat,
avec quelle force, et quelle chaîne causale mène à la cause racine.

Input: DecisionGraph (D01) + DecisionObservation
Output: CausalTree avec RootCause, CausalPath, force causale normalisée.

Note: "cause apparente" (corrélation observée, pas causalité prouvée).
Chaque conclusion porte une confiance explicite.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from dip.core.store import DIPStore, LRUCache
from dip.core.types import LayerStatus, compute_hash
from dip.modules.decision_graph import DecisionGraph, get_graph_engine

if TYPE_CHECKING:
    from observability.decision_observation import DecisionObservation


# ── Types ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CausalFactor:
    factor: str
    strength: float  # 0.0 → 1.0
    layer: str


@dataclass(frozen=True)
class CausalNode:
    node_id: str
    layer: str
    cause_type: str  # ex: "SIGNAL_GENERATED", "GATE_BLOCKED"
    effect_type: str  # ex: "TRIGGERED_NEXT_LAYER", "REJECTED"
    strength: float
    confidence: float
    metadata: dict[str, Any]


@dataclass(frozen=True)
class CausalPath:
    path_id: str
    nodes: tuple[str, ...]  # couches dans l'ordre causal
    total_strength: float
    description: str


@dataclass(frozen=True)
class RootCause:
    cause_type: str
    causing_layer: str
    confidence: float
    description: str
    contributing_factors: tuple[CausalFactor, ...]


@dataclass(frozen=True)
class CausalChain:
    layers: tuple[str, ...]
    description: str
    total_strength: float


@dataclass(frozen=True)
class CausalTree:
    tree_id: str
    packet_id: str
    symbol: str
    direction: str
    regime: str
    result: str  # "APPROVED" | "REJECTED"
    root_cause: RootCause
    causal_paths: tuple[CausalPath, ...]
    causal_nodes: tuple[CausalNode, ...]
    total_causal_depth: int
    overall_confidence: float
    hash: str


# ── Cause type mapping ────────────────────────────────────────────────────────

_CAUSE_TYPES: dict[str, str] = {
    "authority": "AUTHORITY_GATE",
    "meta_strategy": "META_STRATEGY_FILTER",
    "gate": "SCORE_GATE",
    "awareness": "SELF_AWARENESS_BLOCK",
    "conviction": "CONVICTION_INSUFFICIENT",
    "no_trade": "NOTRADE_COOLDOWN",
    "portfolio": "PORTFOLIO_CONSTRAINT",
    "capital_allocation": "CAPITAL_INSUFFICIENT",
    "mistake_memory": "MISTAKE_PATTERN_MATCH",
    "executive_override": "EXECUTIVE_VETO",
    "threat_radar": "THREAT_DETECTED",
    "arbitrator": "ARBITRATION_CONFLICT",
}

_EFFECT_TYPES: dict[str, str] = {
    "authority": "BLOCKED_ALL_DOWNSTREAM",
    "meta_strategy": "BLOCKED_STRATEGY_MISMATCH",
    "gate": "BLOCKED_SCORE_INSUFFICIENT",
    "awareness": "BLOCKED_SYSTEM_DEGRADED",
    "conviction": "BLOCKED_CONVICTION_LOW",
    "no_trade": "BLOCKED_COOLDOWN_ACTIVE",
    "portfolio": "BLOCKED_PORTFOLIO_LIMIT",
    "capital_allocation": "BLOCKED_NO_CAPITAL",
    "mistake_memory": "BLOCKED_KNOWN_MISTAKE",
    "executive_override": "BLOCKED_OVERRIDE_VETO",
    "threat_radar": "BLOCKED_THREAT_ACTIVE",
    "arbitrator": "BLOCKED_CONFLICT",
}


# ── Builder ───────────────────────────────────────────────────────────────────


class CausalTreeBuilder:

    @staticmethod
    def build(obs: "DecisionObservation", graph: DecisionGraph) -> CausalTree:
        # Identifier la couche bloquante
        blocker_node = None
        for n in graph.nodes:
            if n.status == LayerStatus.BLOCKED:
                blocker_node = n
                break

        # Construire les nœuds causaux
        causal_nodes: list[CausalNode] = []
        total_impact = sum(abs(e.confidence_delta) for e in graph.edges) or 1.0

        for i, node in enumerate(graph.nodes):
            incoming = [e for e in graph.edges if e.target_node_id == node.node_id]
            delta = sum(abs(e.confidence_delta) for e in incoming) if incoming else 0.0
            strength = min(1.0, delta / (total_impact or 1.0))

            cause_type = _CAUSE_TYPES.get(node.layer, "LAYER_EVALUATED")
            if node.status == LayerStatus.BLOCKED:
                effect_type = _EFFECT_TYPES.get(node.layer, "BLOCKED")
            else:
                effect_type = (
                    "TRIGGERED_NEXT_LAYER" if i < len(graph.nodes) - 1 else "APPROVED"
                )

            causal_nodes.append(
                CausalNode(
                    node_id=f"cn_{i:03d}",
                    layer=node.layer,
                    cause_type=cause_type,
                    effect_type=effect_type,
                    strength=strength,
                    confidence=min(1.0, 0.7 + strength * 0.3),
                    metadata=node.key_outputs,
                )
            )

        # Cause racine: couche bloquante ou dernière couche si approuvé
        if blocker_node:
            rc_layer = blocker_node.layer
            rc_type = _CAUSE_TYPES.get(rc_layer, "LAYER_BLOCKED")
            rc_desc = CausalTreeBuilder._describe_rejection(obs, blocker_node)
            rc_confidence = 0.90
        else:
            rc_layer = graph.nodes[-1].layer if graph.nodes else "unknown"
            rc_type = "APPROVED_ALL_LAYERS"
            rc_desc = (
                f"Toutes les couches ont approuvé le signal {obs.side} sur {obs.symbol}"
            )
            rc_confidence = 0.85

        # Facteurs contributifs
        contributing = CausalTreeBuilder._contributing_factors(obs, graph, blocker_node)

        root_cause = RootCause(
            cause_type=rc_type,
            causing_layer=rc_layer,
            confidence=rc_confidence,
            description=rc_desc,
            contributing_factors=tuple(contributing),
        )

        # Chemin causal principal
        passed_layers = [
            n.layer for n in graph.nodes if n.status != LayerStatus.BLOCKED
        ]
        blocked_layers = [
            n.layer for n in graph.nodes if n.status == LayerStatus.BLOCKED
        ]
        main_path = passed_layers + blocked_layers

        path_strength = sum(abs(e.confidence_delta) for e in graph.edges) / (
            total_impact or 1.0
        )

        causal_paths = [
            CausalPath(
                path_id="cp_001",
                nodes=tuple(main_path),
                total_strength=min(1.0, path_strength),
                description=CausalTreeBuilder._describe_path(obs, graph, blocker_node),
            )
        ]

        # Confiance globale: produit des confiances de chaque nœud causal
        overall_conf = 1.0
        for cn in causal_nodes:
            overall_conf *= cn.confidence
        overall_conf = max(0.3, overall_conf)

        tree_id = f"ct_{obs.packet_id}"
        content = {"tree_id": tree_id, "root_cause": rc_type, "layer": rc_layer}

        return CausalTree(
            tree_id=tree_id,
            packet_id=obs.packet_id,
            symbol=obs.symbol,
            direction=obs.side,
            regime=obs.regime,
            result="APPROVED" if obs.trade_allowed else "REJECTED",
            root_cause=root_cause,
            causal_paths=tuple(causal_paths),
            causal_nodes=tuple(causal_nodes),
            total_causal_depth=len(graph.nodes),
            overall_confidence=overall_conf,
            hash=compute_hash(content),
        )

    @staticmethod
    def _describe_rejection(obs: "DecisionObservation", blocker_node: Any) -> str:
        layer = blocker_node.layer
        reason = blocker_node.reasoning or ""

        descriptions = {
            "authority": "La couche d'autorité a bloqué le signal avant évaluation.",
            "meta_strategy": f"La méta-stratégie '{obs.personality_name}' a refusé le signal. Raison: {reason or obs.meta_reason}",
            "gate": f"Le Risk Gate a bloqué le signal (score={obs.score:.0f}). Règles échouées: {(_gf if isinstance(_gf := obs.gate_failed, str) else ', '.join(_gf or [])) or 'inconnues'}",
            "awareness": f"Self-Awareness level={obs.awareness_level}: système en état dégradé.",
            "conviction": f"Conviction insuffisante (level={obs.conviction_level}, score={f'{obs.conviction_score:.2f}' if obs.conviction_score else 'N/A'}).",
            "no_trade": f"No-Trade Layer actif: {obs.notrade_reason or 'cooldown actif'}",
            "portfolio": f"Portfolio Brain a bloqué: {obs.portfolio_reason or 'contrainte de portefeuille'}",
            "capital_allocation": "Capital Allocation Engine a bloqué: capital insuffisant.",
            "mistake_memory": f"MistakeMemory a reconnu un pattern: {obs.mistake_reason or 'erreur passée similaire'}",
            "executive_override": f"Executive Override level={obs.override_level}: {obs.override_reason or 'veto exécutif'}",
            "threat_radar": f"ThreatRadar level={obs.radar_level}: {obs.radar_threat_count} menace(s) détectée(s).",
            "arbitrator": f"Arbitrator a rejeté: {obs.arbitration_decision or 'conflit de décision'}",
        }
        return descriptions.get(
            layer, f"Couche {layer} a bloqué le signal. Raison: {reason}"
        )

    @staticmethod
    def _describe_path(
        obs: "DecisionObservation", graph: DecisionGraph, blocker: Optional[Any]
    ) -> str:
        n_passed = sum(1 for n in graph.nodes if n.status != LayerStatus.BLOCKED)
        if blocker:
            return (
                f"Signal {obs.side} (score={obs.score:.0f}) → "
                f"{n_passed} couche(s) approuvée(s) → "
                f"bloqué par {blocker.display_name}"
            )
        return (
            f"Signal {obs.side} (score={obs.score:.0f}) → "
            f"toutes les {n_passed} couches approuvées → exécution"
        )

    @staticmethod
    def _contributing_factors(
        obs: "DecisionObservation",
        graph: DecisionGraph,
        blocker: Optional[Any],
    ) -> list[CausalFactor]:
        factors = []

        # Score de conviction comme facteur
        if obs.conviction_score is not None:
            strength = obs.conviction_score
            factors.append(
                CausalFactor(
                    factor=f"Conviction score={obs.conviction_score:.2f}",
                    strength=round(strength, 3),
                    layer="conviction",
                )
            )

        # Score brut comme facteur
        score_strength = obs.score / 100.0
        factors.append(
            CausalFactor(
                factor=f"Signal score={obs.score:.0f}/100 en régime {obs.regime}",
                strength=round(score_strength, 3),
                layer="gate",
            )
        )

        # Régime comme facteur contextuel
        factors.append(
            CausalFactor(
                factor=f"Régime marché: {obs.regime}",
                strength=0.3,
                layer="meta_strategy",
            )
        )

        return factors[:5]  # max 5 facteurs


# ── Engine ─────────────────────────────────────────────────────────────────────


class CausalTreeEngine:
    """D03 — Arbre causal par packet."""

    def __init__(self) -> None:
        self._graph_engine = get_graph_engine()
        self._cache: LRUCache[CausalTree] = LRUCache(
            max_entries=10_000, ttl_seconds=86_400
        )
        self._store = DIPStore.instance()

    def on_observation(self, obs: "DecisionObservation") -> None:
        graph = self._graph_engine.get_graph(obs.packet_id)
        if not graph:
            return
        tree = CausalTreeBuilder.build(obs, graph)
        self._cache.set(tree.packet_id, tree)
        self._persist(obs.packet_id, tree, obs.regime)

    def build_causal_tree(self, packet_id: str) -> Optional[CausalTree]:
        cached = self._cache.get(packet_id)
        if cached:
            return cached
        row = self._store.get_decision(packet_id)
        if row and row.get("causal_tree_json"):
            return self._deserialize(row["causal_tree_json"])
        return None

    def get_root_cause(self, packet_id: str) -> Optional[RootCause]:
        tree = self.build_causal_tree(packet_id)
        return tree.root_cause if tree else None

    def get_causal_paths(self, packet_id: str) -> list[CausalPath]:
        tree = self.build_causal_tree(packet_id)
        return list(tree.causal_paths) if tree else []

    def get_rejection_cause(self, packet_id: str) -> Optional[CausalChain]:
        tree = self.build_causal_tree(packet_id)
        if not tree or tree.result != "REJECTED":
            return None
        rc = tree.root_cause
        return CausalChain(
            layers=tuple(
                rc.contributing_factors[i].layer
                for i in range(len(rc.contributing_factors))
            ),
            description=rc.description,
            total_strength=rc.confidence,
        )

    def get_approval_cause(self, packet_id: str) -> Optional[CausalChain]:
        tree = self.build_causal_tree(packet_id)
        if not tree or tree.result != "APPROVED":
            return None
        rc = tree.root_cause
        return CausalChain(
            layers=tuple(n.layer for n in tree.causal_nodes),
            description=rc.description,
            total_strength=rc.confidence,
        )

    def get_rejection_stats(
        self,
        symbol: Optional[str] = None,
        regime: Optional[str] = None,
        limit: int = 1000,
    ) -> dict[str, int]:
        """Statistiques des causes racines de rejet."""
        rows = self._store.get_decisions(symbol=symbol, status="REJECTED", limit=limit)
        stats: dict[str, int] = {}
        for r in rows:
            layer = r.get("root_cause_layer")
            if layer:
                stats[layer] = stats.get(layer, 0) + 1
        return dict(sorted(stats.items(), key=lambda x: x[1], reverse=True))

    def _persist(self, packet_id: str, tree: CausalTree, regime: str) -> None:
        try:
            self._store._conn.execute(
                """UPDATE dip_decisions
                   SET causal_tree_json = ?, regime = ?,
                       root_cause_type = ?, root_cause_layer = ?
                   WHERE packet_id = ?""",
                (
                    self._serialize(tree),
                    regime,
                    tree.root_cause.cause_type,
                    tree.root_cause.causing_layer,
                    packet_id,
                ),
            )
            self._store._conn.commit()
        except Exception:
            pass

    def _serialize(self, tree: CausalTree) -> str:
        return json.dumps(
            {
                "tree_id": tree.tree_id,
                "packet_id": tree.packet_id,
                "symbol": tree.symbol,
                "direction": tree.direction,
                "regime": tree.regime,
                "result": tree.result,
                "root_cause": {
                    "cause_type": tree.root_cause.cause_type,
                    "causing_layer": tree.root_cause.causing_layer,
                    "confidence": tree.root_cause.confidence,
                    "description": tree.root_cause.description,
                    "factors": [
                        {"factor": f.factor, "strength": f.strength, "layer": f.layer}
                        for f in tree.root_cause.contributing_factors
                    ],
                },
                "causal_paths": [
                    {
                        "path_id": p.path_id,
                        "nodes": list(p.nodes),
                        "total_strength": p.total_strength,
                        "description": p.description,
                    }
                    for p in tree.causal_paths
                ],
                "causal_nodes": [
                    {
                        "node_id": n.node_id,
                        "layer": n.layer,
                        "cause_type": n.cause_type,
                        "effect_type": n.effect_type,
                        "strength": n.strength,
                        "confidence": n.confidence,
                        "metadata": n.metadata,
                    }
                    for n in tree.causal_nodes
                ],
                "total_causal_depth": tree.total_causal_depth,
                "overall_confidence": tree.overall_confidence,
            }
        )

    def _deserialize(self, json_str: str) -> Optional[CausalTree]:
        try:
            d = json.loads(json_str)
            rc = d["root_cause"]
            root_cause = RootCause(
                cause_type=rc["cause_type"],
                causing_layer=rc["causing_layer"],
                confidence=rc["confidence"],
                description=rc["description"],
                contributing_factors=tuple(
                    CausalFactor(
                        factor=f["factor"], strength=f["strength"], layer=f["layer"]
                    )
                    for f in rc.get("factors", [])
                ),
            )
            causal_paths = tuple(
                CausalPath(
                    path_id=p["path_id"],
                    nodes=tuple(p["nodes"]),
                    total_strength=p["total_strength"],
                    description=p["description"],
                )
                for p in d.get("causal_paths", [])
            )
            causal_nodes = tuple(
                CausalNode(
                    node_id=n["node_id"],
                    layer=n["layer"],
                    cause_type=n["cause_type"],
                    effect_type=n["effect_type"],
                    strength=n["strength"],
                    confidence=n["confidence"],
                    metadata=n.get("metadata", {}),
                )
                for n in d.get("causal_nodes", [])
            )
            return CausalTree(
                tree_id=d["tree_id"],
                packet_id=d["packet_id"],
                symbol=d["symbol"],
                direction=d["direction"],
                regime=d["regime"],
                result=d["result"],
                root_cause=root_cause,
                causal_paths=causal_paths,
                causal_nodes=causal_nodes,
                total_causal_depth=d["total_causal_depth"],
                overall_confidence=d["overall_confidence"],
                hash=compute_hash({"tree_id": d["tree_id"]}),
            )
        except Exception:
            return None


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[CausalTreeEngine] = None
_engine_lock = threading.Lock()


def get_causal_tree_engine() -> CausalTreeEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = CausalTreeEngine()
    return _engine
