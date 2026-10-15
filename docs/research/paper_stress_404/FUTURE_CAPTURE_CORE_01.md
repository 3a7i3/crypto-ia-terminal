# RESEARCH-CAPTURE-CORE-01 — isolated laboratory core

Mission #416 ; parent #414 ; contract #415 ; base
`9aacc6bc3199fe571ac1fbfb74845673d4b09921`.

## Delivered boundary

`research_data.future_capture_core.BoundedCapture` ingests only caller-supplied
immutable JSON bytes for one explicitly declared stream/producer boot. It keeps
exact bytes, rejects identity/sequence/clock-domain contradictions and malformed
JSON (duplicate keys/nonfinite floats including exponent overflow), bounds count,
total bytes and event bytes, and freezes a tuple plus canonical hash manifest.

There is no file writer, socket, environment access, CLI, thread, service, live
collector or import into production. It generates no attempt/packet/receipt/syscall
ID, no clock or boundary, and no fsync evidence. The payload is preserved, not
interpreted as admitted D1-D/E rows; UNKNOWN selection is not converted to false.
This implements **C1_CORE_ONLY**, not the complete C1 native capture pipeline.

## Important limits

- All identities, clocks, sequences and inputs remain declarations. A gap is the
  difference in supplied sequence numbers, not independently proven event loss.
- A first supplied sequence >1 records the declared initial gap. Empty input or
  no observed gaps never proves completeness. All outputs retain NOT_PROVEN.
- Refused records are not retained; only bounded refusal counters survive.
  Event IDs are tracked for retained records only. Valid capacity refusals advance
  observed sequence/clock; retries of those sequences are rejected, not deduplicated.
  Invalid events leave that cursor unchanged and make capture INCOMPLETE.
- Saturation never evicts earlier bytes. Calling seal is a local immutable freeze,
  not a producer/queue fence, persistent commit or custody handoff.
- Limits cover retained bytes/count and event-ID cardinality. Python object overhead,
  transient decoder allocations and seal allocations require later benchmark;
  no RSS/CPU bound or hardware claim is asserted. Individual raw size is checked
  before decoding. Refusal counter labels are fixed, not attacker-supplied.
- Numeric sequence counters are Python integers; their magnitude is bounded by
  input size, not a fixed machine-word protocol. Wall-clock synchronization and
  event-time window admission are future validators, not inferred here.
- No roster acquisition, syscall witness, disk segments, campaign quotas,
  signing/anti-rollback, exporter/adapters, retries/group-fsync or production
  hooks are implemented. Each requires its separate contract/gates and tests.

Malformed events raise EvidenceIntegrityError; capacity refusals return False.
Append after seal raises CAPTURE_SEALED without changing the sealed snapshot.
Callers must handle every refusal; silently discarding one does not become
acceptable merely because counters exist.

## Verification and acceptance

Synthetic tests exercise count/byte saturation without eviction, initial gaps,
duplicates, sequence/time/boot/epoch/config/domain contradictions, immutable
snapshot and caller mutation, bad limits, malformed/mutable bytes, duplicate
JSON keys, unused nested NaN/Infinity/1e400 and unknown payload preservation.
Tests are local laboratory evidence, never native producer receipts.

Reproducible targeted command in isolated development environment:

```bash
PYTHONPATH="$PWD" python -m pytest -q -c /dev/null --noconftest \
  tests/research_data/test_future_capture_core.py \
  tests/research_data/test_stress_d1_producer_denominator.py \
  tests/research_data/test_stress_d1_producer_attempts.py \
  tests/research_data/test_stress_d1_durability.py
```

This deliberately bypasses repository runtime fixtures for pure-source targeted
verification; it does not replace full repository CI at the final PR HEAD.
Local results and exact HEAD CI are recorded in the PR/checkpoint, not assumed
from past PASS. No baseline or production test is modified.

`FUTURE_CAPTURE_CORE=FOR_SOURCE_REVIEW`
`NATIVE_CAPTURE_PIPELINE=NOT_IMPLEMENTED`
`D1_D_PRODUCER_COMPLETENESS=NOT_PROVEN`
`D1_E_PER_PACKET_DURABILITY=NOT_PROVEN`
`FUTURE_CAPTURE_ACTIVATION=DENIED`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`

Rollback: revert the module, its tests and this document only. No deployed
component or active experiment is changed. C2–C6 are not satisfied by this core.
