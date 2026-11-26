"""S4A-RV1 — targeted tests for the four findings of the independent counter-review.

RV-01 numeric types, RV-02 structural coherence, RV-03 publication boundary,
RV-04 typed refusals. Every tampered export is RESEALED, so each refusal comes from
an invariant, never from the seal. SYNTHETIC, offline.
"""
from __future__ import annotations

import ast
import copy
import inspect
import re

import pytest

from observability.radar_projection import contract as pc
from observability.radar_projection import projection as P
from observability.radar_projection import verifier as V
from observability.radar_projection.verifier import ProjectionRefusal, verify_export
from tests.radar_projection._exports import BATCH, ROOT, export, loads, market, reseal

INCOHERENT = "r0_syn_04_incoherent"
TOP = "kraken:spot:BTC/USDT"          # rank 1, COMPLETE, l2 TECHNICALLY_COMPATIBLE
L2_MISSING = "mexc:spot:BTC/USDT"     # ADMISSIBLE, INCOMPLETE (l2 missing), not a candidate
ABSENT_M = "mexc:spot:PEPE/USDT"      # UNKNOWN, no observation
SCOPED = "kraken:spot:BTC/USDT"       # in the batch: VERIFIED_TOP_N with a scope
_BASE = {}
MAX_MESSAGE = max(len(c) for c in ("UNSUPPORTED_EVALUATION_SCHEMA",)) + 1 + pc.MAX_REFUSAL_DETAIL + 40


def base(source=INCOHERENT) -> dict:
    if source not in _BASE:
        _BASE[source] = loads(export(source))
    return copy.deepcopy(_BASE[source])


def refused(raw) -> ProjectionRefusal:
    with pytest.raises(ProjectionRefusal) as exc:
        verify_export(raw)
    return exc.value


def code_after(mutate, source=INCOHERENT) -> str:
    d = base(source)
    mutate(d)
    return refused(reseal(d)).code


# ================================================================ RV-01 numeric types
RV01 = {
    "rank_true": (lambda d: d["candidates"][0].update(rank=True), "INTEGER_EXPECTED"),
    "rank_false": (lambda d: d["candidates"][0].update(rank=False), "INTEGER_EXPECTED"),
    "rank_string": (lambda d: d["candidates"][0].update(rank="1"), "INTEGER_EXPECTED"),
    "rank_zero": (lambda d: d["candidates"][0].update(rank=0), "INTEGER_EXPECTED"),
    "rank_four": (lambda d: d["candidates"][2].update(rank=4), "INTEGER_EXPECTED"),
    "component_true": (lambda d: market(d, TOP)["score"]["components"].update(continuity=True), "INTEGER_EXPECTED"),
    "component_101": (lambda d: market(d, TOP)["score"]["components"].update(continuity=101), "INTEGER_EXPECTED"),
    "count_true": (lambda d: d["counts"].update(candidates=True), "INTEGER_EXPECTED"),
    "ceiling_100_99": (lambda d: market(d, TOP)["score"].update(max_reachable="100.99"), "SCORE_DECIMAL_EXPECTED"),
    "score_100_50": (lambda d: (market(d, TOP)["score"].update(value="100.50"),
                                d["candidates"][0].update(score="100.50")), "SCORE_DECIMAL_EXPECTED"),
    "score_negative": (lambda d: market(d, TOP)["score"].update(value="-1.00"), "SCORE_DECIMAL_EXPECTED"),
    "score_leading_zero": (lambda d: market(d, TOP)["score"].update(value="088.00"), "SCORE_DECIMAL_EXPECTED"),
    "score_one_decimal": (lambda d: market(d, TOP)["score"].update(value="88.0"), "SCORE_DECIMAL_EXPECTED"),
    "score_exponent": (lambda d: market(d, TOP)["score"].update(value="8.8E1"), "SCORE_DECIMAL_EXPECTED"),
    "score_int": (lambda d: market(d, TOP)["score"].update(value=88), "SCORE_DECIMAL_EXPECTED"),
    "ceiling_not_100_when_complete": (lambda d: market(d, TOP)["score"].update(max_reachable="90.00"),
                                      "SCORE_CEILING_MISMATCH"),
    "ceiling_forged_when_incomplete": (lambda d: market(d, L2_MISSING)["score"].update(max_reachable="100.00"),
                                       "SCORE_CEILING_MISMATCH"),
    "score_above_ceiling": (lambda d: market(d, L2_MISSING)["score"].update(value="90.00"), "SCORE_ABOVE_CEILING"),
    "ratio_above_one": (lambda d: market(d, TOP)["criteria"]["continuity"].update(ratio="1.5000"), "RATIO_EXPECTED"),
    "ratio_float_like": (lambda d: market(d, TOP)["criteria"]["continuity"].update(ratio="1"), "RATIO_EXPECTED"),
    "decimal_exponent": (lambda d: market(d, TOP)["criteria"]["spread_depth"]["spread"].update(median_bps="2e0"),
                         "DECIMAL_STRING_EXPECTED"),
}


