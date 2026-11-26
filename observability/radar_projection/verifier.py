"""S4-a — independent verifier of a frozen Radar export (``radar-evaluation/1.2.0``).

Input: the bytes of one export (the ``export`` command of the Radar terminal, or
an evaluation written as canonical JSON). Output: the verified document, or a
``ProjectionRefusal`` with a stable code. Pure: no clock, no network, no file.

Independence. The verifier never imports the Radar engine, its rules or its
ranking: it recomputes no score, no decision and no rank. It reuses only the
strict reader and the canonicalisation of ``radar_selection.fixture`` (the very
functions that produced the seal), so there is a single canonical form.

What the seal proves. ``evaluation_sha256`` is recomputed from the canonical form
of the content: it proves the content is the one that was sealed (integrity).
It does not prove who produced it: anyone able to edit an export can recompute a
SHA-256. This is why every structural and authority invariant below is checked
on its own, after the seal; a resealed malicious export is still refused.
"""
from __future__ import annotations

import re
from decimal import Decimal

from observability.radar_selection.fixture import RadarRefusal, canonical, sha256_hex, strict_loads

from . import contract as pc

_SHA = re.compile(r"[0-9a-f]{64}", re.ASCII)
_CODE = re.compile(r"[A-Z][A-Z0-9_:]{0,95}", re.ASCII)
# Two decimals, no leading zero (as the engine writes it); 0.00..100.00 is checked on the value.
_SCORE = re.compile(r"(100|[1-9]?[0-9])\.[0-9]{2}", re.ASCII)
_DEC = re.compile(r"[0-9]{1,30}(\.[0-9]{1,30})?", re.ASCII)
_COMMIT = re.compile(r"[0-9a-f]{40}", re.ASCII)
_RATIO = re.compile(r"[01]\.[0-9]{4}", re.ASCII)
_D = pc.MAX_VERSION_DIGITS
_VERSION = re.compile(rf"radar-evaluation/([0-9]{{1,{_D}}})\.([0-9]{{1,{_D}}})\.([0-9]{{1,{_D}}})", re.ASCII)
_MAX_MS = 2**53 - 1

TOP_KEYS = {"schema_version", "rules_version", "ranking_version", "mode", "authority", "dataset", "inputs",
            "mission", "evaluation_time_ms", "preferences_sha256", "policy", "sources", "counts",
            "candidates", "candidates_empty_reason", "manual", "orphan_observations", "markets", "budgets",
            "deep_observation_jobs", "evaluation_sha256"}
DATASET_KEYS = {"id", "schema", "sha256", "bytes", "evidence_kind", "admission", "description"}
MARKET_KEYS = {"market_id", "venue", "market_type", "contract_type", "base", "quote", "native_symbol",
               "settlement_asset", "catalogue", "change", "previous", "lifecycle", "observation", "criteria",
               "admissibility", "manual", "score"}
IDENTITY_KEYS = ("market_id", "venue", "market_type", "contract_type", "base", "quote", "native_symbol",
                 "settlement_asset")
CATALOGUE_KEYS = {"collected_ms", "exclusion", "lifecycle", "metadata_current", "metadata_reason", "native_base",
                  "native_quote", "native_status", "provenance", "raw_sha256", "source_market"}
LIFECYCLE_KEYS = {"discovered", "authorized", "authorization_reason", "source_access", "source_access_reason",
                  "recent_data", "scientific"}
OBSERVATION_KEYS = {"present", "reason", "evidence_kind", "source_id", "evidence_ref", "price_kind", "window",
                    "sample_count", "time", "contradictions"}
ADMISSIBILITY_KEYS = {"mission", "decision", "reasons", "reasons_truncated"}
MANUAL_FLAGS = ("selected", "pinned", "excluded")
SCORE_KEYS = {"value", "components", "weights", "missing", "quality", "max_reachable"}
CANDIDATE_KEYS = {"rank", "market_id", "venue", "market_type", "contract_type", "base", "quote", "native_symbol",
                  "regime", "selection_rule", "reason", "score", "quality", "criteria_available",
                  "criteria_missing", "cost", "limits", "status"}
CANDIDATE_IDENTITY = ("venue", "market_type", "contract_type", "base", "quote", "native_symbol")
MANUAL_ITEM_KEYS = {"market_id", "present", "decision", "presented_as_admissible", "note"}
ORPHAN_KEYS = {"venue", "market_type", "native_symbol", "evidence_refs", "reason"}
SOURCE_KEYS = {"market", "catalogue_state", "catalogue_reason", "collected_ms", "metadata_current",
               "metadata_reason", "raw_sha256", "instruments", "access", "access_reason"}
POLICY_KEYS = {"venues", "market_types", "quotes", "asset_classes", "deny"}
INPUTS_KEYS = {"catalogue_manifest", "catalogues", "sources", "refused_observations"}
REF_STATES = ("VERIFIED", "REFUSED")
INPUT_SOURCE_KEYS = {"source_id", "kind", "corpus_id", "producer_commit", "anchor_sha256", "artifacts", "state",
                     "reason"}
CATALOGUE_NAMES = ("mexc_spot_exchange_info", "mexc_contract_detail", "kraken_asset_pairs", "kraken_assets",
                   "kraken_futures_instruments")
CATALOGUE_STATES = ("COMPLETE", "INCOMPLETE", "UNAVAILABLE")
COUNT_KEYS = {"discovered", "listed", "retired_or_source_not_current", "authorized", "not_authorized",
              "identity_unknown", "evaluated", "admissible", "a_qualifier", "non_admissible", "unknown",
              "scored", "manually_excluded", "candidates", "orphan_observations"}
BUDGET_KEYS = {"profile", "limits", "production", "usage"}
USAGE_KEYS = {"input_bytes", "instruments_listed", "instruments_evaluated", "observations"}


class ProjectionRefusal(RadarRefusal):
    """Stable refusal code of the S4-a verifier (message = ``CODE`` or ``CODE:path``)."""


def _refuse(code: str, path: str = "") -> None:
    # The detail is bounded: a refusal never echoes an unbounded piece of the input.
    path = str(path)[:pc.MAX_REFUSAL_DETAIL]
    raise ProjectionRefusal(f"{code}:{path}" if path else code)


# ---------------------------------------------------------------- type helpers
def _obj(v, keys, path):
    if not isinstance(v, dict):
        _refuse("OBJECT_EXPECTED", path)
    if set(v) != keys:
        _refuse("KEYS_MISMATCH", path)
    return v


def _list(v, path, bound=pc.MAX_LIST):
    if not isinstance(v, list) or len(v) > bound:
        _refuse("LIST_EXPECTED", path)
    return v


def _bool(v, path, nullable=False):
    if not (type(v) is bool or (nullable and v is None)):
        _refuse("BOOLEAN_EXPECTED", path)
    return v


def _int(v, path, nullable=False, lo=0, hi=_MAX_MS):
    if v is None and nullable:
        return v
    if type(v) is not int or not lo <= v <= hi:
        _refuse("INTEGER_EXPECTED", path)
    return v


