"""Tests D09 (Knowledge Base) + D13 (Export)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from dip.core.types import TimeRange, now_us
from dip.modules.decision_export import (
    CSVExporter,
    DecisionExportEngine,
    ExportOptions,
    JSONExporter,
    MarkdownExporter,
    ReportBuilder,
)
from dip.modules.knowledge_base import (
    DecisionKnowledgeBase,
    DriftDetector,
    KnowledgeExtractor,
)
from tests.dip.conftest import _insert_decision, _make_obs

# ── Knowledge Base ─────────────────────────────────────────────────────────────


class TestKnowledgeExtractor:

    def test_compute_patterns_insufficient_data(self, tmp_store):
        extractor = KnowledgeExtractor(tmp_store)
        # Moins de 50 obs → aucun pattern
        for _ in range(10):
            _insert_decision(tmp_store, symbol="BTCUSDT", status="REJECTED")
        patterns = extractor.compute_patterns()
        assert patterns == []

    def test_compute_patterns_sufficient_data(self, tmp_store):
        extractor = KnowledgeExtractor(tmp_store)
        for _ in range(60):
            _insert_decision(
                tmp_store,
                symbol="BTCUSDT",
                status="REJECTED",
                root_cause_layer="NoTradeLayer",
            )
        patterns = extractor.compute_patterns()
        # 60 rejets sur même (symbol, layer) → pattern attendu
        assert len(patterns) >= 1
        assert patterns[0].sample_size >= 50

    def test_compute_rules_insufficient_data(self, tmp_store):
        extractor = KnowledgeExtractor(tmp_store)
        rules = extractor.compute_rules()
        assert rules == []


class TestDriftDetector:

    def test_no_drift_empty_data(self, tmp_store):
        detector = DriftDetector(tmp_store)
        report = detector.detect("rejection_rate", window_hours=1)
        assert report.metric == "rejection_rate"
        assert not report.drift_detected

    def test_severity_ok_on_empty(self, tmp_store):
        detector = DriftDetector(tmp_store)
        report = detector.detect("rejection_rate")
        assert report.severity == "OK"


class TestDecisionKnowledgeBase:

    def test_on_observation_doesnt_crash(self, tmp_store):
        kb = DecisionKnowledgeBase()
        with patch.object(kb, "_store", tmp_store):
            obs = _make_obs(False)
            kb.on_observation(obs)  # Ne doit pas lever d'exception

    def test_query_patterns_empty(self, tmp_store):
        kb = DecisionKnowledgeBase()
        with patch.object(kb, "_store", tmp_store):
            patterns = kb.query_patterns(symbol="BTCUSDT")
            assert patterns == []

    def test_get_knowledge_summary(self, populated_store):
        kb = DecisionKnowledgeBase()
        with patch.object(kb, "_store", populated_store):
            summary = kb.get_knowledge_summary()
            assert 0.0 <= summary.overall_approval_rate <= 1.0
            assert summary.computed_at_us > 0

    def test_detect_drift(self, tmp_store):
        kb = DecisionKnowledgeBase()
        with patch.object(kb, "_store", tmp_store):
            report = kb.detect_drift("rejection_rate")
            assert report.metric == "rejection_rate"


# ── Export ─────────────────────────────────────────────────────────────────────


class TestJSONExporter:

    def test_exports_valid_json(self, populated_store):
        rows = populated_store.get_decisions(limit=10)
        content = JSONExporter.export(rows, ExportOptions())
        import json

        data = json.loads(content)
        assert data["decision_count"] == 10
        assert len(data["decisions"]) == 10

    def test_empty_rows(self):
        content = JSONExporter.export([], ExportOptions())
        import json

        data = json.loads(content)
        assert data["decision_count"] == 0


class TestCSVExporter:

    def test_exports_csv_with_header(self, populated_store):
        rows = populated_store.get_decisions(limit=5)
        content = CSVExporter.export(rows)
        lines = content.strip().split("\n")
        assert lines[0].startswith("packet_id")
        assert len(lines) == 6  # header + 5 rows

    def test_empty_produces_header(self):
        content = CSVExporter.export([])
        lines = [l for l in content.strip().split("\n") if l]
        assert len(lines) == 1  # juste le header


class TestReportBuilder:

    def test_build_report(self, populated_store):
        builder = ReportBuilder(populated_store)
        tr = TimeRange.last_hours(168)
        report = builder.build(tr, ExportOptions())
        assert report.decision_count == 10
        assert 0.0 <= report.approval_rate <= 1.0
        assert len(report.sections) > 0

    def test_top_rejection_layer(self, populated_store):
        builder = ReportBuilder(populated_store)
        tr = TimeRange.last_hours(168)
        report = builder.build(tr, ExportOptions())
        assert report.top_rejection_layer == "NoTradeLayer"


class TestDecisionExportEngine:

    def test_export_json(self, populated_store):
        engine = DecisionExportEngine()
        with patch.object(engine, "_store", populated_store), patch.object(
            engine._report_builder, "_store", populated_store
        ):
            result = engine.export_json(hours=168)
            assert result.format == "json"
            assert result.decision_count == 10
            assert result.size_bytes > 0

    def test_export_csv(self, populated_store):
        engine = DecisionExportEngine()
        with patch.object(engine, "_store", populated_store):
            result = engine.export_csv(hours=168)
            assert result.format == "csv"
            assert "packet_id" in result.content

    def test_export_markdown(self, populated_store):
        engine = DecisionExportEngine()
        with patch.object(engine, "_store", populated_store), patch.object(
            engine._report_builder, "_store", populated_store
        ):
            result = engine.export_markdown(hours=168)
            assert result.format == "markdown"
            assert "# Rapport DIP" in result.content

    def test_export_packet_not_found(self, tmp_store):
        engine = DecisionExportEngine()
        with patch.object(engine, "_store", tmp_store):
            result = engine.export_packet("nonexistent_id")
            assert "error" in result.content.lower() or result.decision_count == 0
