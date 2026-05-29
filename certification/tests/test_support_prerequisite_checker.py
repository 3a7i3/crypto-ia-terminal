"""Tests G-01 — PrerequisiteChecker (12 tests)"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from certification.prerequisite_checker import (
    _F_IMPORTABLE,
    _PHASE_MODULES,
    PhaseCheck,
    PrerequisiteChecker,
    PrerequisiteReport,
)

ROOT = Path(__file__).parent.parent.parent


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def checker():
    return PrerequisiteChecker(root=ROOT)


# ── Tests module coverage ─────────────────────────────────────────────────────


def test_phase_modules_all_six_phases():
    assert set(_PHASE_MODULES.keys()) == {
        "P10-A",
        "P10-B",
        "P10-C",
        "P10-D",
        "P10-E",
        "P10-F",
    }


def test_each_phase_has_at_least_5_modules():
    for phase, modules in _PHASE_MODULES.items():
        assert len(modules) >= 5, f"{phase} has only {len(modules)} modules"


def test_f_importable_has_five_modules():
    assert len(_F_IMPORTABLE) == 5


# ── Tests check_phase_files ───────────────────────────────────────────────────


def test_phase_a_files_present(checker):
    result = checker.check_phase_files("P10-A")
    assert isinstance(result, PhaseCheck)
    assert result.phase == "P10-A"
    assert result.files_total == len(_PHASE_MODULES["P10-A"])


def test_phase_f_files_present(checker):
    result = checker.check_phase_files("P10-F")
    assert result.passed, f"Manquants P10-F : {result.missing}"


def test_phase_check_all_ok_when_no_missing(tmp_path):
    checker = PrerequisiteChecker(root=tmp_path)
    phase = "P10-A"
    for m in _PHASE_MODULES[phase]:
        p = tmp_path / m.replace("/", checker._root.__class__.__name__[:1])
        import os

        p_abs = tmp_path / m.replace("/", os.sep)
        p_abs.parent.mkdir(parents=True, exist_ok=True)
        p_abs.write_text("# stub")
    result = checker.check_phase_files(phase)
    assert result.files_ok == result.files_total
    assert result.passed


def test_phase_check_reports_missing(tmp_path):
    checker = PrerequisiteChecker(root=tmp_path)
    result = checker.check_phase_files("P10-A")
    assert not result.passed
    assert len(result.missing) == len(_PHASE_MODULES["P10-A"])


def test_unknown_phase_returns_empty_check(checker):
    result = checker.check_phase_files("P10-Z")
    assert result.files_total == 0
    assert result.passed  # nothing to verify


# ── Tests imports P10-F ───────────────────────────────────────────────────────


def test_f_imports_ok(checker):
    errors = checker.check_f_imports()
    assert errors == [], f"Import errors: {errors}"


def test_f_imports_returns_list_on_failure():
    checker = PrerequisiteChecker()
    with patch("importlib.import_module", side_effect=ImportError("missing")):
        errors = checker.check_f_imports()
    assert len(errors) == len(_F_IMPORTABLE)


# ── Tests run complet ─────────────────────────────────────────────────────────


def test_run_returns_prerequisite_report(checker):
    report = checker.run()
    assert isinstance(report, PrerequisiteReport)
    assert len(report.phase_checks) == 6


def test_run_all_phases_ok(checker):
    report = checker.run()
    assert report.all_phases_ok, report.summary()


def test_summary_contains_phase_labels(checker):
    report = checker.run()
    summary = report.summary()
    for phase in _PHASE_MODULES:
        assert phase in summary
