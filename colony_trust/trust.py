"""Envelopes that authenticate colony lab records (schema colony-trust.envelope/0).

A verdict keeps four properties apart: integrity (this is the record the
envelope names), authenticity (a key of the pinned trust root signed it),
authorization (that issuer may say this, for this lab and subject) and
completeness (every attestation a decision needs is there, once). A single
envelope is at most "attested" (the first three); only verify_bundle()
evaluates completeness and can accept. A property that could not be
evaluated is NOT_EVALUATED, never PASS.

The trust root is supplied by the caller and pinned by its SHA-256 and a
minimum version; it is never read from the lab root. Only LAB_TEST roots are
accepted: this module cannot be used with a production key.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from colony_lab.a1_identity import IdentityError, _canonical

ROOT_SCHEMA = "colony-trust.root/0"
ENVELOPE_SCHEMA = "colony-trust.envelope/0"
VERDICT_SCHEMA = "colony-trust.verdict/0"
LEDGER_SCHEMA = "colony-trust.consumed/0"
ENVIRONMENT = "LAB_TEST"
DOMAIN = ENVELOPE_SCHEMA.encode() + b"\x00"
EXTERNAL = frozenset({"EXTERNAL_HUMAN", "EXTERNAL_REVIEW_PROCESS"})
ISSUER_KINDS = EXTERNAL | {"LAB_OPERATOR"}
KEY_STATUSES = frozenset({"ACTIVE", "RETIRED", "REVOKED"})


class Kind:
    def __init__(self, schema_field: str, purpose: str, issuers: frozenset[str], subject: tuple[str, str],
                 author: tuple[str, str] | None, single_use: bool) -> None:
        self.schema_field, self.purpose, self.issuers = schema_field, purpose, issuers
        self.subject, self.author, self.single_use = subject, author, single_use


KINDS = {
    "colony-lab.individual/0": Kind("individual_schema", "INDIVIDUAL_ADMITTED", frozenset({"LAB_OPERATOR"}),
                                    ("agent_id", "agent_spec_id"), None, False),
    "colony-lab.qualification/0": Kind("qualification_schema", "QUALIFICATION_ATTESTED", EXTERNAL,
                                       ("agent_id", "agent_spec_id"), ("reviewer_kind", "reviewer_id"), False),
    "colony-registrar.admission/0": Kind("admission_schema", "BIRTH_ADMITTED", EXTERNAL,
                                         ("child_agent_id", "child_agent_spec_id"),
                                         ("admitter_kind", "admitter_id"), True),
}
ROOT_FIELDS = frozenset({"root_schema", "environment", "lab_id", "root_version", "issuers", "revoked_envelopes"})
ISSUER_FIELDS = frozenset({"issuer_id", "issuer_kind", "scopes", "keys"})
KEY_FIELDS = frozenset({"key_id", "public_key", "status", "introduced_in_root", "retired_in_root"})
ENVELOPE_FIELDS = frozenset({"envelope_schema", "envelope_id", "lab_id", "root_version", "issuer_id", "key_id",
                             "record_kind", "record_sha256", "subject", "purpose", "signature"})
_NAME = re.compile(r"[a-z][a-z0-9_.:-]{2,127}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_HEX128 = re.compile(r"[0-9a-f]{128}")


class TrustError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _int(value: Any) -> bool:
    return type(value) is int and value >= 1


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def sha256_of(value: Any) -> str:
    """SHA-256 of the lab's canonical encoding; raises TrustError if the value is not canonical."""
    try:
        return _sha(value)
    except IdentityError:
        raise TrustError("NOT_CANONICAL") from None


def key_id(public_key: str) -> str:
    return hashlib.sha256(bytes.fromhex(public_key)).hexdigest()


def public_key_hex(private_key: Ed25519PrivateKey) -> str:
    return private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


