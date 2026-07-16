"""R2 — évaluation à horizons (ADR-0016/0017) : fonctions pures, zéro réseau."""

from observation.horizon_evaluator import (
    evaluate_symbol,
    forward_returns,
    palier_aggregates,
    persistence_1h,
    series_by_symbol,
)

_T0 = 1_784_200_000.0
_TICK = 900.0  # cadence du pouls : 15 min


def _series(prices: list[float]) -> list[tuple[float, float]]:
    return [(_T0 + i * _TICK, p) for i, p in enumerate(prices)]


def test_series_by_symbol_filters_sorts_and_dedupes():
    records = [
        {"ts": _T0 + _TICK, "sym": "BTC/USDT", "last": 101.0},
        {"ts": _T0, "sym": "BTC/USDT", "last": 100.0},
        {"ts": _T0, "sym": "BTC/USDT", "last": 100.0},  # doublon même ts
        {"ts": _T0, "sym": "IGNORED/USDT", "last": 5.0},
        {"ts": _T0 + 2 * _TICK, "sym": "BTC/USDT", "last": 0.0},  # prix mort
    ]

    series = series_by_symbol(records, wanted={"BTC/USDT"})

    assert list(series) == ["BTC/USDT"]
    assert series["BTC/USDT"] == [(_T0, 100.0), (_T0 + _TICK, 101.0)]


def test_forward_returns_15m_on_regular_ticks():
    # +1% par tick de 15 min
    series = _series([100.0, 101.0, 102.01])

    rets = forward_returns(series, 900.0)

    assert len(rets) == 2
    assert abs(rets[0] - 1.0) < 1e-9
    assert abs(rets[1] - 1.0) < 1e-9


def test_forward_returns_skips_gaps_beyond_tolerance():
    # trou de 2h entre les deux points : aucun appariement à 15 min possible
    series = [(_T0, 100.0), (_T0 + 7200.0, 105.0)]

    assert forward_returns(series, 900.0) == []


def test_persistence_detects_momentum_and_mean_reversion():
    up = _series([100 * (1.01**i) for i in range(20)])  # toujours haussier
    # alternance à l'échelle 1h (4 ticks de 15 min par jambe) : mean-reversion
    zigzag = _series([100 + (1 if (i // 4) % 2 else -1) for i in range(24)])

    assert persistence_1h(up) == 1.0
    p_zz = persistence_1h(zigzag)
    assert p_zz is not None and p_zz < 0.5


def test_evaluate_symbol_produces_horizon_metrics():
    series = _series([100 * (1.005**i) for i in range(30)])  # 30 ticks ≈ 7h15

    ev = evaluate_symbol(series)

    assert ev["n_ticks"] == 30
    assert ev["15m"]["n"] > 0
    assert ev["1h"]["n"] > 0
    assert ev["4h"]["n"] > 0
    # +0.5%/15min → ≈ +2% par heure en médiane absolue
    assert 1.5 < ev["1h"]["p50_abs"] < 2.5


def test_palier_aggregates_counts_opportunities_per_day():
    shortlist = [{"sym": f"S{i}/USDT"} for i in range(3)]
    evaluations = {
        "S0/USDT": {
            "4h": {"n": 5, "vol_pct": 1.0},
            "1h": {"n": 5, "vol_pct": 0.5},
            "_4h_ge_thr": 4,
        },
        "S1/USDT": {
            "4h": {"n": 5, "vol_pct": 2.0},
            "1h": {"n": 5, "vol_pct": 1.5},
            "_4h_ge_thr": 2,
        },
        # S2 jamais observé → ignoré
    }

    agg = palier_aggregates(shortlist, evaluations, window_days=2.0, min_move_pct=1.0)

    assert agg["top50"]["n_paires_evaluees"] == 2
    assert agg["top50"]["opportunites_par_jour"] == 3.0  # (4+2)/2 jours
    assert abs(agg["top50"]["vol_1h_mediane_pct"] - 1.0) < 1e-9


def test_palier_aggregates_empty_shortlist():
    agg = palier_aggregates([], {}, window_days=1.0, min_move_pct=1.0)

    assert agg["top50"]["n_paires_evaluees"] == 0
    assert agg["top50"]["opportunites_par_jour"] == 0.0
