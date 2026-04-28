"""Tests d'intégration — MarketScanner (synthétique + testnet Binance)."""

from __future__ import annotations

import pytest

from quant_hedge_ai.agents.market.ohlcv_validator import validate_candles

from .conftest import SKIP_TESTNET, SYMBOLS

pytestmark = pytest.mark.integration

# ── Helpers ───────────────────────────────────────────────────────────────────

REQUIRED_CANDLE_KEYS = {"open", "high", "low", "close", "volume", "source"}


def _assert_candle_structure(candle: dict) -> None:
    for key in REQUIRED_CANDLE_KEYS:
        assert key in candle, f"Clé manquante : {key}"
    assert candle["high"] >= candle["low"]
    assert candle["open"] > 0
    assert candle["close"] > 0
    assert candle["volume"] >= 0


# ── Mode synthétique (pas de réseau) ─────────────────────────────────────────


class TestMarketScannerSynthetic:
    def test_scan_returns_expected_structure(self, scanner_synthetic):
        result = scanner_synthetic.scan()
        assert "candles" in result
        assert "history" in result

    def test_scan_returns_all_symbols(self, scanner_synthetic):
        result = scanner_synthetic.scan()
        for sym in SYMBOLS:
            assert sym in result["history"], f"{sym} absent de l'historique"

    def test_snapshot_candle_has_required_keys(self, scanner_synthetic):
        result = scanner_synthetic.scan()
        for candle in result["candles"]:
            _assert_candle_structure(candle)

    def test_history_has_enough_candles(self, scanner_synthetic):
        result = scanner_synthetic.scan()
        for sym in SYMBOLS:
            series = result["history"][sym]
            assert len(series) >= 50, f"{sym} : seulement {len(series)} bougies"

    def test_all_history_candles_valid(self, scanner_synthetic):
        result = scanner_synthetic.scan()
        for sym, series in result["history"].items():
            clean, report = validate_candles(series, symbol=sym)
            assert (
                report.dropped == 0
            ), f"{sym} : {report.dropped} bougie(s) invalide(s)"

    def test_data_quality_shows_synthetic_source(self, scanner_synthetic):
        scanner_synthetic.scan()
        quality = scanner_synthetic.data_quality()
        assert quality["synthetic"] > 0
        assert quality["real"] == 0

    def test_get_history_after_scan(self, scanner_synthetic):
        scanner_synthetic.scan()
        history = scanner_synthetic.get_history("BTCUSDT")
        assert len(history) >= 50

    def test_two_symbols_have_different_prices(self, scanner_synthetic):
        result = scanner_synthetic.scan()
        btc_close = result["history"]["BTCUSDT"][-1]["close"]
        eth_close = result["history"]["ETHUSDT"][-1]["close"]
        assert btc_close != eth_close

    def test_stats_accumulate_across_scans(self, scanner_synthetic):
        scanner_synthetic.scan()
        before = scanner_synthetic.data_quality()["synthetic"]
        scanner_synthetic.scan()
        after = scanner_synthetic.data_quality()["synthetic"]
        assert after > before  # chaque scan synthétique incrémente le compteur

    def test_series_last_candle_is_within_two_hours(self, scanner_synthetic):
        import time
        from datetime import datetime

        result = scanner_synthetic.scan()
        for series in result["history"].values():
            last_ts = series[-1].get("timestamp", "")
            dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            age = time.time() - dt.timestamp()
            assert age < 7200, f"Dernier candle trop vieux : {age:.0f}s"

    def test_circuit_breaker_state_closed(self, scanner_synthetic):
        scanner_synthetic.scan()
        quality = scanner_synthetic.data_quality()
        assert quality["circuit_state"] == "closed"


# ── Mode testnet Binance (nécessite clés API) ─────────────────────────────────


class TestMarketScannerTestnet:
    @SKIP_TESTNET
    def test_scan_returns_real_data(self, scanner_testnet):
        result = scanner_testnet.scan()
        assert "history" in result
        for sym in SYMBOLS:
            assert sym in result["history"]

    @SKIP_TESTNET
    def test_real_candles_have_valid_structure(self, scanner_testnet):
        result = scanner_testnet.scan()
        for sym, series in result["history"].items():
            assert len(series) > 0, f"{sym} : aucune bougie réelle"
            _assert_candle_structure(series[-1])

    @SKIP_TESTNET
    def test_real_ratio_is_positive(self, scanner_testnet):
        scanner_testnet.scan()
        quality = scanner_testnet.data_quality()
        assert quality["real"] > 0
        assert quality["real_ratio"] > 0.0

    @SKIP_TESTNET
    def test_real_data_passes_ohlcv_validation(self, scanner_testnet):
        result = scanner_testnet.scan()
        for sym, series in result["history"].items():
            clean, report = validate_candles(series, symbol=sym)
            assert report.dropped == 0, f"{sym} : {report.reasons}"
