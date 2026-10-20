# J02 — capacity measurement (synthetic LAB journals)

SOURCE_ONLY / SIMULATED_ONLY / NOT_DEPLOYED. #286 ACTIVE. Measured 2026-10-20 on
the development container: Python 3.11.17, SQLite 3.45.1, x86_64,
4 CPU, non-root user, local disk. Source: the J02 B–D change on main `bfb1109`,
as merged at PR #477 head `ae792913`. Reproduce with `python scripts/sentinel_activity/j02_capacity.py`.

Journals are seeded with valid `OBSERVATION_RECORDED` events through
`tests/sentinel_activity/seed.py` (the recorder's own validation and hashing,
one transaction), then every measurement goes through the public API, which
re-verifies the whole journal. Two writer processes each append 5 events.

| events | full verify (s, median) | first feed page of 100 (s) | mean page, 3 pages (s) | append mean / max with 2 writers (s) | BUSY | integrity after concurrency | backup / restore (s) | restore identical | DB bytes |
|---|---|---|---|---|---|---|---|---|---|
| 500 → 510 | 0.1177 | 0.2082 | 0.2548 | 0.249 / 0.946 | 0 | oui | 0.45 / 0.65 | oui | 835584 |
| 1000 → 1010 | 0.3247 | 0.4538 | 0.3968 | 0.449 / 1.538 | 0 | oui | 1.06 / 1.21 | oui | 1593344 |
| 9990 → 10000 | 3.6844 | 5.2187 | 5.1129 | 5.793 / 21.293 | 0 | oui | 10.09 / 16.21 | oui | 15175680 |

The 10,000 row fills the journal to its `max_events` limit (9,990 seeded + 10).

## Before / after the J02-D text-rule change (same machine, seeded journals)

| events | full verify before (#476 code) | after |
|---|---|---|
| 500 | 0.86 s | 0.13 s |
| 1,000 | 1.58 s | 0.25–0.34 s |
| 10,000 | ≈16 s (extrapolated, not measured) | 3.5–3.7 s |

Process stress on an empty journal (`4×30`, `6×40` appends): 0 BUSY after the
change, measured with an ad hoc harness that `j02_capacity.py` does not include
(not reproducible with the shipped script); the independent review of #476 measured 17–20 and 56 BUSY with #476's
optimistic loop and 5 and 51 with the J01 base.

## Verdict

- 500 events: functional and interactive (≈0.2–0.25 s per page). 1,000 events:
  functional, ≈0.4–0.5 s per page (the independent review measured a median of
  0.50 s and a maximum of 0.52 s), so "below 0.5 s" is not guaranteed.
- 10,000 events: functional (integrity, concurrency without BUSY, restore) but
  NOT interactive: ≈5 s per viewer page, ≈6 s mean append, worst observed append
  21 s for a writer that lost races. No throughput or service level is claimed.
- Not measured: hostile same-account writers, NFS, more than 2 concurrent
  writers at 10,000 events, disk-full during commit, other machines.
