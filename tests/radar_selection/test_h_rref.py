"""R-REF — no mandatory reference market (radar-rules/1.2.0, radar-ranking/1.3.0,
radar-evaluation/1.2.0) and the D-R1 archive of the former engines' outputs.

SYNTHETIC only, offline. The archive is verified by its fingerprints; it is never
recomputed here (no historical engine is kept active). The differential tests
compare the current engine with the archived radar-evaluation/1.1.0 outputs of
the R1-B engine (77bd30e) and require that removing the privileged reference is
the only change.
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal

import pytest

from observability.radar_selection import contract as c
from observability.radar_selection.engine import evaluate, evaluate_batch
from observability.radar_selection.fixture import canonical
from observability.radar_selection.manual import empty_preferences
from observability.radar_selection.selection import select_candidates
from tests.radar_selection import build_batches as bb
from tests.radar_selection._helpers import NAMES, ROOT, ev, market

ARCHIVE = ROOT / "docs" / "research" / "radar_rref" / "archive"
MANIFEST = ARCHIVE / "MANIFEST.json"
# Pinned: any rewrite of the manifest (and so of an archived output's fingerprint) fails here.
MANIFEST_SHA256 = "86835f5b7fa6c9cdf50412dc051d279754d2e083c32ef06a855560426fe46143"
ENGINES = {
    "R0": {"commit": "ca0354f99b2ec2c8fa5ec8ba61c21280f91ed823", "schema_version": "radar-evaluation/1.0.0",
           "rules_version": "radar-rules/1.0.0", "ranking_version": "radar-ranking/1.1.0"},
    "R1-B": {"commit": "77bd30e2888a11207c2c0dbce19eaa62fd4421ac", "schema_version": "radar-evaluation/1.1.0",
             "rules_version": "radar-rules/1.1.0", "ranking_version": "radar-ranking/1.2.0"},
}
FORMER_REFERENCE = "kraken:spot:BTC/USDT"
MISSIONS = tuple(c.MISSIONS)
EVIDENCE = bb.EVIDENCE
BATCH_NAME = "r1b_syn_01_btc_atom"
ALL_BLOBS = {str(p.relative_to(EVIDENCE)): p.read_bytes() for p in EVIDENCE.rglob("*") if p.is_file()}


def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def current(name: str, mission: str, prefs: dict | None = None) -> dict:
    """Current engine on the same source bytes the archived output was produced from."""
    if name.startswith("r1b_"):
        raw = (EVIDENCE / "batches" / f"{name}.json").read_bytes()
        return evaluate_batch(raw, dict(ALL_BLOBS), prefs, mission)
    raw = (ROOT / "observability" / "radar_selection" / "fixtures" / f"{name}.json").read_bytes()
    return evaluate(raw, prefs, mission)


def archived(stage_dir: str, name: str, mission: str) -> dict:
    return json.loads((ARCHIVE / stage_dir / f"{name}.{mission}.json").read_text(encoding="utf-8"))


R1B_CASES = [(e["path"].split("/")[1].rsplit(".", 2)[0], e["mission"])
             for e in json.loads(MANIFEST.read_text(encoding="utf-8"))["entries"] if e["engine"]["stage"] == "R1-B"]


# ------------------------------------------------------------------ versions (D-R2)
def test_RREF_versions_are_the_approved_ones():
    assert c.EVALUATION_SCHEMA == "radar-evaluation/1.2.0"
    assert c.RULES_VERSION == "radar-rules/1.2.0"
    assert c.RANKING_VERSION == "radar-ranking/1.3.0"
    # Other schemas unchanged.
    assert (c.FIXTURE_SCHEMA, c.BATCH_SCHEMA, c.ADAPTER_VERSION, c.PREFERENCES_SCHEMA, c.HISTORY_SCHEMA) == (
        "radar-fixture/1.0.0", "radar-batch/1.0.0", "radar-adapter/1.0.0", "radar-preferences/1.0.0",
        "radar-history/1.0.0")
    for name in NAMES:
        e = ev(name)
        assert (e["schema_version"], e["rules_version"], e["ranking_version"]) == (
            c.EVALUATION_SCHEMA, c.RULES_VERSION, c.RANKING_VERSION)


# ------------------------------------------------------------------ RR1
def test_RR1_no_identity_privilege_in_the_engine():
    for attr in ("REFERENCE", "REFERENCE_HISTORICAL_STATUS", "REFERENCE_NOTE"):
        assert not hasattr(c, attr), attr
    sources = {p.name: p.read_text(encoding="utf-8")
               for p in (ROOT / "observability" / "radar_selection").glob("*.py")}
    for name, text in sources.items():
        if name == "universe.py":  # identity examples in the module docstring only
            text = text.split('"""', 2)[2]
        for pattern in (r"kraken:spot:BTC", r"\bREFERENCE", r"\b_reference\b", r"\bin_ranking\b",
                        r"reference_id", r"NOT_YET_HISTORICALLY_ADMITTED"):
            assert not re.search(pattern, text), (name, pattern)


