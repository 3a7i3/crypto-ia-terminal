"""Numbered, append-only schema migrations of the positioning store.

A migration already applied is never edited: its SQL digest is recorded and checked
at every open. A database written by a newer version is refused (fail closed).
"""

from __future__ import annotations

import hashlib

MIGRATIONS = (
    (1, "initial", """
CREATE TABLE store_identity (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    store_id TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL
);
CREATE TABLE observations (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_key TEXT NOT NULL UNIQUE,
    content_sha256 TEXT NOT NULL,
    venue TEXT NOT NULL,
    native_symbol TEXT NOT NULL,
    contract_type TEXT NOT NULL,
    quote_currency TEXT NOT NULL,
    source_time_ms INTEGER,
    received_at_ms INTEGER NOT NULL,
    effective_time_ms INTEGER NOT NULL,
    time_basis TEXT NOT NULL CHECK (time_basis IN ('SOURCE', 'RECEIPT')),
    out_of_order INTEGER NOT NULL CHECK (out_of_order IN (0, 1)),
    stored_at_ms INTEGER NOT NULL,
    document TEXT NOT NULL
);
CREATE INDEX observations_by_leg_time
    ON observations (venue, native_symbol, contract_type, effective_time_ms);
CREATE TABLE conflicts (
    observation_key TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    first_seen_ms INTEGER NOT NULL,
    last_seen_ms INTEGER NOT NULL,
    attempts INTEGER NOT NULL CHECK (attempts >= 1),
    document TEXT NOT NULL,
    PRIMARY KEY (observation_key, content_sha256)
);
"""),
)

LATEST_VERSION = MIGRATIONS[-1][0]


def sql_sha256(sql: str) -> str:
    return hashlib.sha256(sql.strip().encode("utf-8")).hexdigest()
