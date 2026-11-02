"""Synthetic counter-examples for the #551 offline L2 prototype. No network."""

import ast
import importlib.util
import json
from pathlib import Path
import socket
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "docs/research/market_v0_551"
spec = importlib.util.spec_from_file_location("l2_proto_551", DIR / "l2_reconstruction_prototype.py")
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
Span, Window = m.Span, m.Window
FIX = json.loads((DIR / "SYNTHETIC_L2_FIXTURES.json").read_text())["scenarios"]
SCALE = "SYNTHETIC_COMMON"
S = 1_000_000_000


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("NETWORK_FORBIDDEN")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def raw(message):
    return json.dumps(message).encode()


def rec(t_ns, width=10):
    """Receipt whose monotonic and local-UTC spans are the same synthetic instant."""
    return m.Receipt(Span(t_ns, t_ns + width), Span(t_ns, t_ns + width))


def snap(seq, product="BTC-USD", ts="2030-01-01T00:00:00Z", bid="100", ask="101"):
    return {
        "channel": "l2_data", "timestamp": ts, "sequence_num": seq,
        "events": [{"type": "snapshot", "product_id": product, "updates": [
            {"side": "bid", "price_level": bid, "new_quantity": "1"},
            {"side": "offer", "price_level": ask, "new_quantity": "1"}]}],
    }


def upd(seq, side, price, qty, product="BTC-USD", **extra):
    u = {"side": side, "price_level": price, "new_quantity": qty, **extra}
    return {"channel": "l2_data", "timestamp": "2030-01-01T00:00:01Z", "sequence_num": seq,
            "events": [{"type": "update", "product_id": product, "updates": [u]}]}


def play(conn, messages, t0=1000):
    out = []
    for i, msg in enumerate(messages):
        out.append(conn.feed(raw(msg), rec(t0 + i * 100)))
    return out


def attestations(valid=(0, 10**20), bound=1000, lag=(0, 0), offset=(0, 0)):
    obs = m.ObserverAttestation(SCALE, bound, Span(0, 10**20), "SYNTHETIC-OBSERVER")
    clk = m.ClockAttestation(
        "synthetic_venue", frozenset({"BTC-USD", "ETH-USD"}), "l2_data.timestamp", SCALE,
        Span(*offset), Span(0, 0), Span(*lag), Window(SCALE, Span(*valid)),
        "SYNTHETIC-PROVIDER-CLOCK", "synthetic-test",
    )
    return obs, clk


# ---- snapshot / update ---------------------------------------------------
def test_fixture_snapshot_then_updates_exact_text_and_level_provenance():
    c = m.L2Connection("c1")
    assert all(r["accepted"] for r in play(c, FIX["snapshot_then_updates"]))
    b = c.bbo("BTC-USD")
    assert b["status"] == "OBSERVED_UNQUALIFIED" and b["qualification"] == "UNQUALIFIED"
    assert b["bid"]["price"] == "1000.5" and b["bid"]["size"] == "5"
    assert b["bid"]["level_event_time_ns"] == 1893456000 * S + 400000007  # nine decimals, exact
    assert b["ask"]["price"] == "1002"  # the 1001 level was removed by quantity 0
    assert b["ask"]["level_event_time_state"] == "PLACEHOLDER_EPOCH_NOT_A_DATE"
    assert b["ask"]["level_event_time_ns"] is None  # unknown, not 0, not "old"
    assert b["mid"] is None and b["spread"] is None and b["economic_metrics"] is None


def test_snapshot_native_text_is_kept_verbatim():
    c = m.L2Connection("c1")
    c.feed(raw(FIX["snapshot_then_updates"][0]), rec(0))
    c.feed(raw(upd(1, "bid", "1000.000000001", "0")), rec(100))
    assert c.bbo("BTC-USD")["bid"]["price"] == "999.5"


def test_update_before_snapshot_is_discarded_not_guessed():
    c = m.L2Connection("c1")
    assert c.feed(raw(upd(0, "bid", "100", "1")), rec(0))["accepted"]
    assert c.state("BTC-USD") == ("NO_SNAPSHOT", None)
    assert c.bbo("BTC-USD")["bid"] is None


def test_remove_of_unknown_level_invalidates_instead_of_inventing_state():
    c = m.L2Connection("c1")
    play(c, [snap(0), upd(1, "bid", "77", "0")])
    assert c.state("BTC-USD")[0] == "INVALID"
    assert c.bbo("BTC-USD")["bid"] is None


