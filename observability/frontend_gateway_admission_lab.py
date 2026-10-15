"""Synthetic composition of pinned signature check and atomic single use.

Lab only: no broker, executor or authority. The verifier pin, clock, peer value
and known-release set are caller-supplied fixtures, not trusted system sources.
"""

from __future__ import annotations

import hashlib
import json

from observability.frontend_deploy_request import BINDINGS, decode_document
from observability.frontend_gateway_lab import SCOPE, LabLedger
from observability.frontend_ticket_signature_lab import verify_signed_fixture


class SignedLabLedger(LabLedger):
    def admit_signed(
        self, raw: bytes, *, pinned_public_key: bytes, peer_fixture: str, now: int
    ) -> None:
        """Store only envelopes that verify against the verifier's pin."""
        ticket = decode_document(raw).get("ticket")
        if type(ticket) is not dict:
            raise ValueError("INVALID_ENVELOPE_KEYS")
        request = {key: ticket.get(key) for key in BINDINGS}
        verify_signed_fixture(
            raw, request, pinned_public_key=pinned_public_key,
            peer_fixture=peer_fixture, now=now, revoked=frozenset(),
        )
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] >= 128:
                raise ValueError("LAB_QUOTA_FULL")
            db.execute(
                "INSERT INTO tickets VALUES (?, ?, 'APPROVED')",
                (ticket["ticket_id"], raw),
            )

    def claim_signed_no_execution(
        self, raw_request: bytes, bundle: bytes, *, now: int,
        pinned_public_key: bytes, peer_fixture: str,
        revoked: frozenset[str] = frozenset(),
        known_releases: frozenset[str] = frozenset(),
    ) -> dict:
        """Verify the stored bytes and consume in the same write transaction."""
        if len(bundle) > 4_000_000:
            raise ValueError("LAB_BUNDLE_TOO_LARGE")
        request = decode_document(raw_request)
        ticket_id = request.get("ticket_id")
        if type(ticket_id) is not str:
            raise ValueError("TICKET_ID_REQUIRED")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT document,state FROM tickets WHERE id=?", (ticket_id,)
            ).fetchone()
            if row is None or row[1] != "APPROVED":
                raise ValueError("UNKNOWN_OR_UNAVAILABLE_TICKET")
            verified = verify_signed_fixture(
                row[0], request, pinned_public_key=pinned_public_key,
                peer_fixture=peer_fixture, now=now, revoked=revoked,
            )
            ticket = decode_document(row[0])["ticket"]
            if hashlib.sha256(bundle).hexdigest() != ticket["bundle_sha256"]:
                raise ValueError("BUNDLE_BYTES_MISMATCH")
            if ticket["previous_release_sha"] not in known_releases:
                raise ValueError("UNKNOWN_PREVIOUS_RELEASE")
            receipt = {
                "scope": SCOPE,
                "ticket_id": ticket_id,
                "operation": ticket["operation"],
                "state": "CONSUMED_NO_EXECUTION",
                "claimed_at_lab_clock": now,
                "request_sha256": hashlib.sha256(raw_request).hexdigest(),
                "bundle_sha256": ticket["bundle_sha256"],
                "previous_release_sha": ticket["previous_release_sha"],
                "signature_fixture": verified["signature_fixture"],
                "ticket_authenticity": "NOT_VERIFIED",
                "operator_key_custody": "NOT_PROVEN",
                "peer_identity": "NOT_VERIFIED",
                "source_ci_authority": "NOT_VERIFIED",
                "privileged_execution": False,
            }
            changed = db.execute(
                "UPDATE tickets SET state='CONSUMED' WHERE id=? AND state='APPROVED'",
                (ticket_id,),
            )
            if changed.rowcount != 1:
                raise ValueError("CONCURRENT_CLAIM_CONTRADICTION")
            db.execute(
                "INSERT INTO receipts VALUES (?, ?)",
                (ticket_id, json.dumps(receipt, sort_keys=True)),
            )
        return receipt
