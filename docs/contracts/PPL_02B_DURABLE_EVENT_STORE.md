# PPL-02B — Durable Event Store Contract

Status: **GATE B1 CONTRACT FROZEN**

Mission: PPL-02B — Durable Event Store / PAPER Event Truth

Authority status: **SOURCE-ONLY, NOT WIRED TO PAPER RUNTIME**

Baseline SHA: `f9fff2f619533fcf4d4338dba2fba37ed111cb06`

## 1. Purpose and boundary

PPL-02B provides the first durable store for the existing PPL
`LedgerEvent` model. It persists and reloads immutable PAPER facts so a
caller can later perform deterministic replay through the existing pure
`paper_trading.paper_portfolio_ledger.project()` function.

PPL-02B does not:

- replace `MexcSimulator` or `PaperTradeRecorder`;
- read, rewrite, normalize, backfill, or migrate
  `databases/paper_trades.jsonl`;
- wire PPL into `core/advisor_loop.py` or any runtime entry point;
- implement the PPL-02C legacy bridge;
- implement Treasury, valuation, reconciliation, allocation, or any other
  Financial Institute responsibility;
- change signal, strategy, risk, sizing, exchange, execution, Telegram, or
  dashboard behavior.

The store has no default production path, environment-variable lookup,
singleton, or import-time filesystem side effect. A caller must supply an
explicit root directory.

## 2. Evidence baseline

### SOURCE PROOF

- `paper_trading.ledger_events.LedgerEvent` is the canonical PPL event
  envelope.
- `paper_trading.paper_epoch.PaperEpoch` is the explicit scientific epoch
  value object.
- `paper_trading.paper_portfolio_ledger.project()` is the pure replay
  authority.
- The PPL modules are not statically imported by production runtime paths.
- No PPL durable store exists at the baseline SHA.
- Both `paper_trading/mexc_simulator.py` and `core/advisor_loop.py` contain
  source-reachable legacy `PaperTradeRecorder` write paths.

### RUNTIME PROOF

- The production legacy journal was previously observed structurally valid
  with 2,324 JSONL records and two singleton OPEN lifecycles.
- This contract does not claim which source-reachable legacy writer produced
  a particular production record.
- PPL remains non-authoritative at runtime during PPL-02B.

## 3. Reused domain contract

The store persists the existing `LedgerEvent` fields exactly:

| Field | Wire rule |
|---|---|
| `event_id` | non-empty string; store-wide event identity |
| `paper_epoch_id` | non-empty string; explicit partition identity |
| `sequence` | integer, not boolean, starting at 1 per epoch |
| `event_type` | exact value from `LedgerEventType` |
| `timestamp` | finite JSON number; never used for ordering |
| `trade_id` | string or null, subject to existing event invariant |
| `decision_id` | string or null |
| `payload` | JSON-compatible mapping with string keys |
| `schema_version` | exactly `1` in PPL-02B |

PPL-02B does not create a competing event class. Deserialization produces
the existing immutable `LedgerEvent` type.

## 4. Physical layout

The store uses one append-only JSONL file per PAPER epoch:

```text
<explicit-root>/
└── epochs/
    └── <sha256(utf8(paper_epoch_id))>.jsonl
```

The digest prevents path traversal and filename ambiguity because the
existing domain model intentionally accepts any non-empty epoch string.
The original `paper_epoch_id` remains present in every record. On load, the
store recomputes the digest and verifies every embedded epoch identity; a
digest/path mismatch fails closed.

No manifest, snapshot, database, or mutable index is authoritative in
PPL-02B. A private lock file may coordinate access but contains no event
truth.

## 5. Public interface

The minimal interface is:

```python
store = DurableEventStore(root_dir)

result = store.append(expected_epoch_id, event)
events = store.load_epoch(paper_epoch_id)
```

`append()` requires the expected epoch explicitly. A mismatch between
`expected_epoch_id` and `event.paper_epoch_id` is rejected before I/O.

