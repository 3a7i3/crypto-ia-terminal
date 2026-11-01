from dataclasses import replace
import http.client
import json
import socket
import pytest

from observability.market_venues.public_us import (
    USPlan,
    USSpec,
    USFake,
    PublicUSHTTPS,
    bindings,
    qualify_metadata,
    decode_book,
    run_capture,
    verify_capture,
    DECISION,
)
from observability.market_venues.pilot.capture import Capture
from observability.market_venues.pilot.synthetic import SyntheticClock


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("Real networking is forbidden in unit tests")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def sample(spec):
    clock = SyntheticClock()
    before = clock.sample()
    response = USFake(clock).fetch(spec)
    return Capture(spec, response, before, clock.sample())


def change(capture, callback):
    d = json.loads(capture.response.body)
    callback(d)
    return replace(
        capture, response=replace(capture.response, body=json.dumps(d).encode())
    )


def setup(tmp_path):
    parent = tmp_path / "market-venue-pilot-runs"
    parent.mkdir(mode=0o700)
    clock = SyntheticClock()
    return parent, clock


def run(parent, clock, transport=None, plan=None):
    return run_capture(
        transport or USFake(clock),
        parent,
        plan=plan or USPlan(),
        source_sha="0" * 40,
        clock=clock,
        sleeper=clock.sleep,
        run_id="test",
    )


def test_explicit_usd_roster_and_seven_public_urls():
    p = USPlan().document()
    assert p["maximum_requests"] == 15
    assert p["app_publication"] is False and p["economic_metrics"] is None
    assert len(p["endpoints"]) == 7
    assert {r["host"] for r in p["endpoints"]} == {
        "www.bitstamp.net",
        "api.coinbase.com",
    }
    assert len(bindings()) == 4 and all(
        b["quote_asset_id"] == "USD" and b["market_kind"] == "SPOT" for b in bindings()
    )
    assert USSpec("bitstamp", "metadata").target == "/api/v2/markets/?entity=US_INC"


@pytest.mark.parametrize(
    "spec",
    [
        USSpec("bybit", "book", "BTC"),
        USSpec("bitstamp", "order", "BTC"),
        USSpec("coinbase_advanced", "book", "BTC-USD&secret=x"),
        USSpec("bitstamp", "metadata", "BTC"),
        USSpec("coinbase_advanced", "metadata", "UBTC"),
        USSpec("coinbase_advanced", "book", "USDT"),
    ],
)
def test_no_alternate_venue_currency_order_or_query_injection(spec):
    with pytest.raises(ValueError):
        spec.document()


@pytest.mark.parametrize(
    "field,value",
    [
        ("cycles", 4),
        ("cycles", True),
        ("interval_ms", 1),
        ("duration_ms", 30001),
        ("max_response_bytes", 512001),
        ("max_run_bytes", 1),
        ("request_timeout_ms", 3001),
    ],
)
def test_caps_cannot_expand(field, value):
    with pytest.raises(ValueError):
        replace(USPlan(), **{field: value}).validate()


@pytest.mark.parametrize(
    "venue,base",
    [(v, b) for v in ("coinbase_advanced", "bitstamp") for b in ("BTC", "ETH")],
)
def test_native_metadata_requires_exact_product_and_currency(venue, base):
    spec = USSpec(venue, "metadata", base if venue == "coinbase_advanced" else None)
    c = sample(spec)
    assert qualify_metadata(c, base, USPlan()) is None
    bad = change(
        c,
        lambda d: (
            d
            if venue == "coinbase_advanced"
            else next(x for x in d if x["base_currency"] == base)
        ).__setitem__(
            "quote_currency_id" if venue == "coinbase_advanced" else "counter_currency",
            "USDT",
        ),
    )
    assert qualify_metadata(bad, base, USPlan()) == "METADATA_IDENTITY_MISMATCH"


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "offline"),
        ("is_disabled", True),
        ("trading_disabled", True),
        ("cancel_only", True),
        ("auction_mode", True),
        ("product_type", "FUTURE"),
        ("product_type", "UNKNOWN_PRODUCT_TYPE"),
        ("base_currency_id", "UBTC"),
    ],
)
def test_coinbase_disabled_futures_unknown_and_alias_are_not_admitted(field, value):
    c = sample(USSpec("coinbase_advanced", "metadata", "BTC"))
    bad = change(c, lambda d: d.__setitem__(field, value))
    assert qualify_metadata(bad, "BTC", USPlan()) is not None


