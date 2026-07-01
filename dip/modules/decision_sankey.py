"""
dip/modules/decision_sankey.py — D06 Decision Sankey Engine.

Visualise le flux des décisions à travers les couches du pipeline.
Format de sortie compatible D3.js Sankey.
Invariant: la somme des flux sortants d'un nœud = valeur du nœud.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

from dip.core.store import DIPStore, LRUCache
from dip.core.types import SankeyNodeType, TimeRange, now_us

# ── Types ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SankeyNode:
    node_id: str
    label: str
    value: int
    node_type: SankeyNodeType


@dataclass(frozen=True)
class SankeyFlow:
    source_id: str
    target_id: str
    value: int
    percentage: float


@dataclass(frozen=True)
class LayerConversion:
    layer: str
    total_in: int
    total_rejected: int
    pass_rate: float
    reject_count: int


@dataclass(frozen=True)
class SankeyFunnel:
    conversion_by_layer: tuple[LayerConversion, ...]
    overall_conversion: float
    biggest_bottleneck: str


@dataclass(frozen=True)
class SankeyDiagram:
    sankey_id: str
    time_range: TimeRange
    total_packets: int
    nodes: tuple[SankeyNode, ...]
    flows: tuple[SankeyFlow, ...]
    funnel: SankeyFunnel
    generated_at_us: int


# ── Builder ───────────────────────────────────────────────────────────────────

# Couches dans l'ordre du pipeline
_PIPELINE_LAYERS = [
    ("authority", "Authority"),
    ("meta_strategy", "MetaStrategy"),
    ("gate", "Gate"),
    ("awareness", "SelfAwareness"),
    ("conviction", "ConvictionEngine"),
    ("no_trade", "NoTradeLayer"),
    ("portfolio", "PortfolioBrain"),
    ("capital_allocation", "CapitalAllocation"),
    ("mistake_memory", "MistakeMemory"),
    ("executive_override", "ExecutiveOverride"),
    ("threat_radar", "ThreatRadar"),
    ("arbitrator", "Arbitrator"),
]


class SankeyBuilder:

    @staticmethod
    def build(rows: list[dict], time_range: TimeRange) -> SankeyDiagram:
        total = len(rows)
        if total == 0:
            return SankeyBuilder._empty(time_range)

        # Compter les rejets par couche
        rejections_by_layer: dict[str, int] = {}
        approved_count = 0

        for r in rows:
            status = r.get("status", "")
            rl = r.get("root_cause_layer")
            if status == "APPROVED":
                approved_count += 1
            elif rl:
                rejections_by_layer[rl] = rejections_by_layer.get(rl, 0) + 1

        # Construire les nœuds et flux
        nodes: list[SankeyNode] = []
        flows: list[SankeyFlow] = []
        conversions: list[LayerConversion] = []

        # Nœud source
        nodes.append(
            SankeyNode(
                node_id="entry",
                label=f"Opportunités ({total})",
                value=total,
                node_type=SankeyNodeType.SOURCE,
            )
        )

        remaining = total
        prev_id = "entry"

        for layer_key, layer_label in _PIPELINE_LAYERS:
            rejected_here = rejections_by_layer.get(layer_label, 0)
            if rejected_here == 0 and remaining == 0:
                break

            layer_id = f"layer_{layer_key}"
            nodes.append(
                SankeyNode(
                    node_id=layer_id,
                    label=layer_label,
                    value=remaining,
                    node_type=SankeyNodeType.LAYER,
                )
            )

            # Flux d'entrée
            flows.append(
                SankeyFlow(
                    source_id=prev_id,
                    target_id=layer_id,
                    value=remaining,
                    percentage=round(remaining / total * 100, 1),
                )
            )

            # Flux de rejet
            if rejected_here > 0:
                rej_id = f"rej_{layer_key}"
                nodes.append(
                    SankeyNode(
                        node_id=rej_id,
                        label=f"Rejeté: {layer_label}",
                        value=rejected_here,
                        node_type=SankeyNodeType.REJECTION,
                    )
                )
                flows.append(
                    SankeyFlow(
                        source_id=layer_id,
                        target_id=rej_id,
                        value=rejected_here,
                        percentage=round(rejected_here / total * 100, 1),
                    )
                )

            pass_rate = (
                (remaining - rejected_here) / remaining if remaining > 0 else 0.0
            )
            conversions.append(
                LayerConversion(
                    layer=layer_label,
                    total_in=remaining,
                    total_rejected=rejected_here,
                    pass_rate=round(pass_rate, 4),
                    reject_count=rejected_here,
                )
            )

            remaining -= rejected_here
            prev_id = layer_id

        # Nœuds finaux
        nodes.append(
            SankeyNode(
                node_id="final_approved",
                label=f"Approuvés ({approved_count})",
                value=approved_count,
                node_type=SankeyNodeType.SINK,
            )
        )
        flows.append(
            SankeyFlow(
                source_id=prev_id,
                target_id="final_approved",
                value=approved_count,
                percentage=round(approved_count / total * 100, 1),
            )
        )

        # Goulet d'étranglement: couche avec le plus de rejets
        bottleneck = (
            max(rejections_by_layer.items(), key=lambda x: x[1])[0]
            if rejections_by_layer
            else "N/A"
        )

        funnel = SankeyFunnel(
            conversion_by_layer=tuple(conversions),
            overall_conversion=round(approved_count / total, 4) if total > 0 else 0.0,
            biggest_bottleneck=bottleneck,
        )

        return SankeyDiagram(
            sankey_id=f"sk_{now_us()}",
            time_range=time_range,
            total_packets=total,
            nodes=tuple(nodes),
            flows=tuple(flows),
            funnel=funnel,
            generated_at_us=now_us(),
        )

    @staticmethod
    def _empty(time_range: TimeRange) -> SankeyDiagram:
        return SankeyDiagram(
            sankey_id=f"sk_empty_{now_us()}",
            time_range=time_range,
            total_packets=0,
            nodes=(),
            flows=(),
            funnel=SankeyFunnel(
                conversion_by_layer=(),
                overall_conversion=0.0,
                biggest_bottleneck="N/A",
            ),
            generated_at_us=now_us(),
        )


# ── Engine ─────────────────────────────────────────────────────────────────────


class DecisionSankeyEngine:
    """D06 — Diagramme Sankey du funnel décisionnel."""

    def __init__(self) -> None:
        self._store = DIPStore.instance()
        self._cache: LRUCache[SankeyDiagram] = LRUCache(
            max_entries=100, ttl_seconds=3_600
        )

    def generate_sankey(
        self, hours: int = 24, symbol: Optional[str] = None
    ) -> SankeyDiagram:
        cache_key = f"sankey_{hours}_{symbol or 'all'}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached
        tr = TimeRange.last_hours(hours)
        rows = self._store.get_decisions(
            symbol=symbol, start_us=tr.start_us, limit=50_000
        )
        diagram = SankeyBuilder.build(rows, tr)
        self._cache.set(cache_key, diagram)
        return diagram

    def get_funnel_metrics(self, hours: int = 24) -> SankeyFunnel:
        return self.generate_sankey(hours).funnel

    def get_conversion_rates(self, hours: int = 24) -> dict[str, float]:
        funnel = self.get_funnel_metrics(hours)
        return {lc.layer: lc.pass_rate for lc in funnel.conversion_by_layer}

    def get_flow_between(
        self, layer_a: str, layer_b: str, hours: int = 24
    ) -> Optional[SankeyFlow]:
        diagram = self.generate_sankey(hours)
        for flow in diagram.flows:
            if layer_a in flow.source_id and layer_b in flow.target_id:
                return flow
        return None


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[DecisionSankeyEngine] = None
_engine_lock = threading.Lock()


def get_sankey_engine() -> DecisionSankeyEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = DecisionSankeyEngine()
    return _engine
