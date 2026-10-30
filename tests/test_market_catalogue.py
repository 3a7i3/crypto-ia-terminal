from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

from observability import market_radar_snapshot as producer
from observability.operator_api import app as api_app
from observability.operator_api.market_reader import validate_market_snapshot
from tests.cross_stack.generate_market_catalogue_fixture import (
    FIXED_NOW, generate_market_catalogue_fixture, packet, synthetic_packets,
)


def build(monkeypatch, packets=None, **kwargs):
    monkeypatch.setattr(producer.radar_bot, "load_recent_packets",
                        lambda _hours: synthetic_packets() if packets is None else packets)
    return producer.build_market_snapshot(
        include_catalogue=True, now_fn=lambda: FIXED_NOW,
        window_hours=kwargs.pop("window_hours", 4), top_n=20, **kwargs,
    )


def test_complete_catalogue_preserves_threshold_population_and_source_order(monkeypatch):
    doc = build(monkeypatch)
    assert validate_market_snapshot(doc)
    assert doc["schema_version"] == "1.1.0"
    assert doc["universe_size"] == 47
    assert doc["actionable_count"] == 46
    assert len(doc["top_opportunities"]) == 20
    c = doc["catalogue"]
    assert doc["top_opportunities"] == c["qualified_rows"][:20]
    assert c["qualified_rows"][-1]["symbol"] == "BTC/USDT"
    btc_all = next(r for r in c["rows"] if r["symbol"] == "BTC/USDT")
    assert btc_all["avg_confidence"] == 49
    assert btc_all["n_signals"] == 2
    assert c["qualified_rows"][-1]["avg_confidence"] == 68
    assert c["qualified_rows"][-1]["n_signals"] == 1
    assert "ETH/USDT" in [r["symbol"] for r in c["rows"]]
    assert "ETH/USDT" not in [r["symbol"] for r in c["qualified_rows"]]
    expected = producer.radar_bot.compute_symbol_stats(synthetic_packets()[:48], min_conf=65)
    assert [r["symbol"] for r in c["qualified_rows"]] == [r["symbol"] for r in expected]
    assert c["coverage"] == {
        "start_at_utc": "2026-10-30T08:00:00Z", "end_at_utc": "2026-10-30T12:00:00Z",
        "input_packets": 51, "included_packets": 48,
        "outside_window_packets": 1, "future_packets": 1, "unresolved_timestamp_packets": 1,
    }
    text = json.dumps(doc)
    for key in ["entry_price", "secret", "volume", "SYNTHETIC_MUST_NOT_ESCAPE"]:
        assert key not in text


@pytest.mark.parametrize("hours,expected", [(1, 2), (4, 3)])
def test_window_is_bounded_by_instants_inclusive_and_offsets_normalized(monkeypatch, hours, expected):
    packets = [
        packet("RECENT/USDT", 80, age=0),
        packet("ONEHOUR/USDT", 80, age=3600),
        packet("TWOHOURS/USDT", 80, age=7200),
        {**packet("OFFSET/USDT", 80), "created_at": "2026-10-30T15:00:00+03:00"},
        packet("OLDER/USDT", 80, age=5 * 3600),
        packet("FUTURE/USDT", 80, age=-.1),
        {**packet("UNDATED/USDT", 80), "created_at": None},
    ]
    doc = build(monkeypatch, packets, window_hours=hours)
    assert validate_market_snapshot(doc)
    assert doc["packets_observed"] == expected + 1
    assert doc["source_updated_at_utc"] == "2026-10-30T12:00:00Z"
    assert doc["catalogue"]["coverage"]["future_packets"] == 1
    assert doc["catalogue"]["coverage"]["unresolved_timestamp_packets"] == 1


def test_subsecond_end_is_not_rounded_into_false_future(monkeypatch):
    monkeypatch.setattr(producer.radar_bot, "load_recent_packets",
                        lambda _: [{**packet("BTC/USDT", 70), "created_at": "2026-10-30T12:00:00.100000Z"}])
    doc = producer.build_market_snapshot(include_catalogue=True, now_fn=lambda: FIXED_NOW + .2)
    assert doc["packets_observed"] == 1
    assert doc["generated_at_utc"] == "2026-10-30T12:00:00.200000Z"
    assert validate_market_snapshot(doc)


