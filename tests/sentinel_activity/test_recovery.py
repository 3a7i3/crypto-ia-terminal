import json
import sqlite3
from copy import deepcopy

import pytest

from sentinel_activity.backup import backup, restore
from sentinel_activity.canonical import LedgerError, canonical_bytes
from sentinel_activity.contracts import event_hash
from sentinel_activity.integrity import report, verify_events
from sentinel_activity.reader import read_page
from sentinel_activity.store import ActivityStore
from tests.sentinel_activity.builders import candidate
from tests.sentinel_activity.quest_builders import create_quests, prefix
from tests.sentinel_activity.test_store import create


def test_stable_watermark_filters_and_concurrent_append(tmp_path):
    store = create(tmp_path)
    for i in range(7):
        store.append(candidate('fixture-' + str(i)), producer_id='fixture-producer')
    first = read_page(store.root, limit=2, actor_id='fixture-sentinel')
    assert first['status'] == 'PREFIX_VERIFIED'
    assert first['completeness'] == 'UNKNOWN'
    assert [e['sequence'] for e in first['events']] == [1, 2]
    store.append(candidate('fixture-later'), producer_id='fixture-producer')
    seen = list(first['events'])
    cursor = first['next_cursor']
    while cursor:
        page = read_page(store.root, cursor=cursor, limit=2, actor_id='fixture-sentinel')
        assert page['snapshot_watermark'] == 7
        seen.extend(page['events'])
        cursor = page['next_cursor']
    assert [e['sequence'] for e in seen] == list(range(1, 8))
    assert read_page(store.root)['last_sequence'] == 8
    cursor = deepcopy(first['next_cursor'])
    cursor['head_hash'] = '0' * 64
    with pytest.raises(LedgerError, match='CURSOR_INVALID'):
        read_page(store.root, cursor=cursor, actor_id='fixture-sentinel')
    with pytest.raises(LedgerError, match='CURSOR_INVALID'):
        read_page(store.root, cursor=first['next_cursor'])


def test_no_data_unavailable_and_corrupted_are_distinct(tmp_path):
    root = tmp_path / 'j01-lab-absent'
    root.mkdir(mode=0o700)
    assert read_page(root)['status'] == 'UNAVAILABLE'
    store = create(tmp_path)
    assert read_page(store.root)['status'] == 'NO_DATA'
    store.append(candidate(), producer_id='fixture-producer')
    with sqlite3.connect(store.path) as conn:
        conn.execute("UPDATE projection SET body='{}'")
    page = read_page(store.root)
    assert page['status'] == 'CORRUPTED' and page['events'] is None
    with pytest.raises(LedgerError, match='CORRUPTED'):
        store.append(candidate(), producer_id='fixture-producer')


@pytest.mark.parametrize('mutation', ['hash', 'body', 'index', 'sequence', 'delete', 'missing_field'])
def test_partial_database_tampering_detected_before_retry(tmp_path, mutation):
    store = create(tmp_path)
    store.append(candidate(), producer_id='fixture-producer')
    store.append(candidate('fixture-next'), producer_id='fixture-producer')
    with sqlite3.connect(store.path) as conn:
        conn.execute('DROP TRIGGER events_no_update')
        conn.execute('DROP TRIGGER events_no_delete')
        if mutation == 'index':
            conn.execute("UPDATE events SET request_hash='bad' WHERE sequence=1")
        elif mutation == 'sequence':
            conn.execute('UPDATE events SET sequence=3 WHERE sequence=2')
        elif mutation == 'delete':
            conn.execute('DELETE FROM events WHERE sequence=1')
        else:
            event = json.loads(conn.execute('SELECT body FROM events WHERE sequence=1').fetchone()[0])
            if mutation == 'hash':
                event['integrity']['event_hash'] = '0' * 64
            elif mutation == 'missing_field':
                del event['actor_id']
            else:
                event['summary'] = 'Changed after recording'
            conn.execute('UPDATE events SET body=? WHERE sequence=1', (canonical_bytes(event).decode(),))
    assert read_page(store.root)['status'] == 'CORRUPTED'
    with pytest.raises(LedgerError, match='CORRUPTED'):
        store.append(candidate(), producer_id='fixture-producer')