def test_bitstamp_duplicate_metadata_is_not_silently_selected():
    c = sample(USSpec("bitstamp", "metadata"))
    assert (
        qualify_metadata(change(c, lambda d: d.append(dict(d[0]))), "BTC", USPlan())
        == "METADATA_POPULATION_MISMATCH"
    )


@pytest.mark.parametrize("venue", ["coinbase_advanced", "bitstamp"])
def test_observed_quotes_preserve_native_time_and_never_claim_economic_qualification(
    venue,
):
    c = sample(USSpec(venue, "book", "BTC"))
    row = decode_book(c, as_of=c.after.utc, plan=USPlan())
    assert row["status"] == "OBSERVED" and row["bid"] is not None
    assert row["native_time"] and row["native_time_utc"] != ""
    assert row["age_status"] == "WITHIN_BUDGET"
    assert (
        row["economic_metrics"] is None
        and row["exchange_clock_qualification"] == "NOT_PROVEN"
    )
    assert row["reason"] == "TEMPORAL_QUALIFICATION_PENDING"


@pytest.mark.parametrize("delta,expected", [(6000, "STALE"), (-1000, "FUTURE")])
def test_native_time_is_not_renewed_from_receipt(delta, expected):
    c = sample(USSpec("bitstamp", "book", "BTC"))
    clock = SyntheticClock()
    clock.wall = c.after.utc_ns
    clock.advance(delta)
    row = decode_book(c, as_of=clock.sample().utc, plan=USPlan())
    assert (
        row["age_status"] == expected
        and row["native_time"] == json.loads(c.response.body)["microtimestamp"]
    )


@pytest.mark.parametrize("venue", ["coinbase_advanced", "bitstamp"])
def test_crossed_books_and_missing_native_times_refused(venue):
    c = sample(USSpec(venue, "book", "BTC"))

    def cross(d):
        if venue == "bitstamp":
            d["bids"][0][0] = "999"
        else:
            d["pricebook"]["bids"][0]["price"] = "999"

    assert (
        decode_book(change(c, cross), as_of=c.after.utc, plan=USPlan())["status"]
        == "NOT_AVAILABLE"
    )

    def missing(d):
        (d if venue == "bitstamp" else d["pricebook"]).pop(
            "microtimestamp" if venue == "bitstamp" else "time"
        )

    assert (
        decode_book(change(c, missing), as_of=c.after.utc, plan=USPlan())["reason"]
        == "INVALID_NATIVE_BOOK"
    )


def test_default_transport_cannot_connect():
    with pytest.raises(RuntimeError, match="NETWORK_DISABLED"):
        PublicUSHTTPS().fetch(
            USSpec("bitstamp", "book", "BTC"), timeout_ms=1000, max_bytes=512000
        )
    with pytest.raises(ValueError):
        PublicUSHTTPS(network_enabled=True, decision_reference="https://evil.invalid")


def fake_http(monkeypatch, status=200, body=b"{}", encoding="identity"):
    calls = []

    class Reply:
        def __init__(self):
            self.status = status

        def getheaders(self):
            return [("Content-Type", "application/json"), ("Set-Cookie", "private")]

        def getheader(self, name, default=None):
            return encoding if name == "Content-Encoding" else default

        def read(self, n):
            calls.append(("read", n))
            return body

    class Connection:
        def __init__(self, host, port, **kw):
            calls.append(("connection", host, port))
            assert kw["context"].check_hostname is True

        def request(self, method, target, headers):
            calls.append((method, target, headers))

        def getresponse(self):
            return Reply()

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(http.client, "HTTPSConnection", Connection)
    return calls


