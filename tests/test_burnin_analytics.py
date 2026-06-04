from system.burnin_analytics import BurnInAnalytics


def _trade(score: int, pnl_usd: float, pnl_pct: float, reason: str = "") -> dict:
    return {
        "trade_id": f"t_{score}_{pnl_usd}",
        "close_ts": 1_700_000_000.0,
        "duration_s": 60.0,
        "score": score,
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_pct,
        "exit_reason": reason,
    }


def test_build_report_core_metrics_present() -> None:
    analytics = BurnInAnalytics(initial_capital=1000.0)
    trades = [
        _trade(55, 10.0, 0.01, "take_profit"),
        _trade(58, -5.0, -0.005, "stop_loss"),
        _trade(62, 7.0, 0.007, "tp"),
        _trade(71, -3.0, -0.003, "sl"),
    ]

    report = analytics.build_report(trades, window_hours=24)

    assert report["trades"] == 4
    assert report["wins"] == 2
    assert report["losses"] == 2
    assert report["win_rate"] == 50.0
    assert "profit_factor" in report
    assert "expectancy" in report
    assert "max_drawdown" in report
    assert "sharpe" in report


def test_score_histogram_has_required_ranges() -> None:
    analytics = BurnInAnalytics(initial_capital=1000.0)
    trades = [
        _trade(52, 5.0, 0.005),
        _trade(55, -2.0, -0.002),
        _trade(61, 3.0, 0.003),
        _trade(66, -1.0, -0.001),
        _trade(73, 4.0, 0.004),
    ]

    report = analytics.build_report(trades)
    histogram = report["score_histogram"]

    ranges = [row["range"] for row in histogram]
    assert ranges == ["50-54", "55-59", "60-64", "65-69", "70+"]

    per_range = {row["range"]: row for row in histogram}
    assert per_range["50-54"]["trades"] == 1
    assert per_range["55-59"]["trades"] == 1
    assert per_range["60-64"]["trades"] == 1
    assert per_range["65-69"]["trades"] == 1
    assert per_range["70+"]["trades"] == 1


def test_symbol_breakdown_groups_by_symbol() -> None:
    analytics = BurnInAnalytics()
    trades = [
        {**_trade(60, 10.0, 0.01), "symbol": "BTCUSDT"},
        {**_trade(60, 8.0, 0.008), "symbol": "BTCUSDT"},
        {**_trade(60, -5.0, -0.005), "symbol": "ETHUSDT"},
        {**_trade(60, -3.0, -0.003), "symbol": "ETHUSDT"},
        {**_trade(60, -3.0, -0.003), "symbol": "ETHUSDT"},
    ]

    report = analytics.build_report(trades)
    breakdown = report["symbol_breakdown"]

    symbols = [r["symbol"] for r in breakdown]
    assert "BTCUSDT" in symbols
    assert "ETHUSDT" in symbols

    by_sym = {r["symbol"]: r for r in breakdown}
    assert by_sym["BTCUSDT"]["trades"] == 2
    assert by_sym["ETHUSDT"]["trades"] == 3
    assert by_sym["BTCUSDT"]["win_rate"] == 100.0
    assert by_sym["ETHUSDT"]["win_rate"] == 0.0


def test_symbol_breakdown_sorted_by_expectancy_desc() -> None:
    analytics = BurnInAnalytics()
    trades = [
        {**_trade(60, -5.0, -0.05), "symbol": "DRAG"},
        {**_trade(60, 10.0, 0.10), "symbol": "EDGE"},
        {**_trade(60, 1.0, 0.01), "symbol": "FLAT"},
    ]

    report = analytics.build_report(trades)
    breakdown = report["symbol_breakdown"]

    expectations = [r["expectancy"] for r in breakdown]
    assert expectations == sorted(expectations, reverse=True)


def test_symbol_breakdown_missing_symbol_defaults_to_unknown() -> None:
    analytics = BurnInAnalytics()
    trades = [_trade(60, 5.0, 0.05)]  # pas de champ "symbol"

    report = analytics.build_report(trades)
    breakdown = report["symbol_breakdown"]

    assert len(breakdown) == 1
    assert breakdown[0]["symbol"] == "UNKNOWN"


def test_histogram_includes_score_floor() -> None:
    analytics = BurnInAnalytics()
    report = analytics.build_report([_trade(62, 1.0, 0.01)])
    per_range = {r["range"]: r for r in report["score_histogram"]}
    assert per_range["60-64"]["score_floor"] == 60
    assert per_range["55-59"]["score_floor"] == 55
    assert per_range["70+"]["score_floor"] == 70


