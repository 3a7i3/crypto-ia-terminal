"""Owned temporary SQLite and synthetic tickets; no system service execution."""

import hashlib
import json
import multiprocessing

import pytest

from observability.frontend_deploy_request import BINDINGS
from observability.frontend_gateway_lab import LabLedger

BUNDLE = b"synthetic frontend bytes, never executable"


def documents():
    ticket = {
        "ticket_id": "a" * 32,
        "actor": "chatgpt-ro",
        "operator": "mathieu",
        "audience": "frontend-deploy-gateway",
        "operation": "activate_frontend",
        "service": "crypto-operator-web.service",
        "source_sha": "b" * 40,
        "source_merge_sha": "c" * 40,
        "previous_release_sha": "d" * 40,
        "bundle_sha256": hashlib.sha256(BUNDLE).hexdigest(),
        "approved": True,
        "issued_at": 100,
        "expires_at": 200,
    }
    return json.dumps(ticket).encode(), json.dumps(
        {k: ticket[k] for k in BINDINGS}
    ).encode()


def race_worker(root, request, ready, go, results):
    ledger = LabLedger(root)
    ready.put(True)
    if not go.wait(5):
        results.put("TIMEOUT")
        return
    try:
        results.put(ledger.claim_no_execution(request, BUNDLE, now=150)["state"])
    except ValueError as exc:
        results.put(str(exc))


def test_two_processes_only_one_claim(tmp_path):
    root = tmp_path / "race"
    ticket, request = documents()
    LabLedger.create(root).admit_synthetic(ticket, now=150)
    context = multiprocessing.get_context("spawn")
    ready, results, go = context.Queue(), context.Queue(), context.Event()
    workers = [
        context.Process(target=race_worker, args=(root, request, ready, go, results))
        for _ in range(2)
    ]
    try:
        for worker in workers:
            worker.start()
        assert ready.get(timeout=10) and ready.get(timeout=10)
        go.set()
        outcomes = sorted([results.get(timeout=10), results.get(timeout=10)])
        assert outcomes == ["CONSUMED_NO_EXECUTION", "UNKNOWN_OR_UNAVAILABLE_TICKET"]
        for worker in workers:
            worker.join(timeout=5)
            assert worker.exitcode == 0
        receipt = LabLedger(root).receipt("a" * 32)
        assert receipt["privileged_execution"] is False
        assert receipt["ticket_authenticity"] == "NOT_VERIFIED"
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)
        ready.close()
        results.close()


def test_consumption_survives_reopen_and_replay_is_refused(tmp_path):
    ticket, request = documents()
    ledger = LabLedger.create(tmp_path / "reopen")
    ledger.admit_synthetic(ticket, now=150)
    claimed = ledger.claim_no_execution(request, BUNDLE, now=150)
    reopened = LabLedger(ledger.root)
    assert reopened.receipt("a" * 32) == claimed
    with pytest.raises(ValueError, match="UNAVAILABLE"):
        reopened.claim_no_execution(request, BUNDLE, now=150)


@pytest.mark.parametrize("failure", ["unknown", "revoked", "expired", "bundle"])
def test_bad_claim_never_creates_receipt(tmp_path, failure):
    ticket, request = documents()
    ledger = LabLedger.create(tmp_path / failure)
    if failure != "unknown":
        ledger.admit_synthetic(ticket, now=150)
    if failure == "revoked":
        ledger.revoke_synthetic("a" * 32)
    with pytest.raises(ValueError):
        ledger.claim_no_execution(
            request,
            b"substitution" if failure == "bundle" else BUNDLE,
            now=200 if failure == "expired" else 150,
        )
    assert ledger.receipt("a" * 32) is None
    if failure == "bundle":
        assert (
            ledger.claim_no_execution(request, BUNDLE, now=150)["state"]
            == "CONSUMED_NO_EXECUTION"
        )


def test_existing_directory_is_not_adopted(tmp_path):
    with pytest.raises(FileExistsError):
        LabLedger.create(tmp_path)
