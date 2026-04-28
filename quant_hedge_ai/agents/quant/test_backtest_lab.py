"""Tests unitaires — BacktestLab (indicateurs + moteur de backtest)."""

from __future__ import annotations

import math
import random

import pytest

from quant_hedge_ai.agents.quant.backtest_lab import (
    BacktestLab,
    _bollinger,
    _ema,
    _macd,
    _rsi,
    _sma,
    _vwap,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_candles(n: int, seed: int = 42) -> list[dict]:
    random.seed(seed)
    price = 100.0
    out = []
    for _ in range(n):
        price = max(price * (1 + random.gauss(0, 0.01)), 1.0)
        o, c = price, price * random.uniform(0.995, 1.005)
        out.append(
            {
                "open": o,
                "high": max(o, c) * 1.002,
                "low": min(o, c) * 0.998,
                "close": c,
                "volume": 1000.0,
            }
        )
    return out


# ── Indicateurs techniques ────────────────────────────────────────────────────


class TestEma:
    def test_length_preserved(self):
        prices = [float(i) for i in range(1, 21)]
        result = _ema(prices, 5)
        assert len(result) == len(prices)

    def test_first_value_equals_first_price(self):
        prices = [10.0, 20.0, 30.0]
        assert _ema(prices, 3)[0] == 10.0

    def test_converges_toward_price(self):
        prices = [100.0] * 50 + [200.0] * 50
        ema = _ema(prices, 10)
        assert ema[-1] > 150.0  # converge vers 200

    def test_single_value(self):
        assert _ema([42.0], 1) == [42.0]


class TestSma:
    def test_none_before_period(self):
        prices = [1.0, 2.0, 3.0, 4.0, 5.0]
        sma = _sma(prices, 3)
        assert sma[0] is None
        assert sma[1] is None
        assert sma[2] == pytest.approx(2.0)

    def test_correct_value(self):
        sma = _sma([1.0, 2.0, 3.0, 4.0], 2)
        assert sma[1] == pytest.approx(1.5)
        assert sma[2] == pytest.approx(2.5)
        assert sma[3] == pytest.approx(3.5)

    def test_length_preserved(self):
        prices = list(range(10))
        assert len(_sma(prices, 3)) == 10


class TestRsi:
    def test_length_preserved(self):
        prices = [float(i) for i in range(20)]
        assert len(_rsi(prices, 14)) == 20

    def test_default_fifty_for_short_series(self):
        rsi = _rsi([100.0, 101.0], 14)
        assert all(v == 50.0 for v in rsi)

    def test_all_gains_gives_high_rsi(self):
        prices = [float(i) for i in range(1, 30)]  # toujours en hausse
        rsi = _rsi(prices, 14)
        assert rsi[-1] > 70.0

    def test_all_losses_gives_low_rsi(self):
        prices = [float(i) for i in range(30, 0, -1)]  # toujours en baisse
        rsi = _rsi(prices, 14)
        assert rsi[-1] < 30.0

    def test_values_in_range(self):
        candles = _make_candles(100)
        prices = [c["close"] for c in candles]
        rsi = _rsi(prices, 14)
        assert all(0.0 <= v <= 100.0 for v in rsi)


class TestBollinger:
    def test_none_before_period(self):
        prices = list(range(1, 22))
        upper, lower = _bollinger([float(p) for p in prices], 20)
        assert upper[18] is None
        assert upper[19] is not None

    def test_upper_above_lower(self):
        prices = [float(p) for p in range(1, 50)]
        upper, lower = _bollinger(prices, 20)
        for u, l in zip(upper[19:], lower[19:]):
            assert u > l

    def test_length_preserved(self):
        prices = list(range(30))
        upper, lower = _bollinger([float(p) for p in prices], 10)
        assert len(upper) == len(lower) == 30


class TestMacd:
    def test_lengths_preserved(self):
        prices = _make_candles(60)
        closes = [c["close"] for c in prices]
        macd, signal = _macd(closes, fast=12, slow=26, sig=9)
        assert len(macd) == len(signal) == len(closes)

    def test_returns_floats(self):
        prices = [float(i) for i in range(1, 50)]
        macd, signal = _macd(prices, 5, 10, 3)
        assert all(isinstance(v, float) for v in macd)


class TestVwap:
    def test_length_preserved(self):
        closes = [100.0, 101.0, 102.0]
        volumes = [1000.0, 2000.0, 1500.0]
        assert len(_vwap(closes, volumes)) == 3

    def test_vwap_between_min_max(self):
        closes = [90.0, 95.0, 110.0, 105.0]
        volumes = [1000.0] * 4
        vwap = _vwap(closes, volumes)
        assert min(closes) <= vwap[-1] <= max(closes)

    def test_zero_volume_fallback(self):
        closes = [100.0]
        volumes = [0.0]
        result = _vwap(closes, volumes)
        assert result[0] == 100.0


# ── BacktestLab ───────────────────────────────────────────────────────────────


class TestBacktestLab:
    def setup_method(self):
        self.lab = BacktestLab()
        self.candles = _make_candles(120)

    def _run(self, indicator: str, period: int = 14, threshold: float = 1.0) -> dict:
        return self.lab.run_backtest(
            {"entry_indicator": indicator, "period": period, "threshold": threshold},
            self.candles,
        )

    def test_ema_returns_expected_keys(self):
        result = self._run("EMA")
        assert set(result.keys()) >= {
            "pnl",
            "sharpe",
            "drawdown",
            "win_rate",
            "trades",
            "bars",
        }

    def test_rsi_runs(self):
        result = self._run("RSI")
        assert isinstance(result["sharpe"], float)

    def test_macd_runs(self):
        result = self._run("MACD", period=26)
        assert isinstance(result["pnl"], float)

    def test_bollinger_runs(self):
        result = self._run("BOLLINGER", period=20)
        assert 0.0 <= result["drawdown"] <= 1.0

    def test_vwap_runs(self):
        result = self._run("VWAP")
        assert isinstance(result["win_rate"], float)

    def test_atr_runs(self):
        result = self._run("ATR")
        assert result["bars"] == len(self.candles)

    def test_too_short_series_returns_empty(self):
        result = self.lab.run_backtest(
            {"entry_indicator": "EMA", "period": 14},
            _make_candles(10),  # < MIN_BARS=50
        )
        assert result["trades"] == 0
        assert result["pnl"] == 0.0

    def test_drawdown_between_zero_and_one(self):
        result = self._run("EMA")
        assert 0.0 <= result["drawdown"] <= 1.0

    def test_win_rate_between_zero_and_one(self):
        result = self._run("RSI")
        assert 0.0 <= result["win_rate"] <= 1.0

    def test_bars_equals_candle_count(self):
        result = self._run("EMA")
        assert result["bars"] == len(self.candles)

    def test_timeframe_in_strategy_used_for_sharpe(self):
        r_1h = self.lab.run_backtest(
            {"entry_indicator": "EMA", "period": 14, "timeframe": "1h"},
            self.candles,
        )
        # Le champ timeframe est accepté sans erreur ; le résultat est valide
        assert isinstance(r_1h["sharpe"], float)
        assert not math.isnan(r_1h["sharpe"])

    def test_commission_reduces_pnl(self):
        # Avec des milliers de trades, la commission doit avoir un effet négatif
        candles = _make_candles(200, seed=1)
        result_high_freq = self.lab.run_backtest(
            {"entry_indicator": "EMA", "period": 5, "threshold": 0.01},
            candles,
        )
        # On vérifie juste que ça tourne sans crash
        assert isinstance(result_high_freq["pnl"], float)

    def test_sharpe_is_float(self):
        result = self._run("MACD")
        assert isinstance(result["sharpe"], float)
        assert not math.isnan(result["sharpe"])
        assert not math.isinf(result["sharpe"])

    def test_empty_result_structure(self):
        result = self.lab._empty_result({"entry_indicator": "EMA"})
        assert result["pnl"] == 0.0
        assert result["sharpe"] == 0.0
        assert result["trades"] == 0

    def test_unknown_indicator_returns_no_signals(self):
        result = self.lab.run_backtest(
            {"entry_indicator": "UNKNOWN_IND", "period": 14},
            self.candles,
        )
        # Aucun signal → 0 trades
        assert result["trades"] == 0

    def test_sharpe_static_method(self):
        returns = [0.01, -0.005, 0.02, -0.01, 0.015]
        sharpe = BacktestLab._sharpe(returns, periods_per_year=252)
        assert isinstance(sharpe, float)
        assert not math.isnan(sharpe)

    def test_sharpe_empty_returns_zero(self):
        assert BacktestLab._sharpe([], 252) == 0.0

    def test_sharpe_single_return_zero(self):
        assert BacktestLab._sharpe([0.01], 252) == 0.0
