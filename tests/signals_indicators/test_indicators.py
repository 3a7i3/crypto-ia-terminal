"""Formules du jeu v1 : cas connus et parité avec feature_engineer.py (lecture seule)."""
from __future__ import annotations

from decimal import Decimal as D

import pytest

from observability.signals_indicators import indicators as ind

DAY = 86_400_000
H = 3_600_000


def bars_from_closes(closes, *, rng=D(10), vol=D(100), start=20 * DAY):
    out, prev = [], None
    for i, c in enumerate(closes):
        c = D(c)
        o = prev if prev is not None else c
        out.append({"open_ms": start + i * H, "o": o, "h": max(o, c) + rng / 2,
                    "l": min(o, c) - rng / 2, "c": c, "v": vol})
        prev = c
    return out


def wave(n):
    return [D(100) + D(i) / 10 + D((i * 37) % 23 - 11) / 4 for i in range(n)]


def test_rsi_parity_with_feature_engineer():
    fe = pytest.importorskip("quant_hedge_ai.agents.intelligence.feature_engineer").FeatureEngineer()
    closes = wave(200)
    ours = ind.rsi(bars_from_closes(closes))
    theirs = fe._rsi([float(c) for c in closes], 14)
    assert abs(float(ours) - theirs) < 1e-6


def test_ema_converges_to_feature_engineer():
    """Amorçage différent (SMA ici, 1er prix là-bas) ; l'écart s'éteint."""
    fe = pytest.importorskip("quant_hedge_ai.agents.intelligence.feature_engineer").FeatureEngineer
    closes = wave(400)
    ours = ind.ema_series(closes, 20)[-1]
    theirs = fe._ema([float(c) for c in closes], 20)[-1]
    assert abs(float(ours) - theirs) / theirs < 1e-9


def test_rsi_extremes_and_flat():
    assert ind.rsi(bars_from_closes(range(100, 130))) == D(100)
    flat = ind.rsi(bars_from_closes([100] * 30))
    assert flat == {"state": "NOT_AVAILABLE", "reason": "FLAT_SERIES"}


def test_rsi_insufficient_bars_is_not_zero():
    res = ind.rsi(bars_from_closes(range(100, 110)))
    assert res == {"state": "NOT_AVAILABLE", "reason": "INSUFFICIENT_BARS", "missing": 5}


def test_ema_seed_is_sma():
    assert ind.ema_series([D(1), D(2), D(3)], 3) == [D(2)]
    assert ind.ema_series([D(1), D(2)], 3) == []


def test_atr_constant_range():
    # Prix constant, range fixe de 10 : ATR = 10, soit 10 % d'un prix de 100.
    res = ind.atr_pct(bars_from_closes([100] * 40, rng=D(10)))
    assert res == D(10)


def test_dmi_trend_up_has_di_plus_dominant_and_adx_needs_2n():
    bars = bars_from_closes(range(100, 160))
    out = ind.dmi(bars)
    assert out["di_plus_14"] > out["di_minus_14"]
    assert out["di_minus_14"] == 0
    assert out["adx_14"] == D(100)
    short = ind.dmi(bars[:20])
    assert short["adx_14"]["reason"] == "INSUFFICIENT_BARS" and short["adx_14"]["missing"] == 8
    assert isinstance(short["di_plus_14"], D)


def test_vwap_session_resets_at_utc_midnight():
    bars = bars_from_closes([100, 100, 200, 200], rng=D(0))
    for i, b in enumerate(bars):
        b["open_ms"] = DAY - 2 * H + i * H  # 2 barres la veille, 2 le jour même
    # Session = 2 dernières barres ; prix typique de la 1re : (200+100+200)/3.
    vwap = (D(500) / 3 + D(200)) / 2
    assert ind.vwap_session_dist_pct(bars) == (D(200) - vwap) / vwap * 100


def test_volume_rel_and_delta():
    bars = bars_from_closes([100] * 21)
    bars[-1]["v"] = D(200)
    assert ind.volume_rel(bars) == D(2)
    assert ind.delta_pct_volume(bars)["reason"] == "INPUT_MISSING"
    bars[-1].update(buy_v=D(150), sell_v=D(50))
    assert ind.delta_pct_volume(bars) == D(50)


def test_book_indicators():
    bids = [(D(99), D(3)), (D(98), D(1))]
    asks = [(D(101), D(1)), (D(102), D(1))]
    out = ind.book_indicators(bids, asks, 10)
    assert out["imb_top10"] == (D(4) - D(2)) / D(6)
    assert out["spread_bps"] == D(200)


def test_oi_change():
    assert ind.oi_change_pct([D(100), D(110)]) == D(10)
    assert ind.oi_change_pct([D(100)])["reason"] == "INSUFFICIENT_BARS"
