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

from observability.radar_selection.fixture import RadarRefusal, canonical, sha256_hex, strict_loads

from . import contract as pc

_SHA = re.compile(r"[0-9a-f]{64}", re.ASCII)
_CODE = re.compile(r"[A-Z][A-Z0-9_:]{0,95}", re.ASCII)
_SCORE = re.compile(r"(100|[0-9]{1,2})\.[0-9]{2}", re.ASCII)
_VERSION = re.compile(r"radar-evaluation/([0-9]+)\.([0-9]+)\.([0-9]+)", re.ASCII)
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
COUNT_KEYS = {"discovered", "listed", "retired_or_source_not_current", "authorized", "not_authorized",
              "identity_unknown", "evaluated", "admissible", "a_qualifier", "non_admissible", "unknown",
              "scored", "manually_excluded", "candidates", "orphan_observations"}
BUDGET_KEYS = {"profile", "limits", "production", "usage"}
USAGE_KEYS = {"input_bytes", "instruments_listed", "instruments_evaluated", "observations"}


class ProjectionRefusal(RadarRefusal):
    """Stable refusal code of the S4-a verifier (message = ``CODE`` or ``CODE:path``)."""


def _refuse(code: str, path: str = "") -> None:
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
        # FLOAT_NOT_ALLOWED, NONFINITE_NUMBER), re-raised under the verifier's type.
        raise ProjectionRefusal(str(exc)) from None
    except ValueError:
        # e.g. an integer literal beyond the interpreter's digit limit.
        _refuse("INPUT_MALFORMED", "ValueError")
    if not isinstance(doc, dict):
        _refuse("OBJECT_EXPECTED", "$")
    return doc


def _versions(doc: dict) -> None:
    schema = doc.get("schema_version")
    if not isinstance(schema, str):
        _refuse("EVALUATION_SCHEMA_MISSING")
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
    except UnicodeEncodeError:
        _refuse("INPUT_MALFORMED", "UnicodeEncodeError")
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
    for i, s in enumerate(_list(inputs["sources"], "$.inputs.sources", 64)):
        p = f"$.inputs.sources[{i}]"
        if not isinstance(s, dict):
            _refuse("OBJECT_EXPECTED", p)
        _str(s.get("source_id"), p + ".source_id")
        _one_of(s.get("state"), REF_STATES, p + ".state")
        _code(s.get("reason"), p + ".reason")
    for i, r in enumerate(_list(inputs["refused_observations"], "$.inputs.refused_observations")):
        p = f"$.inputs.refused_observations[{i}]"
        if not isinstance(r, dict):
            _refuse("OBJECT_EXPECTED", p)
        _code(r.get("reason"), p + ".reason", nullable=False)


def _mission(doc: dict) -> str:
    m = _obj(doc["mission"], {"id", "needs_bbo", "needs_l2_verified", "label"}, "$.mission")
    _one_of(m["id"], pc.MISSIONS, "$.mission.id")
    if not _same([m["needs_bbo"], m["needs_l2_verified"]], list(pc.MISSIONS[m["id"]])):
        _refuse("MISSION_RULES_MISMATCH", "$.mission")
    _str(m["label"], "$.mission.label")
    return m["id"]


def _criteria(crit, path) -> None:
    _obj(crit, set(pc.CRITERIA), path)
    for name in pc.CRITERIA:
        c = crit[name]
        if not isinstance(c, dict) or "state" not in c or "reason" not in c:
            _refuse("CRITERION_SHAPE", f"{path}.{name}")
        _one_of(c["state"], pc.CRITERION_STATES, f"{path}.{name}.state")
        if c["reason"] is not None:
            _str(c["reason"], f"{path}.{name}.reason")
        # A missing criterion always says why: UNKNOWN is never silent and never 0.
        if c["state"] in ("UNKNOWN", "INVALID") and c["reason"] is None:
            _refuse("UNKNOWN_WITHOUT_REASON", f"{path}.{name}")


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
        if not isinstance(s[k], str) or not _SCORE.fullmatch(s[k]):
            _refuse("SCORE_DECIMAL_EXPECTED", f"{path}.score.{k}")
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


