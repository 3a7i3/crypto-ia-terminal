"""
tests/dip/test_instrumentation_validation.py — Smoke tests pour INV-IV.

Verifie que chaque check IV-001..IV-010 passe en isolation.
Ces tests sont merge-blocking: si l'un echoue, le DIP n'est pas certifie.
"""

from __future__ import annotations

import pytest

from tools.instrumentation_validator import (
    CheckResult,
    check_iv001,
    check_iv002,
    check_iv003,
    check_iv004,
    check_iv005,
    check_iv006,
    check_iv007,
    check_iv008,
    check_iv009,
    check_iv010,
    run_suite,
    _certify,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _assert_pass(result: CheckResult) -> None:
    assert result.passed, (
        f"{result.check_id} [{result.name}] FAIL:\n{result.error or result.details}"
    )


# ── Individual checks ──────────────────────────────────────────────────────────


def test_iv001_packet_coverage():
    _assert_pass(check_iv001())


def test_iv002_rejection_events():
    _assert_pass(check_iv002())


def test_iv003_regret_parent_uniqueness():
    _assert_pass(check_iv003())


def test_iv004_graph_completeness():
    _assert_pass(check_iv004())


def test_iv005_timeline_coherence():
    _assert_pass(check_iv005())


def test_iv006_replay_fidelity():
    _assert_pass(check_iv006())


def test_iv007_counterfactual_reproducibility():
    _assert_pass(check_iv007())


def test_iv008_heatmap_coverage():
    _assert_pass(check_iv008())


def test_iv009_causal_acyclicity():
    _assert_pass(check_iv009())


def test_iv010_timestamp_monotonicity():
    _assert_pass(check_iv010())


# ── Suite entiere ──────────────────────────────────────────────────────────────


def test_full_suite_certified():
    """La suite complete doit produire le statut CERTIFIED_OBSERVER."""
    results = run_suite()
    cert = _certify(results)
    failed = [r for r in results if not r.passed]
    assert cert["status"] == "CERTIFIED_OBSERVER", (
        f"DIP non certifie: {cert['failed']}/10 checks en FAIL\n"
        + "\n".join(f"  {r.check_id}: {r.error or r.details}" for r in failed)
    )
