# PPL-02C — Legacy Bridge Contract

Status: **PPL_02C_SOURCE_CERTIFIED**

Mission: PPL-02C — read-only legacy PAPER evidence bridge

Authority status: **OFFLINE/EXPLICIT ONLY — NOT WIRED TO PAPER RUNTIME**

Baseline SHA: `cb20d6c04f3d471dad24f401cec0b25378236268`

## 1. Purpose

PPL-02C provides a deterministic, fail-closed bridge between the legacy
`paper_trades.jsonl` evidence format and the existing PPL `LedgerEvent`
contract.

The bridge has two deliberately separate responsibilities:

1. inspect and classify one immutable-in-time snapshot of a legacy journal;
2. build a PPL import plan only when every source lifecycle is representable
   without assumptions.

The bridge never makes an incomplete historical record look complete. Missing
financial evidence is `UNRESOLVED`, not zero and not reconstructed from the
current runtime configuration.

## 2. Certified baseline

### SOURCE PROOF

- `PaperTradeRecorder` writes legacy `OPEN`/`CLOSE` JSONL records.
- Source-reachable writers exist in both `paper_trading/mexc_simulator.py` and
  `core/advisor_loop.py`.
- `PaperTradeRecorder.events()` skips malformed rows with a broad exception;
  PPL-02C must not use it as an evidence reader.
- `core/advisor_loop.py::_remediate_orphan_opens()` can rewrite the legacy
  journal during startup. A PPL-02C read must therefore prove that the file did
  not change while it was captured.
- PPL `POSITION_OPENED` requires `entry_fee`; PPL `POSITION_CLOSED` requires
  `exit_fee`; PPL replay begins with an explicit `EPOCH_CREATED` event.

### RUNTIME PROOF — production snapshot observed 2026-09-14

- source SHA-256:
  `59468b50b5c34a3eb860cc791f9f0bf3aaa0e1aeaa66edbbcabec9a5470b2fd7`;
- 2,337 complete newline-terminated JSON objects;
- 1,170 `OPEN`, 1,167 `CLOSE`, 1,170 unique trade IDs;
- three singleton `OPEN` lifecycles;
- no malformed JSON, blank rows, pair inversion, or pair timestamp regression;
- zero records carry `paper_epoch_id`;
- only 30/1,170 `OPEN` records carry finite `fee_entry_usd`;
- zero/1,167 `CLOSE` records carry `exit_fee` or `fee_exit_usd`.

The snapshot was stable during its bounded read. It is not globally quiescent:
the previous observation contained 2,324 rows, so writers remain active over
time.

### Accepted operator interpretation

The corpus is structurally valid but financially incomplete. Missing facts
remain `UNRESOLVED` and are never replaced by assumptions.

## 3. Absolute boundary

PPL-02C may add only:

- a read-only legacy evidence reader;
- deterministic lifecycle classification;
- explicit source/record provenance;
- deterministic conversion of fully evidenced lifecycles;
- an explicit, retry-safe offline application helper over PPL-02B;
- tests and this contract.

PPL-02C does not:

- modify, normalize, truncate, lock, rename, copy, or backfill the source;
- call `PaperTradeRecorder.events()` or `PaperTradeRecorder.trades()`;
- derive missing fees from `MEXC_SIM_FEE`, PnL, price movement, or any current
  configuration;
- invent a historical epoch, capital, code SHA, or config hash;
- import only the convenient subset of a snapshot;
- alter `MexcSimulator`, `advisor_loop`, notifier, strategy, risk, execution,
  exchange, Telegram, dashboard, SEC-API-01, FIN, or REAL behavior;
- become a runtime writer, dual-writer, shadow authority, or PAPER authority;
- implement any shadow, dual-write, cutover, or authority-promotion mission.

## 4. Public operations

The minimal interface is conceptually:

```python
snapshot = inspect_legacy_journal(path, source_label="databases/paper_trades.jsonl")
plan = build_legacy_import_plan(snapshot, explicit_context)
results = apply_legacy_import_plan(plan, durable_store)
```

`inspect_legacy_journal()` reads only. `build_legacy_import_plan()` is pure.
`apply_legacy_import_plan()` writes only to the explicitly supplied
`DurableEventStore`; it never resolves a default path and never touches the
legacy source.

## 5. Stable capture contract

The reader must:

