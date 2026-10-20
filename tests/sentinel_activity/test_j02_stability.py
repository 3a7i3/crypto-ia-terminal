"""J02 prerequisite regressions; all journals and writers are synthetic."""

import re
import hashlib
import json
import sqlite3
from unittest.mock import patch

import pytest

from governance_tower import redaction
from sentinel_activity.canonical import LedgerError
from sentinel_activity.reader import read_page
from sentinel_activity.redaction_v1 import PROFILE_VERSION, _SECRET_PATTERNS
from sentinel_activity.store import ActivityStore
from tests.sentinel_activity.builders import candidate
from tests.sentinel_activity.test_store import create


def test_tower_pattern_evolution_does_not_reclassify_existing_ledger(tmp_path):
    store = create(tmp_path)
    receipt = store.append(candidate(), producer_id="fixture-producer")
    evolved = redaction._SECRET_PATTERNS + (re.compile("Synthetic activity"),)
    with patch.object(redaction, "_SECRET_PATTERNS", evolved):
        assert redaction.redact("Synthetic activity")[1] == 1
        page = read_page(store.root)
        assert page["events"][0] == receipt
        assert (
            ActivityStore(store.root, clock=store.clock).append(
                candidate(), producer_id="fixture-producer"
            )
            == receipt
        )
    assert PROFILE_VERSION == "j01-secret-patterns/1"


def test_pinned_legacy_profile_is_not_silently_changed():
    raw = json.dumps(
        [(p.pattern, p.flags) for p in _SECRET_PATTERNS], separators=(",", ":")
    ).encode()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "f1a2d57d0a23a144ad00f0e9552137e47d20547c9ffe4e56f7ffd6d47e065fa7"
    )


def test_full_verification_does_not_hold_sqlite_writer_lock(tmp_path):
    store = create(tmp_path)
    verify = store._verified
    checked = []

    def inspect(conn):
        other = sqlite3.connect(store.path, isolation_level=None, timeout=0.05)
        try:
            other.execute("BEGIN IMMEDIATE")
            checked.append(True)
            other.rollback()
        finally:
            other.close()
        return verify(conn)

    with patch.object(store, "_verified", side_effect=inspect):
        receipt = store.append(candidate(), producer_id="fixture-producer")
    assert checked == [True]
    assert receipt["sequence"] == 1


def test_intervening_commit_retries_with_a_fresh_verified_snapshot(tmp_path):
    store = create(tmp_path)
    verify = store._verified
    calls = []

    def race(conn):
        result = verify(conn)
        calls.append(True)
        if len(calls) == 1:
            ActivityStore(store.root, clock=store.clock).append(
                candidate("fixture-competing"), producer_id="fixture-producer"
            )
        return result

    with patch.object(store, "_verified", side_effect=race):
        receipt = store.append(
            candidate("fixture-original"), producer_id="fixture-producer"
        )
    assert len(calls) == 2
    assert receipt["sequence"] == 2
    assert [event["event_id"] for event in store.snapshot()[1]] == [
        "fixture-competing",
        "fixture-original",
    ]


def test_sustained_commit_races_are_bounded_and_do_not_append_stale_work(tmp_path):
    store = create(tmp_path)
    verify = store._verified
    calls = []

    def race(conn):
        result = verify(conn)
        calls.append(True)
        ActivityStore(store.root, clock=store.clock).append(
            candidate(f"fixture-competing-{len(calls)}"), producer_id="fixture-producer"
        )
        return result

    with patch.object(store, "_verified", side_effect=race):
        with pytest.raises(LedgerError, match="BUSY"):
            store.append(candidate("fixture-original"), producer_id="fixture-producer")
    assert len(calls) == 8
    events = store.snapshot()[1]
    assert len(events) == 8
    assert not any(event["event_id"] == "fixture-original" for event in events)
