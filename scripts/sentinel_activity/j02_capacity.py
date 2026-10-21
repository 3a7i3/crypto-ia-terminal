"""J02-D capacity measurement on seeded synthetic LAB journals (local only).

Usage: python scripts/sentinel_activity/j02_capacity.py [--sizes 500 1000 10000]
Creates private j01-lab-* directories under a fresh temporary parent, prints
one JSON document and leaves nothing behind. No network, VPS or credentials.
Numbers describe this machine and interpreter only; they are not a service
level, and nothing here is deployed.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from datetime import timedelta
from multiprocessing import Process, Queue
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sentinel_activity import SCHEMA_VERSION  # noqa: E402
from sentinel_activity.backup import backup, restore  # noqa: E402
from sentinel_activity.canonical import LedgerError  # noqa: E402
from sentinel_activity.feed import feed_page  # noqa: E402
from sentinel_activity.store import ActivityStore  # noqa: E402
from tests.sentinel_activity.seed import T0, seed  # noqa: E402

LATER = T0 + timedelta(days=1)


def _lab(parent: Path, name: str) -> Path:
    root = parent / f"j01-lab-{name}"
    root.mkdir(mode=0o700)
    return root


def _timed(fn, repeat=3):
    samples = []
    result = None
    for _ in range(repeat):
        start = time.perf_counter()
        result = fn()
        samples.append(time.perf_counter() - start)
    return result, {"median_s": round(statistics.median(samples), 4), "max_s": round(max(samples), 4),
                    "samples": len(samples)}


def _candidate(tag: str, actor: str) -> dict:
    return {"schema_version": SCHEMA_VERSION, "event_id": f"fixture-{tag}", "occurred_at_utc": None,
            "actor_id": actor, "actor_kind": "AGENT", "actor_version": None,
            "event_type": "OBSERVATION_RECORDED", "quest_id": None, "correlation_id": "fixture-capacity",
            "causation_event_id": None, "source_kind": "SIMULATED", "summary": f"Synthetic capacity {tag}",
            "reason_declared": None, "payload": {"cost": None, "code": "FIXTURE_OBSERVATION",
                                                 "related_event_id": None},
            "evidence_refs": ["fixture:capacity/proof"], "authorization_ref": None}


def _writer(root: str, index: int, count: int, queue: Queue) -> None:
    actor = "fixture-observer" if index % 2 == 0 else "fixture-observer-2"
    ok, busy, latencies = 0, 0, []
    for number in range(count):
        start = time.perf_counter()
        try:
            ActivityStore(Path(root), clock=lambda: LATER).append(
                _candidate(f"w{index}-{number}", actor), producer_id=actor)
            ok += 1
        except LedgerError as exc:
            if exc.code != "BUSY":
                queue.put({"error": exc.code})
                return
            busy += 1
        latencies.append(time.perf_counter() - start)
    queue.put({"ok": ok, "busy": busy, "max_s": max(latencies), "mean_s": statistics.mean(latencies)})


def measure(parent: Path, size: int, writers: int, appends: int) -> dict:
    root = _lab(parent, f"cap-{size}")
    start = time.perf_counter()
    seed(root, size - writers * appends if size >= 10_000 else size)
    seeded_s = time.perf_counter() - start
    store = ActivityStore(root, clock=lambda: LATER)
    base_count = len(store.snapshot()[1])
    _, snapshot = _timed(lambda: ActivityStore(root).snapshot())
    first, first_page = _timed(lambda: feed_page(root, limit=100))
    assert first["status"] == "PREFIX_VERIFIED" and len(first["items"]) == 100
    last_cursor = None
    pages, cursor = 0, None
    walk_start = time.perf_counter()
    while pages < 3:
        page = feed_page(root, limit=100, cursor_token=cursor)
        assert page["status"] == "PREFIX_VERIFIED"
        pages += 1
        cursor = page["next_cursor"]
        last_cursor = cursor
        if cursor is None:
            break
    walk = {"pages": pages, "mean_page_s": round((time.perf_counter() - walk_start) / pages, 4),
            "more_pages": last_cursor is not None}
    queue = Queue()
    procs = [Process(target=_writer, args=(str(root), i, appends, queue)) for i in range(writers)]
    start = time.perf_counter()
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join()
    concurrent_s = time.perf_counter() - start
    results = [queue.get() for _ in procs]
    errors = [r["error"] for r in results if "error" in r]
    events = ActivityStore(root).snapshot()[1]
    ok = sum(r.get("ok", 0) for r in results)
    integrity = (not errors and len(events) == base_count + ok
                 and [e["sequence"] for e in events] == list(range(1, len(events) + 1)))
    backup_root, restored_root = _lab(parent, f"bak-{size}"), _lab(parent, f"res-{size}")
    start = time.perf_counter()
    manifest = backup(root, backup_root)
    backup_s = time.perf_counter() - start
    start = time.perf_counter()
    restored = restore(backup_root, restored_root)
    restore_s = time.perf_counter() - start
    reopened = ActivityStore(restored_root).snapshot()[1]
    return {
        "events_at_start": base_count, "seed_s": round(seeded_s, 2), "snapshot_full_verify": snapshot,
        "feed_first_page_100": first_page, "feed_walk": walk,
        "concurrent_writers": {"writers": writers, "appends_each": appends, "ok": ok,
                               "busy": sum(r.get("busy", 0) for r in results), "errors": errors,
                               "wall_s": round(concurrent_s, 2),
                               "max_append_s": round(max(r.get("max_s", 0) for r in results), 3),
                               "mean_append_s": round(statistics.mean(r.get("mean_s", 0) for r in results), 3)},
        "integrity_after_concurrency": integrity, "final_events": len(events),
        "backup_s": round(backup_s, 2), "restore_s": round(restore_s, 2),
        "restore_matches": restored["head_hash"] == manifest["head_hash"] and len(reopened) == len(events),
        "db_bytes": sum(p.stat().st_size for p in root.iterdir() if p.is_file()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", type=int, nargs="+", default=[500, 1_000, 10_000])
    parser.add_argument("--writers", type=int, default=2)
    parser.add_argument("--appends", type=int, default=5)
    args = parser.parse_args()
    parent = Path(tempfile.mkdtemp(prefix="j02-capacity-"))
    try:
        report = {"mode": "SIMULATED_ONLY", "python": platform.python_version(),
                  "sqlite": sqlite3.sqlite_version, "machine": platform.machine(),
                  "cpu_count": os.cpu_count(), "results": {}}
        for size in args.sizes:
            report["results"][str(size)] = measure(parent, size, args.writers, args.appends)
        print(json.dumps(report, indent=1, sort_keys=True))
    finally:
        shutil.rmtree(parent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
