# D1-E — per-decision durability receipts (source-only)

Mission [#410](https://github.com/3a7i3/crypto-ia-terminal/issues/410), parent
[#404](https://github.com/3a7i3/crypto-ia-terminal/issues/404), D1-D #408/#409.
The verifier is a future-evidence **consistency capability**, not a certification
or authorization gate. No instrumentation is installed in the current burn-in.

`SATISFIED != CERTIFIED`; `SOURCE_PROOF != RUNTIME_PROOF`;
`CAPABILITY != AUTHORITY`; `UNKNOWN != ZERO`;
`HISTORICAL_RUNTIME_PROOF != CURRENT_RUNTIME_PROOF`;
`REJECTED_PACKET != PERSISTED_REJECTION`;
`CAPTURE_COMPLETENESS != PRODUCER_COMPLETENESS`.

## Inputs, evidence custody and native joins

`research_data.stress_d1_durability.verify_durability_chains` takes four explicit
immutable `bytes` bundles, four independently established SHA256 pins, a declared
boundary and a declared queue/read-prefix fence. It opens no paths, reads no
environment and imports no runtime services. Each JSON envelope has exactly
`boundary` and `rows`; duplicate JSON keys, nonfinite values, wrong hashes and
malformed envelopes abort. Each row must carry the exact same strict boundary
defined in [D1-D V2](D1_D_NATIVE_ATTEMPT_CONTRACT.md).

| Bundle | Required native evidence |
|---|---|
| `roster` | Independently sourced packet roster with unique `attempt_id`, `packet_id`, `trace_id`, `decision_id`, and event time in the UTC event window |
| `receipts` | Per-attempt stage ledger, globally unique `receipt_id`, native causal `sequence`, outcome/stage, aware UTC `at`, native identities and `source_id` |
| `records` | Independently captured exact UTF-8 JSONL line, its SHA256 and byte range, native packet/trace/observation joins, physical file identity and partition |
| `fsync` | Separate native syscall-return witness, unique `fsync_call_id`, outcome `RETURNED`, descriptor-to-file binding, write-range identity and aware UTC return time |

Distinct declared source IDs are required across these four roles. Reusing a
receipt source as its own fsync witness is rejected. **Distinct names do not prove
independence**: an operator/reviewer must establish acquisition, instrument trust,
immutable/root-owned custody, signer trust where applicable, and pins before any
real use. A caller can fabricate all four bundles and pins; a source-only pure
function cannot authenticate the outside world. Every output therefore retains
`custody=NOT_VERIFIED`, `receipt_source_independence=NOT_VERIFIED`,
`native_epoch_binding=NOT_PROVEN`, `actual_persistence_proof=NOT_OBSERVED` and
`per_packet_durability=NOT_PROVEN`, even for a complete consistent chain.

No current capture is admissible to this new interface merely because its
historical hashes match. Actual immutable Research staging/execution requires
a separate operator gate. No production paths, new export or `chatgpt-ro`
privilege elevation is introduced. The four historical D1-C components cannot
supply the missing native receipts or producer roster by inference.

## Explicit state machine

Receipts are sorted only by native per-attempt causal sequence, starting at 1
without gaps or duplicates. Input list order is immaterial; no stage order is
fabricated from timestamp proximity. UTC times must be nondecreasing and within
the capture fence. The verifier checks clock syntax/order, not synchronization.

| State | Permitted next states |
|---|---|
| ROOT | OBSERVATION_BUILD_ATTEMPT, NOT_ATTEMPTED, BUILD_STATE_UNKNOWN |
| OBSERVATION_BUILD_ATTEMPT | BUILD_OK, BUILD_FAILED |
| BUILD_OK | PUBLICATION_ATTEMPT, NOT_PUBLISHED |
| PUBLICATION_ATTEMPT | SUBMITTED, DROPPED, NOT_PUBLISHED |
| SUBMITTED | LISTENER_DISPATCH, NOT_DELIVERED |
| LISTENER_DISPATCH | STARTED, NOT_DELIVERED |
| STARTED | FILTER_ELIGIBLE, FILTERED_OUT, FILTER_UNKNOWN, THREW |
| FILTER_ELIGIBLE | PERSIST_ATTEMPT, THREW |
| FILTERED_OUT | RETURNED |
| FILTER_UNKNOWN | RETURNED, THREW |
| PERSIST_ATTEMPT | RECORD_VALIDATE_PASS, RECORD_VALIDATE_FAIL, VALIDATE_UNKNOWN, PERSIST_FALSE, PERSIST_THREW |
| RECORD_VALIDATE_PASS | WRITE_APPEND, APPEND_ERROR, PERSIST_FALSE, PERSIST_THREW |
| RECORD_VALIDATE_FAIL | PERSIST_FALSE |
| VALIDATE_UNKNOWN | PERSIST_FALSE, PERSIST_THREW |
| WRITE_APPEND | FLUSH, FLUSH_ERROR, PERSIST_FALSE, PERSIST_THREW |
| FLUSH | FSYNC_RETURN, FSYNC_ERROR, PERSIST_FALSE, PERSIST_THREW |
| APPEND_ERROR, FLUSH_ERROR, FSYNC_ERROR | PERSIST_FALSE, PERSIST_THREW |
| FSYNC_RETURN | PERSIST_SUCCESS, PERSIST_FALSE, PERSIST_THREW |
| PERSIST_SUCCESS | RETURNED, THREW |
| PERSIST_FALSE | RETURNED, THREW |
| PERSIST_THREW | THREW |

Terminal states: `NOT_ATTEMPTED`, `BUILD_STATE_UNKNOWN`, `BUILD_FAILED`,
`NOT_PUBLISHED`, `DROPPED`, `NOT_DELIVERED`, `RETURNED`, `THREW`.
Missing whole chain is `MISSING_CHAIN`; a valid prefix without a terminal is
`INCOMPLETE_CHAIN`, not a fabricated failure or success. An observed later stage
without its native causal predecessors is malformed and fails closed. A future
capture protocol must either deliver contiguous evidence or explicitly declare
that it cannot satisfy this contract; it must not insert synthetic predecessors.

`SUBMITTED` means native acceptance for the target delivery, **not** the current
bus's aggregate counter or caller return. The current executor can start a worker
before its post-submit counter increments. A future protocol must provide native
causal sequencing across this race; sorting wall-clock logs cannot supply it.
This verifier models one targeted RejectionStore listener delivery per attempt,
not every listener or a retry protocol. `LISTENER_DISPATCH` carries native
`listener_id` and `listener_kind=REJECTION_STORE`; all downstream receipts must
retain that listener ID. Multi-delivery/retry captures require a separately
versioned delivery-ID contract and must not be collapsed into V1.

Builder-start/skip receipts carry `producer_flags`: actionable, safe_mode,
bus_configured and listener_registered, each exact bool or null. Known contradictory
flags fail; null remains UNKNOWN. Skip reasons distinguish SAFE_MODE,
NON_ACTIONABLE and UNKNOWN_FLAGS. No safe-mode inference from missing rows.
`BUILD_OK` introduces the native observation ID and every later stage preserves it.
Failure/drop/skip/throw/false receipts require an explicit native reason.

## Eligibility and validation are separate

Filter receipts carry exact native criteria: `actionable`, `trade_allowed`,
`side`, `provenance_valid`, `symbol`, `price`. The conjunction is actionable,
denied trading, a BUY/SELL/LONG/SHORT side, and valid provenance. Known false
means an exclusion; missing criteria remain UNKNOWN unless another criterion
already proves exclusion. This is not a claim about which filter executed first.
Packet identity must already be nonempty and causally joined. No legacy
default `provenance_valid=True` is treated as native evidence.

Price/symbol validation is distinct: explicit finite numeric price > 0 and
nonempty symbol. Bool/nonfinite prices are rejected; missing price is UNKNOWN.
These typed finite-value requirements are **stricter Research admissibility**
than the frozen `_validate` implementation, not proof it enforces them. The
frozen implementation checks `price <= 0` without a finite/type guard; no actual
runtime NaN, infinite price or failure incidence is established by that source
finding. The future capture must expose actual validator outcome and all criteria.
Claimed PASS/FAIL/UNKNOWN must agree with supplied criteria. Exact captured
record price/side/symbol must agree with filter criteria on fsync chains.

## Physical bytes, midnight and durability limits

Every append/flush/fsync receipt binds the same `write` mapping:

```
file_id, write_date_utc, partition_selected_at, partition_name,
byte_start, byte_end, record_sha256
```

`file_id` must be a native physical identity including reuse/generation protection,
not merely a path string. `partition_name` is `rejections_YYYY-MM-DD.jsonl` and
must agree with the UTC date at native `partition_selected_at`. Selection must
precede write/flush/fsync. The partition can be selected before midnight and
appended after midnight, and fsync can return in a later day without changing the
open file. Never infer partition from the observation's date or fsync date.

Captured line bytes include exactly one terminal newline. Their length and SHA256
must match the half-open byte range; ranges in the same physical file cannot
overlap. The body must join packet/trace/observation and native `ts_iso` to the
event-window roster. Read-prefix fences must cover the whole record range.
Prefix hashes are declarations: this API does **not** receive or rehash full file
prefix bytes or prove continuity; the external custody gate must verify them.
An existing captured line without native fsync receipts remains
`records_without_fsync_chain`; line existence is not durability proof.

`FSYNC_RETURN` is accepted as **consistent supplied evidence** only when a separate
fsync witness and matching exact captured record exist. The fsync call ID,
observation ID, physical descriptor/file, byte range, record digest, partition
and UTC return time must agree. Fabricated or unmatched fsync claims abort.
A `PERSIST_FALSE`/throw **after** fsync can occur, including failure during close;
it is `FSYNC_ACK_WITH_PERSIST_FAILURE`, distinct from the complete successful
chain. Neither event bus success nor a returned persist bool is substituted
for syscall evidence. An fsync error may coexist with appended bytes; no loss
or absence is automatically certified.

Every roster entry has one exclusive result; sum of all `counts` equals the
declared packet roster length. Results preserve missing/incomplete chain,
build/dispatch/filter/validate outcomes, persist false/throw, listener throw,
consistent fsync chain and fsync ack with persist failure. `last_stage`, captured
record presence, late receipts and unknown flags remain visible per attempt.
This denominator is **captured packets**, not the independent D1-D opportunity
or invocation denominator; D1-D must be reconciled separately.

The declared fence has UTC `at`, `queue_state` (QUIESCENT/NOT_QUIESCENT/UNKNOWN),
and physical prefix entries (`file_id`, `byte_end`, `sha256`). Late writes through
capture cutoff are retained. Even QUIESCENT is a declaration, not authenticated
queue drainage or end-of-window completeness. Cross-clock/distributed chains
require a future clock/causality contract before admissible real use.

`fsync` return does not establish power-loss behavior, storage hardware guarantees,
directory-entry durability for newly created partitions, immutable custody,
or an independently certified current runtime. No code-only claim upgrades these.

## Future-epoch proposal, never active burn-in instrumentation

Before proposing implementation for a future authorized epoch, establish:

1. An independent universe/selection/attempt ledger with a complete boundary fence.
2. Native identity allocation, per-target dispatch sequencing, stage receipts and
   explicit failure semantics; preserve actual concurrency instead of log ordering.
3. Independent fsync descriptor/call witness and exact source-prefix acquisition;
   neither RejectionStore stats nor a witness emitted by the same writer suffices.
4. Clock quality, rotation-boundary capture, queue/quiescence verification, source
   and config/epoch provenance, immutable custody and an approved staging procedure.
5. Independent review of exact source HEAD and real-byte results in a separate
   mission. Fail-closed source capability creates no runtime authority.

The active #282/#286 epoch, runtime SHA/config, PPL/FIN, risk/sizing, Watchdog,
TESTNET/LIVE and exchange behavior remain untouched. No merge or deploy.

`D1_E_PER_PACKET_DURABILITY=NOT_PROVEN`
`D1_D_PRODUCER_COMPLETENESS=NOT_PROVEN`
`D1_NATIVE_EPOCH_BOUNDARY_BINDING=NOT_PROVEN`
`COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY=NOT_PROVEN`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`
