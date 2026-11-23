"""Vérification des données, publication, écarts et déterminisme."""
from __future__ import annotations

import copy
import json
import os
import stat
from decimal import Decimal as D
from pathlib import Path

import pytest

from observability.signals_indicators.__main__ import main as cli
from observability.signals_indicators.build import InputError, build_publication
from observability.signals_indicators.publish import dumps, write_atomic
from observability.signals_indicators.synthetic import reference_input
from observability.signals_indicators.verify import Rejected, coherence, verify_bars, verify_book

FIX = Path(__file__).parent / "fixtures"
H = 3_600_000


def _bars(n=3, start=10 * H):
    return [{"open_ms": start + i * H, "o": "100", "h": "101", "l": "99", "c": "100", "v": "1"}
            for i in range(n)]


def _reason(fn, *a):
    with pytest.raises(Rejected) as exc:
        fn(*a)
    return exc.value.reason


# ── Étape 1 : vérifier ──────────────────────────────────────────────────────

def test_bars_ok_and_forming_kept_only_if_next():
    bars = _bars()
    forming = dict(bars[-1], open_ms=13 * H)
    got, f = verify_bars(bars, forming, H, 13 * H + 5)
    assert len(got) == 3 and f["open_ms"] == 13 * H
    _, f2 = verify_bars(bars, dict(forming, open_ms=14 * H), H, 13 * H + 5)
    assert f2 is None


@pytest.mark.parametrize("mutate,reason", [
    (lambda b: b.pop(1), "BAR_GAP"),
    (lambda b: b[1].update(open_ms=b[1]["open_ms"] + 1), "BAR_MISALIGNED"),
    (lambda b: b.reverse(), "BAR_ORDER"),
    (lambda b: b[0].update(h="98"), "BAR_INVALID"),
    (lambda b: b[0].update(c=100.0), "INPUT_INVALID"),
    (lambda b: b[0].update(v="-1"), "BAR_INVALID"),
    (lambda b: b[0].update(buy_v="1"), "INPUT_INVALID"),
])
def test_bars_rejections(mutate, reason):
    bars = _bars()
    mutate(bars)
    assert _reason(verify_bars, bars, None, H, 13 * H + 5) == reason


def test_bars_not_closed_and_stale():
    assert _reason(verify_bars, _bars(), None, H, 13 * H - 1) == "BAR_NOT_CLOSED"
    assert _reason(verify_bars, _bars(), None, H, 14 * H) == "STALE_BARS"
    assert _reason(verify_bars, [], None, H, 13 * H) == "SOURCE_EMPTY"


def _book(at=1000, bid="99", ask="101"):
    return {"at_ms": at, "bids": [[bid, "1"], ["98", "1"]], "asks": [[ask, "1"], ["102", "1"]]}


def test_book_checks():
    assert verify_book(_book(), 1500)[2] == 1000
    assert _reason(verify_book, _book(), 1000 + 10_001) == "STALE_BOOK"
    assert _reason(verify_book, _book(at=2000), 1500) == "STALE_BOOK"
    assert _reason(verify_book, _book(bid="101"), 1500) == "BOOK_CROSSED"
    bad = _book()
    bad["bids"].reverse()
    assert _reason(verify_book, bad, 1500) == "BOOK_INVALID"


def test_coherence_needs_three_markets():
    assert coherence({"a": D(100), "b": D(200)}) == ("NOT_EVALUATED", {})
    state, out = coherence({"a": D(100), "b": D(100.5), "c": D(100.2), "d": D(110)})
    assert state == "EVALUATED"
    assert out == {"a": None, "b": None, "c": None, "d": "PRICE_INCOHERENT"}


# ── Publication ─────────────────────────────────────────────────────────────

def test_golden_output_byte_identical():
    doc = json.loads((FIX / "btc_reference_input.json").read_text())
    assert doc == reference_input(), "fixture d'entrée = générateur synthétique"
    pub = build_publication(doc, code_sha="GOLDEN")
    assert dumps(pub) == (FIX / "btc_reference_expected.json").read_bytes()
    assert dumps(build_publication(copy.deepcopy(doc), code_sha="GOLDEN")) == dumps(pub)


