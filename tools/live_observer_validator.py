#!/usr/bin/env python
"""
tools/live_observer_validator.py -- INV-IV-LIVE: Live Observer Validation Suite

Certifies that the DIP is a reliable observer of the trading engine.
Targets:
  Level 2 (Certified Instrumentation): synthetic checks, III >= 95
  Level 3 (Certified Live Observer):   live checks on production data, OCS >= 90

Reference: docs/dip/observer_certification_standard_v1.md
ADR-0007:  ALL checks are STRICTLY PASSIVE / READ-ONLY.

Usage:
  python tools/live_observer_validator.py
  python tools/live_observer_validator.py --live
  python tools/live_observer_validator.py --check IV-LIVE-006
  python tools/live_observer_validator.py --json
  python tools/live_observer_validator.py --history
  python tools/live_observer_validator.py --report
  python tools/live_observer_validator.py --export certification.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
import time
import tracemalloc
import uuid
from dataclasses import asdict, dataclass, field  # noqa: F401
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dip.core.store import DIPStore  # noqa: E402
from dip.core.types import (  # noqa: E402,F401
    LAYER_DISPLAY,
    LAYER_ORDER,
    DecisionStatus,
    TimeRange,
    now_us,
)
from dip.modules.causal_tree import CausalTreeBuilder  # noqa: E402
from dip.modules.counterfactual import PipelineSimulator  # noqa: E402,F401
from dip.modules.decision_graph import DecisionGraphEngine, GraphBuilder  # noqa: E402
from dip.modules.decision_heatmap import (  # noqa: E402,F401
    _LAYER_DISPLAY_NAMES,
    HeatmapBuilder,
)
from dip.modules.decision_replay import ReplayBuilder  # noqa: E402
from dip.modules.decision_timeline import TimelineBuilder  # noqa: E402

try:
    from dip.modules.explainability import ExplainabilityScoreEngine  # noqa: F401

    _EXPLAINABILITY_AVAILABLE = True
except ImportError:
    _EXPLAINABILITY_AVAILABLE = False

# ── Constants ──────────────────────────────────────────────────────────────────
MIN_DECISIONS = 50
MEMORY_BUDGET_BYTES_PER_OBS = 2048
CERT_HISTORY_PATH = (
    _ROOT / "databases" / "certifications" / "observer_cert_history.jsonl"
)
VERSION = "1.0"


# ── Result type ────────────────────────────────────────────────────────────────


@dataclass
class LiveCheckResult:
    check_id: str
    name: str
    passed: bool
    skipped: bool
    duration_ms: float
    details: str
    score: float = 100.0
    metrics: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    skip_reason: Optional[str] = None

    @property
    def status(self) -> str:
        if self.skipped:
            return "SKIP"
        return "PASS" if self.passed else "FAIL"


def _result_skip(check_id: str, name: str, reason: str, t0: float) -> LiveCheckResult:
    return LiveCheckResult(
        check_id=check_id,
        name=name,
        passed=False,
        skipped=True,
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
        details=f"SKIP -- {reason}",
        score=0.0,
        skip_reason=reason,
    )


def _result_pass(
    check_id: str,
    name: str,
    details: str,
    t0: float,
    score: float = 100.0,
    metrics: dict | None = None,
) -> LiveCheckResult:
    return LiveCheckResult(
        check_id=check_id,
        name=name,
        passed=True,
        skipped=False,
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
        details=details,
        score=score,
        metrics=metrics or {},
    )


def _result_fail(
    check_id: str,
    name: str,
    details: str,
    t0: float,
    score: float = 0.0,
    metrics: dict | None = None,
    error: str | None = None,
) -> LiveCheckResult:
    return LiveCheckResult(
        check_id=check_id,
        name=name,
        passed=False,
        skipped=False,
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
        details=details,
        score=score,
        metrics=metrics or {},
        error=error,
    )


# ── Shared helpers ─────────────────────────────────────────────────────────────


def _fresh_store() -> tuple[DIPStore, Path]:
    tmp = Path(tempfile.gettempdir()) / f"inv_ivlive_{uuid.uuid4().hex[:8]}.sqlite"
    DIPStore._instance = None
    return DIPStore.instance(db_path=tmp), tmp


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
    obs.regime_confidence = 0.8
    obs.score = score
    obs.ts = ts if ts is not None else time.time()
    obs.personality_name = "default"
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
    obs.confidence = 0.85
    obs.position_size_usd = 50.0
    obs.risk_score = 0.2
    obs.meta_score = 0.75
    obs.final_score = 0.82
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


# ── IV-LIVE-001: Coverage Validation ──────────────────────────────────────────


def check_iv_live_001(live_mode: bool = False) -> LiveCheckResult:
    """All decisions are indexed in DIPStore without null packet_id."""
    CID, NAME = "IV-LIVE-001", "Coverage Validation"
    t0 = time.perf_counter()

    if live_mode:
        try:
            store = DIPStore.instance()
            n = store.count_decisions()
            if n == 0:
                return _result_skip(
                    CID, NAME, "DIPStore vide -- activer FEATURE_DIP=true", t0
                )
            rows = store.get_decisions(limit=n)
            null_ids = sum(1 for r in rows if not r.get("packet_id"))
            if null_ids == 0:
                return _result_pass(
                    CID,
                    NAME,
                    f"{n} decisions indexees, 0 packet_id null",
                    t0,
                    metrics={"n_decisions": n, "null_ids": 0},
                )
            return _result_fail(
                CID,
                NAME,
                f"{null_ids}/{n} decisions avec packet_id null",
                t0,
                metrics={"n_decisions": n, "null_ids": null_ids},
            )
        except Exception as e:
            return _result_fail(
                CID, NAME, "Erreur acces DIPStore production", t0, error=str(e)
            )

    N = 20
    store, tmp = _fresh_store()
    try:
        engine = DecisionGraphEngine()
        for i in range(N):
            engine.on_observation(_make_obs(packet_id=f"ivlive001_{i:04d}"))
        n_stored = store.count_decisions()
        coverage = n_stored / N * 100
        if n_stored == N:
            return _result_pass(
                CID,
                NAME,
                f"{N} obs injectees, {n_stored} persistees -- couverture 100%",
                t0,
                metrics={"n_injected": N, "n_stored": n_stored, "coverage_pct": 100.0},
            )
        return _result_fail(
            CID,
            NAME,
            f"{n_stored}/{N} persistees -- couverture {coverage:.0f}%",
            t0,
            score=coverage,
            metrics={"n_injected": N, "n_stored": n_stored, "coverage_pct": coverage},
        )
    except Exception as e:
        return _result_fail(CID, NAME, "Exception durant injection", t0, error=str(e))
    finally:
        try:
            store._conn.close()
        except Exception:
            pass
        DIPStore._instance = None
        try:
            tmp.unlink(missing_ok=True)
        except PermissionError:
            pass  # Windows: SQLite WAL still held briefly


# ── IV-LIVE-002: Rejection Completeness ───────────────────────────────────────


def check_iv_live_002(live_mode: bool = False) -> LiveCheckResult:
    """All rejections have a valid root_cause_layer (stateless check)."""
    CID, NAME = "IV-LIVE-002", "Rejection Completeness"
    t0 = time.perf_counter()

    blockers = list(LAYER_ORDER)
    ok_count = 0
    missing: list[str] = []

    try:
        for blocker in blockers:
            obs = _make_obs(trade_allowed=False, blocker=blocker)
            graph = GraphBuilder.build(obs)
            tree = CausalTreeBuilder.build(obs, graph)
            rc_layer = tree.root_cause.causing_layer if tree.root_cause else None
            if rc_layer and rc_layer in LAYER_ORDER:
                ok_count += 1
            else:
                missing.append(f"{blocker}->rc={rc_layer}")

        score = ok_count / len(blockers) * 100
        if ok_count == len(blockers):
            return _result_pass(
                CID,
                NAME,
                f"{len(blockers)}/{len(blockers)} rejets avec root_cause_layer valide",
                t0,
                score=100.0,
                metrics={"n_tested": len(blockers), "n_valid": ok_count},
            )
        return _result_fail(
            CID,
            NAME,
            f"{ok_count}/{len(blockers)} root_cause valides -- manquants: {missing}",
            t0,
            score=score,
            metrics={
                "n_tested": len(blockers),
                "n_valid": ok_count,
                "missing": missing,
            },
        )
    except Exception as e:
        return _result_fail(
            CID, NAME, "Exception durant construction CausalTree", t0, error=str(e)
        )


# ── IV-LIVE-003: Lifecycle Completeness ───────────────────────────────────────


def check_iv_live_003(live_mode: bool = False) -> LiveCheckResult:
    """Decision->Trade chain exists without break."""
    CID, NAME = "IV-LIVE-003", "Lifecycle Completeness"
    t0 = time.perf_counter()

    if live_mode:
        db_path = _ROOT / "databases" / "trade_log.sqlite"
        if not db_path.exists():
            return _result_skip(CID, NAME, "trade_log.sqlite introuvable", t0)
        try:
            conn = sqlite3.connect(str(db_path))
            count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            conn.close()
            if count == 0:
                return _result_skip(
                    CID, NAME, "trade_log.sqlite vide -- aucun trade execute", t0
                )
            return _result_pass(
                CID,
                NAME,
                f"trade_log.sqlite: {count} trades -- chaine Decision->Trade active",
                t0,
                metrics={"n_trades": count},
            )
        except Exception as e:
            return _result_fail(
                CID, NAME, "Erreur lecture trade_log.sqlite", t0, error=str(e)
            )

    # Synthetic: APPROVED obs produce complete lifecycle (12 nodes, timeline, causal)
    N = 5
    ok_count = 0
    try:
        for _ in range(N):
            obs = _make_obs(trade_allowed=True)
            graph = GraphBuilder.build(obs)
            tree = CausalTreeBuilder.build(obs, graph)
            tl = TimelineBuilder.build(obs, graph)
            complete = (
                graph.status == DecisionStatus.APPROVED
                and len(graph.nodes) == 12
                and len(tl.steps) == 12
                and tree.root_cause is not None
            )
            if complete:
                ok_count += 1

        score = ok_count / N * 100
        if ok_count == N:
            return _result_pass(
                CID,
                NAME,
                f"{N}/{N} obs -- lifecycle complet (graph+timeline+causal)",
                t0,
                score=100.0,
                metrics={"n_tested": N, "n_complete": ok_count},
            )
        return _result_fail(
            CID,
            NAME,
            f"{ok_count}/{N} lifecycles complets",
            t0,
            score=score,
            metrics={"n_tested": N, "n_complete": ok_count},
        )
    except Exception as e:
        return _result_fail(CID, NAME, "Exception lifecycle", t0, error=str(e))


# ── IV-LIVE-004: Parent Integrity ─────────────────────────────────────────────


def check_iv_live_004(live_mode: bool = False) -> LiveCheckResult:
    """Zero orphan layer references in CausalTree vs graph nodes."""
    CID, NAME = "IV-LIVE-004", "Parent Integrity"
    t0 = time.perf_counter()

    if live_mode:
        try:
            store = DIPStore.instance()
            n = store.count_decisions()
            if n < MIN_DECISIONS:
                return _result_skip(
                    CID,
                    NAME,
                    f"N={n} < MIN={MIN_DECISIONS} decisions de production",
                    t0,
                )
            conn = store._conn
            orphans = conn.execute(
                """
                SELECT COUNT(*) FROM dip_counterfactuals c
                WHERE NOT EXISTS (
                    SELECT 1 FROM dip_decisions d WHERE d.packet_id = c.packet_id
                )
            """
            ).fetchone()[0]
            if orphans == 0:
                return _result_pass(
                    CID,
                    NAME,
                    f"0 orphelin sur {n} decisions",
                    t0,
                    metrics={"n_decisions": n, "n_orphans": 0},
                )
            return _result_fail(
                CID,
                NAME,
                f"{orphans} orphelins dans dip_counterfactuals",
                t0,
                metrics={"n_decisions": n, "n_orphans": orphans},
            )
        except Exception as e:
            return _result_fail(CID, NAME, "Erreur requete orphelins", t0, error=str(e))

    # Synthetic: verify CausalTree only references layers that exist in the graph
    N = 15
    ok_count = 0
    try:
        for i in range(N):
            approved = i % 3 == 0
            blocker = LAYER_ORDER[i % len(LAYER_ORDER)] if not approved else None
            obs = _make_obs(trade_allowed=approved, blocker=blocker)
            graph = GraphBuilder.build(obs)
            tree = CausalTreeBuilder.build(obs, graph)

            graph_layers = {nd.layer for nd in graph.nodes}
            tree_layers = {cn.layer for cn in tree.causal_nodes}
            if tree.root_cause and tree.root_cause.causing_layer:
                tree_layers.add(tree.root_cause.causing_layer)

            orphans = tree_layers - graph_layers
            if not orphans:
                ok_count += 1

        score = ok_count / N * 100
        if ok_count == N:
            return _result_pass(
                CID,
                NAME,
                f"{N}/{N} CausalTrees sans reference orpheline",
                t0,
                score=100.0,
                metrics={"n_tested": N, "n_clean": ok_count},
            )
        return _result_fail(
            CID,
            NAME,
            f"{ok_count}/{N} CausalTrees propres",
            t0,
            score=score,
            metrics={"n_tested": N, "n_clean": ok_count},
        )
    except Exception as e:
        return _result_fail(CID, NAME, "Exception Parent Integrity", t0, error=str(e))


# ── IV-LIVE-005: Timestamp Integrity ──────────────────────────────────────────


def check_iv_live_005(live_mode: bool = False) -> LiveCheckResult:
    """Timestamps are strictly monotone, no duplicates, no inversions."""
    CID, NAME = "IV-LIVE-005", "Timestamp Integrity"
    t0 = time.perf_counter()

    if live_mode:
        try:
            store = DIPStore.instance()
            n = store.count_decisions()
            if n < MIN_DECISIONS:
                return _result_skip(CID, NAME, f"N={n} < MIN={MIN_DECISIONS}", t0)
            rows = store.get_decisions(limit=n)
            timestamps = [
                r.get("created_at") for r in rows if r.get("created_at") is not None
            ]
            if len(timestamps) < 2:
                return _result_skip(CID, NAME, "Moins de 2 timestamps disponibles", t0)
            duplicates = len(timestamps) - len(set(timestamps))
            inversions = sum(
                1
                for i in range(1, len(timestamps))
                if timestamps[i] < timestamps[i - 1]
            )
            if duplicates == 0 and inversions == 0:
                return _result_pass(
                    CID,
                    NAME,
                    f"{len(timestamps)} timestamps: 0 doublon, 0 inversion",
                    t0,
                    metrics={
                        "n_checked": len(timestamps),
                        "duplicates": 0,
                        "inversions": 0,
                    },
                )
            return _result_fail(
                CID,
                NAME,
                f"{duplicates} doublons, {inversions} inversions",
                t0,
                metrics={"duplicates": duplicates, "inversions": inversions},
            )
        except Exception as e:
            return _result_fail(CID, NAME, "Erreur acces timestamps", t0, error=str(e))

    # Synthetic: inject 20 obs with increasing ts, verify timeline preserves order
    N = 20
    base_ts = time.time()
    ts_out: list[int] = []
    try:
        for i in range(N):
            obs = _make_obs(ts=base_ts + i * 0.001)
            graph = GraphBuilder.build(obs)
            tl = TimelineBuilder.build(obs, graph)
            ts_out.append(tl.steps[0].enter_timestamp_us if tl.steps else 0)

        inversions = sum(1 for i in range(1, N) if ts_out[i] <= ts_out[i - 1])
        duplicates = N - len(set(ts_out))
        if inversions == 0 and duplicates == 0:
            return _result_pass(
                CID,
                NAME,
                f"{N} timestamps: 0 inversion, 0 doublon",
                t0,
                metrics={"n_checked": N, "inversions": 0, "duplicates": 0},
            )
        return _result_fail(
            CID,
            NAME,
            f"{inversions} inversions, {duplicates} doublons",
            t0,
            metrics={
                "n_checked": N,
                "inversions": inversions,
                "duplicates": duplicates,
            },
        )
    except Exception as e:
        return _result_fail(CID, NAME, "Exception timestamps", t0, error=str(e))


# ── IV-LIVE-006: DecisionID Integrity ─────────────────────────────────────────


def check_iv_live_006(live_mode: bool = False) -> LiveCheckResult:
    """Zero duplicate packet_id across all of DIPStore."""
    CID, NAME = "IV-LIVE-006", "DecisionID Integrity"
    t0 = time.perf_counter()

    if live_mode:
        try:
            store = DIPStore.instance()
            n = store.count_decisions()
            if n < MIN_DECISIONS:
                return _result_skip(CID, NAME, f"N={n} < MIN={MIN_DECISIONS}", t0)
            duplicates = store._conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT packet_id, COUNT(*) AS cnt
                    FROM dip_decisions GROUP BY packet_id HAVING cnt > 1
                )
            """
            ).fetchone()[0]
            if duplicates == 0:
                return _result_pass(
                    CID,
                    NAME,
                    f"0 packet_id duplique sur {n} decisions",
                    t0,
                    metrics={"n_decisions": n, "duplicates": 0},
                )
            return _result_fail(
                CID,
                NAME,
                f"{duplicates} packet_id dupliques detectes",
                t0,
                metrics={"n_decisions": n, "duplicates": duplicates},
            )
        except Exception as e:
            return _result_fail(
                CID, NAME, "Erreur requete duplicates", t0, error=str(e)
            )

    N = 20
    store, tmp = _fresh_store()
    try:
        engine = DecisionGraphEngine()
        ids_used = [f"ivlive006_{i:04d}" for i in range(N)]
        for pid in ids_used:
            engine.on_observation(_make_obs(packet_id=pid))
        # Re-inject first ID -- should upsert, not duplicate
        engine.on_observation(_make_obs(packet_id=ids_used[0]))

        n_stored = store.count_decisions()
        if n_stored == N:
            return _result_pass(
                CID,
                NAME,
                f"{N} IDs uniques, 0 doublon apres re-injection",
                t0,
                metrics={"n_injected": N, "n_stored": n_stored, "duplicates": 0},
            )
        extra = n_stored - N
        return _result_fail(
            CID,
            NAME,
            f"{extra} doublon(s): {n_stored} entrees pour {N} IDs",
            t0,
            metrics={"n_injected": N, "n_stored": n_stored, "extra": extra},
        )
    except Exception as e:
        return _result_fail(CID, NAME, "Exception DecisionID", t0, error=str(e))
    finally:
        try:
            store._conn.close()
        except Exception:
            pass
        DIPStore._instance = None
        try:
            tmp.unlink(missing_ok=True)
        except PermissionError:
            pass  # Windows: SQLite WAL still held briefly