def _str(v, path, nullable=False):
    if v is None and nullable:
        return v
    if not isinstance(v, str) or not 0 < len(v) <= pc.MAX_TEXT:
        _refuse("STRING_EXPECTED", path)
    return v


def _code(v, path, nullable=True):
    if v is None and nullable:
        return v
    if not isinstance(v, str) or not _CODE.fullmatch(v):
        _refuse("CODE_EXPECTED", path)
    return v


def _sha(v, path):
    if not isinstance(v, str) or not _SHA.fullmatch(v):
        _refuse("SHA256_EXPECTED", path)
    return v


def _one_of(v, allowed, path):
    if not isinstance(v, str) or v not in allowed:
        _refuse("VALUE_NOT_ALLOWED", path)
    return v


def _str_list(v, path, allowed=None):
    _list(v, path)
    for i, x in enumerate(v):
        _str(x, f"{path}[{i}]")
        if allowed is not None:
            _one_of(x, allowed, f"{path}[{i}]")
    if len(set(v)) != len(v):
        _refuse("DUPLICATE_VALUE", path)
    return v


def _same(a, b) -> bool:
    """Strict equality on the canonical form: ``0`` is not ``false``, ``1`` is not ``true``."""
    return canonical(a) == canonical(b)


def _score_decimal(v, path):
    """A score or ceiling: a string with exactly two decimals, between 0.00 and 100.00."""
    if not isinstance(v, str) or not _SCORE.fullmatch(v) or not Decimal(0) <= Decimal(v) <= Decimal(100):
        _refuse("SCORE_DECIMAL_EXPECTED", path)
    return v


def _dec(v, path, nullable=True):
    """A non-negative decimal string as the engine writes it (no float, no exponent)."""
    if v is None and nullable:
        return v
    if not isinstance(v, str) or not _DEC.fullmatch(v):
        _refuse("DECIMAL_STRING_EXPECTED", path)
    return v


def _ratio(v, path):
    """A ratio written with four decimals, between 0.0000 and 1.0000."""
    if not isinstance(v, str) or not _RATIO.fullmatch(v) or Decimal(v) > 1:
        _refuse("RATIO_EXPECTED", path)
    return v


def _sha_map(v, path):
    if not isinstance(v, dict) or len(v) > 16:
        _refuse("OBJECT_EXPECTED", path)
    for k, h in v.items():
        _sha(h, f"{path}.{k}")


# ---------------------------------------------------------------- stage 1: bytes
def _parse(raw) -> dict:
    if not isinstance(raw, (bytes, bytearray)):
        _refuse("INPUT_NOT_BYTES")
    if len(raw) > pc.MAX_EXPORT_BYTES:
        _refuse("INPUT_TOO_LARGE", f"{len(raw)}>{pc.MAX_EXPORT_BYTES}")
    try:
        doc = strict_loads(bytes(raw), pc.MAX_EXPORT_BYTES)
    except ProjectionRefusal:
        raise
    except RadarRefusal as exc:
        # Same typed codes as the Radar reader (INPUT_EMPTY, INPUT_MALFORMED, DUPLICATE_KEY,
        # FLOAT_NOT_ALLOWED, NONFINITE_NUMBER), re-raised under the verifier's type with a
        # bounded detail (a duplicate key may be as long as the input).
        code, _, detail = str(exc).partition(":")
        _refuse(code, detail)
    except (ValueError, RecursionError) as exc:
        # e.g. an integer literal beyond the interpreter's digit limit.
        _refuse("INPUT_MALFORMED", type(exc).__name__)
    if not isinstance(doc, dict):
        _refuse("OBJECT_EXPECTED", "$")
    return doc


def _versions(doc: dict) -> None:
    schema = doc.get("schema_version")
    if not isinstance(schema, str):
        _refuse("EVALUATION_SCHEMA_MISSING")
    if len(schema) > pc.MAX_SCHEMA_CHARS:
        # Bounded before any regex or int(): thousands of digits are a typed refusal.
        _refuse("UNSUPPORTED_EVALUATION_SCHEMA", f"length={len(schema)}")
    if schema in pc.PRE_RREF_SCHEMAS:
        _refuse("PRE_RREF_EVALUATION", schema)
    m = _VERSION.fullmatch(schema)
    if m and (int(m.group(1)), int(m.group(2))) < (1, 2):
        _refuse("PRE_RREF_EVALUATION", schema)
    if schema != pc.EVALUATION_SCHEMA:
        _refuse("UNSUPPORTED_EVALUATION_SCHEMA", schema[:60])
    source = (schema, doc.get("rules_version"), doc.get("ranking_version"))
    if source != pc.SUPPORTED_SOURCE:
        _refuse("UNSUPPORTED_VERSION_COMBINATION")


def _canonical_and_seal(raw: bytes, doc: dict) -> str:
    try:
        form = canonical(doc)
    except (UnicodeEncodeError, ValueError, RecursionError) as exc:
        _refuse("INPUT_MALFORMED", type(exc).__name__)
    if bytes(raw) not in (form, form + b"\n"):
        _refuse("NOT_CANONICAL")
    seal = doc.get("evaluation_sha256")
    if not isinstance(seal, str) or not _SHA.fullmatch(seal):
        _refuse("SEAL_FORMAT")
    body = {k: v for k, v in doc.items() if k != "evaluation_sha256"}
    if sha256_hex(canonical(body)) != seal:
        _refuse("SEAL_MISMATCH")
    return seal


# ---------------------------------------------------------------- stage 2: structure and invariants
def _evidence(doc: dict) -> str:
    _obj(doc["mode"], {"evidence", *pc.MODE_DISABLED}, "$.mode")
    ds = doc["dataset"]
    kind = ds["evidence_kind"]
    if kind in pc.EVIDENCE_REFUSALS:
        _refuse(pc.EVIDENCE_REFUSALS[kind])
    if kind not in pc.PROJECTED_EVIDENCE:
        _refuse("EVIDENCE_KIND_UNKNOWN", str(kind)[:40])
    if kind not in pc.SCHEMA_EVIDENCE[ds["schema"]]:
        _refuse("EVIDENCE_SCHEMA_COMBINATION_REFUSED")
    if doc["mode"]["evidence"] != kind:
        _refuse("EVIDENCE_MIXED", "$.mode.evidence")
    return kind


def _authority(doc: dict) -> None:
    if not _same(doc["authority"], pc.AUTHORITY):
        _refuse("AUTHORITY_INVARIANT", "$.authority")
    if not _same({k: v for k, v in doc["mode"].items() if k != "evidence"}, pc.MODE_DISABLED):
        _refuse("AUTHORITY_INVARIANT", "$.mode")
    if doc["dataset"]["admission"] != pc.ADMISSION:
        _refuse("ADMISSION_INVARIANT", "$.dataset.admission")
    if not _same(doc["deep_observation_jobs"], []):
        _refuse("AUTHORITY_INVARIANT", "$.deep_observation_jobs")


