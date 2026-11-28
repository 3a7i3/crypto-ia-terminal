"""MEO-03 R1–R9: descriptive reading of a MEO-01 replay report (SYNTHETIC inputs only)."""

import ast
import hashlib
import json
from pathlib import Path

import pytest

from observability import meo_trades_replay as cli
from observability.market_flow import meo_reading as mr
from observability.radar_composite import kraken_trade_pilot as ktp

from ._support import MIN, T0, WIN, bar, report, simple, window

ROOT = Path(__file__).resolve().parents[2]


def _one(w, **kw):
    return mr.read_report(report([w], **kw))["windows"][0]


# R1 — an uncovered or partially covered window is UNKNOWN, never zero.
@pytest.mark.parametrize("status", ["NOT_COVERED", "PARTIALLY_COVERED"])
def test_r01_uncovered_windows_publish_null_values_and_unknown_alignment(status):
    bars = [bar(0, "NOT_COVERED")] + [bar(i, o="100", c="100") for i in range(1, 5)]
    w = _one(window(0, bars, status=status))
    for k in ("price_first", "price_last", "price_change", "trade_count", "volume_base", "buy_volume",
              "sell_volume", "unknown_volume", "delta", "cvd_end", "cvd_anchor_ns"):
        assert w[k] is None
    assert w["alignment"] == "UNKNOWN" and w["alignment_reason"] == "WINDOW_NOT_COVERED"
    assert w["eligible_for_first_desalignment"] is False


# R2 — DESALIGN-1 v1 truth table (16 cases), exact zeros included.
PRICE = {"+": ("100", "101"), "-": ("101", "100"), "0": ("100", "100")}
FLOW = {"+": ["1", "1"], "-": ["-1", "-1"], "0": ["0", "0"], "?": ["-1", "1"]}
EXPECTED = {
    ("+", "+"): "ALIGNED", ("+", "-"): "DIVERGENT", ("+", "0"): "FLAT_FLOW", ("+", "?"): "UNKNOWN",
    ("-", "+"): "DIVERGENT", ("-", "-"): "ALIGNED", ("-", "0"): "FLAT_FLOW", ("-", "?"): "UNKNOWN",
    ("0", "+"): "FLAT_PRICE", ("0", "-"): "FLAT_PRICE", ("0", "0"): "FLAT", ("0", "?"): "UNKNOWN",
    ("?", "+"): "UNKNOWN", ("?", "-"): "UNKNOWN", ("?", "0"): "UNKNOWN", ("?", "?"): "UNKNOWN",
}


@pytest.mark.parametrize("sp,sf", sorted(EXPECTED))
def test_r02_desalign_1_truth_table(sp, sf):
    if sp == "?":  # no observed minute at all: no price, the window is still covered (zero minutes)
        bars = [bar(i, "OBSERVED_ZERO") for i in range(5)]
        w = _one(window(0, bars, volume="0", trades=2, bounds=FLOW[sf]))
    else:
        first, last = PRICE[sp]
        w = _one(simple(0, first=first, last=last, buy="1", sell="1", bounds=FLOW[sf]))
    assert w["alignment"] == EXPECTED[(sp, sf)]
    if w["alignment"] != "UNKNOWN":
        assert w["signs"] == {"price": sp, "flow": sf}


def test_r02_fewer_than_two_trades_is_unknown_even_with_a_zero_change():
    bars = [bar(0, o="100", c="100", buy="1", tc=1)] + [bar(i, "OBSERVED_ZERO") for i in range(1, 5)]
    w = _one(window(0, bars, volume="1", bounds=["1", "1"]))
    assert w["price_change"] == "0" and w["trade_count"] == 1
    assert w["alignment"] == "UNKNOWN" and w["alignment_reason"] == "FEWER_THAN_TWO_TRADES"