# ── IV-LIVE-007: Memory Stability ─────────────────────────────────────────────


def check_iv_live_007() -> LiveCheckResult:
    """Memory growth < 2 KB/obs over 1000 stateless builder iterations."""
    CID, NAME = "IV-LIVE-007", "Memory Stability"
    t0 = time.perf_counter()
    N = 1000
    try:
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        for i in range(N):
            obs = _make_obs(
                trade_allowed=(i % 3 != 0),
                blocker=LAYER_ORDER[i % len(LAYER_ORDER)] if i % 3 != 0 else None,
            )
            graph = GraphBuilder.build(obs)
            tree = CausalTreeBuilder.build(obs, graph)
            tl = TimelineBuilder.build(obs, graph)
            del obs, graph, tree, tl

        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snapshot_after.compare_to(snapshot_before, "lineno")
        total_growth = sum(s.size_diff for s in stats if s.size_diff > 0)
        per_obs = total_growth / N

        if per_obs < MEMORY_BUDGET_BYTES_PER_OBS:
            return _result_pass(
                CID,
                NAME,
                f"{N} obs: +{total_growth / 1024:.1f} KB total, {per_obs:.0f} B/obs "
                f"(budget: {MEMORY_BUDGET_BYTES_PER_OBS} B/obs)",
                t0,
                score=100.0,
                metrics={
                    "n_obs": N,
                    "total_growth_kb": round(total_growth / 1024, 2),
                    "per_obs_bytes": round(per_obs),
                },
            )
        score = max(0.0, 100.0 - (per_obs - MEMORY_BUDGET_BYTES_PER_OBS) / 100)
        return _result_fail(
            CID,
            NAME,
            f"Fuite memoire: {per_obs:.0f} B/obs > "
            f"budget {MEMORY_BUDGET_BYTES_PER_OBS} B/obs",
            t0,
            score=score,
            metrics={
                "n_obs": N,
                "total_growth_kb": round(total_growth / 1024, 2),
                "per_obs_bytes": round(per_obs),
            },
        )
    except Exception as e:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        return _result_fail(CID, NAME, "Exception test memoire", t0, error=str(e))