def _dataset(doc: dict) -> None:
    ds = doc["dataset"]
    schema = ds.get("schema") if isinstance(ds, dict) else None
    if schema == pc.FIXTURE_SCHEMA:
        _obj(ds, DATASET_KEYS, "$.dataset")
        if doc["inputs"] is not None:
            _refuse("INPUTS_NOT_ALLOWED_FOR_FIXTURE", "$.inputs")
    elif schema == pc.BATCH_SCHEMA:
        _obj(ds, DATASET_KEYS | {"adapter_version"}, "$.dataset")
        if ds["adapter_version"] != pc.ADAPTER_VERSION:
            _refuse("VALUE_NOT_ALLOWED", "$.dataset.adapter_version")
        _inputs(doc["inputs"])
    else:
        _refuse("DATASET_SCHEMA_NOT_SUPPORTED", "$.dataset.schema")
    _str(ds["id"], "$.dataset.id")
    _sha(ds["sha256"], "$.dataset.sha256")
    _int(ds["bytes"], "$.dataset.bytes", lo=1)
    _str(ds["evidence_kind"], "$.dataset.evidence_kind")
    _str(ds["admission"], "$.dataset.admission")
    _str(ds["description"], "$.dataset.description")


def _ref(r, path):
    _obj(r, {"ref", "sha256", "state", "reason"}, path)
    _str(r["ref"], path + ".ref")
    _sha(r["sha256"], path + ".sha256")
    _one_of(r["state"], REF_STATES, path + ".state")
    _code(r["reason"], path + ".reason")
    if (r["state"] == "VERIFIED") != (r["reason"] is None):
        _refuse("REF_STATE_REASON", path)


def _inputs(inputs) -> None:
    _obj(inputs, INPUTS_KEYS, "$.inputs")
    _ref(inputs["catalogue_manifest"], "$.inputs.catalogue_manifest")
    cats = inputs["catalogues"]
    if not isinstance(cats, dict) or len(cats) > 16:
        _refuse("OBJECT_EXPECTED", "$.inputs.catalogues")
    for name, r in cats.items():
        _ref(r, f"$.inputs.catalogues.{name}")
    if not set(cats) <= set(CATALOGUE_NAMES):
        _refuse("VALUE_NOT_ALLOWED", "$.inputs.catalogues")
    for i, s in enumerate(_list(inputs["sources"], "$.inputs.sources", 64)):
        p = f"$.inputs.sources[{i}]"
        _obj(s, INPUT_SOURCE_KEYS, p)
        _str(s["source_id"], p + ".source_id")
        _one_of(s["kind"], ("BBO_REPLAY_WINDOWS",), p + ".kind")
        _str(s["corpus_id"], p + ".corpus_id")
        if not isinstance(s["producer_commit"], str) or not _COMMIT.fullmatch(s["producer_commit"]):
            _refuse("COMMIT_EXPECTED", p + ".producer_commit")
        _sha(s["anchor_sha256"], p + ".anchor_sha256")
        _int(s["artifacts"], p + ".artifacts", hi=pc.MAX_LIST)
        _one_of(s["state"], REF_STATES, p + ".state")
        _code(s["reason"], p + ".reason")
        if (s["state"] == "VERIFIED") != (s["reason"] is None):
            _refuse("REF_STATE_REASON", p)
    for i, r in enumerate(_list(inputs["refused_observations"], "$.inputs.refused_observations")):
        p = f"$.inputs.refused_observations[{i}]"
        _obj(r, {"venue", "market_type", "native_symbol", "source_id", "reason"}, p)
        _one_of(r["venue"], pc.VENUES, p + ".venue")
        _one_of(r["market_type"], pc.MARKET_TYPES, p + ".market_type")
        _str(r["native_symbol"], p + ".native_symbol")
        _str(r["source_id"], p + ".source_id")
        _code(r["reason"], p + ".reason", nullable=False)


def _mission(doc: dict) -> str:
    m = _obj(doc["mission"], {"id", "needs_bbo", "needs_l2_verified", "label"}, "$.mission")
    _one_of(m["id"], pc.MISSIONS, "$.mission.id")
    if not _same([m["needs_bbo"], m["needs_l2_verified"]], list(pc.MISSIONS[m["id"]])):
        _refuse("MISSION_RULES_MISMATCH", "$.mission")
    _str(m["label"], "$.mission.label")
    return m["id"]


# ---------------------------------------------------------------- sub-structures (S4A-RV-02)
# Shapes of the measures and criteria published by radar-rules/1.2.0, taken from the
# engine (surveillance.py, selection.criteria). Each sub-structure is checked for its
# exact keys, types and vocabulary per state; the combinations the engine applies
# (an aggregate state from its parts, the L2 proof from its status, the regime of the
# diversity criterion) are checked as consistency. Nothing is recomputed from data.
def _variant(v, variants, path):
    """``v`` must be an object whose key set is one of ``variants``."""
    if not isinstance(v, dict):
        _refuse("OBJECT_EXPECTED", path)
    if set(v) not in variants:
        _refuse("KEYS_MISMATCH", path)
    return v


def _state_reason(c, states, path):
    """State in ``states``; reason is null if and only if the state is AVAILABLE."""
    _one_of(c.get("state"), states, path + ".state")
    if c["state"] == "AVAILABLE":
        if c["reason"] is not None:
            _refuse("REASON_ON_AVAILABLE", path + ".reason")
    else:
        # UNKNOWN, INVALID and PARTIAL always say why: an unknown is never silent, never 0.
        if c["reason"] is None:
            _refuse("UNKNOWN_WITHOUT_REASON", path)
        _code(c["reason"], path + ".reason", nullable=False)
    return c["state"]


def _aggregate(parts, invalid):
    if invalid:
        return "INVALID"
    if parts == ["AVAILABLE", "AVAILABLE"]:
        return "AVAILABLE"
    if parts == ["UNKNOWN", "UNKNOWN"]:
        return "UNKNOWN"
    return "PARTIAL"


def _l2(c, path):
    if not isinstance(c, dict):
        _refuse("CRITERION_SHAPE", path)
    if c.get("state") == "UNKNOWN":
        _obj(c, {"state", "reason", "proof"}, path)
        _state_reason(c, ("UNKNOWN",), path)
        if c["proof"] != "UNKNOWN":
            _refuse("L2_PROOF_MISMATCH", path + ".proof")
        return
    status = _one_of(c.get("status"), pc.L2_STATUSES, path + ".status")
    keys = {"state", "reason", "proof", "status", "evidence_ref", "depth_levels"}
    _obj(c, keys | {"scope"} if status == "VERIFIED_TOP_N" else keys, path)
    _state_reason(c, ("AVAILABLE", "PARTIAL"), path)
    if c["proof"] != pc.L2_PROOF[status]:
        _refuse("L2_PROOF_MISMATCH", path + ".proof")
    if (c["state"], c["reason"]) != pc.L2_STATE[status]:
        _refuse("L2_STATE_MISMATCH", path)
    _str(c["evidence_ref"], path + ".evidence_ref", nullable=status != "VERIFIED")
    _int(c["depth_levels"], path + ".depth_levels", nullable=status != "VERIFIED_TOP_N", lo=1, hi=10_000)
    if status == "VERIFIED_TOP_N":
        sc = _obj(c["scope"], {"verified_by", "valid_instants", "grid_instants", "excluded_instants"},
                  path + ".scope")
        _one_of(sc["verified_by"], pc.L2_VERIFIERS, path + ".scope.verified_by")
        _int(sc["valid_instants"], path + ".scope.valid_instants")
        _int(sc["grid_instants"], path + ".scope.grid_instants")
        if sc["valid_instants"] > sc["grid_instants"]:
            _refuse("L2_SCOPE_BOUNDS", path + ".scope")
        for j, e in enumerate(_list(sc["excluded_instants"], path + ".scope.excluded_instants",
                                    pc.MAX_EXCLUDED_INSTANTS)):
            ep = f"{path}.scope.excluded_instants[{j}]"
            _obj(e, {"t_ms", "reason"}, ep)
            _int(e["t_ms"], ep + ".t_ms")
            _code(e["reason"], ep + ".reason", nullable=False)


