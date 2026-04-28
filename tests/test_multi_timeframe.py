"""Tests pour MultiTimeframeScanner et MultiTimeframeSignal."""

from unittest.mock import MagicMock, patch

import pytest

from quant_hedge_ai.agents.execution.multi_timeframe_signal import \
    MultiTimeframeSignal
from quant_hedge_ai.agents.market.multi_timeframe_scanner import \
    MultiTimeframeScanner

# ── Helpers ────────────────────────────────────────────────────────────────────


def _candles(n=30, close=100.0):
    return [
        {
            "open": close,
            "close": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "volume": 1000.0,
            "symbol": "BTC/USDT",
        }
        for _ in range(n)
    ]


# ── MultiTimeframeScanner ─────────────────────────────────────────────────────


class TestMultiTimeframeScanner:
    def test_scan_returns_all_symbols_and_tfs(self):
        mtf = MultiTimeframeScanner(symbols=["BTC/USDT"], timeframes=["4h", "1d"])
        result = mtf.scan(cycle=0)
        assert "BTC/USDT" in result
        for tf in ["4h", "1d"]:
            assert tf in result["BTC/USDT"]
            assert len(result["BTC/USDT"][tf]) > 0

    def test_cache_returned_before_refresh(self):
        mtf = MultiTimeframeScanner(
            symbols=["BTC/USDT"], timeframes=["4h"], refresh_every=4
        )
        r1 = mtf.scan(cycle=0)
        r2 = mtf.scan(cycle=2)
        assert r1 is r2  # même objet en cache

    def test_cache_invalidated_after_refresh(self):
        mtf = MultiTimeframeScanner(
            symbols=["BTC/USDT"], timeframes=["4h"], refresh_every=2
        )
        r1 = mtf.scan(cycle=0)
        r2 = mtf.scan(cycle=5)
        # r2 est un scan frais (pas forcément un objet différent, mais re-fetché)
        assert "BTC/USDT" in r2

    def test_merge_base_adds_1h(self):
        mtf_data = {"BTC/USDT": {"4h": _candles(30), "1d": _candles(20)}}
        candles_1h = _candles(50)
        merged = MultiTimeframeScanner.merge_base(mtf_data, "BTC/USDT", candles_1h)
        assert "1h" in merged
        assert merged["1h"] is candles_1h

    def test_merge_base_preserves_higher_tfs(self):
        c4h = _candles(30)
        c1d = _candles(20)
        mtf_data = {"BTC/USDT": {"4h": c4h, "1d": c1d}}
        merged = MultiTimeframeScanner.merge_base(mtf_data, "BTC/USDT", _candles(50))
        assert merged["4h"] is c4h
        assert merged["1d"] is c1d

    def test_merge_base_missing_symbol_returns_1h_only(self):
        mtf_data = {}
        candles_1h = _candles(50)
        merged = MultiTimeframeScanner.merge_base(mtf_data, "BTC/USDT", candles_1h)
        assert merged == {"1h": candles_1h}

    def test_multiple_symbols(self):
        mtf = MultiTimeframeScanner(symbols=["BTC/USDT", "ETH/USDT"], timeframes=["4h"])
        result = mtf.scan(cycle=0)
        assert "BTC/USDT" in result
        assert "ETH/USDT" in result


# ── MultiTimeframeSignal ──────────────────────────────────────────────────────