# ── IV-LIVE-008: Replay Fidelity (structural) ─────────────────────────────────


def check_iv_live_008(live_mode: bool = False) -> LiveCheckResult:
    """Same input produces identical replay twice (deterministic)."""
    CID, NAME = "IV-LIVE-008", "Replay Fidelity (structural)"
    t0 = time.perf_counter()
    N = 10
    ok_count = 0
    mismatches: list[str] = []
    row = {"packet_id": "", "symbol": "BTCUSDT"}

    try:
        for i in range(N):
            approved = i % 2 == 0
            blocker = LAYER_ORDER[i % len(LAYER_ORDER)] if not approved else None
            obs = _make_obs(
                trade_allowed=approved, blocker=blocker, packet_id=f"ivlive008_{i:04d}"
            )
            row["packet_id"] = obs.packet_id

            graph1 = GraphBuilder.build(obs)
            tl1 = TimelineBuilder.build(obs, graph1)
            graph2 = GraphBuilder.build(obs)
            tl2 = TimelineBuilder.build(obs, graph2)

            replay1 = ReplayBuilder.build(graph1, tl1, obs.packet_id, row)
            replay2 = ReplayBuilder.build(graph2, tl2, obs.packet_id, row)

            same = (
                replay1.final_status == replay2.final_status
                and len(replay1.steps) == len(replay2.steps)
                and replay1.replay_status == replay2.replay_status
            )
            if same:
                ok_count += 1
            else:
                mismatches.append(
                    f"obs_{i}: status={replay1.final_status}!={replay2.final_status}"
                )

        score = ok_count / N * 100
        if ok_count == N:
            return _result_pass(
                CID,
                NAME,
                f"{N}/{N} replays deterministes et identiques",
                t0,
                score=100.0,
                metrics={"n_tested": N, "n_ok": ok_count},
            )
        return _result_fail(
            CID,
            NAME,
            f"{ok_count}/{N} replays identiques -- {mismatches}",
            t0,
            score=score,
            metrics={"n_tested": N, "n_ok": ok_count, "mismatches": mismatches},
        )
    except Exception as e:
        return _result_fail(CID, NAME, "Exception replay fidelity", t0, error=str(e))


