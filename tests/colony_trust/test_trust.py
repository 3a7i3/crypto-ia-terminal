"""colony-trust/0: integrity, authenticity, authorization and completeness are judged apart."""

import ast
import copy
import json
import multiprocessing
import os
import time
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
def test_an_authorized_envelope_is_attested_and_its_bundle_accepted(kind, record, issuer, key, tmp_path):
    envelope = _sign(record, kind, issuer, key)
    verdict = _verify(envelope, record, kind=kind)
    assert _props(verdict) == ("PASS", "PASS", "PASS") and verdict["attested"] and verdict["failures"] == []
    assert "accepted" not in verdict  # a single envelope never accepts a decision
    the_root = root()
    bundle = trust.verify_bundle([(envelope, record)], [(kind, _subject(record, kind))], the_root,
                                 pin_sha256=pin(the_root), minimum_version=1, lab_id=LAB,
                                 ledger=tmp_path / "consumed.jsonl")
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


# ── Single use, judged inside the bundle ──────────────────────────────────
def _admission_bundle(ledger, admission=None, envelope=None, the_root=None):
    admission = admission or _admission()
    envelope = envelope or _sign(admission, ADM, ADMITTER, "admitter-1")
    the_root = the_root or root()
    return trust.verify_bundle([(envelope, admission)], [(ADM, _subject(admission, ADM))], the_root,
                               pin_sha256=pin(the_root), minimum_version=1, lab_id=LAB, ledger=ledger)


def test_a_birth_admission_is_accepted_once_and_its_replay_is_refused(tmp_path):
    ledger = tmp_path / "consumed.jsonl"
    admission = _admission()
    envelope = _sign(admission, ADM, ADMITTER, "admitter-1")
    first = _admission_bundle(ledger, admission, envelope)
    assert first["accepted"] and first["failures"] == []
    again = _admission_bundle(ledger, admission, envelope)
    assert not again["accepted"] and again["failures"] == ["ENVELOPE_REPLAYED"]
    assert again["authorization"] == "FAIL" and again["integrity"] == "PASS" and again["authenticity"] == "PASS"
    other = {**admission, "policy_sha256": "c" * 64}
    reused = _admission_bundle(ledger, other, _sign(other, ADM, ADMITTER, "admitter-1"))  # same envelope id
    assert not reused["accepted"] and reused["failures"] == ["ENVELOPE_ID_REUSED"]
    assert len(ledger.read_bytes().splitlines()) == 1


def test_a_single_use_envelope_without_ledger_is_never_accepted():
    bundle = _admission_bundle(None)
    assert not bundle["accepted"] and bundle["failures"] == ["LEDGER_REQUIRED"]
    assert bundle["authorization"] == "FAIL"


def test_a_refused_bundle_spends_nothing(tmp_path):
    ledger = tmp_path / "consumed.jsonl"
    admission = _admission()
    forged = _resign(_sign(admission, ADM, ADMITTER, "admitter-1"), key="reviewer-1")
    assert _admission_bundle(ledger, admission, forged)["failures"] == ["SIGNATURE_INVALID"]
    assert _admission_bundle(ledger, admission)["accepted"]  # the genuine one is still unspent


def test_the_ledger_is_keyed_by_issuer_and_envelope_id(tmp_path):
    ledger = tmp_path / "consumed.jsonl"
    second = {"issuer_id": "fixture-second-admitter", "issuer_kind": "EXTERNAL_HUMAN",
              "scopes": [ADM], "keys": [key_entry("admitter-2")]}
    the_root = root(issuers=[*root()["issuers"], second])
    one = _admission()
    assert _admission_bundle(ledger, one, the_root=the_root)["accepted"]
    two = _admission(admitter="fixture-second-admitter")
    envelope = _sign(two, ADM, "fixture-second-admitter", "admitter-2")  # same envelope id, other issuer
    assert _admission_bundle(ledger, two, envelope, the_root)["accepted"]


