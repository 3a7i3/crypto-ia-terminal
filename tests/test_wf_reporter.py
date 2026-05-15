"""
tests/test_wf_reporter.py — Tests du reporter walk-forward (P3.4).
"""

from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path

import pytest

from metrics.oos_metrics import TradeResult, compute_oos_metrics
from metrics.stability_score import compute_stability_score
from monitor.degradation_tracker import DegradationTracker
from walk_forward.engine import WalkForwardEngine, WalkForwardResult
from walk_forward.reporter import WalkForwardReporter, build_alerts, build_section
from walk_forward.walk_forward_loop import WalkForwardLoop
from walk_forward.window_splitter import WindowSplitter

SEED = 42


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result() -> WalkForwardResult:
    rng = random.Random(SEED)
    data = [
        {"value": rng.gauss(0.2, 1.0), "regime": ["bull", "bear", "stable"][i % 3]}
        for i in range(1000)
    ]

    def opt(train):
        vals = [d["value"] for d in train]
        return {"thr": sum(vals) / len(vals)}

    def val(test, params):
        return [
            TradeResult(i * 1000, d["value"] * 0.05, regime=d["regime"])
            for i, d in enumerate(test)
            if abs(d["value"]) > abs(params["thr"])
        ]

    sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, step=100)
    loop = WalkForwardLoop(optimizer=opt, validator=val)
    engine = WalkForwardEngine(splitter=sp, loop=loop)
    return engine.run(data)


def _make_state(result: WalkForwardResult) -> dict:
    reporter = WalkForwardReporter()
    # appel interne sans ecrire sur disque
    return reporter._to_state(result)


# ---------------------------------------------------------------------------
# TestBuildAlerts
# ---------------------------------------------------------------------------


class TestBuildAlerts:

    def test_empty_state_no_alerts(self):
        assert build_alerts({}) == []

    def test_critical_degradation_event_produces_critical(self):
        state = {
            "degradation_events": [
                {
                    "severity": "critical",
                    "metric": "sharpe",
                    "message": "Sharpe en chute",
                    "detected_at_fold": 3,
                    "current_value": -1.0,
                    "baseline_value": 1.5,
                    "z_score": -3.0,
                    "trend_tau": -0.8,
                    "trend_p_value": 0.02,
                }
            ],
            "is_robust": False,
            "n_degradation_criticals": 1,
        }
        alerts = build_alerts(state)
        assert any(a["level"] == "CRITICAL" for a in alerts)

    def test_warning_degradation_produces_warning(self):
        state = {
            "degradation_events": [
                {
                    "severity": "warning",
                    "metric": "win_rate",
                    "message": "WR sous le seuil",
                    "detected_at_fold": 2,
                    "current_value": 0.32,
                    "baseline_value": 0.60,
                    "z_score": -1.8,
                    "trend_tau": 0.0,
                    "trend_p_value": 1.0,
                }
            ],
            "is_robust": True,
            "n_degradation_criticals": 0,
        }
        alerts = build_alerts(state)
        assert any(a["level"] == "WARNING" for a in alerts)

    def test_not_robust_without_events_gives_warning(self):
        state = {
            "degradation_events": [],
            "is_robust": False,
            "n_degradation_criticals": 0,
            "aggregate": {"sharpe_ratio": 0.2},
            "n_profitable_folds": 1,
            "n_folds": 4,
        }
        alerts = build_alerts(state)
        assert any(a["level"] == "WARNING" for a in alerts)

    def test_robust_no_events_no_alerts(self):
        state = {
            "degradation_events": [],
            "is_robust": True,
            "n_degradation_criticals": 0,
        }
        assert build_alerts(state) == []

    def test_alert_message_is_string(self):
        state = {
            "degradation_events": [
                {
                    "severity": "critical",
                    "metric": "sharpe",
                    "message": "test",
                    "detected_at_fold": 0,
                    "current_value": 0.0,
                    "baseline_value": 1.0,
                    "z_score": -3.0,
                    "trend_tau": 0.0,
                    "trend_p_value": 1.0,
                }
            ],
            "n_degradation_criticals": 1,
        }
        alerts = build_alerts(state)
        for a in alerts:
            assert isinstance(a["msg"], str)
            assert a["level"] in ("CRITICAL", "WARNING")


