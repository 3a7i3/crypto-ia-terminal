from system.alpha_kill_switch import AlphaKillSwitch


def _trade(
    pnl_pct: float, symbol: str = "BTC", close_ts: float = 1_700_000_000.0
) -> dict:
    return {
        "pnl_pct": pnl_pct,
        "symbol": symbol,
        "close_ts": close_ts,
    }


def test_not_triggered_when_too_few_trades() -> None:
    # Trades gagnants en nombre insuffisant : aucun check ne se déclenche
    ks = AlphaKillSwitch(window=50, pf_floor=0.8, min_trades=30, symbol_min_trades=30)
    trades = [_trade(0.02) for _ in range(20)]  # < min_trades et < symbol_min_trades
    result = ks.evaluate(trades)
    assert not result.triggered
    assert result.rolling_pf is None


def test_triggered_when_pf_below_floor() -> None:
    ks = AlphaKillSwitch(window=50, pf_floor=0.8, min_trades=30)
    # 70% de pertes -> PF << 0.8
    trades = [_trade(-0.05, close_ts=1_700_000_000.0 + i) for i in range(21)] + [
        _trade(0.02, close_ts=1_700_000_000.0 + 100 + i) for i in range(9)
    ]
    result = ks.evaluate(trades)
    assert result.triggered
    assert result.rolling_pf is not None
    assert result.rolling_pf < 0.8
    assert "AUTO_PAPER_ONLY" in result.suggested_actions


def test_not_triggered_when_pf_above_floor() -> None:
    ks = AlphaKillSwitch(window=50, pf_floor=0.8, min_trades=30)
    # 60% gagnants, chaque trade +2% ou -1%
    trades = [_trade(0.02, close_ts=1_700_000_000.0 + i) for i in range(18)] + [
        _trade(-0.01, close_ts=1_700_000_000.0 + 100 + i) for i in range(12)
    ]
    result = ks.evaluate(trades)
    assert not result.triggered


def test_drag_symbol_detected() -> None:
    ks = AlphaKillSwitch(
        window=50,
        pf_floor=0.8,
        min_trades=5,
        symbol_drag_threshold=-0.3,
        symbol_min_trades=5,
    )
    # DOGE perd beaucoup sur 5 trades
    doge_trades = [
        _trade(-0.10, symbol="DOGE", close_ts=1_700_000_000.0 + i) for i in range(5)
    ]
    btc_trades = [
        _trade(0.05, symbol="BTC", close_ts=1_700_000_001.0 + i) for i in range(5)
    ]
    result = ks.evaluate(doge_trades + btc_trades)

    assert "DOGE" in result.drag_symbols
    assert any("AUTO_DISABLE_SYMBOL=DOGE" in a for a in result.suggested_actions)


def test_drag_symbol_not_flagged_below_min_trades() -> None:
    ks = AlphaKillSwitch(
        symbol_min_trades=5, symbol_drag_threshold=-0.3, min_trades=100
    )
    trades = [
        _trade(-0.10, symbol="DOGE", close_ts=1_700_000_000.0 + i) for i in range(4)
    ]
    result = ks.evaluate(trades)
    assert "DOGE" not in result.drag_symbols


def test_result_as_dict_is_serialisable() -> None:
    import json

    ks = AlphaKillSwitch(min_trades=1, symbol_min_trades=1)
    trades = [_trade(-0.05, close_ts=1_700_000_000.0)]
    result = ks.evaluate(trades)
    serialised = json.dumps(result.as_dict())
    assert "triggered" in serialised


def test_uses_only_recent_window() -> None:
    ks = AlphaKillSwitch(window=10, pf_floor=0.8, min_trades=10)
    # 40 trades gagnants anciens, 10 trades perdants récents
    old_trades = [_trade(0.05, close_ts=1_600_000_000.0 + i) for i in range(40)]
    recent_trades = [_trade(-0.10, close_ts=1_700_000_000.0 + i) for i in range(10)]
    result = ks.evaluate(old_trades + recent_trades)
    # Seule la fenêtre récente compte → déclenché
    assert result.triggered
    assert result.trades_evaluated == 10