1. reject a missing source;
2. reject a symlink or non-regular source;
3. open read-only with no symlink following where supported;
4. record device, inode, size, nanosecond modification time, and nanosecond
   status-change time before read;
5. read the complete byte stream through the same descriptor;
6. re-check descriptor and path identity/metadata after read;
7. reject any detected replacement, truncation, append, or mutation;
8. compute SHA-256 over the exact captured bytes.

The bridge does not attempt to make an active legacy writer cooperative. A
concurrent change is an explicit `LegacySourceChangedError`; the operator may
retry later.

## 6. Fail-closed byte and record contract

The complete snapshot is rejected on:

- an empty source;
- missing final newline for a non-empty source;
- invalid UTF-8;
- blank rows;
- malformed JSON;
- duplicate JSON object keys;
- non-object records;
- JSON `NaN`, `Infinity`, or `-Infinity`;
- unsupported event types;
- missing/invalid trade identity, timestamp, mode, side, symbol, price, or
  principal fields where applicable;
- duplicate OPEN, duplicate CLOSE, CLOSE-before-OPEN, orphan CLOSE, or
  close-timestamp regression.

No valid prefix, skipped record, repaired order, or deduplicated history is
returned.

Legacy schema versions 1 through 5 and an absent legacy schema marker are
recognized. Absence remains explicit in provenance; it is not silently
rewritten into a stored legacy row.

Only legacy modes `paper` and `futures_demo` are accepted. `live`, REAL, or an
unknown mode is rejected so the PAPER bridge cannot absorb exchange authority.

## 7. Classification contract

Each trade lifecycle receives exactly one status:

- `IMPORTABLE`: every fact required to construct its PPL lifecycle exists and
  is valid;
- `IMPORTABLE_AS_UNRESOLVED`: the OPEN is fully representable and the CLOSE
  honestly establishes that the financial outcome is not fully evidenced, so
  the lifecycle can terminate as the existing PPL `POSITION_UNRESOLVED`;
- `UNRESOLVED`: the legacy structure is coherent, but one or more facts needed
  even to construct the PPL OPEN were never recorded;
- `REJECTED`: one or more supplied facts contradict the supported legacy/PPL
  contract.

Reason codes are a closed vocabulary and are sorted deterministically.

At minimum, these conditions are `UNRESOLVED`:

- missing/null `fee_entry_usd` on OPEN;

When the matching OPEN is otherwise fully evidenced, these CLOSE conditions
are `IMPORTABLE_AS_UNRESOLVED`:

- missing/null `exit_fee`/`fee_exit_usd` on an ordinary CLOSE;
- `pnl_fee_evidence_incomplete=true`;
- `expired_on_restore` or a missing/null `exit_price`.

If their matching OPEN is itself `UNRESOLVED` or `REJECTED`, the more severe
OPEN status governs the whole lifecycle.

Invalid, negative, non-finite, contradictory, or ambiguous supplied values are
`REJECTED`, not `UNRESOLVED`.

A singleton OPEN is not inherently corrupt: it represents an open position.
It is `IMPORTABLE` only if all required OPEN evidence exists.

## 8. No inferred finance

The bridge never derives a missing fee from:

```text
gross price PnL - reported pnl_usd
```

That arithmetic cannot prove which writer produced the event, which fee policy
was active, whether stored PnL used the same convention, or how total fees
split between entry and exit.

When explicit entry and exit fees do exist, the bridge verifies that the
legacy reported `pnl_usd`, rounded to the legacy four-decimal contract, agrees
with the PPL projector's deterministic price/fee arithmetic. A disagreement is
`REJECTED`. This consistency check is intentionally not promoted to a known
financial fact when the record itself declares fee evidence incomplete or an
unknown outcome; those lifecycles remain `IMPORTABLE_AS_UNRESOLVED`.

## 9. Explicit epoch context

The source has no historical PPL epoch facts. Import planning therefore
requires an immutable `LegacyImportContext` with no defaults:

- exact expected source SHA-256;
- explicit `paper_epoch_id`;
- explicit epoch timestamp;
- explicit initial virtual capital;
- explicit code SHA;
- explicit configuration snapshot hash;
- explicit provenance declaration `EXTERNALLY_EVIDENCED`.

The context is not inferred from file timestamps, current wallet values,
environment variables, current Git HEAD, or trade PnL.

The expected source digest must equal the inspected snapshot digest. This
prevents applying an approval/context prepared for different bytes.