# R3 — unknown side (B02 V09): bounds straddling zero never yield a desalignment.
def test_r03_unknown_side_bounds_straddling_zero_give_unknown_not_divergent():
    w = _one(simple(0, first="101", last="100", buy="3", sell="1", unk="2", bounds=["0", "4"]))
    assert w["unknown_volume"] == "2" and w["delta_bounds"] == ["0", "4"]
    assert w["signs"]["flow"] == "?" and w["alignment"] == "UNKNOWN"
    assert w["alignment_reason"] == "FLOW_SIGN_UNRESOLVED"
    r = mr.read_report(report([simple(0, first="101", last="100", buy="3", sell="1", unk="2",
                                      bounds=["0", "4"])]))
    assert r["divergent_windows"] == [] and r["first_desalignment"] is None


# R4 — CVD exactly as the source anchored it; the first-desalignment search restarts per segment.
def test_r04_cvd_values_and_anchor_are_the_source_engine_ones_and_search_restarts_per_segment():
    a = simple(0, first="101", last="100", buy="2", sell="1", seg=0, cvd=("7.5", "8.5"))
    gap = window(1, [bar(i, "NOT_COVERED", start=T0 + WIN) for i in range(5)], status="NOT_COVERED")
    b = simple(2, first="101", last="100", buy="2", sell="1", seg=1, cvd=("2", "3"))
    c = simple(3, first="101", last="100", buy="2", sell="1", seg=1, cvd=("4", "5"))
    r = mr.read_report(report([a, gap, b, c]))
    w0, _, w2, w3 = r["windows"]
    assert (w0["cvd_end"], w0["cvd_end_bounds"], w0["cvd_segment"]) == ("8.5", ["8.5", "8.5"], 0)
    assert w0["cvd_anchor_ns"] == str(T0)
    assert w2["cvd_anchor_ns"] == w3["cvd_anchor_ns"] == str(T0 + 2 * WIN)
    assert w3["cvd_end"] == "5"  # never re-accumulated across the gap
    assert r["first_desalignment_by_segment"] == [{"segment": 0, "start_ns": str(T0)},
                                                  {"segment": 1, "start_ns": str(T0 + 2 * WIN)}]
    assert r["first_desalignment"]["start_ns"] == str(T0)
    assert r["first_desalignment"]["meaning"] == "FIRST_OBSERVED_NOT_FORMATION_INSTANT"


# R5 — operator M3: windows before, overlapping the subscription or without transport continuity are
# read and kept, but excluded from the first-desalignment search.
def test_r05_pre_overlapping_and_discontinuous_windows_are_read_but_excluded():
    div = dict(first="101", last="100", buy="2", sell="1")
    ws = [simple(0, **div), simple(1, **div), simple(2, transport=False, **div), simple(3, **div)]
    r = mr.read_report(report(ws, ack=T0 + WIN + MIN))
    reasons = [w["exclusion_reason"] for w in r["windows"]]
    assert reasons == ["PRE_SUBSCRIPTION", "OVERLAPS_SUBSCRIPTION", "TRANSPORT_NOT_CONTINUOUS", None]
    assert all(w["alignment"] == "DIVERGENT" for w in r["windows"])  # the reading itself is kept
    assert len(r["divergent_windows"]) == 4
    assert r["first_desalignment"]["start_ns"] == str(T0 + 3 * WIN)
    none = mr.read_report(report(ws[:3], ack=T0 + WIN + MIN))
    assert none["first_desalignment"] is None and none["first_desalignment_by_segment"] == []
    no_ack = mr.read_report(report(ws, ack=None))
    assert {w["exclusion_reason"] for w in no_ack["windows"]} == {"NO_SUBSCRIPTION_ACK"}


# R6 — determinism: same sealed capture, two reads, identical bytes and SHA-256.
@pytest.fixture(scope="module")
def capture(tmp_path_factory):
    out = tmp_path_factory.mktemp("meo03") / "c"
    _, code = ktp.dry_run(out)
    assert code == 0
    return out


def test_r06_two_reads_of_the_same_capture_are_byte_identical(capture, tmp_path, capsys):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    assert cli.main(["read", str(capture), "--out", str(a)]) == 0
    assert cli.main(["read", str(capture), "--out", str(b)]) == 0
    assert a.read_bytes() == b.read_bytes()
    assert hashlib.sha256(a.read_bytes()).hexdigest() in capsys.readouterr().out
    assert cli.main(["read", str(capture), "--out", str(a)]) == 4  # never overwritten


