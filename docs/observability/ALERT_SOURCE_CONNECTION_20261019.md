# Explicit alert inputs for the presentation bridge

## Verified cause and reuse

The deployed bridge was configured only for PPL. The existing event-center producer already supports bounded P12 and supervision inputs and strips messages, context and raw records from its published events. Reuse it instead of creating another alert database or reader.

A one-shot operator capture on 2026-10-19 at 22:19:16 UTC found P12 PARTIAL_TAIL: 10,000 records in a bounded tail window, 100 published alerts, source size 2,070,742 bytes. The selected alerts were MEMORY events. This is historical data, not proof that a critical condition remains active. Per-source freshness remains UNKNOWN for these JSONL inputs because no producer heartbeat is declared.

The explicitly selected supervision audit was INVALID. Keep this visible; do not treat it as empty or repair its source. A bounded local format diagnostic is required before any adapter change. The expected Research presentation artifact remains absent; this does not prove absence of admitted evidence elsewhere and does not authorize manufacturing a Research result.

## Change

Add optional explicit P12 and supervision paths to publish() and its CLI. Paths must be absolute, without symlink components, inside the declared source root and outside the presentation output. Defaults remain unconfigured. The existing bounded reader handles absent, partial, unreadable and invalid sources independently while retaining PPL. A manifest records source statuses, input hashes and coverage, never raw messages or source paths.

No implicit discovery, environment default, service startup or source mutation. The caller must supply and authorize paths. No frontend or API change is needed: both already support schema 1.1.0 and its coverage fields.

## Tests and runtime gate

Tests verify filtered messages, unchanged source bytes, explicit MISSING/INVALID instead of fake zero populations, PPL preservation, and rejection of external/symlink inputs before publication. Existing bridge atomicity, validation, locking, quotas and rollback tests remain applicable.

Source integration alone does not update the deployed publisher. First run the reviewed bridge once into a separate private output and inspect its projection and timing. A later, separately reviewed publisher-only release may preserve the existing retention runner and timer. It must not restart Advisor or alter PPL/FIN/config/epoch. Rollback restores the prior publisher ExecStart and leaves historical projections intact. #286 remains ACTIVE.
