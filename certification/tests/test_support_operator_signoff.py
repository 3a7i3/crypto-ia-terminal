"""Tests G-03 — OperatorSignoff (11 tests)"""

from __future__ import annotations

import json

import pytest

from certification.operator_signoff import (
    OperatingMode,
    OperatorSignoff,
    SignoffDecision,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _good_kwargs() -> dict:
    return dict(
        kpi_ok=True,
        mode="TESTNET",
        shadow_days=8.0,
        paper_sharpe=1.2,
        paper_max_dd=0.05,
        paper_win_rate=0.55,
        killswitch_tested=True,
        risk_limits_loaded=True,
        failed_unresolved=0,
        comments="F-01 validé",
    )


# ── Tests sign_phase ──────────────────────────────────────────────────────────


def test_sign_phase_returns_decision():
    sf = OperatorSignoff(phase="F-01", operator="Test")
    d = sf.sign_phase(**_good_kwargs())
    assert isinstance(d, SignoffDecision)
    assert d.phase == "F-01"
    assert d.operator == "Test"


def test_sign_phase_sets_signature():
    sf = OperatorSignoff(phase="F-01", operator="Test")
    d = sf.sign_phase(**_good_kwargs())
    assert d.signature != ""
    assert d.verify()


def test_sign_phase_approved_when_all_ok():
    sf = OperatorSignoff(phase="F-01", operator="Test")
    d = sf.sign_phase(**_good_kwargs())
    assert d.approved


def test_sign_phase_not_approved_when_violations():
    sf = OperatorSignoff(phase="F-01", operator="Test")
    bad = _good_kwargs()
    bad["shadow_days"] = 2.0  # < 7 requis
    bad["paper_sharpe"] = 0.5  # < 0.8 requis
    d = sf.sign_phase(**bad)
    assert not d.approved
    assert len(d.operational_violations) >= 2


def test_operating_mode_unknown_for_invalid_string():
    sf = OperatorSignoff(phase="F-01", operator="Test")
    d = sf.sign_phase(**{**_good_kwargs(), "mode": "INVALID"})
    assert d.mode == OperatingMode.UNKNOWN


# ── Tests save / load ─────────────────────────────────────────────────────────


def test_save_and_load_roundtrip(tmp_path):
    sf = OperatorSignoff(phase="F-01", operator="Test", signoff_dir=tmp_path)
    sf.sign_phase(**_good_kwargs())
    path = sf.save()
    assert path.exists()

    sf2 = OperatorSignoff(phase="F-01", operator="Test", signoff_dir=tmp_path)
    d = sf2.load()
    assert d.phase == "F-01"
    assert d.operator == "Test"
    assert d.approved


def test_load_raises_if_not_saved(tmp_path):
    sf = OperatorSignoff(phase="F-02", operator="Test", signoff_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        sf.load()


def test_is_signed_true_after_save(tmp_path):
    sf = OperatorSignoff(phase="F-01", operator="Test", signoff_dir=tmp_path)
    sf.sign_phase(**_good_kwargs())
    sf.save()
    assert sf.is_signed()


def test_is_signed_false_if_no_file(tmp_path):
    sf = OperatorSignoff(phase="F-03", operator="Test", signoff_dir=tmp_path)
    assert not sf.is_signed()


# ── Tests signature intégrité ─────────────────────────────────────────────────


def test_signature_invalid_after_tampering(tmp_path):
    sf = OperatorSignoff(phase="F-01", operator="Test", signoff_dir=tmp_path)
    sf.sign_phase(**_good_kwargs())
    path = sf.save()

    # Tampering
    data = json.loads(path.read_text())
    data["kpi_ok"] = False
    path.write_text(json.dumps(data))

    sf2 = OperatorSignoff(phase="F-01", operator="Test", signoff_dir=tmp_path)
    assert not sf2.is_signed()


def test_from_dict_roundtrip():
    sf = OperatorSignoff(phase="F-01", operator="Test")
    d = sf.sign_phase(**_good_kwargs())
    d2 = SignoffDecision.from_dict(d.to_dict())
    assert d2.verify()
    assert d2.phase == d.phase
    assert d2.operator == d.operator
