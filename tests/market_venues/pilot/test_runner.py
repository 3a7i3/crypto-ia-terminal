from dataclasses import replace
import hashlib
import json
import pytest
from observability.market_venues.pilot.plan import PilotPlan
from observability.market_venues.pilot.runner import run_bounded_pilot
from observability.market_venues.pilot.synthetic import (
    SyntheticClock,
    SyntheticTransport,
)
from observability.market_venues.pilot.store import RunStore
from observability.market_venues.schema import validate_publication
from observability.operator_api.venue_comparison_reader import VenueComparisonReader


def setup(tmp_path, transport_type=SyntheticTransport):
    root = tmp_path / "market-venue-pilot-runs"
    root.mkdir(mode=0o700)
    clock = SyntheticClock()
    transport = transport_type(clock)
    return root, clock, transport


def run(root, clock, transport, **kwargs):
    return run_bounded_pilot(
        transport,
        root,
        source_sha="0" * 40,
        plan=kwargs.pop("plan", PilotPlan(cycles=2)),
        clock=clock,
        sleeper=clock.sleep,
        run_id="case",
        **kwargs,
    )


def test_captures_are_persisted_with_independent_intents_before_valid_publication(
    tmp_path,
):
    root, clock, transport = setup(tmp_path)
    result = run(root, clock, transport)
    folder = root / "case"
    assert (
        result["status"] == "COMPLETED"
        and result["cycles_published"] == 2
        and result["requests_attempted"] == 16
    )
    assert len(transport.calls) == 16
    for receipt in folder.glob("*.receipt.json"):
        record = json.loads(receipt.read_text())
        ordinal = record["ordinal"]
        assert (
            hashlib.sha256((folder / record["raw_file"]).read_bytes()).hexdigest()
            == record["raw_sha256"]
        )
        assert (
            hashlib.sha256(
                (folder / f"attempt-{ordinal:04d}.intent.json").read_bytes()
            ).hexdigest()
            == record["intent_sha256"]
        )
        assert record["request"]["method"] == "GET" and record["body_complete"] is True
        assert (folder / record["raw_file"]).stat().st_mode & 0o777 == 0o400
    doc = json.loads((folder / "latest.json").read_text())
    assert validate_publication(doc)
    assert doc["evidence_kind"] == "SYNTHETIC" and doc["source_counts"] == {
        "expected": 4,
        "supplied": 4,
        "available": 4,
    }
    assert len(doc["groups"]) == 2 and len(list(folder.glob("publication-*.json"))) == 2
    assert doc["groups"][0]["comparisons"][0]["mid_basis_bps"] == "29.97002997"
    reader = VenueComparisonReader(
        folder / "latest.json", now_fn=lambda: clock.wall / 1000000000
    )
    assert reader.read().snapshot["freshness_classification"] == "FRESH"
    clock.advance(6000)
    stale = reader.read().snapshot
    assert (
        stale["freshness_classification"] == "STALE"
        and stale["groups"] == doc["groups"]
    )


def mutator(callback):
    class Modified(SyntheticTransport):
        def fetch(self, spec, **kwargs):
            response = super().fetch(spec, **kwargs)
            return callback(self, spec, response)

    return Modified


def test_metadata_mismatch_preserves_roster_and_does_not_fetch_books(tmp_path):
    def change(t, s, r):
        if s.purpose == "metadata" and s.venue == "bybit":
            doc = json.loads(r.body)
            doc["result"]["list"][0]["baseCoin"] = "UBTC"
            return replace(r, body=json.dumps(doc).encode())
        return r

    root, clock, transport = setup(tmp_path, mutator(change))
    result = run(root, clock, transport)
    assert result["stopped_reason"] == "METADATA_NOT_QUALIFIED" and all(
        s.purpose == "metadata" for s in transport.calls
    )
    doc = json.loads((root / "case/latest.json").read_text())
    assert doc["source_counts"] == {"expected": 4, "supplied": 0, "available": 0}
    assert doc["valid_until_utc"] is None and len(doc["groups"]) == 2


@pytest.mark.parametrize("status", [403, 429, 302])
def test_access_denial_stops_without_retry_or_alternate_host(tmp_path, status):
    root, clock, transport = setup(
        tmp_path, mutator(lambda t, s, r: replace(r, status=status))
    )
    result = run(root, clock, transport)
    assert (
        result["stopped_reason"] == "ACCESS_OR_RATE_LIMIT_REFUSED"
        and len(transport.calls) == 1
    )
    assert (
        json.loads((root / "case/latest.json").read_text())["source_counts"][
            "available"
        ]
        == 0
    )


def test_invalid_book_never_borrows_a_previous_or_other_symbol_quote(tmp_path):
    def change(t, s, r):
        if s.purpose == "book" and s.venue == "bybit" and s.native_symbol == "BTCUSDT":
            return replace(r, body=b'{"retCode":0,"result":{"s":"ETHUSDT"}}')
        return r

    root, clock, transport = setup(tmp_path, mutator(change))
    run(root, clock, transport)
    doc = json.loads((root / "case/latest.json").read_text())
    row = doc["groups"][0]["rows"][0]
    assert (
        row["reason"] == "INVALID_NATIVE_SNAPSHOT"
        and row["bid"] is None
        and row["source"]["payload_sha256"] is not None
    )
    assert doc["source_counts"]["available"] == 3