def _continuity(c, path):
    if not isinstance(c, dict):
        _refuse("CRITERION_SHAPE", path)
    if c.get("state") in ("UNKNOWN", "INVALID"):
        _obj(c, {"state", "reason", "time"}, path)
        state = _state_reason(c, ("UNKNOWN", "INVALID"), path)
        time = _one_of(c["time"], pc.TIME_STATES, path + ".time")
        allowed = ("UNKNOWN", "UNCERTIFIED") if state == "UNKNOWN" else ("INCOHERENT", "CERTIFIED")
        if time not in allowed:
            _refuse("CONTINUITY_TIME_MISMATCH", path + ".time")
        return
    _obj(c, {"state", "reason", "time", "class", "ratio", "covered", "expected", "gaps", "longest_gap",
             "freshness", "age_ms"}, path)
    state = _state_reason(c, ("AVAILABLE", "PARTIAL"), path)
    if c["time"] != "CERTIFIED":
        _refuse("CONTINUITY_TIME_MISMATCH", path + ".time")
    _one_of(c["class"], pc.CONTINUITY_CLASSES, path + ".class")
    _ratio(c["ratio"], path + ".ratio")
    for k in ("covered", "expected", "gaps", "longest_gap"):
        _int(c[k], f"{path}.{k}", hi=10_000)
    if c["covered"] > c["expected"] or c["longest_gap"] > c["expected"]:
        _refuse("CONTINUITY_BOUNDS", path)
    fresh = _one_of(c["freshness"], pc.FRESHNESS_CLASSES, path + ".freshness")
    if (state, c["reason"]) != (("AVAILABLE", None) if fresh == "FRESH" else ("PARTIAL", "SOURCE_STALE")):
        _refuse("FRESHNESS_STATE_MISMATCH", path)
    _int(c["age_ms"], path + ".age_ms", lo=-pc.FUTURE_TOLERANCE_MS)


def _spread(v, path):
    if isinstance(v, dict) and v.get("state") == "UNKNOWN":
        _variant(v, ({"state", "reason"}, {"state", "reason", "basis"}), path)
        _state_reason(v, ("UNKNOWN",), path)
        if v.get("basis") is not None:
            _refuse("VALUE_NOT_ALLOWED", path + ".basis")
        return "UNKNOWN"
    _obj(v, {"state", "basis", "median_bps", "bbo_samples", "bbo_coverage", "reason"}, path)
    state = _state_reason(v, ("AVAILABLE", "PARTIAL"), path)
    if v["basis"] != "BBO":
        _refuse("VALUE_NOT_ALLOWED", path + ".basis")
    _dec(v["median_bps"], path + ".median_bps", nullable=False)
    _int(v["bbo_samples"], path + ".bbo_samples", lo=1, hi=10_000)
    _ratio(v["bbo_coverage"], path + ".bbo_coverage")
    return state


def _depth(v, path):
    if isinstance(v, dict) and v.get("state") == "UNKNOWN":
        _variant(v, ({"state", "reason"}, {"state", "reason", "basis"}), path)
        _state_reason(v, ("UNKNOWN",), path)
        if v.get("basis") not in (None, "L2"):
            _refuse("VALUE_NOT_ALLOWED", path + ".basis")
        return "UNKNOWN"
    _obj(v, {"state", "reason", "basis", "bid_quote_10bps", "ask_quote_10bps"}, path)
    state = _state_reason(v, ("AVAILABLE", "PARTIAL"), path)
    if v["basis"] != "L2":
        _refuse("VALUE_NOT_ALLOWED", path + ".basis")
    for k in ("bid_quote_10bps", "ask_quote_10bps"):
        _dec(v[k], f"{path}.{k}", nullable=state == "PARTIAL")
    return state


def _spread_depth(c, invalid, path):
    _obj(c, {"state", "spread", "depth", "reason"}, path)
    state = _state_reason(c, pc.CRITERION_STATES, path)
    parts = [_spread(c["spread"], path + ".spread"), _depth(c["depth"], path + ".depth")]
    if state != _aggregate(parts, invalid):
        _refuse("AGGREGATE_STATE_MISMATCH", path + ".state")


def _activity(v, path):
    if isinstance(v, dict) and v.get("state") == "UNKNOWN":
        _variant(v, ({"state", "reason"}, {"state", "reason", "kind"}), path)
        _state_reason(v, ("UNKNOWN",), path)
        if "kind" in v:
            _str(v["kind"], path + ".kind")
        return "UNKNOWN"
    _obj(v, {"state", "kind", "value", "evidence_ref", "reason"}, path)
    _state_reason(v, ("AVAILABLE",), path)
    _one_of(v["kind"], pc.ACTIVITY_KINDS, path + ".kind")
    _int(v["value"], path + ".value")
    _str(v["evidence_ref"], path + ".evidence_ref", nullable=True)
    return "AVAILABLE"


def _volatility(v, path):
    if isinstance(v, dict) and v.get("state") == "UNKNOWN":
        _variant(v, ({"state", "reason"}, {"state", "reason", "returns", "min_returns"}), path)
        _state_reason(v, ("UNKNOWN",), path)
        for k in ("returns", "min_returns"):
            if k in v:
                _int(v[k], f"{path}.{k}", hi=10_000)
        return None
    _obj(v, {"state", "rms_step_bps", "returns", "regime", "price_kind", "reason"}, path)
    _state_reason(v, ("AVAILABLE",), path)
    _dec(v["rms_step_bps"], path + ".rms_step_bps", nullable=False)
    _int(v["returns"], path + ".returns", lo=1, hi=10_000)
    _one_of(v["price_kind"], pc.PRICE_KINDS, path + ".price_kind")
    return _one_of(v["regime"], pc.REGIMES, path + ".regime")


def _activity_volatility(c, invalid, path):
    _obj(c, {"state", "activity", "volatility", "reason"}, path)
    state = _state_reason(c, pc.CRITERION_STATES, path)
    act = _activity(c["activity"], path + ".activity")
    regime = _volatility(c["volatility"], path + ".volatility")
    vol = "AVAILABLE" if regime is not None else "UNKNOWN"
    if state != _aggregate([act, vol], invalid):
        _refuse("AGGREGATE_STATE_MISMATCH", path + ".state")
    return regime