def test_RR1_order_preserving_renaming_keeps_the_calm_ranking():
    """Scope: no fixed identity is privileged. Renaming every market while keeping the
    lexicographic order of the identifiers (same prefix added to all) gives the same
    ranking, mapped to the new names; no name is looked up.

    It does not claim that selection ignores market_id. The calm fixture has ties
    (e.g. seven markets at 82.00 INCOMPLETE, regime CALM), and among tied markets the
    ascending market_id decides (see the tie test below): an order-changing renaming
    may legitimately pick another member of a tie group.
    """
    calm = ev("calm")
    entries = calm["markets"]
    groups: dict = {}
    for m in entries:
        if m["score"] is not None:
            groups.setdefault((m["score"]["quality"], m["score"]["value"]), []).append(m["market_id"])
    assert len(groups[("INCOMPLETE", "82.00")]) == 7  # ties exist in this fixture
    base, _ = select_candidates(entries, set())
    renamed = [dict(e, market_id="zz:" + e["market_id"]) for e in entries]
    again, _ = select_candidates(renamed, set())
    assert [x["market_id"] for x in again] == ["zz:" + x["market_id"] for x in base]
    assert [(x["score"], x["regime"], x["base"], x["selection_rule"]) for x in again] == \
           [(x["score"], x["regime"], x["base"], x["selection_rule"]) for x in base]
    # The second candidate is the first of its tie group by market_id, not a privileged name.
    second = base[1]
    tie = sorted(groups[(second["quality"], second["score"])])
    assert second["selection_rule"] == "BASE_DIVERSITY" and second["market_id"] in tie
    bases_before = {base[0]["base"]}
    eligible = [mid for mid in tie if next(m for m in entries if m["market_id"] == mid)["base"] not in bases_before]
    assert second["market_id"] == eligible[0]


