"""Tests D05 (Heatmap) + D06 (Sankey)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from dip.core.types import HeatmapType, SankeyNodeType, TimeRange, now_us
from dip.modules.decision_heatmap import DecisionHeatmapEngine, HeatmapBuilder
from dip.modules.decision_sankey import DecisionSankeyEngine, SankeyBuilder
from tests.dip.conftest import _insert_decision


class TestHeatmapBuilder:

    def _make_rows(self):
        rows = []
        for _ in range(15):
            rows.append(
                {
                    "symbol": "BTCUSDT",
                    "regime": "SIDEWAYS",
                    "status": "REJECTED",
                    "root_cause_layer": "NoTradeLayer",
                }
            )
        for _ in range(5):
            rows.append(
                {
                    "symbol": "ETHUSDT",
                    "regime": "TRENDING_UP",
                    "status": "APPROVED",
                    "root_cause_layer": None,
                }
            )
        return rows

    def test_symbol_layer_matrix_nonempty(self):
        tr = TimeRange.last_hours(168)
        matrix = HeatmapBuilder.build_symbol_layer(self._make_rows(), tr)
        assert matrix is not None
        assert len(matrix.cells) > 0

    def test_regime_layer_matrix_nonempty(self):
        tr = TimeRange.last_hours(168)
        matrix = HeatmapBuilder.build_regime_layer(self._make_rows(), tr)
        assert matrix is not None

    def test_hot_spot_detected(self):
        # 15 rejets sur NoTradeLayer pour BTCUSDT → hot spot
        tr = TimeRange.last_hours(168)
        matrix = HeatmapBuilder.build_symbol_layer(self._make_rows(), tr)
        hot_spots = [c for c in matrix.cells if c.is_hot_spot]
        assert len(hot_spots) > 0

    def test_cell_value_in_range(self):
        tr = TimeRange.last_hours(168)
        matrix = HeatmapBuilder.build_symbol_layer(self._make_rows(), tr)
        for cell in matrix.cells:
            assert 0.0 <= cell.value <= 1.0

    def test_empty_rows(self):
        tr = TimeRange.last_hours(24)
        matrix = HeatmapBuilder.build_symbol_layer([], tr)
        assert matrix.total_decisions == 0


class TestSankeyBuilder:

    def _make_rows(self):
        rows = []
        for _ in range(10):
            rows.append({"status": "REJECTED", "root_cause_layer": "NoTradeLayer"})
        for _ in range(5):
            rows.append({"status": "APPROVED", "root_cause_layer": None})
        return rows

    def test_sankey_nonempty(self):
        tr = TimeRange.last_hours(24)
        diagram = SankeyBuilder.build(self._make_rows(), tr)
        assert diagram.total_packets == 15
        assert len(diagram.nodes) > 0
        assert len(diagram.flows) > 0

    def test_bottleneck_detected(self):
        tr = TimeRange.last_hours(24)
        diagram = SankeyBuilder.build(self._make_rows(), tr)
        assert diagram.funnel.biggest_bottleneck == "NoTradeLayer"

    def test_overall_conversion(self):
        tr = TimeRange.last_hours(24)
        diagram = SankeyBuilder.build(self._make_rows(), tr)
        assert abs(diagram.funnel.overall_conversion - 5 / 15) < 0.01

    def test_empty_diagram(self):
        tr = TimeRange.last_hours(24)
        diagram = SankeyBuilder.build([], tr)
        assert diagram.total_packets == 0

    def test_source_node_exists(self):
        tr = TimeRange.last_hours(24)
        diagram = SankeyBuilder.build(self._make_rows(), tr)
        sources = [n for n in diagram.nodes if n.node_type == SankeyNodeType.SOURCE]
        assert len(sources) == 1


class TestHeatmapEngine:

    def test_generate_symbol_layer(self, populated_store):
        engine = DecisionHeatmapEngine()
        with patch.object(engine, "_store", populated_store):
            matrix = engine.generate_symbol_layer_heatmap(hours=168)
            assert matrix.heatmap_type == HeatmapType.SYMBOL_LAYER


class TestSankeyEngine:

    def test_generate_sankey(self, populated_store):
        engine = DecisionSankeyEngine()
        with patch.object(engine, "_store", populated_store):
            diagram = engine.generate_sankey(hours=168)
            assert diagram.total_packets == 10

    def test_get_funnel(self, populated_store):
        engine = DecisionSankeyEngine()
        with patch.object(engine, "_store", populated_store):
            funnel = engine.get_funnel_metrics(hours=168)
            assert 0.0 <= funnel.overall_conversion <= 1.0
