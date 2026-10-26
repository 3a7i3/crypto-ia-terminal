"""Private strict statement/scientific comparisons on already acquired bytes.

The acquisition layer must prove inventories, bounds, origin and stability.
Hashing a caller-supplied subset here never certifies a code closure.
"""

import hashlib
import re
from dataclasses import dataclass, field

from colony_trust import trust

from . import formats as f
from ._attestation_core import CoreError, decode, need
from .physical_evidence import NE, STATEMENT_FIELDS

PRESENT = "PRESENT_ATTESTATION_OF_EXISTING_EVIDENCE"
FRESH = "FRESH_CAMPAIGN"
CRITERIA_PATH = "docs/colony_lab/SENTINEL_QUALIFICATION_CRITERIA_R8.json"
EVIDENCE_PATH = "docs/colony_lab/evidence/C9_sentinel_evidence.json"
HISTORY_PATH = "docs/colony_lab/SENTINEL_QUALIFICATION_RECORD_R8.json"
CRITERIA_PIN = "22528f1629db5d565f54137e11e99f670c68152eb3127cbafabe5f1072ca990a"
EVIDENCE_PIN = "bc2f37df6bf7ab8138d326862906431154c07b298fb4b482db4fc6a0910f71cf"
HISTORY_PIN = "d38656c56f59c7d950d3031ec969cfe6e6e126ed27f3ab2c83ab3d022518c578"
SUBJECT_PIN = "2c926421416731dc629915067bcea472729e6785ec8dcb6e28f15ae7b41e4ec8"
EVALUATOR_PIN = "41b78971184809652dd1190dded49ab27d58c35c8a995351a47bf0f85756faa4"


@dataclass(frozen=True)
class StatementFact:
    status: str = NE
    codes: tuple[str, ...] = ()
    accepted: bool = field(default=False, init=False)
    source_revision_provenance: str = field(default=NE, init=False)


def safe_path(path):
    if type(path) is not str or not path or path.startswith("/") or "\\" in path:
        return False
    for name in path.split("/"):
        lower = name.lower()
        if name in ("", ".", "..") or "\x00" in name or lower.startswith(".env") or any(
                token in lower for token in ("secret", "credential", "private_key")) or lower in (
                "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519") or lower.endswith((".pem", ".key", ".p12", ".pfx")):
            return False
    return True


def code_digest(files):
    """Exact encoding only; acquisition, not this helper, proves a complete closure."""
    need(type(files) is tuple and len(files) <= 4096, "SOURCE_LIMIT")
    names = tuple(path for path, _ in files)
    need(all(safe_path(path) for path in names), "SOURCE_PATH_FORBIDDEN")
    need(names == tuple(sorted(set(names))), "SOURCE_CODE_IRREGULAR")
    need(bool(files), "SCIENTIFIC_SOURCE_UNAVAILABLE")
    digest = hashlib.sha256()
    count = 0
    for path, raw in files:
        need(type(raw) is bytes and len(raw) <= 16 * 1024 * 1024, "SOURCE_LIMIT")
        count += len(raw)
        need(count <= 32 * 1024 * 1024, "SOURCE_LIMIT")
        digest.update(path.encode("utf-8") + b"\x00" + hashlib.sha256(raw).digest())
    return digest.hexdigest()