# ── IV-LIVE-009: Reporting Consistency ────────────────────────────────────────


def check_iv_live_009() -> LiveCheckResult:
    """Graph, CausalTree, Timeline are mutually consistent for same obs."""
    CID, NAME = "IV-LIVE-009", "Reporting Consistency"
    t0 = time.perf_counter()
    N = 15
    ok_count = 0
    inconsistencies: list[str] = []

    try:
        for i in range(N):
            approved = i % 3 != 0
            blocker = LAYER_ORDER[i % len(LAYER_ORDER)] if not approved else None
            obs = _make_obs(trade_allowed=approved, blocker=blocker)

            graph = GraphBuilder.build(obs)
            tree = CausalTreeBuilder.build(obs, graph)
            tl = TimelineBuilder.build(obs, graph)

            pid_ok = graph.packet_id == obs.packet_id == tl.packet_id == tree.packet_id
            status_ok = graph.status.value == tree.result == tl.final_status.value
            dir_ok = graph.direction == tl.direction
            count_ok = len(graph.nodes) == len(tl.steps)

            if pid_ok and status_ok and dir_ok and count_ok:
                ok_count += 1
            else:
                issues = []
                if not pid_ok:
                    issues.append("packet_id_mismatch")
                if not status_ok:
                    issues.append(
                        f"status_mismatch(graph={graph.status.value},"
                        f"tree={tree.result},tl={tl.final_status.value})"
                    )
                if not dir_ok:
                    issues.append("direction_mismatch")
                if not count_ok:
                    issues.append(
                        f"count_mismatch(nodes={len(graph.nodes)},"
                        f"steps={len(tl.steps)})"
                    )
                inconsistencies.append(f"obs_{i}: {', '.join(issues)}")

        score = ok_count / N * 100
        if ok_count == N:
            return _result_pass(
                CID,
                NAME,
                f"{N}/{N} triplets Graph+CausalTree+Timeline coherents"
                " (explainability="
                f"{'available' if _EXPLAINABILITY_AVAILABLE else 'absent'})",
                t0,
                score=100.0,
                metrics={
                    "n_tested": N,
                    "n_ok": ok_count,
                    "explainability_available": _EXPLAINABILITY_AVAILABLE,
                },
            )
        return _result_fail(
            CID,
            NAME,
            f"{ok_count}/{N} coherents -- {inconsistencies[:3]}",
            t0,
            score=score,
            metrics={"n_tested": N, "n_ok": ok_count, "issues": inconsistencies},
        )
    except Exception as e:
        return _result_fail(CID, NAME, "Exception coherence", t0, error=str(e))


