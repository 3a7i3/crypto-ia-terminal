from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from observability.operator_api import app as api_app


def _valid_market(generated_at_utc="2026-09-14T20:00:00Z"):
    return {
        "schema_version": "1.0.0",
        "product": "CryptoRadar",
        "domain": "market",
        "authority": "OBSERVATIONAL_TELEMETRY",
        "mode": "OBSERVATION",
        "generated_at_utc": generated_at_utc,
        "source_updated_at_utc": "2026-09-14T19:59:30Z",
        "window_hours": 24,
        "min_confidence": 65.0,
        "packets_observed": 10,
        "market_regime": "bull_trend",
        "universe_size": 3,
        "actionable_count": 1,
        "watchlist_count": 1,
        "top_opportunities": [
            {
                "symbol": "BTC/USDT",
                "avg_confidence": 75.0,
                "max_confidence": 80.0,
                "n_signals": 2,
                "dominant_side": "LONG",
                "dominance_pct": 100.0,
                "regime": "bull_trend",
            }
        ],
    }


def _write(path: Path, doc) -> None:
    path.write_text(json.dumps(doc), encoding="utf-8")


def _client(path: Path, now_ts: float, stale_after_s: float = 90.0) -> TestClient:
    api_app.configure_market_reader(
        market_snapshot_path=path,
        stale_after_s=stale_after_s,
        now_fn=lambda: now_ts,
    )
    return TestClient(api_app.app)


def test_market_route_returns_validated_observational_payload(tmp_path):
    path = tmp_path / "market.json"
    _write(path, _valid_market())
    # 2026-09-14T20:00:30Z
    client = _client(path, 1_757_883_630.0)

    resp = client.get("/api/operator/v1/market")
    assert resp.status_code == 200
    body = resp.json()
    assert body["product"] == "CryptoRadar"
    assert body["authority"] == "OBSERVATIONAL_TELEMETRY"
    assert body["freshness_classification"] == "FRESH"
    assert body["snapshot_age_s"] >= 0
    assert body["top_opportunities"][0]["symbol"] == "BTC/USDT"


def test_market_route_preserves_stale_evidence_instead_of_fabricating_current(tmp_path):
    path = tmp_path / "market.json"
    _write(path, _valid_market())
    client = _client(path, 1_757_883_800.0, stale_after_s=90.0)

    resp = client.get("/api/operator/v1/market")
    assert resp.status_code == 200
    body = resp.json()
    assert body["freshness_classification"] == "STALE"
    assert body["packets_observed"] == 10


def test_market_route_missing_is_explicit_503(tmp_path):
    path = tmp_path / "missing.json"
    client = _client(path, 1_757_883_630.0)

    resp = client.get("/api/operator/v1/market")
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "MARKET_SNAPSHOT_MISSING"


def test_market_route_malformed_is_explicit_503(tmp_path):
    path = tmp_path / "market.json"
    path.write_text("{bad", encoding="utf-8")
    client = _client(path, 1_757_883_630.0)

    resp = client.get("/api/operator/v1/market")
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "MARKET_SNAPSHOT_MALFORMED_JSON"


def test_market_route_rejects_wrong_authority_and_execution_shaped_rows(tmp_path):
    path = tmp_path / "market.json"
    bad = _valid_market()
    bad["authority"] = "EXECUTION_AUTHORITY"
    _write(path, bad)
    client = _client(path, 1_757_883_630.0)

    resp = client.get("/api/operator/v1/market")
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "MARKET_SNAPSHOT_INVALID_SCHEMA"

    bad = _valid_market()
    bad["top_opportunities"][0]["entry"] = 123.0
    _write(path, bad)
    resp = client.get("/api/operator/v1/market")
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "MARKET_SNAPSHOT_INVALID_SCHEMA"


def test_market_route_has_no_mutating_methods(tmp_path):
    path = tmp_path / "market.json"
    _write(path, _valid_market())
    client = _client(path, 1_757_883_630.0)

    for method in ("post", "put", "patch", "delete"):
        resp = getattr(client, method)("/api/operator/v1/market")
        assert resp.status_code in (404, 405)
