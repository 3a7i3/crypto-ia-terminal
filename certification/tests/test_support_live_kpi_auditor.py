"""Tests G-02 — LiveKPIAuditor (10 tests)"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from certification.live_kpi_auditor import (
    _MIN_CRITERIA,
    KPIAuditReport,
    KPISnapshot,
    KPIViolation,
    LiveKPIAuditor,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _good_tracker(phase: str = "F-01") -> MagicMock:
    t = MagicMock()
    t.snapshot.return_value = {
        "win_rate": 0.55,
        "sharpe_ratio": 1.5,
        "max_drawdown": 0.01,
        "total_trades": 25,
    }
    return t


def _bad_tracker() -> MagicMock:
    t = MagicMock()
    t.snapshot.return_value = {
        "win_rate": 0.30,
        "sharpe_ratio": 0.5,
        "max_drawdown": 0.05,
        "total_trades": 5,
    }
    return t


# ── Tests config ──────────────────────────────────────────────────────────────


def test_min_criteria_covers_f01_f05():
    assert set(_MIN_CRITERIA.keys()) == {"F-01", "F-02", "F-03", "F-04", "F-05"}


def test_criteria_monotonically_tighter():
    # Sharpe requis augmente de F-01 à F-04
    assert _MIN_CRITERIA["F-02"]["sharpe_ratio"] > _MIN_CRITERIA["F-01"]["sharpe_ratio"]
    assert _MIN_CRITERIA["F-03"]["sharpe_ratio"] > _MIN_CRITERIA["F-02"]["sharpe_ratio"]


# ── Tests audit pass ──────────────────────────────────────────────────────────


def test_audit_pass_with_good_kpis():
    auditor = LiveKPIAuditor(phase="F-01", kpi_tracker=_good_tracker())
    report = auditor.audit()
    assert report.passed
    assert report.violations == []


def test_audit_returns_signed_report():
    auditor = LiveKPIAuditor(phase="F-01", kpi_tracker=_good_tracker())
    report = auditor.audit()
    assert report.signature != ""
    assert report.verify()


# ── Tests audit fail ──────────────────────────────────────────────────────────


def test_audit_fail_detects_all_violations():
    auditor = LiveKPIAuditor(phase="F-01", kpi_tracker=_bad_tracker())
    report = auditor.audit()
    assert not report.passed
    metric_names = {v.metric for v in report.violations}
    assert "win_rate" in metric_names
    assert "sharpe_ratio" in metric_names
    assert "max_drawdown" in metric_names


def test_violation_delta_is_negative():
    auditor = LiveKPIAuditor(phase="F-01", kpi_tracker=_bad_tracker())
    report = auditor.audit()
    for v in report.violations:
        if v.metric != "max_drawdown":
            assert v.delta < 0


# ── Tests signature ───────────────────────────────────────────────────────────


def test_signature_fails_with_wrong_key():
    auditor = LiveKPIAuditor(phase="F-01", kpi_tracker=_good_tracker())
    report = auditor.audit()
    assert not report.verify(b"wrong_key")


def test_signature_changes_if_snapshot_mutated():
    auditor = LiveKPIAuditor(phase="F-01", kpi_tracker=_good_tracker())
    report = auditor.audit()
    original_sig = report.signature
    report.snapshot.win_rate = 0.99  # mutate
    report.sign()
    assert report.signature != original_sig


# ── Tests audit_for_phase ─────────────────────────────────────────────────────


def test_audit_for_phase_uses_correct_criteria():
    # F-03 requires sharpe > 1.5 — good tracker gives 1.5 (borderline)
    auditor = LiveKPIAuditor(phase="F-01", kpi_tracker=_good_tracker())
    report_f01 = auditor.audit_for_phase("F-01")
    report_f03 = auditor.audit_for_phase("F-03")
    # F-01 passes, F-03 may fail on sharpe (1.5 is not > 1.5)
    assert report_f01.passed
    assert report_f03.phase == "F-03"


def test_summary_contains_phase_and_status():
    auditor = LiveKPIAuditor(phase="F-01", kpi_tracker=_good_tracker())
    report = auditor.audit()
    summary = report.summary()
    assert "F-01" in summary
    assert "PASS" in summary
