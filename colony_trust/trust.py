"""Envelopes that authenticate colony lab records (schema colony-trust.envelope/0).

A verdict keeps four properties apart: integrity (this is the record the
envelope names), authenticity (a key of the pinned trust root signed it),
authorization (that issuer may say this, for this lab and subject) and
completeness (every attestation a decision needs is there, once). A single
envelope is at most "attested" (the first three); only verify_bundle()
evaluates completeness and can accept; it also judges the replay of
single-use envelopes against a ledger and spends them only on acceptance. A
property that could not be evaluated is NOT_EVALUATED, never PASS.

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
import stat
from contextlib import contextmanager
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
OPERATION_LEDGER_SCHEMA = "colony-trust.consumed/1"
ENVIRONMENT = "LAB_TEST"
DOMAIN = ENVELOPE_SCHEMA.encode() + b"\x00"
EXTERNAL = frozenset({"EXTERNAL_HUMAN", "EXTERNAL_REVIEW_PROCESS"})
ISSUER_KINDS = EXTERNAL | {"LAB_OPERATOR"}
KEY_STATUSES = frozenset({"ACTIVE", "RETIRED", "REVOKED"})
MAX_VERSION = 2**31 - 1


class Kind:
    def __init__(self, schema_field: str, purpose: str, issuers: frozenset[str], subject: tuple[str, str],
                 author: tuple[str, str] | None, single_use: bool) -> None:
        self.schema_field, self.purpose, self.issuers = schema_field, purpose, issuers
        self.subject, self.author, self.single_use = subject, author, single_use


KINDS = {
    "colony-admission.attestation-statement/0": Kind(
        "statement_schema", "QUALIFICATION_STATEMENT_ATTESTED", EXTERNAL,
        ("subject_agent_id", "subject_agent_spec_id"), ("issuer_kind", "issuer_id"), False),
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
LEDGER_FIELDS = frozenset({"ledger_schema", "issuer_id", "envelope_id", "envelope_sha256"})
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
    return type(value) is int and 1 <= value <= MAX_VERSION


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def sha256_of(value: Any) -> str:
    """SHA-256 of the lab's canonical encoding; raises TrustError if the value is not canonical."""
    try:
        return _sha(value)
    except IdentityError:
        raise TrustError("NOT_CANONICAL") from None


def loads(raw: bytes) -> Any:
    """Parse bytes that are exactly the lab's canonical encoding of a value; NOT_CANONICAL otherwise.

    Duplicate keys, NaN, whitespace or any other spelling of the same value are refused, so every
    reader of a stored record or envelope sees the value whose hash is verified."""
    try:
        value = json.loads(raw.decode("utf-8"))
        if _canonical(value) == raw:
            return value
    except (AttributeError, ValueError, TypeError, RecursionError, IdentityError):
        pass
    raise TrustError("NOT_CANONICAL")


# ── Ed25519 public keys (RFC 8032 §5.1.3) ─────────────────────────────────
_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _add(a: tuple, b: tuple) -> tuple:
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    e, f = (y1 - x1) * (y2 - x2) % _P, (y1 + x1) * (y2 + x2) % _P
    g, h = 2 * _D * t1 * t2 % _P, 2 * z1 * z2 % _P
    e, f, g, h = f - e, h - g, h + g, f + e
    return e * f % _P, g * h % _P, f * g % _P, e * h % _P


def _is_identity(point: tuple) -> bool:
    x, y, z, _ = point
    return x % _P == 0 and (y - z) % _P == 0


def prime_order_key(raw: bytes) -> bool:
    """True only for a canonical encoding of a point of the prime-order subgroup other than the identity.

    The library accepts any 32 bytes; a small-order key such as the identity verifies forged signatures."""
    if type(raw) is not bytes or len(raw) != 32:
        return False
    y, sign = int.from_bytes(raw, "little") & ((1 << 255) - 1), raw[31] >> 7
    if y >= _P:
        return False
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P or (x == 0 and sign):
        return False
    if x & 1 != sign:
        x = _P - x
    point, result = (x, y, 1, x * y % _P), (0, 1, 1, 0)
    for bit in bin(_L)[2:]:
        result = _add(result, result)
        if bit == "1":
            result = _add(result, point)
    return not _is_identity(point) and _is_identity(result)


def key_id(public_key: str) -> str:
    """SHA-256 of a raw public key given in hex; KEY_INVALID for anything else."""
    if type(public_key) is not str or not _HEX64.fullmatch(public_key):
        raise TrustError("KEY_INVALID")
    return hashlib.sha256(bytes.fromhex(public_key)).hexdigest()


def public_key_hex(private_key: Ed25519PrivateKey) -> str:
    return private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


