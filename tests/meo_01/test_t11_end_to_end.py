"""T11 end to end on a synthetic Kraken: capture -> sealed directory -> verify -> replay -> report."""

import hashlib
import json

import pytest

from observability import meo_trades_replay as cli
from observability.market_flow import kraken_trades as kt
from observability.radar_composite import kraken_trade_pilot as ktp


@pytest.fixture(scope="module")
def capture(tmp_path_factory):
    out = tmp_path_factory.mktemp("meo01") / "c"
    _, code = ktp.dry_run(out)
    assert code == 0
    return out


def test_t11_verify_then_replay_twice_gives_identical_bytes(capture, tmp_path, capsys):
    assert cli.main(["verify", str(capture)]) == 0
    assert json.loads(capsys.readouterr().out)["verified"] is True
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    assert cli.main(["replay", str(capture), "--out", str(a)]) == 0
    assert cli.main(["replay", str(capture), "--out", str(b)]) == 0
    assert a.read_bytes() == b.read_bytes()
    assert hashlib.sha256(a.read_bytes()).hexdigest() in capsys.readouterr().out


def test_t11_a_synthetic_capture_yields_a_covered_five_minute_exit_window(capture):
    manifest, events = cli.load(capture)
    r = kt.replay_journal(manifest, events)
    assert r["synthetic"] is True and r["evidence_kind"] == "SYNTHETIC"
    ew = r["exit_window"]
    assert ew is not None and int(ew["end_ns"]) - int(ew["start_ns"]) == kt.WINDOW_NS
    assert int(ew["start_ns"]) % kt.WINDOW_NS == 0  # aligned on a UTC 5-minute boundary
    w = next(w for w in r["windows"] if w["start_ns"] == ew["start_ns"])
    assert w["status"] == "COVERED" and len(w["bars"]) == 5
    # A window covered only thanks to the snapshot (before the subscription) is reported, not used as exit.
    ack = int(r["subscription"]["acknowledged_receipt_ns"])
    before = [x for x in r["windows"] if x["status"] == "COVERED" and int(x["start_ns"]) < ack]
    assert before and int(ew["start_ns"]) >= ack and w["transport_continuous_receipt_axis"] is True
    assert r["rest_cross_check"]["exit_window"]["status"] == "MATCH"
    assert {k: v["status"] for k, v in r["hypotheses"].items()} == {
        "H1_side_is_taker": "DOCUMENTARY", "H2_trade_id_plus_one": "CONFIRMED_ON_CAPTURE",
        "H3_timestamp_meaning": "UNKNOWN", "H4_plain_decimal_numbers": "CONFIRMED_ON_CAPTURE",
        "H5_order_and_time_follow_ids": "CONFIRMED_ON_CAPTURE", "H6_symbol_echo": "CONFIRMED_ON_CAPTURE",
        "H7_ws_row_equals_rest_row": "CONFIRMED_ON_CAPTURE"}
    assert r["source"]["capture_code_digest"] == ktp.code_identity()["digest"]
    assert all(set(n) == {"schema_version", "receipt_seq", "item_index", "trade_id", "price", "quantity",
                          "aggressor_side", "side_basis"} for n in r["normalized_trades_exit_window"])


def test_t11_faults_in_the_capture_reach_the_report(tmp_path):
    out = tmp_path / "f"
    ktp.dry_run(out, faults=[("id_gap", 200_000), ("silence", 400_000, 420_000), ("exponent", 600_000)])
    manifest, events = cli.load(out)
    r = kt.replay_journal(manifest, events)
    assert r["trade_coverage"]["id_gaps_count"] >= 3
    assert r["ledger"]["refused"].get("DECIMAL_TEXT_REFUSED") == 1
    assert len(r["transport_continuity"]["spans_ns"]) == 2  # the silence cuts the transport too
    assert r["hypotheses"]["H2_trade_id_plus_one"]["status"] == "CONFIRMED_ON_CAPTURE"  # REST holds the lost ids
    assert r["hypotheses"]["H4_plain_decimal_numbers"]["status"] == "REFUTED"
    assert any(w["status"] == "PARTIALLY_COVERED" for w in r["windows"])


def test_t11_altered_evidence_or_existing_output_is_refused(capture, tmp_path):
    copy = tmp_path / "copy"
    copy.mkdir()
    for name in ("manifest.json", "events.jsonl", "frames.bin"):
        (copy / name).write_bytes((capture / name).read_bytes())
    raw = bytearray((copy / "frames.bin").read_bytes())
    raw[100] ^= 1
    (copy / "frames.bin").write_bytes(bytes(raw))
    assert cli.main(["verify", str(copy)]) == 4
    with pytest.raises(kt.JournalRefusal, match="FRAMES_SHA256_MISMATCH"):
        cli.load(copy)
    existing = tmp_path / "exists.json"
    existing.write_text("keep")
    assert cli.main(["replay", str(capture), "--out", str(existing)]) == 4
    assert existing.read_text() == "keep"
    assert cli.main(["verify", str(tmp_path / "missing")]) == 4


def test_t11_journal_tiling_is_checked_event_by_event(capture):
    manifest = json.loads((capture / "manifest.json").read_text())
    log = (capture / "events.jsonl").read_bytes()
    frames = (capture / "frames.bin").read_bytes()
    lines = log.splitlines(keepends=True)
    swapped = lines[1] + lines[0] + b"".join(lines[2:])
    m = {**manifest, "sealed": {**manifest["sealed"], "events_sha256": hashlib.sha256(swapped).hexdigest()}}
    with pytest.raises(kt.JournalRefusal, match="SEQUENCE_NOT_CONTIGUOUS"):
        kt.verify_journal(m, swapped, frames)
    with pytest.raises(kt.JournalRefusal, match="NOT_SEALED"):
        kt.verify_journal({}, log, frames)