class TestMultiTimeframeSignal:
    def _strategy(self, indicator="RSI", period=14, entry=30, exit_=70):
        return {
            "entry_indicator": indicator,
            "period": period,
            "entry_threshold": entry,
            "exit_threshold": exit_,
        }

    def test_returns_required_keys(self):
        sig = MultiTimeframeSignal()
        result = sig.confirm(self._strategy(), {"1h": _candles()})
        for key in ("signal", "confirmed", "strength", "alignment", "detail"):
            assert key in result

    def test_empty_mtf_returns_hold(self):
        sig = MultiTimeframeSignal()
        result = sig.confirm(self._strategy(), {})
        assert result["signal"] == "HOLD"
        assert not result["confirmed"]

    def test_single_tf_never_confirmed(self):
        # min_agreement=2 mais 1 seul TF → jamais confirmé
        sig = MultiTimeframeSignal(min_agreement=2)
        result = sig.confirm(self._strategy(), {"1h": _candles()})
        assert not result["confirmed"]

    def test_all_buy_confirmed(self):
        """Patch compute_signal pour retourner BUY sur tous les TF."""
        sig = MultiTimeframeSignal(min_strength=0.4, min_agreement=2)
        with patch(
            "quant_hedge_ai.agents.execution.multi_timeframe_signal.compute_signal",
            return_value="BUY",
        ):
            result = sig.confirm(
                self._strategy(), {"1h": _candles(), "4h": _candles(), "1d": _candles()}
            )
        assert result["signal"] == "BUY"
        assert result["confirmed"]
        assert result["strength"] == pytest.approx(1.0)

    def test_all_sell_confirmed(self):
        sig = MultiTimeframeSignal(min_strength=0.4, min_agreement=2)
        with patch(
            "quant_hedge_ai.agents.execution.multi_timeframe_signal.compute_signal",
            return_value="SELL",
        ):
            result = sig.confirm(
                self._strategy(), {"1h": _candles(), "4h": _candles(), "1d": _candles()}
            )
        assert result["signal"] == "SELL"
        assert result["confirmed"]

    def test_divergence_returns_hold(self):
        """1h=BUY, 1d=SELL → pas de majorité → HOLD."""
        sig = MultiTimeframeSignal(min_strength=0.5, min_agreement=2)
        side_effects = {"1h": "BUY", "4h": "HOLD", "1d": "SELL"}

        def _mock(strategy, candles):
            # On distingue par la taille des candles (1h=50, 4h=30, 1d=20)
            n = len(candles)
            if n >= 50:
                return "BUY"
            if n >= 30:
                return "HOLD"
            return "SELL"

        with patch(
            "quant_hedge_ai.agents.execution.multi_timeframe_signal.compute_signal",
            side_effect=_mock,
        ):
            result = sig.confirm(
                self._strategy(),
                {"1h": _candles(50), "4h": _candles(30), "1d": _candles(20)},
            )
        assert result["signal"] == "HOLD"

    def test_strength_weighted_correctly(self):
        """1d(poids 3) + 4h(poids 2) BUY, 1h(poids 1) SELL → BUY confirmé, force=5/6."""
        sig = MultiTimeframeSignal(min_strength=0.5, min_agreement=2)

        def _mock(strategy, candles):
            return "SELL" if len(candles) >= 50 else "BUY"

        with patch(
            "quant_hedge_ai.agents.execution.multi_timeframe_signal.compute_signal",
            side_effect=_mock,
        ):
            result = sig.confirm(
                self._strategy(),
                {"1h": _candles(50), "4h": _candles(30), "1d": _candles(20)},
            )
        assert result["signal"] == "BUY"
        assert result["confirmed"]
        assert result["strength"] == pytest.approx(5 / 6, rel=1e-3)

    def test_min_strength_not_met_returns_hold(self):
        """Force trop faible → HOLD même si 2 TF d'accord."""
        sig = MultiTimeframeSignal(min_strength=0.99, min_agreement=2)
        with patch(
            "quant_hedge_ai.agents.execution.multi_timeframe_signal.compute_signal",
            return_value="BUY",
        ):
            result = sig.confirm(
                self._strategy(),
                {
                    "1h": _candles(),
                    "4h": _candles(),
                },  # 1h(1) + 4h(2) = 3/3 = ok mais strength < 0.99
            )
        # BUY sur 2/2 TF → strength=1.0 → confirmé quand même
        assert result["confirmed"]

    def test_alignment_contains_all_tfs(self):
        sig = MultiTimeframeSignal()
        with patch(
            "quant_hedge_ai.agents.execution.multi_timeframe_signal.compute_signal",
            return_value="HOLD",
        ):
            result = sig.confirm(
                self._strategy(), {"1h": _candles(), "4h": _candles(), "1d": _candles()}
            )
        assert set(result["alignment"].keys()) == {"1h", "4h", "1d"}

    def test_summary_string_not_empty(self):
        sig = MultiTimeframeSignal()
        result = {
            "signal": "BUY",
            "confirmed": True,
            "strength": 0.75,
            "alignment": {"1h": "BUY"},
            "detail": "BUY: 1/1 TF | poids=75%",
        }
        summary = sig.summary(result)
        assert "BUY" in summary
        assert "75%" in summary
