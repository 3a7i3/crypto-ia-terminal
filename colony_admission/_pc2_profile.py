"""Private pilot-p1-pc2-present-native-v0 comparisons (PC2 amendment C8.3).

Pure validators over bytes and digests an acquisition owner already holds. No
reader calls them yet: until C8.4, PC2/p1 stays SCIENTIFIC_PROFILE_UNSUPPORTED/NE
in every public projection. A PASS here is a comparison of declared, pinned
claims; it is not a qualification, a review, a signature or a fresh campaign.
"""

import hashlib
from dataclasses import dataclass

from colony_lab import a1_identity as a1
from colony_lab import lineage
from colony_lab.a1_identity import IdentityError

from . import _attestation_statement as s
from . import formats as f
from ._attestation_core import CoreError, decode, need

PROFILE = "pilot-p1-pc2-present-native-v0"
R8_PROFILE = "sentinel-r8-c9"
P1C_PATH = "docs/colony_lab/PILOT_CRITERIA_P1.json"
PC2_PATH = "docs/colony_lab/evidence/PC2_pilot_evidence.json"
P1C_PIN = "dcc3fe71909117ee2501ff3c5d2f8866f5343123929af40e06484a8ebf713ef7"
PC2_PIN = "d706928e843275d58cab330426f6745db864194a86ef389fbed1dd93a7bc6b4d"
# C2.1: the five raw pins, exactly; R8C/C9/R8Q are the R8 profile's own files.
PINS = {P1C_PATH: P1C_PIN, PC2_PATH: PC2_PIN, s.CRITERIA_PATH: s.CRITERIA_PIN,
        s.EVIDENCE_PATH: s.EVIDENCE_PIN, s.HISTORY_PATH: s.HISTORY_PIN}
SUBJECT_PIN = s.SUBJECT_PIN
EVALUATOR_PIN = s.EVALUATOR_PIN
PILOT_PIN = "97fb6b0489976f8b003823c1536932ec10a1c7faa699ef6f6eb1bd4056238bc7"
PILOT_ROOTS = ("colony_pilot",)  # C3.1: recursive, E is not subtracted
QUALIFICATION_FIELDS = frozenset({"qualification_schema", "agent_id", "agent_spec_id", "state", "scope",
    "criteria_sha256", "evidence_sha256", "subject_code_sha256", "evaluator_code_sha256",
    "reviewer_kind", "reviewer_id"})
# C5.3: the acquired lineage context, compared by canonical bytes.
SENTINEL = {"agent_id": "4279e165b2706c088840d1cdc4ebe3efa76c2ea220bc948a8336c4343eb23173",
            "agent_spec_id": "b74ab69619acdb3747edd64affbc6d5ae3c99f32249c49bf4288e5786836d4ed",
            "spec_artifact_hash": "fd130c1bcd6c10a13b9cab3cbcd4d8e78b5b21a388251523b298dbc14927b5a6"}
PILOT = {"agent_id": "1eb3baaf0bf1ec4ddc6559e128b8685e4a1d91da49f417ff33cc0fa196c0a22a",
         "agent_spec_id": "660ec9a818fc3c3c41b432520dbcc881cc8c840cdb1a5a80318488ee0e22d986",
         "spec_artifact_hash": "3eb0786822165e7f7fd60b1f8bb8d84bef4c803e90ac52bcbff08e093cbb4dcc"}
SENTINEL_PERMISSIONS = ["DIAGNOSTIC_PRODUCE", "GOVERNED_ARTIFACT_READ"]
PILOT_PERMISSIONS = ["DIAGNOSTIC_PRODUCE"]
DECLARED_DIFF = ["purpose"]
BUDGET = {"cpu_seconds": 30, "wall_seconds": 60, "memory_bytes": 1073741824, "output_bytes": 1048576,
          "runs": 10, "journal_events": 100}
ROUNDS = 2


@dataclass(frozen=True)
class Context:
    """Records/specs of the subject pilot and its Sentinel parent, from the snapshot owner."""
    sentinel_record: bytes | None
    sentinel_spec: bytes | None
    pilot_record: bytes | None
    pilot_spec: bytes | None


def select(qualification_bytes, statement_bytes):
    """C10.2 steps 2-5 after the general statement grammar: only q.criteria and s.scope."""
    try:
        q, st = decode(qualification_bytes), decode(statement_bytes, 16384)
        criteria, scope = q.get("criteria_sha256"), st.get("scope")
    except CoreError:
        return None
    if criteria == s.CRITERIA_PIN:
        return R8_PROFILE
    if criteria == P1C_PIN and scope == s.PRESENT:
        return PROFILE
    return None


