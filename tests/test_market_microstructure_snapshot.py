from __future__ import annotations

import copy
import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from observability import market_microstructure_snapshot as producer
from observability.market_microstructure_contract import validate_microstructure_snapshot
from observability.operator_api import app as api
from observability.operator_api.market_microstructure_reader import MarketMicrostructureReader
from tests.cross_stack.generate_microstructure_fixture import NOW, lmi_source


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "lmi.json"
    path.write_text(json.dumps(lmi_source()), encoding="utf-8")
    return path


def publish(source, tmp_path, now=NOW):
    artifact = tmp_path / "projection.json"
    doc = producer.write_microstructure_snapshot(source, artifact, now_fn=lambda: now)
    return artifact, doc


def test_projection_preserves_real_zeros_missing_nulls_population_and_units(source, tmp_path):
    before = source.read_bytes()
    _, doc = publish(source, tmp_path)
    assert source.read_bytes() == before
    assert doc["coverage"] == {"requested": 3, "streamable": 2, "observed": 2, "unavailable": 1}
    btc, eth, missing = doc["rows"]
    assert btc["price"] == 65000
    assert btc["total_flow_usd"] == 17501
    assert btc["buy_pressure_pct"] == pytest.approx(71.43)
    assert btc["resistance"] == 12345.67  # no clamping to an invented 0–100 scale
    assert btc["flow_window_ms"] == 10_000
    assert btc["notable"] is True
    assert eth["price"] == eth["state_confidence"] == 0
    assert eth["buy_flow_usd"] is None and eth["price_change_bps"] is None
    assert missing["price"] is None and missing["availability"] == "UNAVAILABLE"
    assert "GHOSTUSDT" not in [r["symbol"] for r in doc["rows"]]
    assert "MUST_NOT_ESCAPE" not in json.dumps(doc)
    assert validate_microstructure_snapshot(doc)


def test_republication_does_not_rejuvenate_source_or_observation(source, tmp_path):
    artifact, _ = publish(source, tmp_path, NOW + 100)
    result = MarketMicrostructureReader(artifact, now_fn=lambda: NOW + 101).read()
    assert result.ok
    assert result.snapshot["source_age_s"] == 101
    assert result.snapshot["freshness_classification"] == "STALE"
    assert result.snapshot["rows"][0]["observation_age_s"] == 102
    assert result.snapshot["rows"][0]["freshness_classification"] == "STALE"


@pytest.mark.parametrize("offset,expected", [(0, "FRESH"), (15, "FRESH"), (15.001, "STALE"), (100, "STALE")])
def test_temporal_boundary(source, tmp_path, offset, expected):
    artifact, _ = publish(source, tmp_path)
    result = MarketMicrostructureReader(artifact, now_fn=lambda: NOW + offset).read()
    assert result.ok and result.snapshot["freshness_classification"] == expected
    assert result.snapshot["rows"][1]["freshness_classification"] == "STALE"
    assert result.snapshot["rows"][2]["freshness_classification"] == "NOT_AVAILABLE"
    assert validate_microstructure_snapshot(result.snapshot, transport=True)


