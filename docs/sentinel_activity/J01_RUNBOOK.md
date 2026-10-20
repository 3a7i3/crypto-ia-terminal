# J01 — laboratory runbook

SOURCE_ONLY / SIMULATED_ONLY / NOT_DEPLOYED / NO_RUNTIME_AUTHORITY.
#286 ACTIVE. This runbook does not authorize production operations, a service,
network exposure, a worker, a real operator decision or an Agent Registry.

## Installation and tests

Use an isolated Python 3.11 environment and the repository's CI dependencies.
J01 itself adds no third-party dependency. From a source checkout:

```bash
python -m pytest -q tests/sentinel_activity/
python -m pytest -q tests/governance_tower/
python scripts/ci/ruff_baseline_gate.py check
python -m pytest -q tests/cross_stack/
```

The existing CI correctness job collects tests/sentinel_activity automatically.
No workflow was added or dispatched manually. Source CI is not deployment proof.

## One-shot synthetic demonstration

The example explicitly creates a private temporary LAB directory, outside the
checkout. It does not inspect a VPS or use credentials:

```python
import json
import tempfile
from pathlib import Path
from sentinel_activity.demo import run_demo

root = Path(tempfile.mkdtemp(prefix="j01-lab-demo-"))
print(root)
print(json.dumps(run_demo(root), indent=2))
```

Nine SIMULATED events: proposal, simulated publication approval, publication,
DEMO-A acceptance, DEMO-B decline (synthetic budget), start, synthetic artifact,
review by a distinct fixture actor, closure. Cost remains null; no AIC created.
All fixture roles are local scenario configuration, NOT real authentication,
A1 registration, F3/F4 capability admission or an operational decision queue.

Stop the Python process. In another process, reuse the printed directory:

```python
from pathlib import Path
from sentinel_activity.store import ActivityStore
from sentinel_activity.integrity import report
from sentinel_activity.reader import read_page

root = Path("/absolute/path/to/j01-lab-demo-REPLACE")
meta, events, projection = ActivityStore(root).snapshot()
print(report(meta, events))
print(read_page(root, limit=3))
```

Expected: same event count/head and projection; status PREFIX_VERIFIED,
completeness UNKNOWN, authenticity NOT_PROVEN, anchor NOT_CONFIGURED.
NO_DATA means no recorded event in an existing verified local DB, not no agent
activity. An absent DB returns UNAVAILABLE and is never implicitly created.
The read-only SQLite connection may maintain SQLite WAL/SHM coordination files;
"read-only" means no event/schema mutation, not zero filesystem coordination.

## API and pagination

ActivityStore.create requires an existing absolute j01-lab-* directory owned
by the caller, exactly mode 0700; database/sidecars must be private regular
0600 files without extra hardlinks. Every path component is checked for symlinks.
Choose a trusted local parent directory; hostile same-account writers, parent
replacement races, NFS and OS-level confinement are not qualified by J01.
No default location or production path is provided. Construction opens nothing
until explicitly called; imports do not create files or read environment values.

read_page supports quest_id, actor_id and correlation_id, limit 1..100, and a
structured next_cursor. Repeat the same filters and pass next_cursor unchanged.
A cursor pins a watermark/head; later appends do not enter that paginated snapshot.
The full currently stored journal is verified before serving a page. Cursors are
not authentication or signed completeness assertions. A caller can select a
verified historical prefix; it never receives global completeness authority.

The snapshot API is diagnostic and bounded to 10,000 events. Projections have a
separate 4 MiB bound. Recorded events <=32 KiB, candidate <=24 KiB, payload <=16 KiB.
A fixture producer may append <=5,000 events (configurable downward). There is no
producer timer/rate service. SQLite waits at most 2 s per lock acquisition on
contention. Append preparation uses a read transaction and is retried if another
connection commits before the write phase; the eighth and last attempt verifies
under the writer lock, so a writer cannot be starved by optimistic retries. No
total wall-time bound is implied. Full replay still costs O(N) per operation;
measured latencies are in J02_CAPACITY_REPORT.md. File-size admission uses a conservative reserve against <=128 MiB total DB/sidecars; this
is not an OS hard quota or protection from another process growing the files.
At quota or I/O error, refuse admission; do not delete historical data.

## Backup and recovery

Prepare an empty absolute private j01-lab-* directory outside the checkout,
then call backup(source_root, backup_root). It uses SQLite's backup API inside
one verified read transaction, never a raw copy of a live WAL database.
A manifest records ledger/version/policy/count/head and main-file hash.

restore(backup_root, new_empty_root) checks the manifest and source snapshot
before copying into a new private directory. It never overwrites an existing
journal. Restore includes a second snapshot consistency check inside the copy
transaction. Reopen and verify before any later use. Partial destinations on
failure are preserved and must be inspected; do not treat them as admitted
recovery because a file exists. There is no automatic deletion/repair/migration.
A malformed or unknown storage/event/backup version is refused.

The adjacent manifest is a consistency check, not an independent trust anchor.
A complete coherent rewrite of DB+manifest or a valid tail truncation without
an external remembered head cannot be detected. Do not label the history complete,
authenticated, certified, tamper-proof or evidence of economic value.

## Security and lifecycle

Known secret patterns are rejected recursively before persistence; errors expose
closed codes, not submitted text. Unknown secret formats can escape pattern
recognition: never feed raw logs, private prompts, .env content or credentials.
Reason is declared explanation, never chain of thought. Text is not executed or
interpreted as tool instructions; this package has no renderer or shell tool.

OperatorDecision (#315), A1 (#284/#374), security AuditLog and PPL/FIN remain
separate. No existing component imports this package. No integration hook, route,
systemd unit, GitHub writer, external LLM or scheduler is shipped. J02 and later
need new mandates; no source result changes #286, Gate O or deployed runtime.
