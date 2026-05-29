"""Tests G-04 — FinalGate (10 tests)"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from certification.final_gate import FinalGate, FinalGateResult
from certification.operator_signoff import OperatorSignoff

# ── Helpers ───────────────────────────────────────────────────────────────────


def _good_tracker() -> MagicMock:
    t = MagicMock()
    t.snapshot.return_value = {
        "win_rate": 0.55,
        "sharpe_ratio": 1.5,
        "max_drawdown": 0.01,
        "total_trades": 30,
    }
    return t


def _bad_tracker() -> MagicMock:
    t = MagicMock()
    t.snapshot.return_value = {
        "win_rate": 0.25,
        "sharpe_ratio": 0.3,
        "max_drawdown": 0.10,
        "total_trades": 3,
    }
    return t


def _write_good_signoff(tmp_path: Path, phase: str = "F-01") -> None:
    sf = OperatorSignoff(phase=phase, operator="Test", signoff_dir=tmp_path)
    sf.sign_phase(
        kpi_ok=True,
        mode="TESTNET",
        shadow_days=10.0,
        paper_sharpe=1.3,
        paper_max_dd=0.04,
        paper_win_rate=0.56,
        killswitch_tested=True,
        risk_limits_loaded=True,
        failed_unresolved=0,
        comments="OK",
    )
    sf.save()


# ── Tests run ─────────────────────────────────────────────────────────────────


def test_run_returns_result(tmp_path):
    _write_good_signoff(tmp_path)
    gate = FinalGate(phase="F-01", kpi_tracker=_good_tracker(), cert_dir=tmp_path)
    result = gate.run()
    assert isinstance(result, FinalGateResult)
    assert result.phase == "F-01"


def test_go_when_all_conditions_met(tmp_path):
    _write_good_signoff(tmp_path)
    gate = FinalGate(phase="F-01", kpi_tracker=_good_tracker(), cert_dir=tmp_path)
    result = gate.run()
    assert result.prerequisite_ok
    assert result.kpi_ok
    assert result.signoff_ok
    assert result.signoff_approved
    assert result.go


def test_no_go_when_kpi_fail(tmp_path):
    _write_good_signoff(tmp_path)
    gate = FinalGate(phase="F-01", kpi_tracker=_bad_tracker(), cert_dir=tmp_path)
    result = gate.run()
    assert not result.kpi_ok
    assert not result.go


def test_no_go_when_no_signoff(tmp_path):
    gate = FinalGate(phase="F-01", kpi_tracker=_good_tracker(), cert_dir=tmp_path)
    result = gate.run()
    assert not result.signoff_ok
    assert not result.go


def test_summary_contains_go_or_nogo(tmp_path):
    _write_good_signoff(tmp_path)
    gate = FinalGate(phase="F-01", kpi_tracker=_good_tracker(), cert_dir=tmp_path)
    result = gate.run()
    summary = result.summary()
    assert "GO" in summary or "NO-GO" in summary


# ── Tests certificate ─────────────────────────────────────────────────────────


def test_save_certificate_when_go(tmp_path):
    _write_good_signoff(tmp_path)
    gate = FinalGate(phase="F-01", kpi_tracker=_good_tracker(), cert_dir=tmp_path)
    gate.run()
    cert_path = gate.save_certificate()
    assert cert_path.exists()
    assert "CERTIFIED_F-01" in cert_path.name


def test_verify_certificate_after_save(tmp_path):
    _write_good_signoff(tmp_path)
    gate = FinalGate(phase="F-01", kpi_tracker=_good_tracker(), cert_dir=tmp_path)
    gate.run()
    gate.save_certificate()
    assert gate.verify_certificate("F-01")


def test_save_certificate_raises_if_no_go(tmp_path):
    gate = FinalGate(phase="F-01", kpi_tracker=_bad_tracker(), cert_dir=tmp_path)
    gate.run()
    with pytest.raises(RuntimeError, match="NO-GO"):
        gate.save_certificate()


def test_verify_certificate_returns_false_if_tampered(tmp_path):
    import json

    _write_good_signoff(tmp_path)
    gate = FinalGate(phase="F-01", kpi_tracker=_good_tracker(), cert_dir=tmp_path)
    gate.run()
    cert_path = gate.save_certificate()
    data = json.loads(cert_path.read_text())
    data["operator"] = "hacker"
    cert_path.write_text(json.dumps(data))
    assert not gate.verify_certificate("F-01")


def test_verify_certificate_returns_false_if_no_file(tmp_path):
    gate = FinalGate(phase="F-01", cert_dir=tmp_path)
    assert not gate.verify_certificate("F-01")