def test_empty_catalogue_has_no_fabricated_source_date(monkeypatch):
    doc = build(monkeypatch, [])
    assert validate_market_snapshot(doc)
    assert doc["source_updated_at_utc"] is None
    assert doc["catalogue"]["rows"] == []
    assert doc["catalogue"]["qualified_rows"] == []


@pytest.mark.parametrize("change", [
    lambda d: d.update(schema_version="1.0.0"),
    lambda d: d.update(schema_version=[]),
    lambda d: d["catalogue"].update(population="ALL_EXCHANGE_PAIRS"),
    lambda d: d["catalogue"]["rows"].pop(),
    lambda d: d["catalogue"]["rows"].append(d["catalogue"]["rows"][0]),
    lambda d: d["catalogue"]["qualified_rows"].reverse(),
    lambda d: d["catalogue"]["qualified_rows"][-1].update(symbol="UNOBSERVED/USDT"),
    lambda d: d["catalogue"]["rows"][0].update(entry_price=123),
    lambda d: d["catalogue"]["rows"][0].update(dominant_side=[]),
    lambda d: d["catalogue"]["rows"][0].update(n_signals=0),
    lambda d: d["catalogue"]["coverage"].update(included_packets=1),
    lambda d: d["catalogue"]["coverage"].update(input_packets=0),
    lambda d: d["catalogue"]["coverage"].update(outside_window_packets=True),
    lambda d: d["catalogue"]["coverage"].update(start_at_utc="2026-10-29T08:00:00Z"),
    lambda d: d["catalogue"]["coverage"].update(end_at_utc="2026-10-30T11:59:59Z"),
    lambda d: d.update(source_updated_at_utc="2026-10-30T12:00:01Z"),
])
def test_inconsistent_catalogue_is_rejected_without_partial_success(monkeypatch, change):
    doc = copy.deepcopy(build(monkeypatch))
    change(doc)
    assert not validate_market_snapshot(doc)


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), -1, True, "80"])
def test_invalid_packet_does_not_become_a_complete_catalogue(monkeypatch, confidence):
    with pytest.raises(ValueError):
        build(monkeypatch, [packet("BTC/USDT", confidence)])


def test_default_stays_legacy_and_catalogue_is_explicit(monkeypatch):
    monkeypatch.setattr(producer.radar_bot, "load_recent_packets", lambda _: synthetic_packets()[:48])
    doc = producer.build_market_snapshot(now_fn=lambda: FIXED_NOW)
    assert doc["schema_version"] == "1.0.0"
    assert "catalogue" not in doc
    assert validate_market_snapshot(doc)


def test_real_producer_reader_api_roundtrip_and_global_reader_restored(tmp_path):
    before = api_app.get_market_reader()
    result = generate_market_catalogue_fixture(tmp_path)
    assert api_app.get_market_reader() is before
    assert result["http_status"] == 200
    body = result["body"]
    assert body["freshness_classification"] == "STALE"
    assert body["snapshot_age_s"] == 120
    assert len(body["catalogue"]["rows"]) == 47
    assert len(body["catalogue"]["qualified_rows"]) == 46
    assert len(body["top_opportunities"]) == 20
    # The actual API refuses a catalogue whose population accounting is broken.
    path = tmp_path / "_producer" / "R_market_catalogue" / "market.json"
    doc = json.loads(path.read_text())
    doc["catalogue"]["coverage"]["input_packets"] = 0
    path.write_text(json.dumps(doc))
    try:
        api_app.configure_market_reader(market_snapshot_path=path, now_fn=lambda: FIXED_NOW)
        with TestClient(api_app.app) as client:
            response = client.get("/api/operator/v1/market")
        assert response.status_code == 503
        assert response.json()["error_code"] == "MARKET_SNAPSHOT_INVALID_SCHEMA"
    finally:
        api_app._market_reader = before


def test_cli_non_default_window_requires_catalogue_and_does_not_publish(monkeypatch):
    monkeypatch.setattr(producer, "publish_once", lambda *a, **k: pytest.fail("must not publish"))
    with pytest.raises(SystemExit) as error:
        producer.main(["--once", "--window-hours", "1"])
    assert error.value.code == 2
