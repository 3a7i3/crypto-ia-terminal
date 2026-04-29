"""Migration tests replacing legacy whale/liquidity orphan coverage."""

from __future__ import annotations

from quant_hedge_ai.agents.whales import WhaleRadar


def test_whale_radar_emits_threshold_alert_without_random_transfer(monkeypatch):
    monkeypatch.setattr("quant_hedge_ai.agents.whales.random.random", lambda: 0.99)

    radar = WhaleRadar(threshold_usd=1_000_000)
    result = radar.scan("BTCUSDT", volume=25.0, price=50_000.0)

    assert result["symbol"] == "BTCUSDT"
    assert result["alerts"] == ["WHALE_BUY: 1.2M USD"]
    assert result["threat_level"] == "medium"


def test_whale_radar_combines_notional_and_transfer_alerts(monkeypatch):
    monkeypatch.setattr("quant_hedge_ai.agents.whales.random.random", lambda: 0.01)
    monkeypatch.setattr(
        "quant_hedge_ai.agents.whales.random.uniform", lambda a, b: 2_400_000.0
    )
    monkeypatch.setattr(
        "quant_hedge_ai.agents.whales.random.choice", lambda values: values[-1]
    )

    radar = WhaleRadar(threshold_usd=1_000_000)
    result = radar.scan("ETHUSDT", volume=500.0, price=3_000.0)

    assert result["alerts"] == [
        "WHALE_BUY: 1.5M USD",
        "OUTFLOW_FROM_EXCHANGE: 2.4M USD",
    ]
    assert result["threat_level"] == "high"


def test_whale_radar_low_activity_has_no_alerts(monkeypatch):
    monkeypatch.setattr("quant_hedge_ai.agents.whales.random.random", lambda: 0.99)

    radar = WhaleRadar(threshold_usd=1_000_000)
    result = radar.scan("SOLUSDT", volume=100.0, price=100.0)

    assert result["alerts"] == []
    assert result["threat_level"] == "low"


def test_whale_radar_pattern_analysis_handles_empty_and_large_transactions():
    radar = WhaleRadar(threshold_usd=1_000_000)

    assert radar.analyze_pattern([]) == {
        "pattern": "insufficient_data",
        "anomaly_score": 0.0,
    }

    report = radar.analyze_pattern(
        [
            {"amount": 2_000_000},
            {"amount": 3_000_000},
            {"amount": 500},
            {"amount": 4_000_000},
        ]
    )
    assert report == {
        "pattern": "whale_accumulation",
        "anomaly_score": 0.75,
        "large_tx_count": 3,
    }
