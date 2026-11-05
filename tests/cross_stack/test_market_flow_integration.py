"""CryptoRadar Flux (lot 3A): the real replay -> reader -> route chain feeds the TypeScript corpus.

No ``importorskip``: if FastAPI (or any dependency) is missing, collection FAILS. A Flux gate that
silently skips would look validated without being so.
"""
from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
from pathlib import Path

import pytest

from observability.market_flow import fixtures as fx
from observability.market_flow.artifact import replay
from observability.operator_api import app as api
from tests.cross_stack.generate_market_flow_fixture import (
    CORPUS_DIR, generate_market_flow_fixture, nonprintable_ranges, publication_verdict,
)

GOLDEN = Path(__file__).resolve().parents[2] / "observability/market_flow/fixtures/market_flow_artifact_synthetic.json"
REQUIRED_NATIVE = {
    "native_base", "native_ns_above_2_53", "native_ns_30_digits", "native_eth_unicode_text", "native_as_of_straddle",
    "native_book_invalid_gap", "native_no_snapshot", "native_malformed_message", "native_event_times",
    "native_silence_exceeded", "native_depth_limited", "native_no_trades",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    golden_before = digest(GOLDEN)
    reader_before = api._market_flow_reader
    out = tmp_path_factory.mktemp("flow-corpus")
    manifest = generate_market_flow_fixture(out)
    assert api._market_flow_reader is reader_before, "the reader API global must be restored"
    assert digest(GOLDEN) == golden_before, "the reference file must never be touched"
    return out, manifest


def case(manifest, case_id):
    return next(c for c in manifest["cases"] if c["id"] == case_id)


def body_of(root, c):
    return (root / CORPUS_DIR / "bodies" / c["body"]["file"]).read_bytes()


def test_generation_reports_no_problem_and_covers_every_required_native_case(corpus):
    _, manifest = corpus
    assert manifest["generator_problems"] == []
    assert set(manifest["required_native_cases"]) == REQUIRED_NATIVE
    groups = {c["group"] for c in manifest["cases"]}
    assert groups == {"native", "derived_variant", "artifact_corruption", "response_mutation", "http_error"}
    assert manifest["oracle_non_value_errors"] == 0
    assert manifest["reader_sampled_mutations"] > 100
    for key, info in manifest["mutation_files"].items():
        assert info["count"] > 2000 and 0 < info["valid"] < info["count"], key


def test_native_cases_are_real_replay_outputs_served_unchanged(corpus):
    root, manifest = corpus
    natives = [c for c in manifest["cases"] if c["group"] == "native"]
    assert {c["id"] for c in natives} == REQUIRED_NATIVE
    for c in natives:
        assert c["http_status"] == 200 and c["expect"] == "success"
        served = json.loads(body_of(root, c))
        serving = served.pop("serving")
        assert serving == {"freshness_classification": "NOT_ASSESSED_" + served["state_label"]}
        assert served["inputs"]["events_sha256"] == c["events_sha256"]
        assert served["synthetic"] is True and served["economic_metrics"] is None
    base = json.loads(body_of(root, case(manifest, "native_base")))
    base.pop("serving")
    assert base == json.loads(GOLDEN.read_text())  # the generated base IS the repository reference


def test_native_base_equals_a_fresh_replay_and_replay_does_not_mutate_its_inputs(corpus):
    root, _ = corpus
    events, cfg = fx.synthetic_session()
    snapshot = json.dumps(events, sort_keys=True), repr(sorted(cfg))
    artifact = replay(events, cfg)
    assert (json.dumps(events, sort_keys=True), repr(sorted(cfg))) == snapshot
    served = json.loads(body_of(root, case(corpus[1], "native_base")))
    served.pop("serving")
    assert served == artifact


def test_instants_beyond_2_53_and_30_digit_texts_are_really_produced(corpus):
    root, manifest = corpus
    high = json.loads(body_of(root, case(manifest, "native_ns_above_2_53")))
    assert int(high["anchor_ns"]) > 2**53 and int(high["as_of_receipt_ns"]) > 2**53
    thirty = json.loads(body_of(root, case(manifest, "native_ns_30_digits")))
    assert len(thirty["as_of_receipt_ns"]) >= 29 and len(thirty["as_of_receipt_ns"]) <= 30
    assert thirty["bars"][0]["start_ns"] == thirty["anchor_ns"]


def test_no_event_after_as_of_reaches_the_result(corpus):
    events, cfg = fx.synthetic_session()
    as_of = cfg["as_of_receipt_ns"]
    later = events + [
        fx._trade(98, as_of + 10 * fx.S, as_of + 9 * fx.S, "tfuture1", "B", "1001", "999"),
        fx._l2(77, as_of + 20 * fx.S, fx._upd([("bid", "1000.25", "88")])),
    ]
    base, leaked = replay(events, cfg), replay(later, cfg)
    assert leaked["inputs"]["events_after_as_of_not_read"] == base["inputs"]["events_after_as_of_not_read"] + 2
    for doc in (base, leaked):
        doc["inputs"].pop("events_after_as_of_not_read")
    assert leaked == base


def test_straddle_and_halt_counters_come_from_the_real_replay(corpus):
    root, manifest = corpus
    cut = json.loads(body_of(root, case(manifest, "native_as_of_straddle")))
    assert cut["book"]["state"] == ["UNRESOLVED", "MESSAGE_STRADDLES_AS_OF"]
    assert cut["inputs"]["events_straddling_as_of_not_read"] == 1
    assert cut["inputs"]["l2_events_not_read_after_straddle"] == 1
    assert cut["book"]["freshness"] is None


def test_derived_variants_are_labelled_as_such_and_never_native(corpus):
    root, manifest = corpus
    variants = [c for c in manifest["cases"] if c["group"] == "derived_variant"]
    assert variants and all("NOT a native" in c["provenance"] for c in variants)
    historical = case(manifest, "variant_historical")
    assert historical["python"]["valid"] and historical["http_status"] == 200
    served = json.loads(body_of(root, historical))
    assert served["evidence_kind"] == "HISTORICAL" and served["serving"]["freshness_classification"] == "NOT_ASSESSED_HISTORICAL"
    inconsistent = case(manifest, "variant_qualified_with_unresolved")
    assert not inconsistent["python"]["valid"] and inconsistent["http_status"] == 503


def test_corrupted_artifacts_are_refused_by_the_real_reader_with_native_codes(corpus):
    _, manifest = corpus
    corrupted = [c for c in manifest["cases"] if c["group"] == "artifact_corruption"]
    assert len(corrupted) >= 15
    codes = {c["error_code"] for c in corrupted}
    assert codes <= {"MARKET_FLOW_INVALID_SCHEMA", "MARKET_FLOW_MALFORMED_JSON", "MARKET_FLOW_UNREADABLE", "MARKET_FLOW_TOO_LARGE"}
    assert {"MARKET_FLOW_INVALID_SCHEMA", "MARKET_FLOW_MALFORMED_JSON", "MARKET_FLOW_TOO_LARGE", "MARKET_FLOW_UNREADABLE"} <= codes
    assert all(c["http_status"] == 503 for c in corrupted)


def test_response_mutations_carry_a_python_verdict_that_matches_their_intent(corpus):
    root, manifest = corpus
    raws = [c for c in manifest["cases"] if c["group"] == "response_mutation"]
    assert sum(1 for c in raws if c["python"]["valid"]) >= 6 and sum(1 for c in raws if not c["python"]["valid"]) >= 25
    for c in raws:
        assert publication_verdict(body_of(root, c))["valid"] == c["python"]["valid"], c["id"]


def test_the_unicode_oracle_is_recorded_with_its_exact_runtime(corpus):
    _, manifest = corpus
    oracle = manifest["oracle"]
    assert oracle["python_version"].startswith("%d.%d." % sys.version_info[:2])
    assert oracle["unicode_version"] == unicodedata.unidata_version
    assert oracle["nonprintable_ranges"] == nonprintable_ranges()
    for lo, hi in oracle["nonprintable_ranges"]:
        assert not chr(lo).isprintable() and not chr(hi).isprintable()
        assert chr(lo - 1).isprintable() if lo else True


def test_generation_is_deterministic(corpus, tmp_path):
    root, _ = corpus
    second = tmp_path / "second"
    generate_market_flow_fixture(second)
    first_files = sorted(p.relative_to(root) for p in (root / CORPUS_DIR).rglob("*") if p.is_file())
    second_files = sorted(p.relative_to(second) for p in (second / CORPUS_DIR).rglob("*") if p.is_file())
    assert first_files == second_files and len(first_files) > 100
    for rel in first_files:
        assert (root / rel).read_bytes() == (second / rel).read_bytes(), rel