@pytest.mark.parametrize("case", sorted(RV01))
def test_RV01_numeric_types_and_bounds(case):
    mutate, code = RV01[case]
    assert code_after(mutate) == code


def test_RV01_boundaries_0_and_100_are_accepted_as_written_by_the_engine():
    assert V._score_decimal("0.00", "$") == "0.00"
    assert V._score_decimal("100.00", "$") == "100.00"
    for bad in ("100.01", "00.00", "1000.00", "", " 88.00", "88.00 "):
        with pytest.raises(ProjectionRefusal):
            V._score_decimal(bad, "$")


# ================================================================ RV-02 structural coherence
def _crit(mid, name, **kw):
    return lambda d: market(d, mid)["criteria"][name].update(**kw)


def _swap_sources(d):
    d["sources"][0], d["sources"][1] = d["sources"][1], d["sources"][0]


RV02 = {
    # sub-structures: exact keys, types, vocabularies
    "continuity_ratio_list": (_crit(TOP, "continuity", ratio=["x"]), "RATIO_EXPECTED"),
    "continuity_extra_key": (_crit(TOP, "continuity", outside_window=0), "KEYS_MISMATCH"),
    "continuity_class_forged": (_crit(TOP, "continuity", **{"class": "EXCELLENT"}), "VALUE_NOT_ALLOWED"),
    "continuity_covered_gt_expected": (_crit(TOP, "continuity", covered=31), "CONTINUITY_BOUNDS"),
    "continuity_stale_but_available": (_crit(TOP, "continuity", freshness="STALE"), "FRESHNESS_STATE_MISMATCH"),
    "continuity_time_vs_observation": (lambda d: market(d, TOP)["observation"]["time"].update(
        state="UNCERTIFIED", reason="TIMESTAMP_MISSING"), "CONTINUITY_TIME_MISMATCH"),
    "l2_proof_forged": (_crit(TOP, "l2_quality", proof="PROVEN"), "L2_PROOF_MISMATCH"),
    "l2_promoted_to_available": (_crit(TOP, "l2_quality", state="AVAILABLE", reason=None), "L2_STATE_MISMATCH"),
    "l2_status_forged": (_crit(TOP, "l2_quality", status="VERIFIED"), "L2_PROOF_MISMATCH"),
    "l2_unknown_with_status": (_crit(L2_MISSING, "l2_quality", status="VERIFIED"), "KEYS_MISMATCH"),
    "spread_promoted_available": (_crit(TOP, "spread_depth", state="AVAILABLE", reason=None),
                                  "AGGREGATE_STATE_MISMATCH"),
    "spread_basis_forged": (lambda d: market(d, TOP)["criteria"]["spread_depth"]["spread"].update(basis="L2"),
                            "VALUE_NOT_ALLOWED"),
    "depth_unknown_given_values": (lambda d: market(d, TOP)["criteria"]["spread_depth"]["depth"].update(
        bid_quote_10bps="1"), "KEYS_MISMATCH"),
    "activity_unknown_given_zero": (lambda d: market(d, ABSENT_M)["criteria"]["activity_volatility"]["activity"]
                                    .update(value=0), "KEYS_MISMATCH"),
    "activity_value_string": (lambda d: market(d, TOP)["criteria"]["activity_volatility"]["activity"]
                              .update(value="2000"), "INTEGER_EXPECTED"),
    "volatility_regime_forged": (lambda d: market(d, TOP)["criteria"]["activity_volatility"]["volatility"]
                                 .update(regime="CHAOTIC"), "VALUE_NOT_ALLOWED"),
    "diversity_regime_forged": (_crit(TOP, "diversity", regime="VOLATILE"), "DIVERSITY_REGIME_MISMATCH"),
    "cost_missing_forged": (_crit(TOP, "collection_cost", missing=["cpu_pct"]), "COST_MISSING_MISMATCH"),
    "cost_basis_forged": (_crit(TOP, "collection_cost", basis="GUESSED"), "VALUE_NOT_ALLOWED"),
    "reason_on_available": (_crit(TOP, "diversity", reason="FORGED"), "REASON_ON_AVAILABLE"),
    # UNKNOWN, INVALID and null preserved
    "unknown_spread_silenced": (lambda d: market(d, ABSENT_M)["criteria"]["spread_depth"]["spread"]
                                .update(reason=None), "UNKNOWN_WITHOUT_REASON"),
    "absent_observation_criterion_available": (_crit(ABSENT_M, "diversity", state="AVAILABLE", regime="CALM",
                                                     reason=None), "CRITERION_WITHOUT_OBSERVATION"),
    "absent_observation_with_window": (lambda d: market(d, ABSENT_M)["observation"].update(
        window={"start_ms": 1, "end_ms": 1, "step_ms": 1, "points": 2}), "ABSENT_OBSERVATION_WITH_DATA"),
    "absent_recent_data_forged": (lambda d: market(d, ABSENT_M)["lifecycle"].update(recent_data="UNKNOWN"),
                                  "RECENT_DATA_MISMATCH"),
    "observed_recent_data_forged": (lambda d: market(d, TOP)["lifecycle"].update(recent_data="STALE"),
                                    "RECENT_DATA_MISMATCH"),
    "window_end_forged": (lambda d: market(d, TOP)["observation"]["window"].update(end_ms=1), "WINDOW_BOUNDS"),
    # candidate concordance with its market
    "candidate_all_criteria_available": (lambda d: d["candidates"][0].update(
        criteria_available=sorted(pc.CRITERIA), criteria_missing=[]), "CANDIDATE_CRITERIA_MISMATCH"),
    "candidate_criteria_swapped": (lambda d: d["candidates"][0].update(
        criteria_available=d["candidates"][0]["criteria_missing"],
        criteria_missing=d["candidates"][0]["criteria_available"]), "CANDIDATE_CRITERIA_MISMATCH"),
    "candidate_cost_forged": (lambda d: d["candidates"][0]["cost"].update(network_kib_s="1"),
                              "CANDIDATE_COST_MISMATCH"),
    "candidate_cost_basis_measured": (lambda d: d["candidates"][0]["cost"].update(basis="MEASURED"),
                                      "CANDIDATE_COST_MISMATCH"),
    # catalogue identity and fingerprints vs sources
    "catalogue_hash_not_source": (lambda d: market(d, TOP)["catalogue"]["raw_sha256"].update(
        kraken_asset_pairs="0" * 64), "CATALOGUE_SOURCE_MISMATCH"),
    "catalogue_source_market_forged": (lambda d: market(d, TOP)["catalogue"].update(source_market="MEXC_SPOT"),
                                       "CATALOGUE_SOURCE_MISMATCH"),
    "catalogue_collected_forged": (lambda d: market(d, TOP)["catalogue"].update(collected_ms=1),
                                   "CATALOGUE_SOURCE_MISMATCH"),
    "source_hash_forged": (lambda d: d["sources"][1]["raw_sha256"].update(kraken_asset_pairs="0" * 64),
                           "CATALOGUE_SOURCE_MISMATCH"),
    "source_removed": (lambda d: d["sources"].pop(1), "CATALOGUE_SOURCE_UNKNOWN"),
    "sources_unordered": (_swap_sources, "SOURCES_NOT_ORDERED_OR_DUPLICATED"),
    "source_state_forged": (lambda d: d["sources"][0].update(catalogue_state="LIVE"), "VALUE_NOT_ALLOWED"),
    "market_id_forged": (lambda d: market(d, TOP).update(base="ETH"), "MARKET_ID_IDENTITY_MISMATCH"),
    "previous_extra_key": (lambda d: d["markets"][0].update(previous={"market_id": "x", "native_symbol": None,
                                                                       "contract_type": None,
                                                                       "settlement_asset": None, "rank": 1}),
                           "KEYS_MISMATCH"),
}