def _same(value, expected):
    return f.canonical(value) == f.canonical(expected)


def _context(context):
    need(type(context) is Context and all(
        raw is not None for raw in (context.sentinel_record, context.sentinel_spec,
                                    context.pilot_record, context.pilot_spec)), "SCIENTIFIC_SOURCE_UNAVAILABLE")
    parent, parent_spec = decode(context.sentinel_record), decode(context.sentinel_spec)
    pilot, pilot_spec = decode(context.pilot_record), decode(context.pilot_spec)
    try:
        lineage.verify_record(parent, parent_spec)
        lineage.verify_record(pilot, pilot_spec, parent, parent_spec)
        artifacts = a1.spec_artifact_hash(parent_spec), a1.spec_artifact_hash(pilot_spec)
        diff = lineage.spec_diff(parent_spec, pilot_spec)
    except (lineage.LineageError, IdentityError):
        raise CoreError("SCIENTIFIC_DIVERGENCE") from None
    common = {"budget": BUDGET, "memory": lineage.MEMORY, "credentials": "NONE",
              "registry": lineage.REGISTRY, "operational_authority": "DENIED"}
    lineage_id = lineage.lineage_id(SENTINEL["agent_id"])
    expected_parent = {**SENTINEL, **common, "role": "FOUNDER", "lab_permissions": SENTINEL_PERMISSIONS,
        "lineage": {"lineage_id": lineage_id, "founder_agent_id": SENTINEL["agent_id"],
                    "parent_agent_id": None, "parent_agent_spec_id": None, "generation": 0},
        "genotype": {"base_agent_spec_id": None, "declared_diff": []}}
    expected_pilot = {**PILOT, **common, "role": "DESCENDANT", "lab_permissions": PILOT_PERMISSIONS,
        "lineage": {"lineage_id": lineage_id, "founder_agent_id": SENTINEL["agent_id"],
                    "parent_agent_id": SENTINEL["agent_id"], "parent_agent_spec_id": SENTINEL["agent_spec_id"],
                    "generation": 1},
        "genotype": {"base_agent_spec_id": SENTINEL["agent_spec_id"], "declared_diff": DECLARED_DIFF}}
    need(all(_same(parent[k], v) for k, v in expected_parent.items())
         and all(_same(pilot[k], v) for k, v in expected_pilot.items())
         and artifacts == (SENTINEL["spec_artifact_hash"], PILOT["spec_artifact_hash"])
         and _same(diff, DECLARED_DIFF), "SCIENTIFIC_DIVERGENCE")
    return parent, pilot, pilot_spec


def _rounds(pc2, p1c, r8c):
    ids = ([t["id"] for t in p1c["birth_trials"]] + [t["id"] for t in r8c["trials"]]
           + [t["id"] for t in p1c["permission_trials"]])
    rounds = pc2["rounds"]
    need(type(rounds) is list and len(rounds) == ROUNDS and len(ids) == 28 == len(set(ids))
         and all(_same(r, rounds[0]) for r in rounds), "SCIENTIFIC_DIVERGENCE")
    for entry in rounds[0]:
        need(type(entry) is dict and entry["passed"] is True and _same(entry["failed_predicates"], [])
             and f.hex64(entry["facts_sha256"]), "SCIENTIFIC_DIVERGENCE")
    need(_same([e["id"] for e in rounds[0]], ids), "SCIENTIFIC_DIVERGENCE")


def _statement(st):
    # C4.7/C13.3: only PC2 raw is the native historical record; no campaign or past signature.
    need(st["historical_record_path"] == PC2_PATH and st["historical_record_sha256"] == PINS[PC2_PATH]
         and st["campaign_replayed"] is False and st["campaign_evidence_sha256"] is None
         and st["historical_signature_claimed"] is False, "STATEMENT_INVALID")


def _qualification(q, st):
    # C4.1/C4.7/C10.1: q keeps the eleven fields and names the pilot, p1 and PC2 raw.
    need(set(q) == QUALIFICATION_FIELDS and q["qualification_schema"] == lineage.QUALIFICATION_SCHEMA
         and q["agent_id"] == st["subject_agent_id"] == PILOT["agent_id"]
         and q["agent_spec_id"] == st["subject_agent_spec_id"] == PILOT["agent_spec_id"]
         and q["state"] == "QUALIFIED_SIMULATED" and q["scope"] == "SIMULATED_DETERMINISTIC"
         and q["criteria_sha256"] == st["criteria_sha256"] == P1C_PIN
         and q["evidence_sha256"] == PINS[PC2_PATH]
         and _same(st["evidence"], [{"path": PC2_PATH, "sha256": PINS[PC2_PATH]}]), "SCIENTIFIC_DIVERGENCE")