def test_clock_probe_failure_keeps_native_evidence_but_suppresses_all_pair_metrics(
    tmp_path,
):
    root, clock, transport = setup(
        tmp_path,
        mutator(
            lambda t, s, r: (
                replace(r, status=500)
                if s.purpose == "time" and s.venue == "bybit"
                else r
            )
        ),
    )
    run(root, clock, transport)
    doc = json.loads((root / "case/latest.json").read_text())
    row = doc["groups"][0]["rows"][0]
    assert (
        row["bid"] == "100"
        and row["observed_at_utc"] is not None
        and row["reason"] == "CLOCK_PROBE_NOT_QUALIFIED"
    )
    assert doc["source_counts"]["available"] == 2
    for group in doc["groups"]:
        for pair in group["comparisons"]:
            assert (
                pair["status"] == "NOT_AVAILABLE"
                and pair["mid_basis_bps"] is None
                and pair["buy_reference_sell_other_gross_bps"] is None
            )


def test_native_timestamp_is_never_refreshed_from_receipt_time(tmp_path):
    def change(t, s, r):
        if s.purpose == "book":
            doc = json.loads(r.body)
            if s.venue == "bybit":
                doc["result"]["ts"] -= 60000
            else:
                doc["data"][0]["ts"] = str(int(doc["data"][0]["ts"]) - 60000)
            return replace(r, body=json.dumps(doc).encode())
        return r

    root, clock, transport = setup(tmp_path, mutator(change))
    run(root, clock, transport)
    doc = json.loads((root / "case/latest.json").read_text())
    assert doc["source_counts"]["available"] == 0 and all(
        row["reason"] == "STALE" for g in doc["groups"] for row in g["rows"]
    )


def test_wall_clock_jump_stops_and_never_publishes_qualified_prices(tmp_path):
    def change(t, s, r):
        if s.purpose == "book" and s.venue == "okx":
            t.clock.wall += 1000000000
        return r

    root, clock, transport = setup(tmp_path, mutator(change))
    result = run(root, clock, transport)
    assert result["stopped_reason"] == "CLOCK_JUMP" and result["cycles_published"] == 1
    doc = json.loads((root / "case/latest.json").read_text())
    assert doc["source_counts"]["available"] == 0 and doc["valid_until_utc"] is None


def test_duration_and_storage_limits_leave_an_explicit_incomplete_receipt(tmp_path):
    root, clock, transport = setup(tmp_path)
    result = run(root, clock, transport, plan=PilotPlan(cycles=2, duration_ms=1))
    assert (
        result["status"] == "INCOMPLETE"
        and result["stopped_reason"] == "DURATION_LIMIT"
        and result["requests_attempted"] == 1
    )
    assert not (root / "case/latest.json").exists()

    def large(t, s, r):
        doc = json.loads(r.body)
        doc["padding"] = "x" * 7000
        return replace(r, body=json.dumps(doc).encode())

    other = tmp_path / "other"
    other.mkdir()
    root, clock, transport = setup(other, mutator(large))
    result = run(root, clock, transport, plan=PilotPlan(cycles=2, max_run_bytes=16384))
    assert (
        result["status"] == "INCOMPLETE"
        and result["stopped_reason"] == "STORAGE_BUDGET_EXHAUSTED"
    )
    assert (root / "case/run-result.json").exists() and not (
        root / "case/latest.json"
    ).exists()


def test_symlinks_active_path_names_and_wrong_permissions_are_refused(tmp_path):
    parent = tmp_path / "market-venue-pilot-runs"
    parent.mkdir(mode=0o777)
    parent.chmod(0o777)
    with pytest.raises(ValueError, match="OWNER_OR_MODE"):
        RunStore(parent, "case", max_bytes=16384)
    parent.chmod(0o700)
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError):
        RunStore(link / "market-venue-pilot-runs", "case", max_bytes=16384)
    blocked = tmp_path / "presentation" / "market-venue-pilot-runs"
    blocked.mkdir(parents=True, mode=0o700)
    with pytest.raises(ValueError, match="ISOLATED"):
        RunStore(blocked, "case", max_bytes=16384)


def test_run_is_exclusive_and_immutable_evidence_is_not_overwritten(tmp_path):
    root, clock, transport = setup(tmp_path)
    run(root, clock, transport)
    before = (root / "case/latest.json").read_bytes()
    with pytest.raises(FileExistsError):
        run(root, clock, transport)
    assert (root / "case/latest.json").read_bytes() == before
    store = RunStore(root, "other", max_bytes=16384)
    try:
        store.json("evidence.json", {"value": 1})
        with pytest.raises(FileExistsError):
            store.json("evidence.json", {"value": 2})
    finally:
        store.close()