@pytest.mark.parametrize("case", sorted(RV02))
def test_RV02_resealed_structural_incoherence_is_refused(case):
    mutate, code = RV02[case]
    assert code_after(mutate) == code


RV02_BATCH = {
    "scope_valid_gt_grid": (lambda d: market(d, SCOPED)["criteria"]["l2_quality"]["scope"].update(
        valid_instants=999), "L2_SCOPE_BOUNDS"),
    "scope_verifier_forged": (lambda d: market(d, SCOPED)["criteria"]["l2_quality"]["scope"].update(
        verified_by="TRUST_ME"), "VALUE_NOT_ALLOWED"),
    "scope_removed": (lambda d: market(d, SCOPED)["criteria"]["l2_quality"].pop("scope"), "KEYS_MISMATCH"),
    "input_commit_forged": (lambda d: d["inputs"]["sources"][0].update(producer_commit="HEAD"), "COMMIT_EXPECTED"),
    "input_source_extra_key": (lambda d: d["inputs"]["sources"][0].update(live=False), "KEYS_MISMATCH"),
    "input_catalogue_name_forged": (lambda d: d["inputs"]["catalogues"].update(
        binance={"ref": "x", "sha256": "0" * 64, "state": "VERIFIED", "reason": None}), "VALUE_NOT_ALLOWED"),
}