# ---------------------------------------------------------------------------
# TestBuildSection
# ---------------------------------------------------------------------------


class TestBuildSection:

    def test_empty_state_returns_placeholder(self):
        lines = build_section({})
        assert any("Aucune donnee" in l for l in lines)

    def test_section_starts_with_header(self):
        result = _make_result()
        state = _make_state(result)
        lines = build_section(state)
        assert lines[0] == "## Walk-Forward"

    def test_section_contains_sharpe(self):
        result = _make_result()
        state = _make_state(result)
        text = "\n".join(build_section(state))
        assert "Sharpe" in text

    def test_section_contains_fold_table(self):
        result = _make_result()
        state = _make_state(result)
        text = "\n".join(build_section(state))
        assert "Fold" in text
        assert "Train" in text

    def test_section_contains_robustesse(self):
        result = _make_result()
        state = _make_state(result)
        text = "\n".join(build_section(state))
        assert "Robustesse" in text

    def test_section_contains_stability(self):
        result = _make_result()
        state = _make_state(result)
        text = "\n".join(build_section(state))
        assert "stabilit" in text.lower() or "Stabilit" in text

    def test_section_is_list_of_strings(self):
        result = _make_result()
        state = _make_state(result)
        lines = build_section(state)
        assert isinstance(lines, list)
        for l in lines:
            assert isinstance(l, str)

    def test_section_no_degradation_events_no_alert_block(self):
        state = {
            "degradation_events": [],
            "is_robust": True,
            "n_folds": 4,
            "n_profitable_folds": 3,
            "profitable_fold_rate": 0.75,
            "mean_oos_sharpe": 1.2,
            "std_oos_sharpe": 0.3,
            "aggregate": {
                "sharpe_ratio": 1.1,
                "max_drawdown_pct": -4.0,
                "win_rate": 0.62,
                "profit_factor": 1.8,
            },
            "stability": {
                "stability_score": 0.75,
                "is_regime_stable": True,
                "sharpe_cv": 0.2,
                "min_regime_sharpe": 0.9,
                "max_regime_sharpe": 1.4,
                "worst_regime": "bear",
                "best_regime": "bull",
            },
            "fold_summaries": [],
            "generated_at": "2026-05-13T12:00:00",
        }
        text = "\n".join(build_section(state))
        assert "degradation" not in text.lower() or "Alertes" not in text


# ---------------------------------------------------------------------------
# TestWalkForwardReporter
# ---------------------------------------------------------------------------