def test_RR1_ties_are_broken_by_market_id_only_not_by_a_fixed_privilege(monkeypatch):
    """Two markets with the same quality, score, regime and base: the order is the
    ascending market_id, whatever the input order. The former reference wins or loses
    such a tie by the same lexicographic rule as any market, never by a fixed rank."""
    import itertools

    import observability.radar_selection.selection as sel
    monkeypatch.setattr(sel, "_candidate", lambda e, rank, rule: (e["market_id"], rule))

    def entry(mid, base="BTC", value="88.00", quality="COMPLETE", regime="CALM"):
        return {"market_id": mid, "base": base, "score": {"value": value, "quality": quality},
                "criteria": {"diversity": {"regime": regime}}}

    def ranked(pool):
        return [x[0] for x in select_candidates(pool, set())[0]]

    # The former reference sorts before its twin: it comes first, and only because "kraken" < "mexc".
    pair = [entry(FORMER_REFERENCE), entry("mexc:spot:BTC/USDT")]
    for order in itertools.permutations(pair):
        assert ranked(list(order)) == [FORMER_REFERENCE, "mexc:spot:BTC/USDT"]
    # Same tie against a market that sorts before it: the former reference comes second.
    pair = [entry(FORMER_REFERENCE), entry("binance:spot:BTC/USDT")]
    for order in itertools.permutations(pair):
        assert ranked(list(order)) == ["binance:spot:BTC/USDT", FORMER_REFERENCE]
    # With a third market of another base, the tie still decides which twin takes the slot.
    trio = [entry(FORMER_REFERENCE), entry("mexc:spot:BTC/USDT"), entry("mexc:spot:ETH/USDT", base="ETH")]
    results = {tuple(ranked(list(order))) for order in itertools.permutations(trio)}
    assert results == {(FORMER_REFERENCE, "mexc:spot:BTC/USDT", "mexc:spot:ETH/USDT")}
    # A real difference of score or quality always beats the identifier.
    pair = [entry(FORMER_REFERENCE, value="87.99"), entry("mexc:spot:BTC/USDT")]
    assert ranked(pair) == ["mexc:spot:BTC/USDT", FORMER_REFERENCE]
    pair = [entry(FORMER_REFERENCE, quality="INCOMPLETE", value="95.00"), entry("mexc:spot:BTC/USDT")]
    assert ranked(pair) == ["mexc:spot:BTC/USDT", FORMER_REFERENCE]


# ------------------------------------------------------------------ RR2
def test_RR2_kraken_btc_usdt_can_become_a_candidate():
    e = ev("incoherent")
    ids = [x["market_id"] for x in e["candidates"]]
    assert FORMER_REFERENCE in ids
    assert market(e, FORMER_REFERENCE)["admissibility"]["decision"] == c.ADMISSIBLE
    cand = next(x for x in e["candidates"] if x["market_id"] == FORMER_REFERENCE)
    assert cand["status"] == "PROPOSED_NOT_AUTHORIZED"


def test_RR2_kraken_btc_usdt_is_rejected_by_the_same_rules():
    # Without evidence it is UNKNOWN, unscored and never a candidate (no automatic admission).
    from tests.radar_selection._helpers import clone, doc
    d = clone(doc("incoherent"))
    d["observations"] = [o for o in d["observations"]
                         if not (o["venue"] == "kraken" and o["market_type"] == "SPOT" and o["native_symbol"] == "XBTUSDT")]
    e = ev(d)
    m = market(e, FORMER_REFERENCE)
    assert m["admissibility"]["decision"] != c.ADMISSIBLE and m["score"] is None
    assert FORMER_REFERENCE not in [x["market_id"] for x in e["candidates"]]
    # A stricter mission rejects it like every other market (L2 not verified).
    strict = ev("incoherent", mission="L2_DEPTH_STUDY")
    assert market(strict, FORMER_REFERENCE)["admissibility"]["decision"] == c.TO_QUALIFY
    assert FORMER_REFERENCE not in [x["market_id"] for x in strict["candidates"]]
    # In calm it is scored but loses on the same diversity rule as any market
    # (the CALM slot and base BTC are already taken by a higher-scored market).
    calm = ev("calm")
    assert market(calm, FORMER_REFERENCE)["score"] is not None
    assert FORMER_REFERENCE not in [x["market_id"] for x in calm["candidates"]]
    top = calm["candidates"][0]
    assert top["base"] == "BTC" and Decimal(top["score"]) >= Decimal(market(calm, FORMER_REFERENCE)["score"]["value"])


def test_RR2_manual_exclusion_still_removes_a_market():
    prefs = empty_preferences() | {"excluded": [FORMER_REFERENCE]}
    e = ev("incoherent", prefs=prefs)
    assert FORMER_REFERENCE not in [x["market_id"] for x in e["candidates"]]
    assert market(e, FORMER_REFERENCE)["manual"]["excluded"] is True
    assert e["counts"]["manually_excluded"] == 1
    # Exclusion is a preference, not a decision: the scientific decision is unchanged.
    assert market(e, FORMER_REFERENCE)["admissibility"] == market(ev("incoherent"), FORMER_REFERENCE)["admissibility"]


