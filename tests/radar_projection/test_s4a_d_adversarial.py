"""S4-a — adversarial exports whose seal has been RECOMPUTED, and SA7 (evidence separation).

Each case tampers with a real export and reseals it, as anyone could: the SHA-256 is
then correct, so the refusal can only come from the structural, scientific and
authority invariants. This shows that validation does not rest on the seal alone.
"""
from __future__ import annotations

import copy
import random

import pytest

from observability.radar_projection.verifier import ProjectionRefusal, verify_export
from tests.radar_projection._exports import BATCH, export, loads, market, reseal

INCOHERENT = "r0_syn_04_incoherent"
TOP = "kraken:spot:BTC/USDT"           # candidate rank 1, ADMISSIBLE, COMPLETE
L2_MISSING = "mexc:spot:BTC/USDT"      # ADMISSIBLE, score INCOMPLETE (l2 missing), not a candidate
UNKNOWN_M = "kraken:perp:ETH/USD"      # UNKNOWN decision, observation present
ABSENT_M = "mexc:spot:PEPE/USDT"       # UNKNOWN, no observation
_BASE = {}


def base(source=INCOHERENT, mission="DEEP_OBSERVATION") -> dict:
    key = (source, mission)
    if key not in _BASE:
        _BASE[key] = loads(export(source, mission))
    return copy.deepcopy(_BASE[key])


def refused_after(mutate, source=INCOHERENT, mission="DEEP_OBSERVATION") -> str:
    d = base(source, mission)
    mutate(d)
    with pytest.raises(ProjectionRefusal) as exc:
        verify_export(reseal(d))
    return exc.value.code


def test_baselines_are_valid():
    for source in (INCOHERENT, BATCH):
        assert verify_export(reseal(base(source)))["doc"]["schema_version"] == "radar-evaluation/1.2.0"


# ---------------------------------------------------------------- authority (SA7 / Phase D)
def _set(path, value):
    def f(d):
        target = d
        for k in path[:-1]:
            target = target[k]
        target[path[-1]] = value
    return f


AUTHORITY_CASES = {
    "execution_true": (_set(["authority", "execution_authority"], True), "AUTHORITY_INVARIANT"),
    "execution_zero_int": (_set(["authority", "execution_authority"], 0), "AUTHORITY_INVARIANT"),
    "collection_true": (_set(["authority", "collection_authority"], True), "AUTHORITY_INVARIANT"),
    "proposal_authorized": (_set(["authority", "proposal_status"], "AUTHORIZED"), "AUTHORITY_INVARIANT"),
    "extra_authority_key": (_set(["authority", "live_authority"], False), "AUTHORITY_INVARIANT"),
    "network_enabled": (_set(["mode", "network"], "ENABLED"), "AUTHORITY_INVARIANT"),
    "paper_enabled": (_set(["mode", "paper"], "ENABLED"), "AUTHORITY_INVARIANT"),
    "deep_observation_job": (_set(["deep_observation_jobs"], [{"market_id": TOP}]), "AUTHORITY_INVARIANT"),
    "admission_granted": (_set(["dataset", "admission"], "ADMITTED"), "ADMISSION_INVARIANT"),
    "candidate_authorized": (_set(["candidates", 0, "status"], "AUTHORIZED"), "AUTHORITY_INVARIANT"),
    "production_budgets": (_set(["budgets", "production"], {"status": "MEASURED", "values": {}}),
                           "PRODUCTION_BUDGETS_INVARIANT"),
}


@pytest.mark.parametrize("case", sorted(AUTHORITY_CASES))
def test_SA7_authority_invariants_resist_a_recomputed_seal(case):
    mutate, code = AUTHORITY_CASES[case]
    assert refused_after(mutate) == code


# ---------------------------------------------------------------- evidence (SA7)
def _evidence(kind, everywhere=True):
    def f(d):
        d["dataset"]["evidence_kind"] = kind
        d["mode"]["evidence"] = kind
        if everywhere:
            for m in d["markets"]:
                m["observation"]["evidence_kind"] = kind
    return f


@pytest.mark.parametrize("source", [INCOHERENT, BATCH])
def test_SA7_historical_is_not_projected(source):
    assert refused_after(_evidence("HISTORICAL"), source) == "EVIDENCE_HISTORICAL_NOT_SUPPORTED"


@pytest.mark.parametrize("source", [INCOHERENT, BATCH])
def test_SA7_live_is_always_refused(source):
    assert refused_after(_evidence("LIVE"), source) == "EVIDENCE_LIVE_REFUSED"


@pytest.mark.parametrize("kind", ["REAL", "synthetic", "PAPER", ""])
def test_SA7_unknown_evidence_kind_is_refused(kind):
    assert refused_after(_evidence(kind)) in ("EVIDENCE_KIND_UNKNOWN", "STRING_EXPECTED")


