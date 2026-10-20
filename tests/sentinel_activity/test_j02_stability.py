"""J02 prerequisite regressions; all journals and writers are synthetic."""

import re
import hashlib
import json
import sqlite3
from unittest.mock import patch


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


def test_sustained_commit_races_end_with_a_locked_final_attempt(tmp_path):
    # Seven optimistic attempts lose a race; the eighth verifies under the
    # writer lock, so the competing writer is the one refused (BUSY) and the
    # original event is appended on the current, verified state.
    store = create(tmp_path)
    verify = store._verified
    calls, competing = [], []

    def race(conn):
        result = verify(conn)
        calls.append(True)
        try:
            ActivityStore(store.root, clock=store.clock).append(
                candidate(f"fixture-competing-{len(calls)}"), producer_id="fixture-producer"
            )
            competing.append("COMMITTED")
        except LedgerError as exc:
            competing.append(exc.code)
        return result

    with patch.object(store, "_verified", side_effect=race):
        receipt = store.append(candidate("fixture-original"), producer_id="fixture-producer")
    assert len(calls) == 8
    assert competing == ["COMMITTED"] * 7 + ["BUSY"]
    events = store.snapshot()[1]
    assert [e["event_id"] for e in events] == [f"fixture-competing-{i}" for i in range(1, 8)] + [
        "fixture-original"
    ]
    assert receipt["sequence"] == 8


class _ConnectionProxy:
    """Delegates to a real sqlite3 connection; runs a hook before one SQL text."""

    def __init__(self, conn, hook):
        self._conn, self._hook = conn, hook

    def execute(self, sql, *args):
        self._hook(sql)
        return self._conn.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def test_commit_between_read_rollback_and_writer_lock_is_detected(tmp_path):
    from sentinel_activity import store as store_module

    store = create(tmp_path)
    real_connect = sqlite3.connect
    state = {"armed": True, "begin_immediate": 0}

    def hook(sql):
        if sql == "BEGIN IMMEDIATE" and state["armed"]:
            state["armed"] = False
            state["begin_immediate"] += 1
            ActivityStore(store.root, clock=store.clock).append(
                candidate("fixture-window"), producer_id="fixture-producer")

    def connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        return _ConnectionProxy(conn, hook) if state["armed"] else conn

    with patch.object(store_module.sqlite3, "connect", side_effect=connect):
        receipt = store.append(candidate("fixture-original"), producer_id="fixture-producer")
    assert state["begin_immediate"] == 1
    assert receipt["sequence"] == 2
    assert [e["event_id"] for e in store.snapshot()[1]] == ["fixture-window", "fixture-original"]


def test_tower_admission_patterns_still_match_frozen_profile():
    # Divergence must force an explicit decision about an admission profile v2,
    # never a silent mismatch between display and admission rules.
    tower = [(p.pattern, p.flags) for p in redaction._SECRET_PATTERNS]
    assert tower == [(p.pattern, p.flags) for p in _SECRET_PATTERNS]
