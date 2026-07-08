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


class _FakeSummary:
    def __init__(self, n_open: int, unrealized_pnl_usd: float):
        self.n_open = n_open
        self.unrealized_pnl_usd = unrealized_pnl_usd


class _FakeVirtualPortfolio:
    def __init__(self, n_open: int, unrealized_pnl_usd: float):
        self._summary = _FakeSummary(n_open, unrealized_pnl_usd)

    def get_open_positions_summary(self):
        return self._summary


class _BrokenVirtualPortfolio:
    def get_open_positions_summary(self):
        raise RuntimeError("boom")


def test_display_position_summary_prefers_virtual_portfolio_over_pos_manager():
    """Régression Pos: 0 menteur (RECOVERY.md 2026-07-05) : quand le simulateur
    est disponible, il prime sur pb_health (issu de pos_manager) pour
    l'affichage — même si pb_health prétend 0 position."""
    pb_health = {"n_positions": 0, "open_pnl_usd": 0.0}
    vp = _FakeVirtualPortfolio(n_open=2, unrealized_pnl_usd=-3.72)

    n_open, pnl = advisor_loop._display_position_summary(vp, pb_health)

    assert n_open == 2
    assert pnl == -3.72


def test_display_position_summary_falls_back_when_no_virtual_portfolio():
    pb_health = {"n_positions": 1, "open_pnl_usd": 0.42}

    n_open, pnl = advisor_loop._display_position_summary(None, pb_health)

    assert n_open == 1
    assert pnl == 0.42


def test_display_position_summary_falls_back_on_exception():
    pb_health = {"n_positions": 3, "open_pnl_usd": -1.0}

    n_open, pnl = advisor_loop._display_position_summary(
        _BrokenVirtualPortfolio(), pb_health
    )

    assert n_open == 3
    assert pnl == -1.0


class _FakeKpiTracker:
    def __init__(self, total_trades: int, win_rate: float = 0.5):
        self._total_trades = total_trades
        self._win_rate = win_rate

    def snapshot(self):
        from capital_deployment.phase_kpi_tracker import KPISnapshot

        return KPISnapshot(
            phase="F-01",
            win_rate=self._win_rate,
            sharpe=1.0,
            max_drawdown=0.01,
            current_drawdown=0.0,
            total_trades=self._total_trades,
            unsigned_decisions=0,
            days_elapsed=1.0,
        )


def test_kpi_snapshot_returns_none_when_no_tracker():
    assert advisor_loop._kpi_snapshot_with_canonical_n(None) is None


def test_kpi_snapshot_overrides_total_trades_with_canonical_n(monkeypatch):
    """Régression 'Trades: 0' perpétuel : PhaseKPITracker n'est jamais
    alimenté (même divergence pos_manager/MexcSimulator que P2), le compte
    affiché doit venir du dataset canonique, pas du tracker vide."""
    import tools.cri_calculator as cri_calculator

    monkeypatch.setattr(
        cri_calculator, "load_clean_trades", lambda: [{"event": "CLOSE"}] * 24
    )

    tracker = _FakeKpiTracker(total_trades=0)  # jamais alimenté — reproduit le bug
    snap = advisor_loop._kpi_snapshot_with_canonical_n(tracker)

    assert snap.total_trades == 24  # N canonique, pas les 0 du tracker
    assert snap.win_rate == 0.5  # le reste du snapshot (win_rate/sharpe) inchangé