@pytest.mark.parametrize("content", [
    b"{not json\n",
    b'{"envelope_id":"' + b"a" * 64 + b'"}\n',  # foreign fields
    b'{"envelope_id": "x"}\n',  # not canonical
    b"",  # empty is fine: see below
])
def test_a_corrupt_or_truncated_ledger_refuses_and_is_not_extended(tmp_path, content):
    ledger = tmp_path / "consumed.jsonl"
    ledger.write_bytes(content)
    bundle = _admission_bundle(ledger)
    if content == b"":
        assert bundle["accepted"]
        return
    assert not bundle["accepted"] and bundle["failures"] == ["LEDGER_CORRUPT"]
    assert ledger.read_bytes() == content


def test_a_ledger_with_a_truncated_or_duplicated_entry_refuses(tmp_path):
    ledger = tmp_path / "consumed.jsonl"
    assert _admission_bundle(ledger)["accepted"]
    line = ledger.read_bytes()
    ledger.write_bytes(line[:-1])  # crash before the newline
    assert _admission_bundle(ledger, _admission(_individual()))["failures"] == ["LEDGER_CORRUPT"]
    ledger.write_bytes(line + line)
    assert _admission_bundle(ledger)["failures"] == ["LEDGER_CORRUPT"]
    duplicate = line[:-2] + b',"envelope_id":"' + b"0" * 64 + b'"}\n'
    ledger.write_bytes(duplicate)
    assert _admission_bundle(ledger)["failures"] == ["LEDGER_CORRUPT"]


def test_a_symlinked_ledger_is_refused(tmp_path):
    target = tmp_path / "elsewhere.jsonl"
    target.write_bytes(b"")
    ledger = tmp_path / "consumed.jsonl"
    ledger.symlink_to(target)
    assert _admission_bundle(ledger)["failures"] == ["LEDGER_CORRUPT"]
    assert target.read_bytes() == b""


def test_durable_attestations_need_no_ledger_and_spend_nothing(tmp_path):
    record = _qualification()
    ledger = tmp_path / "consumed.jsonl"
    bundle = trust.verify_bundle([(_sign(record), record)], [(QUAL, _subject(record))], root(),
                                 pin_sha256=pin(root()), minimum_version=1, lab_id=LAB, ledger=ledger)
    assert bundle["accepted"] and not ledger.exists()
    # Amendment 4 adds a verifier-backed consume API; durable-only bundles still cannot spend.
    verdict = trust.consume([(_sign(record), record)], [(QUAL, _subject(record), pin(record))], root(),
                            pin_sha256=pin(root()), minimum_version=1, lab_id=LAB, ledger=ledger,
                            operation_sha256="a" * 64)
    assert not verdict["accepted"] and verdict["failures"] == ["ADMISSION_REQUIRED"]
    assert not ledger.exists()


# ── Weak keys ─────────────────────────────────────────────────────────────
_IDENTITY = (1).to_bytes(32, "little")
_ORDER_2 = (trust._P - 1).to_bytes(32, "little")  # (0, -1)
_ORDER_4 = (0).to_bytes(32, "little")  # (±sqrt(-1), 0)
_SMALL_8 = bytes.fromhex("26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05")  # order 8


@pytest.mark.parametrize("raw", [
    _IDENTITY,
    bytes([*_IDENTITY[:31], 0x80]),  # x = 0 with sign bit set
    _ORDER_2, _ORDER_4, _SMALL_8,
    (trust._P + 1).to_bytes(32, "little"),  # y ≥ p: a non-canonical identity
    (2).to_bytes(32, "little"),  # y = 2 is not on the curve
])
def test_small_order_non_canonical_and_off_curve_keys_are_refused(raw):
    assert not trust.prime_order_key(raw)
    entry = {"key_id": trust.key_id(raw.hex()), "public_key": raw.hex(), "status": "ACTIVE",
             "introduced_in_root": 1, "retired_in_root": None}
    bad = root(issuers=[{"issuer_id": REVIEWER, "issuer_kind": "EXTERNAL_REVIEW_PROCESS", "scopes": [QUAL],
                         "keys": [entry]}])
    with pytest.raises(trust.TrustError, match="TRUST_ROOT_INVALID"):
        trust.check_root(bad, pin_sha256=pin(bad), minimum_version=1, lab_id=LAB)