@pytest.mark.parametrize("case", sorted(RV02_BATCH))
def test_RV02_resealed_batch_incoherence_is_refused(case):
    mutate, code = RV02_BATCH[case]
    assert code_after(mutate, BATCH) == code


def test_RV02_targets_are_what_the_cases_assume():
    d, b = base(), base(BATCH)
    assert market(d, TOP)["criteria"]["l2_quality"]["status"] == "TECHNICALLY_COMPATIBLE"
    assert market(d, TOP)["criteria"]["spread_depth"]["state"] == "PARTIAL"
    assert market(d, L2_MISSING)["criteria"]["l2_quality"]["state"] == "UNKNOWN"
    assert market(d, ABSENT_M)["observation"]["present"] is False
    assert market(d, ABSENT_M)["lifecycle"]["recent_data"] == "ABSENT"
    assert d["sources"][1]["market"] == "KRAKEN_SPOT" and d["candidates"][0]["market_id"] == TOP
    assert market(b, SCOPED)["criteria"]["l2_quality"]["status"] == "VERIFIED_TOP_N"


def test_RV02_score_admissibility_and_selection_are_not_recomputed():
    # The verifier never imports the rules, the scoring tables or the selection.
    source = (ROOT / "observability" / "radar_projection" / "verifier.py").read_text(encoding="utf-8")
    for name in ("CONTINUITY_POINTS", "SPREAD_POINTS_BPS", "ACTIVITY_POINTS", "L2_POINTS", "COST_POINTS_KIB_S",
                 "select_candidates", "DIVERSITY_ORDER", "REGIME_ACTIVE_BPS", "BBO_COVERAGE_MIN",
                 "CONTINUITY_GOOD", "radar_selection.selection", "radar_selection.engine"):
        assert name not in source, name
    assert not re.search(r"(?<![_A-Za-z])(admissibility|score|criteria|observe)\(", source)


# ================================================================ RV-03 publication boundary
def test_RV03_public_surface_is_bytes_only():
    assert P.__all__ == ["project", "project_bytes"]
    public = {n for n, v in vars(P).items() if callable(v) and not n.startswith("_")
              and getattr(v, "__module__", "") == P.__name__}
    assert public == {"project", "project_bytes"}
    for fn in (P.project, P.project_bytes):
        assert list(inspect.signature(fn).parameters) == ["raw"]
    assert not hasattr(P, "build_projection") and not hasattr(P, "projection_bytes")


@pytest.mark.parametrize("fn", [P.project, P.project_bytes])
def test_RV03_a_document_cannot_be_declared_verified(fn):
    forged = base()
    forged["authority"]["execution_authority"] = True
    for value in (forged, {"doc": forged, "export_sha256": "0" * 64, "export_bytes": 1}, [forged]):
        with pytest.raises(ProjectionRefusal) as exc:
            fn(value)
        assert exc.value.code == "INPUT_NOT_BYTES"


def test_RV03_the_private_builder_is_called_only_by_project():
    tree = ast.parse((ROOT / "observability" / "radar_projection" / "projection.py").read_text(encoding="utf-8"))
    callers = set()
    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        for call in (c for c in ast.walk(fn) if isinstance(c, ast.Call)):
            if isinstance(call.func, ast.Name) and call.func.id == "_build_projection":
                callers.add(fn.name)
                # Its only argument is what verify_export(raw) returned in the same function.
                assert isinstance(call.args[0], ast.Name)
                sources = [a.value for a in ast.walk(fn) if isinstance(a, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == call.args[0].id for t in a.targets)]
                assert len(sources) == 1 and isinstance(sources[0], ast.Call)
                assert sources[0].func.id == "verify_export" and sources[0].args[0].id == "raw"
    assert callers == {"project"}
    for path in (ROOT / "observability").rglob("*.py"):
        if path.parent.name != "radar_projection":
            assert "_build_projection" not in path.read_text(encoding="utf-8"), path