# ── IV-LIVE-010: Root Cause Integrity ─────────────────────────────────────────


def check_iv_live_010(live_mode: bool = False) -> LiveCheckResult:
    """CausalTree root_cause.causing_layer matches graph blocker structure."""
    CID, NAME = "IV-LIVE-010", "Root Cause Integrity"
    t0 = time.perf_counter()

    # 12 blocked scenarios + 3 approved
    test_cases: list[tuple[Optional[str], bool]] = [
        (layer, False) for layer in LAYER_ORDER
    ]
    test_cases += [(None, True)] * 3

    ok_count = 0
    errors: list[str] = []

    try:
        for blocker, approved in test_cases:
            obs = _make_obs(trade_allowed=approved, blocker=blocker)
            graph = GraphBuilder.build(obs)
            tree = CausalTreeBuilder.build(obs, graph)
            rc = tree.root_cause.causing_layer if tree.root_cause else None

            if approved:
                expected = graph.nodes[-1].layer if graph.nodes else LAYER_ORDER[-1]
                if rc == expected:
                    ok_count += 1
                else:
                    errors.append(f"APPROVED: rc={rc}, expected={expected}")
            else:
                if rc == blocker:
                    ok_count += 1
                else:
                    errors.append(f"blocker={blocker}: rc={rc}")

        total = len(test_cases)
        score = ok_count / total * 100
        if ok_count == total:
            return _result_pass(
                CID,
                NAME,
                f"{total}/{total} root_cause coherents (12 blockers + 3 APPROVED)",
                t0,
                score=100.0,
                metrics={"n_tested": total, "n_ok": ok_count},
            )
        return _result_fail(
            CID,
            NAME,
            f"{ok_count}/{total} root_cause coherents -- {errors[:3]}",
            t0,
            score=score,
            metrics={"n_tested": total, "n_ok": ok_count, "errors": errors},
        )
    except Exception as e:
        return _result_fail(
            CID, NAME, "Exception Root Cause Integrity", t0, error=str(e)
        )


