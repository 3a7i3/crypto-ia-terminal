from dataclasses import replace
import json
import pytest
from observability.market_venues.pilot.plan import PilotPlan, RequestSpec, roster
from observability.market_venues.pilot.capture import (
    Capture,
    metadata_problem,
    probe_result,
)
from observability.market_venues.pilot.synthetic import (
    SyntheticClock,
    SyntheticTransport,
)


def capture(spec):
    clock = SyntheticClock()
    before = clock.sample()
    response = SyntheticTransport(clock).fetch(spec, timeout_ms=3000, max_bytes=65536)
    return Capture(spec, response, before, clock.sample())


def changed(c, mutate):
    doc = json.loads(c.response.body)
    mutate(doc)
    return replace(c, response=replace(c.response, body=json.dumps(doc).encode()))


def test_explicit_roster_is_closed_and_not_inferred_from_responses():
    rows = roster()
    assert [(b.venue, b.native_symbol) for b in rows] == [
        ("bybit", "BTCUSDT"),
        ("okx", "BTC-USDT"),
        ("bybit", "ETHUSDT"),
        ("okx", "ETH-USDT"),
    ]
    assert all(
        b.instrument.market_kind == "SPOT" and b.instrument.quote_asset_id == "USDT"
        for b in rows
    )
    assert len({b.mapping_sha256 for b in rows}) == 4
    doc = PilotPlan().document()
    assert (
        doc["activation_status"] == "PREPARED_NOT_AUTHORISED"
        and doc["maximum_requests"] == 724
    )
    assert doc["credentials"] is False and doc["trading_authority"] is False


@pytest.mark.parametrize(
    "spec",
    [
        RequestSpec("mexc", "book", "BTCUSDT"),
        RequestSpec("bybit", "order", "BTCUSDT"),
        RequestSpec("bybit", "book", "BTCUSDT&api_key=x"),
        RequestSpec("okx", "book", "BTC-USDT-SWAP"),
        RequestSpec("okx", "time", "BTC-USDT"),
    ],
)
def test_non_public_or_changed_requests_are_refused(spec):
    with pytest.raises(ValueError):
        spec.validate()


@pytest.mark.parametrize(
    "field,value",
    [
        ("cycles", 121),
        ("cycles", True),
        ("interval_ms", 1),
        ("duration_ms", 600001),
        ("max_age_ms", 5001),
        ("max_skew_ms", 501),
        ("max_clock_jump_ms", -1),
        ("request_timeout_ms", 3001),
        ("max_response_bytes", 65537),
        ("max_run_bytes", 4096),
    ],
)
def test_operator_plan_cannot_silently_expand_limits(field, value):
    with pytest.raises(ValueError):
        replace(PilotPlan(), **{field: value}).validate()


@pytest.mark.parametrize("binding", roster())
def test_native_metadata_is_qualified_separately_from_book(binding):
    assert (
        metadata_problem(
            capture(RequestSpec(binding.venue, "metadata", binding.native_symbol)),
            binding,
            PilotPlan(),
        )
        is None
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("baseCoin", "UBTC"),
        ("quoteCoin", "USD"),
        ("status", "PreLaunch"),
        ("symbol", "ETHUSDT"),
    ],
)
def test_wrong_asset_currency_state_or_symbol_refused(field, value):
    b = roster()[0]
    c = capture(RequestSpec(b.venue, "metadata", b.native_symbol))
    c = changed(c, lambda d: d["result"]["list"][0].__setitem__(field, value))
    assert metadata_problem(c, b, PilotPlan()) == "METADATA_IDENTITY_OR_STATUS_MISMATCH"


def test_wrong_product_and_invalid_precision_refused():
    b = roster()[1]
    c = capture(RequestSpec(b.venue, "metadata", b.native_symbol))
    assert (
        metadata_problem(
            changed(c, lambda d: d["data"][0].__setitem__("instType", "SWAP")),
            b,
            PilotPlan(),
        )
        == "METADATA_IDENTITY_OR_STATUS_MISMATCH"
    )
    assert (
        metadata_problem(
            changed(c, lambda d: d["data"][0].__setitem__("lotSz", "NaN")),
            b,
            PilotPlan(),
        )
        == "INVALID_METADATA"
    )


@pytest.mark.parametrize("venue", ["bybit", "okx"])
def test_server_clock_interval_is_recorded_without_rewriting_native_time(venue):
    c = capture(RequestSpec(venue, "time"))
    before = c.response.body
    result = probe_result(c, PilotPlan())
    assert result["status"] == "AVAILABLE" and result["round_trip_ms"] == "20"
    assert "NOT_PHYSICAL_CLOCK_CERTIFICATION" in result["assumption"]
    assert c.response.body == before


def test_native_clock_offset_and_type_errors_are_explicit():
    c = capture(RequestSpec("okx", "time"))
    late = changed(
        c,
        lambda d: d["data"][0].__setitem__("ts", str(c.after.utc_ns // 1000000 + 1000)),
    )
    assert probe_result(late, PilotPlan())["reason"] == "CLOCK_OFFSET_BOUND_EXCEEDED"
    assert (
        probe_result(
            changed(c, lambda d: d["data"][0].__setitem__("ts", True)), PilotPlan()
        )["reason"]
        == "INVALID_TIME_PROBE"
    )


def test_utc_and_monotonic_jumps_and_latency_are_not_qualified():
    c = capture(RequestSpec("bybit", "time"))
    assert (
        probe_result(
            replace(c, after=replace(c.after, utc_ns=c.after.utc_ns + 1000000000)),
            PilotPlan(),
        )["reason"]
        == "CLOCK_JUMP"
    )
    assert (
        probe_result(
            replace(
                c,
                after=replace(
                    c.after,
                    utc_ns=c.after.utc_ns + 2000000000,
                    monotonic_ns=c.after.monotonic_ns + 2000000000,
                ),
            ),
            PilotPlan(),
        )["reason"]
        == "ROUND_TRIP_TOO_LONG"
    )


@pytest.mark.parametrize(
    "status,reason",
    [
        (429, "ACCESS_OR_RATE_LIMIT_REFUSED"),
        (403, "ACCESS_OR_RATE_LIMIT_REFUSED"),
        (302, "ACCESS_OR_RATE_LIMIT_REFUSED"),
        (500, "HTTP_UNAVAILABLE"),
    ],
)
def test_access_and_rate_limits_are_not_decoded_as_quotes(status, reason):
    c = capture(RequestSpec("bybit", "time"))
    c = replace(c, response=replace(c.response, status=status))
    assert probe_result(c, PilotPlan())["reason"] == reason


def test_documented_plan_matches_source_and_cli_has_no_network_mode(capsys):
    from pathlib import Path
    from observability.market_venues.pilot.__main__ import main

    root = Path(__file__).resolve().parents[3]
    stored = json.loads(
        (
            root / "docs/research/market_multi_venue_pilot_539/PILOT_PLAN.json"
        ).read_text()
    )
    assert stored == PilotPlan().document()
    main(["--check-plan"])
    assert json.loads(capsys.readouterr().out) == stored
    with pytest.raises(SystemExit) as error:
        main(["--network"])
    assert error.value.code == 2