def _cost(c, path):
    if isinstance(c, dict) and c.get("state") == "UNKNOWN":
        _obj(c, {"state", "reason", "basis"}, path)
        _state_reason(c, ("UNKNOWN",), path)
        if c["basis"] is not None:
            _refuse("VALUE_NOT_ALLOWED", path + ".basis")
        return
    _obj(c, {"state", "reason", "basis", "provenance", *pc.COST_FIELDS, "rate_limit_note", "missing"}, path)
    state = _state_reason(c, ("AVAILABLE", "PARTIAL"), path)
    _one_of(c["basis"], pc.COST_BASES, path + ".basis")
    _str(c["provenance"], path + ".provenance")
    for k in ("network_kib_s", "cpu_pct", "memory_mib", "storage_mib_h"):
        _dec(c[k], f"{path}.{k}")
    _int(c["connections"], path + ".connections", nullable=True, hi=1000)
    _str(c["rate_limit_note"], path + ".rate_limit_note", nullable=True)
    missing = [k for k in pc.COST_FIELDS if c[k] is None]
    if not _same(c["missing"], missing):
        _refuse("COST_MISSING_MISMATCH", path + ".missing")
    if (state, c["reason"]) != (("AVAILABLE", None) if not missing else ("PARTIAL", "COST_FIELDS_MISSING")):
        _refuse("COST_STATE_MISMATCH", path)


def _diversity(c, regime, path):
    if isinstance(c, dict) and c.get("state") == "AVAILABLE":
        _obj(c, {"state", "regime", "reason"}, path)
        _state_reason(c, ("AVAILABLE",), path)
        _one_of(c["regime"], pc.REGIMES, path + ".regime")
    else:
        _obj(c, {"state", "regime", "reason"}, path)
        _state_reason(c, ("UNKNOWN",), path)
        if c["regime"] is not None:
            _refuse("VALUE_NOT_ALLOWED", path + ".regime")
    if c["regime"] != regime:
        _refuse("DIVERSITY_REGIME_MISMATCH", path + ".regime")


def _criteria(crit, ob, path) -> None:
    _obj(crit, set(pc.CRITERIA), path)
    for name in pc.CRITERIA:
        if not isinstance(crit[name], dict) or "state" not in crit[name] or "reason" not in crit[name]:
            _refuse("CRITERION_SHAPE", f"{path}.{name}")
    if not ob["present"]:
        # No observation: every criterion is UNKNOWN with the reason of the absence (SA6).
        for name in pc.CRITERIA:
            c = crit[name]
            if c["state"] != "UNKNOWN" or c["reason"] != ob["reason"]:
                _refuse("CRITERION_WITHOUT_OBSERVATION", f"{path}.{name}")
    _l2(crit["l2_quality"], path + ".l2_quality")
    _continuity(crit["continuity"], path + ".continuity")
    invalid = crit["continuity"]["state"] == "INVALID"
    if ob["present"]:
        time = ob["time"]["state"]
        if crit["continuity"]["time"] != time:
            _refuse("CONTINUITY_TIME_MISMATCH", path + ".continuity.time")
        if invalid != (time == "INCOHERENT" or bool(ob["contradictions"])):
            _refuse("CONTINUITY_INVALID_MISMATCH", path + ".continuity.state")
    _spread_depth(crit["spread_depth"], invalid, path + ".spread_depth")
    regime = _activity_volatility(crit["activity_volatility"], invalid, path + ".activity_volatility")
    _cost(crit["collection_cost"], path + ".collection_cost")
    _diversity(crit["diversity"], regime, path + ".diversity")


def _observation(ob, lc, evidence, path) -> None:
    _obj(ob, OBSERVATION_KEYS, path)
    present = _bool(ob["present"], path + ".present")
    if ob["evidence_kind"] != evidence:
        _refuse("EVIDENCE_MIXED", path + ".evidence_kind")
    t = ob["time"]
    _variant(t, ({"state", "reason"}, {"state", "reason", "missing"}), path + ".time")
    _one_of(t["state"], pc.TIME_STATES, path + ".time.state")
    if (t["state"] == "CERTIFIED") != (t["reason"] is None):
        _refuse("UNKNOWN_WITHOUT_REASON", path + ".time")
    _code(t["reason"], path + ".time.reason")
    if "missing" in t:
        _int(t["missing"], path + ".time.missing", lo=1)
    for j, code in enumerate(_list(ob["contradictions"], path + ".contradictions", 16)):
        _code(code, f"{path}.contradictions[{j}]", nullable=False)
    if ob["contradictions"] != sorted(set(ob["contradictions"])):
        _refuse("DUPLICATE_VALUE", path + ".contradictions")
    _str(ob["source_id"], path + ".source_id", nullable=True)
    if not present:
        if ob["reason"] is None:
            _refuse("UNKNOWN_WITHOUT_REASON", path)
        _code(ob["reason"], path + ".reason", nullable=False)
        if t["state"] != "UNKNOWN" or ob["contradictions"] or any(
                ob[k] is not None for k in ("window", "sample_count", "price_kind", "evidence_ref")):
            _refuse("ABSENT_OBSERVATION_WITH_DATA", path)
        expected = "ABSENT" if ob["reason"] == "NO_OBSERVATION" else "UNKNOWN"
        if lc["recent_data"] in ("FRESH", "STALE"):
            _refuse("FRESHNESS_WITHOUT_OBSERVATION", path.replace(".observation", ".lifecycle.recent_data"))
        if lc["recent_data"] != expected:
            _refuse("RECENT_DATA_MISMATCH", path.replace(".observation", ".lifecycle.recent_data"))
        return
    if ob["reason"] is not None:
        _refuse("VALUE_NOT_ALLOWED", path + ".reason")
    _str(ob["evidence_ref"], path + ".evidence_ref")
    _one_of(ob["price_kind"], pc.PRICE_KINDS, path + ".price_kind")
    _int(ob["sample_count"], path + ".sample_count", hi=pc.MAX_LIST)
    w = _obj(ob["window"], {"start_ms", "end_ms", "step_ms", "points"}, path + ".window")
    _int(w["start_ms"], path + ".window.start_ms", lo=1)
    _int(w["step_ms"], path + ".window.step_ms", lo=1, hi=86_400_000)
    _int(w["points"], path + ".window.points", lo=2, hi=pc.MAX_LIST)
    _int(w["end_ms"], path + ".window.end_ms", lo=1)
    if w["end_ms"] != w["start_ms"] + (w["points"] - 1) * w["step_ms"]:
        _refuse("WINDOW_BOUNDS", path + ".window")


def _recent_data(m, path) -> None:
    """recent_data of an observed market = freshness of its continuity, UNKNOWN when uncertified."""
    if not m["observation"]["present"]:
        return
    cont = m["criteria"]["continuity"]
    expected = cont["freshness"] if cont["state"] in ("AVAILABLE", "PARTIAL") else "UNKNOWN"
    if m["lifecycle"]["recent_data"] != expected:
        _refuse("RECENT_DATA_MISMATCH", path + ".lifecycle.recent_data")