# ── Trust root ────────────────────────────────────────────────────────────
def _root_shape(root: Any) -> dict:
    """Index issuers and keys of a well-formed root; TRUST_ROOT_INVALID otherwise."""
    bad = TrustError("TRUST_ROOT_INVALID")
    if type(root) is not dict or set(root) != ROOT_FIELDS or root["root_schema"] != ROOT_SCHEMA:
        raise bad
    if type(root["environment"]) is not str or type(root["lab_id"]) is not str or \
            not _NAME.fullmatch(root["lab_id"]) or not _int(root["root_version"]):
        raise bad
    revoked = root["revoked_envelopes"]
    if type(revoked) is not list or revoked != sorted(set(revoked)) or \
            any(type(e) is not str or not _HEX64.fullmatch(e) for e in revoked):
        raise bad
    issuers, keys = {}, set()
    if type(root["issuers"]) is not list or not root["issuers"]:
        raise bad
    for issuer in root["issuers"]:
        if type(issuer) is not dict or set(issuer) != ISSUER_FIELDS or type(issuer["issuer_id"]) is not str or \
                not _NAME.fullmatch(issuer["issuer_id"]) or issuer["issuer_kind"] not in ISSUER_KINDS or \
                issuer["issuer_id"] in issuers:
            raise bad
        scopes = issuer["scopes"]
        if type(scopes) is not list or not scopes or scopes != sorted(set(scopes)) or \
                any(scope not in KINDS or issuer["issuer_kind"] not in KINDS[scope].issuers for scope in scopes):
            raise bad
        if type(issuer["keys"]) is not list or not issuer["keys"]:
            raise bad
        for key in issuer["keys"]:
            if type(key) is not dict or set(key) != KEY_FIELDS or type(key["public_key"]) is not str or \
                    not _HEX64.fullmatch(key["public_key"]) or key["key_id"] != key_id(key["public_key"]) or \
                    key["key_id"] in keys or key["status"] not in KEY_STATUSES or \
                    not _int(key["introduced_in_root"]) or key["introduced_in_root"] > root["root_version"]:
                raise bad
            retired = key["retired_in_root"]
            if key["status"] == "ACTIVE":
                if retired is not None:
                    raise bad
            elif not _int(retired) or not key["introduced_in_root"] < retired <= root["root_version"]:
                raise bad
            try:
                Ed25519PublicKey.from_public_bytes(bytes.fromhex(key["public_key"]))
            except ValueError:
                raise bad from None
            keys.add(key["key_id"])
        issuers[issuer["issuer_id"]] = issuer
    return issuers


def check_root(root: Any, *, pin_sha256: str, minimum_version: int, lab_id: str) -> dict:
    """Issuers of the pinned root for this lab, or TrustError naming the first failure."""
    try:
        digest = _sha(root)
    except IdentityError:
        raise TrustError("TRUST_ROOT_INVALID") from None
    if type(pin_sha256) is not str or digest != pin_sha256:
        raise TrustError("TRUST_ROOT_PIN_MISMATCH")
    issuers = _root_shape(root)
    if root["environment"] != ENVIRONMENT:
        raise TrustError("TRUST_ROOT_NOT_LAB_TEST")
    if not _int(minimum_version) or root["root_version"] < minimum_version:
        raise TrustError("TRUST_ROOT_ROLLBACK")
    if root["lab_id"] != lab_id:
        raise TrustError("TRUST_ROOT_OTHER_LAB")
    return issuers


# ── Envelopes ─────────────────────────────────────────────────────────────
def _message(envelope: dict) -> bytes:
    return DOMAIN + _canonical({name: value for name, value in envelope.items() if name != "signature"})


def make_envelope(record: dict, *, record_kind: str, lab_id: str, root_version: int, issuer_id: str,
                  private_key: Ed25519PrivateKey, envelope_id: str) -> dict:
    """Sign a statement about one record (lab and tests only; keys are LAB_TEST keys)."""
    kind = KINDS[record_kind]
    envelope = {"envelope_schema": ENVELOPE_SCHEMA, "envelope_id": envelope_id, "lab_id": lab_id,
                "root_version": root_version, "issuer_id": issuer_id,
                "key_id": key_id(public_key_hex(private_key)), "record_kind": record_kind,
                "record_sha256": sha256_of(record),
                "subject": {"agent_id": record[kind.subject[0]], "agent_spec_id": record[kind.subject[1]]},
                "purpose": kind.purpose}
    envelope["signature"] = private_key.sign(_message(envelope)).hex()
    return envelope


