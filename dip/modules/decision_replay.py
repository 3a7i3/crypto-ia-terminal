"""
dip/modules/decision_replay.py — D07 Decision Replay Engine.

Rejoue une décision passée pas à pas à partir du graph stocké.
Permet d'inspecter l'état du pipeline à chaque étape.

Passif: lit uniquement le DIPStore. Ne touche jamais au moteur de décision.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

from dip.core.store import DIPStore, LRUCache
from dip.core.types import LayerStatus, ReplayStatus, StepStatus, now_us
from dip.modules.decision_graph import DecisionGraph, get_graph_engine
from dip.modules.decision_timeline import DecisionTimeline, get_timeline_engine

# ── Types ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReplayStep:
    step_index: int
    layer: str
    status: LayerStatus
    confidence_before: float
    confidence_after: float
    confidence_delta: float
    duration_us: int
    reason: str
    is_blocker: bool
    is_critical_path: bool
    step_status: StepStatus


@dataclass(frozen=True)
class ReplayState:
    current_step: int
    total_steps: int
    steps_completed: tuple[ReplayStep, ...]
    current_confidence: float
    is_finished: bool
    is_approved: bool


@dataclass(frozen=True)
class ReplaySession:
    session_id: str
    packet_id: str
    symbol: str
    direction: str
    regime: str
    total_steps: int
    steps: tuple[ReplayStep, ...]
    final_status: str
    replay_status: ReplayStatus
    created_at_us: int


@dataclass(frozen=True)
class ReplayAnnotation:
    step_index: int
    layer: str
    annotation: str
    author: str
    created_at_us: int


@dataclass(frozen=True)
class ReplayComparison:
    packet_id_a: str
    packet_id_b: str
    steps_a: tuple[ReplayStep, ...]
    steps_b: tuple[ReplayStep, ...]
    divergence_layer: Optional[str]
    divergence_step: Optional[int]
    summary: str


# ── Builder ───────────────────────────────────────────────────────────────────


class ReplayBuilder:

    @staticmethod
    def build(
        graph: DecisionGraph,
        timeline: Optional[DecisionTimeline],
        packet_id: str,
        row: dict,
    ) -> ReplaySession:
        steps = []
        critical_path_ids = set(graph.critical_path)  # node_ids (strings)
        timeline_by_layer = {}
        if timeline:
            for step in timeline.steps:
                timeline_by_layer[step.layer] = step.duration_us

        for i, node in enumerate(graph.nodes):
            duration = timeline_by_layer.get(node.layer, 0)

            step_status = StepStatus.COMPLETED
            if node.status == LayerStatus.BLOCKED:
                step_status = StepStatus.BLOCKED
            elif node.status == LayerStatus.SKIPPED:
                step_status = StepStatus.SKIPPED

            steps.append(
                ReplayStep(
                    step_index=i,
                    layer=node.layer,
                    status=node.status,
                    confidence_before=node.confidence_before,
                    confidence_after=node.confidence_after,
                    confidence_delta=round(
                        node.confidence_after - node.confidence_before, 4
                    ),
                    duration_us=duration,
                    reason=node.reasoning,
                    is_blocker=node.status == LayerStatus.BLOCKED,
                    is_critical_path=node.node_id in critical_path_ids,
                    step_status=step_status,
                )
            )

        return ReplaySession(
            session_id=f"replay_{packet_id}_{now_us()}",
            packet_id=packet_id,
            symbol=row.get("symbol", "?"),
            direction=row.get("direction", "?"),
            regime=row.get("regime", "?"),
            total_steps=len(steps),
            steps=tuple(steps),
            final_status="APPROVED" if graph.status.value == "APPROVED" else "REJECTED",
            replay_status=ReplayStatus.COMPLETED,
            created_at_us=now_us(),
        )


# ── Interactive Replay ────────────────────────────────────────────────────────


class InteractiveReplay:
    """État d'un replay interactif step-by-step."""

    def __init__(self, session: ReplaySession) -> None:
        self._session = session
        self._current = 0
        self._annotations: list[ReplayAnnotation] = []

    def current_state(self) -> ReplayState:
        completed = self._session.steps[: self._current]
        last_conf = completed[-1].confidence_after if completed else 1.0
        return ReplayState(
            current_step=self._current,
            total_steps=self._session.total_steps,
            steps_completed=completed,
            current_confidence=last_conf,
            is_finished=self._current >= self._session.total_steps,
            is_approved=self._session.final_status == "APPROVED",
        )

    def step_forward(self) -> Optional[ReplayStep]:
        if self._current >= self._session.total_steps:
            return None
        step = self._session.steps[self._current]
        self._current += 1
        return step

    def step_backward(self) -> Optional[ReplayStep]:
        if self._current <= 0:
            return None
        self._current -= 1
        return self._session.steps[self._current]

    def jump_to(self, step_index: int) -> ReplayState:
        self._current = max(0, min(step_index, self._session.total_steps))
        return self.current_state()

    def jump_to_blocker(self) -> Optional[ReplayStep]:
        for step in self._session.steps:
            if step.is_blocker:
                self._current = step.step_index + 1
                return step
        return None

    def add_annotation(
        self, step_index: int, text: str, author: str = "operator"
    ) -> None:
        self._annotations.append(
            ReplayAnnotation(
                step_index=step_index,
                layer=(
                    self._session.steps[step_index].layer
                    if step_index < len(self._session.steps)
                    else "?"
                ),
                annotation=text,
                author=author,
                created_at_us=now_us(),
            )
        )

    def get_annotations(self) -> list[ReplayAnnotation]:
        return list(self._annotations)