def test_RR2_all_admissible_excluded_reason_is_renamed():
    admissible = [m["market_id"] for m in ev("incoherent")["markets"] if m["score"]]
    e = ev("incoherent", prefs=empty_preferences() | {"excluded": sorted(admissible)})
    assert e["candidates"] == [] and e["candidates_empty_reason"] == "ADMISSIBLE_MARKETS_ALL_EXCLUDED"


# ------------------------------------------------------------------ RR3
@pytest.mark.parametrize("mission", MISSIONS)
def test_RR3_evaluation_has_no_reference_field(mission):
    outs = [ev(n, mission=mission) for n in NAMES] + [current(BATCH_NAME, mission)]
    for e in outs:
        assert "reference" not in e
        blob = canonical(e).decode("utf-8")
        for needle in ("in_ranking", "NOT_YET_HISTORICALLY_ADMITTED", "REFERENCE_NOT_IN_UNIVERSE",
                       "EXCLUDED_OR_REFERENCE"):
            assert needle not in blob


# ------------------------------------------------------------------ RR4 (D-R1 archive)
def test_RR4_manifest_is_pinned_and_complete():
    raw = MANIFEST.read_bytes()
    assert sha(raw) == MANIFEST_SHA256, "archive manifest rewritten"
    m = json.loads(raw)
    assert m["schema"] == "radar-archive-manifest/1.0.0"
    assert m["evidence_kind"] == "SYNTHETIC" and m["admission"] == "NONE"
    assert {k: v["commit"] for k, v in m["engines"].items()} == {
        "r0_ca0354f": ENGINES["R0"]["commit"], "r1b_77bd30e": ENGINES["R1-B"]["commit"]}
    listed = sorted(e["path"] for e in m["entries"])
    on_disk = sorted(str(p.relative_to(ARCHIVE)) for p in ARCHIVE.rglob("*.json") if p.name != "MANIFEST.json")
    assert listed == on_disk  # nothing added, nothing missing
    assert len(listed) == 27  # R0: 4 fixtures x 3 missions; R1-B: (4 fixtures + 1 batch) x 3 missions


def test_RR4_every_archived_output_matches_its_fingerprints_and_engine():
    for e in manifest()["entries"]:
        raw = (ARCHIVE / e["path"]).read_bytes()
        assert len(raw) == e["bytes"] and sha(raw) == e["sha256"], e["path"]
        doc = json.loads(raw)
        eng = ENGINES[e["engine"]["stage"]]
        assert e["engine"]["commit"] == eng["commit"]
        for k in ("schema_version", "rules_version", "ranking_version"):
            assert doc[k] == e[k] == eng[k], (e["path"], k)
        assert doc["mission"]["id"] == e["mission"]
        assert doc["dataset"]["evidence_kind"] == e["evidence_kind"] == "SYNTHETIC"
        assert doc["dataset"]["id"] == e["source"]["dataset_id"]
        assert doc["dataset"]["sha256"] == e["source"]["dataset_sha256"]
        # The output still carries the seal its engine computed over its own content.
        body = {k: v for k, v in doc.items() if k != "evaluation_sha256"}
        assert sha(canonical(body)) == doc["evaluation_sha256"] == e["evaluation_sha256"], e["path"]
        # Former engines published the mandatory reference; the archive keeps it as produced.
        assert doc["reference"]["market_id"] == FORMER_REFERENCE and doc["reference"]["in_ranking"] is False


def test_RR4_archived_sources_are_the_current_inputs():
    """Fixture and batch bytes the archive cites are still the repository's inputs (no regeneration)."""
    for e in manifest()["entries"]:
        src = e["source"]
        assert sha((ROOT / src["path"]).read_bytes()) == src["sha256"], src["path"]
        assert src["path"].endswith(e["path"].split("/")[1].rsplit(".", 2)[0] + ".json")


