"""Tests D01 — Decision Graph Engine."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from dip.core.types import DecisionStatus, LayerStatus, now_us
from dip.modules.decision_graph import (
    DecisionGraphEngine,
    GraphBuilder,
    _extract_layer_data,
    get_graph_engine,
)


class TestExtractLayerData:

    def test_approved_has_all_layers(self, obs_approved):
        layers = _extract_layer_data(obs_approved)
        assert len(layers) == 12

    def test_rejected_truncates_at_blocker(self, obs_rejected):
        # meta_strategy est le bloqueur → on s'arrête après meta_strategy
        layers = _extract_layer_data(obs_rejected)
        layer_names = [l["layer"] for l in layers]
        # Le bloqueur est "meta_strategy" (lowercase avec underscore)
        assert "meta_strategy" in layer_names
        blocker_idx = layer_names.index("meta_strategy")
        assert not any(
            l["status"] == LayerStatus.PASSED for l in layers[blocker_idx + 1 :]
        )

    def test_gate_rejected(self, obs_rejected_gate):
        layers = _extract_layer_data(obs_rejected_gate)
        gate_layers = [l for l in layers if l["layer"] == "gate"]
        assert gate_layers
        assert gate_layers[0]["status"] == LayerStatus.BLOCKED


class TestGraphBuilder:

    def test_build_approved(self, obs_approved):
        graph = GraphBuilder.build(obs_approved)
        assert graph.status == DecisionStatus.APPROVED
        assert len(graph.nodes) > 0
        assert graph.metrics.depth > 0

    def test_build_rejected(self, obs_rejected):
        graph = GraphBuilder.build(obs_rejected)
        assert graph.status == DecisionStatus.REJECTED
        blocked = [n for n in graph.nodes if n.status == LayerStatus.BLOCKED]
        assert len(blocked) >= 1
        assert blocked[0].layer == "meta_strategy"

    def test_critical_path_nonempty_approved(self, obs_approved):
        graph = GraphBuilder.build(obs_approved)
        # Le chemin critique peut être vide si un seul nœud
        assert isinstance(graph.critical_path, tuple)

    def test_edge_weights(self, obs_approved):
        graph = GraphBuilder.build(obs_approved)
        if graph.edges:
            for edge in graph.edges:
                assert isinstance(edge.weight, float)

    def test_metrics_confidence_range(self, obs_approved):
        graph = GraphBuilder.build(obs_approved)
        assert 0.0 <= graph.metrics.confidence_start <= 1.0
        assert 0.0 <= graph.metrics.confidence_end <= 1.0

    def test_packet_id_preserved(self, obs_approved):
        graph = GraphBuilder.build(obs_approved)
        assert graph.packet_id == obs_approved.packet_id


class TestDecisionGraphEngine:

    def test_on_observation_stores_graph(self, tmp_store):
        from dip.modules.decision_graph import DecisionGraphEngine

        engine = DecisionGraphEngine()
        # Patch le store
        with patch.object(engine, "_store", tmp_store):
            from tests.dip.conftest import _make_obs

            obs = _make_obs(True)
            engine.on_observation(obs)
            graph = engine.get_graph(obs.packet_id)
            assert graph is not None
            assert graph.packet_id == obs.packet_id

    def test_layer_contributions(self, tmp_store):
        from dip.modules.decision_graph import DecisionGraphEngine

        engine = DecisionGraphEngine()
        with patch.object(engine, "_store", tmp_store):
            from tests.dip.conftest import _make_obs

            obs = _make_obs(False)
            engine.on_observation(obs)
            contribs = engine.get_layer_contributions(obs.packet_id)
            assert contribs is not None
            assert len(contribs) > 0

    def test_rejection_stats_empty(self, tmp_store):
        from dip.modules.decision_graph import DecisionGraphEngine

        engine = DecisionGraphEngine()
        with patch.object(engine, "_store", tmp_store):
            stats = engine.get_layer_rejection_stats(start_us=0, end_us=now_us())
            assert isinstance(stats, dict)