def _artifacts(artifacts):
    """C2: every present artifact is checked against its raw pin before any is decoded."""
    need(type(artifacts) is dict and set(artifacts) <= set(PINS), "SCIENTIFIC_DIVERGENCE")
    for path, pin in PINS.items():
        raw = artifacts.get(path)
        if raw is not None:
            need(type(raw) is bytes and len(raw) <= 16 * 1024 * 1024, "SOURCE_LIMIT")
            need(hashlib.sha256(raw).hexdigest() == pin, "SCIENTIFIC_DIVERGENCE")
    need(all(artifacts.get(path) is not None for path in PINS), "SCIENTIFIC_SOURCE_UNAVAILABLE")
    return {path: decode(artifacts[path]) for path in PINS}


def _native(docs, artifacts, q):
    p1c, pc2 = docs[P1C_PATH], docs[PC2_PATH]
    c9, r8q = docs[s.EVIDENCE_PATH], docs[s.HISTORY_PATH]
    # C6.1: p1 criteria and the R8 parent files they name.
    need(p1c["criteria_schema"] == "colony-lab.pilot-criteria/0" and p1c["revision"] == "p1"
         and p1c["scope"] == "SIMULATED_DETERMINISTIC" and p1c["parent"]["criteria_revision"] == "r8"
         and "docs/colony_lab/" + p1c["parent"]["record_file"] == s.HISTORY_PATH
         and "docs/colony_lab/" + p1c["parent"]["evidence_file"] == s.EVIDENCE_PATH, "SCIENTIFIC_DIVERGENCE")
    # C6.2: native PC2 claims, literal booleans only.
    need(pc2["evidence_schema"] == "colony-lab.pilot-evidence/0" and pc2["criteria_revision"] == "p1"
         and pc2["criteria_status"] == "CURRENT" and pc2["criteria_sha256"] == P1C_PIN
         and pc2["scope"] == q["scope"] and pc2["proposed_state"] == "PROPOSED_QUALIFIED_SIMULATED"
         and _same(pc2["failure_reasons"], []) and _same(pc2["code_irregular"], [])
         and pc2["deterministic_across_fresh_labs"] is True
         and pc2["evaluator_runtime"]["source_only"] is True
         and pc2["sandbox_view"]["matches_subject"] is True
         and pc2["environment"]["sandbox"] == "VERIFIED", "SCIENTIFIC_DIVERGENCE")
    # C6.3: PC2.parent is Sentinel and copies R8Q raw and decoded, historical reviewer included.
    native_parent = pc2["parent"]
    need(native_parent["agent_id"] == SENTINEL["agent_id"]
         and native_parent["agent_spec_id"] == SENTINEL["agent_spec_id"]
         and native_parent["matches_current_code"] is True and _same(native_parent["mismatched"], [])
         and native_parent["record_sha256"] == PINS[s.HISTORY_PATH]
         == hashlib.sha256(artifacts[s.HISTORY_PATH]).hexdigest()
         and _same(native_parent["qualification"], r8q), "SCIENTIFIC_DIVERGENCE")
    # C6.4: the historical R8 dependency, never the PRESENT R8 copy rule.
    need(r8q["agent_id"] == c9["subject"]["agent_id"] == SENTINEL["agent_id"]
         and r8q["agent_spec_id"] == c9["subject"]["agent_spec_id"] == SENTINEL["agent_spec_id"]
         and r8q["criteria_sha256"] == PINS[s.CRITERIA_PATH]
         and r8q["evidence_sha256"] == PINS[s.EVIDENCE_PATH]
         == hashlib.sha256(artifacts[s.EVIDENCE_PATH]).hexdigest()
         and r8q["state"] == "QUALIFIED_SIMULATED" and r8q["scope"] == "SIMULATED_DETERMINISTIC"
         and c9["criteria_revision"] == "r8" and c9["criteria_status"] == "CURRENT"
         and c9["criteria_sha256"] == PINS[s.CRITERIA_PATH]
         and c9["proposed_state"] == "PROPOSED_QUALIFIED_SIMULATED"
         and _same(c9["failure_reasons"], []) and _same(c9["code_irregular"], [])
         and c9["deterministic_across_fresh_labs"] is True and c9["golden_subject_code_matches"] is True
         and c9["evaluator_runtime"]["source_only"] is True, "SCIENTIFIC_DIVERGENCE")
    # C6.5 (claims side): native pilot, p1 pilot description and not_claimed.
    expected_native = {**PILOT, "generation": 1, "lab_permissions": PILOT_PERMISSIONS,
                       "declared_diff": DECLARED_DIFF}
    native, described = pc2["pilot"], p1c["pilot"]
    need(type(native) is dict and set(native) == set(expected_native)
         and all(_same(native[k], v) for k, v in expected_native.items())
         and _same(described["lab_permissions"], PILOT_PERMISSIONS)
         and _same(described["declared_diff"], DECLARED_DIFF)
         and _same(described["parent_lab_permissions"], SENTINEL_PERMISSIONS)
         and _same(pc2["not_claimed"], p1c["not_claimed"]), "SCIENTIFIC_DIVERGENCE")
    _rounds(pc2, p1c, docs[s.CRITERIA_PATH])  # C6.6