def test_missing_observation_timestamp_and_unit_evidence_stay_unknown(source, tmp_path):
    doc = lmi_source()
    del doc["symbols"]["BTCUSDT"]["timestamp_ms"]
    del doc["contract_meta"]
    del doc["stats"]
    source.write_text(json.dumps(doc), encoding="utf-8")
    artifact, projected = publish(source, tmp_path)
    assert projected["unit_contract_source"] == "unknown"
    assert projected["unit_contract_degraded"] is None
    assert projected["pressure_field_count"] is None
    row = MarketMicrostructureReader(artifact, now_fn=lambda: NOW).read().snapshot["rows"][0]
    assert row["observed_at_utc"] is row["observation_age_s"] is None
    assert row["freshness_classification"] == "UNKNOWN"
    assert row["price"] == 65000


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(updated_at="2026-09-15T00:00:00Z"),
    lambda d: d.update(updated_at="2026-09-14T20:00:00"),
    lambda d: d.update(watchlist=["BTCUSDT", "BTCUSDT"]),
    lambda d: d.update(stream_watchlist=["OUTSIDEUSDT"]),
    lambda d: d.update(coverage={}),
    lambda d: d["symbols"]["BTCUSDT"].update(timestamp_ms=int((NOW + 1) * 1000)),
    lambda d: d["symbols"]["BTCUSDT"].update(timestamp_ms=True),
    lambda d: d["symbols"]["BTCUSDT"].update(price=True),
    lambda d: d["symbols"]["BTCUSDT"].update(state="buy_now"),
    lambda d: d["symbols"]["BTCUSDT"].update(symbol="OTHERUSDT"),
    lambda d: d["symbols"]["BTCUSDT"]["flow"].update(pressure_ratio=1.1),
    lambda d: d["symbols"]["BTCUSDT"]["flow"].update(buy_volume_usd=-1),
    lambda d: d["symbols"]["BTCUSDT"]["flow"].update(window_ms=True),
    lambda d: d["symbols"]["BTCUSDT"]["resistance"].update(fragility_score=2),
    lambda d: d.update(watchlist=[f"S{i}" for i in range(101)]),
])
def test_invalid_source_fails_without_replacing_old_projection(source, tmp_path, mutate):
    artifact, _ = publish(source, tmp_path)
    before = artifact.read_bytes()
    doc = lmi_source()
    mutate(doc)
    source.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises((ValueError, TypeError)):
        producer.write_microstructure_snapshot(source, artifact, now_fn=lambda: NOW)
    assert artifact.read_bytes() == before


def test_atomic_write_failure_preserves_previous_artifact_and_cleans_temp(source, tmp_path):
    artifact, _ = publish(source, tmp_path)
    before = artifact.read_bytes()
    with patch.object(producer.os, "replace", side_effect=OSError("failure")), pytest.raises(OSError):
        producer.write_microstructure_snapshot(source, artifact, now_fn=lambda: NOW)
    assert artifact.read_bytes() == before
    assert list(tmp_path.glob("*.tmp")) == []


def test_source_output_collision_is_refused(source):
    with pytest.raises(ValueError, match="COLLISION"):
        producer.write_microstructure_snapshot(source, source)


@pytest.mark.parametrize("kind", ["missing", "symlink", "directory", "fifo", "duplicate", "oversized", "nan", "bad_json", "list"])
def test_reader_artifact_errors_are_bounded_and_closed(tmp_path, kind):
    path = tmp_path / "bad.json"
    if kind == "symlink":
        target = tmp_path / "target"
        target.write_text("{}")
        path.symlink_to(target)
    elif kind == "directory":
        path.mkdir()
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind == "duplicate":
        path.write_text('{"x":1,"x":2}')
    elif kind == "oversized":
        path.write_bytes(b" " * 262145)
    elif kind == "nan":
        path.write_text('{"x":NaN}')
    elif kind == "bad_json":
        path.write_text("secret-fragment{")
    elif kind == "list":
        path.write_text("[]")
    result = MarketMicrostructureReader(path).read()
    assert not result.ok
    assert result.error_code in {"MICROSTRUCTURE_MISSING", "MICROSTRUCTURE_INVALID_ARTIFACT"}
    assert result.snapshot is None


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(entry=1),
    lambda d: d["rows"][0].update(entry_price=1),
    lambda d: d["rows"][0].update(notable=False),
    lambda d: d["rows"][0].update(total_flow_usd=0),
    lambda d: d["coverage"].update(observed=0),
    lambda d: d["rows"].append(copy.deepcopy(d["rows"][0])),
    lambda d: d["rows"][2].update(price=0),
])
def test_closed_contract_rejects_corruption(source, tmp_path, mutate):
    artifact, doc = publish(source, tmp_path)
    mutate(doc)
    artifact.write_text(json.dumps(doc))
    assert not validate_microstructure_snapshot(doc)
    assert MarketMicrostructureReader(artifact).read().error_code == "MICROSTRUCTURE_INVALID_SCHEMA"