# ── Trust root ────────────────────────────────────────────────────────────
def _root_shape(root: Any) -> dict:
    """Index issuers and keys of a well-formed root; TRUST_ROOT_INVALID otherwise, never another error."""
    try:
        return _root_index(root)
    except (TypeError, ValueError, KeyError, RecursionError) as exc:
        if isinstance(exc, TrustError):
            raise
        raise TrustError("TRUST_ROOT_INVALID") from None


def _root_index(root: Any) -> dict:
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
            if not prime_order_key(bytes.fromhex(key["public_key"])):
                raise bad
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
        if _sha(record) != envelope["record_sha256"]:  # _canonical bounds depth and size
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


def _bundle_shape(items: Any, required: Any) -> bool:
    if type(items) is not list or type(required) is not list:
        return False
    if any(type(item) not in {list, tuple} or len(item) != 2 for item in items):
        return False
    pairs = []
    for need in required:
        if type(need) not in {list, tuple} or len(need) != 2 or type(need[0]) is not str or \
                type(need[1]) is not dict or set(need[1]) != {"agent_id", "agent_spec_id"} or \
                any(type(v) is not str for v in need[1].values()):
            return False
        pairs.append((need[0], need[1]["agent_id"], need[1]["agent_spec_id"]))
    return len(pairs) == len(set(pairs))


def verify_bundle(items: Any, required: Any, root: Any, *, pin_sha256: str, minimum_version: int, lab_id: str,
                  ledger: Path | None = None) -> dict:
    """Accept a decision only if each required (record_kind, subject) has exactly one attested envelope,
    no envelope is unexpected and no single-use envelope was spent before. ``items`` are (envelope, record)
    pairs. Single-use envelopes need ``ledger``; they are spent there only when the bundle is accepted."""
    return _evaluate_bundle(items, required, root, pin_sha256=pin_sha256,
                            minimum_version=minimum_version, lab_id=lab_id, ledger=ledger)


def _evaluate_bundle(items, required, root, *, pin_sha256, minimum_version, lab_id,
                     ledger=None, spend=True, replay=True, record_keys=False):
    shape = _operation_bundle_shape if record_keys else _bundle_shape
    if not shape(items, required):
        return {"verdict_schema": VERDICT_SCHEMA, "integrity": "NOT_EVALUATED", "authenticity": "NOT_EVALUATED",
                "authorization": "NOT_EVALUATED", "completeness": "FAIL", "accepted": False,
                "failures": ["BUNDLE_INVALID"], "envelopes": []}
    completeness, verdicts = [], []
    matched = set()
    for need in required:
        record_kind, subject = need[:2]
        hits = [i for i, (envelope, _) in enumerate(items)
                if _envelope_shape(envelope) is None and envelope["record_kind"] == record_kind
                and envelope["subject"] == subject
                and (not record_keys or envelope["record_sha256"] == need[2])]
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
    single = [items[i][0] for i in sorted(matched) if KINDS[items[i][0]["record_kind"]].single_use]
    replay_codes = []
    if single and replay:
        if ledger is None:
            replay_codes.append("LEDGER_REQUIRED")
        else:
            accept = all(value == "PASS" for value in summary.values())
            try:
                replay_codes = _spend(ledger, single, commit=accept and spend, private=record_keys)
            except TrustError as exc:
                replay_codes = [exc.code]
            except (OSError, TypeError, ValueError):
                replay_codes = ["LEDGER_CORRUPT"]
    if replay_codes:
        summary["authorization"] = "FAIL"
    return {"verdict_schema": VERDICT_SCHEMA, **summary,
            "accepted": all(value == "PASS" for value in summary.values()),
            "failures": [*completeness, *(code for v in verdicts for code in v["failures"]), *replay_codes],
            "envelopes": verdicts}


# ── Single-use envelopes ──────────────────────────────────────────────────
@contextmanager
def _locked(ledger: Path, *, create: bool, private=False):
    """The ledger, locked; None when it does not exist and nothing will be written."""
    if not isinstance(ledger, Path):
        raise TrustError("LEDGER_CORRUPT")
    flags = os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_CREAT if create else 0)
    try:
        fd = os.open(ledger, flags, 0o600)
    except FileNotFoundError:
        if create:
            raise
        yield None
        return
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or \
                (private and stat.S_IMODE(info.st_mode) != 0o600):
            raise TrustError("LEDGER_CORRUPT")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield fd
    finally:
        os.close(fd)


def _read(fd: int) -> dict:
    """Spent envelopes by (issuer_id, envelope_id); LEDGER_CORRUPT unless every line is a canonical entry."""
    return {key: entry["envelope_sha256"] for key, entry in _read_entries(fd).items()}


