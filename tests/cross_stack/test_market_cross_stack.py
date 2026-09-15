from __future__ import annotations

import json

from tests.cross_stack.generate_market_fixture import generate_market_fixture


def test_market_real_producer_artifact_reader_api_roundtrip(tmp_path):
    result = generate_market_fixture(tmp_path)

    assert result["http_status"] == 200
    body = result["body"]
    assert body["product"] == "CryptoRadar"
    assert body["domain"] == "market"
    assert body["authority"] == "OBSERVATIONAL_TELEMETRY"
    assert body["mode"] == "OBSERVATION"
    assert body["freshness_classification"] == "FRESH"
    assert body["snapshot_age_s"] == 30.0
    assert body["packets_observed"] == 3
    assert body["actionable_count"] == 1
    assert body["top_opportunities"][0]["symbol"] == "BTC/USDT"

    proof = result["_proof"]
    assert proof["producer_authority"] == "OBSERVATIONAL_TELEMETRY"
    assert proof["producer_product"] == "CryptoRadar"
    assert proof["producer_rows"] == 1
    assert proof["artifact_is_regular_file"] is True

    # Upstream deterministic evidence contains entry/SL/TP. The actual
    # producer projection and API must prove those fields cannot escape.
    serialized = json.dumps(body).lower()
    for forbidden in (
        '"entry"',
        '"entry_price"',
        '"sl"',
        '"stop_loss"',
        '"tp"',
        '"take_profit"',
        '"trade_allowed"',
        '"is_actionable"',
        '"token"',
        '"password"',
        '"secret"',
    ):
        assert forbidden not in serialized