def test_api_get_only_transports_artifact_never_invokes_producer(source, tmp_path):
    artifact, _ = publish(source, tmp_path)
    with patch.object(api, "_microstructure_reader", MarketMicrostructureReader(artifact, now_fn=lambda: NOW + 2)), patch.object(producer, "build_microstructure_snapshot", side_effect=AssertionError("API invoked producer")), TestClient(api.app) as client:
        response = client.get("/api/operator/v1/market-microstructure")
        assert response.status_code == 200
        assert response.json()["rows"][0]["freshness_classification"] == "FRESH"
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client, method)("/api/operator/v1/market-microstructure").status_code == 405


def test_api_missing_is_503_without_fabricated_counts(tmp_path):
    with patch.object(api, "_microstructure_reader", MarketMicrostructureReader(tmp_path / "missing")), TestClient(api.app) as client:
        response = client.get("/api/operator/v1/market-microstructure")
        assert response.status_code == 503
        assert response.json() == {"error_code": "MICROSTRUCTURE_MISSING"}


def test_reader_rejects_future_artifact(source, tmp_path):
    artifact, _ = publish(source, tmp_path)
    assert MarketMicrostructureReader(artifact, now_fn=lambda: NOW - 1).read().error_code == "MICROSTRUCTURE_FUTURE_TIMESTAMP"


def test_explicit_empty_population_and_pressure_field_zero_are_preserved(source, tmp_path):
    doc = lmi_source()
    doc.update(watchlist=[], stream_watchlist=[], coverage={}, stats={"events": 0})
    source.write_text(json.dumps(doc), encoding="utf-8")
    _, result = publish(source, tmp_path)
    assert result["rows"] == []
    assert result["pressure_field_count"] == 0
    assert result["coverage"] == {"requested": 0, "streamable": 0, "observed": 0, "unavailable": 0}


@pytest.mark.parametrize("kind", ["symlink", "oversized", "duplicate", "invalid_json"])
def test_producer_rejects_invalid_source_file_without_replacing_output(source, tmp_path, kind):
    artifact, _ = publish(source, tmp_path)
    before = artifact.read_bytes()
    if kind == "symlink":
        target = tmp_path / "source_copy"
        source.rename(target)
        source.symlink_to(target)
    elif kind == "oversized":
        source.write_bytes(b" " * 524289)
    elif kind == "duplicate":
        source.write_text('{"watchlist":[],"watchlist":["BTCUSDT"]}')
    else:
        source.write_text("bad json")
    with pytest.raises((OSError, ValueError)):
        producer.write_microstructure_snapshot(source, artifact, now_fn=lambda: NOW)
    assert artifact.read_bytes() == before


def test_source_offset_is_normalized_and_legacy_age_is_never_trusted(source, tmp_path):
    doc = lmi_source()
    doc["updated_at"] = "2026-09-14T22:00:00+02:00"
    doc["symbols"]["ETHUSDT"]["age_ms"] = 0
    doc["coverage"]["ETHUSDT"].update(status="LIVE", age_ms=0)
    source.write_text(json.dumps(doc), encoding="utf-8")
    artifact, result = publish(source, tmp_path)
    assert result["source_updated_at_utc"] == "2026-09-14T20:00:00.000Z"
    assert MarketMicrostructureReader(artifact, now_fn=lambda: NOW).read().snapshot["rows"][1]["freshness_classification"] == "STALE"


@pytest.mark.parametrize("field", ["source", "observation"])
def test_contract_rejects_negative_age_even_within_numeric_tolerance(source, tmp_path, field):
    artifact, doc = publish(source, tmp_path)
    doc["rows"][0]["observed_at_utc"] = doc["source_updated_at_utc"]
    artifact.write_text(json.dumps(doc))
    transport = MarketMicrostructureReader(artifact, now_fn=lambda: NOW).read().snapshot
    assert validate_microstructure_snapshot(transport, transport=True)
    if field == "source":
        transport["source_age_s"] = -1e-8
    else:
        transport["rows"][0]["observation_age_s"] = -1e-8
    assert not validate_microstructure_snapshot(transport, transport=True)