def test_subset_metrics_includes_sharpe_and_alpha_class() -> None:
    analytics = BurnInAnalytics()
    # 10 trades uniformément gagnants -> alpha positive
    trades = [_trade(62, 2.0, 0.02) for _ in range(10)]
    report = analytics.build_report(trades)
    bin_60 = next(r for r in report["score_histogram"] if r["range"] == "60-64")
    assert "sharpe" in bin_60
    assert bin_60["sharpe"] == 0.0  # std=0 quand tous identiques
    assert bin_60["alpha_class"] == "positive"


def test_alpha_class_negative_when_expectancy_low() -> None:
    analytics = BurnInAnalytics()
    trades = [_trade(62, -5.0, -0.05) for _ in range(10)]
    report = analytics.build_report(trades)
    bin_60 = next(r for r in report["score_histogram"] if r["range"] == "60-64")
    assert bin_60["alpha_class"] == "negative"


def test_alpha_class_insufficient_data_below_10() -> None:
    analytics = BurnInAnalytics()
    trades = [_trade(62, 10.0, 0.10) for _ in range(5)]  # seulement 5 trades
    report = analytics.build_report(trades)
    bin_60 = next(r for r in report["score_histogram"] if r["range"] == "60-64")
    assert bin_60["alpha_class"] == "insufficient_data"


def test_expected_value_curve_only_populated_bins() -> None:
    analytics = BurnInAnalytics()
    trades = [_trade(55, 1.0, 0.01), _trade(62, -1.0, -0.01)]
    report = analytics.build_report(trades)
    curve = report["expected_value_curve"]
    floors = [p["score_floor"] for p in curve]
    assert 55 in floors
    assert 60 in floors
    assert 50 not in floors  # bin 50-54 vide
    assert 65 not in floors  # bin 65-69 vide


def test_recommended_score_floor_none_when_insufficient() -> None:
    analytics = BurnInAnalytics()
    trades = [_trade(62, 1.0, 0.01) for _ in range(3)]  # < 10 trades
    report = analytics.build_report(trades)
    assert report["recommended_score_floor"] is None
    assert report["score_floor_confidence"] == "INSUFFICIENT_DATA"


def test_recommended_score_floor_positive_bin() -> None:
    analytics = BurnInAnalytics()
    # 10 trades gagnants dans 60-64 -> bin positive -> recommande floor 60
    trades = [_trade(62, 2.0, 0.02) for _ in range(10)]
    report = analytics.build_report(trades)
    assert report["recommended_score_floor"] == 60
    assert report["score_floor_confidence"] == "LOW"  # 10 trades < 50


def test_score_to_bin_in_recorder() -> None:
    from paper_trading.recorder import _score_to_bin

    assert _score_to_bin(45) == "<50"
    assert _score_to_bin(52) == "50-54"
    assert _score_to_bin(57) == "55-59"
    assert _score_to_bin(63) == "60-64"
    assert _score_to_bin(68) == "65-69"
    assert _score_to_bin(75) == "70+"


def test_symbol_bin_matrix_structure() -> None:
    analytics = BurnInAnalytics()
    trades = [
        {**_trade(57, 2.0, 0.02), "symbol": "BTC"},
        {**_trade(57, -1.0, -0.01), "symbol": "ETH"},
        {**_trade(62, 3.0, 0.03), "symbol": "BTC"},
        {**_trade(62, -2.0, -0.02), "symbol": "ETH"},
        {**_trade(62, -2.0, -0.02), "symbol": "ETH"},
    ]
    report = analytics.build_report(trades)
    matrix = report["symbol_bin_matrix"]

    assert "BTC" in matrix
    assert "ETH" in matrix
    assert "55-59" in matrix["BTC"]
    assert "60-64" in matrix["BTC"]
    assert "60-64" in matrix["ETH"]

    assert matrix["BTC"]["55-59"]["trades"] == 1
    assert matrix["BTC"]["60-64"]["trades"] == 1
    assert matrix["ETH"]["60-64"]["trades"] == 2


def test_symbol_bin_matrix_expectancy_values() -> None:
    analytics = BurnInAnalytics()
    trades = [
        {**_trade(57, 5.0, 0.05), "symbol": "ALPHA"},
        {**_trade(57, 5.0, 0.05), "symbol": "ALPHA"},
        {**_trade(62, -3.0, -0.03), "symbol": "DRAG"},
        {**_trade(62, -3.0, -0.03), "symbol": "DRAG"},
    ]
    report = analytics.build_report(trades)
    matrix = report["symbol_bin_matrix"]

    assert matrix["ALPHA"]["55-59"]["expectancy"] > 0
    assert matrix["DRAG"]["60-64"]["expectancy"] < 0