def _catalogue(m, sources, path) -> None:
    cat = _obj(m["catalogue"], CATALOGUE_KEYS, path + ".catalogue")
    cp = path + ".catalogue"
    _one_of(cat["lifecycle"], pc.CATALOGUE_LIFECYCLES, cp + ".lifecycle")
    _sha_map(cat["raw_sha256"], cp + ".raw_sha256")
    _int(cat["collected_ms"], cp + ".collected_ms", nullable=True)
    _code(cat["exclusion"], cp + ".exclusion")
    _bool(cat["metadata_current"], cp + ".metadata_current")
    _code(cat["metadata_reason"], cp + ".metadata_reason")
    for k in ("native_base", "native_quote", "native_status"):
        _str(cat[k], f"{cp}.{k}", nullable=True)
    _str(cat["provenance"], cp + ".provenance")
    market = _one_of(cat["source_market"], pc.SCANNER_MARKETS, cp + ".source_market")
    # Identity and fingerprints of the catalogue agree with its source (sources[]).
    if pc.SCANNER_MARKETS[market] != (m["venue"], m["market_type"]):
        _refuse("CATALOGUE_SOURCE_MISMATCH", cp + ".source_market")
    src = sources.get(market)
    if src is None:
        _refuse("CATALOGUE_SOURCE_UNKNOWN", cp + ".source_market")
    for k in ("raw_sha256", "collected_ms", "metadata_current"):
        if not _same(cat[k], src[k]):
            _refuse("CATALOGUE_SOURCE_MISMATCH", f"{cp}.{k}")


def _identity(m, path) -> None:
    """market_id = venue:type-code:BASE/QUOTE (or ?NATIVE when the identity is insufficient),
    with an optional ~NATIVE suffix when two instruments share the same base id."""
    prefix = f"{m['venue']}:{pc.TYPE_CODES.get(m['contract_type'], 'unknown-contract')}:"
    if m["base"] is None or m["quote"] is None:
        core = f"?{m['native_symbol']}"
    else:
        core = f"{m['base']}/{m['quote']}"
    if m["market_id"] not in (prefix + core, f"{prefix}{core}~{m['native_symbol']}"):
        _refuse("MARKET_ID_IDENTITY_MISMATCH", path + ".market_id")
    prev = m["previous"]
    if prev is not None:
        _obj(prev, {"market_id", "native_symbol", "contract_type", "settlement_asset"}, path + ".previous")
        _str(prev["market_id"], path + ".previous.market_id")
        for k in ("native_symbol", "contract_type", "settlement_asset"):
            _str(prev[k], f"{path}.previous.{k}", nullable=True)


def _admissibility(m, mission, path) -> str:
    a = _obj(m["admissibility"], ADMISSIBILITY_KEYS, path + ".admissibility")
    if a["mission"] != mission:
        _refuse("MISSION_MISMATCH", path + ".admissibility.mission")
    decision = _one_of(a["decision"], pc.DECISIONS, path + ".admissibility.decision")
    _bool(a["reasons_truncated"], path + ".admissibility.reasons_truncated")
    reasons = _list(a["reasons"], path + ".admissibility.reasons", pc.MAX_REASON_CODES)
    pairs = []
    for i, r in enumerate(reasons):
        rp = f"{path}.admissibility.reasons[{i}]"
        _obj(r, {"code", "decision"}, rp)
        _str(r["code"], rp + ".code")
        _one_of(r["decision"], (pc.TO_QUALIFY, pc.NON_ADMISSIBLE, pc.UNKNOWN), rp + ".decision")
        pairs.append((r["decision"], r["code"]))
    ordered = sorted(set(pairs), key=lambda p: (-pc.DECISION_SEVERITY[p[0]], p[1]))
    if pairs != ordered:
        _refuse("REASONS_NOT_ORDERED_OR_DUPLICATED", path + ".admissibility.reasons")
    expected = pairs[0][0] if pairs else pc.ADMISSIBLE
    if decision != expected or (a["reasons_truncated"] and len(pairs) < pc.MAX_REASON_CODES):
        _refuse("DECISION_REASONS_MISMATCH", path + ".admissibility")
    if m["lifecycle"]["scientific"] != decision:
        _refuse("DECISION_LIFECYCLE_MISMATCH", path + ".lifecycle.scientific")
    return decision


def _score(m, decision, path) -> None:
    s = m["score"]
    if decision != pc.ADMISSIBLE:
        if s is not None:
            _refuse("SCORE_ON_NON_ADMISSIBLE", path + ".score")
        return
    if s is None:
        _refuse("ADMISSIBLE_WITHOUT_SCORE", path + ".score")
    _obj(s, SCORE_KEYS, path + ".score")
    if not _same(s["weights"], pc.WEIGHTS):
        _refuse("WEIGHTS_MISMATCH", path + ".score.weights")
    comps = s["components"]
    if not isinstance(comps, dict) or not set(comps) <= set(pc.WEIGHTS) or "continuity" not in comps:
        _refuse("SCORE_COMPONENTS", path + ".score.components")
    for k, v in comps.items():
        _int(v, f"{path}.score.components.{k}", hi=100)
    if s["missing"] != sorted(set(pc.WEIGHTS) - set(comps)):
        _refuse("SCORE_MISSING_MISMATCH", path + ".score.missing")
    if s["quality"] != ("COMPLETE" if not s["missing"] else "INCOMPLETE"):
        _refuse("SCORE_QUALITY_MISMATCH", path + ".score.quality")
    for k in ("value", "max_reachable"):
        _score_decimal(s[k], f"{path}.score.{k}")
    # Ceiling: 100 minus the weights of the missing components (weights are not
    # redistributed). The value can never exceed it. No score is recomputed.
    ceiling = Decimal(100) - sum(Decimal(pc.WEIGHTS[k]) for k in s["missing"])
    if Decimal(s["max_reachable"]) != ceiling:
        _refuse("SCORE_CEILING_MISMATCH", path + ".score.max_reachable")
    if Decimal(s["value"]) > Decimal(s["max_reachable"]):
        _refuse("SCORE_ABOVE_CEILING", path + ".score.value")
    # An unknown input never scores (SA6): a component is present only if its criterion is known.
    crit = m["criteria"]
    known = {
        "continuity": crit["continuity"]["state"] in ("AVAILABLE", "PARTIAL"),
        "spread": (crit["spread_depth"].get("spread") or {}).get("state") == "AVAILABLE",
        "activity": (crit["activity_volatility"].get("activity") or {}).get("state") == "AVAILABLE",
        "l2": crit["l2_quality"]["state"] != "UNKNOWN",
        "cost": crit["collection_cost"]["state"] != "UNKNOWN"
        and crit["collection_cost"].get("network_kib_s") is not None,
    }
    for k in comps:
        if not known[k]:
            _refuse("UNKNOWN_SCORED", f"{path}.score.components.{k}")
    if not m["observation"]["present"]:
        _refuse("ADMISSIBLE_WITHOUT_OBSERVATION", path)


