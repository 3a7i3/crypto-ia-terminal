"""colony-trust/0: integrity, authenticity, authorization and completeness are judged apart."""

import ast
import copy
import json
from pathlib import Path

import pytest

from colony_trust import trust
from tests.colony_lab import builders
from tests.colony_trust.keys import (
    ADMITTER,
    LAB,
    OPERATOR,
    REVIEWER,
    eid,
    key_entry,
    lab_key,
    pin,
    root,
)

ROOT = Path(__file__).resolve().parents[2]
QUAL = "colony-lab.qualification/0"
IND = "colony-lab.individual/0"
ADM = "colony-registrar.admission/0"


def _individual():
    return builders.founder()[1]


def _qualification(record=None, reviewer=REVIEWER, kind="EXTERNAL_REVIEW_PROCESS"):
    return builders.qualification(record or _individual(), reviewer=reviewer, kind=kind)


def _admission(child=None, admitter=ADMITTER):
    child = child or _individual()
    return {"admission_schema": ADM, "child_agent_id": child["agent_id"], "child_agent_spec_id": child["agent_spec_id"],
            "parent_agent_id": "a" * 64, "admitter_kind": "EXTERNAL_HUMAN", "admitter_id": admitter,
            "policy_sha256": "b" * 64}


def _subject(record, kind=QUAL):
    fields = trust.KINDS[kind].subject
    return {"agent_id": record[fields[0]], "agent_spec_id": record[fields[1]]}


def _sign(record, kind=QUAL, issuer=REVIEWER, key="reviewer-1", version=1, label="e1", lab=LAB):
    return trust.make_envelope(record, record_kind=kind, lab_id=lab, root_version=version, issuer_id=issuer,
                               private_key=lab_key(key), envelope_id=eid(label))


def _resign(envelope, key="reviewer-1", **changes):
    envelope = {**copy.deepcopy(envelope), **changes}
    envelope["signature"] = lab_key(key).sign(trust._message(envelope)).hex()
    return envelope


def _verify(envelope, record, the_root=None, kind=QUAL, subject=None, minimum=1, lab=LAB):
    the_root = the_root or root()
    return trust.verify_envelope(envelope, record, the_root, pin_sha256=pin(the_root), minimum_version=minimum,
                                 lab_id=lab, record_kind=kind, subject=subject or _subject(record, kind))


def _bundle(items, required, the_root=None, minimum=1):
    the_root = the_root or root()
    return trust.verify_bundle(items, required, the_root, pin_sha256=pin(the_root), minimum_version=minimum,
                               lab_id=LAB)


def _props(verdict):
    return verdict["integrity"], verdict["authenticity"], verdict["authorization"]


# ── Acceptance only for a complete bundle ────────────────────────────────
@pytest.mark.parametrize("kind,record,issuer,key", [
    (QUAL, _qualification(), REVIEWER, "reviewer-1"),
    (IND, _individual(), OPERATOR, "operator-1"),
    (ADM, _admission(), ADMITTER, "admitter-1"),
])
def test_an_authorized_envelope_is_attested_and_its_bundle_accepted(kind, record, issuer, key):
    envelope = _sign(record, kind, issuer, key)
    verdict = _verify(envelope, record, kind=kind)
    assert _props(verdict) == ("PASS", "PASS", "PASS") and verdict["attested"] and verdict["failures"] == []
    assert "accepted" not in verdict  # a single envelope never accepts a decision
    bundle = _bundle([(envelope, record)], [(kind, _subject(record, kind))])
    assert bundle["accepted"] and bundle["completeness"] == "PASS" and bundle["failures"] == []


def test_a_record_without_envelope_is_not_authenticated():
    record = _qualification()
    verdict = _verify(None, record)
    assert verdict["failures"] == ["NOT_AUTHENTICATED"] and not verdict["attested"]
    assert _bundle([], [(QUAL, _subject(record))])["failures"] == ["ATTESTATION_MISSING"]