# ── Engine ─────────────────────────────────────────────────────────────────────


class DecisionReplayEngine:
    """D07 — Moteur de replay décisionnel."""

    def __init__(self) -> None:
        self._store = DIPStore.instance()
        self._graph_engine = get_graph_engine()
        self._timeline_engine = get_timeline_engine()
        self._cache: LRUCache[ReplaySession] = LRUCache(
            max_entries=1_000, ttl_seconds=3_600
        )
        self._active_replays: dict[str, InteractiveReplay] = {}
        self._lock = threading.Lock()

    def build_replay(self, packet_id: str) -> Optional[ReplaySession]:
        cached = self._cache.get(packet_id)
        if cached:
            return cached

        row = self._store.get_decision(packet_id)
        if not row:
            return None

        graph = self._graph_engine.get_graph(packet_id)
        if not graph:
            return None

        timeline = self._timeline_engine.build_timeline(packet_id)
        session = ReplayBuilder.build(graph, timeline, packet_id, row)
        self._cache.set(packet_id, session)
        return session

    def start_interactive(self, packet_id: str) -> Optional[str]:
        """Démarre un replay interactif. Retourne l'ID de session."""
        session = self.build_replay(packet_id)
        if not session:
            return None
        replay_id = f"ir_{packet_id}"
        with self._lock:
            self._active_replays[replay_id] = InteractiveReplay(session)
        return replay_id

    def get_replay(self, replay_id: str) -> Optional[InteractiveReplay]:
        with self._lock:
            return self._active_replays.get(replay_id)

    def step_forward(self, replay_id: str) -> Optional[ReplayStep]:
        ir = self.get_replay(replay_id)
        return ir.step_forward() if ir else None

    def step_backward(self, replay_id: str) -> Optional[ReplayStep]:
        ir = self.get_replay(replay_id)
        return ir.step_backward() if ir else None

    def jump_to_blocker(self, replay_id: str) -> Optional[ReplayStep]:
        ir = self.get_replay(replay_id)
        return ir.jump_to_blocker() if ir else None

    def get_state(self, replay_id: str) -> Optional[ReplayState]:
        ir = self.get_replay(replay_id)
        return ir.current_state() if ir else None

    def close(self, replay_id: str) -> None:
        with self._lock:
            self._active_replays.pop(replay_id, None)

    def compare(self, packet_id_a: str, packet_id_b: str) -> Optional[ReplayComparison]:
        sa = self.build_replay(packet_id_a)
        sb = self.build_replay(packet_id_b)
        if not sa or not sb:
            return None

        # Trouver la couche de divergence
        steps_a = {s.layer: s for s in sa.steps}
        steps_b = {s.layer: s for s in sb.steps}

        divergence_layer = None
        divergence_step = None
        for i, step in enumerate(sa.steps):
            b_step = steps_b.get(step.layer)
            if b_step and step.status != b_step.status:
                divergence_layer = step.layer
                divergence_step = i
                break

        if divergence_layer:
            summary = (
                f"Divergence à la couche '{divergence_layer}' (step {divergence_step}): "
                f"{packet_id_a} → {steps_a[divergence_layer].status.value}, "
                f"{packet_id_b} → {steps_b[divergence_layer].status.value}"
            )
        else:
            summary = f"Trajectoires identiques ({sa.total_steps} étapes). Résultats: {sa.final_status} vs {sb.final_status}"

        return ReplayComparison(
            packet_id_a=packet_id_a,
            packet_id_b=packet_id_b,
            steps_a=sa.steps,
            steps_b=sb.steps,
            divergence_layer=divergence_layer,
            divergence_step=divergence_step,
            summary=summary,
        )

    def get_recent_sessions(self, limit: int = 10) -> list[ReplaySession]:
        rows = self._store.get_decisions(limit=limit)
        sessions = []
        for r in rows:
            s = self.build_replay(r["packet_id"])
            if s:
                sessions.append(s)
        return sessions


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[DecisionReplayEngine] = None
_engine_lock = threading.Lock()


def get_replay_engine() -> DecisionReplayEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = DecisionReplayEngine()
    return _engine
