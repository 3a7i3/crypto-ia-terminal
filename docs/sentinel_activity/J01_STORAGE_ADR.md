# J01 local storage decision

Accepted source design under the operator-approved plan, 2026-10-18.
Status: SOURCE_ONLY / NOT_DEPLOYED. #286 ACTIVE, Gate O OPEN.

Use a separate explicit private laboratory directory and SQLite database.
No default path, shared production file, public endpoint, scheduler, external
key or automatic connection. Pure modules open nothing at import time.
Existing Governance Tower isolation tests remain unchanged (sqlite3 is not
on their allowlist). OperatorDecision storage is a design precedent, not an
import/dependency: its authority and trust policy belong to #315.

Storage schema version j01-storage/1. Explicit create differs from read/open;
an absent file is not an empty database. WAL + synchronous FULL, foreign keys,
bounded lock wait. BEGIN IMMEDIATE serializes writers across processes.
Sequence, event, idempotency fingerprint and projection update commit together.
No acknowledgment before commit. Crash after commit/before acknowledgment is
recovered by retry with original event_id. This is not external exactly-once.

Events append only through the API and SQL triggers; the database owner can
still tamper with files/triggers. Verification and projection use the same
SQLite snapshot. All events are revalidated for this bounded J01 prototype.
No silent repair. Derived caches must match replay or fail closed.

Limits: <=10,000 events, <=128 MiB across DB/WAL/SHM and admission reserve,
<=100 events/page, <=2 seconds SQLite lock wait. Bounded local disk only; no
NFS qualification. Full verification cost is measured, not optimized in J01.

No automatic migration, pruning, vacuum, deletion or rotation. Unknown schema
is refused before writes. At capacity, refuse admission visibly; operator
may back up and start a separately identified journal under a future mandate.
Backup uses SQLite backup API (not copying a live WAL DB), with a manifest.
Restore targets a new destination, verifies schema/hash/replay and preserves
the source; never overwrite a journal or repair corrupted history.

Without an independent trusted head, valid-prefix truncation/full rewrite
cannot be detected. Report PREFIX_VERIFIED / COMPLETENESS_UNKNOWN /
AUTHENTICITY_NOT_PROVEN / ANCHOR_NOT_CONFIGURED. No fake operational AVAILABLE.
Crash tests are process-failure evidence, not power-loss/hardware qualification.
