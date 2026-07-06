from types import SimpleNamespace

from core import advisor_loop


def _result(
    *,
    score: int = 50,
    actionable: bool = False,
    gate_allowed: bool = False,
    trade_allowed: bool = False,
    meta_allowed: bool = True,
):
    return {
        "signal": SimpleNamespace(score=score, actionable=actionable),
        "gate": SimpleNamespace(allowed=gate_allowed),
        "trade_allowed": trade_allowed,
        "meta_allowed": meta_allowed,
    }


def test_decision_engine_wait_when_no_actionable():
    state, reason = advisor_loop._decision_engine_summary(
        [_result(score=40, actionable=False, gate_allowed=False, trade_allowed=False)]
    )
    assert state == "WAIT"
    assert "No setup" in reason


def test_decision_engine_active_when_tradable_exists():
    state, reason = advisor_loop._decision_engine_summary(
        [_result(score=80, actionable=True, gate_allowed=True, trade_allowed=True)]
    )
    assert state == "ACTIVE"
    assert "tradable" in reason


def test_decision_engine_blocked_reports_reason():
    state, reason = advisor_loop._decision_engine_summary(
        [_result(score=78, actionable=True, gate_allowed=False, trade_allowed=False)]
    )
    assert state == "BLOCKED"
    assert reason.startswith("gate")


def test_brain_score_builds_bar():
    pct, bar = advisor_loop._brain_score(
        [
            _result(score=80, actionable=True, gate_allowed=True, trade_allowed=True),
            _result(score=60, actionable=True, gate_allowed=True, trade_allowed=False),
        ]
    )
    assert pct == 70
    assert bar == "███████░░░"