def test_no_existing_record_becomes_authenticated():
    """Sentinel's R8 record stays unauthenticated; the repository holds no envelope and no trust root."""
    r8 = json.loads((ROOT / "docs/colony_lab/SENTINEL_QUALIFICATION_RECORD_R8.json").read_text())
    bundle = _bundle([], [(QUAL, _subject(r8))])
    assert not bundle["accepted"] and bundle["failures"] == ["ATTESTATION_MISSING"]
    for path in (ROOT / "docs").rglob("*.json"):
        text = path.read_text(errors="replace")
        assert trust.ENVELOPE_SCHEMA not in text and trust.ROOT_SCHEMA not in text, path


# ── Integrity ─────────────────────────────────────────────────────────────
def test_a_changed_record_fails_integrity_while_the_signature_stays_valid():
    record = _qualification()
    envelope = _sign(record)
    changed = {**record, "evidence_sha256": "9" * 64}
    verdict = _verify(envelope, changed)
    assert _props(verdict) == ("FAIL", "PASS", "PASS") and verdict["failures"] == ["RECORD_HASH_MISMATCH"]


@pytest.mark.parametrize("record", [["not", "a", "dict"], {"value": float("nan")}])
def test_a_non_canonical_record_fails_integrity(record):
    envelope = _sign(_qualification())
    assert "RECORD_NOT_CANONICAL" in _verify(envelope, record, subject=envelope["subject"])["failures"]


# ── Authenticity ──────────────────────────────────────────────────────────
def test_a_changed_envelope_breaks_the_signature():
    record = _qualification()
    forged = {**_sign(record), "root_version": 1, "envelope_id": eid("other")}
    verdict = _verify(forged, record)
    assert _props(verdict) == ("PASS", "FAIL", "PASS") and verdict["failures"] == ["SIGNATURE_INVALID"]


def test_a_signature_by_another_key_is_invalid():
    record = _qualification()
    forged = _resign(_sign(record), key="stranger")  # the reviewer's key_id, someone else's signature
    assert _verify(forged, record)["failures"] == ["SIGNATURE_INVALID"]


def test_an_unknown_issuer_or_key_is_refused():
    record = _qualification(reviewer="fixture-unknown-reviewer")
    verdict = _verify(_sign(record, issuer="fixture-unknown-reviewer", key="stranger"), record)
    assert verdict["authenticity"] == "FAIL" and verdict["failures"] == ["UNKNOWN_ISSUER"]
    assert verdict["authorization"] == "NOT_EVALUATED"  # no scope to judge: unknown is not PASS
    record = _qualification()
    verdict = _verify(_sign(record, key="stranger"), record)  # known issuer, a key it does not hold
    assert verdict["failures"] == ["UNKNOWN_KEY"]


def test_a_key_of_another_issuer_is_not_the_issuer_key():
    record = _qualification()
    envelope = _sign(record, key="operator-1")  # operator's key, presented as the reviewer's
    assert _verify(envelope, record)["failures"] == ["UNKNOWN_KEY"]


def _rotated(old_status, retired=2, version=2):
    issuers = root()["issuers"]
    issuers[1]["keys"] = [key_entry("reviewer-1", old_status, 1, retired), key_entry("reviewer-2", "ACTIVE", 2)]
    return root(version=version, issuers=issuers)


def test_rotation_keeps_earlier_envelopes_and_refuses_later_ones_of_the_retired_key():
    record = _qualification()
    rotated = _rotated("RETIRED")
    assert _verify(_sign(record, version=1), record, rotated)["attested"]
    assert _verify(_sign(record, version=2), record, rotated)["failures"] == ["KEY_RETIRED"]
    assert _verify(_sign(record, key="reviewer-2", version=2), record, rotated)["attested"]
    assert _verify(_sign(record, key="reviewer-2", version=1), record, rotated)["failures"] == ["KEY_NOT_YET_VALID"]


def test_a_revoked_key_verifies_nothing_whatever_the_declared_version():
    record = _qualification()
    revoked = _rotated("REVOKED")
    assert _verify(_sign(record, version=1), record, revoked)["failures"] == ["KEY_REVOKED"]


