# J02 — local activity feed, plan and prerequisites

SOURCE_ONLY / SIMULATED_ONLY / NOT_DEPLOYED / NO_RUNTIME_AUTHORITY.
#286 ACTIVE. The operator authorized resumption of Research and J02 on 2026-10-19.
Base: main 0f5f12f3ca3ac564527fc58610fb121b1e057b20. Existing J01 journals, event
hashes, quest semantics, policies and SQLite storage version are retained.

## A — journal stability (this change)

Two independently reproduced defects precede any new view:

1. Canonical event validation called the evolving Governance Tower redactor.
   A new Tower pattern could therefore classify unchanged historical bytes as
   corrupted. J01 storage/event contracts now bind to the immutable local
   `j01-secret-patterns/1` profile, reproducing the original patterns exactly.
   Its pattern/flag fingerprint is
   `f1a2d57d0a23a144ad00f0e9552137e47d20547c9ffe4e56f7ffd6d47e065fa7`.
   A future pattern update requires a new profile and explicit admission/version
   policy; never edit this legacy profile in place. This is a known-pattern
   detector, not a guarantee against unknown secret formats. No event bytes,
   hash, metadata or historical journal is migrated or rewritten.
2. Append held BEGIN IMMEDIATE while verifying and projecting the whole journal.
   Verification, admission, causation and projection now run in a consistent read
   transaction. After releasing it, a short write transaction compares SQLite's
   data_version on the same connection. Any intervening commit invalidates the
   entire preparation and triggers full reverification. At most eight attempts;
   sustained competing commits return BUSY without appending stale work.
   Space is rechecked under the write lock. The event and projection commit
   atomically as before. Idempotent retries return a verified snapshot receipt.

This removes full replay from the writer critical section. It does NOT make
verification or projection constant-time, eliminate contention, or qualify
10,000-event throughput. Full replay still occurs per operation; total CPU cost
and adversarial high-contention behavior remain future qualification items.
SQLite data_version is not a signature or a defense against hostile same-account
filesystem replacement. Existing local/private path and WAL qualifications apply.

Tests must demonstrate pattern evolution without false corruption, immutable
legacy profile, availability of the SQLite writer lock during verification,
intervening-commit retry, bounded sustained-race refusal, and all J01 recovery,
corruption, causation, quota and quest-state regressions. Test data are synthetic.

## B — feed projection (next isolated change)

Reuse sentinel_activity.reader.read_page: filters, fixed watermark, prefix/head,
ledger identity, provenance and completeness limits already exist. Add only
presentation fields needed by a feed, never a second journal or quest authority.
Apply current display-time sanitization without changing the hashed event.
Qualify redaction behavior when a newer display rule conceals a historical field.
Preserve NO_DATA / UNAVAILABLE / CORRUPTED / UNKNOWN; no inference of completeness.

## C — separate local GET-only viewer

Separate module/process outside Governance Tower and the Operator API. Explicit
LAB root, loopback binding, no implicit creation, no secrets, no producer/worker,
no connection to the VPS and no deployment in J02 source work. Bound query/cursor,
response and concurrency sizes. Reject mutations, unexpected query fields and
cross-origin browser access. Escape untrusted text and never dereference event
references. Document the limits of loopback exposure on a multi-user host.

## D — qualification and acceptance

Fresh-process restart and cursor continuity, two real writers, corruption before
and after a read, crash before/after commit, display injection and secret patterns,
GET-only failures and bounded unavailable states. Measure seeded 500/1,000/10,000
synthetic journals before making any throughput or capacity-service claim.
No mutable global verification cache is introduced by prerequisite A.

Source checks and independent review precede each integration. A local synthetic
viewer is not a deployed agent. No governor, secretary, clan, quest executor,
AIC economy, auto-acceptance, merge, deployment or operational authority is enabled.

## Rollback

This source change preserves canonical bytes and storage/event versions. Existing
journals remain readable by the prior implementation when its original redaction
patterns are unchanged. Rolling source back does not delete or repair a journal.
A future profile migration requires its own compatibility and backup contract.
No runtime rollback is needed here because no service is installed or restarted.