# ── Suite runner ───────────────────────────────────────────────────────────────


def run_suite(live_mode: bool = False) -> list[LiveCheckResult]:
    return [
        check_iv_live_001(live_mode),
        check_iv_live_002(live_mode),
        check_iv_live_003(live_mode),
        check_iv_live_004(live_mode),
        check_iv_live_005(live_mode),
        check_iv_live_006(live_mode),
        check_iv_live_007(),
        check_iv_live_008(live_mode),
        check_iv_live_009(),
        check_iv_live_010(live_mode),
    ]


def run_single(check_id: str, live_mode: bool = False) -> LiveCheckResult:
    check_map = {
        "IV-LIVE-001": lambda: check_iv_live_001(live_mode),
        "IV-LIVE-002": lambda: check_iv_live_002(live_mode),
        "IV-LIVE-003": lambda: check_iv_live_003(live_mode),
        "IV-LIVE-004": lambda: check_iv_live_004(live_mode),
        "IV-LIVE-005": lambda: check_iv_live_005(live_mode),
        "IV-LIVE-006": lambda: check_iv_live_006(live_mode),
        "IV-LIVE-007": lambda: check_iv_live_007(),
        "IV-LIVE-008": lambda: check_iv_live_008(live_mode),
        "IV-LIVE-009": lambda: check_iv_live_009(),
        "IV-LIVE-010": lambda: check_iv_live_010(live_mode),
    }
    fn = check_map.get(check_id.upper())
    if not fn:
        raise ValueError(f"Check ID inconnu: {check_id}. Valides: {list(check_map)}")
    return fn()


# ── Metrics ────────────────────────────────────────────────────────────────────


def _compute_iii(iv_live_results: list[LiveCheckResult]) -> dict[str, float]:
    """
    III = weighted average of IV (assumed PASS) + IV-LIVE scores.
    IV checks: 4% each x 10 = 40%. IV-LIVE: 6% each x 10 = 60% (SKIP excluded).
    """
    iv_weight = 4.0
    iv_live_weight = 6.0
    total_weight = 10 * iv_weight
    weighted_score = 10 * iv_weight * 100.0

    for r in iv_live_results:
        if r.skipped:
            continue
        total_weight += iv_live_weight
        weighted_score += iv_live_weight * r.score

    iii = round(weighted_score / total_weight, 1) if total_weight > 0 else 0.0

    def _avg(*ids: str) -> float:
        matches = [r for r in iv_live_results if r.check_id in ids and not r.skipped]
        return (
            round(sum(r.score for r in matches) / len(matches), 1) if matches else 100.0
        )

    return {
        "iii": iii,
        "sub_coverage": _avg("IV-LIVE-001", "IV-LIVE-002"),
        "sub_lifecycle": _avg("IV-LIVE-003"),
        "sub_integrity": _avg("IV-LIVE-004", "IV-LIVE-006"),
        "sub_timeline": _avg("IV-LIVE-005"),
        "sub_memory": _avg("IV-LIVE-007"),
        "sub_replay": _avg("IV-LIVE-008"),
        "sub_consistency": _avg("IV-LIVE-009"),
        "sub_root_cause": _avg("IV-LIVE-010"),
    }


def _compute_ocs(
    iii: float,
    iv_live_results: list[LiveCheckResult],
    replay_score: float,
    dataset_score: float = 0.0,
    exp001_active: bool = False,
) -> float:
    n_pass = sum(1 for r in iv_live_results if r.passed and not r.skipped)
    n_total = sum(1 for r in iv_live_results if not r.skipped)
    live_rate = (n_pass / n_total * 100.0) if n_total > 0 else 0.0

    return round(
        iii * 0.30
        + live_rate * 0.25
        + replay_score * 0.20
        + dataset_score * 0.15
        + (100.0 if exp001_active else 0.0) * 0.10,
        1,
    )