def test_an_envelope_from_a_future_root_or_revoked_by_id_is_refused():
    record = _qualification()
    assert _verify(_sign(record, version=2), record)["failures"] == ["ENVELOPE_FROM_FUTURE_ROOT"]
    envelope = _sign(record)
    revoked = root(revoked=[envelope["envelope_id"]])
    assert _verify(envelope, record, revoked)["failures"] == ["ENVELOPE_REVOKED"]


# ── Trust root ────────────────────────────────────────────────────────────
def test_the_trust_root_must_match_its_pin():
    record = _qualification()
    envelope = _sign(record)
    other = root(issuers=root()["issuers"][1:])
    verdict = trust.verify_envelope(envelope, record, other, pin_sha256=pin(root()), minimum_version=1, lab_id=LAB,
                                    record_kind=QUAL, subject=_subject(record))
    assert verdict["failures"] == ["TRUST_ROOT_PIN_MISMATCH"]
    assert _props(verdict) == ("PASS", "FAIL", "NOT_EVALUATED")


def test_only_a_lab_test_root_is_accepted_even_when_pinned():
    record = _qualification()
    production = root(environment="PRODUCTION")
    assert _verify(_sign(record), record, production)["failures"] == ["TRUST_ROOT_NOT_LAB_TEST"]


def test_an_older_root_or_a_root_of_another_lab_is_refused():
    record = _qualification()
    assert _verify(_sign(record), record, minimum=2)["failures"] == ["TRUST_ROOT_ROLLBACK"]
    other_lab = root(lab_id="fixture-other-lab")
    verdict = _verify(_sign(record), record, other_lab)
    assert verdict["failures"] == ["TRUST_ROOT_OTHER_LAB"]


def _broken(change):
    value = root()
    change(value)
    return value


@pytest.mark.parametrize("change", [
    lambda r: r.update(root_schema="colony-trust.root/1"),
    lambda r: r.update(issuers=[]),
    lambda r: r.update(root_version=True),
    lambda r: r.update(revoked_envelopes=["B" * 64]),
    lambda r: r["issuers"].append(copy.deepcopy(r["issuers"][0])),  # duplicate issuer and key
    lambda r: r["issuers"][1].update(scopes=[IND]),  # an external reviewer cannot admit individuals
    lambda r: r["issuers"][2].update(scopes=[QUAL]),  # the operator cannot attest a qualification
    lambda r: r["issuers"][1].update(scopes=[QUAL, QUAL]),
    lambda r: r["issuers"][1].update(scopes=["colony-lab.unknown/0"]),
    lambda r: r["issuers"][1].update(issuer_kind="AGENT"),
    lambda r: r["issuers"][1]["keys"][0].update(key_id="0" * 64),
    lambda r: r["issuers"][1]["keys"][0].update(retired_in_root=1),  # ACTIVE with a retirement
    lambda r: r["issuers"][1]["keys"][0].update(status="RETIRED", retired_in_root=1),  # not after introduction
    lambda r: r["issuers"][1]["keys"][0].update(introduced_in_root=2),  # after the root itself
    lambda r: r["issuers"][1]["keys"][0].update(status="UNKNOWN"),
    lambda r: r["issuers"][1].update(keys=[]),
])
def test_a_malformed_trust_root_is_refused(change):
    record = _qualification()
    verdict = _verify(_sign(record), record, _broken(change))
    assert verdict["failures"] == ["TRUST_ROOT_INVALID"] and verdict["authenticity"] == "FAIL"


# ── Authorization ─────────────────────────────────────────────────────────
def test_an_envelope_made_for_another_lab_is_not_authorized_here():
    record = _qualification()
    verdict = _verify(_sign(record, lab="fixture-other-lab"), record)
    assert _props(verdict) == ("PASS", "PASS", "FAIL") and verdict["failures"] == ["AUDIENCE_MISMATCH"]


def test_an_envelope_is_only_valid_for_the_decision_kind_it_names():
    record = _qualification()
    verdict = _verify(_sign(record), record, kind=IND, subject=_subject(record))
    assert verdict["failures"] == ["RECORD_KIND_MISMATCH"]