def test_crossed_book_is_invalid_not_published():
    c = m.L2Connection("c1")
    play(c, [snap(0), upd(1, "bid", "102", "1")])
    assert c.state("BTC-USD") == ("INVALID", "CROSSED_OR_LOCKED_BOOK")


def test_refused_message_leaves_previous_good_book_untouched_then_invalidates():
    c = m.L2Connection("c1")
    play(c, [snap(0)])
    bad = upd(1, "bid", "100.5", "1", event_time="not-a-date")
    assert not c.feed(raw(bad), rec(100))["accepted"]
    assert c.state("BTC-USD")[0] == "INVALID"


# ---- gaps, order, scope, reconnection -----------------------------------
def test_fixture_gap_invalidates_until_new_snapshot():
    c = m.L2Connection("c1")
    r = play(c, FIX["gap"])
    assert r[1]["reason"] == "SEQUENCE_GAP"
    assert c.state("ETH-USD") == ("INVALID", "SEQUENCE_GAP")
    c.feed(raw(snap(4, "ETH-USD", bid="60", ask="61")), rec(500))
    assert c.state("ETH-USD")[0] == "LIVE" and c.books["ETH-USD"].resyncs == 1
    assert c.bbo("ETH-USD")["bid"]["price"] == "60"


def test_gap_in_one_product_stream_invalidates_every_product_of_the_connection():
    c = m.L2Connection("c1")
    play(c, [snap(0), snap(1, "ETH-USD")])
    c.feed(raw(upd(5, "bid", "100.5", "1", "ETH-USD")), rec(500))
    assert c.state("BTC-USD")[0] == c.state("ETH-USD")[0] == "INVALID"


def test_duplicate_sequence_is_not_applied_twice():
    c = m.L2Connection("c1")
    play(c, [snap(0), upd(1, "bid", "100.5", "9")])
    r = c.feed(raw(upd(1, "bid", "100.5", "10")), rec(900))
    assert r["reason"] == "SEQUENCE_DUPLICATE_OR_REORDERED"
    assert c.state("BTC-USD")[0] == "INVALID"
    assert c.books["BTC-USD"].bids[m.Decimal("100.5")][2] == "9"  # not 10, not 19


def test_deltas_after_a_gap_do_not_resurrect_the_book():
    c = m.L2Connection("c1")
    play(c, [snap(0), upd(2, "bid", "100.5", "1"), upd(3, "bid", "100.6", "1")])
    assert c.state("BTC-USD")[0] == "INVALID"


def test_sequence_is_scoped_to_the_connection_never_global():
    a, b = m.L2Connection("a"), m.L2Connection("b")
    play(a, [snap(0), upd(1, "bid", "100.5", "1")])
    b.feed(raw(snap(0)), rec(0))  # a fresh connection restarts at its own counter
    assert b.state("BTC-USD")[0] == "LIVE"
    assert b.books["BTC-USD"] is not a.books["BTC-USD"]
    assert b.bbo("BTC-USD")["bid"]["price"] == "100"  # nothing inherited from "a"


def test_other_channel_messages_share_the_connection_counter():
    c = m.L2Connection("c1")
    play(c, [snap(0), {"channel": "heartbeats", "sequence_num": 1, "timestamp": "2030-01-01T00:00:01Z"}, upd(2, "bid", "100.5", "1")])
    assert c.state("BTC-USD")[0] == "LIVE"
    play(c, [{"channel": "heartbeats", "sequence_num": 4}], t0=900)  # seq 3 never seen
    assert c.state("BTC-USD")[0] == "INVALID"


def test_closed_connection_serves_nothing():
    c = m.L2Connection("c1")
    play(c, [snap(0)])
    c.close()
    assert c.state("BTC-USD")[0] == "CONNECTION_CLOSED"
    assert c.bbo("BTC-USD")["status"] == "NOT_AVAILABLE"
    assert c.feed(raw(upd(1, "bid", "100.5", "1")), rec(5))["accepted"] is False


# ---- instruments, numbers, bytes -----------------------------------------
@pytest.mark.parametrize("product", ["BTC-USDT", "BTC-USDC", "btcusd", "ETH-EUR"])
def test_usd_is_not_usdt_usdc_or_a_neighbour(product):
    c = m.L2Connection("c1")
    assert not c.feed(raw(snap(0, product)), rec(0))["accepted"]