def _read_entries(fd: int) -> dict:
    chunks = []
    os.lseek(fd, 0, os.SEEK_SET)
    while chunk := os.read(fd, 65_536):
        chunks.append(chunk)
    raw = b"".join(chunks)
    if raw and not raw.endswith(b"\n"):
        raise TrustError("LEDGER_CORRUPT")
    spent = {}
    for line in raw.split(b"\n")[:-1]:
        try:
            entry = loads(line)
        except TrustError:
            raise TrustError("LEDGER_CORRUPT") from None
        if type(entry) is not dict:
            raise TrustError("LEDGER_CORRUPT")
        schema = entry.get("ledger_schema")
        fields = LEDGER_FIELDS | {"operation_sha256"} if schema == OPERATION_LEDGER_SCHEMA else LEDGER_FIELDS
        if set(entry) != fields or schema not in {LEDGER_SCHEMA, OPERATION_LEDGER_SCHEMA} or \
                any(type(entry[n]) is not str for n in fields) or \
                not _NAME.fullmatch(entry["issuer_id"]) or \
                not all(_HEX64.fullmatch(entry[n]) for n in ("envelope_id", "envelope_sha256")) or \
                (schema == OPERATION_LEDGER_SCHEMA and not _HEX64.fullmatch(entry["operation_sha256"])):
            raise TrustError("LEDGER_CORRUPT")
        key = (entry["issuer_id"], entry["envelope_id"])
        if key in spent:
            raise TrustError("LEDGER_CORRUPT")
        spent[key] = entry
    return spent