def test_a_purpose_other_than_its_kind_is_refused():
    record = _qualification()
    envelope = _resign(_sign(record), purpose="INDIVIDUAL_ADMITTED")
    assert _verify(envelope, record)["failures"] == ["PURPOSE_MISMATCH"]


def test_a_key_cannot_sign_outside_its_scope():
    record = _qualification(reviewer=OPERATOR, kind="EXTERNAL_HUMAN")
    verdict = _verify(_sign(record, issuer=OPERATOR, key="operator-1"), record)
    assert "SCOPE_NOT_GRANTED" in verdict["failures"] and verdict["authenticity"] == "PASS"


def test_the_record_author_must_be_the_issuer():
    record = _qualification(reviewer="fixture-other-reviewer")
    verdict = _verify(_sign(record), record)
    assert _props(verdict) == ("PASS", "PASS", "FAIL") and verdict["failures"] == ["AUTHOR_NOT_ISSUER"]
    record = _qualification(kind="EXTERNAL_HUMAN")  # the issuer is a review process, not a human
    assert _verify(_sign(record), record)["failures"] == ["AUTHOR_NOT_ISSUER"]


def test_an_envelope_cannot_be_moved_to_another_subject():
    record, other = _qualification(), _qualification(builders.founder(name="archivist_01")[1])
    envelope = _sign(record)
    verdict = _verify(envelope, other)
    assert set(verdict["failures"]) == {"RECORD_HASH_MISMATCH", "SUBJECT_MISMATCH"}
    resigned = _resign(envelope, subject=_subject(other))  # subject changed, record hash kept
    assert set(_verify(resigned, record, subject=_subject(other))["failures"]) == {"SUBJECT_MISMATCH"}
    assert set(_verify(envelope, record, subject=_subject(other))["failures"]) == {"SUBJECT_MISMATCH"}


# ── Unknown or invalid envelopes ──────────────────────────────────────────
@pytest.mark.parametrize("change,code", [
    (lambda e: e.update(envelope_schema="colony-trust.envelope/1"), "UNKNOWN_ENVELOPE_SCHEMA"),
    (lambda e: e.update(record_kind="colony-lab.unknown/0"), "UNKNOWN_RECORD_KIND"),
    (lambda e: e.pop("purpose"), "ENVELOPE_INVALID"),
    (lambda e: e.update(extra=1), "ENVELOPE_INVALID"),
    (lambda e: e.update(root_version=True), "ENVELOPE_INVALID"),
    (lambda e: e.update(root_version=0), "ENVELOPE_INVALID"),
    (lambda e: e.update(signature=e["signature"].upper()), "ENVELOPE_INVALID"),
    (lambda e: e.update(signature=e["signature"][:-2]), "ENVELOPE_INVALID"),
    (lambda e: e.update(envelope_id="x" * 64), "ENVELOPE_INVALID"),
    (lambda e: e["subject"].update(extra="a" * 64), "ENVELOPE_INVALID"),
    (lambda e: e.update(lab_id="Lab"), "ENVELOPE_INVALID"),
])
def test_unknown_or_invalid_envelopes_are_refused(change, code):
    record = _qualification()
    envelope = _sign(record)
    change(envelope)
    verdict = _verify(envelope, record)
    assert verdict["failures"] == [code] and not verdict["attested"]
    assert verdict["integrity"] == "FAIL" and verdict["authorization"] == "NOT_EVALUATED"


# ── Completeness ──────────────────────────────────────────────────────────
def test_a_bundle_fails_on_a_missing_a_duplicated_or_an_unexpected_attestation():
    qual, ind = _qualification(), _individual()
    q_env, i_env = _sign(qual), _sign(ind, IND, OPERATOR, "operator-1", label="e2")
    both = [(QUAL, _subject(qual)), (IND, _subject(ind, IND))]
    assert _bundle([(q_env, qual), (i_env, ind)], both)["accepted"]
    missing = _bundle([(q_env, qual)], both)
    assert missing["failures"] == ["ATTESTATION_MISSING"] and missing["completeness"] == "FAIL"
    assert missing["integrity"] == "PASS" and not missing["accepted"]
    again = _sign(qual, label="e3")
    assert _bundle([(q_env, qual), (again, qual)], both[:1])["failures"] == ["ATTESTATION_DUPLICATED"]
    assert _bundle([(q_env, qual), (i_env, ind)], both[:1])["failures"] == ["ATTESTATION_UNEXPECTED"]
    assert _bundle([], [])["failures"] == ["ATTESTATION_MISSING"]