def _market(m, i, mission, evidence, sources) -> str:
    path = f"$.markets[{i}]"
    _obj(m, MARKET_KEYS, path)
    _str(m["market_id"], path + ".market_id")
    _one_of(m["venue"], pc.VENUES, path + ".venue")
    _one_of(m["market_type"], pc.MARKET_TYPES, path + ".market_type")
    for k in ("contract_type", "native_symbol"):
        _str(m[k], f"{path}.{k}")
    for k in ("base", "quote", "settlement_asset"):
        _str(m[k], f"{path}.{k}", nullable=True)
    _identity(m, path)
    _catalogue(m, sources, path)
    _one_of(m["change"], pc.CHANGES, path + ".change")
    lc = _obj(m["lifecycle"], LIFECYCLE_KEYS, path + ".lifecycle")
    _bool(lc["discovered"], path + ".lifecycle.discovered")
    _bool(lc["authorized"], path + ".lifecycle.authorized", nullable=True)
    _str(lc["authorization_reason"], path + ".lifecycle.authorization_reason", nullable=True)
    _one_of(lc["source_access"], pc.SOURCE_ACCESS, path + ".lifecycle.source_access")
    _code(lc["source_access_reason"], path + ".lifecycle.source_access_reason")
    _one_of(lc["recent_data"], pc.RECENT_DATA, path + ".lifecycle.recent_data")
    _one_of(lc["scientific"], pc.DECISIONS, path + ".lifecycle.scientific")
    _observation(m["observation"], lc, evidence, path + ".observation")
    _criteria(m["criteria"], m["observation"], path + ".criteria")
    _recent_data(m, path)
    man = _obj(m["manual"], set(MANUAL_FLAGS), path + ".manual")
    for k in MANUAL_FLAGS:
        _bool(man[k], f"{path}.manual.{k}")
    decision = _admissibility(m, mission, path)
    _score(m, decision, path)
    return decision


def _markets(doc: dict, mission: str, evidence: str) -> dict:
    markets = _list(doc["markets"], "$.markets", pc.MAX_MARKETS)
    sources = {s["market"]: s for s in doc["sources"]}
    by_id = {}
    previous = None
    for i, m in enumerate(markets):
        _market(m, i, mission, evidence, sources)
        mid = m["market_id"]
        if mid in by_id:
            _refuse("DUPLICATE_MARKET", mid[:80])
        if previous is not None and mid < previous:
            _refuse("MARKETS_NOT_ORDERED", f"$.markets[{i}]")
        previous = mid
        by_id[mid] = m
    return by_id


def _candidates(doc: dict, by_id: dict) -> None:
    cands = _list(doc["candidates"], "$.candidates")
    if len(cands) > pc.MAX_CANDIDATES:
        _refuse("CANDIDATES_TOO_MANY", f"{len(cands)}>{pc.MAX_CANDIDATES}")
    seen = set()
    order = []
    for i, cd in enumerate(cands):
        p = f"$.candidates[{i}]"
        _obj(cd, CANDIDATE_KEYS, p)
        _int(cd["rank"], p + ".rank", lo=1, hi=pc.MAX_CANDIDATES)  # a boolean is not a rank
        if cd["rank"] != i + 1:
            _refuse("RANK_SEQUENCE", p + ".rank")
        mid = _str(cd["market_id"], p + ".market_id")
        if mid in seen:
            _refuse("DUPLICATE_CANDIDATE", p)
        seen.add(mid)
        m = by_id.get(mid)
        if m is None:
            _refuse("CANDIDATE_NOT_IN_MARKETS", p)
        if any(cd[k] != m[k] for k in CANDIDATE_IDENTITY):
            _refuse("CANDIDATE_IDENTITY_MISMATCH", p)
        if m["admissibility"]["decision"] != pc.ADMISSIBLE:
            _refuse("CANDIDATE_NOT_ADMISSIBLE", p)
        if m["manual"]["excluded"]:
            _refuse("CANDIDATE_EXCLUDED_BY_OPERATOR", p)
        if cd["score"] != m["score"]["value"] or cd["quality"] != m["score"]["quality"]:
            _refuse("CANDIDATE_SCORE_MISMATCH", p)
        if cd["regime"] != m["criteria"]["diversity"].get("regime"):
            _refuse("CANDIDATE_REGIME_MISMATCH", p)
        _one_of(cd["selection_rule"], pc.SELECTION_RULES, p + ".selection_rule")
        if cd["status"] != pc.CANDIDATE_STATUS:
            _refuse("AUTHORITY_INVARIANT", p + ".status")
        _str(cd["reason"], p + ".reason")
        _str_list(cd["criteria_available"], p + ".criteria_available", pc.CRITERIA)
        _str_list(cd["criteria_missing"], p + ".criteria_missing", pc.CRITERIA)
        if set(cd["criteria_available"]) | set(cd["criteria_missing"]) != set(pc.CRITERIA) or \
                set(cd["criteria_available"]) & set(cd["criteria_missing"]):
            _refuse("CANDIDATE_CRITERIA_PARTITION", p)
        # Available / missing criteria are those of the market, in the engine's order.
        crit = m["criteria"]
        if cd["criteria_available"] != sorted(k for k in pc.CRITERIA if crit[k]["state"] == "AVAILABLE") or \
                cd["criteria_missing"] != sorted(k for k in pc.CRITERIA if crit[k]["state"] != "AVAILABLE"):
            _refuse("CANDIDATE_CRITERIA_MISMATCH", p)
        # The candidate's cost is a copy of the market's collection_cost fields.
        cost = crit["collection_cost"]
        if not _same(cd["cost"], {k: cost.get(k) for k in pc.CANDIDATE_COST_FIELDS}):
            _refuse("CANDIDATE_COST_MISMATCH", p + ".cost")
        _str_list(cd["limits"], p + ".limits")
        order.append((cd["quality"] != "COMPLETE", cd["score"], mid))
    # Presentation order of the published values (no ranking is recomputed): quality,
    # then published score descending, then market_id.
    keyed = [(q, -int(s.replace(".", "")), mid) for q, s, mid in order]
    if keyed != sorted(keyed):
        _refuse("CANDIDATES_NOT_ORDERED")
    reason = doc["candidates_empty_reason"]
    scored_open = [m for m in by_id.values() if m["score"] is not None and not m["manual"]["excluded"]]
    scored = [m for m in by_id.values() if m["score"] is not None]
    if cands:
        if reason is not None:
            _refuse("EMPTY_REASON_WITH_CANDIDATES")
        if len(cands) < min(pc.MAX_CANDIDATES, len(scored_open)):
            _refuse("CANDIDATES_INCOMPLETE")
    else:
        expected = ("NO_ADMISSIBLE_MARKET_FOR_MISSION" if not scored else
                    "ADMISSIBLE_MARKETS_ALL_EXCLUDED" if not scored_open else None)
        if expected is None or reason != expected:
            _refuse("EMPTY_REASON_MISMATCH", "$.candidates_empty_reason")