def test_unknown_storage_version_refused_without_migration(tmp_path):
    store = create(tmp_path)
    with sqlite3.connect(store.path) as conn:
        trigger = conn.execute("SELECT sql FROM sqlite_master WHERE name='meta_no_update'").fetchone()[0]
        conn.execute('DROP TRIGGER meta_no_update')
        meta = json.loads(conn.execute('SELECT body FROM ledger_meta').fetchone()[0])
        meta['storage_version'] = 'future/99'
        raw = canonical_bytes(meta).decode()
        conn.execute('UPDATE ledger_meta SET body=?', (raw,))
        conn.execute(trigger)
    with pytest.raises(LedgerError, match='UNKNOWN_VERSION'):
        ActivityStore(store.root)
    with sqlite3.connect(store.path) as conn:
        assert conn.execute('SELECT body FROM ledger_meta').fetchone()[0] == raw


def test_valid_prefix_truncation_is_not_claimed_detectable(tmp_path):
    store = create(tmp_path)
    for i in range(3):
        store.append(candidate('fixture-' + str(i)), producer_id='fixture-producer')
    meta, events, _ = store.snapshot()
    assert verify_events(meta, events[:2]) == {'quests': {}, 'participations': {}}
    assert report(meta, events[:2])['completeness'] == 'UNKNOWN'
    rewritten = deepcopy(events)
    rewritten[0]['summary'] = 'Coherent full rewrite'
    for i, event in enumerate(rewritten):
        event['integrity']['previous_hash'] = rewritten[i - 1]['integrity']['event_hash'] if i else 'GENESIS'
        event['integrity']['event_hash'] = event_hash(event)
    assert report(meta, rewritten)['authenticity'] == 'NOT_PROVEN'


def test_timestamp_regression_is_warning_not_reordering(tmp_path):
    store = create(tmp_path)
    first = candidate('fixture-first')
    first['occurred_at_utc'] = '2026-10-18T07:59:00Z'
    second = candidate('fixture-second')
    second['occurred_at_utc'] = '2026-10-18T07:58:00Z'
    store.append(first, producer_id='fixture-producer')
    store.append(second, producer_id='fixture-producer')
    result = read_page(store.root)
    assert result['warnings'] == [{'code': 'TIMESTAMP_REGRESSION', 'sequence': 2}]
    assert [e['sequence'] for e in result['events']] == [1, 2]


def test_backup_restore_and_append_after_restore(tmp_path):
    store = create_quests(tmp_path)
    prefix(store, 9)
    backup_root = tmp_path / 'j01-lab-backup'
    restore_root = tmp_path / 'j01-lab-restored'
    backup_root.mkdir(mode=0o700)
    restore_root.mkdir(mode=0o700)
    manifest = backup(store.root, backup_root)
    restored = restore(backup_root, restore_root)
    assert restored['head_hash'] == manifest['head_hash']
    assert ActivityStore(restore_root).snapshot() == store.snapshot()
    ActivityStore(restore_root).append(candidate('fixture-observation', actor='fixture-sentinel'),
                                       producer_id='fixture-sentinel')
    assert len(ActivityStore(restore_root).snapshot()[1]) == 10
    assert len(store.snapshot()[1]) == 9
    with pytest.raises(LedgerError, match='ALREADY_EXISTS'):
        restore(backup_root, restore_root)


def test_restore_rejects_changed_manifest_or_database(tmp_path):
    store = create(tmp_path)
    store.append(candidate(), producer_id='fixture-producer')
    backup_root = tmp_path / 'j01-lab-backup'
    backup_root.mkdir(mode=0o700)
    backup(store.root, backup_root)
    path = backup_root / 'manifest.json'
    manifest = json.loads(path.read_bytes())
    manifest['head_hash'] = '0' * 64
    path.write_bytes(canonical_bytes(manifest))
    destination = tmp_path / 'j01-lab-restore'
    destination.mkdir(mode=0o700)
    with pytest.raises(LedgerError, match='CORRUPTED'):
        restore(backup_root, destination)
    assert not list(destination.iterdir())