def _closures(q, st, docs, digests):
    """C3.2-C3.4: S, P and E each bound to its pin, every claim and its recomputed closure."""
    subject, evaluator, pilot = digests
    s_values = [q["subject_code_sha256"], st["subject_code_sha256"]]
    p_values = [q["evaluator_code_sha256"], st["evaluator_code_sha256"]]
    e_values = []
    if docs is not None:
        pc2, c9, r8q = docs[PC2_PATH], docs[s.EVIDENCE_PATH], docs[s.HISTORY_PATH]
        s_values += [pc2["subject_code_sha256"], c9["subject"]["subject_code_sha256"], r8q["subject_code_sha256"]]
        p_values += [pc2["pilot_code_sha256"]]
        e_values += [pc2["sentinel_evaluator_code_sha256"], c9["evaluator_code_sha256"],
                     r8q["evaluator_code_sha256"]]
    s_values += [] if subject is None else [subject]
    p_values += [] if pilot is None else [pilot]
    e_values += [] if evaluator is None else [evaluator]
    for pin, values in ((SUBJECT_PIN, s_values), (PILOT_PIN, p_values), (EVALUATOR_PIN, e_values)):
        need(all(type(v) is str and v == pin for v in values), "SCIENTIFIC_DIVERGENCE")
    need(docs is not None and None not in digests, "SCIENTIFIC_SOURCE_UNAVAILABLE")


def _pilot_names(docs, context):
    # C6.5 (context side): p1 nominal identity and purpose are those of the acquired pilot spec.
    _, _, pilot_spec = _context(context)
    if docs is not None:
        described = docs[P1C_PATH]["pilot"]
        need(all(described[k] == pilot_spec[k] for k in ("canonical_name", "display_name", "purpose")),
             "SCIENTIFIC_DIVERGENCE")


def bindings(statement_bytes, qualification_bytes, artifacts, subject_digest, evaluator_digest, pilot_digest,
             context):
    """Every C2-C6 comparison of the PC2 profile; no acquisition, signature or SR claim.

`artifacts` is the detached five-path mapping of C2.2 and the three digests come
from complete inventories (C3.1, C7.1); neither is acquired here. Missing inputs
give NE only when no comparison that could run is a proven FAIL (C13.1).
"""
    try:
        q, st = decode(qualification_bytes), decode(statement_bytes, 16384)
        if q.get("criteria_sha256") != P1C_PIN or st.get("scope") == s.FRESH:
            return s.StatementFact(codes=("SCIENTIFIC_PROFILE_UNSUPPORTED",))
        need(st.get("scope") == s.PRESENT, "STATEMENT_INVALID")
    except CoreError as exc:
        return s.StatementFact("FAIL", (str(exc),))
    fails, missing, docs = [], [], None

    def run(check, *args):
        try:
            return check(*args)
        except CoreError as exc:
            (missing if str(exc) == "SCIENTIFIC_SOURCE_UNAVAILABLE" else fails).append(str(exc))
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, UnicodeError, RecursionError):
            fails.append("SCIENTIFIC_DIVERGENCE")
        return None

    run(_statement, st)
    run(_qualification, q, st)
    docs = run(_artifacts, artifacts)
    if docs is not None:
        run(_native, docs, artifacts, q)
    run(_closures, q, st, docs, (subject_digest, evaluator_digest, pilot_digest))
    run(_pilot_names, docs, context)
    if fails:
        return s.StatementFact("FAIL", tuple(dict.fromkeys(fails)))
    if missing:
        return s.StatementFact(codes=("SCIENTIFIC_SOURCE_UNAVAILABLE",))
    return s.StatementFact("PASS")
