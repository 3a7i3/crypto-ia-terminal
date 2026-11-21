import hashlib
import json

from fastapi.testclient import TestClient

from observability.operator_api import app as api
from observability.operator_api.derivatives_positioning_reader import DerivativesPositioningReader
from tests.derivatives_positioning.positioning_fixture import AS_OF_MS, build

ROUTE = "/api/operator/v1/derivatives-positioning"


def reader(tmp_path, **kw):
    data, roster = build(tmp_path / "state", tmp_path / "roster.json")
    return DerivativesPositioningReader(str(data), str(roster), now_fn=lambda: AS_OF_MS / 1000, **kw)


def legs(snap):
    return {leg["venue"]: leg for leg in snap["legs"]}


def test_snapshot_keeps_units_provenance_freshness_and_reasons(tmp_path):
    res = reader(tmp_path).read()
    assert res.ok, res.error_code
    s = res.snapshot
    assert s["product"] == "MarketDerivativesPositioning" and s["execution_authority"] is False
    assert s["evidence_kind"] == "SYNTHETIC"
    a = legs(s)["exchange_a"]["latest"]["observation"]
    assert a["units"]["open_interest"] == "CONTRACTS" and a["units"]["funding_interval_s"] == 28800
    assert a["provenance"]["source"] == "synthetic:exchange_a/ticker"
    assert a["freshness"]["status"] == "FRESH" and a["freshness"]["age_ms"] == 30_000
    assert legs(s)["exchange_d"]["latest"]["reason"] == "NO_OBSERVATION"
    b = legs(s)["exchange_b"]["latest"]["observation"]
    assert {"field": "spot_reference", "reason": "SPOT_REFERENCE_NOT_QUALIFIED"} in b["unavailable_fields"]


def test_partial_coverage_and_non_comparable_contracts(tmp_path):
    s = reader(tmp_path).read().snapshot
    oi = {v: {w["window_s"]: w for w in leg["oi_change"]} for v, leg in legs(s).items()}
    assert all(w["status"] == "AVAILABLE" for w in oi["exchange_a"].values())
    assert oi["exchange_b"][3600]["reason"] == "INSUFFICIENT_COVERAGE"
    assert oi["exchange_b"][86400]["status"] == "AVAILABLE"
    assert oi["exchange_c"][3600]["status"] == "AVAILABLE"
    assert oi["exchange_c"][14400]["reason"] == "CONTRACT_SIZES_DIFFER"
    assert {w["reason"] for w in oi["exchange_d"].values()} == {"NO_COMPARABLE_POINT_AT_END"}
    pair = {(p["a"].split(":")[0], p["b"].split(":")[0]): p for p in s["pairs"]}
    assert pair[("exchange_a", "exchange_b")]["open_interest"]["reason"] == "OPEN_INTEREST_UNITS_DIFFER"
    assert pair[("exchange_a", "exchange_b")]["funding"]["reason"] == "FUNDING_INTERVALS_DIFFER"
    assert pair[("exchange_a", "exchange_c")]["open_interest"]["reason"] == "CONTRACT_SIZES_DIFFER"
    assert pair[("exchange_a", "exchange_d")]["open_interest"]["reason"] == "LEG_WITHOUT_OBSERVATION"


def test_chart_series_only_when_comparable_and_aligned(tmp_path):
    chart = reader(tmp_path).read().snapshot["chart"]
    series = {row["leg_id"].split(":")[0]: row for row in chart["series"]}
    assert series["exchange_a"]["status"] == "AVAILABLE" and len(series["exchange_a"]["points"]) == 288  # (as_of - 24 h, as_of]
    assert series["exchange_a"]["oi_unit"] == "CONTRACTS" and series["exchange_a"]["price_unit"] == "USDT"
    assert series["exchange_b"]["status"] == "AVAILABLE"  # 8 missing slots of 289: coverage above 0.8
    assert series["exchange_c"]["reason"] == "CONTRACT_SIZES_DIFFER" and series["exchange_c"]["points"] == []
    assert series["exchange_d"]["reason"] == "NO_OBSERVATION"
    assert chart["reference_leg_id"].startswith("exchange_a")


def test_reader_is_read_only_and_errors_are_typed(tmp_path, monkeypatch):
    r = reader(tmp_path)
    db = tmp_path / "state" / "positioning.sqlite3"
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    assert r.read().ok and r.read().ok
    # No byte of the database changes. SQLite may create its WAL index (-shm/-wal) to read
    # a WAL database; those hold no observation (see runbook, lot 2).
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    wal = tmp_path / "state" / "positioning.sqlite3-wal"
    assert not wal.exists() or wal.stat().st_size == 0
    for var in ("DIR", "ROSTER", "POLICY"):
        monkeypatch.delenv("OPERATOR_DERIVATIVES_POSITIONING_" + var, raising=False)
    assert DerivativesPositioningReader().read().error_code == "DERIVATIVES_POSITIONING_NOT_CONFIGURED"
    roster = tmp_path / "roster.json"
    assert DerivativesPositioningReader(str(tmp_path / "absent"), str(roster)).read().error_code \
        == "DERIVATIVES_POSITIONING_STORAGE_DIRECTORY_MISSING"
    empty = tmp_path / "empty"
    empty.mkdir()
    assert DerivativesPositioningReader(str(empty), str(roster)).read().error_code \
        == "DERIVATIVES_POSITIONING_STORAGE_EMPTY_NOT_INITIALISED"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"evidence_kind": "SYNTHETIC", "legs": []}))
    assert DerivativesPositioningReader(str(tmp_path / "state"), str(bad)).read().error_code \
        == "DERIVATIVES_POSITIONING_INVALID_CONFIGURATION"


def test_route_is_get_only_no_store_and_503(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_derivatives_positioning_reader", reader(tmp_path))
    with TestClient(api.app) as client:
        ok = client.get(ROUTE)
        assert ok.status_code == 200 and ok.headers["cache-control"] == "no-store"
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client, method)(ROUTE).status_code == 405
    monkeypatch.setattr(api, "_derivatives_positioning_reader", DerivativesPositioningReader("", ""))
    with TestClient(api.app) as client:
        r = client.get(ROUTE)
        assert r.status_code == 503 and r.json() == {"error_code": "DERIVATIVES_POSITIONING_NOT_CONFIGURED"}