For a `READY` snapshot, the explicit epoch timestamp must be no later than the
earliest legacy event timestamp. The bridge rejects a context that would make
the leading `EPOCH_CREATED` event occur after evidence already assigned to
that epoch. A `BLOCKED` snapshot remains reportable even when one of its
rejection reasons is an invalid legacy timestamp; no unsafe numeric conversion
is attempted while constructing that empty plan.

## 10. Deterministic identity and ordering

The epoch event identity is a domain-separated SHA-256 of the explicit epoch
context.

Every legacy-derived event identity contains the physical line number and
exact line SHA-256 in readable form, plus a domain-separated SHA-256 of:

- bridge schema version;
- explicit logical source label;
- physical source line number;
- SHA-256 of the exact source line bytes;
- mapped PPL event type.

No clock, randomness, process state, absolute host path, or current source-file
digest participates in per-record identity. Appending new legacy rows therefore
does not change identities for an unchanged prefix. The persisted event ID
retains sufficient record provenance to locate and hash-verify its legacy line
without a mutable index. The explicit logical source label separates otherwise
identical line evidence originating from different journals without coupling
identity to a machine-specific absolute path.

PPL sequence is physical legacy order plus the leading epoch event:

```text
EPOCH_CREATED = sequence 1
legacy line 1 = sequence 2
legacy line N = sequence N + 1
```

Timestamp is never used to reorder rows.

## 11. Mapping contract

Fully evidenced records map as follows:

| Legacy evidence | PPL event |
|---|---|
| `OPEN` | `POSITION_OPENED` |
| ordinary known-outcome `CLOSE` | `POSITION_CLOSED` |
| explicit unknown-outcome close | `POSITION_UNRESOLVED` |

Mappings preserve trade ID, timestamp, symbol, normalized side, principal,
entry/exit prices, and explicit fees. `BUY/LONG` maps to `LONG`; `SELL/SHORT`
maps to `SHORT` through the existing PPL normalizer.

Legacy reported PnL, regime, score, TP/SL, and presentation fields are not
invented as new PPL accounting fields. Their original bytes remain covered by
record and source hashes.

## 12. Whole-snapshot import gate

A plan is `READY` only when:

- every physical record belongs to exactly one valid lifecycle;
- every lifecycle is `IMPORTABLE` or `IMPORTABLE_AS_UNRESOLVED`;
- explicit epoch context matches the source digest;
- the complete generated sequence passes the existing pure PPL projector.

If any lifecycle is `UNRESOLVED` or `REJECTED`:

- plan status is `BLOCKED`;
- generated event sequence is empty;
- application raises `LegacyImportBlockedError` before target-store I/O.

This prevents an apparently complete PPL epoch built from a convenient subset.

The certified production snapshot is therefore expected to be `BLOCKED`
because 1,140 OPEN records lack entry-fee evidence. A subset of the 30
fee-evidenced OPEN lifecycles may be representable, but partial-subset import is
not permitted.
PPL-02C makes that limitation deterministic and auditable; it does not conceal
it.

## 13. Offline apply semantics

Applying a `READY` plan appends events sequentially through the existing
`DurableEventStore`. PPL-02B supplies durable write, identity, order, and
idempotency guarantees.

An I/O failure may leave a valid durable prefix in the target PPL store. The
bridge does not roll it back or modify event truth. Reapplying the same plan is
safe: identical events return `ALREADY_EXISTS`, then the remaining suffix is
appended.

Application returns every `AppendResult` so idempotent replay is visible.

## 14. Deterministic report

Inspection exposes immutable provenance and counts, including:

- source label, byte length, line count, SHA-256;
- OPEN/CLOSE and legacy-schema counts;
- lifecycle status counts;
- one assessment per trade lifecycle with source line numbers and reason
  codes;
- overall `READY`/`BLOCKED` status.

The report contains no secret and does not depend on wall-clock time.

## 15. Error taxonomy

- `LegacyBridgeError`
- `LegacySourceNotFoundError`
- `LegacySourceCorruptionError`
- `LegacySourceChangedError`
- `LegacyImportContextError`
- `LegacyImportBlockedError`

Native target-store `OSError` and PPL errors propagate during offline apply.
No durability or evidence-boundary exception is swallowed.

## 16. Required proof matrix

