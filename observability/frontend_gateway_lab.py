"""Synthetic ledger only. No broker, ticket authenticity or privileged execution."""

from __future__ import annotations

import hashlib
from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import sqlite3

from observability.frontend_deploy_request import (
    BINDINGS,
    decode_document,
    validate_candidate,
)

SCOPE = "FRONTEND_GATEWAY_SYNTHETIC_ONLY"
LIMIT = 128


class LabLedger:
    def __init__(self, root: Path):
        self.root = Path(root).absolute()
        if self.root.is_symlink() or not self.root.is_dir():
            raise ValueError("LAB_DIRECTORY_REQUIRED")
        stat = self.root.stat()
        if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            raise ValueError("OWNED_PRIVATE_LAB_REQUIRED")
        self.path = self.root / "synthetic-tickets.sqlite"
        if self.path.is_symlink() or not self.path.is_file():
            raise ValueError("EXISTING_LAB_DATABASE_REQUIRED")
        with self._connect() as db:
            if db.execute("SELECT scope FROM metadata").fetchall() != [(SCOPE,)]:
                raise ValueError("WRONG_LAB_SCOPE")

    @classmethod
    def create(cls, root: Path) -> "LabLedger":
        root = Path(root).absolute()
        root.mkdir(mode=0o700, exist_ok=False)
        path = root / "synthetic-tickets.sqlite"
        with closing(sqlite3.connect(path, timeout=5)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript("""
                CREATE TABLE metadata(scope TEXT NOT NULL);
                CREATE TABLE tickets(id TEXT PRIMARY KEY, document BLOB NOT NULL,
                                     state TEXT NOT NULL CHECK(state IN ('APPROVED','REVOKED','CONSUMED')));
                CREATE TABLE receipts(ticket_id TEXT PRIMARY KEY REFERENCES tickets(id),
                                      body TEXT NOT NULL);
            """)
            db.execute("INSERT INTO metadata VALUES (?)", (SCOPE,))
            db.commit()
        path.chmod(0o600)
        return cls(root)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def admit_synthetic(self, raw: bytes, *, now: int) -> None:
        """Test issuer fixture insertion, never an authenticated operator grant."""
        ticket = decode_document(raw)
        request = {key: ticket.get(key) for key in BINDINGS}
        validate_candidate(ticket, request, now=now, consumed=frozenset())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] >= LIMIT:
                raise ValueError("LAB_QUOTA_FULL")
            db.execute(
                "INSERT INTO tickets VALUES (?, ?, 'APPROVED')",
                (ticket["ticket_id"], raw),
            )

    def revoke_synthetic(self, ticket_id: str) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute(
                "UPDATE tickets SET state='REVOKED' WHERE id=? AND state='APPROVED'",
                (ticket_id,),
            )
            if result.rowcount != 1:
                raise ValueError("UNKNOWN_OR_UNAVAILABLE_TICKET")

    def claim_no_execution(
        self, raw_request: bytes, bundle: bytes, *, now: int
    ) -> dict:
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
            ticket = decode_document(row[0])
            validate_candidate(ticket, request, now=now, consumed=frozenset())
            if hashlib.sha256(bundle).hexdigest() != ticket["bundle_sha256"]:
                raise ValueError("BUNDLE_BYTES_MISMATCH")
            receipt = {
                "scope": SCOPE,
                "ticket_id": ticket_id,
                "state": "CONSUMED_NO_EXECUTION",
                "claimed_at_lab_clock": now,
                "request_sha256": hashlib.sha256(raw_request).hexdigest(),
                "bundle_sha256": ticket["bundle_sha256"],
                "ticket_authenticity": "NOT_VERIFIED",
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

    def receipt(self, ticket_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT body FROM receipts WHERE ticket_id=?", (ticket_id,)
            ).fetchone()
        return json.loads(row[0]) if row is not None else None
