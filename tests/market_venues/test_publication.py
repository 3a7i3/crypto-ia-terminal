from copy import deepcopy
from dataclasses import replace
import json
import pytest
from fastapi.testclient import TestClient
from observability.market_venues.decoders import unavailable
from observability.market_venues.publication import build_publication
from observability.market_venues.schema import validate_publication
from observability.operator_api.venue_comparison_reader import VenueComparisonReader
from observability.operator_api import app as api
from tests.market_venues.support import NOW, binding, decode, pilot, raw


def document():
    bindings, observations = pilot()
    return build_publication(
        bindings,
        observations,
        as_of=NOW,
        max_age_ms=5000,
        max_skew_ms=100,
        evidence_kind="SYNTHETIC",
    )


def test_compatible_instruments_and_missing_timestamps_remain_distinct():
    doc = document()
    assert validate_publication(doc)
    assert len(doc["groups"]) == 5 and doc["source_counts"] == {
        "expected": 12,
        "supplied": 12,
        "available": 6,
    }
    group = doc["groups"][0]
    assert [r["venue"] for r in group["rows"]] == ["bybit", "okx", "mexc", "kucoin"]
    pair = next(
        p
        for p in group["comparisons"]
        if p["reference_venue"] == "bybit" and p["other_venue"] == "okx"
    )
    assert pair["status"] == "AVAILABLE" and pair["mid_basis_bps"] == "29.97002997"
    assert all(
        r["status"] == "NOT_AVAILABLE"
        for r in group["rows"]
        if r["venue"] in ("mexc", "kucoin")
    )
    assert doc["valid_until_utc"].endswith("12:00:04.880000Z")


def test_roster_is_explicit_missing_source_stays_visible():
    a, b = binding("bybit"), binding("okx")
    doc = build_publication(
        [a, b],
        [decode(a)],
        as_of=NOW,
        max_age_ms=5000,
        max_skew_ms=100,
        evidence_kind="SYNTHETIC",
    )
    missing = doc["groups"][0]["rows"][1]
    assert missing["bid"] is None and missing["reason"] == "SOURCE_NOT_SUPPLIED"
    assert missing["received_at_utc"] is None and doc["source_counts"]["supplied"] == 1


@pytest.mark.parametrize("case", ["duplicate", "foreign", "changed"])
def test_observation_identity_cannot_change_the_binding_roster(case):
    b = binding("bybit")
    d = decode(b)
    items = (
        [d, d]
        if case == "duplicate"
        else [decode(binding("okx"))]
        if case == "foreign"
        else [replace(d, binding=replace(b, mapping_id="CHANGED"))]
    )
    with pytest.raises(ValueError):
        build_publication(
            [b],
            items,
            as_of=NOW,
            max_age_ms=5000,
            max_skew_ms=100,
            evidence_kind="SYNTHETIC",
        )


def test_unsynchronised_books_keep_internal_metrics_but_refuse_basis():
    a, b = binding("bybit"), binding("okx")
    d = decode(b, raw("okx", time_ms=1793447999500))
    doc = build_publication(
        [a, b],
        [decode(a), d],
        as_of=NOW,
        max_age_ms=5000,
        max_skew_ms=100,
        evidence_kind="SYNTHETIC",
    )
    assert all(r["status"] == "AVAILABLE" for r in doc["groups"][0]["rows"])
    assert all(
        p["status"] == "NOT_AVAILABLE" and p["reason"] == "EVENTS_NOT_SYNCHRONIZED"
        for p in doc["groups"][0]["comparisons"]
    )


def test_raw_extra_fields_never_escape_into_presentation():
    b = binding("bybit")
    j = json.loads(raw("bybit"))
    j["apiKey"] = "SYNTHETIC_SECRET_DO_NOT_COPY"
    doc = build_publication(
        [b],
        [decode(b, json.dumps(j).encode())],
        as_of=NOW,
        max_age_ms=5000,
        max_skew_ms=100,
        evidence_kind="SYNTHETIC",
    )
    assert "SYNTHETIC_SECRET_DO_NOT_COPY" not in json.dumps(
        doc
    ) and "apiKey" not in json.dumps(doc)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(execution_authority=True),
        lambda d: d.update(extra="unexpected"),
        lambda d: d["source_counts"].update(expected=0),
        lambda d: d["groups"][0]["rows"].append(deepcopy(d["groups"][0]["rows"][0])),
        lambda d: d["groups"][0]["comparisons"].pop(),
        lambda d: d["groups"][0]["rows"][0]["source"].update(endpoint_id="wrong"),
        lambda d: d["groups"][0]["rows"][0].update(spread_bps="NaN"),
        lambda d: d["groups"][0].update(instrument_id="0" * 24),
        lambda d: d["groups"][0]["instrument"].update(quote_asset_id="USD"),
        lambda d: d["quality_policy"].update(max_age_ms=True),
        lambda d: d["groups"][0]["rows"][1].update(observer_clock_id="OTHER_CLOCK"),
        lambda d: d["groups"][0]["comparisons"][0].update(event_skew_ms="0"),
    ],
)
def test_closed_schema_refuses_corruption(mutate):
    doc = document()
    mutate(doc)
    assert not validate_publication(doc)