def statement(raw, qualification_bytes, qualification_envelope_bytes, statement_envelope_bytes):
    """Closed grammar and signed-author/subject bindings, not scientific validation."""
    if any(x is None for x in (raw, qualification_bytes, qualification_envelope_bytes, statement_envelope_bytes)):
        return StatementFact(codes=("EVIDENCE_NOT_STORED",))
    try:
        s, q = decode(raw, 16384), decode(qualification_bytes)
        qe, se = decode(qualification_envelope_bytes, 16384), decode(statement_envelope_bytes, 16384)
        need(set(s) == STATEMENT_FIELDS and s["statement_schema"] == "colony-admission.attestation-statement/0",
             "STATEMENT_INVALID")
        need(type(s["scope"]) is str and s["scope"] in (PRESENT, FRESH), "STATEMENT_INVALID")
        need(type(s["issuer_root_version"]) is int and 1 <= s["issuer_root_version"] <= trust.MAX_VERSION,
             "STATEMENT_INVALID")
        need(type(s["verified_at_source_sha"]) is str and bool(re.fullmatch("[0-9a-f]{40}", s["verified_at_source_sha"])),
             "STATEMENT_INVALID")
        need(s["historical_signature_claimed"] is False, "STATEMENT_INVALID")
        expected = {"subject_agent_id": q["agent_id"], "subject_agent_spec_id": q["agent_spec_id"],
            "qualification_record_sha256": f.digest(q), "issuer_kind": q["reviewer_kind"], "issuer_id": q["reviewer_id"],
            "criteria_sha256": q["criteria_sha256"], "subject_code_sha256": q["subject_code_sha256"],
            "evaluator_code_sha256": q["evaluator_code_sha256"]}
        need(all(f.canonical(s[k]) == f.canonical(v) for k, v in expected.items()), "STATEMENT_INVALID")
        need(all(f.hex64(s[k]) for k in ("subject_agent_id", "subject_agent_spec_id", "qualification_record_sha256",
             "criteria_sha256", "subject_code_sha256", "evaluator_code_sha256")), "STATEMENT_INVALID")
        need(s["issuer_id"] != "colony-review-481-r8", "STATEMENT_INVALID")
        for envelope, record, kind in ((qe, q, "colony-lab.qualification/0"),
                                       (se, s, "colony-admission.attestation-statement/0")):
            need(trust._envelope_shape(envelope) is None and envelope["record_kind"] == kind
                 and envelope["record_sha256"] == f.digest(record)
                 and envelope["issuer_id"] == s["issuer_id"]
                 and envelope["root_version"] == s["issuer_root_version"]
                 and envelope["subject"] == {"agent_id": q["agent_id"], "agent_spec_id": q["agent_spec_id"]},
                 "STATEMENT_INVALID")
        evidence = s["evidence"]
        need(type(evidence) is list and 0 < len(evidence) <= 252, "STATEMENT_INVALID")
        need(all(type(e) is dict and set(e) == {"path", "sha256"} and safe_path(e["path"])
                 and f.hex64(e["sha256"]) for e in evidence), "STATEMENT_INVALID")
        paths = [e["path"] for e in evidence]
        need(paths == sorted(set(paths)), "STATEMENT_INVALID")
        if s["scope"] == PRESENT:
            need(safe_path(s["historical_record_path"]) and f.hex64(s["historical_record_sha256"])
                 and s["campaign_replayed"] is False and s["campaign_evidence_sha256"] is None, "STATEMENT_INVALID")
        else:
            need(s["historical_record_path"] is None and s["historical_record_sha256"] is None
                 and s["campaign_replayed"] is True and f.hex64(s["campaign_evidence_sha256"])
                 and s["campaign_evidence_sha256"] == q["evidence_sha256"], "STATEMENT_INVALID")
        return StatementFact("PASS")
    except (CoreError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return StatementFact("FAIL", ("STATEMENT_INVALID",))


def scientific_bindings(statement_bytes, qualification_bytes, artifacts, subject_digest, evaluator_digest):
    """R8/C9 bindings only; no claim of code inventory, campaign freshness or provenance.

`artifacts` is the detached fixed-profile mapping acquired by the owner. Digests
must come from its complete inventories; this function does not acquire them.
"""
    try:
        q, s = decode(qualification_bytes), decode(statement_bytes, 16384)
        if q.get("criteria_sha256") != CRITERIA_PIN:
            return StatementFact(codes=("SCIENTIFIC_PROFILE_UNSUPPORTED",))
        need(s.get("scope") in (PRESENT, FRESH), "STATEMENT_INVALID")
        expected = {CRITERIA_PATH: CRITERIA_PIN, EVIDENCE_PATH: EVIDENCE_PIN}
        if s["scope"] == PRESENT:
            expected[HISTORY_PATH] = HISTORY_PIN
        need(set(artifacts) == set(expected), "SCIENTIFIC_SOURCE_UNAVAILABLE")
        for path, pin in expected.items():
            raw = artifacts[path]
            need(raw is not None, "SCIENTIFIC_SOURCE_UNAVAILABLE")
            need(type(raw) is bytes and len(raw) <= 16 * 1024 * 1024, "SOURCE_LIMIT")
            need(hashlib.sha256(raw).hexdigest() == pin, "SCIENTIFIC_DIVERGENCE")
            decode(raw)
        need(s["evidence"] == [{"path": EVIDENCE_PATH, "sha256": EVIDENCE_PIN}]
             and q["evidence_sha256"] == EVIDENCE_PIN, "SCIENTIFIC_DIVERGENCE")
        need(subject_digest is not None and evaluator_digest is not None, "SCIENTIFIC_SOURCE_UNAVAILABLE")
        need(subject_digest == SUBJECT_PIN == q["subject_code_sha256"] == s["subject_code_sha256"]
             and evaluator_digest == EVALUATOR_PIN == q["evaluator_code_sha256"] == s["evaluator_code_sha256"]
             and q["criteria_sha256"] == s["criteria_sha256"], "SCIENTIFIC_DIVERGENCE")
        evidence = decode(artifacts[EVIDENCE_PATH])
        need(evidence["subject"]["agent_id"] == q["agent_id"]
             and evidence["subject"]["agent_spec_id"] == q["agent_spec_id"]
             and evidence["criteria_revision"] == "r8" and evidence["criteria_status"] == "CURRENT"
             and evidence["criteria_sha256"] == CRITERIA_PIN
             and evidence["scope"] == q["scope"] == "SIMULATED_DETERMINISTIC"
             and evidence["subject"]["subject_code_sha256"] == subject_digest
             and evidence["evaluator_code_sha256"] == evaluator_digest
             and evidence["proposed_state"] == "PROPOSED_QUALIFIED_SIMULATED"
             and q["state"] == "QUALIFIED_SIMULATED" and evidence["failure_reasons"] == []
             and evidence["code_irregular"] == [] and evidence["deterministic_across_fresh_labs"] is True
             and evidence["golden_subject_code_matches"] is True
             and evidence["evaluator_runtime"]["source_only"] is True, "SCIENTIFIC_DIVERGENCE")
        if s["scope"] == PRESENT:
            need(s["historical_record_path"] == HISTORY_PATH and s["historical_record_sha256"] == HISTORY_PIN,
                 "STATEMENT_INVALID")
            historical = decode(artifacts[HISTORY_PATH])
            need(set(historical) == set(q) and all(f.canonical(v) == f.canonical(q[k]) for k, v in historical.items()
                 if k not in ("reviewer_kind", "reviewer_id")), "SCIENTIFIC_DIVERGENCE")
        else:
            need(s["campaign_evidence_sha256"] == EVIDENCE_PIN, "STATEMENT_INVALID")
        return StatementFact("PASS")
    except CoreError as exc:
        code = str(exc)
        return StatementFact(NE if code == "SCIENTIFIC_SOURCE_UNAVAILABLE" else "FAIL", (code,))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return StatementFact("FAIL", ("SCIENTIFIC_DIVERGENCE",))