def test_RR4_current_engine_never_emits_a_former_version():
    formers = {v["schema_version"] for v in ENGINES.values()}
    for mission in MISSIONS:
        for name in (*NAMES, BATCH_NAME):
            e = current(name, mission) if name == BATCH_NAME else ev(name, mission=mission)
            assert e["schema_version"] not in formers


# ------------------------------------------------------------------ differential (R1-B 1.1.0 -> 1.2.0)
@pytest.mark.parametrize("name,mission", R1B_CASES)
def test_DIFF_markets_decisions_scores_and_reasons_unchanged(name, mission):
    old, new = archived("r1b_77bd30e", name, mission), current(name, mission)
    assert new["markets"] == old["markets"]
    for k in ("dataset", "inputs", "mission", "policy", "sources", "orphan_observations", "manual",
              "evaluation_time_ms", "preferences_sha256", "mode", "authority", "budgets", "deep_observation_jobs"):
        assert new[k] == old[k], k
    assert {k: v for k, v in new["counts"].items() if k != "candidates"} == \
           {k: v for k, v in old["counts"].items() if k != "candidates"}


@pytest.mark.parametrize("name,mission", R1B_CASES)
def test_DIFF_only_the_removed_privilege_explains_ranking_changes(name, mission):
    """Excluding the former reference by preference reproduces the former ranking exactly."""
    old = archived("r1b_77bd30e", name, mission)
    replay = current(name, mission, empty_preferences() | {"excluded": [FORMER_REFERENCE]})
    assert replay["candidates"] == old["candidates"]
    former_reason = old["candidates_empty_reason"]
    expected = {"ADMISSIBLE_MARKETS_ALL_EXCLUDED_OR_REFERENCE": "ADMISSIBLE_MARKETS_ALL_EXCLUDED"}.get(
        former_reason, former_reason)
    assert replay["candidates_empty_reason"] == expected


def test_DIFF_expected_ranking_changes_are_exactly_these():
    """Listed so that any other change of rank is reported (one case changes, all others are identical)."""
    changed = {}
    for name, mission in R1B_CASES:
        old = [x["market_id"] for x in archived("r1b_77bd30e", name, mission)["candidates"]]
        new = [x["market_id"] for x in current(name, mission)["candidates"]]
        if old != new:
            changed[(name, mission)] = (old, new)
    expected_new = ["kraken:spot:BTC/USDT", "mexc:spot:SOL/USDT", "mexc:spot:DOGE/USDT"]
    expected_old = ["mexc:spot:BTC/USDT", "mexc:spot:SOL/USDT", "mexc:spot:DOGE/USDT"]
    assert changed == {("r0_syn_04_incoherent", m): (expected_old, expected_new)
                       for m in ("PRICE_STUDY", "DEEP_OBSERVATION")}
    # Why: same base BTC, same regime CALM; Kraken scores 88.00 COMPLETE against MEXC
    # 82.00 INCOMPLETE (l2 missing), so it wins on quality and score, not on its identifier.
    # It was only set aside by the former fixed reference rule.
    for mission in ("PRICE_STUDY", "DEEP_OBSERVATION"):
        e = ev("incoherent", mission=mission)
        k, m = market(e, FORMER_REFERENCE), market(e, "mexc:spot:BTC/USDT")
        assert (k["score"]["value"], k["score"]["quality"]) == ("88.00", "COMPLETE")
        assert (m["score"]["value"], m["score"]["quality"], m["score"]["missing"]) == ("82.00", "INCOMPLETE", ["l2"])
        assert k["criteria"]["diversity"]["regime"] == m["criteria"]["diversity"]["regime"] == "CALM"


# ------------------------------------------------------------------ RR6
def test_RR6_no_runtime_paper_fin_ppl_advisor_or_collection_effect():
    for name in NAMES:
        e = ev(name)
        assert e["deep_observation_jobs"] == []
        assert e["authority"] == c.AUTHORITY and e["mode"]["network"] == "DISABLED"
        assert all(x["status"] == "PROPOSED_NOT_AUTHORIZED" for x in e["candidates"])
    assert c.ADMISSION == "NONE" and c.AUTHORITY["execution_authority"] is False