def test_symbol_bin_matrix_empty_on_no_trades() -> None:
    analytics = BurnInAnalytics()
    report = analytics.build_report([])
    assert report["symbol_bin_matrix"] == {}


def test_equity_curve_follows_pnl_sequence() -> None:
    analytics = BurnInAnalytics(initial_capital=1000.0)
    trades = [
        {**_trade(60, 10.0, 0.01), "close_ts": 1_700_000_001.0},
        {**_trade(60, -5.0, -0.005), "close_ts": 1_700_000_002.0},
        {**_trade(60, 8.0, 0.008), "close_ts": 1_700_000_003.0},
    ]
    report = analytics.build_report(trades)
    curve = report["equity_curve"]

    assert len(curve) == 3
    assert curve[0]["trade"] == 1
    assert curve[0]["equity"] == 1010.0
    assert curve[1]["equity"] == 1005.0
    assert curve[2]["equity"] == 1013.0
    assert all("ts_iso" in p for p in curve)


def test_equity_curve_empty_on_no_trades() -> None:
    analytics = BurnInAnalytics(initial_capital=1000.0)
    report = analytics.build_report([])
    assert report["equity_curve"] == []


def test_alpha_drift_groups_by_symbol_and_week() -> None:
    analytics = BurnInAnalytics()
    # Deux semaines distincts
    trades = [
        {**_trade(60, 5.0, 0.05), "symbol": "BTC", "close_ts": 1_700_000_000.0},
        {
            **_trade(60, -2.0, -0.02),
            "symbol": "BTC",
            "close_ts": 1_700_000_000.0 + 604800,
        },
        {**_trade(60, 3.0, 0.03), "symbol": "ETH", "close_ts": 1_700_000_000.0},
    ]
    report = analytics.build_report(trades)
    drift = report["alpha_drift"]

    assert "BTC" in drift
    assert "ETH" in drift
    assert len(drift["BTC"]) == 2  # 2 semaines différentes


def test_alpha_drift_empty_on_no_trades() -> None:
    analytics = BurnInAnalytics()
    report = analytics.build_report([])
    assert report["alpha_drift"] == {}


def test_alpha_digest_lines_structure() -> None:
    """_alpha_digest_lines produit les lignes meilleur/pire bin et symbole."""
    import sys

    sys.path.insert(0, "scripts")
    from vps_burn_in_collector import _alpha_digest_lines

    burnin = {
        "trades": 30,
        "win_rate": 45.0,
        "profit_factor": 1.2,
        "sharpe": 0.5,
        "max_drawdown": 3.0,
        "score_histogram": [
            {
                "range": "55-59",
                "score_floor": 55,
                "trades": 10,
                "win_rate": 60.0,
                "expectancy": 0.5,
                "profit_factor": 1.5,
                "sharpe": 0.8,
                "alpha_class": "positive",
            },
            {
                "range": "60-64",
                "score_floor": 60,
                "trades": 20,
                "win_rate": 35.0,
                "expectancy": -0.3,
                "profit_factor": 0.7,
                "sharpe": -0.4,
                "alpha_class": "negative",
            },
        ],
        "symbol_breakdown": [
            {
                "symbol": "BTC",
                "trades": 15,
                "win_rate": 60.0,
                "expectancy": 0.6,
                "profit_factor": 1.4,
                "sharpe": 0.7,
                "alpha_class": "positive",
            },
            {
                "symbol": "DOGE",
                "trades": 15,
                "win_rate": 30.0,
                "expectancy": -0.5,
                "profit_factor": 0.6,
                "sharpe": -0.5,
                "alpha_class": "negative",
            },
        ],
        "recommended_score_floor": 55,
        "score_floor_confidence": "LOW",
    }

    lines = _alpha_digest_lines(burnin)
    full_text = "\n".join(lines)

    assert "30" in full_text  # total trades
    assert "55-59" in full_text  # meilleur bin
    assert "60-64" in full_text  # pire bin
    assert "BTC" in full_text  # meilleur symbole
    assert "DOGE" in full_text  # pire symbole
    assert "55" in full_text  # score floor recommandé


def test_tp_sl_breakdown_detects_tp_and_sl_variants() -> None:
    analytics = BurnInAnalytics()
    trades = [
        _trade(56, 1.0, 0.001, "take_profit"),
        _trade(56, 1.0, 0.001, "tp_hit"),
        _trade(56, -1.0, -0.001, "stop_loss"),
        _trade(56, -1.0, -0.001, "sl_hit"),
        _trade(56, 0.0, 0.0, "timeout"),
    ]

    report = analytics.build_report(trades)
    breakdown = report["tp_sl_breakdown"]

    assert breakdown["tp_closes"] == 2
    assert breakdown["sl_closes"] == 2
    assert breakdown["other_closes"] == 1