@pytest.mark.parametrize("bad", [100, 100.5, "1e3", "-1", "+1", " 1", "NaN", "1,5", True, None, "0"])
def test_price_must_be_exact_positive_decimal_text(bad):
    msg = snap(0)
    msg["events"][0]["updates"][0]["price_level"] = bad
    text = json.dumps(msg).encode()
    assert not m.L2Connection("c").feed(text, rec(0))["accepted"]


def test_json_fraction_numbers_are_refused_before_any_float_exists():
    text = b'{"channel":"l2_data","sequence_num":0,"events":[{"type":"snapshot","product_id":"BTC-USD","updates":[{"side":"bid","price_level":100.5,"new_quantity":"1"}]}]}'
    assert m.L2Connection("c").feed(text, rec(0))["reason"] == "JSON_NUMBER_FRACTION_REFUSED"


def test_duplicate_json_keys_and_huge_messages_are_refused():
    dup = b'{"channel":"l2_data","channel":"x","sequence_num":0}'
    assert m.L2Connection("c").feed(dup, rec(0))["reason"] == "DUPLICATE_NATIVE_FIELD"
    assert m.L2Connection("c").feed(b" " * (m.MAX_MESSAGE_BYTES + 1), rec(0))["accepted"] is False


@pytest.mark.parametrize("seq", [True, -1, "0", 1.0, None])
def test_sequence_must_be_a_nonnegative_integer(seq):
    msg = snap(0)
    msg["sequence_num"] = seq
    assert not m.L2Connection("c").feed(json.dumps(msg).encode(), rec(0))["accepted"]


def test_level_limit_is_enforced():
    c = m.L2Connection("c1", max_levels_per_side=1)
    play(c, [snap(0), upd(1, "bid", "99", "1")])
    assert c.state("BTC-USD")[0] == "INVALID"


# ---- dates: absent, future, precision -------------------------------------
def test_nine_decimal_time_is_exact_integer_nanoseconds():
    assert m.parse_rfc3339_ns("1970-01-01T00:00:01.123456789Z") == S + 123456789
    assert m.parse_rfc3339_ns("1970-01-01T00:00:01.1Z") == S + 100000000


@pytest.mark.parametrize("text", ["2030-01-01T00:00:00+00:00", "2030-01-01 00:00:00Z", "2030-02-30T00:00:00Z", "2030-01-01T00:00:60Z", "2030-01-01T00:00:00.1234567890Z", "", 5, None])
def test_time_text_outside_the_closed_format_is_refused(text):
    with pytest.raises(m.L2Refusal):
        m.parse_rfc3339_ns(text)


def test_absent_dates_stay_unknown_and_never_become_zero():
    msg = snap(0)
    del msg["timestamp"]
    c = m.L2Connection("c")
    c.feed(raw(msg), rec(0))
    assert c.last_send == (None, "NOT_SUPPLIED")
    obs, clk = attestations()
    f = c.freshness("BTC-USD", rec(50), silence_budget_ns=10**9, age_budget_ns=10**9, observer=obs, envelope_clock=clk)
    assert f["state_age_ns"] is None and "SEND_TIME_NOT_SUPPLIED" in f["unresolved"]
    assert f["freshness"] == "LIVE_UNQUALIFIED"


def test_future_send_time_is_flagged_not_hidden():
    c = m.L2Connection("c")
    c.feed(raw(snap(0, ts="1970-01-01T00:01:40Z")), rec(1 * S))  # send 100 s, received ~1 s
    obs, clk = attestations()
    f = c.freshness("BTC-USD", rec(2 * S), silence_budget_ns=10**12, age_budget_ns=5 * S, observer=obs, envelope_clock=clk)
    assert f["state_age_status"] == "FUTURE" and f["freshness"] == "FUTURE_TIMESTAMP"


# ---- freshness: attestation, expiry, old-but-newly-received ----------------
def test_without_attestations_nothing_is_ever_called_fresh():
    c = m.L2Connection("c")
    c.feed(raw(snap(0)), rec(0))
    f = c.freshness("BTC-USD", rec(5), silence_budget_ns=10**9)
    assert f["freshness"] == "LIVE_UNQUALIFIED" and f["state_age_status"] == "UNRESOLVED"
    assert "OBSERVER_ATTESTATION_MISSING" in f["unresolved"]
    assert set(f["unattested_assumptions"]) == set(m.ASSUMPTIONS)


