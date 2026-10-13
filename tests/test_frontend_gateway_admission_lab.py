"""Signed admission and atomic claim, synthetic ephemeral keys only."""

import hashlib
import json
import multiprocessing

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from observability.frontend_deploy_request import BINDINGS
from observability.frontend_gateway_admission_lab import SignedLabLedger
from observability.frontend_ticket_signature_lab import signing_bytes

BUNDLE = b"synthetic frontend bytes, never executable"
PREVIOUS = "d" * 40
KNOWN = frozenset({PREVIOUS})


def pin_of(key):
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


def make(key, operation="activate_frontend", ticket_id="a" * 32):
    ticket = dict(
        ticket_id=ticket_id, actor="chatgpt-ro", operator="mathieu",
        audience="frontend-deploy-gateway", operation=operation,
        service="crypto-operator-web.service", source_sha="b" * 40,
        source_merge_sha="c" * 40, previous_release_sha=PREVIOUS,
        bundle_sha256=hashlib.sha256(BUNDLE).hexdigest(),
        approved=True, issued_at=100, expires_at=200,
    )
    env = {"ticket": ticket, "signature": key.sign(signing_bytes(ticket)).hex()}
    return json.dumps(env).encode(), json.dumps({k: ticket[k] for k in BINDINGS}).encode()


@pytest.fixture
def ledger(tmp_path):
    return SignedLabLedger.create(tmp_path / "lab")


def kw(key, **extra):
    base = dict(now=150, pinned_public_key=pin_of(key), peer_fixture="chatgpt-ro",
                known_releases=KNOWN)
    base.update(extra)
    return base


def test_signed_claim_consumes_once(ledger):
    key = Ed25519PrivateKey.generate()
    env, req = make(key)
    ledger.admit_signed(env, pinned_public_key=pin_of(key), peer_fixture="chatgpt-ro", now=150)
    receipt = ledger.claim_signed_no_execution(req, BUNDLE, **kw(key))
    assert receipt["state"] == "CONSUMED_NO_EXECUTION"
    assert receipt["operator_key_custody"] == "NOT_PROVEN"
    assert receipt["privileged_execution"] is False
    with pytest.raises(ValueError, match="UNKNOWN_OR_UNAVAILABLE_TICKET"):
        ledger.claim_signed_no_execution(req, BUNDLE, **kw(key))


def test_unsigned_or_foreign_key_not_admitted(ledger):
    key, attacker = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    env, _ = make(attacker)
    with pytest.raises(ValueError, match="SIGNATURE_MISMATCH"):
        ledger.admit_signed(env, pinned_public_key=pin_of(key), peer_fixture="chatgpt-ro", now=150)


def test_row_tampered_after_admission_refused_at_claim(ledger):
    key = Ed25519PrivateKey.generate()
    env, req = make(key)
    ledger.admit_signed(env, pinned_public_key=pin_of(key), peer_fixture="chatgpt-ro", now=150)
    forged = json.loads(env)
    forged["ticket"]["expires_at"] = 3000
    with ledger._connect() as db:
        db.execute("UPDATE tickets SET document=?", (json.dumps(forged).encode(),))
    with pytest.raises(ValueError):
        ledger.claim_signed_no_execution(req, BUNDLE, **kw(key))
    assert ledger.receipt("a" * 32) is None


def test_failed_checks_leave_ticket_reusable(ledger):
    key = Ed25519PrivateKey.generate()
    env, req = make(key)
    ledger.admit_signed(env, pinned_public_key=pin_of(key), peer_fixture="chatgpt-ro", now=150)
    with pytest.raises(ValueError, match="BUNDLE_BYTES_MISMATCH"):
        ledger.claim_signed_no_execution(req, b"other", **kw(key))
    with pytest.raises(ValueError, match="UNKNOWN_PREVIOUS_RELEASE"):
        ledger.claim_signed_no_execution(req, BUNDLE, **kw(key, known_releases=frozenset()))
    with pytest.raises(ValueError, match="REVOKED_TICKET"):
        ledger.claim_signed_no_execution(req, BUNDLE, **kw(key, revoked=frozenset({"a" * 32})))
    with pytest.raises(ValueError, match="PEER_FIXTURE_MISMATCH"):
        ledger.claim_signed_no_execution(req, BUNDLE, **kw(key, peer_fixture="root"))
    assert ledger.claim_signed_no_execution(req, BUNDLE, **kw(key))["state"] == "CONSUMED_NO_EXECUTION"


def test_rollback_limited_to_known_previous_release(ledger):
    key = Ed25519PrivateKey.generate()
    env, req = make(key, operation="rollback_frontend")
    ledger.admit_signed(env, pinned_public_key=pin_of(key), peer_fixture="chatgpt-ro", now=150)
    with pytest.raises(ValueError, match="UNKNOWN_PREVIOUS_RELEASE"):
        ledger.claim_signed_no_execution(req, BUNDLE, **kw(key, known_releases=frozenset({"e" * 40})))


def race(root, req, pin, ready, go, out):
    led = SignedLabLedger(root)
    ready.put(True)
    go.wait(5)
    try:
        out.put(led.claim_signed_no_execution(
            req, BUNDLE, now=150, pinned_public_key=pin, peer_fixture="chatgpt-ro",
            known_releases=KNOWN)["state"])
    except ValueError as exc:
        out.put(str(exc))


def test_two_processes_one_signed_claim(ledger):
    key = Ed25519PrivateKey.generate()
    env, req = make(key)
    ledger.admit_signed(env, pinned_public_key=pin_of(key), peer_fixture="chatgpt-ro", now=150)
    ctx = multiprocessing.get_context("spawn")
    ready, out, go = ctx.Queue(), ctx.Queue(), ctx.Event()
    procs = [ctx.Process(target=race, args=(ledger.root, req, pin_of(key), ready, go, out))
             for _ in range(2)]
    for p in procs:
        p.start()
    for _ in procs:
        ready.get(timeout=10)
    go.set()
    results = sorted(out.get(timeout=10) for _ in procs)
    for p in procs:
        p.join(10)
    assert results == ["CONSUMED_NO_EXECUTION", "UNKNOWN_OR_UNAVAILABLE_TICKET"]
