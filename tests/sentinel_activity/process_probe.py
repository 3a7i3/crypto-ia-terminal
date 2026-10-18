"""Subprocess-only fixture harness, never imported by the shipped package."""

import json
import os
import sqlite3
import sys
from pathlib import Path

from sentinel_activity.canonical import LedgerError
from sentinel_activity.demo import run_demo
from sentinel_activity.integrity import report
from sentinel_activity.store import ActivityStore
from tests.sentinel_activity.builders import candidate
from tests.sentinel_activity.quest_builders import step


def main():
    mode, root = sys.argv[1], Path(sys.argv[2])
    if mode == 'demo':
        print(json.dumps(run_demo(root), sort_keys=True))
        return
    store = ActivityStore(root)
    if mode == 'inspect':
        meta, events, projection = store.snapshot()
        print(json.dumps({**report(meta, events), 'projection': projection}, sort_keys=True))
        return
    if mode.startswith('claim-'):
        actor = mode.removeprefix('claim-')
        event = step(store, 'QUEST_ACCEPTED', actor, event_id='fixture-claim-' + actor)
        # Parent starts both processes before releasing this barrier file.
        barrier = root / 'fixture-go'
        import time
        deadline = time.monotonic() + 15
        while not barrier.exists():
            if time.monotonic() > deadline:
                raise RuntimeError('fixture barrier timeout')
            time.sleep(0.01)
        try:
            result = store.append(event, producer_id='fixture-' + actor)
            print(json.dumps({'status': 'APPENDED', 'sequence': result['sequence']}))
        except LedgerError as error:
            print(json.dumps({'status': error.code}))
        return
    original_connect = sqlite3.connect

    class CrashConnection(sqlite3.Connection):
        def commit(self):
            if mode == 'before':
                os._exit(71)
            super().commit()
            if mode == 'after':
                os._exit(72)

    def connect(*args, **kwargs):
        kwargs['factory'] = CrashConnection
        return original_connect(*args, **kwargs)

    sqlite3.connect = connect
    store.append(candidate(), producer_id='fixture-producer')


if __name__ == '__main__':
    main()
