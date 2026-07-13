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


def _clean_close(ts: float, pnl_usd: float) -> dict:
    return {
        "event": "CLOSE",
        "ts": ts,
        "pnl_usd": pnl_usd,
        "symbol": "BTC/USDT",
        "side": "buy",
        "exit_price": 100.0,
    }


def test_kpi_snapshot_recomputes_from_canonical_dataset(monkeypatch):
    """Régression 'Trades: 27 | Win Rate: 0%' (réconciliation 2026-07-12) :
    PhaseKPITracker n'est jamais alimenté (divergence pos_manager/MexcSim),
    donc compte ET win rate affichés doivent venir du dataset canonique —
    pas d'un tracker vide qui prétend 0%."""
    import tools.cri_calculator as cri_calculator

    base_ts = 1_783_000_000.0
    trades = [
        _clean_close(base_ts + i * 3600.0, 1.0 if i < 9 else -1.0) for i in range(27)
    ]
    monkeypatch.setattr(cri_calculator, "load_clean_trades", lambda: trades)
    monkeypatch.setattr(advisor_loop, "_replay_base_capital", lambda: 100.0)

    tracker = _FakeKpiTracker(total_trades=0)  # jamais alimenté — reproduit le bug
    snap = advisor_loop._kpi_snapshot_with_canonical_n(tracker)

    assert snap.total_trades == 27  # N canonique, pas les 0 du tracker
    assert abs(snap.win_rate - 9 / 27) < 1e-9  # 9W/18L du dataset, pas le tracker
    assert snap.days_elapsed == 1.0  # champs hors-dataset conservés du tracker réel
    assert snap.phase == "F-01"


def test_kpi_snapshot_empty_dataset_shows_zero_trades(monkeypatch):
    import tools.cri_calculator as cri_calculator

    monkeypatch.setattr(cri_calculator, "load_clean_trades", lambda: [])

    snap = advisor_loop._kpi_snapshot_with_canonical_n(_FakeKpiTracker(total_trades=5))

    assert snap.total_trades == 0


def test_replay_clean_trades_kpis_drawdown_on_given_base():
    """Le drawdown rejoué est une fraction de la base fournie (wallet paper),
    jamais des $10 F-01 ni du solde API — confusion des 3 échelles de capital."""
    base_ts = 1_783_000_000.0
    trades = [_clean_close(base_ts, +2.0), _clean_close(base_ts + 60.0, -1.0)]

    snap = advisor_loop._replay_clean_trades_kpis(trades, base_capital=100.0)

    assert snap.total_trades == 2
    assert abs(snap.win_rate - 0.5) < 1e-9
    # pic 102 -> equity 101 : DD = 1/102
    assert abs(snap.max_drawdown - 1.0 / 102.0) < 1e-9


class _FakeOpenPosition:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.side = "buy"
        self.entry_price = 100.0
        self.live_pnl_pct = -1.5
        self.opened_ts = 0.0
        self.current_price = 98.5
        self.live_pnl_usd = -0.15
        self.qty_usd = 10.0
        self.tp_price = 104.0
        self.sl_price = 98.0


class _FakeSimWithPositions:
    def __init__(self, symbols: list[str]):
        self._symbols = symbols

    def get_open_positions_summary(self):
        positions = [_FakeOpenPosition(s) for s in self._symbols]
        return SimpleNamespace(
            n_open=len(positions),
            unrealized_pnl_usd=sum(p.live_pnl_usd for p in positions),
            positions=positions,
        )


class _FakePosManager:
    def __init__(self, snapshot: list[dict]):
        self._snapshot = snapshot

    def snapshot(self):
        return self._snapshot


def test_positions_for_display_prefers_mexcsim_ledger():
    """Régression 'POSITIONS 0 ouverte' du rapport 21:00 (2026-07-12) :
    pos_manager vide alors que MexcSim portait 3 positions ouvertes —
    l'affichage doit montrer le vrai ledger."""
    sim = _FakeSimWithPositions(["BTC/USDT", "BNB/USDT", "ETH/USDT"])
    pm = _FakePosManager([])  # pos_manager désynchronisé — reproduit le bug

    rows = advisor_loop._positions_for_display(sim, pm)

    assert [r["symbol"] for r in rows] == ["BTC/USDT", "BNB/USDT", "ETH/USDT"]
    assert rows[0]["entry"] == 100.0
    assert rows[0]["pnl_usd"] == -0.15
    assert rows[0]["unrealized_pnl"] == -0.15  # clé lue par le rapport programmé
    assert rows[0]["tp"] == 104.0 and rows[0]["sl"] == 98.0


def test_positions_for_display_empty_sim_is_truth_not_fallback():
    """0 position dans MexcSim actif = vérité — ne pas retomber sur pos_manager."""
    sim = _FakeSimWithPositions([])
    pm = _FakePosManager([{"symbol": "GHOST/USDT"}])

    assert advisor_loop._positions_for_display(sim, pm) == []


def test_positions_for_display_falls_back_without_sim():
    pm = _FakePosManager([{"symbol": "BTC/USDT", "side": "long"}])

    rows = advisor_loop._positions_for_display(None, pm)

    assert rows == [{"symbol": "BTC/USDT", "side": "long"}]


def test_positions_for_display_falls_back_on_sim_error():
    pm = _FakePosManager([{"symbol": "BTC/USDT"}])

    rows = advisor_loop._positions_for_display(_BrokenVirtualPortfolio(), pm)

    assert rows == [{"symbol": "BTC/USDT"}]
