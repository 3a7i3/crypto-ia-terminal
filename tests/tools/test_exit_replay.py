"""exit_audit v2 — moteur de rejeu des sorties (fonctions pures, zéro I/O)."""

from tools.exit_replay import ExitPolicy, replay_trade, signed_return_pct

_T0 = 1_784_400_000.0
_TICK = 900.0


def _path(rets_pct: list[float], entry: float = 100.0) -> list:
    """Chemin de prix construit depuis des rendements signés BUY (%)."""
    return [(_T0 + i * _TICK, entry * (1 + r / 100.0)) for i, r in enumerate(rets_pct)]


def _pol(tp=1.5, sl=1.5, be=None, to=48.0) -> ExitPolicy:
    return ExitPolicy(tp_pct=tp, sl_pct=sl, be_arm_pct=be, timeout_h=to)


def test_signed_return_inverts_for_sell():
    assert signed_return_pct("buy", 100.0, 101.0) == 1.0
    assert signed_return_pct("sell", 100.0, 101.0) == -1.0


def test_tp_hit():
    reason, net = replay_trade(
        _path([0.0, 0.5, 1.6]), "buy", _T0, 100.0, _pol(tp=1.5), cost_pct=0.30
    )

    assert reason == "TP"
    assert abs(net - 1.2) < 1e-9  # 1.5 - 0.30


def test_sl_hit():
    reason, net = replay_trade(
        _path([0.0, -0.5, -1.7]), "buy", _T0, 100.0, _pol(sl=1.5), cost_pct=0.30
    )

    assert reason == "SL"
    assert abs(net - (-1.8)) < 1e-9  # -1.5 - 0.30


def test_same_tick_tp_and_sl_is_pessimistic():
    """Un tick qui franchit TP et SL à la fois → SL d'abord (pessimiste)."""
    path = [(_T0, 100.0), (_T0 + _TICK, 98.0)]  # -2% : franchit SL0.8 ET rien
    reason, _ = replay_trade(path, "buy", _T0, 100.0, _pol(tp=1.5, sl=0.8), 0.30)
    assert reason == "SL"


def test_break_even_protects_a_would_be_loser():
    """Monte à +0.6% (BE armé) puis retombe : sortie ~0 au lieu du SL."""
    path = _path([0.0, 0.6, 0.2, -0.4, -2.0])
    with_be = _pol(tp=3.0, sl=1.5, be=0.5)
    without_be = _pol(tp=3.0, sl=1.5, be=None)

    r_be, net_be = replay_trade(path, "buy", _T0, 100.0, with_be, 0.30)
    r_no, net_no = replay_trade(path, "buy", _T0, 100.0, without_be, 0.30)

    assert r_be == "SL" and abs(net_be - (-0.30)) < 1e-9  # stop à l'entrée
    assert r_no == "SL" and abs(net_no - (-1.80)) < 1e-9  # plein SL


def test_timeout_exit_at_current_return():
    path = _path([0.0, 0.2, 0.3, 0.1, 0.4, 0.2])
    pol = _pol(tp=3.0, sl=1.5, to=1.0)  # timeout 1h = 4 ticks

    reason, net = replay_trade(path, "buy", _T0, 100.0, pol, 0.30)

    assert reason == "TIMEOUT"
    assert abs(net - (0.4 - 0.30)) < 1e-9  # tick à t+1h : +0.4%


def test_path_exhausted_reports_fin_donnees():
    reason, _ = replay_trade(
        _path([0.0, 0.1]), "buy", _T0, 100.0, _pol(tp=3.0, sl=3.0, to=48.0), 0.30
    )

    assert reason == "FIN_DONNEES"


def test_sell_side_tp_on_price_drop():
    path = _path([0.0, -1.0, -1.8])  # le prix BAISSE → gain pour un SELL

    reason, net = replay_trade(path, "sell", _T0, 100.0, _pol(tp=1.5, sl=1.5), 0.30)

    assert reason == "TP"
    assert abs(net - 1.2) < 1e-9
