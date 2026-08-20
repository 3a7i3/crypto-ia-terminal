"""
tests/test_command_center_gate.py

Preuve que /gate rend le vrai GateResult (allowed + conditions 5-checks +
failed/warnings) au lieu de champs inexistants (level/size_factor…) qui
donnaient « GlobalRiskGate non disponible ».
"""

from __future__ import annotations

from capital_deployment.command_center_bot import (
    CommandDataProvider,
    _fmt_gate,
)


def _provider(gate_snap):
    return CommandDataProvider(get_gate=lambda: gate_snap)


def test_gate_unavailable_when_none():
    assert "non disponible" in _fmt_gate(_provider(None))


def test_gate_pass_renders_conditions():
    snap = {
        "allowed": True,
        "conditions": {"session": True, "drawdown": True, "score": True},
        "failed": [],
        "warnings": [],
        "symbol": "BTC/USDT",
    }
    out = _fmt_gate(_provider(snap))
    assert "PASS" in out
    assert "BTC/USDT" in out
    assert "3/3 OK" in out


def test_gate_block_lists_failed():
    snap = {
        "allowed": False,
        "conditions": {"session": True, "score": False},
        "failed": ["score"],
        "warnings": ["vol élevée"],
        "symbol": "ETH/USDT",
    }
    out = _fmt_gate(_provider(snap))
    assert "BLOCK" in out
    assert "score" in out
    assert "vol élevée" in out


def test_gate_accepts_dataclass_like_with_as_dict():
    class _FakeResult:
        def as_dict(self):
            return {
                "allowed": True,
                "conditions": {"a": True},
                "failed": [],
                "warnings": [],
            }

    out = _fmt_gate(_provider(_FakeResult()))
    assert "PASS" in out
    assert "1/1 OK" in out
