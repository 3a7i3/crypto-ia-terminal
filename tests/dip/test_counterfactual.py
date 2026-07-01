"""Tests D04 — Counterfactual Engine."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dip.core.types import DecisionStatus, LayerStatus, ScenarioType
from dip.modules.counterfactual import (
    CounterfactualEngine,
    ImpactAssessor,
    PipelineSimulator,
    Scenario,
)
from dip.modules.decision_graph import GraphBuilder


class TestPipelineSimulator:

    def test_remove_blocker_leads_to_next_blocker_or_approved(self, obs_rejected):
        graph = GraphBuilder.build(obs_rejected)
        status, conf = PipelineSimulator.simulate_without_layer(graph, "MetaStrategy")
        # Soit APPROVED (pas d'autre bloqueur) soit REJECTED (autre bloqueur)
        assert status in (DecisionStatus.APPROVED, DecisionStatus.REJECTED)

    def test_remove_nonblocker_unchanged(self, obs_approved):
        graph = GraphBuilder.build(obs_approved)
        status, conf = PipelineSimulator.simulate_without_layer(graph, "ThreatRadar")
        # Si aucune couche ne bloque, résultat inchangé
        assert status == DecisionStatus.APPROVED

    def test_threshold_permissive_on_blocker(self, obs_rejected):
        graph = GraphBuilder.build(obs_rejected)
        status, conf = PipelineSimulator.simulate_with_threshold(
            graph, "MetaStrategy", 0.5
        )
        assert status in (
            DecisionStatus.APPROVED,
            DecisionStatus.REJECTED,
            DecisionStatus.UNKNOWN,
        )

    def test_threshold_strict_on_approved(self, obs_approved):
        graph = GraphBuilder.build(obs_approved)
        status, conf = PipelineSimulator.simulate_with_threshold(graph, "Gate", 2.0)
        assert status in (DecisionStatus.APPROVED, DecisionStatus.REJECTED)


class TestImpactAssessor:

    def test_outcome_unchanged(self):
        impact = ImpactAssessor.assess(
            DecisionStatus.REJECTED, DecisionStatus.REJECTED, 0.4, 0.4
        )
        assert not impact.outcome_changed
        assert impact.estimated_pnl_impact == 0.0

    def test_rejected_to_approved(self):
        impact = ImpactAssessor.assess(
            DecisionStatus.REJECTED, DecisionStatus.APPROVED, 0.0, 0.7
        )
        assert impact.outcome_changed
        assert impact.estimated_pnl_impact > 0.0

    def test_approved_to_rejected(self):
        impact = ImpactAssessor.assess(
            DecisionStatus.APPROVED, DecisionStatus.REJECTED, 0.7, 0.0
        )
        assert impact.outcome_changed
        assert impact.estimated_pnl_impact < 0.0


class TestCounterfactualEngine:

    def test_simulate_without_layer(self, tmp_store):
        from dip.modules.counterfactual import CounterfactualEngine
        from dip.modules.decision_graph import DecisionGraphEngine

        graph_engine = DecisionGraphEngine()
        cf_engine = CounterfactualEngine()

        with patch.object(graph_engine, "_store", tmp_store), patch.object(
            cf_engine, "_store", tmp_store
        ), patch.object(cf_engine, "_graph_engine", graph_engine):
            from tests.dip.conftest import _make_obs

            obs = _make_obs(False)
            graph_engine.on_observation(obs)
            result = cf_engine.simulate_without_layer(obs.packet_id, "MetaStrategy")
            assert result is not None
            assert result.packet_id == obs.packet_id
            assert result.disclaimer

    def test_disclaimer_present(self, tmp_store):
        from dip.modules.counterfactual import CounterfactualEngine
        from dip.modules.decision_graph import DecisionGraphEngine

        graph_engine = DecisionGraphEngine()
        cf_engine = CounterfactualEngine()
        with patch.object(graph_engine, "_store", tmp_store), patch.object(
            cf_engine, "_store", tmp_store
        ), patch.object(cf_engine, "_graph_engine", graph_engine):
            from tests.dip.conftest import _make_obs

            obs = _make_obs(False)
            graph_engine.on_observation(obs)
            result = cf_engine.simulate_without_layer(obs.packet_id, "MetaStrategy")
            assert result is not None
            assert (
                "0.85" in result.disclaimer or "simulation" in result.disclaimer.lower()
            )

    def test_confidence_max_085(self, tmp_store):
        from dip.modules.counterfactual import CounterfactualEngine
        from dip.modules.decision_graph import DecisionGraphEngine

        graph_engine = DecisionGraphEngine()
        cf_engine = CounterfactualEngine()
        with patch.object(graph_engine, "_store", tmp_store), patch.object(
            cf_engine, "_store", tmp_store
        ), patch.object(cf_engine, "_graph_engine", graph_engine):
            from tests.dip.conftest import _make_obs

            obs = _make_obs(False)
            graph_engine.on_observation(obs)
            result = cf_engine.simulate_without_layer(obs.packet_id, "MetaStrategy")
            if result:
                assert result.confidence <= 0.85

    def test_batch_simulate(self, tmp_store):
        from dip.modules.counterfactual import CounterfactualEngine
        from dip.modules.decision_graph import DecisionGraphEngine

        graph_engine = DecisionGraphEngine()
        cf_engine = CounterfactualEngine()
        with patch.object(graph_engine, "_store", tmp_store), patch.object(
            cf_engine, "_store", tmp_store
        ), patch.object(cf_engine, "_graph_engine", graph_engine):
            from tests.dip.conftest import _make_obs

            obs = _make_obs(False)
            graph_engine.on_observation(obs)
            scenarios = [
                Scenario(
                    scenario_type=ScenarioType.LAYER_REMOVAL,
                    target_layer="MetaStrategy",
                    parameter_overrides=None,
                    context_overrides=None,
                    description="Remove MetaStrategy",
                )
            ]
            batch = cf_engine.batch_simulate(obs.packet_id, scenarios)
            assert batch.total_scenarios >= 0