- C01: inspect a valid paired lifecycle;
- C02: source SHA and line hashes are exact and deterministic;
- C03: inspection never changes source bytes/metadata;
- C04: appended source prefix preserves prior event IDs;
- C05: missing final newline fails closed;
- C06: malformed JSON in the middle fails closed;
- C07: duplicate JSON keys and non-finite constants fail closed;
- C08: detected source mutation/replacement fails closed;
- C09: symlink/non-regular source fails closed;
- C10: orphan CLOSE, duplicate lifecycle, inversion, and timestamp regression
  are rejected;
- C11: unknown/REAL mode and unknown side are rejected;
- C12: missing entry fee is `UNRESOLVED`;
- C13: missing exit fee maps the evidenced OPEN to an explicit PPL
  `POSITION_UNRESOLVED`;
- C14: fee-evidence-incomplete and expired restore remain `UNRESOLVED`;
- C15: no fee is inferred from PnL/current configuration;
- C16: explicit source digest and epoch context are mandatory;
- C16a: epoch creation cannot postdate the earliest imported event;
- C17: fully evidenced fixture produces strict deterministic PPL sequence;
- C18: generated events replay deterministically through `project()`;
- C19: reported-PnL contradiction blocks import;
- C20: any unresolved/rejected lifecycle yields no partial events;
- C21: two identical plans are equal;
- C22: offline apply is idempotent across retry/reopen;
- C23: target write/fsync failure never reports full success;
- C24: production legacy path is never a default or import-time side effect;
- C25: no production Python module imports or constructs the bridge;
- C26: PPL-02B, legacy journal semantics, and runtime authority remain
  unchanged.

## 17. Known limitations and next boundary

- The production snapshot cannot become a certified PPL epoch under the
  current evidence: no close contains an explicit exit fee and no record
  contains epoch identity.
- File stability is proved only across one bounded capture, not by cooperation
  with legacy writers.
- Source hashes preserve provenance but do not recover facts that were never
  recorded.
- PPL-02C does not decide a future historical-accounting policy. That belongs
  to a separately authorized semantics mission, not an adapter.
- The established architecture dependency after PPL-02C is FIN-00. Any future
  PAPER runtime-authority transition remains a separate, explicitly authorized
  mission.

## 18. Source certification evidence

### SOURCE PROOF

- The change is purely additive: one bridge module, one test module, and this
  contract document.
- No production Python module imports or constructs `legacy_ppl_bridge`.
- The bridge has no default production path, environment-derived finance,
  import-time I/O, legacy writer, runtime loop, or financial-accounting model.
- The only write operation is an explicit call to a caller-supplied
  PPL-02B `DurableEventStore`; inspection itself opens the legacy descriptor
  read-only.
- `MexcSimulator`, `advisor_loop`, notifier, PAPER execution, REAL execution,
  strategy, risk, exchange, Telegram, dashboard, SEC-API-01, FIN, and the
  tracked legacy schema are unchanged by the diff.

### RUNTIME PROOF

- PPL-02C bridge matrix: **52 passed**.
- Complete `tests/paper_trading`: **326 passed**.
- Adjacent recorder/dataset/restore/REM-C/path/notifier regression set:
  **205 passed**.
- Interrupted full-suite suffix, resumed from `test_restart_safety.py`:
  **1,068 passed**.
- Ruff formatting and lint checks on changed Python files: **clean**.
- `git diff --check`: **clean**.
- A full-suite attempt collected 7,044 tests plus one collection skip and was
  externally interrupted after 84%; it is not represented as a completed
  full-suite result.
- The 335-test set containing every failure/error observed before that
  interruption produced **305 passed, 21 failed, 9 errors** on this branch and
  exactly **305 passed, 21 failed, 9 errors** on the exact baseline commit
  `cb20d6c04f3d471dad24f401cec0b25378236268`. The failing identities and root
  causes were the same; no PPL-02C regression was introduced by that set.

### INFERENCE

- From the supplied production field counts, the current 2,337-line snapshot
  would yield a `BLOCKED` whole-snapshot plan because 1,140 OPEN records lack
  entry-fee evidence. This inference has not been promoted to runtime proof by
  copying or applying the production journal.

### UNKNOWN

- Which of the source-reachable legacy writers is exercised in live production
  remains unknown.
- Stability outside one bounded source capture remains unknown while legacy
  writers are active.
- No production import, target-store write, runtime cutover, or power-loss test
  was performed in PPL-02C.

Certification verdict: **PPL_02C_SOURCE_CERTIFIED**.
