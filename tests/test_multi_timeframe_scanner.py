from __future__ import annotations

from quant_hedge_ai.agents.market.multi_timeframe_scanner import MultiTimeframeScanner


class _StubScanner:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def scan(self) -> dict:
        self.calls += 1
        return self.payload


def test_scan_uses_cache_until_refresh_window():
    mtf = MultiTimeframeScanner(symbols=["BTC/USDT"], timeframes=["4h", "1d"], refresh_every=3)
    stub_payload = {"history": {"BTC/USDT": [{"source": "stub"}]}, "candles": {}}
    stub_4h = _StubScanner(stub_payload)
    stub_1d = _StubScanner(stub_payload)
    mtf._scanners = {"4h": stub_4h, "1d": stub_1d}

    first = mtf.scan(cycle=1)
    second = mtf.scan(cycle=2)

    assert first["BTC/USDT"]["4h"][0]["source"] == "stub"
    assert second == first
    assert stub_4h.calls == 1
    assert stub_1d.calls == 1


def test_merge_base_injects_one_hour_series():
    merged = MultiTimeframeScanner.merge_base(
        {"BTC/USDT": {"4h": [{"close": 1.0}], "1d": [{"close": 2.0}]}},
        "BTC/USDT",
        [{"close": 3.0}],
    )

    assert merged["1h"][0]["close"] == 3.0
    assert merged["4h"][0]["close"] == 1.0
    assert merged["1d"][0]["close"] == 2.0