`load_epoch()` returns an immutable tuple ordered by authoritative
`sequence`. A missing epoch raises an explicit `EpochNotFoundError`; it is
not represented as an apparently valid empty history.

Append results use a closed vocabulary:

- `APPENDED`: one record was written, flushed, and durably synced;
- `ALREADY_EXISTS`: the same `event_id` and identical canonical event were
  already present; no bytes were appended. Before returning this result,
  the existing file and its parent directory are synced again. This makes a
  retry safe after an earlier append wrote visible bytes but reported an
  `fsync` failure.

## 6. Canonical serialization

Each event is encoded as exactly one UTF-8 JSON object followed by exactly
one LF byte (`\n`). Serialization uses:

```python
json.dumps(
    record,
    ensure_ascii=False,
    allow_nan=False,
    sort_keys=True,
    separators=(",", ":"),
)
```

The immutable `MappingProxyType`/tuple payload is recursively converted to
plain JSON objects/arrays. `dataclasses.asdict()` is not used because it
cannot copy the existing recursively frozen payload.

Serialization rejects:

- NaN and positive/negative infinity;
- non-string mapping keys;
- arbitrary Python objects or `default=str` coercion;
- unsupported event types or schema versions;
- missing or extra top-level fields;
- missing or extra payload fields for schema version 1.

Schema-version-1 payload shapes are frozen as:

| Event type | Exact payload keys |
|---|---|
| `EPOCH_CREATED` | `initial_virtual_capital`, `code_sha`, `config_snapshot_hash` |
| `POSITION_OPENED` | `symbol`, `side`, `principal`, `entry_price`, `entry_fee` |
| `POSITION_CLOSED` | `exit_price`, `exit_fee` |
| `POSITION_UNRESOLVED` | `reason` |
| `RECOVERY_COMPLETED` | `restored_count`, `unresolved_count` |

Financial/lifecycle arithmetic remains solely in the projector. Wire-shape
validation in the store is not accounting logic.

## 7. Identity contract

`event_id` identifies one canonical event across the entire explicit store
root, not merely within one epoch.

Identity checks occur before sequence checks:

1. Same `event_id` and byte-equivalent canonical event:
   sync the existing file and parent directory, then return
   `ALREADY_EXISTS`; write nothing.
2. Same `event_id` and different canonical event:
   raise `EventIdentityCollisionError`; write nothing.
3. A duplicate physical `event_id` already present on disk, even if both
   records are logically identical:
   classify the store as corrupt and fail closed. A correct idempotent append
   never creates the second physical record.

No overwrite and no last-write-wins behavior are permitted.

## 8. Ordering contract

`sequence` is the only authoritative order. Timestamp is metadata.

Within one `paper_epoch_id`:

```text
expected_sequence = last_sequence + 1
```

- empty epoch + sequence 1: accept;
- exact already-persisted event: `ALREADY_EXISTS` regardless of the current
  tail sequence;
- lower sequence with another event identity: regression error;
- higher sequence: gap error;
- no sorting, gap filling, renumbering, or silent repair.

Physical line order must already equal sequence order. `load_epoch()`
validates line order and returns it unchanged.

## 9. Epoch isolation

- One file contains exactly one `paper_epoch_id`.
- The requested epoch, filename digest, and every embedded event epoch must
  agree.
- A record from another epoch in the file is corruption.
- Sequence restarts at 1 independently for every epoch.
- Event identity remains store-wide, preventing an envelope identity from
  being reused across epochs.

## 10. Concurrency

Correctness must not depend on an undocumented single-process assumption.
Append and load operations coordinate through an advisory store-wide POSIX
file lock:

- append: exclusive lock;
- load: shared lock.

The exclusive lock covers integrity scan, identity check, sequence check,
write, flush, and sync. This prevents two processes or two store instances
from both accepting the same next sequence.

The target deployment and CI platform are Linux. Failure to acquire or use
the lock is explicit; there is no unlocked fallback.

