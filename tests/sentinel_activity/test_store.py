import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from sentinel_activity.canonical import LedgerError, parse_utc
from sentinel_activity.store import ActivityStore, Limits
from tests.sentinel_activity.builders import NOW, candidate


def policy():
    return {"version": "fixture-policy-1", "producers": {"fixture-producer": {
        "actor_id": "fixture-sentinel", "actor_kind": "AGENT", "actor_version": None, "role": "OBSERVER"}}}


def create(tmp_path, **kwargs):
    root = tmp_path / "j01-lab-test"
    root.mkdir(mode=0o700)
    return ActivityStore.create(root, policy(), ledger_id="fixture-journal", clock=lambda: parse_utc(NOW), **kwargs)


def test_restart_and_original_receipt(tmp_path):
    store = create(tmp_path)
    first = store.append(candidate(), producer_id="fixture-producer")
    reopened = ActivityStore(store.root)
    assert reopened.append(candidate(), producer_id="fixture-producer") == first
    assert len(reopened.snapshot()[1]) == 1
    assert first["occurred_at_utc"] is None
    assert first["sequence"] == 1


def test_conflict_does_not_consume_sequence(tmp_path):
    store = create(tmp_path)
    store.append(candidate(), producer_id="fixture-producer")
    changed = candidate()
    changed["summary"] = "Different"
    with pytest.raises(LedgerError, match="EVENT_ID_COLLISION"):
        store.append(changed, producer_id="fixture-producer")
    assert store.append(candidate("fixture-next"), producer_id="fixture-producer")["sequence"] == 2


def test_concurrent_identical_emission(tmp_path):
    store = create(tmp_path)

    def emit(_):
        return ActivityStore(store.root).append(candidate(), producer_id="fixture-producer")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(emit, range(8)))
    assert all(e == results[0] for e in results)
    assert len(store.snapshot()[1]) == 1


@pytest.mark.parametrize("source", ["AGENT_REPORTED", "SYSTEM_OBSERVED", "OPERATOR_DECISION"])
def test_real_provenance_disabled(tmp_path, source):
    store = create(tmp_path)
    event = candidate()
    event["source_kind"] = source
    with pytest.raises(LedgerError, match="PROVENANCE_DENIED"):
        store.append(event, producer_id="fixture-producer")
    assert not store.snapshot()[1]


def test_actor_spoof_and_orphan_cause(tmp_path):
    store = create(tmp_path)
    with pytest.raises(LedgerError, match="ACTOR_DENIED"):
        store.append(candidate(actor="fixture-other"), producer_id="fixture-producer")
    with pytest.raises(LedgerError, match="CAUSATION_INVALID"):
        store.append(candidate(cause="fixture-missing"), producer_id="fixture-producer")
    assert not store.snapshot()[1]


def test_logical_append_only(tmp_path):
    store = create(tmp_path)
    store.append(candidate(), producer_id="fixture-producer")
    with sqlite3.connect(store.path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM events")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE events SET body='{}'")


def test_maximum_event_and_producer_budgets(tmp_path):
    store = create(tmp_path, limits=Limits(max_events=1, per_producer=1))
    receipt = store.append(candidate(), producer_id="fixture-producer")
    # Even at the cap a retry must recover the original committed receipt.
    assert store.append(candidate(), producer_id="fixture-producer") == receipt
    with pytest.raises(LedgerError, match="BUDGET_EXCEEDED"):
        store.append(candidate("fixture-second"), producer_id="fixture-producer")


def test_paths_and_explicit_create(tmp_path):
    root = tmp_path / "j01-lab-empty"
    root.mkdir(mode=0o700)
    with pytest.raises(LedgerError, match="UNAVAILABLE"):
        ActivityStore(root)
    assert not list(root.iterdir())
    wrong = tmp_path / "production"
    wrong.mkdir(mode=0o700)
    with pytest.raises(LedgerError, match="PATH_DENIED"):
        ActivityStore.create(wrong, policy(), ledger_id="fixture-journal")
    link = tmp_path / "j01-lab-link"
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(LedgerError, match="PATH_DENIED"):
        ActivityStore(link)


def test_no_overwrite_or_adoption_of_sidecar(tmp_path):
    store = create(tmp_path)
    with pytest.raises(LedgerError, match="ALREADY_EXISTS"):
        ActivityStore.create(store.root, policy(), ledger_id="fixture-other")


def test_future_and_clock_regression(tmp_path):
    store = create(tmp_path)
    event = candidate()
    event["occurred_at_utc"] = "2027-10-18T08:00:00Z"
    with pytest.raises(LedgerError, match="INVALID_TIME"):
        store.append(event, producer_id="fixture-producer")
    store.append(candidate(), producer_id="fixture-producer")
    old = ActivityStore(store.root, clock=lambda: parse_utc("2025-10-18T08:00:00Z"))
    with pytest.raises(LedgerError, match="CLOCK_REGRESSION"):
        old.append(candidate("fixture-old"), producer_id="fixture-producer")