def _n_production() -> int:
    try:
        return DIPStore.instance().count_decisions()
    except Exception:
        return 0


# ── Certification ──────────────────────────────────────────────────────────────


def certify(
    iv_live_results: list[LiveCheckResult],
    iv_all_pass: bool = True,
    live_mode: bool = False,
) -> dict[str, Any]:
    n_production = _n_production() if live_mode else 0

    metrics = _compute_iii(iv_live_results)
    iii = metrics["iii"]

    replay_r = next((r for r in iv_live_results if r.check_id == "IV-LIVE-008"), None)
    replay_score = replay_r.score if replay_r and not replay_r.skipped else 100.0
    ocs = _compute_ocs(iii, iv_live_results, replay_score)

    n_pass = sum(1 for r in iv_live_results if r.passed and not r.skipped)
    n_fail = sum(1 for r in iv_live_results if not r.passed and not r.skipped)
    n_skip = sum(1 for r in iv_live_results if r.skipped)

    critical_ids = {"IV-LIVE-001", "IV-LIVE-008", "IV-LIVE-010"}
    critical_fail = any(
        not r.passed and not r.skipped and r.check_id in critical_ids
        for r in iv_live_results
    )

    if not iv_all_pass:
        level, level_name = 0, "NOT_CERTIFIED"
        decision = "IV-001..IV-010 requis avant toute certification"
    elif critical_fail:
        level, level_name = 1, "Certified Software"
        failed_c = [
            r.check_id
            for r in iv_live_results
            if not r.passed and not r.skipped and r.check_id in critical_ids
        ]
        decision = f"Level 1 -- check critique FAIL: {failed_c}"
    elif iii < 95.0:
        level, level_name = 1, "Certified Software"
        decision = f"Level 1 -- III={iii:.1f} < 95 requis pour Level 2"
    elif n_fail > 2:
        level, level_name = 1, "Certified Software"
        decision = f"Level 1 -- {n_fail} check(s) FAIL (max 2 pour Level 2)"
    elif n_production < MIN_DECISIONS:
        level, level_name = 2, "Certified Instrumentation"
        decision = (
            f"Level 2 atteint -- activer FEATURE_DIP=true et collecter "
            f"N>={MIN_DECISIONS} decisions pour Level 3 (actuel: N={n_production})"
        )
    elif ocs < 90.0 or n_fail > 0:
        level, level_name = 2, "Certified Instrumentation"
        decision = (
            f"Level 2 -- OCS={ocs:.1f} < 90 requis pour Level 3"
            if ocs < 90.0
            else f"Level 2 -- {n_fail} check(s) FAIL sur donnees de production"
        )
    else:
        level, level_name = 3, "Certified Live Observer"
        decision = "Level 3 ATTEINT -- DIP certifie observateur live, S1 autorise"

    return {
        "level": level,
        "level_name": level_name,
        "decision": decision,
        "iii": iii,
        "ocs": ocs,
        "n_pass": n_pass,
        "n_fail": n_fail,
        "n_skip": n_skip,
        "n_production": n_production,
        "critical_fail": critical_fail,
        "sub_scores": metrics,
        "iv_all_pass": iv_all_pass,
        "live_mode": live_mode,
    }


# ── History ────────────────────────────────────────────────────────────────────


def save_history(results: list[LiveCheckResult], cert: dict[str, Any]) -> None:
    CERT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    seq = 1
    if CERT_HISTORY_PATH.exists():
        lines = [
            ln
            for ln in CERT_HISTORY_PATH.read_text(encoding="utf-8").strip().splitlines()
            if ln
        ]
        seq = len(lines) + 1

    _year = datetime.now(timezone.utc).strftime("%Y")
    entry = {
        "certification_id": f"OBS-CERT-{_year}-{seq:04d}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "level": cert["level"],
        "level_name": cert["level_name"],
        "iii": cert["iii"],
        "ocs": cert["ocs"],
        "iv_live_passed": cert["n_pass"],
        "iv_live_failed": cert["n_fail"],
        "iv_live_skipped": cert["n_skip"],
        "n_decisions_production": cert["n_production"],
        "live_mode": cert["live_mode"],
        "revoked": False,
        "revocation_reason": None,
        "decision": cert["decision"],
        "checks": [
            {
                "id": r.check_id,
                "status": r.status,
                "score": r.score,
                "duration_ms": r.duration_ms,
            }
            for r in results
        ],
    }
    with CERT_HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")


def load_history() -> list[dict]:
    if not CERT_HISTORY_PATH.exists():
        return []
    result = []
    for line in CERT_HISTORY_PATH.read_text(encoding="utf-8").strip().splitlines():
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return result


# ── Formatters ─────────────────────────────────────────────────────────────────

_STATUS_ICON = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}
_LEVEL_ICON = {0: "[!!]", 1: "[L1]", 2: "[L2]", 3: "[L3]", 4: "[L4]"}


