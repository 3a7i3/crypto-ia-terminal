"""Sonde de débit — fonctions pures (audit passif, ADR famine 2026-07-14)."""

from tools.throughput_probe import (
    _normalize_regret_horizons,
    _normalize_regret_legacy,
    days_to_target,
    distinct_opportunities_per_day,
    quality_at_threshold,
    simulated_throughput,
)

_DAY1 = 1_784_000_000.0  # 2026-07-14 ~03:33 UTC
_DAY2 = _DAY1 + 86_400.0


def _rej(ts: float, symbol: str, side: str, score: float) -> dict:
    return {"ts": ts, "symbol": symbol, "side": side, "score": score}


def test_distinct_opportunities_dedupe_same_setup_same_day():
    """21 signaux 'ETH SELL 70' dans la même journée = 1 opportunité
    (constat 2026-07-14), mais le même setup un autre jour recompte."""
    records = [_rej(_DAY1 + i * 300, "ETH/USDT", "SELL", 70) for i in range(21)]
    records.append(_rej(_DAY2, "ETH/USDT", "SELL", 70))
    records.append(_rej(_DAY1, "ETH/USDT", "BUY", 70))  # sens opposé = distinct

    days = distinct_opportunities_per_day(records)

    assert sum(len(v) for v in days.values()) == 3


def test_simulated_throughput_filters_by_score():
    records = [
        _rej(_DAY1, "A/USDT", "BUY", 55),
        _rej(_DAY1, "B/USDT", "BUY", 62),
        _rej(_DAY1, "C/USDT", "BUY", 70),
    ]

    sim = simulated_throughput(records, n_days=1.0, thresholds=[55, 62, 66, 72])

    assert sim[55]["distinct_per_day"] == 3
    assert sim[62]["distinct_per_day"] == 2
    assert sim[66]["distinct_per_day"] == 1
    assert sim[72]["distinct_per_day"] == 0


def test_quality_at_threshold_direction_and_expectancy():
    regrets = [
        {
            "score": 70,
            "direction_ok": True,
            "ret_if_followed": 0.02,
            "regret_type": "MISSED_WIN",
        },
        {
            "score": 68,
            "direction_ok": False,
            "ret_if_followed": -0.04,
            "regret_type": "GOOD_REFUSAL",
        },
        {
            "score": 50,
            "direction_ok": True,
            "ret_if_followed": 0.10,
            "regret_type": "MISSED_WIN",
        },
    ]

    q = quality_at_threshold(regrets, threshold=66)

    assert q["n"] == 2  # le score 50 est exclu
    assert q["direction_ok_pct"] == 50.0
    assert abs(q["mean_ret_pct"] - (-1.0)) < 1e-9  # (2% - 4%) / 2
    assert q["types"] == {"MISSED_WIN": 1, "GOOD_REFUSAL": 1}


def test_quality_empty_selection():
    assert quality_at_threshold([], threshold=66) == {"n": 0}


def test_days_to_target_basic_and_edge_cases():
    assert days_to_target(2.0, current_n=36, target=100) == 32.0
    assert days_to_target(0.0, current_n=36, target=100) == float("inf")
    assert days_to_target(5.0, current_n=500, target=500) == 0.0


def test_normalize_regret_horizons_prefers_longest_and_inverts_sell():
    record = {
        "ts_signal": _DAY1,
        "symbol": "LAB/USDT",
        "side": "SELL",
        "score": 67.0,
        "regime": "high_volatility_regime",
        "horizons": {
            "5m": {
                "horizon": "5m",
                "return_pct": 0.01,
                "direction_ok": False,
                "regret_type": "NEUTRAL",
            },
            "30m": {
                "horizon": "30m",
                "return_pct": -0.02,
                "direction_ok": True,
                "regret_type": "GOOD_REFUSAL",
            },
        },
    }

    norm = _normalize_regret_horizons(record)

    assert norm["horizon"] == "30m"  # préférence horizon long
    # SELL suivi d'une baisse de 2% = +2% si on avait suivi le signal
    assert abs(norm["ret_if_followed"] - 0.02) < 1e-12
    assert norm["direction_ok"] is True


def test_normalize_regret_legacy_flat_schema():
    record = {
        "ts_signal": _DAY1,
        "symbol": "ANSEM/USDT",
        "signal": "BUY",
        "score": 69,
        "regime": "high_volatility_regime",
        "potential_pnl_pct": -0.0446,
        "direction_correct": False,
        "regret_type": "GOOD_REFUSAL",
    }

    norm = _normalize_regret_legacy(record)

    assert norm["side"] == "BUY"
    assert abs(norm["ret_if_followed"] - (-0.0446)) < 1e-12
    assert norm["regret_type"] == "GOOD_REFUSAL"


def test_normalize_regret_legacy_rejects_foreign_schema():
    assert _normalize_regret_legacy({"ts_signal": _DAY1, "symbol": "X"}) is None