def test_SA7_mode_and_dataset_evidence_must_agree():
    assert refused_after(_set(["mode", "evidence"], "HISTORICAL")) == "EVIDENCE_MIXED"


def test_SA7_one_market_with_other_evidence_is_refused():
    def f(d):
        market(d, TOP)["observation"]["evidence_kind"] = "HISTORICAL"
    assert refused_after(f) == "EVIDENCE_MIXED"


def test_SA7_fixture_cannot_carry_batch_inputs():
    assert refused_after(_set(["inputs"], base(BATCH)["inputs"])) == "INPUTS_NOT_ALLOWED_FOR_FIXTURE"


def test_SA7_dataset_schema_must_be_known():
    assert refused_after(_set(["dataset", "schema"], "radar-live/1.0.0")) == "DATASET_SCHEMA_NOT_SUPPORTED"


def test_SA7_batch_adapter_version_is_pinned():
    assert refused_after(_set(["dataset", "adapter_version"], "radar-adapter/2.0.0"), BATCH) == "VALUE_NOT_ALLOWED"


def test_SA7_batch_reference_state_and_reason_agree():
    def f(d):
        d["inputs"]["catalogue_manifest"]["reason"] = "FORGED"
    assert refused_after(f, BATCH) == "REF_STATE_REASON"


# ---------------------------------------------------------------- scientific coherence (SA5 / SA6)
def _decision(mid, decision, reasons, score=None, scientific=None):
    def f(d):
        m = market(d, mid)
        m["admissibility"]["decision"] = decision
        m["admissibility"]["reasons"] = reasons
        m["lifecycle"]["scientific"] = scientific or decision
        m["score"] = score
    return f


def _unknown_scored(d):
    m = market(d, L2_MISSING)
    m["score"]["components"]["l2"] = 40
    m["score"]["missing"] = []
    m["score"]["quality"] = "COMPLETE"
    m["score"]["max_reachable"] = "100.00"


def _swap_ranks(d):
    d["candidates"][0]["rank"], d["candidates"][1]["rank"] = 2, 1


def _reverse_candidates(d):
    d["candidates"].reverse()
    for i, c in enumerate(d["candidates"]):
        c["rank"] = i + 1


def _drop_candidate(d):
    d["candidates"].pop()
    d["counts"]["candidates"] -= 1


def _duplicate_market(d):
    d["markets"].insert(1, copy.deepcopy(d["markets"][0]))


def _unordered_markets(d):
    d["markets"][0], d["markets"][1] = d["markets"][1], d["markets"][0]