class TestWalkForwardReporter:

    def test_save_state_creates_json(self):
        result = _make_result()
        with tempfile.TemporaryDirectory() as tmp:
            r = WalkForwardReporter(
                project_os_dir=Path(tmp) / "project_os",
                reports_dir=Path(tmp) / "reports",
            )
            path = r.save_state(result)
            assert path.exists()
            d = json.loads(path.read_text())
            assert "n_folds" in d
            assert "aggregate" in d
            assert "fold_summaries" in d
            assert "generated_at" in d

    def test_save_state_json_valid(self):
        result = _make_result()
        with tempfile.TemporaryDirectory() as tmp:
            r = WalkForwardReporter(project_os_dir=Path(tmp))
            path = r.save_state(result)
            d = json.loads(path.read_text())
            assert d["n_folds"] == result.n_folds

    def test_export_jsonl_creates_file(self):
        result = _make_result()
        with tempfile.TemporaryDirectory() as tmp:
            r = WalkForwardReporter(reports_dir=Path(tmp))
            path = r.export_jsonl(result)
            assert path.exists()
            lines = path.read_text().strip().split("\n")
            assert len(lines) == result.n_folds

    def test_export_jsonl_each_line_valid_json(self):
        result = _make_result()
        with tempfile.TemporaryDirectory() as tmp:
            r = WalkForwardReporter(reports_dir=Path(tmp))
            path = r.export_jsonl(result, tag="test")
            for line in path.read_text().strip().split("\n"):
                d = json.loads(line)
                assert "fold_index" in d
                assert "oos" in d

    def test_export_jsonl_tag_in_filename(self):
        result = _make_result()
        with tempfile.TemporaryDirectory() as tmp:
            r = WalkForwardReporter(reports_dir=Path(tmp))
            path = r.export_jsonl(result, tag="btc")
            assert "btc" in path.name

    def test_write_markdown_creates_file(self):
        result = _make_result()
        with tempfile.TemporaryDirectory() as tmp:
            r = WalkForwardReporter(reports_dir=Path(tmp))
            path = r.write_markdown(result)
            assert path.exists()
            content = path.read_text()
            assert "Walk-Forward" in content

    def test_write_markdown_contains_fold_table(self):
        result = _make_result()
        with tempfile.TemporaryDirectory() as tmp:
            r = WalkForwardReporter(reports_dir=Path(tmp))
            path = r.write_markdown(result)
            content = path.read_text()
            assert "Fold" in content

    def test_write_markdown_tag_in_filename(self):
        result = _make_result()
        with tempfile.TemporaryDirectory() as tmp:
            r = WalkForwardReporter(reports_dir=Path(tmp))
            path = r.write_markdown(result, tag="eth")
            assert "eth" in path.name

    def test_to_state_fold_summaries_count(self):
        result = _make_result()
        r = WalkForwardReporter()
        state = r._to_state(result)
        assert len(state["fold_summaries"]) == result.n_folds

    def test_to_state_degradation_events_serialized(self):
        result = _make_result()
        r = WalkForwardReporter()
        state = r._to_state(result)
        for ev in state["degradation_events"]:
            assert "severity" in ev
            assert "metric" in ev
            assert "message" in ev

    def test_to_state_overfitting_ratio_present(self):
        result = _make_result()
        r = WalkForwardReporter()
        state = r._to_state(result)
        for fold in state["fold_summaries"]:
            assert "overfitting_ratio" in fold

    def test_creates_parent_dirs(self):
        result = _make_result()
        with tempfile.TemporaryDirectory() as tmp:
            r = WalkForwardReporter(
                project_os_dir=Path(tmp) / "deep" / "project_os",
                reports_dir=Path(tmp) / "deep" / "reports",
            )
            r.save_state(result)
            r.export_jsonl(result)
            r.write_markdown(result)


# ---------------------------------------------------------------------------
# TestProjectOSIntegration
# ---------------------------------------------------------------------------


class TestProjectOSIntegration:

    def test_reporter_loads_wf_state(self):
        """project_os/reporter.py charge walk_forward_state.json si present."""
        result = _make_result()
        with tempfile.TemporaryDirectory() as tmp:
            pos_dir = Path(tmp) / "project_os"
            wf_reporter = WalkForwardReporter(
                project_os_dir=pos_dir,
                reports_dir=Path(tmp) / "reports",
            )
            wf_reporter.save_state(result)
            # Verifier que le fichier est lisible
            state_path = pos_dir / "walk_forward_state.json"
            assert state_path.exists()
            loaded = json.loads(state_path.read_text())
            assert loaded["n_folds"] == result.n_folds

    def test_build_alerts_compatible_format(self):
        """Les alertes retournees ont le bon format pour project_os/reporter.py."""
        state = {
            "degradation_events": [],
            "is_robust": False,
            "n_degradation_criticals": 0,
            "aggregate": {"sharpe_ratio": 0.1},
            "n_profitable_folds": 0,
            "n_folds": 4,
        }
        alerts = build_alerts(state)
        for a in alerts:
            assert "level" in a
            assert "msg" in a
            assert a["level"] in ("CRITICAL", "WARNING")

    def test_build_section_compatible_with_reporter_style(self):
        """La section retournee est une liste de str sans objets non-serialisables."""
        result = _make_result()
        r = WalkForwardReporter()
        state = r._to_state(result)
        lines = build_section(state)
        # Tout doit etre str, pas de None ou d'objets
        for line in lines:
            assert isinstance(line, str)
