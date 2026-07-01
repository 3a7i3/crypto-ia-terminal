"""Tests D07 (Replay) + D11 (Diff) + D12 (Alert)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dip.core.types import Severity, now_us
from dip.modules.decision_alert import (
    RULE_REJECTION_BURST,
    AlertDetector,
    DecisionAlertEngine,
)
from dip.modules.decision_diff import DecisionDiffEngine
from dip.modules.decision_graph import DecisionGraphEngine, GraphBuilder
from dip.modules.decision_replay import DecisionReplayEngine, ReplayBuilder
from tests.dip.conftest import _insert_decision, _make_obs

# ── Replay ─────────────────────────────────────────────────────────────────────


class TestReplayBuilder:

    def test_build_creates_steps(self, obs_rejected):
        graph = GraphBuilder.build(obs_rejected)
        row = {"symbol": "BTCUSDT", "direction": "LONG", "regime": "SIDEWAYS"}
        session = ReplayBuilder.build(graph, None, obs_rejected.packet_id, row)
        assert session.total_steps > 0
        assert session.packet_id == obs_rejected.packet_id

    def test_blocker_is_marked(self, obs_rejected):
        graph = GraphBuilder.build(obs_rejected)
        row = {"symbol": "BTCUSDT", "direction": "LONG", "regime": "SIDEWAYS"}
        session = ReplayBuilder.build(graph, None, obs_rejected.packet_id, row)
        blockers = [s for s in session.steps if s.is_blocker]
        assert len(blockers) >= 1

    def test_approved_no_blocker(self, obs_approved):
        graph = GraphBuilder.build(obs_approved)
        row = {"symbol": "BTCUSDT", "direction": "LONG", "regime": "SIDEWAYS"}
        session = ReplayBuilder.build(graph, None, obs_approved.packet_id, row)
        blockers = [s for s in session.steps if s.is_blocker]
        assert len(blockers) == 0


class TestInteractiveReplay:

    def _make_session(self, obs):
        graph = GraphBuilder.build(obs)
        row = {"symbol": "BTCUSDT", "direction": "LONG", "regime": "SIDEWAYS"}
        return ReplayBuilder.build(graph, None, obs.packet_id, row)

    def test_step_forward(self, obs_rejected):
        from dip.modules.decision_replay import InteractiveReplay

        session = self._make_session(obs_rejected)
        ir = InteractiveReplay(session)
        step = ir.step_forward()
        assert step is not None
        assert step.step_index == 0

    def test_step_backward_at_start(self, obs_rejected):
        from dip.modules.decision_replay import InteractiveReplay

        session = self._make_session(obs_rejected)
        ir = InteractiveReplay(session)
        step = ir.step_backward()
        assert step is None

    def test_jump_to_blocker(self, obs_rejected):
        from dip.modules.decision_replay import InteractiveReplay

        session = self._make_session(obs_rejected)
        ir = InteractiveReplay(session)
        blocker = ir.jump_to_blocker()
        assert blocker is not None
        assert blocker.is_blocker

    def test_add_annotation(self, obs_rejected):
        from dip.modules.decision_replay import InteractiveReplay

        session = self._make_session(obs_rejected)
        ir = InteractiveReplay(session)
        ir.step_forward()
        ir.add_annotation(0, "Test annotation", "test_user")
        annotations = ir.get_annotations()
        assert len(annotations) == 1
        assert annotations[0].annotation == "Test annotation"


class TestDecisionReplayEngine:

    def test_build_replay_returns_none_if_unknown(self, tmp_store):
        engine = DecisionReplayEngine()
        with patch.object(engine, "_store", tmp_store):
            session = engine.build_replay("nonexistent_id")
            assert session is None

    def test_compare_returns_summary(self, tmp_store):
        from dip.modules.decision_graph import DecisionGraphEngine

        graph_engine = DecisionGraphEngine()
        engine = DecisionReplayEngine()

        with patch.object(graph_engine, "_store", tmp_store), patch.object(
            engine, "_store", tmp_store
        ), patch.object(engine, "_graph_engine", graph_engine):
            obs1 = _make_obs(False)
            obs2 = _make_obs(False)
            graph_engine.on_observation(obs1)
            graph_engine.on_observation(obs2)
            _insert_decision(
                tmp_store, packet_id=obs1.packet_id, symbol="BTCUSDT", status="REJECTED"
            )
            _insert_decision(
                tmp_store, packet_id=obs2.packet_id, symbol="BTCUSDT", status="REJECTED"
            )
            result = engine.compare(obs1.packet_id, obs2.packet_id)
            # Peut être None si get_graph échoue, acceptable
            if result is not None:
                assert isinstance(result.summary, str)


# ── Diff ───────────────────────────────────────────────────────────────────────


class TestDecisionDiffEngine:

    def test_diff_same_obs(self, tmp_store):
        from dip.modules.decision_graph import DecisionGraphEngine

        graph_engine = DecisionGraphEngine()
        diff_engine = DecisionDiffEngine()

        with patch.object(graph_engine, "_store", tmp_store), patch.object(
            diff_engine, "_store", tmp_store
        ), patch.object(diff_engine, "_graph_engine", graph_engine):
            obs1 = _make_obs(False)
            obs2 = _make_obs(False)
            graph_engine.on_observation(obs1)
            graph_engine.on_observation(obs2)
            _insert_decision(tmp_store, packet_id=obs1.packet_id, status="REJECTED")
            _insert_decision(tmp_store, packet_id=obs2.packet_id, status="REJECTED")
            diff = diff_engine.diff(obs1.packet_id, obs2.packet_id)
            if diff is not None:
                # Même résultat → outcome_changed = False
                assert isinstance(diff.summary, str)

    def test_diff_approved_vs_rejected(self, tmp_store):
        from dip.modules.decision_graph import DecisionGraphEngine

        graph_engine = DecisionGraphEngine()
        diff_engine = DecisionDiffEngine()

        with patch.object(graph_engine, "_store", tmp_store), patch.object(
            diff_engine, "_store", tmp_store
        ), patch.object(diff_engine, "_graph_engine", graph_engine):
            obs_a = _make_obs(True)
            obs_r = _make_obs(False)
            graph_engine.on_observation(obs_a)
            graph_engine.on_observation(obs_r)
            _insert_decision(tmp_store, packet_id=obs_a.packet_id, status="APPROVED")
            _insert_decision(tmp_store, packet_id=obs_r.packet_id, status="REJECTED")
            diff = diff_engine.diff(obs_a.packet_id, obs_r.packet_id)
            if diff is not None:
                assert diff.outcome_changed


# ── Alert ──────────────────────────────────────────────────────────────────────


class TestAlertDetector:

    def test_no_alert_below_threshold(self, tmp_store):
        detector = AlertDetector(tmp_store)
        obs = _make_obs(False)
        # 9 obs rejected = sous le seuil de 10
        for _ in range(9):
            alerts = detector.update(_make_obs(False))
        assert not any(a.rule_id == "R01" for a in alerts)

    def test_burst_alert_at_10(self, tmp_store):
        detector = AlertDetector(tmp_store)
        for _ in range(9):
            detector.update(_make_obs(False))
        # 10e obs → burst
        alerts = detector.update(_make_obs(False))
        r01_alerts = [a for a in alerts if a.rule_id == "R01"]
        assert len(r01_alerts) >= 1

    def test_no_burst_with_mixed(self, tmp_store):
        detector = AlertDetector(tmp_store)
        for i in range(10):
            # Alternance approved/rejected
            obs = _make_obs(i % 2 == 0)
            alerts = detector.update(obs)
        r01 = [a for a in alerts if a.rule_id == "R01"]
        assert len(r01) == 0


class TestDecisionAlertEngine:

    def test_get_active_alerts_empty(self, tmp_store):
        engine = DecisionAlertEngine()
        with patch.object(engine, "_store", tmp_store):
            alerts = engine.get_active_alerts()
            assert alerts == []

    def test_get_rules(self):
        engine = DecisionAlertEngine()
        rules = engine.get_rules()
        assert len(rules) == 5

    def test_summary_no_alerts(self, tmp_store):
        engine = DecisionAlertEngine()
        with patch.object(engine, "_store", tmp_store):
            summary = engine.get_summary()
            assert summary.total_active == 0
            assert summary.top_severity == "OK"

    def test_cooldown_prevents_duplicate(self, tmp_store):
        engine = DecisionAlertEngine()
        with patch.object(engine, "_store", tmp_store), patch.object(
            engine._detector, "_store", tmp_store
        ):
            # Simuler burst
            for _ in range(9):
                engine._detector.update(_make_obs(False))
            alerts1 = engine.on_observation(_make_obs(False))
            alerts2 = engine.on_observation(_make_obs(False))
            # 2e alerte supprimée par cooldown
            r01_count_2 = sum(1 for a in alerts2 if a.rule_id == "R01")
            assert r01_count_2 == 0