SCIENCE_CASES = {
    "admissible_with_blocking_reasons": (
        _decision(UNKNOWN_M, "ADMISSIBLE", base()["markets"][2]["admissibility"]["reasons"]),
        "DECISION_REASONS_MISMATCH"),
    "unknown_without_reasons": (_decision(UNKNOWN_M, "UNKNOWN", []), "DECISION_REASONS_MISMATCH"),
    "lifecycle_disagrees": (_set(["markets", 2, "lifecycle", "scientific"], "ADMISSIBLE"),
                            "DECISION_LIFECYCLE_MISMATCH"),
    "reasons_unordered": (lambda d: market(d, "kraken:perp-inv:BTC/USD")["admissibility"]["reasons"].reverse(),
                          "REASONS_NOT_ORDERED_OR_DUPLICATED"),
    "unknown_given_a_score": (_set(["markets", 2, "score"], base()["markets"][7]["score"]),
                              "SCORE_ON_NON_ADMISSIBLE"),
    "admissible_without_score": (lambda d: market(d, L2_MISSING).update(score=None), "ADMISSIBLE_WITHOUT_SCORE"),
    "unknown_component_scored": (_unknown_scored, "UNKNOWN_SCORED"),
    "missing_list_forged": (lambda d: market(d, L2_MISSING)["score"].update(missing=[]), "SCORE_MISSING_MISMATCH"),
    "quality_forged": (lambda d: market(d, L2_MISSING)["score"].update(quality="COMPLETE"), "SCORE_QUALITY_MISMATCH"),
    "weights_changed": (lambda d: market(d, TOP)["score"]["weights"].update(l2=40, cost=-15), "WEIGHTS_MISMATCH"),
    "score_as_number_string": (lambda d: market(d, TOP)["score"].update(value="88"), "SCORE_DECIMAL_EXPECTED"),
    "score_above_100": (lambda d: market(d, TOP)["score"].update(value="188.00"), "SCORE_DECIMAL_EXPECTED"),
    "criterion_unknown_silenced": (lambda d: market(d, UNKNOWN_M)["criteria"]["l2_quality"].update(reason=None),
                                   "UNKNOWN_WITHOUT_REASON"),
    "absent_observation_silenced": (lambda d: market(d, ABSENT_M)["observation"].update(reason=None),
                                    "UNKNOWN_WITHOUT_REASON"),
    "freshness_without_observation": (lambda d: market(d, ABSENT_M)["lifecycle"].update(recent_data="FRESH"),
                                      "FRESHNESS_WITHOUT_OBSERVATION"),
    "mission_of_one_market": (lambda d: market(d, TOP)["admissibility"].update(mission="PRICE_STUDY"),
                              "MISSION_MISMATCH"),
    "mission_rules_forged": (_set(["mission", "needs_bbo"], False), "MISSION_RULES_MISMATCH"),
    "mission_flag_int": (_set(["mission", "needs_bbo"], 1), "MISSION_RULES_MISMATCH"),
    "candidate_not_admissible": (_decision(TOP, "UNKNOWN", [{"code": "FORGED", "decision": "UNKNOWN"}]),
                                 "CANDIDATE_NOT_ADMISSIBLE"),
    "candidate_score_forged": (_set(["candidates", 0, "score"], "99.00"), "CANDIDATE_SCORE_MISMATCH"),
    "candidate_quality_forged": (_set(["candidates", 1, "quality"], "COMPLETE"), "CANDIDATE_SCORE_MISMATCH"),
    "candidate_identity_forged": (_set(["candidates", 0, "base"], "ETH"), "CANDIDATE_IDENTITY_MISMATCH"),
    "candidate_unknown_market": (_set(["candidates", 0, "market_id"], "ghost:spot:X/Y"), "CANDIDATE_NOT_IN_MARKETS"),
    "candidate_excluded": (lambda d: market(d, TOP)["manual"].update(excluded=True),
                           "CANDIDATE_EXCLUDED_BY_OPERATOR"),
    "candidate_regime_forged": (_set(["candidates", 0, "regime"], "VOLATILE"), "CANDIDATE_REGIME_MISMATCH"),
    "candidate_rule_forged": (_set(["candidates", 0, "selection_rule"], "OPERATOR"), "VALUE_NOT_ALLOWED"),
    "candidate_criteria_overlap": (_set(["candidates", 0, "criteria_missing"], ["continuity"]),
                                   "CANDIDATE_CRITERIA_PARTITION"),
    "ranks_swapped": (_swap_ranks, "RANK_SEQUENCE"),
    "candidates_reordered": (_reverse_candidates, "CANDIDATES_NOT_ORDERED"),
    "candidate_duplicated": (lambda d: d["candidates"].__setitem__(1, {**copy.deepcopy(d["candidates"][0]),
                                                                       "rank": 2}),
                             "DUPLICATE_CANDIDATE"),
    "fourth_candidate": (lambda d: d["candidates"].append(copy.deepcopy(d["candidates"][0])),
                         "CANDIDATES_TOO_MANY"),
    "candidate_dropped": (_drop_candidate, "CANDIDATES_INCOMPLETE"),
    "empty_reason_with_candidates": (_set(["candidates_empty_reason"], "NO_ADMISSIBLE_MARKET_FOR_MISSION"),
                                     "EMPTY_REASON_WITH_CANDIDATES"),
    "candidates_erased": (lambda d: d.update(candidates=[], candidates_empty_reason="NO_ADMISSIBLE_MARKET_FOR_MISSION"),
                          "EMPTY_REASON_MISMATCH"),
    "counts_admissible": (lambda d: d["counts"].update(admissible=d["counts"]["admissible"] + 1), "COUNTS_MISMATCH"),
    "counts_unknown_zeroed": (lambda d: d["counts"].update(unknown=0), "COUNTS_MISMATCH"),
    "counts_evaluated": (lambda d: d["counts"].update(evaluated=999), "COUNTS_MISMATCH"),
    "orphans_hidden": (lambda d: d.update(orphan_observations=[]), "COUNTS_MISMATCH"),
    "usage_listed": (lambda d: d["budgets"]["usage"].update(instruments_listed=1), "BUDGET_USAGE_MISMATCH"),
    "manual_flag_without_list": (lambda d: market(d, UNKNOWN_M)["manual"].update(selected=True),
                                 "MANUAL_FLAG_MISMATCH"),
    "manual_item_forged": (lambda d: d["manual"]["excluded"].append(
        {"market_id": TOP, "present": True, "decision": "ADMISSIBLE", "presented_as_admissible": False,
         "note": "X"}), "MANUAL_DECISION_MISMATCH"),
    "manual_ghost_present": (lambda d: d["manual"]["selected"].append(
        {"market_id": "ghost:spot:X/Y", "present": True, "decision": "UNKNOWN", "presented_as_admissible": False,
         "note": "X"}), "MANUAL_PRESENCE_MISMATCH"),
    "duplicate_market": (_duplicate_market, "DUPLICATE_MARKET"),
    "markets_unordered": (_unordered_markets, "MARKETS_NOT_ORDERED"),
    "extra_top_key": (_set(["live"], True), "KEYS_MISMATCH"),
    "extra_market_key": (_set(["markets", 0, "rank"], 1), "KEYS_MISMATCH"),
    "missing_market_key": (lambda d: d["markets"][0].pop("criteria"), "KEYS_MISMATCH"),
    "market_id_type": (_set(["markets", 0, "market_id"], ["x"]), "STRING_EXPECTED"),
    "mission_id_type": (_set(["mission", "id"], ["DEEP_OBSERVATION"]), "VALUE_NOT_ALLOWED"),
    "decision_type": (_set(["markets", 0, "admissibility", "decision"], {"x": 1}), "VALUE_NOT_ALLOWED"),
    "criterion_missing": (lambda d: d["markets"][0]["criteria"].pop("diversity"), "KEYS_MISMATCH"),
    "criterion_state_forged": (lambda d: market(d, TOP)["criteria"]["continuity"].update(state="GOOD"),
                               "VALUE_NOT_ALLOWED"),
    "catalogue_hash_forged": (_set(["markets", 0, "catalogue", "raw_sha256", "kraken_futures_instruments"], "x"),
                              "SHA256_EXPECTED"),
    "authorized_as_string": (_set(["markets", 0, "lifecycle", "authorized"], "true"), "BOOLEAN_EXPECTED"),
    "score_component_invented": (lambda d: market(d, TOP)["score"]["components"].update(liquidity=10),
                                 "SCORE_COMPONENTS"),
    "admissible_without_observation": (lambda d: (market(d, TOP)["observation"].update(present=False, reason="X"),
                                                  market(d, TOP)["lifecycle"].update(recent_data="ABSENT")),
                                       "ABSENT_OBSERVATION_WITH_DATA"),
    "criterion_without_state": (_set(["markets", 0, "criteria", "diversity"], {"regime": None}), "CRITERION_SHAPE"),
    "negative_sample_count": (_set(["markets", 1, "observation", "sample_count"], -1), "INTEGER_EXPECTED"),
    "orphan_reason_not_a_code": (_set(["orphan_observations", 0, "reason"], "no such market"), "CODE_EXPECTED"),
    "policy_duplicate_value": (_set(["policy", "venues"], ["kraken", "kraken"]), "DUPLICATE_VALUE"),
    "spread_not_an_object": (lambda d: market(d, TOP)["criteria"]["spread_depth"].update(spread=[1]),
                             "OBJECT_EXPECTED"),
}


