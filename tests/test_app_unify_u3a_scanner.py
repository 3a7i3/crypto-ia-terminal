"""Compare safe scanner projection with historical ranking on identical evidence."""
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest

from observability import market_radar_snapshot as producer
from observability.operator_api.market_reader import validate_market_snapshot
from tests.cross_stack.generate_scanner_fixture import generate_scanner_fixture, scanner_packets


def historical_stats(packets, min_conf):
    # Execute just the historical pure ranking function. Importing the dashboard
    # would initialize its authentication/transport, outside this source test.
    module = ast.parse(Path("scripts/dashboard_api.py").read_text(encoding="utf-8"))
    function = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "compute_stats")
    scope = {"defaultdict": defaultdict}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "historical_compute_stats", "exec"), scope)
    return scope["compute_stats"](packets, min_conf)


def test_same_population_threshold_and_order_match_historical_scanner(monkeypatch):
    packets = scanner_packets() + [
        {"symbol": "S00/USDT", "confidence": 66, "side": "SHORT", "regime": "bull"},
        {"symbol": "BELOW/USDT", "confidence": 64, "side": "LONG", "regime": "bull"},
    ]
    monkeypatch.setattr(producer.radar_bot, "load_recent_packets", lambda _hours: packets)
    doc = producer.build_market_snapshot()
    historical = historical_stats(packets, doc["min_confidence"])[:50]
    safe = [{key: row[key] for key in producer._ALLOWED_ROW_KEYS} for row in historical]
    assert doc["top_opportunities"] == safe
    assert len(safe) == 50
    assert doc["actionable_count"] == 60
    assert doc["universe_size"] == 61
    assert doc["min_confidence"] == 65
    assert doc["schema_version"] == "1.0.0"
    assert validate_market_snapshot(doc)


def test_scanner_real_producer_reader_api_roundtrip(tmp_path):
    result = generate_scanner_fixture(tmp_path)
    assert result["http_status"] == 200
    doc = result["body"]
    assert len(doc["top_opportunities"]) == 50
    assert doc["actionable_count"] == doc["universe_size"] == 60
    assert doc["freshness_classification"] == "FRESH"
    assert doc["top_opportunities"][25]["symbol"] == "S25/USDT"
    for row in doc["top_opportunities"]:
        assert set(row) == producer._ALLOWED_ROW_KEYS


@pytest.mark.parametrize("kind", ["duplicate", "too_many_rows", "count_over_universe"])
def test_reader_rejects_incoherent_coverage(monkeypatch, kind):
    monkeypatch.setattr(producer.radar_bot, "load_recent_packets", lambda _hours: scanner_packets())
    doc = producer.build_market_snapshot()
    if kind == "duplicate":
        doc["top_opportunities"][1] = doc["top_opportunities"][0]
    elif kind == "too_many_rows":
        doc["actionable_count"] = 49
    else:
        doc["universe_size"] = 59
    assert not validate_market_snapshot(doc)