def _manual(doc: dict, by_id: dict) -> None:
    manual = _obj(doc["manual"], set(MANUAL_FLAGS), "$.manual")
    for k in MANUAL_FLAGS:
        items = _list(manual[k], f"$.manual.{k}")
        ids = []
        for i, it in enumerate(items):
            p = f"$.manual.{k}[{i}]"
            _obj(it, MANUAL_ITEM_KEYS, p)
            _str(it["market_id"], p + ".market_id")
            _bool(it["present"], p + ".present")
            _bool(it["presented_as_admissible"], p + ".presented_as_admissible")
            _code(it["note"], p + ".note", nullable=False)
            m = by_id.get(it["market_id"])
            if it["present"] != (m is not None):
                _refuse("MANUAL_PRESENCE_MISMATCH", p)
            decision = m["admissibility"]["decision"] if m is not None else pc.UNKNOWN
            if it["decision"] != decision or it["presented_as_admissible"] != (decision == pc.ADMISSIBLE):
                _refuse("MANUAL_DECISION_MISMATCH", p)
            ids.append(it["market_id"])
        if len(set(ids)) != len(ids):
            _refuse("DUPLICATE_VALUE", f"$.manual.{k}")
        flagged = {mid for mid, m in by_id.items() if m["manual"][k]}
        if flagged != {mid for mid in ids if mid in by_id}:
            _refuse("MANUAL_FLAG_MISMATCH", f"$.manual.{k}")


def _counts(doc: dict, by_id: dict) -> None:
    counts = _obj(doc["counts"], COUNT_KEYS, "$.counts")
    for k, v in counts.items():
        _int(v, f"$.counts.{k}")
    ms = list(by_id.values())
    expected = {
        "discovered": sum(m["lifecycle"]["discovered"] for m in ms),
        "listed": sum(m["catalogue"]["lifecycle"] == "LISTED" for m in ms),
        "retired_or_source_not_current": sum(m["catalogue"]["lifecycle"] != "LISTED" for m in ms),
        "authorized": sum(m["lifecycle"]["authorized"] is True for m in ms),
        "not_authorized": sum(m["lifecycle"]["authorized"] is False for m in ms),
        "identity_unknown": sum(m["lifecycle"]["authorized"] is None for m in ms),
        **{d.lower(): sum(m["admissibility"]["decision"] == d for m in ms) for d in pc.DECISIONS},
        "scored": sum(m["score"] is not None for m in ms),
        "manually_excluded": sum(m["manual"]["excluded"] for m in ms),
        "candidates": len(doc["candidates"]),
        "orphan_observations": len(doc["orphan_observations"]),
    }
    for k, v in expected.items():
        if counts[k] != v:
            _refuse("COUNTS_MISMATCH", f"$.counts.{k}")
    # Evaluated markets cannot exceed authorized ones (engine: only authorized markets are evaluated).
    if counts["evaluated"] > counts["authorized"]:
        _refuse("COUNTS_MISMATCH", "$.counts.evaluated")


def _budgets(doc: dict) -> None:
    b = _obj(doc["budgets"], BUDGET_KEYS, "$.budgets")
    _str(b["profile"], "$.budgets.profile")
    lim = _obj(b["limits"], set(pc.BUDGET_LIMIT_KEYS) | {"future_cycle_interval_s", "profile"}, "$.budgets.limits")
    for k in pc.BUDGET_LIMIT_KEYS:
        _int(lim[k], f"$.budgets.limits.{k}", lo=1)
    _int(lim["future_cycle_interval_s"], "$.budgets.limits.future_cycle_interval_s", nullable=True, lo=1)
    if lim["profile"] != b["profile"]:
        _refuse("BUDGET_PROFILE_MISMATCH", "$.budgets.limits.profile")
    if not _same(b["production"], {"status": pc.PRODUCTION_BUDGETS_STATUS, "values": None}):
        _refuse("PRODUCTION_BUDGETS_INVARIANT", "$.budgets.production")
    u = _obj(b["usage"], USAGE_KEYS, "$.budgets.usage")
    for k in USAGE_KEYS:
        _int(u[k], f"$.budgets.usage.{k}")
    if u["instruments_listed"] != len(doc["markets"]) or \
            u["instruments_evaluated"] != doc["counts"]["evaluated"] or \
            u["input_bytes"] != doc["dataset"]["bytes"]:
        _refuse("BUDGET_USAGE_MISMATCH", "$.budgets.usage")


def _context(doc: dict) -> None:
    _int(doc["evaluation_time_ms"], "$.evaluation_time_ms", lo=1)
    _sha(doc["preferences_sha256"], "$.preferences_sha256")
    p = _obj(doc["policy"], POLICY_KEYS, "$.policy")
    for k in POLICY_KEYS:
        _str_list(p[k], f"$.policy.{k}")
    markets = []
    for i, s in enumerate(_list(doc["sources"], "$.sources", len(pc.SCANNER_MARKETS))):
        sp = f"$.sources[{i}]"
        _obj(s, SOURCE_KEYS, sp)
        markets.append(_one_of(s["market"], pc.SCANNER_MARKETS, sp + ".market"))
        _one_of(s["catalogue_state"], CATALOGUE_STATES, sp + ".catalogue_state")
        _code(s["catalogue_reason"], sp + ".catalogue_reason")
        _int(s["collected_ms"], sp + ".collected_ms", nullable=True)
        _bool(s["metadata_current"], sp + ".metadata_current")
        _code(s["metadata_reason"], sp + ".metadata_reason")
        _sha_map(s["raw_sha256"], sp + ".raw_sha256")
        _int(s["instruments"], sp + ".instruments", hi=pc.MAX_LIST)
        _one_of(s["access"], pc.SOURCE_ACCESS, sp + ".access")
        _code(s["access_reason"], sp + ".access_reason")
    if markets != sorted(set(markets)):
        _refuse("SOURCES_NOT_ORDERED_OR_DUPLICATED", "$.sources")
    for i, o in enumerate(_list(doc["orphan_observations"], "$.orphan_observations")):
        op = f"$.orphan_observations[{i}]"
        _obj(o, ORPHAN_KEYS, op)
        _one_of(o["venue"], pc.VENUES, op + ".venue")
        _one_of(o["market_type"], pc.MARKET_TYPES, op + ".market_type")
        _str(o["native_symbol"], op + ".native_symbol")
        _str_list(o["evidence_refs"], op + ".evidence_refs")
        _code(o["reason"], op + ".reason", nullable=False)
    _list(doc["deep_observation_jobs"], "$.deep_observation_jobs")


def verify_export(raw: bytes) -> dict:
    """Verify one frozen export. Returns {"doc", "export_sha256", "export_bytes"}; refuses otherwise."""
    doc = _parse(raw)
    _versions(doc)
    _canonical_and_seal(raw, doc)
    if set(doc) != TOP_KEYS:
        _refuse("KEYS_MISMATCH", "$")
    try:
        _structure(doc)
    except ProjectionRefusal:
        raise
    except (TypeError, KeyError, AttributeError, ValueError, ArithmeticError, RecursionError) as exc:
        # Safety net: a shape no explicit check anticipated is still a typed refusal.
        _refuse("STRUCTURE_INVALID", type(exc).__name__)
    return {"doc": doc, "export_sha256": sha256_hex(bytes(raw)), "export_bytes": len(raw)}


def _structure(doc: dict) -> None:
    _dataset(doc)
    evidence = _evidence(doc)
    _authority(doc)
    _context(doc)
    mission = _mission(doc)
    by_id = _markets(doc, mission, evidence)
    _candidates(doc, by_id)
    _manual(doc, by_id)
    _counts(doc, by_id)
    _budgets(doc)