## 11. Durable append boundary

An `APPENDED` result is returned only after:

1. complete canonical serialization;
2. integrity validation of existing store bytes;
3. one complete record write;
4. newline write as part of that record;
5. file `flush()`;
6. file `os.fsync()`;
7. parent-directory `fsync` when the epoch file is newly created.

When `<explicit-root>/epochs` or any missing parent supplied in the explicit
root is first created, every new directory entry is synced through its
parent before event bytes are appended. This ensures a synced event file is
also durably reachable through a newly-created directory hierarchy. If an
initial directory sync fails and a later retry finds an empty hierarchy, the
store reconfirms that hierarchy through the filesystem root before writing.

Short writes are detected and treated as `OSError`.

`IOError`/`OSError` from open, write, flush, file sync, directory sync, or
locking is never swallowed and never converted into success.

A failed/in-flight append may leave a truncated tail because JSONL cannot
transactionally roll back an unknown partial kernel write. The store never
truncates or repairs that evidence automatically. Every later load or append
detects the incomplete tail and fails closed until a separate, explicitly
authorized recovery mission handles it.

## 12. Fail-closed load and corruption rules

The reader processes bytes in physical order and rejects the whole
operation on any violation. It never returns a valid prefix.

Corruption includes:

- invalid UTF-8;
- an empty existing epoch file;
- a symlink or other non-regular entry in the epoch partition;
- blank records;
- malformed JSON;
- duplicate JSON object keys;
- non-object top-level JSON;
- missing final newline;
- truncated final JSON;
- unsupported `schema_version`;
- missing/extra fields or malformed field types;
- unknown `event_type`;
- filename/epoch mismatch;
- mixed epochs;
- duplicate physical event identity;
- sequence gap, regression, or duplicate sequence;
- cross-epoch reuse of an `event_id`.

JSON constants `NaN`, `Infinity`, and `-Infinity` are rejected during parse,
even though Python's default JSON decoder accepts them.

## 13. Replay separation

The store performs storage, envelope/schema, identity, ordering, and epoch
validation only. It does not compute positions, cash, PnL, fees, equity, or
legal trade transitions.

Replay remains:

```python
events = store.load_epoch(epoch_id)
state = project(events)
```

Tests must prove repeated `project(store.load_epoch(epoch_id))` calls over
identical bytes produce equal logical state.

## 14. Error taxonomy

PPL-02B uses explicit exceptions under a store-specific base error:

- `EventStoreError`
- `EpochNotFoundError`
- `EventSerializationError`
- `EventDeserializationError`
- `UnsupportedSchemaVersionError`
- `EventIdentityCollisionError`
- `StoreCorruptionError`
- `StoreEpochMismatchError`
- `StoreSequenceRegressionError`
- `StoreSequenceGapError`

Native durability/locking `OSError` failures propagate. Error messages name
the violated invariant and record number but never include secrets.

## 15. Required proof matrix

The PPL-02B test module must cover T01–T20 from the mission, including:

- first and sequential appends;
- close/reopen/reload byte and logical determinism;
- exact duplicate idempotency and conflicting identity rejection;
- sequence regression/gap and epoch contamination;
- middle corruption, truncated tail, missing newline, duplicate JSON keys,
  malformed schema, and unsupported schema version;
- separate epoch isolation and store-wide event identity;
- observed file `fsync` and newly-created-directory `fsync` paths;
- write, flush, file-sync, and directory-sync failures returning no success;
- repeated pure projection determinism;
- source proof that no legacy/runtime authority import or write path changed.

Property-style loops may be implemented with standard-library/pytest
parameterization. PPL-02B introduces no property-testing dependency.

## 16. Known limitations and non-goals

- JSONL lookup is linear; no index is authoritative.
- Store-wide identity verification scans epoch files. Correctness and
  auditability take priority over premature optimization.
- There is no automatic corruption repair, compaction, truncation, or
  deletion.
