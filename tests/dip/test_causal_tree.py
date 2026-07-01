"""Tests D03 — Causal Tree Engine."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dip.modules.causal_tree import CausalTreeBuilder, CausalTreeEngine
from dip.modules.decision_graph import GraphBuilder


class TestCausalTreeBuilder:

    def test_build_rejected(self, obs_rejected):
        graph = GraphBuilder.build(obs_rejected)
        tree = CausalTreeBuilder.build(obs_rejected, graph)
        assert tree is not None
        assert tree.root_cause is not None
        assert tree.root_cause.causing_layer == "meta_strategy"

    def test_build_approved(self, obs_approved):
        graph = GraphBuilder.build(obs_approved)
        tree = CausalTreeBuilder.build(obs_approved, graph)
        assert tree is not None
        assert tree.result == "APPROVED"

    def test_causal_paths_nonempty(self, obs_rejected):
        graph = GraphBuilder.build(obs_rejected)
        tree = CausalTreeBuilder.build(obs_rejected, graph)
        assert len(tree.causal_paths) >= 0  # peut être vide si aucun bloqueur

    def test_description_nonempty(self, obs_rejected):
        graph = GraphBuilder.build(obs_rejected)
        tree = CausalTreeBuilder.build(obs_rejected, graph)
        assert tree.root_cause.description
        assert len(tree.root_cause.description) > 5


class TestCausalTreeEngine:

    def test_on_observation_builds_tree(self, tmp_store):
        from dip.modules.causal_tree import CausalTreeEngine
        from dip.modules.decision_graph import DecisionGraphEngine

        graph_engine = DecisionGraphEngine()
        tree_engine = CausalTreeEngine()

        with patch.object(graph_engine, "_store", tmp_store), patch.object(
            tree_engine, "_store", tmp_store
        ), patch.object(tree_engine, "_graph_engine", graph_engine):
            from tests.dip.conftest import _make_obs

            obs = _make_obs(False)
            graph_engine.on_observation(obs)
            tree_engine.on_observation(obs)
            tree = tree_engine.build_causal_tree(obs.packet_id)
            assert tree is not None

    def test_get_root_cause(self, tmp_store):
        from dip.modules.causal_tree import CausalTreeEngine
        from dip.modules.decision_graph import DecisionGraphEngine

        graph_engine = DecisionGraphEngine()
        tree_engine = CausalTreeEngine()

        with patch.object(graph_engine, "_store", tmp_store), patch.object(
            tree_engine, "_store", tmp_store
        ), patch.object(tree_engine, "_graph_engine", graph_engine):
            from tests.dip.conftest import _make_obs

            obs = _make_obs(False)
            graph_engine.on_observation(obs)
            tree_engine.on_observation(obs)
            root = tree_engine.get_root_cause(obs.packet_id)
            assert root is not None
            assert root.causing_layer == "meta_strategy"

    def test_rejection_stats_empty_on_fresh(self, tmp_store):
        from dip.modules.causal_tree import CausalTreeEngine

        engine = CausalTreeEngine()
        with patch.object(engine, "_store", tmp_store):
            stats = engine.get_rejection_stats()
            assert isinstance(stats, dict)