def test_a_bundle_reports_the_failure_of_each_envelope():
    qual = _qualification()
    bundle = _bundle([(_sign(qual, lab="fixture-other-lab"), qual)], [(QUAL, _subject(qual))])
    assert bundle["completeness"] == "PASS" and bundle["authorization"] == "FAIL" and not bundle["accepted"]
    assert bundle["failures"] == ["AUDIENCE_MISMATCH"]


# ── Single use ────────────────────────────────────────────────────────────
def test_a_birth_admission_is_consumed_once(tmp_path):
    ledger = tmp_path / "consumed.jsonl"
    admission = _admission()
    envelope = _sign(admission, ADM, ADMITTER, "admitter-1")
    trust.consume(ledger, envelope)
    with pytest.raises(trust.TrustError, match="ENVELOPE_REPLAYED"):
        trust.consume(ledger, envelope)
    other = _sign({**admission, "policy_sha256": "c" * 64}, ADM, ADMITTER, "admitter-1")  # same envelope id
    with pytest.raises(trust.TrustError, match="ENVELOPE_ID_REUSED"):
        trust.consume(ledger, other)
    assert len(ledger.read_text().splitlines()) == 1


def test_durable_attestations_are_not_single_use_and_a_corrupt_ledger_refuses(tmp_path):
    with pytest.raises(trust.TrustError, match="NOT_SINGLE_USE"):
        trust.consume(tmp_path / "consumed.jsonl", _sign(_qualification()))
    ledger = tmp_path / "corrupt.jsonl"
    ledger.write_text("{not json\n")
    with pytest.raises(trust.TrustError, match="LEDGER_CORRUPT"):
        trust.consume(ledger, _sign(_admission(), ADM, ADMITTER, "admitter-1"))


# ── Separation ────────────────────────────────────────────────────────────
def _imports(path):
    tree = ast.parse(path.read_text())
    return {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | \
        {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}


def test_trust_is_not_wired_into_the_lab_and_imports_no_runtime():
    for package in ("colony_lab", "colony_pilot"):
        for path in (ROOT / package).rglob("*.py"):
            assert not any(name.startswith("colony_trust") for name in _imports(path)), path
    allowed = ("__future__", "fcntl", "hashlib", "json", "os", "re", "pathlib", "typing", "cryptography",
               "colony_lab.a1_identity")
    for path in (ROOT / "colony_trust").rglob("*.py"):
        assert all(name.startswith(allowed) for name in _imports(path)), path


def test_the_signature_covers_the_domain_separated_message_only():
    record = _qualification()
    envelope = _sign(record)
    body = {name: value for name, value in envelope.items() if name != "signature"}
    bare = {**envelope, "signature": lab_key("reviewer-1").sign(trust._canonical(body)).hex()}
    assert _verify(bare, record)["failures"] == ["SIGNATURE_INVALID"]


def test_a_record_of_another_kind_under_the_same_subject_is_refused():
    individual = _individual()
    envelope = trust.make_envelope(individual, record_kind=IND, lab_id=LAB, root_version=1, issuer_id=REVIEWER,
                                   private_key=lab_key("reviewer-1"), envelope_id=eid("kind"))
    envelope = _resign(envelope, record_kind=QUAL, purpose="QUALIFICATION_ATTESTED")
    verdict = _verify(envelope, individual, subject=_subject(individual))
    assert {"RECORD_KIND_MISMATCH", "AUTHOR_NOT_ISSUER"} <= set(verdict["failures"])
    assert verdict["integrity"] == "PASS" and verdict["authenticity"] == "PASS"


def test_a_property_not_evaluated_is_never_attested():
    assert trust._verdict({}, [], [], [], True, True, False)["attested"] is False
    assert trust._verdict({}, [], [], [], True, False, True)["attested"] is False
