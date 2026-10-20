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
| Concurrency | 2 requests in flight; others `BUSY` (503); 10 s socket timeout |
| Browser | Host must be 127.0.0.1/localhost:port; foreign Origin or cross-site fetch → 403; CSP `default-src 'none'`, no CORS, no-store |
| Content | all event text HTML-escaped; references displayed as inert text, never links |
| Errors | `UNAVAILABLE`, `BUSY` → 503; `CURSOR_INVALID` → 400; `CORRUPTED`, `UNKNOWN_VERSION`, `PATH_DENIED` → 500. A failure is never an empty feed |
| Logs | no request target, filter or cursor is logged |

Loopback is not authentication: any local process of any account can read the
pages. Do not run it on a shared multi-user host or against non-synthetic data.
Each request re-verifies the whole journal (≈5 s per page at 10,000 events on
the measured machine, see J02_CAPACITY_REPORT.md). A thread per connection is
used; slow clients are bounded only by the socket timeout.

## Rollback

Stop the process. No state, file or journal is created or changed by the viewer.