- There is no historical import or runtime bridge.
- There is no PAPER authority promotion.
- There is no Financial Institute logic.
- Power-loss behavior after an append failure is fail-closed, not automatic
  rollback.

Any relaxation or format change requires a later explicit schema/mission;
it must not be introduced silently during PPL-02B.

## 17. Source certification evidence

### SOURCE PROOF

- The complete source diff contains exactly three added files: this
  contract, `paper_trading/durable_event_store.py`, and
  `tests/paper_trading/test_durable_event_store.py`.
- No production runtime module imports or constructs `DurableEventStore`.
- `core/advisor_loop.py`, `paper_trading/mexc_simulator.py`,
  `src/paper/paper_trade_notifier.py`, strategy, risk, exchange, execution,
  Telegram, dashboard, and Financial Institute sources are unchanged.
- `databases/paper_trades.jsonl` is absent from the diff. PPL-02B neither
  reads nor writes it.
- The store reuses `LedgerEvent`, `LedgerEventType`, `Side`, and the pure
  `project()` function. It defines no competing financial event model or
  projection logic.
- The three paths reported by the full-suite scientific-data guard are
  referenced only by unchanged legacy startup/supervision sources:
  `runtime/lifecycle_manager.py`, `supervision/recovery_playbooks.py`, and
  `supervision/healing_actions.py`. PPL-02B tests use pytest `tmp_path` and
  do not reference those paths.

### RUNTIME PROOF

Final-source local tests on Python 3.12.14 / Linux:

| Proof set | Result |
|---|---:|
| PPL-02B durable-store tests | 54 passed |
| Existing PPL model/projector + PPL-02B | 157 passed |
| Complete `tests/paper_trading` regression set | 271 passed |
| Ruff format check | passed |
| Ruff lint check | passed |

The store tests execute real local file writes, flushes, file `fsync`,
directory `fsync`, close/reopen, multi-process locking, corruption reads,
and deterministic projector replay. Injected write, flush, file-sync, and
directory-sync failures never produce a success result. Retries after
failed file or initial-directory sync are separately proven.

A full-repository run collected 6,992 tests before the final isolated
directory-durability hardening: 6,941 passed, 21 failed, 9 errored, 19 were
skipped, and 3 were xfailed. All then-existing 52 PPL-02B tests passed in
that run. The final hardening was subsequently covered by the 54-test store
set and the complete 271-test PAPER regression set above.

The 30 failing/error node IDs from that repository-wide run were executed
unchanged against a detached clean baseline at
`f9fff2f619533fcf4d4338dba2fba37ed111cb06`, using the same interpreter and
dependencies:

- 19 failures and all 9 errors reproduced on baseline;
- the remaining two tests (`test_100k_memory_growth_bounded` and
  `test_market_scanner_preloads_markets_once_per_shared_exchange`) passed
  in isolation on both baseline and the PPL-02B branch, proving their
  repository-wide failures are load/order-sensitive rather than a
  reproducible PPL-02B regression.

### INFERENCE

- Because no runtime source imports the new module, the PPL store cannot
  become PAPER authority through this diff alone.
- Because event bytes and their directory entries are synced before
  success, the implementation provides the strongest POSIX durability
  boundary available through the selected JSONL primitive without adding a
  transactional database.

### UNKNOWN

- No claim is made about activation of either source-reachable legacy writer
  on a particular production VPS process without a new runtime trace.
- Actual behavior under sudden power loss depends on the production
  filesystem, mount, kernel, and storage hardware honoring POSIX `fsync`;
  this local source certification does not constitute a physical
  power-cut test.
- PR CI, review, and security-scanning status remain unknown until a PR is
  opened and those systems complete.

## 18. PPL-02B source verdict

`PPL_02B_SOURCE_CERTIFIED`

This verdict certifies the source substrate only. It does not promote PPL
to runtime authority, authorize merge, bridge the legacy journal, or begin
PPL-02C.