def test_foreign_latest_is_preserved(tmp_path):
    root, clock, transport = setup(tmp_path)
    run(root, clock, transport)
    doc = json.loads((root / "case/latest.json").read_text())
    store = RunStore(root, "foreign", max_bytes=100000)
    try:
        foreign = root / "foreign/latest.json"
        foreign.write_text("foreign")
        foreign.chmod(0o400)
        with pytest.raises(RuntimeError, match="FOREIGN_LATEST"):
            store.publish(1, doc)
        assert foreign.read_text() == "foreign"
    finally:
        store.close()


def test_offline_verification_links_intents_receipts_raw_and_publication(tmp_path):
    from observability.market_venues.pilot.verify import verify_run

    root, clock, transport = setup(tmp_path)
    run(root, clock, transport)
    result = verify_run(root / "case")
    assert (
        result["status"] == "LOCAL_COHERENCE_PASS"
        and result["capture_population_complete"] is True
    )
    assert (
        result["origin_certified"] is False and result["scientific_certified"] is False
    )
    raw = root / "case/response-0001.bin"
    raw.chmod(0o600)
    raw.write_bytes(b"corrupted")
    raw.chmod(0o400)
    with pytest.raises(ValueError, match="RAW_HASH_CHANGED"):
        verify_run(root / "case")


def test_offline_verification_exposes_pending_capture_after_budget_stop(tmp_path):
    from observability.market_venues.pilot.verify import verify_run

    def large(t, s, r):
        doc = json.loads(r.body)
        doc["padding"] = "x" * 7000
        return replace(r, body=json.dumps(doc).encode())

    root, clock, transport = setup(tmp_path, mutator(large))
    result = run(root, clock, transport, plan=PilotPlan(cycles=2, max_run_bytes=16384))
    evidence = verify_run(root / "case")
    assert (
        result["status"] == "INCOMPLETE"
        and evidence["capture_population_complete"] is False
        and evidence["pending_ordinals"]
    )


def test_full_proposed_budget_is_finite_without_real_wait_or_network(tmp_path):
    root, clock, transport = setup(tmp_path)
    result = run(root, clock, transport, plan=PilotPlan())
    assert result["status"] == "COMPLETED"
    assert result["cycles_published"] == 120 and result["requests_attempted"] == 724
    assert len(transport.calls) == 724
    assert result["bytes_before_final_receipt"] < 16 * 1024 * 1024
    assert clock.mono < 601 * 1000000000


def test_offline_verification_does_not_call_a_short_prefix_complete(tmp_path):
    from observability.market_venues.pilot.verify import verify_run

    root, clock, transport = setup(tmp_path)
    result = run(root, clock, transport, plan=PilotPlan(cycles=2, duration_ms=1))
    assert result["status"] == "INCOMPLETE"
    receipt = root / "case/run-result.json"
    doc = json.loads(receipt.read_text())
    doc["status"] = "COMPLETED"
    receipt.chmod(0o600)
    receipt.write_text(json.dumps(doc))
    receipt.chmod(0o400)
    with pytest.raises(ValueError, match="FALSE_COMPLETE_RUN"):
        verify_run(root / "case")


def test_interruption_preserves_a_terminal_incomplete_receipt_and_pending_intent(
    tmp_path,
):
    from observability.market_venues.pilot.verify import verify_run

    def interrupted(t, spec, response):
        if spec.purpose == "book":
            raise KeyboardInterrupt()
        return response

    root, clock, transport = setup(tmp_path, mutator(interrupted))
    with pytest.raises(KeyboardInterrupt):
        run(root, clock, transport)
    result = json.loads((root / "case/run-result.json").read_text())
    assert result["status"] == "INCOMPLETE"
    assert result["stopped_reason"] == "INTERRUPTED_OR_UNEXPECTED_FAILURE"
    checked = verify_run(root / "case")
    assert checked["pending_ordinals"] == [7]
    assert not checked["capture_population_complete"]


@pytest.mark.parametrize(
    "venue,code",
    [("bybit", 10006), ("bybit", 10009), ("okx", "50011"), ("okx", "50040")],
)
def test_native_refusal_in_http_200_stops_before_another_request(tmp_path, venue, code):
    def refuse(t, spec, response):
        if spec.purpose == "book" and spec.venue == venue:
            payload = {"retCode": code} if venue == "bybit" else {"code": code}
            return replace(response, body=json.dumps(payload).encode())
        return response

    root, clock, transport = setup(tmp_path, mutator(refuse))
    result = run(root, clock, transport)
    assert (
        result["status"] == "STOPPED"
        and result["stopped_reason"] == "NATIVE_API_REFUSED"
    )
    attempted = 7 if venue == "bybit" else 8
    assert len(transport.calls) == attempted
    receipt = json.loads(
        (root / f"case/attempt-{attempted:04d}.receipt.json").read_text()
    )
    assert receipt["http_status"] == 200 and receipt["body_complete"] is True
    assert (root / "case" / receipt["raw_file"]).exists()
    doc = json.loads((root / "case/latest.json").read_text())
    assert doc["source_counts"]["expected"] == 4
    assert any(
        row["reason"] == "NATIVE_API_REFUSED"
        for group in doc["groups"]
        for row in group["rows"]
    )