def test_public_https_checks_tls_and_drops_cookies(monkeypatch):
    calls = fake_http(monkeypatch)
    r = PublicUSHTTPS(network_enabled=True, decision_reference=DECISION).fetch(
        USSpec("coinbase_advanced", "book", "BTC"), timeout_ms=1000, max_bytes=512000
    )
    assert calls[0] == ("connection", "api.coinbase.com", 443)
    assert calls[1][0] == "GET" and "Authorization" not in calls[1][2]
    assert r.headers == {"content-type": "application/json"}


@pytest.mark.parametrize("status", [302, 401, 403, 429, 503])
def test_transport_does_not_retry_or_follow_redirects(monkeypatch, status):
    calls = fake_http(monkeypatch, status=status)
    r = PublicUSHTTPS(network_enabled=True, decision_reference=DECISION).fetch(
        USSpec("bitstamp", "book", "BTC"), timeout_ms=1000, max_bytes=1024
    )
    assert r.status == status and len([c for c in calls if c[0] == "connection"]) == 1


def test_oversize_and_compressed_response_never_get_decoded(monkeypatch):
    fake_http(monkeypatch, body=b"x" * 1025)
    t = PublicUSHTTPS(network_enabled=True, decision_reference=DECISION)
    r = t.fetch(USSpec("bitstamp", "book", "BTC"), timeout_ms=1000, max_bytes=1024)
    assert (
        r.error == "RESPONSE_TOO_LARGE" and r.complete is False and len(r.body) == 1024
    )
    fake_http(monkeypatch, encoding="gzip")
    r = t.fetch(USSpec("bitstamp", "book", "BTC"), timeout_ms=1000, max_bytes=1024)
    assert r.error == "CONTENT_ENCODING_REFUSED" and r.body is None


def test_complete_synthetic_pipeline_with_exact_fifteen_receipts_and_four_sources_per_cycle(
    tmp_path,
):
    parent, clock = setup(tmp_path)
    result = run(parent, clock)
    assert (
        result["status"] == "COMPLETED"
        and result["requests_attempted"] == 15
        and result["cycles_captured"] == 3
    )
    assert result["app_publication"] is False and result["economic_metrics"] is None
    proof = verify_capture(parent / "test")
    assert proof["receipts"] == 15 and proof["pending_ordinals"] == []
    for i in (1, 2, 3):
        d = json.loads((parent / f"test/cycle-{i:04d}.json").read_text())
        assert len(d["sources"]) == 4 and all(
            r["status"] == "OBSERVED" for r in d["sources"]
        )
        assert all(r["age_as_of_utc"] == d["as_of_utc"] for r in d["sources"])


@pytest.mark.parametrize("status", [403, 429, 302])
def test_first_refusal_stops_run_and_preserves_raw_response(tmp_path, status):
    parent, clock = setup(tmp_path)

    class Refuse(USFake):
        def fetch(self, spec, **kw):
            return replace(super().fetch(spec, **kw), status=status)

    result = run(parent, clock, Refuse(clock))
    assert (
        result["requests_attempted"] == 1
        and result["cycles_captured"] == 0
        and result["status"] == "STOPPED"
    )
    assert (parent / "test/response-0001.bin").exists()
    assert verify_capture(parent / "test")["run_status"] == "STOPPED"


def test_bad_native_metadata_stops_before_books(tmp_path):
    parent, clock = setup(tmp_path)

    class Wrong(USFake):
        def fetch(self, spec, **kw):
            r = super().fetch(spec, **kw)
            if spec.venue == "coinbase_advanced" and spec.purpose == "metadata":
                d = json.loads(r.body)
                d["product_type"] = "FUTURE"
                r = replace(r, body=json.dumps(d).encode())
            return r

    result = run(parent, clock, Wrong(clock))
    assert (
        result["cycles_captured"] == 0
        and result["stopped_reason"] == "METADATA_NOT_QUALIFIED"
    )
    assert result["requests_attempted"] == 3