def test_attested_recent_state_is_within_assumptions_only():
    t = m.parse_rfc3339_ns("1970-01-01T00:00:10Z")
    c = m.L2Connection("c")
    c.feed(raw(snap(0, ts="1970-01-01T00:00:10Z")), rec(t + 1000))
    obs, clk = attestations(bound=500, lag=(0, 200), offset=(-100, 100))
    f = c.freshness("BTC-USD", rec(t + 2000), silence_budget_ns=S, age_budget_ns=S, observer=obs, envelope_clock=clk)
    assert f["state_age_status"] == "WITHIN_ASSUMPTIONS"
    assert f["freshness"] == "QUALIFIED_WITHIN_ASSUMPTIONS"


def test_age_window_arithmetic_is_conservative_both_sides():
    t = 10 * S
    c = m.L2Connection("c")
    c.feed(raw(snap(0, ts="1970-01-01T00:00:10Z")), rec(t))
    obs, clk = attestations(bound=500, lag=(0, 200), offset=(-100, 100))
    f = c.freshness("BTC-USD", rec(t + 2000), silence_budget_ns=S, age_budget_ns=S, observer=obs, envelope_clock=clk)
    # now=[t+1500, t+2510]; event=[t-100-200, t+100-0]=[t-300, t+100]
    assert f["state_age_ns"] == [1500 - 100, 2510 + 300]


def test_old_state_newly_received_is_stale_not_fresh():
    c = m.L2Connection("c")
    c.feed(raw(snap(0, ts="1970-01-01T00:00:10Z")), rec(10 * S + 3_600 * S))  # received an hour later
    obs, clk = attestations()
    now = rec(10 * S + 3_600 * S + 50)
    f = c.freshness("BTC-USD", now, silence_budget_ns=10**12, age_budget_ns=5 * S, observer=obs, envelope_clock=clk)
    assert f["silence_status"] == "WITHIN_BUDGET"  # received just now...
    assert f["freshness"] == "STALE"  # ...but the state it carries is old


def test_silence_alone_can_refuse_without_any_provider_clock():
    c = m.L2Connection("c")
    c.feed(raw(snap(0)), rec(0))
    f = c.freshness("BTC-USD", rec(20 * S), silence_budget_ns=5 * S)
    assert f["silence_status"] == "STALE_BY_SILENCE" and f["freshness"] == "STALE"
    g = c.freshness("BTC-USD", m.Receipt(Span(5 * S - 5, 5 * S + 5), Span(0, 0)), silence_budget_ns=5 * S)
    assert g["silence_status"] == "SILENCE_BUDGET_NOT_EXCLUDED"


def test_monotonic_regression_is_unresolved_not_zero_silence():
    c = m.L2Connection("c")
    c.feed(raw(snap(0)), rec(10_000))
    f = c.freshness("BTC-USD", rec(0), silence_budget_ns=S)
    assert f["silence_ns"] is None and f["freshness"] == "UNRESOLVED"


def test_silence_budget_is_mandatory_and_explicit():
    c = m.L2Connection("c")
    c.feed(raw(snap(0)), rec(0))
    with pytest.raises(ValueError):
        c.freshness("BTC-USD", rec(1), silence_budget_ns=None)


@pytest.mark.parametrize("which", ["observer", "provider"])
def test_expired_or_non_covering_proof_yields_unresolved(which):
    t = 10 * S
    c = m.L2Connection("c")
    c.feed(raw(snap(0, ts="1970-01-01T00:00:10Z")), rec(t))
    obs, clk = attestations()
    if which == "observer":
        obs = m.ObserverAttestation(SCALE, 1000, Span(0, t), "SYNTHETIC-OBSERVER")  # ends before "now"
    else:
        clk = attestations(valid=(0, t - 1))[1]  # event window leaves the validity window
    f = c.freshness("BTC-USD", rec(t + 100), silence_budget_ns=S, age_budget_ns=S, observer=obs, envelope_clock=clk)
    assert f["state_age_ns"] is None and f["freshness"] == "LIVE_UNQUALIFIED"
    assert any(x.startswith(("OBSERVER_ATTESTATION", "ATTESTATION_NOT_COVERING")) for x in f["unresolved"])


