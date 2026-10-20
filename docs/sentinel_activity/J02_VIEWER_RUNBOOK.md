# J02 — local feed viewer runbook

SOURCE_ONLY / SIMULATED_ONLY / NOT_DEPLOYED / NO_RUNTIME_AUTHORITY. #286 ACTIVE.
This runbook does not authorize a service, a systemd unit, network exposure, a
VPS installation or any real ingestion. It describes a laboratory process.

## What it is

- `sentinel_activity/feed.py`: `feed_page(root, limit, cursor_token, filters)`.
  A presentation of `read_page`: same verified events, same statuses, plus an
  opaque hex cursor token and display-time redaction by the current
  `governance_tower.redaction` rules. Historical bytes and hashes never change.
- `sentinel_viewer/`: a separate process, outside Governance Tower and the
  Operator API, serving `GET /ledger/<n>` (HTML, no JavaScript) and
  `GET /api/ledger/<n>` (JSON) for LAB roots fixed at start-up.

## Start (laboratory only)

```bash
python -m sentinel_viewer --root /absolute/path/j01-lab-demo-XXXX --port 8765
```

Only `127.0.0.1` is bound. Roots must be absolute `j01-lab-*` paths; up to 8.
Nothing is created: a missing journal returns `UNAVAILABLE` (HTTP 503).

## Guarantees and limits

| Property | Behaviour |
|---|---|
| Methods | GET only; POST/PUT/DELETE/PATCH/HEAD/OPTIONS → 405, journal unchanged |
| Request | target ≤ 2 KiB, no body, closed query fields, no duplicates |
| Page | `limit` 1..100 (default 25); cursor pinned to watermark/head and filters |
| Response | ≤ 4 MiB, else `RESPONSE_TOO_LARGE` |
| Concurrency | 2 journal reads in flight; others `BUSY` (503); 10 s timeout per socket operation, no deadline per request and no cap on open connections |
| Browser | Host must be 127.0.0.1/localhost:port; foreign Origin or cross-site fetch → 403; CSP `default-src 'none'`, no CORS, no-store |
| Content | all event text HTML-escaped; references displayed as inert text, never links |
| Errors | `UNAVAILABLE`, `BUSY` → 503; `CURSOR_INVALID`, `QUERY_INVALID` → 400; `CORRUPTED`, `UNKNOWN_VERSION`, `PATH_DENIED` → 500; malformed requests rejected by `http.server` itself → JSON `REQUEST_MALFORMED` with the same security headers. A failure is never an empty feed |
| Logs | no request target, filter or cursor is logged |

Loopback is not authentication: any local process of any account can read the
pages. Do not run it on a shared multi-user host or against non-synthetic data.
Each request re-verifies the whole journal (≈5 s per page at 10,000 events on
the measured machine, see J02_CAPACITY_REPORT.md). A thread per connection is
used and connections are not capped: a client sending one byte just under every
10 s keeps its connection (and a thread) open indefinitely. This is an accepted
limit for a loopback LAB viewer, not a service level.

## Rollback

Stop the process. The viewer writes no journal data and no file of its own.
Reading a journal in WAL mode lets SQLite create or update its `-wal`/`-shm`
coordination files next to `activity.sqlite3` (for example on a copy made
without them); the database content is not changed.