def test_the_identity_key_would_verify_a_forged_signature_and_is_refused_first():
    """R = identity, S = 0 is a valid signature of any message under the identity key."""
    record = _qualification()
    entry = {"key_id": trust.key_id(_IDENTITY.hex()), "public_key": _IDENTITY.hex(), "status": "ACTIVE",
             "introduced_in_root": 1, "retired_in_root": None}
    bad = root(issuers=[{"issuer_id": REVIEWER, "issuer_kind": "EXTERNAL_REVIEW_PROCESS", "scopes": [QUAL],
                         "keys": [entry]}])
    envelope = {**_sign(record), "key_id": entry["key_id"]}
    envelope["signature"] = (_IDENTITY + bytes(32)).hex()
    verdict = _verify(envelope, record, bad)
    assert verdict["failures"] == ["TRUST_ROOT_INVALID"] and not verdict["attested"]


def _decode(raw):
    p = trust._P
    y, sign = int.from_bytes(raw, "little") & ((1 << 255) - 1), raw[31] >> 7
    x2 = (y * y - 1) * pow(trust._D * y * y + 1, p - 2, p) % p
    x = pow(x2, (p + 3) // 8, p)
    if (x * x - x2) % p:
        x = x * trust._SQRT_M1 % p
    if x & 1 != sign:
        x = p - x
    return x, y, 1, x * y % p


def _encode(point):
    p = trust._P
    inverse = pow(point[2], p - 2, p)
    x, y = point[0] * inverse % p, point[1] * inverse % p
    return (y | (x & 1) << 255).to_bytes(32, "little")


@pytest.mark.parametrize("torsion", [_ORDER_2, _ORDER_4, _SMALL_8])
def test_a_key_with_a_small_order_component_is_refused(torsion):
    """A valid key plus a point of order 2, 4 or 8 is on the curve but outside the prime-order subgroup."""
    good = bytes.fromhex(trust.public_key_hex(lab_key("reviewer-1")))
    mixed = _encode(trust._add(_decode(good), _decode(torsion)))
    assert trust.prime_order_key(good) and _encode(_decode(good)) == good
    assert mixed != good and not trust.prime_order_key(mixed)


def test_the_public_key_helpers_refuse_anything_but_raw_keys():
    for value in ("zz" * 32, "00" * 31, 1, None, b"\x00" * 32):
        with pytest.raises(trust.TrustError, match="KEY_INVALID"):
            trust.key_id(value)
    for value in ("00" * 32, None, 1, bytearray(32), b"\x01" * 31):
        assert trust.prime_order_key(value) is False


def test_every_lab_test_key_is_of_prime_order():
    for label in ("admitter-1", "admitter-2", "reviewer-1", "operator-1"):
        assert trust.prime_order_key(bytes.fromhex(trust.public_key_hex(lab_key(label))))


# ── Malformed inputs get coded refusals ───────────────────────────────────
@pytest.mark.parametrize("change", [
    lambda r: r.update(root_version=2**31),
    lambda r: r.update(root_version=True),
    lambda r: r.update(revoked_envelopes=[["x"]]),
    lambda r: r.update(revoked_envelopes=[1, "a"]),
    lambda r: r.update(environment={"a": 1}),
    lambda r: r["issuers"][0].update(scopes=[["x"]]),
    lambda r: r["issuers"][0].update(issuer_kind=["EXTERNAL_HUMAN"]),
    lambda r: r["issuers"][0]["keys"][0].update(status={"x": 1}),
    lambda r: r["issuers"][0]["keys"][0].update(public_key="zz" * 32),
    lambda r: r["issuers"].append("not an issuer"),
    lambda r: r.update(extra=1),
    lambda r: r["issuers"][0].update(extra=1),
    lambda r: r["issuers"][0]["keys"][0].update(extra=1),
    lambda r: r["issuers"][0].update(issuer_id="X!"),
    lambda r: r.update(lab_id="X"),
    lambda r: r.update(revoked_envelopes=["b" * 64, "a" * 64]),
    lambda r: r.update(revoked_envelopes=["a" * 64, "a" * 64]),
    lambda r: r["issuers"][0].update(scopes=[]),
    lambda r: r["issuers"][0]["keys"][0].update(introduced_in_root=0),
    lambda r: (r.update(root_version=2), r["issuers"][0]["keys"][0].update(status="WHATEVER", retired_in_root=2)),
])
def test_a_malformed_root_is_refused_with_a_code(change):
    bad = root()
    change(bad)
    with pytest.raises(trust.TrustError, match="TRUST_ROOT_INVALID|TRUST_ROOT_PIN_MISMATCH"):
        trust.check_root(bad, pin_sha256=pin(bad) if _canonical_ok(bad) else "0" * 64, minimum_version=1,
                         lab_id=LAB)
    record = _qualification()
    assert not _verify(_sign(record), record, bad)["attested"]


def _canonical_ok(value):
    try:
        trust.sha256_of(value)
        return True
    except trust.TrustError:
        return False


@pytest.mark.parametrize("items,required", [
    ("not a list", []),
    ([("only one",)], []),
    ([], "not a list"),
    ([], [("kind",)]),
    ([], [(QUAL, {"agent_id": ["x"]})]),
    ([], [(QUAL, {"agent_id": "a", "agent_spec_id": "b"}), (QUAL, {"agent_id": "a", "agent_spec_id": "b"})]),
    (None, [(QUAL, {"agent_id": "a", "agent_spec_id": "b"})]),
    ([({}, {})], None),
    ([], [(["kind"], {"agent_id": "a", "agent_spec_id": "b"})]),
    ([], [(QUAL, ["agent_id", "agent_spec_id"])]),
    ([], [(QUAL, {"agent_id": "a"})]),
    ([], [(QUAL, {"agent_id": "a", "agent_spec_id": ["b"]})]),
])
def test_a_malformed_bundle_or_a_duplicated_requirement_is_refused_with_a_code(items, required):
    bundle = _bundle(items, required)
    assert not bundle["accepted"] and bundle["failures"] == ["BUNDLE_INVALID"]
    assert bundle["completeness"] == "FAIL" and bundle["integrity"] == "NOT_EVALUATED"


def test_a_duplicated_requirement_is_refused_even_with_its_envelope():
    record = _qualification()
    need = (QUAL, _subject(record))
    assert _bundle([(_sign(record), record)], [need, need])["failures"] == ["BUNDLE_INVALID"]


def test_strict_loads_refuses_every_other_spelling_of_a_record():
    record = _qualification()
    raw = trust._canonical(record)
    assert trust.loads(raw) == record
    for other in (raw + b" ", raw.replace(b'{"', b'{ "', 1), b'{"a":1,"a":2}', b'{"a":NaN}', b"[" * 20 + b"]" * 20,
                  "text", None):
        with pytest.raises(trust.TrustError, match="NOT_CANONICAL"):
            trust.loads(other)


# ── Separation ────────────────────────────────────────────────────────────
def _imports(path):
    tree = ast.parse(path.read_text())
    return {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | \
        {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}


def test_trust_is_not_wired_into_the_lab_and_imports_no_runtime():
    for package in ("colony_lab", "colony_pilot"):
        for path in (ROOT / package).rglob("*.py"):
            assert not any(name.startswith("colony_trust") for name in _imports(path)), path
    allowed = ("__future__", "contextlib", "fcntl", "hashlib", "json", "os", "re", "stat", "pathlib", "typing",
               "cryptography",
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


# ── Second review: guards for every property the operator requires ──────
def test_two_envelopes_with_the_same_issuer_and_id_in_one_bundle_are_refused_and_spend_nothing(tmp_path):
    ledger = tmp_path / "consumed.jsonl"
    one, two = _admission(), _admission(builders.founder(name="other_01")[1])
    first = _sign(one, ADM, ADMITTER, "admitter-1", label="same")
    second = _sign(two, ADM, ADMITTER, "admitter-1", label="same")
    bundle = trust.verify_bundle([(first, one), (second, two)], [(ADM, _subject(one, ADM)), (ADM, _subject(two, ADM))],
                                 root(), pin_sha256=pin(root()), minimum_version=1, lab_id=LAB, ledger=ledger)
    assert not bundle["accepted"] and bundle["failures"] == ["ENVELOPE_ID_REUSED"]
    assert not ledger.exists()


def _accept_once(ledger, queue):
    queue.put(_admission_bundle(Path(ledger))["accepted"])


def test_concurrent_bundles_accept_a_single_use_envelope_once(tmp_path, monkeypatch):
    ledger = tmp_path / "consumed.jsonl"
    read = trust._read

    def slow_read(fd):  # widen the window between reading the ledger and writing it
        spent = read(fd)
        time.sleep(0.05)
        return spent
    monkeypatch.setattr(trust, "_read", slow_read)
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    workers = [context.Process(target=_accept_once, args=(str(ledger), queue)) for _ in range(12)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(30)
    results = [queue.get(timeout=5) for _ in workers]
    assert results.count(True) == 1 and len(ledger.read_bytes().splitlines()) == 1


def test_the_ledger_is_private_and_only_a_regular_single_link_file(tmp_path):
    ledger = tmp_path / "consumed.jsonl"
    assert _admission_bundle(ledger)["accepted"]
    assert ledger.stat().st_mode & 0o777 == 0o600
    linked = tmp_path / "linked.jsonl"
    os.link(ledger, linked)
    assert _admission_bundle(linked, _admission(_individual()))["failures"] == ["LEDGER_CORRUPT"]
    directory = tmp_path / "a-directory"
    directory.mkdir()
    for bad in (directory, tmp_path / "nul\x00name", tmp_path / "missing" / "consumed.jsonl"):
        assert _admission_bundle(bad)["failures"] == ["LEDGER_CORRUPT"], bad


def test_a_refused_bundle_creates_no_ledger(tmp_path):
    ledger = tmp_path / "consumed.jsonl"
    admission = _admission()
    forged = _resign(_sign(admission, ADM, ADMITTER, "admitter-1"), key="reviewer-1")
    assert not _admission_bundle(ledger, admission, forged)["accepted"]
    assert not ledger.exists()


def test_an_unsynced_ledger_write_is_not_accepted(tmp_path, monkeypatch):
    def fail(fd):
        raise OSError("fsync failed")
    monkeypatch.setattr(trust.os, "fsync", fail)
    bundle = _admission_bundle(tmp_path / "consumed.jsonl")
    assert not bundle["accepted"] and bundle["failures"] == ["LEDGER_CORRUPT"]


def test_a_malformed_envelope_leaves_the_other_properties_not_evaluated():
    record = _qualification()
    signed = _sign(record)
    for envelope in ("x", {}, {**signed, "purpose": "\ud800"},
                     {**signed, "subject": {"agent_id": "X" * 64, "agent_spec_id": "a" * 64}},
                     ["envelope_schema"], list(signed), {**signed, "key_id": 1}, {**signed, "envelope_id": 1},
                     {**signed, "signature": 1}, {**signed, "subject": ["agent_id", "agent_spec_id"]},
                     {**signed, "subject": {"agent_id": 1, "agent_spec_id": "a" * 64}}):
        verdict = _verify(envelope, record)
        assert verdict["integrity"] == "FAIL" and not verdict["attested"]
        assert (verdict["authenticity"], verdict["authorization"]) in {("NOT_EVALUATED", "NOT_EVALUATED")}, verdict
        assert verdict["failures"][0] in {"ENVELOPE_INVALID", "UNKNOWN_ENVELOPE_SCHEMA"}


def test_an_empty_bundle_evaluates_nothing():
    bundle = _bundle([], [])
    assert (bundle["integrity"], bundle["authenticity"], bundle["authorization"]) == ("NOT_EVALUATED",) * 3
    assert not bundle["accepted"]
    bundle = _bundle(None, None)
    assert bundle["failures"] == ["BUNDLE_INVALID"] and not bundle["accepted"]


def test_issuers_and_keys_are_unique_across_the_root():
    issuers = root()["issuers"]
    twice = root(issuers=[*issuers, {**copy.deepcopy(issuers[0]), "keys": [key_entry("admitter-2")]}])
    shared = copy.deepcopy(issuers)
    shared[1]["keys"] = copy.deepcopy(shared[0]["keys"])
    for bad in (twice, root(issuers=shared)):
        with pytest.raises(trust.TrustError, match="TRUST_ROOT_INVALID"):
            trust.check_root(bad, pin_sha256=pin(bad), minimum_version=1, lab_id=LAB)


def test_a_non_canonical_root_gets_a_coded_refusal():
    bad = {**root(), "root_version": 1.0}
    with pytest.raises(trust.TrustError, match="TRUST_ROOT_INVALID"):
        trust.check_root(bad, pin_sha256="0" * 64, minimum_version=1, lab_id=LAB)
    record = _qualification()
    verdict = trust.verify_envelope(_sign(record), record, bad, pin_sha256="0" * 64, minimum_version=1, lab_id=LAB,
                                    record_kind=QUAL, subject=_subject(record))
    assert verdict["failures"] == ["TRUST_ROOT_INVALID"] and verdict["authenticity"] == "FAIL"


def test_the_root_version_bound_is_inclusive():
    top = root(version=trust.MAX_VERSION)
    trust.check_root(top, pin_sha256=pin(top), minimum_version=trust.MAX_VERSION, lab_id=LAB)
    above = root(version=trust.MAX_VERSION + 1)
    with pytest.raises(trust.TrustError, match="TRUST_ROOT_INVALID"):
        trust.check_root(above, pin_sha256=pin(above), minimum_version=1, lab_id=LAB)
    with pytest.raises(trust.TrustError, match="TRUST_ROOT_ROLLBACK"):
        trust.check_root(top, pin_sha256=pin(top), minimum_version=trust.MAX_VERSION + 1, lab_id=LAB)


def test_a_lab_id_of_another_type_is_another_lab():
    with pytest.raises(trust.TrustError, match="TRUST_ROOT_OTHER_LAB"):
        trust.check_root(root(), pin_sha256=pin(root()), minimum_version=1, lab_id=1)


def test_a_property_not_evaluated_is_never_attested():
    assert trust._verdict({}, [], [], [], True, True, False)["attested"] is False
    assert trust._verdict({}, [], [], [], True, False, True)["attested"] is False


# ── Third review: guards for the remaining central properties ───────────
def test_a_key_of_unknown_status_is_refused_even_with_a_retirement_root():
    issuers = root()["issuers"]
    issuers[0]["keys"] = [key_entry("admitter-1", status="WHATEVER", retired=2)]
    bad = root(version=2, issuers=issuers)
    with pytest.raises(trust.TrustError, match="TRUST_ROOT_INVALID"):
        trust.check_root(bad, pin_sha256=pin(bad), minimum_version=1, lab_id=LAB)
    assert not _admission_bundle(None, the_root=bad)["accepted"]


def test_a_refused_bundle_spends_none_of_its_fresh_envelopes(tmp_path):
    ledger = tmp_path / "consumed.jsonl"
    spent, fresh = _admission(), _admission(builders.founder(name="other_01")[1])
    spent_envelope = _sign(spent, ADM, ADMITTER, "admitter-1", label="spent")
    fresh_envelope = _sign(fresh, ADM, ADMITTER, "admitter-1", label="fresh")
    assert _admission_bundle(ledger, spent, spent_envelope)["accepted"]
    both = trust.verify_bundle([(spent_envelope, spent), (fresh_envelope, fresh)],
                               [(ADM, _subject(spent, ADM)), (ADM, _subject(fresh, ADM))], root(),
                               pin_sha256=pin(root()), minimum_version=1, lab_id=LAB, ledger=ledger)
    assert not both["accepted"] and both["failures"] == ["ENVELOPE_REPLAYED"]
    assert len(ledger.read_bytes().splitlines()) == 1
    assert _admission_bundle(ledger, fresh, fresh_envelope)["accepted"]


def test_a_device_ledger_is_refused_before_it_is_read(monkeypatch):
    assert _admission_bundle(Path("/dev/null"))["failures"] == ["LEDGER_CORRUPT"]

    def never(fd):
        raise AssertionError("a device must be refused before it is read")
    monkeypatch.setattr(trust, "_read", never)
    assert _admission_bundle(Path("/dev/zero"))["failures"] == ["LEDGER_CORRUPT"]


@pytest.mark.parametrize("change", [
    {"ledger_schema": "colony-trust.consumed/9"},
    {"issuer_id": "X!"},
    {"envelope_id": "A" * 64},
    {"envelope_sha256": "A" * 64},
])
def test_a_ledger_line_outside_the_grammar_is_corrupt(tmp_path, change):
    ledger = tmp_path / "consumed.jsonl"
    entry = {"ledger_schema": trust.LEDGER_SCHEMA, "issuer_id": ADMITTER, "envelope_id": eid("other"),
             "envelope_sha256": "a" * 64, **change}
    ledger.write_bytes(trust._canonical(entry) + b"\n")
    ledger.chmod(0o600)
    bundle = _admission_bundle(ledger)
    assert not bundle["accepted"] and bundle["failures"] == ["LEDGER_CORRUPT"]
    assert len(ledger.read_bytes().splitlines()) == 1


def test_a_ledger_of_another_type_is_corrupt():
    assert _admission_bundle(5)["failures"] == ["LEDGER_CORRUPT"]


def test_strict_parsing_codes_every_malformed_input():
    for raw in (b"garbage", b"\xff", b"[" * 100_000):
        with pytest.raises(trust.TrustError, match="NOT_CANONICAL"):
            trust.loads(raw)
    with pytest.raises(trust.TrustError, match="NOT_CANONICAL"):
        trust.sha256_of(1.0)


def test_a_root_needs_an_integer_minimum_version():
    for minimum in (0, None, True, 1.0):
        with pytest.raises(trust.TrustError, match="TRUST_ROOT_ROLLBACK"):
            trust.check_root(root(), pin_sha256=pin(root()), minimum_version=minimum, lab_id=LAB)


def test_an_unauthenticated_envelope_leaves_the_bundle_authorization_not_evaluated():
    record = _qualification()
    bundle = _bundle([(_sign(record, issuer="fixture-unknown-issuer"), record)], [(QUAL, _subject(record))])
    assert (bundle["authenticity"], bundle["authorization"]) == ("FAIL", "NOT_EVALUATED")
    assert not bundle["accepted"]


def test_malformed_envelopes_beside_a_requirement_are_unexpected_not_errors():
    record = _qualification()
    for envelope in (None, {}, "x", ["record_kind"]):
        bundle = _bundle([(envelope, record)], [(QUAL, _subject(record))])
        assert not bundle["accepted"] and bundle["envelopes"] == []
        assert bundle["failures"] == ["ATTESTATION_MISSING", "ATTESTATION_UNEXPECTED"]
