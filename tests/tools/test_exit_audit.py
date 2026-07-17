"""Audit des sorties H-exit — fonctions pures, zéro réseau."""

from tools.exit_audit import capture_stats, net_actual_pct, simulate_tp


def _trade(
    *,
    mfe: float,
    mae: float = -1.0,
    pnl_usd: float,
    size: float = 10.0,
    pnl_pct: float = 0.0,
    reason: str = "TIMEOUT",
) -> dict:
    return {
        "mfe_pct": mfe,
        "mae_pct": mae,
        "pnl_usd": pnl_usd,
        "size_usd": size,
        "pnl_pct": pnl_pct,
        "reason": reason,
    }


def test_net_actual_pct_uses_net_pnl_over_size():
    t = _trade(mfe=1.0, pnl_usd=-0.05, size=10.0)

    assert abs(net_actual_pct(t) - (-0.5)) < 1e-9  # -0.05$ sur 10$ = -0.5%


def test_capture_stats_counts_losers_with_high_mfe():
    trades = [
        _trade(mfe=1.2, pnl_usd=-0.02),  # perdant monté à +1.2%
        _trade(mfe=0.6, pnl_usd=-0.01),  # perdant monté à +0.6%
        _trade(mfe=2.0, pnl_usd=+0.10),  # gagnant
    ]

    cap = capture_stats(trades)

    assert cap["n_perdants"] == 2
    assert cap["perdants_mfe_ge_1.0"] == 1
    assert cap["perdants_mfe_ge_0.5"] == 2
    assert abs(cap["mfe_perdants_moy_pct"] - 0.9) < 1e-9


def test_simulate_tp_sure_capture_when_no_sl():
    """MFE >= TP sans SL touché : TP capturé de façon certaine (net du coût)."""
    trades = [_trade(mfe=1.5, pnl_usd=-0.03, reason="TIMEOUT")]

    s = simulate_tp(trades, tp_pct=1.0, cost_pct=0.30)

    assert s["n_tp_sur"] == 1
    assert s["n_ambigu"] == 0
    # +1.0% brut - 0.30% coût = +0.70% net, bornes identiques
    assert abs(s["esperance_optimiste_pct"] - 0.70) < 1e-9
    assert s["esperance_optimiste_pct"] == s["esperance_pessimiste_pct"]


def test_simulate_tp_ambiguous_when_sl_hit():
    """MFE >= TP mais SL réellement touché : fourchette pessimiste/optimiste."""
    trades = [_trade(mfe=1.5, pnl_usd=-0.20, size=10.0, reason="SL")]

    s = simulate_tp(trades, tp_pct=1.0, cost_pct=0.30)

    assert s["n_ambigu"] == 1
    assert abs(s["esperance_optimiste_pct"] - 0.70) < 1e-9  # TP d'abord
    assert abs(s["esperance_pessimiste_pct"] - (-2.0)) < 1e-9  # SL réel


def test_simulate_tp_unchanged_when_mfe_below_tp():
    trades = [_trade(mfe=0.4, pnl_usd=+0.05, size=10.0, reason="TIMEOUT")]

    s = simulate_tp(trades, tp_pct=1.0, cost_pct=0.30)

    assert s["n_inchange"] == 1
    # résultat réel net conservé : +0.5%
    assert abs(s["esperance_optimiste_pct"] - 0.5) < 1e-9
    assert s["esperance_optimiste_pct"] == s["esperance_pessimiste_pct"]


def test_simulate_tp_mixed_population_bounds():
    trades = [
        _trade(mfe=1.5, pnl_usd=-0.03, reason="TIMEOUT"),  # TP sûr
        _trade(mfe=1.2, pnl_usd=-0.20, size=10.0, reason="SL"),  # ambigu
        _trade(mfe=0.2, pnl_usd=-0.02, size=10.0, reason="TIMEOUT"),  # inchangé
    ]

    s = simulate_tp(trades, tp_pct=1.0, cost_pct=0.30)

    assert (s["n_tp_sur"], s["n_ambigu"], s["n_inchange"]) == (1, 1, 1)
    # optimiste : 0.70 + 0.70 - 0.20 ; pessimiste : 0.70 - 2.0 - 0.20
    assert abs(s["total_optimiste_pct"] - 1.20) < 1e-6
    assert abs(s["total_pessimiste_pct"] - (-1.50)) < 1e-6
