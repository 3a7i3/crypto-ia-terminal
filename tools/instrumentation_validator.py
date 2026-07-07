"""
tools/instrumentation_validator.py -- INV-IV: DIP Instrumentation Validation Suite.

Verifie que le DIP observe correctement le moteur avant de lancer S1.
Le pipeline d'observation doit etre certifie AVANT de collecter des donnees.

Moteur de trading -> DIP -> dataset -> S1
Si le DIP est imparfait, S1 certifiera un mauvais dataset.

Usage:
    python tools/instrumentation_validator.py              # tous les checks
    python tools/instrumentation_validator.py --check IV-006
    python tools/instrumentation_validator.py --verbose
    python tools/instrumentation_validator.py --json

Certification:
    10/10 PASS  -> CERTIFIED_OBSERVER  -> S1 autorise
    8-9/10 PASS -> CONDITIONAL         -> corriger avant S1
    <8/10 PASS  -> NOT_CERTIFIED       -> S1 interdit
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dip.core.store import DIPStore  # noqa: E402
from dip.core.types import (  # noqa: E402,F401
    LAYER_DISPLAY,
    LAYER_ORDER,
    LayerStatus,
    TimeRange,
    now_us,
)
from dip.modules.causal_tree import CausalTreeBuilder  # noqa: E402
from dip.modules.counterfactual import PipelineSimulator  # noqa: E402
from dip.modules.decision_graph import DecisionGraphEngine, GraphBuilder  # noqa: E402
from dip.modules.decision_heatmap import (  # noqa: E402
    _LAYER_DISPLAY_NAMES,
    HeatmapBuilder,
)
from dip.modules.decision_replay import ReplayBuilder  # noqa: E402
from dip.modules.decision_timeline import TimelineBuilder  # noqa: E402

# -- CheckResult ----------------------------------------------------------------


@dataclass
class CheckResult:
    check_id: str
    name: str
    passed: bool
    duration_ms: float
    details: str
    metrics: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"


# -- Observation factory --------------------------------------------------------


def _make_obs(
    *,
    trade_allowed: bool = True,
    symbol: str = "BTCUSDT",
    regime: str = "SIDEWAYS",
    score: float = 75.0,
    blocker: Optional[str] = None,
    ts: Optional[float] = None,
    packet_id: Optional[str] = None,
) -> Any:
    obs = MagicMock()
    obs.packet_id = packet_id or str(uuid.uuid4())
    obs.symbol = symbol
    obs.side = "LONG"
    obs.direction = "LONG"
    obs.trade_allowed = trade_allowed
    obs.regime = regime
    obs.score = score
    obs.personality_name = "momentum"
    obs.ts = ts or time.time()

    obs.authority_ok = True
    obs.meta_allowed = True
    obs.meta_reason = "OK"
    obs.gate_allowed = True
    obs.gate_failed = None
    obs.awareness_ok = True
    obs.awareness_level = "NORMAL"
    obs.conviction_ok = True
    obs.conviction_level = "HIGH"
    obs.conviction_score = 0.75
    obs.conviction_size_factor = 1.0
    obs.notrade_ok = True
    obs.notrade_reason = None
    obs.notrade_rejection_score = 0.0
    obs.portfolio_ok = True
    obs.portfolio_reason = None
    obs.portfolio_size_factor = 1.0
    obs.cae_ok = True
    obs.cae_size_usd = 10.0
    obs.cae_kelly = 0.3
    obs.cae_ev = 0.05
    obs.mistake_ok = True
    obs.mistake_reason = None
    obs.override_ok = True
    obs.override_level = "NONE"
    obs.override_size_factor = 1.0
    obs.override_reason = None
    obs.radar_ok = True
    obs.radar_level = "LOW"
    obs.radar_threat_count = 0
    obs.arbitration_decision = "APPROVED"
    obs.first_blocker = None
    obs.all_blockers = []

    if not trade_allowed:
        target = blocker or "meta_strategy"
        obs.first_blocker = LAYER_DISPLAY.get(target, target)
        obs.all_blockers = [LAYER_DISPLAY.get(target, target)]
        obs.arbitration_decision = "REJECTED"
        _apply_blocker(obs, target)

    return obs


def _apply_blocker(obs: Any, layer: str) -> None:
    if layer == "authority":
        obs.authority_ok = False
    elif layer == "meta_strategy":
        obs.meta_allowed = False
        obs.meta_reason = "confidence_too_low"
    elif layer == "gate":
        obs.gate_allowed = False
        obs.gate_failed = ["score_insufficient"]
    elif layer == "awareness":
        obs.awareness_ok = False
        obs.awareness_level = "DEGRADED"
    elif layer == "conviction":
        obs.conviction_ok = False
        obs.conviction_level = "LOW"
    elif layer == "no_trade":
        obs.notrade_ok = False
        obs.notrade_reason = "cooldown_active"
    elif layer == "portfolio":
        obs.portfolio_ok = False
        obs.portfolio_reason = "max_exposure_reached"
    elif layer == "capital_allocation":
        obs.cae_ok = False
    elif layer == "mistake_memory":
        obs.mistake_ok = False
        obs.mistake_reason = "known_losing_pattern"
    elif layer == "executive_override":
        obs.override_ok = False
        obs.override_level = "DRAWDOWN"
        obs.override_reason = "max_drawdown_hit"
    elif layer == "threat_radar":
        obs.radar_ok = False
        obs.radar_level = "HIGH"
        obs.radar_threat_count = 3
    elif layer == "arbitrator":
        obs.arbitration_decision = "CONFLICT"


# -- Store helpers --------------------------------------------------------------


def _fresh_store() -> tuple[DIPStore, Path]:
    tmp = Path(tempfile.gettempdir()) / f"inv_iv_{uuid.uuid4().hex[:8]}.sqlite"
    DIPStore._instance = None
    return DIPStore.instance(db_path=tmp), tmp


# ===============================================================================
# IV-001 -- Packet Coverage
# ===============================================================================


def check_iv001(verbose: bool = False) -> CheckResult:
    """Chaque observation injectee est-elle persistee dans DIPStore?"""
    start = time.time()
    N = 20
    try:
        store, _ = _fresh_store()
        engine = DecisionGraphEngine()

        packet_ids = []
        for i in range(N):
            obs = _make_obs(trade_allowed=(i % 2 == 0))
            engine.on_observation(obs)
            packet_ids.append(obs.packet_id)

        count = store.count_decisions()
        missing = [pid for pid in packet_ids if store.get_decision(pid) is None]

        passed = count == N and len(missing) == 0
        return CheckResult(
            check_id="IV-001",
            name="Packet Coverage",
            passed=passed,
            duration_ms=(time.time() - start) * 1000,
            details=(
                f"{N} injectes -> {count} dans DIPStore"
                + (f" -- {len(missing)} manquant(s)" if missing else "")
            ),
            metrics={"injected": N, "found": count, "missing": len(missing)},
            error=f"Manquants: {missing[:3]}" if missing else None,
        )
    except Exception:
        return CheckResult(
            check_id="IV-001",
            name="Packet Coverage",
            passed=False,
            duration_ms=(time.time() - start) * 1000,
            details="Exception",
            error=traceback.format_exc(),
        )


# ===============================================================================
# IV-002 -- Rejection Events
# ===============================================================================


def check_iv002(verbose: bool = False) -> CheckResult:
    """Chaque rejet produit-il un noeud BLOCKED + first_blocker non-null?"""
    start = time.time()
    from dip.core.types import DecisionStatus

    errors: list[str] = []
    try:
        for layer in LAYER_ORDER:
            obs = _make_obs(trade_allowed=False, blocker=layer)
            graph = GraphBuilder.build(obs)
            pid = obs.packet_id[:8]

            if not obs.first_blocker:
                errors.append(f"{layer}: obs.first_blocker est None")

            blocked = [n for n in graph.nodes if n.status == LayerStatus.BLOCKED]
            if not blocked:
                errors.append(f"{layer}: aucun noeud BLOCKED dans le graphe")

            if graph.status != DecisionStatus.REJECTED:
                errors.append(f"{layer}: graph.status={graph.status.value}")

            if not graph.metrics.rejection_layer:
                errors.append(f"{layer}: metrics.rejection_layer est None")

        passed = len(errors) == 0
        return CheckResult(
            check_id="IV-002",
            name="Rejection Events",
            passed=passed,
            duration_ms=(time.time() - start) * 1000,
            details=(
                f"12/12 couches -> BLOCKED correct"
                if not errors
                else f"{len(errors)} erreurs sur 12 couches"
            ),
            metrics={"layers_tested": 12, "errors": len(errors)},
            error="\n".join(errors) if errors else None,
        )
    except Exception:
        return CheckResult(
            check_id="IV-002",
            name="Rejection Events",
            passed=False,
            duration_ms=(time.time() - start) * 1000,
            details="Exception",
            error=traceback.format_exc(),
        )


# ===============================================================================
# IV-003 -- Regret Parent Uniqueness
# ===============================================================================


def check_iv003(verbose: bool = False) -> CheckResult:
    """Chaque rejet possede-t-il exactement un RootCause (parent unique)?"""
    start = time.time()
    N = 24
    errors: list[str] = []
    try:
        for i in range(N):
            layer = LAYER_ORDER[i % len(LAYER_ORDER)]
            obs = _make_obs(trade_allowed=False, blocker=layer)
            graph = GraphBuilder.build(obs)
            tree = CausalTreeBuilder.build(obs, graph)
            pid = obs.packet_id[:8]

            # Exactement un root cause
            rc = tree.root_cause
            if rc.causing_layer not in LAYER_ORDER:
                errors.append(
                    f"{pid}: causing_layer='{rc.causing_layer}' hors LAYER_ORDER"
                )

            if not (0.0 <= rc.confidence <= 1.0):
                errors.append(f"{pid}: rc.confidence={rc.confidence:.3f} hors [0,1]")

            if len(tree.causal_paths) == 0:
                errors.append(f"{pid}: aucun causal_path")

            # Root cause correspond au blocker attendu
            if rc.causing_layer != layer:
                errors.append(f"{pid}: root_cause={rc.causing_layer}, attendu={layer}")

        passed = len(errors) == 0
        return CheckResult(
            check_id="IV-003",
            name="Regret Parent Uniqueness",
            passed=passed,
            duration_ms=(time.time() - start) * 1000,
            details=(
                f"{N} rejets -> RootCause unique et valide"
                if not errors
                else f"{len(errors)} erreurs sur {N}"
            ),
            metrics={"tested": N, "errors": len(errors)},
            error="\n".join(errors[:5]) if errors else None,
        )
    except Exception:
        return CheckResult(
            check_id="IV-003",
            name="Regret Parent Uniqueness",
            passed=False,
            duration_ms=(time.time() - start) * 1000,
            details="Exception",
            error=traceback.format_exc(),
        )


# ===============================================================================
# IV-004 -- Graph Completeness
# ===============================================================================


def check_iv004(verbose: bool = False) -> CheckResult:
    """Le DecisionGraph est-il complet (nodes, edges, critical_path)?"""
    start = time.time()
    N = 24
    errors: list[str] = []
    try:
        for i in range(N):
            trade_allowed = i % 3 != 0
            blocker = LAYER_ORDER[i % len(LAYER_ORDER)] if not trade_allowed else None
            obs = _make_obs(trade_allowed=trade_allowed, blocker=blocker)
            graph = GraphBuilder.build(obs)
            pid = obs.packet_id[:8]

            if len(graph.nodes) == 0:
                errors.append(f"{pid}: aucun noeud")
                continue

            # Pas de node_id dupliques
            node_ids = [n.node_id for n in graph.nodes]
            if len(set(node_ids)) != len(node_ids):
                errors.append(f"{pid}: node_ids dupliques")

            # Chaine lineaire: edges consecutifs
            for j in range(1, len(graph.nodes)):
                src = graph.nodes[j - 1].node_id
                tgt = graph.nodes[j].node_id
                if not any(
                    e.source_node_id == src and e.target_node_id == tgt
                    for e in graph.edges
                ):
                    errors.append(f"{pid}: arete manquante {src}->{tgt}")

            # edges = nodes - 1
            expected_edges = len(graph.nodes) - 1
            if len(graph.edges) != expected_edges:
                errors.append(f"{pid}: {len(graph.edges)} aretes != {expected_edges}")

            # critical_path non-vide
            if not graph.critical_path:
                errors.append(f"{pid}: critical_path vide")

            # Approuve -> 12 couches
            if trade_allowed and len(graph.nodes) != len(LAYER_ORDER):
                errors.append(
                    f"{pid}: approuve mais {len(graph.nodes)} noeuds "
                    f"(attendu {len(LAYER_ORDER)})"
                )

            # Rejete -> dernier noeud BLOCKED
            if not trade_allowed:
                last = graph.nodes[-1]
                if last.status != LayerStatus.BLOCKED:
                    errors.append(f"{pid}: dernier noeud status={last.status.value}")

        passed = len(errors) == 0
        return CheckResult(
            check_id="IV-004",
            name="Graph Completeness",
            passed=passed,
            duration_ms=(time.time() - start) * 1000,
            details=(
                f"{N} graphes complets et valides"
                if not errors
                else f"{len(errors)} erreurs sur {N}"
            ),
            metrics={"tested": N, "errors": len(errors)},
            error="\n".join(errors[:5]) if errors else None,
        )
    except Exception:
        return CheckResult(
            check_id="IV-004",
            name="Graph Completeness",
            passed=False,
            duration_ms=(time.time() - start) * 1000,
            details="Exception",
            error=traceback.format_exc(),
        )


# ===============================================================================
# IV-005 -- Timeline Coherence
# ===============================================================================


def check_iv005(verbose: bool = False) -> CheckResult:
    """Le DecisionTimeline est-il coherent (monotone, pas de doublons)?"""
    start = time.time()
    N = 20
    errors: list[str] = []
    try:
        for i in range(N):
            trade_allowed = i % 2 == 0
            blocker = LAYER_ORDER[i % len(LAYER_ORDER)] if not trade_allowed else None
            obs = _make_obs(trade_allowed=trade_allowed, blocker=blocker)
            graph = GraphBuilder.build(obs)
            timeline = TimelineBuilder.build(obs, graph)
            pid = obs.packet_id[:8]

            if not timeline.steps:
                errors.append(f"{pid}: timeline.steps est vide")
                continue

            layers_seen = [s.layer for s in timeline.steps]

            # Pas de couches dupliquees
            if len(set(layers_seen)) != len(layers_seen):
                errors.append(f"{pid}: couches dupliquees: {layers_seen}")

            # exit >= enter pour chaque step
            for step in timeline.steps:
                if step.exit_timestamp_us < step.enter_timestamp_us:
                    errors.append(f"{pid}: step {step.layer}: exit < enter")

            # Timestamps monotones entre steps
            for j in range(1, len(timeline.steps)):
                prev = timeline.steps[j - 1]
                curr = timeline.steps[j]
                if curr.enter_timestamp_us < prev.exit_timestamp_us:
                    errors.append(f"{pid}: step[{j}].enter < step[{j-1}].exit")

            # Couches dans l'ordre LAYER_ORDER (pas d'inversion)
            for j in range(1, len(layers_seen)):
                p, c = layers_seen[j - 1], layers_seen[j]
                if p in LAYER_ORDER and c in LAYER_ORDER:
                    if LAYER_ORDER.index(c) < LAYER_ORDER.index(p):
                        errors.append(f"{pid}: inversion {c} avant {p}")

            # Steps count matches nodes count
            if len(timeline.steps) != len(graph.nodes):
                errors.append(
                    f"{pid}: {len(timeline.steps)} steps != {len(graph.nodes)} nodes"
                )

        passed = len(errors) == 0
        return CheckResult(
            check_id="IV-005",
            name="Timeline Coherence",
            passed=passed,
            duration_ms=(time.time() - start) * 1000,
            details=(
                f"{N} timelines coherentes"
                if not errors
                else f"{len(errors)} erreurs sur {N}"
            ),
            metrics={"tested": N, "errors": len(errors)},
            error="\n".join(errors[:5]) if errors else None,
        )
    except Exception:
        return CheckResult(
            check_id="IV-005",
            name="Timeline Coherence",
            passed=False,
            duration_ms=(time.time() - start) * 1000,
            details="Exception",
            error=traceback.format_exc(),
        )


# ===============================================================================
# IV-006 -- Replay Fidelity
# ===============================================================================


def check_iv006(verbose: bool = False) -> CheckResult:
    """Le Replay reconstruit-il exactement la decision (determinisme)?"""
    start = time.time()
    N = 20
    errors: list[str] = []
    from dip.core.types import ReplayStatus

    try:
        for i in range(N):
            trade_allowed = i % 2 == 0
            blocker = LAYER_ORDER[i % len(LAYER_ORDER)] if not trade_allowed else None
            obs = _make_obs(trade_allowed=trade_allowed, blocker=blocker)
            graph = GraphBuilder.build(obs)
            timeline = TimelineBuilder.build(obs, graph)
            row = {"symbol": obs.symbol, "direction": obs.side, "regime": obs.regime}
            pid = obs.packet_id[:8]

            s1 = ReplayBuilder.build(graph, timeline, obs.packet_id, row)
            s2 = ReplayBuilder.build(graph, timeline, obs.packet_id, row)

            # Meme nombre de steps
            if s1.total_steps != s2.total_steps:
                errors.append(f"{pid}: steps {s1.total_steps} != {s2.total_steps}")
                continue

            # Chaque step identique
            for j, (a, b) in enumerate(zip(s1.steps, s2.steps)):
                if a.layer != b.layer:
                    errors.append(f"{pid}[{j}]: layer {a.layer} != {b.layer}")
                if a.status != b.status:
                    errors.append(f"{pid}[{j}]: status mismatch ({a.layer})")
                if abs(a.confidence_after - b.confidence_after) > 1e-9:
                    errors.append(f"{pid}[{j}]: confidence_after mismatch ({a.layer})")
                if a.is_blocker != b.is_blocker:
                    errors.append(f"{pid}[{j}]: is_blocker mismatch ({a.layer})")

            # final_status coherent avec trade_allowed
            expected = "APPROVED" if trade_allowed else "REJECTED"
            if s1.final_status != expected:
                errors.append(
                    f"{pid}: final_status={s1.final_status}, attendu={expected}"
                )

            # replay_status = COMPLETED
            if s1.replay_status != ReplayStatus.COMPLETED:
                errors.append(f"{pid}: replay_status={s1.replay_status.value}")

        passed = len(errors) == 0
        return CheckResult(
            check_id="IV-006",
            name="Replay Fidelity",
            passed=passed,
            duration_ms=(time.time() - start) * 1000,
            details=(
                f"{N} replays deterministes et fideles"
                if not errors
                else f"{len(errors)} erreurs sur {N}"
            ),
            metrics={"tested": N, "errors": len(errors)},
            error="\n".join(errors[:5]) if errors else None,
        )
    except Exception:
        return CheckResult(
            check_id="IV-006",
            name="Replay Fidelity",
            passed=False,
            duration_ms=(time.time() - start) * 1000,
            details="Exception",
            error=traceback.format_exc(),
        )


# ===============================================================================
# IV-007 -- Counterfactual Reproducibility
# ===============================================================================


def check_iv007(verbose: bool = False) -> CheckResult:
    """Le Counterfactual produit-il le meme resultat pour les memes entrees?"""
    start = time.time()
    errors: list[str] = []
    scenarios_run = 0
    try:
        # Layer removal: pour chaque couche bloquante
        for layer in LAYER_ORDER:
            obs = _make_obs(trade_allowed=False, blocker=layer)
            graph = GraphBuilder.build(obs)
            # Simuler sans chaque couche deux fois
            for target in LAYER_ORDER[:4]:
                s1, c1 = PipelineSimulator.simulate_without_layer(graph, target)
                s2, c2 = PipelineSimulator.simulate_without_layer(graph, target)
                scenarios_run += 1
                if s1 != s2:
                    errors.append(
                        f"blocker={layer},target={target}: status {s1} != {s2}"
                    )
                if abs(c1 - c2) > 1e-9:
                    errors.append(f"blocker={layer},target={target}: conf {c1} != {c2}")

        # Threshold simulation: sur des observations approuvees
        for layer in LAYER_ORDER:
            obs = _make_obs(trade_allowed=True)
            graph = GraphBuilder.build(obs)
            for mult in (0.7, 1.3):
                s1, c1 = PipelineSimulator.simulate_with_threshold(graph, layer, mult)
                s2, c2 = PipelineSimulator.simulate_with_threshold(graph, layer, mult)
                scenarios_run += 1
                if s1 != s2:
                    errors.append(f"threshold layer={layer} x{mult}: status mismatch")
                if abs(c1 - c2) > 1e-9:
                    errors.append(f"threshold layer={layer} x{mult}: conf mismatch")

        passed = len(errors) == 0
        return CheckResult(
            check_id="IV-007",
            name="Counterfactual Reproducibility",
            passed=passed,
            duration_ms=(time.time() - start) * 1000,
            details=(
                f"{scenarios_run} simulations reproductibles"
                if not errors
                else f"{len(errors)} erreurs sur {scenarios_run} scenarios"
            ),
            metrics={"scenarios": scenarios_run, "errors": len(errors)},
            error="\n".join(errors[:5]) if errors else None,
        )
    except Exception:
        return CheckResult(
            check_id="IV-007",
            name="Counterfactual Reproducibility",
            passed=False,
            duration_ms=(time.time() - start) * 1000,
            details="Exception",
            error=traceback.format_exc(),
        )


# ===============================================================================
# IV-008 -- Heatmap Layer Coverage
# ===============================================================================


def check_iv008(verbose: bool = False) -> CheckResult:
    """Le Heatmap couvre-t-il les 12 couches canoniques sur les deux axes?"""
    start = time.time()
    errors: list[str] = []
    try:
        # Construire des rows couvrant toutes les couches
        rows = []
        for layer_key in LAYER_ORDER:
            display = LAYER_DISPLAY.get(layer_key, layer_key)
            sym = f"SYM_{layer_key[:3].upper()}"
            for _ in range(12):  # > _MIN_CELL_COUNT=10
                rows.append(
                    {
                        "symbol": sym,
                        "root_cause_layer": display,
                        "status": "REJECTED",
                        "regime": "SIDEWAYS",
                    }
                )
        # APPROVED sans root_cause_layer
        for k in range(24):
            rows.append(
                {
                    "symbol": "BTCUSDT",
                    "root_cause_layer": None,
                    "status": "APPROVED",
                    "regime": "TRENDING_UP",
                }
            )

        tr = TimeRange.last_hours(24)

        # Symbol x Layer
        hm_sym = HeatmapBuilder.build_symbol_layer(rows, tr)
        expected = set(_LAYER_DISPLAY_NAMES)
        actual_x = set(hm_sym.axes.x_values)
        missing = expected - actual_x
        if missing:
            errors.append(f"SymbolxLayer: couches manquantes: {missing}")
        if len(hm_sym.axes.x_values) != 12:
            errors.append(
                f"SymbolxLayer: {len(hm_sym.axes.x_values)} couches (attendu 12)"
            )
        if hm_sym.total_decisions != len(rows):
            errors.append(
                f"SymbolxLayer: total_decisions={hm_sym.total_decisions} != {len(rows)}"
            )
        if len(hm_sym.cells) == 0:
            errors.append("SymbolxLayer: cells vide")

        # Regime x Layer
        hm_reg = HeatmapBuilder.build_regime_layer(rows, tr)
        actual_rx = set(hm_reg.axes.x_values)
        missing_r = expected - actual_rx
        if missing_r:
            errors.append(f"RegimexLayer: couches manquantes: {missing_r}")
        if len(hm_reg.axes.x_values) != 12:
            errors.append(
                f"RegimexLayer: {len(hm_reg.axes.x_values)} couches (attendu 12)"
            )

        passed = len(errors) == 0
        return CheckResult(
            check_id="IV-008",
            name="Heatmap Layer Coverage",
            passed=passed,
            duration_ms=(time.time() - start) * 1000,
            details=(
                f"12/12 couches, {len(hm_sym.cells)} cellules (symbol), "
                f"{len(hm_reg.cells)} (regime)"
                if not errors
                else f"{len(errors)} erreurs"
            ),
            metrics={
                "x_layers": len(hm_sym.axes.x_values),
                "cells_symbol": len(hm_sym.cells),
                "cells_regime": len(hm_reg.cells),
                "errors": len(errors),
            },
            error="\n".join(errors) if errors else None,
        )
    except Exception:
        return CheckResult(
            check_id="IV-008",
            name="Heatmap Layer Coverage",
            passed=False,
            duration_ms=(time.time() - start) * 1000,
            details="Exception",
            error=traceback.format_exc(),
        )


# ===============================================================================
# IV-009 -- Causal Acyclicity
# ===============================================================================


def check_iv009(verbose: bool = False) -> CheckResult:
    """La CauseTree est-elle acyclique et sans couche dupliquee?"""
    start = time.time()
    N = 24
    errors: list[str] = []
    try:
        for i in range(N):
            trade_allowed = i % 3 != 0
            blocker = LAYER_ORDER[i % len(LAYER_ORDER)] if not trade_allowed else None
            obs = _make_obs(trade_allowed=trade_allowed, blocker=blocker)
            graph = GraphBuilder.build(obs)
            tree = CausalTreeBuilder.build(obs, graph)
            pid = obs.packet_id[:8]

            # Pas de node_id dupliques dans causal_nodes
            cn_ids = [n.node_id for n in tree.causal_nodes]
            if len(set(cn_ids)) != len(cn_ids):
                errors.append(f"{pid}: causal_nodes.node_id dupliques")

            # Chaque causal_path: pas de couches dupliquees (= pas de cycle)
            for path in tree.causal_paths:
                layers = list(path.nodes)
                if len(set(layers)) != len(layers):
                    errors.append(f"{pid} path '{path.path_id}': couches dupliquees")

            # Causal chain respecte LAYER_ORDER (pas de reference retrograde)
            for path in tree.causal_paths:
                prev_idx = -1
                for lname in path.nodes:
                    if lname in LAYER_ORDER:
                        curr_idx = LAYER_ORDER.index(lname)
                        if curr_idx < prev_idx:
                            errors.append(
                                f"{pid}: inversion causale {lname}(idx={curr_idx}) "
                                f"apres idx={prev_idx}"
                            )
                        prev_idx = curr_idx

            # root_cause.causing_layer present dans causal_nodes
            rc_layer = tree.root_cause.causing_layer
            cn_layers = {n.layer for n in tree.causal_nodes}
            if rc_layer not in cn_layers:
                errors.append(
                    f"{pid}: root_cause.causing_layer='{rc_layer}' "
                    "absent de causal_nodes"
                )

            # overall_confidence in [0,1]
            if not (0.0 <= tree.overall_confidence <= 1.0):
                errors.append(
                    f"{pid}: overall_confidence={tree.overall_confidence:.3f} "
                    "hors [0,1]"
                )

        passed = len(errors) == 0
        return CheckResult(
            check_id="IV-009",
            name="Causal Acyclicity",
            passed=passed,
            duration_ms=(time.time() - start) * 1000,
            details=(
                f"{N} CausalTrees acycliques et valides"
                if not errors
                else f"{len(errors)} erreurs sur {N}"
            ),
            metrics={"tested": N, "errors": len(errors)},
            error="\n".join(errors[:5]) if errors else None,
        )
    except Exception:
        return CheckResult(
            check_id="IV-009",
            name="Causal Acyclicity",
            passed=False,
            duration_ms=(time.time() - start) * 1000,
            details="Exception",
            error=traceback.format_exc(),
        )


# ===============================================================================
# IV-010 -- Timestamp Monotonicity
# ===============================================================================


def check_iv010(verbose: bool = False) -> CheckResult:
    """Les timestamps sont-ils monotones (causalite temporelle preservee)?"""
    start = time.time()
    N = 20
    errors: list[str] = []
    try:
        store, _ = _fresh_store()
        engine = DecisionGraphEngine()

        base_ts = time.time()
        packet_ids: list[str] = []
        for i in range(N):
            obs = _make_obs(ts=base_ts + i * 0.05)  # 50ms apart
            engine.on_observation(obs)
            packet_ids.append(obs.packet_id)

        rows = store.get_decisions(limit=N + 10)

        # Count
        if len(rows) < N:
            errors.append(f"Seulement {len(rows)}/{N} decisions retrouvees")

        # Monotonie (rows retournees DESC -> inverser)
        rows_asc = list(reversed(rows))
        for i in range(1, len(rows_asc)):
            if rows_asc[i]["created_at_us"] < rows_asc[i - 1]["created_at_us"]:
                errors.append(
                    f"Non-monotone: row[{i}].ts={rows_asc[i]['created_at_us']} "
                    f"< row[{i-1}].ts={rows_asc[i-1]['created_at_us']}"
                )
                break

        # Dans chaque graphe: timestamps des noeuds monotones
        for pid in packet_ids[:5]:
            row = store.get_decision(pid)
            if row and row.get("graph_json"):
                import json as _json

                g = _json.loads(row["graph_json"])
                ts_list = [n["timestamp_us"] for n in g["nodes"]]
                for k in range(1, len(ts_list)):
                    if ts_list[k] < ts_list[k - 1]:
                        errors.append(
                            f"Graph {pid[:8]}: node[{k}].ts={ts_list[k]} < "
                            f"node[{k-1}].ts={ts_list[k-1]}"
                        )
                        break

        # Pas de timestamps created_at_us identiques entre deux packets differents
        all_ts = [r["created_at_us"] for r in rows]
        if len(set(all_ts)) != len(all_ts):
            errors.append("Timestamps created_at_us dupliques entre decisions")

        passed = len(errors) == 0
        return CheckResult(
            check_id="IV-010",
            name="Timestamp Monotonicity",
            passed=passed,
            duration_ms=(time.time() - start) * 1000,
            details=(
                f"{N} decisions, timestamps monotones"
                if not errors
                else f"{len(errors)} erreurs sur {N}"
            ),
            metrics={"tested": N, "found": len(rows), "errors": len(errors)},
            error="\n".join(errors[:5]) if errors else None,
        )
    except Exception:
        return CheckResult(
            check_id="IV-010",
            name="Timestamp Monotonicity",
            passed=False,
            duration_ms=(time.time() - start) * 1000,
            details="Exception",
            error=traceback.format_exc(),
        )


# -- Registry -------------------------------------------------------------------

ALL_CHECKS: list[tuple[str, str, Any]] = [
    ("IV-001", "Packet Coverage", check_iv001),
    ("IV-002", "Rejection Events", check_iv002),
    ("IV-003", "Regret Parent Uniqueness", check_iv003),
    ("IV-004", "Graph Completeness", check_iv004),
    ("IV-005", "Timeline Coherence", check_iv005),
    ("IV-006", "Replay Fidelity", check_iv006),
    ("IV-007", "Counterfactual Reproducibility", check_iv007),
    ("IV-008", "Heatmap Layer Coverage", check_iv008),
    ("IV-009", "Causal Acyclicity", check_iv009),
    ("IV-010", "Timestamp Monotonicity", check_iv010),
]


# -- Runner --------------------------------------------------------------------


def run_suite(
    check_filter: Optional[str] = None,
    verbose: bool = False,
) -> list[CheckResult]:
    results = []
    for check_id, _name, fn in ALL_CHECKS:
        if check_filter and check_filter.upper() != check_id:
            continue
        result = fn(verbose=verbose)
        results.append(result)
    return results


# -- Certification -------------------------------------------------------------


def _certify(results: list[CheckResult]) -> dict[str, Any]:
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    failed = total - passed

    if failed == 0:
        status = "CERTIFIED_OBSERVER"
        decision = "S1 autorise -- observateur certifie"
    elif failed <= 2:
        status = "CONDITIONAL"
        decision = f"S1 conditionnel -- corriger {failed} check(s) en FAIL"
    else:
        status = "NOT_CERTIFIED"
        decision = f"S1 interdit -- {failed}/{total} checks en FAIL"

    return {
        "status": status,
        "decision": decision,
        "passed": passed,
        "total": total,
        "failed": failed,
        "score_pct": round(passed / total * 100, 1) if total else 0,
    }


# -- Report --------------------------------------------------------------------


def generate_report(
    results: list[CheckResult],
    verbose: bool = False,
    as_json: bool = False,
) -> str:
    cert = _certify(results)

    if as_json:
        return json.dumps(
            {
                "suite": "INV-IV",
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "results": [
                    {
                        "check_id": r.check_id,
                        "name": r.name,
                        "status": r.status,
                        "passed": r.passed,
                        "duration_ms": round(r.duration_ms, 2),
                        "details": r.details,
                        "metrics": r.metrics,
                        "error": r.error,
                    }
                    for r in results
                ],
                "certification": cert,
            },
            indent=2,
        )

    W = 68
    SEP = "=" * W
    lines: list[str] = [""]
    lines.append(SEP)
    lines.append("  INV-IV -- DIP Instrumentation Validation Suite")
    lines.append("  L2.5 Certified Observer Protocol")
    lines.append(SEP)
    lines.append("")

    for r in results:
        icon = "[PASS]" if r.passed else "[FAIL]"
        dur = f"{r.duration_ms:.0f}ms"
        lines.append(f"  {icon}  {r.check_id}  {r.name:<38}  [{dur:>6}]")
        lines.append(f"         {r.details}")
        if verbose and r.error:
            for line in r.error.strip().split("\n")[:6]:
                lines.append(f"         >> {line}")
        lines.append("")

    total_ms = sum(r.duration_ms for r in results)
    lines.append("-" * W)
    lines.append(
        f"  Score:    {cert['passed']}/{cert['total']} checks PASS  "
        f"({cert['score_pct']}%)  [{total_ms:.0f}ms total]"
    )
    lines.append(f"  Statut:   {cert['status']}")
    lines.append(f"  Decision: {cert['decision']}")
    lines.append("")

    if cert["status"] == "CERTIFIED_OBSERVER":
        lines.append("  [OK] DIP certifie CERTIFIED OBSERVER")
        lines.append("       Le pipeline d'observation est fiable.")
        lines.append("       Toutes les donnees collectees peuvent alimenter H1-H6.")
    elif cert["status"] == "CONDITIONAL":
        failed_ids = [r.check_id for r in results if not r.passed]
        lines.append(
            f"  [!!] DIP CONDITIONNEL -- checks a corriger: {', '.join(failed_ids)}"
        )
        lines.append("       Investiguer les erreurs avant de lancer S1.")
    else:
        failed_ids = [r.check_id for r in results if not r.passed]
        lines.append(f"  [KO] DIP NON CERTIFIE -- {cert['failed']} checks en FAIL")
        lines.append(f"       Checks: {', '.join(failed_ids)}")
        lines.append(
            "       Instrumentation defectueuse -> donnees non fiables -> S1 interdit."
        )

    lines.append("")
    return "\n".join(lines)


# -- CLI -----------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="INV-IV: DIP Instrumentation Validation Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Checks:
  IV-001  Packet Coverage            -- chaque observation -> DIPStore
  IV-002  Rejection Events           -- chaque rejet -> BLOCKED node + first_blocker
  IV-003  Regret Parent Uniqueness   -- chaque rejet -> exactement 1 RootCause
  IV-004  Graph Completeness         -- nodes, edges, critical_path valides
  IV-005  Timeline Coherence         -- timestamps monotones, pas de doublons
  IV-006  Replay Fidelity            -- replay deterministe et fidele au verdict
  IV-007  Counterfactual Repro.      -- meme entree -> meme sortie contrefactuelle
  IV-008  Heatmap Layer Coverage     -- 12/12 couches dans la matrice
  IV-009  Causal Acyclicity          -- CauseTree sans cycle ni doublon
  IV-010  Timestamp Monotonicity     -- ordre causal preserve dans le store

Certification:
  10/10  CERTIFIED_OBSERVER  -> S1 autorise
  8-9/10 CONDITIONAL         -> corriger avant S1
  <8/10  NOT_CERTIFIED       -> S1 interdit
        """,
    )
    parser.add_argument("--check", metavar="ID", help="Un seul check (ex: IV-006)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Details d'erreur")
    parser.add_argument("--json", action="store_true", help="Sortie JSON pour CI")
    args = parser.parse_args()

    results = run_suite(check_filter=args.check, verbose=args.verbose)
    print(generate_report(results, verbose=args.verbose, as_json=args.json))

    sys.exit(0 if all(r.passed for r in results) else 1)


if __name__ == "__main__":
    main()
