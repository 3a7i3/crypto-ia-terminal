"""Tests D08 — Explainability Score Engine."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from dip.modules.causal_tree import CausalTreeBuilder
from dip.modules.decision_graph import GraphBuilder
from dip.modules.explainability import (
    ExplainabilityScoreEngine,
    _grade,
    _score_causal_clarity,
    _score_path_simplicity,
    _score_reasoning_readability,
    _score_threshold_stability,
)


class TestGradeScale:

    def test_grade_A_plus(self):
        assert _grade(0.97) == "A+"

    def test_grade_A(self):
        assert _grade(0.91) == "A"

    def test_grade_F(self):
        assert _grade(0.30) == "F"

    def test_grade_B(self):
        assert _grade(0.76) == "B"

    def test_grade_boundaries(self):
        for score in [0.0, 0.5, 0.75, 0.95, 1.0]:
            grade = _grade(score)
            assert grade in (
                "A+",
                "A",
                "A-",
                "B+",
                "B",
                "B-",
                "C+",
                "C",
                "C-",
                "D",
                "F",
            )


class TestScorers:

    def test_path_simplicity_short_pipeline(self, obs_rejected):
        graph = GraphBuilder.build(obs_rejected)
        score, detail = _score_path_simplicity(graph)
        assert 0.0 <= score <= 1.0
        assert isinstance(detail, str)

    def test_causal_clarity(self, obs_rejected):
        graph = GraphBuilder.build(obs_rejected)
        tree = CausalTreeBuilder.build(obs_rejected, graph)
        score, detail = _score_causal_clarity(tree)
        assert 0.0 <= score <= 1.0

    def test_threshold_stability_no_edges(self, obs_approved):
        graph = GraphBuilder.build(obs_approved)
        score, detail = _score_threshold_stability(graph)
        assert 0.0 <= score <= 1.0

    def test_reasoning_readability_approved(self, obs_approved):
        score, detail = _score_reasoning_readability(obs_approved)
        assert 0.0 <= score <= 1.0

    def test_reasoning_readability_rejected_with_reason(self, obs_rejected):
        score, detail = _score_reasoning_readability(obs_rejected)
        assert 0.0 <= score <= 1.0


class TestExplainabilityEngine:

    def test_on_observation_computes_score(self, tmp_store):
        from dip.modules.causal_tree import CausalTreeEngine
        from dip.modules.decision_graph import DecisionGraphEngine

        graph_engine = DecisionGraphEngine()
        tree_engine = CausalTreeEngine()
        exp_engine = ExplainabilityScoreEngine()

        with patch.object(graph_engine, "_store", tmp_store), patch.object(
            tree_engine, "_store", tmp_store
        ), patch.object(tree_engine, "_graph_engine", graph_engine), patch.object(
            exp_engine, "_store", tmp_store
        ), patch.object(
            exp_engine, "_graph_engine", graph_engine
        ), patch.object(
            exp_engine, "_causal_engine", tree_engine
        ):
            from tests.dip.conftest import _make_obs

            obs = _make_obs(False)
            graph_engine.on_observation(obs)
            tree_engine.on_observation(obs)
            exp_engine.on_observation(obs)
            score = exp_engine.compute_score(obs.packet_id)
            assert score is not None
            assert 0.0 <= score.global_score <= 1.0
            assert score.grade in (
                "A+",
                "A",
                "A-",
                "B+",
                "B",
                "B-",
                "C+",
                "C",
                "C-",
                "D",
                "F",
            )

    def test_weights_sum_to_one(self):
        weights = ExplainabilityScoreEngine._WEIGHTS
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.001

    def test_5_dimensions(self, tmp_store):
        from dip.modules.causal_tree import CausalTreeEngine
        from dip.modules.decision_graph import DecisionGraphEngine

        graph_engine = DecisionGraphEngine()
        tree_engine = CausalTreeEngine()
        exp_engine = ExplainabilityScoreEngine()
        with patch.object(graph_engine, "_store", tmp_store), patch.object(
            tree_engine, "_store", tmp_store
        ), patch.object(tree_engine, "_graph_engine", graph_engine), patch.object(
            exp_engine, "_store", tmp_store
        ), patch.object(
            exp_engine, "_graph_engine", graph_engine
        ), patch.object(
            exp_engine, "_causal_engine", tree_engine
        ):
            from tests.dip.conftest import _make_obs

            obs = _make_obs(False)
            graph_engine.on_observation(obs)
            tree_engine.on_observation(obs)
            exp_engine.on_observation(obs)
            score = exp_engine.compute_score(obs.packet_id)
            if score:
                assert len(score.dimensions) == 5