def write(tmp_path, doc=None):
    p = tmp_path / "venues.json"
    p.write_text(json.dumps(document() if doc is None else doc))
    return p


def test_reader_marks_quote_expiry_without_recalculating_values(tmp_path):
    p = write(tmp_path)
    fresh = VenueComparisonReader(p, now_fn=lambda: NOW.timestamp() + 0.1).read()
    stale = VenueComparisonReader(p, now_fn=lambda: NOW.timestamp() + 4.881).read()
    assert fresh.ok and fresh.snapshot["freshness_classification"] == "FRESH"
    assert stale.ok and stale.snapshot["freshness_classification"] == "STALE"
    for key in document():
        assert fresh.snapshot[key] == stale.snapshot[key]


def test_reader_missing_unconfigured_and_symlink_are_honest(tmp_path, monkeypatch):
    monkeypatch.delenv("OPERATOR_VENUE_COMPARISON_PATH", raising=False)
    assert VenueComparisonReader().read().error_code.endswith("NOT_CONFIGURED")
    assert (
        VenueComparisonReader(tmp_path / "missing")
        .read()
        .error_code.endswith("MISSING")
    )
    p = write(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(p)
    assert VenueComparisonReader(link).read().error_code.endswith("INVALID_PATH")
    assert VenueComparisonReader(tmp_path).read().error_code.endswith("INVALID_PATH")


def test_reader_refuses_duplicate_keys_future_and_large_artifact(tmp_path):
    p = tmp_path / "venues.json"
    p.write_text('{"x":1,"x":2}')
    assert VenueComparisonReader(p).read().error_code.endswith("MALFORMED_JSON")
    p = write(tmp_path)
    assert (
        VenueComparisonReader(p, now_fn=lambda: NOW.timestamp() - 1)
        .read()
        .error_code.endswith("FUTURE")
    )
    p.write_bytes(b"x" * 4_000_001)
    assert VenueComparisonReader(p).read().error_code.endswith("TOO_LARGE")


@pytest.mark.parametrize("clock", [float("nan"), float("inf"), 10**100])
def test_bad_reader_clock_is_not_fresh(tmp_path, clock):
    assert (
        VenueComparisonReader(write(tmp_path), now_fn=lambda: clock)
        .read()
        .error_code.endswith("INVALID_READER_CLOCK")
    )


def test_api_get_is_transport_only_and_mutations_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(
        api,
        "_venue_comparison_reader",
        VenueComparisonReader(write(tmp_path), now_fn=lambda: NOW.timestamp() + 0.1),
    )
    with TestClient(api.app) as client:
        response = client.get("/api/operator/v1/venue-comparison")
        assert (
            response.status_code == 200
            and response.headers["cache-control"] == "no-store"
        )
        assert response.json()["groups"] == document()["groups"]
        for method in ["POST", "PUT", "PATCH", "DELETE"]:
            assert (
                client.request(method, "/api/operator/v1/venue-comparison").status_code
                == 405
            )
    monkeypatch.setattr(
        api, "_venue_comparison_reader", VenueComparisonReader(tmp_path / "missing")
    )
    with TestClient(api.app) as client:
        assert client.get("/api/operator/v1/venue-comparison").status_code == 503


def test_failed_source_without_payload_remains_visible_and_is_not_counted_as_received():
    a, b = binding("bybit"), binding("okx")
    failure = unavailable(
        b, received_at=NOW, clock_id="SYNTHETIC_CLOCK", reason="CAPTURE_FAILED"
    )
    doc = build_publication(
        [a, b],
        [decode(a), failure],
        as_of=NOW,
        max_age_ms=5000,
        max_skew_ms=100,
        evidence_kind="SYNTHETIC",
    )
    row = doc["groups"][0]["rows"][1]
    assert row["reason"] == "CAPTURE_FAILED" and row["source"]["payload_sha256"] is None
    assert doc["source_counts"] == {"expected": 2, "supplied": 1, "available": 1}
    assert all(
        p["status"] == "NOT_AVAILABLE" and p["mid_basis_bps"] is None
        for p in doc["groups"][0]["comparisons"]
    )
