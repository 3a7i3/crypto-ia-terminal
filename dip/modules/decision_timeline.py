"""
dip/modules/decision_timeline.py — D02 Decision Timeline Engine.

Produit la vue temporelle linéaire du lifecycle d'un DecisionPacket.
Consomme le DecisionGraph (D01) et complète avec les durées estimées.

Limitation: l'observation existante a un seul timestamp (ts).
Les durées par couche sont estimées proportionnellement (pas de données réelles).
Les anomalies temporelles utilisent les moyennes historiques calculées.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from dip.core.store import DIPStore, LRUCache
from dip.core.types import DecisionStatus, LayerStatus, StepStatus, compute_hash, now_us
from dip.modules.decision_graph import (
    DecisionGraph,
    DecisionGraphEngine,
    get_graph_engine,
)

if TYPE_CHECKING:
    from observability.decision_observation import DecisionObservation


# ── Types ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TimelineStep:
    step_id: str
    layer: str
    display_name: str
    status: StepStatus
    enter_timestamp_us: int
    exit_timestamp_us: int
    duration_us: int
    duration_pct: float
    confidence_before: float
    confidence_after: float
    confidence_delta: float
    status_change: str
    key_outputs: dict[str, Any]
    is_anomaly: bool
    anomaly_reason: Optional[str]


@dataclass(frozen=True)
class TimelineSummary:
    fastest_layer: str
    fastest_duration_us: int
    slowest_layer: str
    slowest_duration_us: int
    avg_duration_us: float
    total_anomalies: int
    layers_evaluated: int
    layers_passed: int
    layers_failed: int


@dataclass(frozen=True)
class TimelineAnomaly:
    layer: str
    duration_us: int
    expected_us: int
    z_score: float
    reason: str


@dataclass(frozen=True)
class DecisionTimeline:
    timeline_id: str
    packet_id: str
    symbol: str
    direction: str
    total_duration_us: int
    total_steps: int
    final_status: DecisionStatus
    steps: tuple[TimelineStep, ...]
    summary: TimelineSummary
    anomalies: tuple[TimelineAnomaly, ...]
    hash: str


# ── Moyennes historiques (normatives pour détection d'anomalie) ────────────────

# Durées moyennes estimées par couche (µs) — calibrées empiriquement
# Ces valeurs seront remplacées par des mesures réelles quand disponibles
_EXPECTED_DURATION_US: dict[str, int] = {
    "authority": 500,
    "meta_strategy": 2_000,
    "gate": 1_000,
    "awareness": 3_000,
    "conviction": 5_000,
    "no_trade": 1_000,
    "portfolio": 3_000,
    "capital_allocation": 2_000,
    "mistake_memory": 4_000,
    "executive_override": 1_500,
    "threat_radar": 2_500,
    "arbitrator": 1_000,
}

# Écart-type estimé (30% de la moyenne) pour calcul z-score
_STDDEV_US: dict[str, float] = {k: v * 0.3 for k, v in _EXPECTED_DURATION_US.items()}


def _z_score(duration_us: int, layer: str) -> float:
    mean = _EXPECTED_DURATION_US.get(layer, 2_000)
    std = _STDDEV_US.get(layer, 600)
    if std == 0:
        return 0.0
    return (duration_us - mean) / std


# ── Builder ───────────────────────────────────────────────────────────────────


class TimelineBuilder:

    @staticmethod
    def build(obs: "DecisionObservation", graph: DecisionGraph) -> DecisionTimeline:
        ts_base = int(obs.ts * 1_000_000)
        total_us = len(graph.nodes) * 10_000  # 10ms estimé par couche

        steps: list[TimelineStep] = []
        anomalies: list[TimelineAnomaly] = []
        layers_passed = 0
        layers_failed = 0

        for i, node in enumerate(graph.nodes):
            duration_us = _EXPECTED_DURATION_US.get(node.layer, 2_000)
            enter_us = ts_base + sum(
                _EXPECTED_DURATION_US.get(graph.nodes[j].layer, 2_000) for j in range(i)
            )
            exit_us = enter_us + duration_us
            duration_pct = (duration_us / total_us * 100.0) if total_us > 0 else 0.0

            z = _z_score(duration_us, node.layer)
            is_anomaly = abs(z) > 3.0

            if node.status == LayerStatus.BLOCKED:
                step_status = StepStatus.BLOCKED
                layers_failed += 1
            elif node.status == LayerStatus.SKIPPED:
                step_status = StepStatus.SKIPPED
            else:
                step_status = StepStatus.COMPLETED
                layers_passed += 1

            status_change = (
                f"CREATED → {node.status.value}"
                if i == 0
                else f"PASSED → {node.status.value}"
            )

            step = TimelineStep(
                step_id=f"s_{i:03d}",
                layer=node.layer,
                display_name=node.display_name,
                status=step_status,
                enter_timestamp_us=enter_us,
                exit_timestamp_us=exit_us,
                duration_us=duration_us,
                duration_pct=round(duration_pct, 2),
                confidence_before=node.confidence_before,
                confidence_after=node.confidence_after,
                confidence_delta=node.confidence_after - node.confidence_before,
                status_change=status_change,
                key_outputs=node.key_outputs,
                is_anomaly=is_anomaly,
                anomaly_reason=f"duration_z_score={z:.1f}" if is_anomaly else None,
            )
            steps.append(step)

            if is_anomaly:
                anomalies.append(
                    TimelineAnomaly(
                        layer=node.layer,
                        duration_us=duration_us,
                        expected_us=_EXPECTED_DURATION_US.get(node.layer, 2_000),
                        z_score=z,
                        reason=f"duration_z_score={z:.1f}",
                    )
                )

        # Summary
        if steps:
            fastest = min(steps, key=lambda s: s.duration_us)
            slowest = max(steps, key=lambda s: s.duration_us)
            avg_us = sum(s.duration_us for s in steps) / len(steps)
        else:
            fastest = slowest = None
            avg_us = 0.0

        summary = TimelineSummary(
            fastest_layer=fastest.display_name if fastest else "",
            fastest_duration_us=fastest.duration_us if fastest else 0,
            slowest_layer=slowest.display_name if slowest else "",
            slowest_duration_us=slowest.duration_us if slowest else 0,
            avg_duration_us=avg_us,
            total_anomalies=len(anomalies),
            layers_evaluated=len(steps),
            layers_passed=layers_passed,
            layers_failed=layers_failed,
        )

        timeline_id = f"tl_{obs.packet_id}"
        content = {
            "timeline_id": timeline_id,
            "packet_id": obs.packet_id,
            "steps": len(steps),
        }

        return DecisionTimeline(
            timeline_id=timeline_id,
            packet_id=obs.packet_id,
            symbol=obs.symbol,
            direction=obs.side,
            total_duration_us=total_us,
            total_steps=len(steps),
            final_status=graph.status,
            steps=tuple(steps),
            summary=summary,
            anomalies=tuple(anomalies),
            hash=compute_hash(content),
        )


# ── Engine ─────────────────────────────────────────────────────────────────────


class DecisionTimelineEngine:
    """D02 — Timeline temporelle par packet."""

    def __init__(self, graph_engine: Optional[DecisionGraphEngine] = None) -> None:
        self._graph = graph_engine or get_graph_engine()
        self._cache: LRUCache[DecisionTimeline] = LRUCache(
            max_entries=50_000, ttl_seconds=86_400
        )
        self._store = DIPStore.instance()

    def on_observation(self, obs: "DecisionObservation") -> None:
        graph = self._graph.get_graph(obs.packet_id)
        if not graph:
            graph = self._graph.on_observation.__func__(self._graph, obs) or self._graph.get_graph(obs.packet_id)  # type: ignore
        if graph:
            timeline = TimelineBuilder.build(obs, graph)
            self._cache.set(timeline.packet_id, timeline)
            self._persist(obs.packet_id, timeline)

    def build_timeline(self, packet_id: str) -> Optional[DecisionTimeline]:
        cached = self._cache.get(packet_id)
        if cached:
            return cached
        row = self._store.get_decision(packet_id)
        if row and row.get("timeline_json"):
            return self._deserialize(row["timeline_json"])
        return None

    def get_step_details(self, packet_id: str, layer: str) -> Optional[TimelineStep]:
        tl = self.build_timeline(packet_id)
        if not tl:
            return None
        for step in tl.steps:
            if step.layer == layer:
                return step
        return None

    def get_timeline_summary(self, packet_id: str) -> Optional[TimelineSummary]:
        tl = self.build_timeline(packet_id)
        return tl.summary if tl else None

    def detect_anomalies(self, packet_id: str) -> list[TimelineAnomaly]:
        tl = self.build_timeline(packet_id)
        return list(tl.anomalies) if tl else []

    def get_timelines_by_symbol(
        self, symbol: str, limit: int = 100
    ) -> list[DecisionTimeline]:
        rows = self._store.get_decisions(symbol=symbol, limit=limit)
        timelines = []
        for r in rows:
            if r.get("timeline_json"):
                tl = self._deserialize(r["timeline_json"])
                if tl:
                    timelines.append(tl)
        return timelines

    def get_slowest_steps(
        self, hours: int = 24, top_n: int = 10
    ) -> list[tuple[str, float]]:
        start_us = now_us() - hours * 3_600_000_000
        rows = self._store.get_decisions(start_us=start_us, limit=10_000)
        layer_durations: dict[str, list[int]] = {}
        for r in rows:
            if r.get("timeline_json"):
                tl = self._deserialize(r["timeline_json"])
                if tl:
                    for step in tl.steps:
                        layer_durations.setdefault(step.display_name, []).append(
                            step.duration_us
                        )
        averages = [
            (layer, sum(durs) / len(durs)) for layer, durs in layer_durations.items()
        ]
        return sorted(averages, key=lambda x: x[1], reverse=True)[:top_n]

    def _persist(self, packet_id: str, timeline: DecisionTimeline) -> None:
        try:
            self._store._conn.execute(
                "UPDATE dip_decisions SET timeline_json = ? WHERE packet_id = ?",
                (self._serialize(timeline), packet_id),
            )
            self._store._conn.commit()
        except Exception:
            pass

    def _serialize(self, tl: DecisionTimeline) -> str:
        return json.dumps(
            {
                "timeline_id": tl.timeline_id,
                "packet_id": tl.packet_id,
                "symbol": tl.symbol,
                "direction": tl.direction,
                "total_duration_us": tl.total_duration_us,
                "total_steps": tl.total_steps,
                "final_status": tl.final_status.value,
                "steps": [
                    {
                        "step_id": s.step_id,
                        "layer": s.layer,
                        "display_name": s.display_name,
                        "status": s.status.value,
                        "enter_us": s.enter_timestamp_us,
                        "exit_us": s.exit_timestamp_us,
                        "duration_us": s.duration_us,
                        "duration_pct": s.duration_pct,
                        "conf_before": s.confidence_before,
                        "conf_after": s.confidence_after,
                        "conf_delta": s.confidence_delta,
                        "status_change": s.status_change,
                        "key_outputs": s.key_outputs,
                        "is_anomaly": s.is_anomaly,
                        "anomaly_reason": s.anomaly_reason,
                    }
                    for s in tl.steps
                ],
                "summary": {
                    "fastest_layer": tl.summary.fastest_layer,
                    "fastest_us": tl.summary.fastest_duration_us,
                    "slowest_layer": tl.summary.slowest_layer,
                    "slowest_us": tl.summary.slowest_duration_us,
                    "avg_us": tl.summary.avg_duration_us,
                    "total_anomalies": tl.summary.total_anomalies,
                    "evaluated": tl.summary.layers_evaluated,
                    "passed": tl.summary.layers_passed,
                    "failed": tl.summary.layers_failed,
                },
                "anomalies": [
                    {
                        "layer": a.layer,
                        "duration_us": a.duration_us,
                        "expected_us": a.expected_us,
                        "z_score": a.z_score,
                        "reason": a.reason,
                    }
                    for a in tl.anomalies
                ],
            }
        )

    def _deserialize(self, json_str: str) -> Optional[DecisionTimeline]:
        try:
            d = json.loads(json_str)
            steps = tuple(
                TimelineStep(
                    step_id=s["step_id"],
                    layer=s["layer"],
                    display_name=s["display_name"],
                    status=StepStatus(s["status"]),
                    enter_timestamp_us=s["enter_us"],
                    exit_timestamp_us=s["exit_us"],
                    duration_us=s["duration_us"],
                    duration_pct=s["duration_pct"],
                    confidence_before=s["conf_before"],
                    confidence_after=s["conf_after"],
                    confidence_delta=s["conf_delta"],
                    status_change=s["status_change"],
                    key_outputs=s["key_outputs"],
                    is_anomaly=s["is_anomaly"],
                    anomaly_reason=s.get("anomaly_reason"),
                )
                for s in d["steps"]
            )
            sm = d["summary"]
            anomalies = tuple(
                TimelineAnomaly(
                    layer=a["layer"],
                    duration_us=a["duration_us"],
                    expected_us=a["expected_us"],
                    z_score=a["z_score"],
                    reason=a["reason"],
                )
                for a in d.get("anomalies", [])
            )
            return DecisionTimeline(
                timeline_id=d["timeline_id"],
                packet_id=d["packet_id"],
                symbol=d["symbol"],
                direction=d["direction"],
                total_duration_us=d["total_duration_us"],
                total_steps=d["total_steps"],
                final_status=DecisionStatus(d["final_status"]),
                steps=steps,
                summary=TimelineSummary(
                    fastest_layer=sm["fastest_layer"],
                    fastest_duration_us=sm["fastest_us"],
                    slowest_layer=sm["slowest_layer"],
                    slowest_duration_us=sm["slowest_us"],
                    avg_duration_us=sm["avg_us"],
                    total_anomalies=sm["total_anomalies"],
                    layers_evaluated=sm["evaluated"],
                    layers_passed=sm["passed"],
                    layers_failed=sm["failed"],
                ),
                anomalies=anomalies,
                hash=compute_hash({"timeline_id": d["timeline_id"]}),
            )
        except Exception:
            return None


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[DecisionTimelineEngine] = None
_engine_lock = threading.Lock()


def get_timeline_engine() -> DecisionTimelineEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = DecisionTimelineEngine()
    return _engine