def test_RV03_verify_export_result_cannot_influence_a_projection():
    raw = export(INCOHERENT)
    first = P.project_bytes(raw)
    verified = verify_export(raw)
    verified["doc"]["authority"]["execution_authority"] = True  # caller-side mutation
    assert P.project_bytes(raw) == first
    assert P.project(raw)["authority"]["execution_authority"] is False


def test_RV03_verify_export_returns_no_verified_declaration():
    out = verify_export(export(INCOHERENT))
    assert set(out) == {"doc", "export_sha256", "export_bytes"}
    assert "integrity" not in out and "integrity" not in out["doc"]


# ================================================================ RV-04 typed refusals
@pytest.mark.parametrize("schema", [
    "radar-evaluation/" + "9" * 5000 + ".0.0",
    "radar-evaluation/1." + "2" * 5000 + ".0",
    "radar-evaluation/1.2." + "0" * 5000,
    "radar-evaluation/1.2.0" + " " * 100,
    "radar-evaluation/9999999.0.0",
    "x" * 100_000,
])
def test_RV04_huge_version_strings_are_typed_refusals(schema):
    d = base()
    d["schema_version"] = schema
    err = refused(reseal(d))
    assert err.code == "UNSUPPORTED_EVALUATION_SCHEMA"
    assert len(str(err)) <= MAX_MESSAGE


@pytest.mark.parametrize("schema,code", [("radar-evaluation/0.999999.999999", "PRE_RREF_EVALUATION"),
                                         ("radar-evaluation/999999.0.0", "UNSUPPORTED_EVALUATION_SCHEMA"),
                                         ("radar-evaluation/1.2.000000", "UNSUPPORTED_EVALUATION_SCHEMA")])
def test_RV04_bounded_digits_still_parse(schema, code):
    d = base()
    d["schema_version"] = schema
    assert refused(reseal(d)).code == code


def test_RV04_refusal_messages_are_bounded():
    key = "k" * 200_000
    cases = [('{"%s":1,"%s":2}' % (key, key)).encode(), b"{" * 100_000, b'{"a":' + b"9" * 6000 + b"}"]
    d = base()
    d["markets"][0]["market_id"] = "m" * 4000
    cases.append(reseal(d))
    for raw in cases:
        err = refused(raw)
        assert len(str(err)) <= MAX_MESSAGE, (err.code, len(str(err)))


def test_RV04_deep_nesting_inside_a_resealed_export_is_typed():
    d = base()
    nested = "x"
    for _ in range(200):
        nested = [nested]
    d["markets"][0]["previous"] = {"market_id": "x", "native_symbol": nested, "contract_type": None,
                                   "settlement_asset": None}
    assert refused(reseal(d)).code == "STRING_EXPECTED"
    # Formerly free-form fields are now closed: nothing deep can reach the projection builder.
    d = base()
    d["budgets"]["limits"]["max_cycle_ms"] = nested
    assert refused(reseal(d)).code == "INTEGER_EXPECTED"
    d = base()
    d["manual"]["selected"] = [{"market_id": "ghost:spot:X/Y", "present": False, "decision": "UNKNOWN",
                                "presented_as_admissible": False, "note": nested}]
    assert refused(reseal(d)).code == "CODE_EXPECTED"


def test_RV04_budget_limits_are_closed():
    d = base()
    d["budgets"]["limits"]["live_budget"] = 1
    assert refused(reseal(d)).code == "KEYS_MISMATCH"
    d = base()
    d["budgets"]["limits"]["profile"] = "PRODUCTION"
    assert refused(reseal(d)).code == "BUDGET_PROFILE_MISMATCH"


def test_RV04_project_wraps_an_unexpected_builder_failure(monkeypatch):
    def explode(verified):
        raise RecursionError("simulated")

    monkeypatch.setattr(P, "_build_projection", explode)
    with pytest.raises(ProjectionRefusal) as exc:
        P.project(export(INCOHERENT))
    assert exc.value.code == "STRUCTURE_INVALID"


def test_RV04_safety_net_of_the_verifier_is_typed(monkeypatch):
    def explode(doc):
        raise KeyError("simulated")

    monkeypatch.setattr(V, "_budgets", explode)
    assert refused(export(INCOHERENT)).code == "STRUCTURE_INVALID"


def test_RV04_only_typed_refusals_escape_any_stage(monkeypatch):
    # Parsing, canonicalisation and validation failures all become ProjectionRefusal.
    raw = export(INCOHERENT)

    def explode(*a, **k):
        raise RecursionError("simulated")

    monkeypatch.setattr(V, "canonical", explode)
    assert refused(raw).code == "INPUT_MALFORMED"
