"""
tests/dip/test_live_observer_validation.py -- Merge-blocking tests for INV-IV-LIVE.

Verifies that each IV-LIVE-001..010 check passes in synthetic mode.
ALL tests must pass before activating FEATURE_DIP=true on the VPS.

Reference: docs/dip/observer_certification_standard_v1.md
ADR-0007: checks are passive/read-only, no modification of the engine.
"""
from __future__ import annotations

import json

import pytest

from tools.live_observer_validator import (
    LiveCheckResult,
    certify,
    check_iv_live_001,
    check_iv_live_002,
    check_iv_live_003,
    check_iv_live_004,
    check_iv_live_005,
    check_iv_live_006,
    check_iv_live_007,
    check_iv_live_008,
    check_iv_live_009,
    check_iv_live_010,
    load_history,
    run_suite,
    save_history,
)


# ── Helper ─────────────────────────────────────────────────────────────────────


def _assert_pass(result: LiveCheckResult) -> None:
    assert not result.skipped, (
        f"{result.check_id} [{result.name}] skipped unexpectedly in synthetic mode:\n"
        f"  skip_reason: {result.skip_reason}"
    )
    assert result.passed, (
        f"{result.check_id} [{result.name}] FAIL:\n"
        f"  details: {result.details}\n"
        f"  error:   {result.error}"
    )


# ── Individual checks ──────────────────────────────────────────────────────────


def test_iv_live_001_coverage_validation():
    _assert_pass(check_iv_live_001(live_mode=False))


def test_iv_live_002_rejection_completeness():
    _assert_pass(check_iv_live_002(live_mode=False))


def test_iv_live_003_lifecycle_completeness():
    _assert_pass(check_iv_live_003(live_mode=False))


def test_iv_live_004_parent_integrity():
    _assert_pass(check_iv_live_004(live_mode=False))


def test_iv_live_005_timestamp_integrity():
    _assert_pass(check_iv_live_005(live_mode=False))


def test_iv_live_006_decision_id_integrity():
    _assert_pass(check_iv_live_006(live_mode=False))


def test_iv_live_007_memory_stability():
    _assert_pass(check_iv_live_007())


def test_iv_live_008_replay_fidelity():
    _assert_pass(check_iv_live_008(live_mode=False))


def test_iv_live_009_reporting_consistency():
    _assert_pass(check_iv_live_009())


def test_iv_live_010_root_cause_integrity():
    _assert_pass(check_iv_live_010(live_mode=False))


# ── Suite and certification ────────────────────────────────────────────────────


def test_full_suite_level2():
    """Full synthetic suite must achieve Level 2 (Certified Instrumentation)."""
    results = run_suite(live_mode=False)
    cert = certify(results, iv_all_pass=True, live_mode=False)

    failed = [r for r in results if not r.passed and not r.skipped]
    skipped = [r for r in results if r.skipped]

    assert cert["level"] >= 2, (
        f"DIP n'atteint pas Level 2:\n"
        f"  level={cert['level']}  III={cert['iii']}  decision={cert['decision']}\n"
        f"  FAIL: {[r.check_id for r in failed]}\n"
        f"  SKIP: {[r.check_id for r in skipped]}"
    )
    assert cert["iii"] >= 95.0, (
        f"III={cert['iii']:.1f} < 95.0 requis pour Level 2\n"
        f"  sub_scores: {cert['sub_scores']}"
    )


def test_iii_above_threshold():
    """III must be >= 95 in synthetic mode."""
    results = run_suite(live_mode=False)
    cert = certify(results, iv_all_pass=True, live_mode=False)
    assert cert["iii"] >= 95.0, f"III={cert['iii']:.1f} < 95"


def test_no_critical_fail():
    """Coverage, Replay, and RootCause checks must PASS."""
    critical_ids = {"IV-LIVE-001", "IV-LIVE-008", "IV-LIVE-010"}
    results = run_suite(live_mode=False)
    critical_failed = [r for r in results if r.check_id in critical_ids and not r.passed and not r.skipped]
    assert not critical_failed, (
        f"Check(s) critique(s) en FAIL: {[r.check_id for r in critical_failed]}\n"
        + "\n".join(f"  {r.check_id}: {r.details}" for r in critical_failed)
    )


def test_no_unexpected_skip():
    """No check should SKIP in synthetic mode (live_mode=False)."""
    results = run_suite(live_mode=False)
    skipped = [r for r in results if r.skipped]
    assert not skipped, (
        f"Check(s) ignores en mode synthetique: {[r.check_id for r in skipped]}\n"
        + "\n".join(f"  {r.check_id}: {r.skip_reason}" for r in skipped)
    )


# ── Score integrity ────────────────────────────────────────────────────────────


def test_scores_in_range():
    """All check scores must be in [0, 100]."""
    results = run_suite(live_mode=False)
    out_of_range = [r for r in results if not (0.0 <= r.score <= 100.0)]
    assert not out_of_range, (
        f"Scores hors [0,100]: " + ", ".join(f"{r.check_id}={r.score}" for r in out_of_range)
    )


def test_certify_with_all_fail():
    """certify() with iv_all_pass=False must return level 0."""
    results = run_suite(live_mode=False)
    cert = certify(results, iv_all_pass=False, live_mode=False)
    assert cert["level"] == 0, f"Expected level 0, got {cert['level']}"
    assert "NOT_CERTIFIED" in cert["level_name"]


# ── History ────────────────────────────────────────────────────────────────────


def test_history_roundtrip(tmp_path, monkeypatch):
    """save_history + load_history produces valid append-only records."""
    import tools.live_observer_validator as mod
    monkeypatch.setattr(mod, "CERT_HISTORY_PATH", tmp_path / "cert.jsonl")

    results = run_suite(live_mode=False)
    cert = certify(results, iv_all_pass=True, live_mode=False)

    save_history(results, cert)
    save_history(results, cert)  # two entries

    history = load_history()
    assert len(history) == 2, f"Expected 2 entries, got {len(history)}"

    entry = history[0]
    assert "certification_id" in entry
    assert entry["level"] >= 2
    assert entry["iii"] >= 95.0
    assert not entry["revoked"]
    assert len(entry["checks"]) == 10

    # Second entry should have seq incremented
    assert history[1]["certification_id"] != history[0]["certification_id"]