def _market(m, i, mission, evidence) -> str:
    path = f"$.markets[{i}]"
    _obj(m, MARKET_KEYS, path)
    _str(m["market_id"], path + ".market_id")
    _one_of(m["venue"], pc.VENUES, path + ".venue")
    _one_of(m["market_type"], pc.MARKET_TYPES, path + ".market_type")
    for k in ("contract_type", "native_symbol"):
        _str(m[k], f"{path}.{k}")
    for k in ("base", "quote", "settlement_asset"):
        _str(m[k], f"{path}.{k}", nullable=True)
    cat = _obj(m["catalogue"], CATALOGUE_KEYS, path + ".catalogue")
    _one_of(cat["lifecycle"], pc.CATALOGUE_LIFECYCLES, path + ".catalogue.lifecycle")
    _sha_map(cat["raw_sha256"], path + ".catalogue.raw_sha256")
    _int(cat["collected_ms"], path + ".catalogue.collected_ms", nullable=True)
    _one_of(m["change"], pc.CHANGES, path + ".change")
    if m["previous"] is not None and not isinstance(m["previous"], dict):
        _refuse("OBJECT_EXPECTED", path + ".previous")
    lc = _obj(m["lifecycle"], LIFECYCLE_KEYS, path + ".lifecycle")
    _bool(lc["discovered"], path + ".lifecycle.discovered")
    _bool(lc["authorized"], path + ".lifecycle.authorized", nullable=True)
    _one_of(lc["source_access"], pc.SOURCE_ACCESS, path + ".lifecycle.source_access")
    _one_of(lc["recent_data"], pc.RECENT_DATA, path + ".lifecycle.recent_data")
    _one_of(lc["scientific"], pc.DECISIONS, path + ".lifecycle.scientific")
    ob = _obj(m["observation"], OBSERVATION_KEYS, path + ".observation")
    _bool(ob["present"], path + ".observation.present")
    if ob["evidence_kind"] != evidence:
        _refuse("EVIDENCE_MIXED", path + ".observation.evidence_kind")
    if not ob["present"] and ob["reason"] is None:
        _refuse("UNKNOWN_WITHOUT_REASON", path + ".observation")
    if not ob["present"] and lc["recent_data"] in ("FRESH", "STALE"):
        _refuse("FRESHNESS_WITHOUT_OBSERVATION", path + ".lifecycle.recent_data")
    _int(ob["sample_count"], path + ".observation.sample_count", nullable=True)
    _list(ob["contradictions"], path + ".observation.contradictions")
    if ob["window"] is not None:
        w = _obj(ob["window"], {"start_ms", "end_ms", "step_ms", "points"}, path + ".observation.window")
        for k in ("start_ms", "end_ms", "step_ms", "points"):
            _int(w[k], f"{path}.observation.window.{k}", nullable=True)
    _criteria(m["criteria"], path + ".criteria")
    man = _obj(m["manual"], set(MANUAL_FLAGS), path + ".manual")
    for k in MANUAL_FLAGS:
        _bool(man[k], f"{path}.manual.{k}")
    decision = _admissibility(m, mission, path)
    _score(m, decision, path)
    return decision


def _markets(doc: dict, mission: str, evidence: str) -> dict:
    markets = _list(doc["markets"], "$.markets", pc.MAX_MARKETS)
    by_id = {}
    previous = None
    for i, m in enumerate(markets):
        _market(m, i, mission, evidence)
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
        if not isinstance(cd["cost"], dict):
            _refuse("OBJECT_EXPECTED", p + ".cost")
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
    if not isinstance(b["limits"], dict):
        _refuse("OBJECT_EXPECTED", "$.budgets.limits")
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
    for i, s in enumerate(_list(doc["sources"], "$.sources", 16)):
        sp = f"$.sources[{i}]"
        _obj(s, SOURCE_KEYS, sp)
        _sha_map(s["raw_sha256"], sp + ".raw_sha256")
        _int(s["instruments"], sp + ".instruments", nullable=True)
    for i, o in enumerate(_list(doc["orphan_observations"], "$.orphan_observations")):
        op = f"$.orphan_observations[{i}]"
        _obj(o, ORPHAN_KEYS, op)
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
    except (TypeError, KeyError, AttributeError, ValueError) as exc:
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