def _write(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        count = os.write(fd, view)
        if count <= 0:
            raise OSError("ledger write made no progress")
        view = view[count:]
    os.fsync(fd)


def _spend(ledger: Path, envelopes: list, *, commit: bool, private=False) -> list:
    """Replay codes for single-use envelopes; with ``commit`` and none, append them (one locked section)."""
    keys = [(envelope["issuer_id"], envelope["envelope_id"]) for envelope in envelopes]
    if len(set(keys)) != len(keys):  # the same key twice in one bundle: refused before the ledger is touched
        return ["ENVELOPE_ID_REUSED"]
    with _locked(ledger, create=commit, private=private) as fd:
        spent, codes, lines = ({} if fd is None else _read(fd)), [], []
        for envelope in envelopes:
            key, digest = (envelope["issuer_id"], envelope["envelope_id"]), _sha(envelope)
            if key in spent:
                codes.append("ENVELOPE_REPLAYED" if spent[key] == digest else "ENVELOPE_ID_REUSED")
                continue
            lines.append(_canonical({"ledger_schema": LEDGER_SCHEMA, "issuer_id": key[0], "envelope_id": key[1],
                                     "envelope_sha256": digest}) + b"\n")
        if commit and not codes:
            _write(fd, b"".join(lines))
        return codes


def _operation_bundle_shape(items, required):
    if type(items) is not list or type(required) is not list:
        return False
    if any(type(n) not in {list, tuple} or len(n) != 3 or type(n[2]) is not str or
           not _HEX64.fullmatch(n[2]) for n in required):
        return False
    if any(not _bundle_shape(items, [n[:2]]) for n in required):
        return False
    keys = [(n[0], n[1]["agent_id"], n[1]["agent_spec_id"], n[2]) for n in required]
    return len(keys) == len(set(keys)) and all(
        type(i) in {tuple, list} and len(i) == 2 for i in items)


def _refuse(verdict, code):
    return {**verdict, "accepted": False, "authorization": "FAIL",
            "failures": [*verdict["failures"], code]}


def check_bundle(items: Any, required: Any, root: Any, *, pin_sha256: str, minimum_version: int,
                 lab_id: str, ledger: Path | None = None) -> dict:
    """Read-only full verification with record-hash completeness keys. Never reserves an envelope."""
    return _evaluate_bundle(items, required, root, pin_sha256=pin_sha256,
                            minimum_version=minimum_version, lab_id=lab_id,
                            ledger=ledger, spend=False, record_keys=True)


def _operation(value):
    if type(value) is not str or not _HEX64.fullmatch(value):
        raise TrustError("OPERATION_INVALID")


def _sync_parent(path):
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def consume(items: Any, required: Any, root: Any, *, pin_sha256: str, minimum_version: int,
            lab_id: str, ledger: Path, operation_sha256: str) -> dict:
    """Verify and consume fresh admissions under one lock; exact resumes are NOT new acceptances.

    Only a controller can decide whether the operation is COMMITTED. A failed durable write is
    reported distinctly and must be recorded outside this ledger by that controller.
    """
    # Snapshot caller-owned data before verification. Each record is bounded by _canonical.
    try:
        _operation(operation_sha256)
        if not _operation_bundle_shape(items, required):
            raise TrustError("BUNDLE_INVALID")
        items = [(loads(_canonical(e)), loads(_canonical(r))) for e, r in items]
        required = [(k, loads(_canonical(s)), digest) for k, s, digest in required]
        root = loads(_canonical(root))
    except (TrustError, IdentityError, TypeError, ValueError) as exc:
        code = exc.code if isinstance(exc, TrustError) else "BUNDLE_INVALID"
        return {"verdict_schema": VERDICT_SCHEMA, "accepted": False, "integrity": "NOT_EVALUATED",
                "authenticity": "NOT_EVALUATED", "authorization": "FAIL", "completeness": "FAIL",
                "failures": [code], "envelopes": [], "consumption": "NOT_CONSUMED"}

    def evaluate():
        return _evaluate_bundle(items, required, root, pin_sha256=pin_sha256,
                                minimum_version=minimum_version, lab_id=lab_id,
                                replay=False, record_keys=True)

    verdict = {**evaluate(), "consumption": "NOT_CONSUMED"}
    if not verdict["accepted"]:
        return verdict  # no file creation for an invalid bundle
    singles = [e for e, _ in items if KINDS[e["record_kind"]].single_use]
    if not singles:
        return _refuse(verdict, "ADMISSION_REQUIRED")
    keys = [(e["issuer_id"], e["envelope_id"]) for e in singles]
    if len(set(keys)) != len(keys):
        return _refuse(verdict, "ENVELOPE_ID_REUSED")
    # An invalid path is rejected before attempting an open (including embedded NUL).
    if not isinstance(ledger, Path):
        return _refuse(verdict, "LEDGER_CORRUPT")
    try:
        with _locked(ledger, create=True, private=True) as fd:
            verdict = {**evaluate(), "consumption": "NOT_CONSUMED"}
            if not verdict["accepted"]:
                return verdict
            spent = _read_entries(fd)
            lines, own = [], 0
            for envelope, key in zip(singles, keys):
                digest = _sha(envelope)
                previous = spent.get(key)
                if previous is not None:
                    if previous["envelope_sha256"] != digest:
                        return _refuse(verdict, "ENVELOPE_ID_REUSED")
                    if previous.get("operation_sha256") != operation_sha256:
                        return _refuse(verdict, "ENVELOPE_REPLAYED")
                    own += 1
                else:
                    lines.append(_canonical({"ledger_schema": OPERATION_LEDGER_SCHEMA,
                                             "issuer_id": key[0], "envelope_id": key[1],
                                             "envelope_sha256": digest,
                                             "operation_sha256": operation_sha256}) + b"\n")
            if own:
                if lines:
                    return _refuse(verdict, "OPERATION_STATE_INCONSISTENT")
                return {**verdict, "accepted": False, "consumption": "CONSUMED_BY_THIS_OPERATION"}
            try:
                _write(fd, b"".join(lines))
                _sync_parent(ledger)
            except OSError:
                return _refuse(verdict, "LEDGER_DURABILITY_UNKNOWN")
            return {**verdict, "consumption": "CONSUMED"}
    except TrustError as exc:
        return _refuse(verdict, exc.code)
    except (OSError, ValueError, TypeError):
        return _refuse(verdict, "LEDGER_CORRUPT")


def verify_consumed(envelope: Any, ledger: Path, operation_sha256: str) -> dict:
    """Consumption evidence only: never proves authenticity or a controller COMMITTED state."""
    result = {"consumed": False, "failures": []}
    try:
        _operation(operation_sha256)
        if _envelope_shape(envelope) is not None or not KINDS[envelope["record_kind"]].single_use:
            raise TrustError("ENVELOPE_INVALID")
        with _locked(ledger, create=False, private=True) as fd:
            entries = {} if fd is None else _read_entries(fd)
            entry = entries.get((envelope["issuer_id"], envelope["envelope_id"]))
            if entry is None or entry["envelope_sha256"] != _sha(envelope) or \
                    entry.get("operation_sha256") != operation_sha256:
                raise TrustError("CONSUMPTION_NOT_FOR_OPERATION")
        return {"consumed": True, "failures": []}
    except TrustError as exc:
        return {**result, "failures": [exc.code]}
    except (OSError, ValueError, TypeError):
        return {**result, "failures": ["LEDGER_CORRUPT"]}


def classify_envelope(*args, **kwargs) -> dict:
    """Keep genuine-but-revoked separate from authentication; it can only restrict privileges."""
    verdict = verify_envelope(*args, **kwargs)
    genuine = (verdict["integrity"] == verdict["authorization"] == "PASS" and
               bool(verdict["failures"]) and
               set(verdict["failures"]) <= {"KEY_REVOKED", "ENVELOPE_REVOKED"})
    return {**verdict, "genuine_but_revoked": genuine}