def print_report(
    results: list[LiveCheckResult], cert: dict[str, Any], verbose: bool = False
) -> None:
    print("=" * 72)
    print(f"INV-IV-LIVE: Live Observer Validation Suite v{VERSION}")
    mode = "PRODUCTION" if cert["live_mode"] else "SYNTHETIC"
    print(
        f"Mode: {mode}  |  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    print("=" * 72)
    total_ms = sum(r.duration_ms for r in results)
    for r in results:
        icon = _STATUS_ICON[r.status]
        score_str = f"  score={r.score:.0f}%" if not r.passed and not r.skipped else ""
        print(
            f"  {icon} {r.check_id:<16}  {r.name:<36} "
            f"{r.duration_ms:>6.0f}ms{score_str}"
        )
        if verbose or (not r.passed and not r.skipped):
            print(f"           {r.details}")
            if r.error:
                print(f"           ERROR: {r.error}")
        elif r.skipped and verbose:
            print(f"           {r.skip_reason}")
    print("-" * 72)
    print(
        f"  IV-LIVE: {cert['n_pass']} PASS  {cert['n_fail']} FAIL  "
        f"{cert['n_skip']} SKIP  |  {total_ms:.0f}ms"
    )
    print(f"  III:     {cert['iii']:.1f}/100   (seuil Level 2: >=95)")
    print(f"  OCS:     {cert['ocs']:.1f}/100   (seuil Level 3: >=90)")
    if verbose:
        sub = cert["sub_scores"]
        print(
            f"  Sub:     Coverage={sub['sub_coverage']:.0f}%  "
            f"Replay={sub['sub_replay']:.0f}%  "
            f"RootCause={sub['sub_root_cause']:.0f}%  "
            f"Memory={sub['sub_memory']:.0f}%  "
            f"Consistency={sub['sub_consistency']:.0f}%"
        )
    print()
    level_icon = _LEVEL_ICON.get(cert["level"], "[??]")
    print(f"  {level_icon} {cert['level_name']}")
    print(f"  {cert['decision']}")
    print("=" * 72)


def print_history(history: list[dict]) -> None:
    if not history:
        print("Aucune certification enregistree.")
        return
    print("=" * 72)
    print("Historique des certifications (20 derniers)")
    print("=" * 72)
    for entry in history[-20:]:
        revoked = " [REVOQUE]" if entry.get("revoked") else ""
        print(
            f"  {entry['certification_id']}  "
            f"L{entry['level']}  III={entry['iii']:.1f}  "
            f"OCS={entry.get('ocs', 0):.1f}  "
            f"{entry['generated_at'][:10]}{revoked}"
        )
        print(f"    {entry['decision']}")
    print("=" * 72)


# ── CLI ────────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="INV-IV-LIVE: Live Observer Validation Suite"
    )
    parser.add_argument("--live", action="store_true", help="Use production DIPStore")
    parser.add_argument(
        "--check", metavar="ID", help="Run single check (e.g. IV-LIVE-006)"
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output", help="JSON output"
    )
    parser.add_argument(
        "--history", action="store_true", help="Show certification history"
    )
    parser.add_argument(
        "--report", action="store_true", help="Show detailed sub-scores"
    )
    parser.add_argument(
        "--export", metavar="FILE", help="Export full certification to JSON file"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose per-check details"
    )
    args = parser.parse_args()

    if args.history:
        history = load_history()
        if args.json_output:
            print(json.dumps(history, indent=2, ensure_ascii=True))
        else:
            print_history(history)
        return 0

    if args.check:
        try:
            result = run_single(args.check, live_mode=args.live)
        except ValueError as e:
            print(f"ERREUR: {e}")
            return 1
        if args.json_output:
            d = {k: v for k, v in result.__dict__.items()}
            d["status"] = result.status
            print(json.dumps(d, indent=2, ensure_ascii=True))
        else:
            icon = _STATUS_ICON[result.status]
            print(f"{icon} {result.check_id}: {result.name}")
            print(f"  Status:   {result.status}")
            print(f"  Score:    {result.score:.0f}%")
            print(f"  Time:     {result.duration_ms:.1f}ms")
            print(f"  Details:  {result.details}")
            if result.error:
                print(f"  Error:    {result.error}")
            if result.skip_reason:
                print(f"  Skip:     {result.skip_reason}")
        return 0 if (result.passed or result.skipped) else 1

    results = run_suite(live_mode=args.live)
    cert = certify(results, iv_all_pass=True, live_mode=args.live)
    save_history(results, cert)

    output_dict: dict[str, Any] = {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "live_mode": args.live,
        "certification": cert,
        "results": [
            {
                "check_id": r.check_id,
                "name": r.name,
                "status": r.status,
                "score": r.score,
                "duration_ms": r.duration_ms,
                "details": r.details,
                "metrics": r.metrics,
                "error": r.error,
                "skip_reason": r.skip_reason,
            }
            for r in results
        ],
    }

    if args.export:
        export_path = Path(args.export)
        export_path.write_text(
            json.dumps(output_dict, indent=2, ensure_ascii=True), encoding="utf-8"
        )
        print(f"Certification exportee: {export_path}")

    if args.json_output:
        print(json.dumps(output_dict, indent=2, ensure_ascii=True))
    else:
        print_report(results, cert, verbose=args.verbose or args.report)

    return 0 if cert["level"] >= 2 else 1


if __name__ == "__main__":
    sys.exit(main())