def _envelope_shape(envelope: Any) -> str | None:
    if envelope is None:
        return "NOT_AUTHENTICATED"
    if type(envelope) is dict and "envelope_schema" in envelope and envelope["envelope_schema"] != ENVELOPE_SCHEMA:
        return "UNKNOWN_ENVELOPE_SCHEMA"
    if type(envelope) is not dict or set(envelope) != ENVELOPE_FIELDS:
        return "ENVELOPE_INVALID"
    subject = envelope["subject"]
    names = ("envelope_id", "lab_id", "issuer_id", "key_id", "record_kind", "record_sha256", "purpose", "signature")
    if any(type(envelope[name]) is not str for name in names) or not _int(envelope["root_version"]) or \
            type(subject) is not dict or set(subject) != {"agent_id", "agent_spec_id"} or \
            any(type(v) is not str or not _HEX64.fullmatch(v) for v in subject.values()):
        return "ENVELOPE_INVALID"
    if not all(_HEX64.fullmatch(envelope[name]) for name in ("envelope_id", "key_id", "record_sha256")) or \
            not _HEX128.fullmatch(envelope["signature"]) or not _NAME.fullmatch(envelope["lab_id"]) or \
            not _NAME.fullmatch(envelope["issuer_id"]):
        return "ENVELOPE_INVALID"
    try:
        _canonical(envelope)
    except IdentityError:
        return "ENVELOPE_INVALID"
    if envelope["record_kind"] not in KINDS:
        return "UNKNOWN_RECORD_KIND"
    return None


def _status(codes: list[str], evaluated: bool) -> str:
    return "FAIL" if codes else ("PASS" if evaluated else "NOT_EVALUATED")


def verify_envelope(envelope: Any, record: Any, root: Any, *, pin_sha256: str, minimum_version: int, lab_id: str,
                    record_kind: str, subject: dict) -> dict:
    """Per-envelope verdict: integrity, authenticity and authorization, each PASS, FAIL or NOT_EVALUATED."""
    integrity, authenticity, authorization = [], [], []
    shape = _envelope_shape(envelope)
    issuers = None
    try:
        issuers = check_root(root, pin_sha256=pin_sha256, minimum_version=minimum_version, lab_id=lab_id)
    except TrustError as exc:
        authenticity.append(exc.code)
    if shape is not None:
        integrity.append(shape)
        return _verdict(envelope, integrity, authenticity, authorization, False, False, False)
    kind = KINDS[envelope["record_kind"]]
    # Integrity: exactly the record the envelope names.
    try:
        if type(record) is not dict:
            raise IdentityError("LAB_RECORD_NOT_CANONICAL")
        if _sha(record) != envelope["record_sha256"]:
            integrity.append("RECORD_HASH_MISMATCH")
    except IdentityError:
        integrity.append("RECORD_NOT_CANONICAL")
    # Authenticity: a valid key of the pinned root signed this envelope.
    issuer = None
    if issuers is not None:
        issuer = issuers.get(envelope["issuer_id"])
        key = None if issuer is None else next((k for k in issuer["keys"] if k["key_id"] == envelope["key_id"]),
                                                None)
        version = envelope["root_version"]
        if issuer is None:
            authenticity.append("UNKNOWN_ISSUER")
        elif key is None:
            authenticity.append("UNKNOWN_KEY")
        else:
            if version > root["root_version"]:
                authenticity.append("ENVELOPE_FROM_FUTURE_ROOT")
            if version < key["introduced_in_root"]:
                authenticity.append("KEY_NOT_YET_VALID")
            if key["status"] == "REVOKED":
                authenticity.append("KEY_REVOKED")
            elif key["status"] == "RETIRED" and version >= key["retired_in_root"]:
                authenticity.append("KEY_RETIRED")
            try:
                Ed25519PublicKey.from_public_bytes(bytes.fromhex(key["public_key"])).verify(
                    bytes.fromhex(envelope["signature"]), _message(envelope))
            except InvalidSignature:
                authenticity.append("SIGNATURE_INVALID")
        if envelope["envelope_id"] in root["revoked_envelopes"]:
            authenticity.append("ENVELOPE_REVOKED")
    # Authorization: this issuer may say this, here, about this subject.
    if envelope["lab_id"] != lab_id:
        authorization.append("AUDIENCE_MISMATCH")
    if envelope["record_kind"] != record_kind or type(record) is not dict or \
            record.get(kind.schema_field) != envelope["record_kind"]:
        authorization.append("RECORD_KIND_MISMATCH")
    if envelope["purpose"] != kind.purpose:
        authorization.append("PURPOSE_MISMATCH")
    claimed = None if type(record) is not dict else \
        {"agent_id": record.get(kind.subject[0]), "agent_spec_id": record.get(kind.subject[1])}
    if envelope["subject"] != subject or claimed != envelope["subject"]:
        authorization.append("SUBJECT_MISMATCH")
    if issuer is not None:
        if envelope["record_kind"] not in issuer["scopes"]:
            authorization.append("SCOPE_NOT_GRANTED")
        if kind.author is not None and (type(record) is not dict or
                                        record.get(kind.author[0]) != issuer["issuer_kind"] or
                                        record.get(kind.author[1]) != issuer["issuer_id"]):
            authorization.append("AUTHOR_NOT_ISSUER")
    evaluated = issuers is not None
    return _verdict(envelope, integrity, authenticity, authorization, True, evaluated, issuer is not None)


