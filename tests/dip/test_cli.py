"""Tests CLI dip — vérification des sous-commandes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dip.cli import build_parser, main

# ── Parser ────────────────────────────────────────────────────────────────────


class TestParser:

    def test_graph_parses(self):
        parser = build_parser()
        args = parser.parse_args(["graph", "abc-123"])
        assert args.command == "graph"
        assert args.packet_id == "abc-123"

    def test_causal_parses(self):
        parser = build_parser()
        args = parser.parse_args(["causal", "abc-123"])
        assert args.command == "causal"

    def test_diff_parses(self):
        parser = build_parser()
        args = parser.parse_args(["diff", "id-a", "id-b"])
        assert args.packet_id_a == "id-a"
        assert args.packet_id_b == "id-b"

    def test_report_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["report"])
        assert args.hours == 168
        assert args.format == "md"
        assert args.output is None

    def test_replay_step_flag(self):
        parser = build_parser()
        args = parser.parse_args(["replay", "p1"])
        assert args.step is False
        args2 = parser.parse_args(["replay", "p1", "--step"])
        assert args2.step is True

    def test_alerts_severity_filter(self):
        parser = build_parser()
        args = parser.parse_args(["alerts", "--severity", "HIGH"])
        assert args.severity == "HIGH"

    def test_heatmap_type(self):
        parser = build_parser()
        args = parser.parse_args(["heatmap", "--type", "regime", "--hours", "48"])
        assert args.type == "regime"
        assert args.hours == 48

    def test_counterfactual_layer(self):
        parser = build_parser()
        args = parser.parse_args(["counterfactual", "p1", "--layer", "NoTradeLayer"])
        assert args.layer == "NoTradeLayer"

    def test_kb_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["kb"])
        assert args.symbol is None
        assert args.regime is None
        assert args.drift is False

    def test_metrics_default_hours(self):
        parser = build_parser()
        args = parser.parse_args(["metrics"])
        assert args.hours == 24


# ── cmd_graph ─────────────────────────────────────────────────────────────────


class TestCmdGraph:

    def test_returns_0_when_found(self, capsys):
        mock_graph = MagicMock()
        mock_graph.packet_id = "p1"
        mock_graph.status.value = "REJECTED"
        mock_graph.metrics.depth = 5
        mock_graph.metrics.confidence_start = 0.8
        mock_graph.metrics.confidence_end = 0.3
        mock_graph.metrics.rejection_layer = "meta_strategy"
        mock_graph.metrics.rejection_reason = "no meta allowed"
        node = MagicMock()
        node.layer = "meta_strategy"
        node.status.value = "BLOCKED"
        node.confidence_after = 0.3
        mock_graph.nodes = [node]
        mock_engine = MagicMock()
        mock_engine.get_graph.return_value = mock_graph

        with patch(
            "dip.modules.decision_graph.get_graph_engine", return_value=mock_engine
        ):
            rc = main(["graph", "p1"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "meta_strategy" in out

    def test_returns_1_when_not_found(self, capsys):
        mock_engine = MagicMock()
        mock_engine.get_graph.return_value = None
        with patch(
            "dip.modules.decision_graph.get_graph_engine", return_value=mock_engine
        ):
            rc = main(["graph", "nonexistent"])
        assert rc == 1


# ── cmd_alerts ────────────────────────────────────────────────────────────────


class TestCmdAlerts:

    def test_no_alerts(self, capsys):
        from dip.modules.decision_alert import AlertSummary

        mock_engine = MagicMock()
        mock_engine.get_active_alerts.return_value = []
        mock_engine.get_summary.return_value = AlertSummary(
            total_active=0,
            critical_count=0,
            warning_count=0,
            info_count=0,
            most_recent=None,
            top_severity="NONE",
        )
        with patch(
            "dip.modules.decision_alert.get_alert_engine", return_value=mock_engine
        ):
            rc = main(["alerts"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Aucune alerte" in out

    def test_invalid_severity_returns_1(self, capsys):
        with patch(
            "dip.modules.decision_alert.get_alert_engine", return_value=MagicMock()
        ):
            rc = main(["alerts", "--severity", "INVALID_XYZ"])
        assert rc == 1


# ── cmd_health ────────────────────────────────────────────────────────────────


class TestCmdHealth:

    def test_health_ok(self, capsys, tmp_store):
        from dip.core.store import DIPStore

        with patch.object(DIPStore, "instance", return_value=tmp_store):
            rc = main(["health"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "OK" in out


# ── cmd_metrics ───────────────────────────────────────────────────────────────


class TestCmdMetrics:

    def test_no_data(self, capsys, tmp_store):
        from dip.core.store import DIPStore

        with patch.object(DIPStore, "instance", return_value=tmp_store):
            rc = main(["metrics", "--hours", "24"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Aucune décision" in out

    def test_with_data(self, capsys, populated_store):
        from dip.core.store import DIPStore

        with patch.object(DIPStore, "instance", return_value=populated_store):
            rc = main(["metrics", "--hours", "9999"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Décisions" in out


# ── cmd_kb ────────────────────────────────────────────────────────────────────


class TestCmdKb:

    def test_kb_empty(self, capsys):
        from dip.modules.knowledge_base import KnowledgeSummary

        mock_kb = MagicMock()
        mock_kb.get_knowledge_summary.return_value = KnowledgeSummary(
            total_entries=0,
            total_rules=0,
            total_patterns=0,
            top_rejection_cause="N/A",
            top_rejection_regime="N/A",
            overall_approval_rate=0.0,
            computed_at_us=0,
        )
        mock_kb.query_patterns.return_value = []
        with patch(
            "dip.modules.knowledge_base.get_knowledge_base", return_value=mock_kb
        ):
            rc = main(["kb"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Knowledge Base" in out


# ── cmd_audit ────────────────────────────────────────────────────────────────


class TestCmdAudit:

    def test_audit_report(self, capsys, tmp_store):
        from dip.modules.audit_trail import DecisionAuditTrail, get_audit_trail

        trail = get_audit_trail()
        with patch.object(trail, "_store", tmp_store):
            rc = main(["audit", "--hours", "24"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Audit Trail" in out


# ── cmd_report ────────────────────────────────────────────────────────────────


class TestCmdReport:

    def test_report_markdown(self, capsys):
        from dip.modules.decision_export import ExportResult

        mock_engine = MagicMock()
        mock_engine.export_markdown.return_value = ExportResult(
            export_id="e1",
            format="md",
            filename="report.md",
            content="# Report\nOK",
            size_bytes=13,
            decision_count=5,
            created_at_us=0,
        )
        with patch(
            "dip.modules.decision_export.get_export_engine", return_value=mock_engine
        ):
            rc = main(["report", "--format", "md"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "# Report" in out

    def test_report_to_file(self, tmp_path, capsys):
        from dip.modules.decision_export import ExportResult

        out_path = str(tmp_path / "out.md")
        mock_engine = MagicMock()
        mock_engine.export_markdown.return_value = ExportResult(
            export_id="e1",
            format="md",
            filename="report.md",
            content="# Report",
            size_bytes=8,
            decision_count=3,
            created_at_us=0,
        )
        with patch(
            "dip.modules.decision_export.get_export_engine", return_value=mock_engine
        ):
            rc = main(["report", "--output", out_path])
        assert rc == 0
        assert "exporté" in capsys.readouterr().out
        with open(out_path) as f:
            assert "# Report" in f.read()