def test_attestation_does_not_transfer_to_neighbour_field_or_product():
    t = 10 * S
    c = m.L2Connection("c")
    c.feed(raw(snap(0, "ETH-USD", ts="1970-01-01T00:00:10Z")), rec(t))
    obs, clk = attestations()
    narrow = m.ClockAttestation(clk.venue, frozenset({"BTC-USD"}), clk.field, SCALE, clk.offset, clk.quantization, clk.lag, clk.validity, clk.evidence_ref, clk.attested_by)
    f = c.freshness("ETH-USD", rec(t + 5), silence_budget_ns=S, age_budget_ns=S, observer=obs, envelope_clock=narrow)
    assert "ATTESTATION_DOMAIN_MISMATCH" in f["unresolved"]
    other = m.ClockAttestation(clk.venue, clk.products, "l2_data.events.updates.event_time", SCALE, clk.offset, clk.quantization, clk.lag, clk.validity, clk.evidence_ref, clk.attested_by)
    f = c.freshness("ETH-USD", rec(t + 5), silence_budget_ns=S, age_budget_ns=S, observer=obs, envelope_clock=other)
    assert "ATTESTATION_DOMAIN_MISMATCH" in f["unresolved"]


def test_attestation_without_provenance_is_not_accepted():
    obs, clk = attestations()
    blank = m.ClockAttestation(clk.venue, clk.products, clk.field, SCALE, clk.offset, clk.quantization, clk.lag, clk.validity, "", "")
    assert blank.window(10, "BTC-USD", clk.field) == (None, "ATTESTATION_PROVENANCE_MISSING")


def test_cache_style_double_counting_is_absent_lag_counted_once():
    # Only the declared event->label lag widens the window; no residence term exists.
    _, clk = attestations(lag=(0, 7))
    w, _ = clk.window(100, "BTC-USD", "l2_data.timestamp")
    assert w.span == Span(100 - 7, 100)


def test_level_time_is_never_used_as_book_age():
    c = m.L2Connection("c")
    play(c, [snap(0), upd(1, "bid", "100.5", "1", event_time="1970-01-01T00:00:01Z")])
    f = c.freshness("BTC-USD", rec(2 * 3_600 * S), silence_budget_ns=10**15)
    assert f["state_age_ns"] is None and f["freshness"] == "LIVE_UNQUALIFIED"


# ---- pair --------------------------------------------------------------------
def test_pair_without_second_venue_is_unresolved_and_metricless():
    p = m.pair_state({"event_window": Window(SCALE, Span(0, 1))}, None, max_gap_ns=5)
    assert p["comparability"] == "NOT_PROVEN" and p["mid"] is None and p["spread"] is None
    assert p["reason"] == "SOURCE_NOT_SUPPLIED_OR_UNQUALIFIED"


def test_pair_needs_explicit_budget_and_same_scale():
    a, b = {"event_window": Window(SCALE, Span(0, 1))}, {"event_window": Window("OTHER", Span(0, 1))}
    assert m.pair_state(a, a)["reason"] == "EXPLICIT_GAP_BUDGET_REQUIRED"
    assert m.pair_state(a, b, max_gap_ns=5)["reason"] == "DIFFERENT_COMMON_SCALES"
    assert m.pair_state(a, a, max_gap_ns=5)["reason"] == "WITHIN_ASSUMPTIONS"
    assert m.pair_state(a, a, max_gap_ns=5)["comparability"] == "NOT_PROVEN"


# ---- passivity ----------------------------------------------------------------
def test_module_has_no_transport_clock_or_write_import_and_no_float():
    tree = ast.parse((DIR / "l2_reconstruction_prototype.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"socket", "ssl", "http", "urllib", "asyncio", "time", "requests", "websockets", "subprocess", "os", "random"}
    assert not any(isinstance(n, ast.Name) and n.id == "float" for n in ast.walk(tree))
    assert not any(isinstance(n, ast.Constant) and isinstance(n.value, float) for n in ast.walk(tree))
    src = (DIR / "l2_reconstruction_prototype.py").read_text()
    assert "now()" not in src and "open(" not in src.replace("importlib", "")


def test_fixtures_are_flagged_synthetic_and_unadmitted():
    doc = json.loads((DIR / "SYNTHETIC_L2_FIXTURES.json").read_text())
    assert doc["synthetic"] is True and doc["admission_granted"] is False


def test_no_producer_or_reader_imports_the_prototype():
    hits = []
    for base in ("observability", "core", "paper_trading", "frontend/src"):
        for p in (ROOT / base).rglob("*"):
            if p.suffix in (".py", ".ts", ".tsx") and p.is_file():
                if "market_v0_551" in p.read_text(errors="ignore"):
                    hits.append(str(p))
    assert hits == []