def test_reference_shape():
    pub = build_publication(reference_input())
    sym = pub["symbols"][0]
    assert pub["status"] == "PARTIAL" and pub["provenance"]["fixture"] == "SYNTHETIC"
    assert sym["base"] == "BTC" and list(sym["markets"]) == [
        "mexc_spot", "mexc_perp", "kraken_spot", "kraken_perp"]
    assert all(m["check"] == "VERIFIED" for m in sym["markets"].values())
    assert sym["markets"]["kraken_spot"]["book"]["reason"] == "STALE_BOOK"
    assert sym["gaps"]["imb_top10"]["spot_vs_perp"]["kraken"]["reason"] == "SIDE_MISSING"
    assert sym["gaps"]["rsi_14"]["dispersion"]["markets_used"] == 4
    assert sym["gaps"]["adx_14"]["dispersion"]["markets_used"] == 3
    assert "cvd_session" not in sym["gaps"]


def _walk_values(obj):
    if isinstance(obj, dict):
        if "state" in obj:
            yield obj
        for v in obj.values():
            yield from _walk_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_values(v)


def test_unknown_is_never_zero_and_states_are_closed():
    pub = build_publication(reference_input())
    for cell in _walk_values(pub):
        if cell["state"] == "OK":
            assert isinstance(cell["value"], str) and "e" not in cell["value"].lower()
        else:
            assert cell["state"] == "NOT_AVAILABLE" and "value" not in cell and cell["reason"]


def test_rejected_market_publishes_no_values_and_no_gaps():
    doc = reference_input()
    doc["markets"]["mexc_perp"]["bars"].pop(5)
    pub = build_publication(doc)
    mk = pub["symbols"][0]["markets"]["mexc_perp"]
    assert mk["check"] == "REJECTED" and mk["reason"] == "BAR_GAP" and "values" not in mk
    gap = pub["symbols"][0]["gaps"]["rsi_14"]
    assert gap["spot_vs_perp"]["mexc"]["state"] == "NOT_AVAILABLE"
    assert gap["dispersion"]["markets_used"] == 3
    assert pub["status"] == "PARTIAL"


def test_incoherent_price_is_rejected():
    doc = reference_input()
    for b in doc["markets"]["kraken_perp"]["bars"]:
        for k in ("o", "h", "l", "c"):
            b[k] = format(D(b[k]) * D("1.05"), "f")
    mk = build_publication(doc)["symbols"][0]["markets"]["kraken_perp"]
    assert mk["check"] == "REJECTED" and mk["reason"] == "PRICE_INCOHERENT"


def test_not_listed_and_missing_market():
    doc = reference_input()
    doc["markets"]["kraken_perp"] = {"instrument": "PF_XBTUSD", "quote": "USD", "listed": False}
    del doc["markets"]["mexc_perp"]
    pub = build_publication(doc)
    mk = pub["symbols"][0]["markets"]
    assert mk["kraken_perp"]["check"] == "NOT_LISTED"
    assert mk["mexc_perp"] == {"exchange": "mexc", "kind": "perp", "check": "UNRESOLVED",
                               "reason": "SOURCE_MISSING"}
    assert pub["symbols"][0]["aggregate"]["perp"]["markets_used"] == 0


def test_all_failed():
    doc = reference_input()
    for m in doc["markets"].values():
        m["bars"] = []
    assert build_publication(doc)["status"] == "FAILED"


@pytest.mark.parametrize("patch", [
    {"schema": "x"}, {"timeframe": "3m"}, {"as_of_ms": 1.5}, {"base": "BTC/USD"},
    {"markets": {"binance_spot": {}}},
])
def test_envelope_refused(patch):
    doc = reference_input()
    doc.update(patch)
    with pytest.raises(InputError):
        build_publication(doc)


def test_atomic_write_mode_0644(tmp_path):
    out = tmp_path / "current" / "indicators.json"
    write_atomic(out, b"{}\n")
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o644
    assert [p.name for p in out.parent.iterdir()] == ["indicators.json"]


def test_cli(tmp_path):
    out = tmp_path / "out.json"
    assert cli(["--input", str(FIX / "btc_reference_input.json"), "--output", str(out),
                "--code-sha", "GOLDEN"]) == 0
    assert out.read_bytes() == (FIX / "btc_reference_expected.json").read_bytes()
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    assert cli(["--input", str(bad), "--output", str(tmp_path / "x.json")]) == 2