# R7 — the reading copies the report; its window sums agree with the report or it refuses.
def test_r07_sums_equal_the_report_and_an_inconsistent_report_is_refused(capture, tmp_path):
    rep = tmp_path / "r.json"
    assert cli.main(["replay", str(capture), "--out", str(rep)]) == 0
    source = json.loads(rep.read_text())
    reading = mr.read_report(source)
    assert reading["corpus_ref"]["source_report_sha256"] == hashlib.sha256(rep.read_bytes()).hexdigest()
    for w, s in zip(reading["windows"], source["windows"]):
        if s["status"] == "COVERED":
            assert w["trade_count"] == s["totals"]["trade_count"]
            assert w["volume_base"] == s["totals"]["volume_base"]
            assert w["delta_bounds"] == s["delta_300s"]["delta_base_bounds"]
            assert w["cvd_end"] == s["bars"][-1]["cvd_base"]
    bad = simple(0)
    bad["totals"]["volume_base"] = "999"
    with pytest.raises(mr.ReadingRefusal, match="WINDOW_VOLUMES_INCONSISTENT"):
        mr.read_report(report([bad]))


# R8 — mandatory marking; a SYNTHETIC fixture never becomes HISTORICAL or OBSERVATION.
def test_r08_marking_and_evidence_kind_projection(capture, tmp_path):
    out = tmp_path / "s.json"
    assert cli.main(["read", str(capture), "--out", str(out)]) == 0
    s = json.loads(out.read_text())
    assert (s["evidence_kind"], s["source_evidence_kind"]) == ("SYNTHETIC", "SYNTHETIC")
    assert s["admission"] == {"instrument_admission": "PROBATION", "use": "TRADE_FLOW",
                              "claims_admitted_partial": False}
    assert (s["time_basis"], s["axis"], s["qualification"]) == (
        "UNATTESTED", "NATIVE", "CONDITIONAL_ON_UNPROVEN_NATIVE_UTC_ALIGNMENT")
    assert s["quality"]["state"] == "DEGRADED" and s["rule"]["id"] == "DESALIGN-1"
    obs = mr.read_report(report([simple(0)], kind="OBSERVATION", synthetic=False))
    assert (obs["evidence_kind"], obs["source_evidence_kind"]) == ("HISTORICAL", "OBSERVATION")
    mixed = mr.read_report(report([simple(0)], kind="OBSERVATION", synthetic=True))
    assert mixed["evidence_kind"] == "SYNTHETIC"  # any synthetic flag wins
    for kind, synthetic in (("LIVE", False), ("HISTORICAL", False), (None, False)):
        with pytest.raises(mr.ReadingRefusal, match="EVIDENCE_KIND_NOT_READABLE"):
            mr.read_report(report([simple(0)], kind=kind, synthetic=synthetic))
    with pytest.raises(mr.ReadingRefusal, match="REPORT_SCHEMA_UNSUPPORTED"):
        mr.read_report({"schema": "other"})


# R9 — package rules: a pure projection inside market_flow, reached only through the operator CLI.
def test_r09_reading_module_is_pure_and_only_the_cli_uses_it():
    tree = ast.parse((ROOT / "observability/market_flow/meo_reading.py").read_text())
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imported.add(("." * n.level) + (n.module or ""))
    assert imported == {"decimal", "hashlib", "json", ".", ".exact", ".kraken_trades"}
    hits = []
    for base in ("observability", "core", "paper_trading", "frontend/src"):
        for p in (ROOT / base).rglob("*"):
            if p.suffix in (".py", ".ts", ".tsx") and p.is_file() and p.name != "meo_reading.py":
                if "meo_reading" in p.read_text(errors="ignore"):
                    hits.append(str(p.relative_to(ROOT)))
    assert hits == ["observability/meo_trades_replay.py"]