def test_interruption_and_byte_budget_remain_incomplete(tmp_path):
    parent, clock = setup(tmp_path)
    result = run(parent, clock, plan=USPlan(duration_ms=1))
    assert result["status"] == "INCOMPLETE" and result["requests_attempted"] == 1
    assert verify_capture(parent / "test")["cycles"] == 0
    other = tmp_path / "second"
    other.mkdir()
    parent, clock = setup(other)

    class Huge(USFake):
        def fetch(self, spec, **kw):
            r = super().fetch(spec, **kw)
            return replace(r, body=r.body + b" " * 12000)

    result = run(parent, clock, Huge(clock), plan=USPlan(max_run_bytes=16384))
    assert (
        result["status"] == "INCOMPLETE"
        and verify_capture(parent / "test")["pending_ordinals"]
    )


def test_tampered_raw_and_forged_completed_run_are_refused(tmp_path):
    parent, clock = setup(tmp_path)
    run(parent, clock)
    raw = parent / "test/response-0001.bin"
    raw.chmod(0o600)
    raw.write_bytes(b"{}")
    raw.chmod(0o400)
    with pytest.raises(ValueError, match="RAW_HASH_CHANGED"):
        verify_capture(parent / "test")


@pytest.mark.parametrize("venue", ["coinbase_advanced", "bitstamp"])
def test_native_http200_error_stops_before_any_new_request(tmp_path, venue):
    parent, clock = setup(tmp_path)

    class Refuse(USFake):
        def fetch(self, spec, **kw):
            r = super().fetch(spec, **kw)
            if spec.purpose == "book" and spec.venue == venue:
                return replace(
                    r,
                    body=json.dumps(
                        {"error": "RATE_LIMIT"}
                        if venue == "coinbase_advanced"
                        else {"response_code": "400.002"}
                    ).encode(),
                )
            return r

    r = run(parent, clock, Refuse(clock))
    assert r["stopped_reason"] == "NATIVE_API_REFUSED" and r["requests_attempted"] == (
        4 if venue == "coinbase_advanced" else 5
    )
    assert verify_capture(parent / "test")["receipts"] == r["requests_attempted"]


def test_age_is_computed_at_complete_cycle_not_the_earlier_receipt(tmp_path):
    parent, clock = setup(tmp_path)
    run(parent, clock, plan=USPlan(max_age_ms=1))
    d = json.loads((parent / "test/cycle-0001.json").read_text())
    assert [r["age_status"] for r in d["sources"]] == [
        "STALE",
        "STALE",
        "STALE",
        "WITHIN_BUDGET",
    ]


def test_clock_jump_stops_with_all_sources_explicitly_unqualified(tmp_path):
    parent, clock = setup(tmp_path)

    class Jump(USFake):
        def fetch(self, spec, **kw):
            r = super().fetch(spec, **kw)
            if spec.purpose == "book":
                self.clock.wall += 1000000000
            return r

    r = run(parent, clock, Jump(clock))
    assert r["stopped_reason"] == "CLOCK_JUMP" and r["cycles_captured"] == 1
    doc = json.loads((parent / "test/cycle-0001.json").read_text())
    assert all(s["status"] == "NOT_AVAILABLE" for s in doc["sources"])


def test_forged_completion_is_refused(tmp_path):
    parent, clock = setup(tmp_path)
    run(parent, clock, plan=USPlan(duration_ms=1))
    p = parent / "test/run-result.json"
    r = json.loads(p.read_text())
    r["status"] = "COMPLETED"
    p.chmod(0o600)
    p.write_text(json.dumps(r))
    p.chmod(0o400)
    with pytest.raises(ValueError, match="FALSE_COMPLETE_RUN"):
        verify_capture(parent / "test")
