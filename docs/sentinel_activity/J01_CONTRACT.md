# J01 — Persistent Activity Ledger

SOURCE_ONLY · SIMULATED_ONLY · NOT_DEPLOYED · NO_RUNTIME_AUTHORITY.
Plan approved by the operator in Work on 2026-10-18, following PR #465
(`811c2feda8dfe4439c77ec23bd8e88d4248aedef`). Base main:
`a49eedfcd683145cf8ae6e38c6dc38cff8ea698e`. #286 stays ACTIVE.
Approval covers isolated source development; no merge/deployment authorization.

## Version and ownership

`sentinel-event/0.1` is finalized from the unimplemented proposal. Candidate
fields are exactly `CANDIDATE_FIELDS` in `sentinel_activity/contracts.py`.
The recorder exclusively assigns `ledger_id`, `producer_id`,
`ingestion_policy_version`, `sequence`, `recorded_at_utc`, and `integrity`.
Sequence starts at 1, contiguous. Unknown occurred time remains null.

All 18 event types in the proposal are preserved. Payloads are closed per
type (`PAYLOAD_FIELDS`), with required `cost: null`: real accounting is future
work, not zero cost or AIC. All string input is bounded NFC, without controls,
format controls or surrogates. Known secret patterns are rejected recursively
before hashing/persistence, not silently redacted. Pattern detection is not
a guarantee against unknown secret formats; do not ingest raw logs.

## Canonical bytes

UTF-8 JSON, sorted keys, compact separators, ensure_ascii=False, allow_nan=False.
Only exact JSON types; no floats, tuple, duplicate keys, non-string keys,
out-of-range integers or silent normalization. Boolean is not an integer field.
Canonical event <=32 KiB; candidate <=24 KiB; payload <=16 KiB; depth <=8.
Summary <=300 characters, reason <=1000, references <=16 sorted/unique.

`event_hash = SHA256(canonical(event with only integrity.event_hash removed))`.
The previous hash is GENESIS exactly at sequence 1. The recorder fields are
covered. Re-emission compares canonical candidate + producer identity, not
new recording timestamps or sequences. Same id/content returns original receipt;
different content/context is EVENT_ID_COLLISION.

## Truth and provenance

SIMULATED is the only ingestible source in J01, including simulated operator
decisions and simulated observations. Other source enum values are vocabulary,
not enabled integrations. Source is not actor kind: a simulated operator has
actor_kind=OPERATOR and source_kind=SIMULATED. Declared reason is not private
chain of thought. Publication approval is never execution permission.

Evidence grammars: fixture:<bounded-id>, sha256:<hex64>, git:commit:<sha40>,
github:issue:<owner>/<repo>#<number>, github:pr:<owner>/<repo>#<number>@<sha40>.
No URL dereference or file path supplied by an event. A reference is not an
authenticated proof. Non-simulated evidence ingestion is disabled in J01.

## A0/A1 compatibility and reuse

A1 owns agent_id, agent_spec_id, spec_artifact_hash and registry states.
J01 actor IDs do not register agents. Fixture actors use fixture-* identifiers;
no AVAILABLE registry, active-agent count, capability or F3/F4 admission is
inferred. PR #374 remains parked and is not a dependency. The canonical byte
algorithm follows A1 / research_candidate but adds J01 validation; no import of
the Research registry (package initialization also exports its writer).
governance_tower.redaction is reused without importing its orchestrator.
The security AuditLog remains separate and unchanged.

## Errors and limitations

Closed codes are in canonical.ERROR_CODES. Errors never echo input. Unknown
versions fail closed. Future extensions require a new version and explicit
migration, never silently reinterpreted history. Hash integrity does not prove
source identity, tail completeness, human authority or economic contribution.
J01 cannot record activity that was never emitted by a producer.