@pytest.mark.parametrize("case", sorted(SCIENCE_CASES))
def test_resealed_incoherent_export_is_refused(case):
    mutate, code = SCIENCE_CASES[case]
    assert refused_after(mutate) == code


def test_case_targets_are_what_the_cases_assume():
    d = base()
    assert d["candidates"][0]["market_id"] == TOP
    assert market(d, L2_MISSING)["score"]["missing"] == ["l2"]
    assert market(d, L2_MISSING)["market_id"] not in [c["market_id"] for c in d["candidates"]]
    assert d["markets"][2]["market_id"] == UNKNOWN_M and d["markets"][7]["market_id"] == TOP
    assert market(d, UNKNOWN_M)["admissibility"]["decision"] == "UNKNOWN"
    assert market(d, ABSENT_M)["observation"]["present"] is False


# ---------------------------------------------------------------- fuzz: only typed refusals escape
def _paths(value, path=()):
    yield path
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _paths(v, path + (k,))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _paths(v, path + (i,))


REPLACEMENTS = [None, 0, -1, 1, True, False, "", "UNKNOWN", "ADMISSIBLE", "x" * 5000, [], {}, [None], {"a": None},
                2**60]


@pytest.mark.parametrize("source", [INCOHERENT, BATCH])
def test_fuzz_resealed_random_mutations_raise_only_typed_refusals(source):
    rng = random.Random(20261125)
    d0 = base(source)
    paths = [p for p in _paths(d0) if p and p[0] != "evaluation_sha256"]
    accepted = 0
    for _ in range(400):
        d = copy.deepcopy(d0)
        path = rng.choice(paths)
        target = d
        for k in path[:-1]:
            target = target[k]
        target[path[-1]] = rng.choice(REPLACEMENTS)
        try:
            verify_export(reseal(d))
            accepted += 1
        except ProjectionRefusal:
            pass
    # Some mutations are legitimately harmless (free text, provenance labels); most are refused.
    assert accepted < 200