def _verdict(envelope, integrity, authenticity, authorization, integrity_done, authenticity_done,
             authorization_done) -> dict:
    properties = {"integrity": _status(integrity, integrity_done),
                  "authenticity": _status(authenticity, authenticity_done),
                  "authorization": _status(authorization, authorization_done)}
    return {"verdict_schema": VERDICT_SCHEMA, **properties,
            "attested": all(value == "PASS" for value in properties.values()),
            "failures": [*integrity, *authenticity, *authorization],
            "envelope_id": envelope.get("envelope_id") if type(envelope) is dict else None}


def verify_bundle(items: list, required: list, root: Any, *, pin_sha256: str, minimum_version: int,
                  lab_id: str) -> dict:
    """Accept a decision only if each required (record_kind, subject) has exactly one attested envelope
    and no envelope is unexpected. ``items`` are (envelope, record) pairs."""
    completeness, verdicts = [], []
    matched = set()
    for record_kind, subject in required:
        hits = [i for i, (envelope, _) in enumerate(items)
                if _envelope_shape(envelope) is None and envelope["record_kind"] == record_kind
                and envelope["subject"] == subject]
        if not hits:
            completeness.append("ATTESTATION_MISSING")
            continue
        if len(hits) > 1:
            completeness.append("ATTESTATION_DUPLICATED")
        matched.update(hits)
        for i in hits:
            envelope, record = items[i]
            verdicts.append(verify_envelope(envelope, record, root, pin_sha256=pin_sha256,
                                            minimum_version=minimum_version, lab_id=lab_id,
                                            record_kind=record_kind, subject=subject))
    if len(matched) != len(items):
        completeness.append("ATTESTATION_UNEXPECTED")
    if not required:
        completeness.append("ATTESTATION_MISSING")
    summary = {name: ("FAIL" if any(v[name] == "FAIL" for v in verdicts) else
                      "PASS" if verdicts and all(v[name] == "PASS" for v in verdicts) else "NOT_EVALUATED")
               for name in ("integrity", "authenticity", "authorization")}
    summary["completeness"] = "FAIL" if completeness else "PASS"
    return {"verdict_schema": VERDICT_SCHEMA, **summary,
            "accepted": all(value == "PASS" for value in summary.values()),
            "failures": [*completeness, *(code for v in verdicts for code in v["failures"])],
            "envelopes": verdicts}


# ── Single-use envelopes ──────────────────────────────────────────────────
def consume(ledger: Path, envelope: dict) -> None:
    """Record a single-use envelope as spent (append-only, fsynced); refuse a replay or a reused id."""
    if _envelope_shape(envelope) is not None or not KINDS[envelope["record_kind"]].single_use:
        raise TrustError("NOT_SINGLE_USE")
    digest = _sha(envelope)
    fd = os.open(ledger, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        with open(ledger, "rb") as handle:
            lines = handle.read().splitlines()
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                raise TrustError("LEDGER_CORRUPT") from None
            if type(entry) is not dict or entry.get("ledger_schema") != LEDGER_SCHEMA:
                raise TrustError("LEDGER_CORRUPT")
            if entry.get("envelope_id") == envelope["envelope_id"]:
                raise TrustError("ENVELOPE_REPLAYED" if entry.get("envelope_sha256") == digest
                                 else "ENVELOPE_ID_REUSED")
        entry = {"ledger_schema": LEDGER_SCHEMA, "envelope_id": envelope["envelope_id"], "envelope_sha256": digest}
        os.write(fd, json.dumps(entry, sort_keys=True).encode() + b"\n")
        os.fsync(fd)
    finally:
        os.close(fd)
