# FIN-02R4 — Governed Runtime Activation Proof

Status: **SOURCE IMPLEMENTATION ACTIVE / RUNTIME NOT STARTED**

Parent mission: #247 — FIN-02
Parent architecture: #150
Governance: #148
Reference PR: #254

Certified dependencies:

- `FIN_02_R1_RUNTIME_PROVENANCE_SOURCE_CERTIFIED`
- `FIN_02_R2_COHERENT_PASSIVE_CAPTURE_SOURCE_CERTIFIED`
- `FIN_02_R3_PASSIVE_PRODUCER_SOURCE_CERTIFIED`

Certified R3 HEAD:

`3dbdcbee97dc7c2c1943c88df4d5e513ca31a079`

This R4 source phase does **not** authorize deployment, restart or runtime activation.
It defines the evidence required before runtime activation can be certified.

## 1. Mission

R1-R3 proved the source-level financial chain:

```
authoritative PPL provenance
        ↓
coherent passive PPL + MEXC_SIM capture
        ↓
FIN-01 financial snapshot
        ↓
FIN-02 reconciliation
        ↓
fail-passive atomic observational artifact
```

R4 must prove that this chain can be activated in the real Advisor process
without silently changing authority, cadence, financial semantics or the active
F00 experiment.

The required runtime question is:

> Can the certified R1-R3 producer run inside the already-authoritative PAPER
> process as a bounded, fail-passive observer, with one canonical artifact
> path, one PPL writer authority, explicit source/config/epoch governance and
> reproducible runtime evidence?

## 2. Absolute authority boundary

R4 remains observational.

FIN-02 R4 must never:
- submit, cancel or modify an exchange order;
- append or rewrite PPL events;
- alter MEXC_SIM cash, positions or orders;
- mutate FIN accounting truth;
- alter strategy, signal, gate, risk, sizing or execution decisions;
- start a second MEXC_SIM;
- start a second PPL authority runtime;
- start a second exchange client;
- create an independent background trading loop;
- silently rotate the active F00 epoch;
- silently replace the active F00 config.

The only R3-owned mutation that may become active is atomic replacement of the
FIN-02 observational artifact.

## 3. Required proof track A — real passive caller placement

R4 must identify the exact production call site in `core/advisor_loop.py`.

The preferred integration pattern is the existing end-of-cycle passive
observability boundary already used by canonical operator/runtime snapshot
writers.

The source proof must establish:
- exact function / surrounding lifecycle location;
- execution occurs after the cycle's decision/execution work;
- no call occurs inside signal, gate, risk, sizing or order submission code;
- the existing live `_virtual_portfolio` / MEXC_SIM reference is injected;
- no new simulator or PPL runtime is instantiated;
- no exchange client is constructed by FIN-02;
- the call is wrapped so producer failure cannot escape into the Advisor loop;
- no new background thread is required.

Before runtime activation, tests must prove that producer exceptions do not
change control flow of the Advisor cycle.

## 4. Required proof track B — bounded cadence

FIN-02 must not write on every arbitrary read request and must not spin in a
dedicated polling thread.

The repository already contains a certified passive precedent:

`OperatorSnapshotWriter.maybe_refresh(...)`

with a bounded default cadence of approximately 30 seconds.

R4 must define and test its own explicit cadence policy.

Required evidence:
- cadence value is configuration/constant evidence, not implicit timing;
- calls inside the minimum interval are skipped without failure;
- first eligible call writes;
- next eligible call writes only after the interval;
- a failed write does not alter trading control flow;
- cadence state is process-local observational state only;
- restart resets cadence state without altering financial truth;
- no catch-up burst occurs after a delay.

The exact cadence selected by R4 must be documented in source and runtime
evidence. Reusing a 30-second passive cadence is allowed only after source proof,
not by assumption.

## 5. Required proof track C — canonical artifact path

Existing FIN-02 artifact default:

`databases/financial_reconciliation_snapshot.json`

Existing override:

`FINANCIAL_RECONCILIATION_SNAPSHOT_PATH`

R4 must prove one canonical runtime path for both producer and Operator API
reader.

Required source/runtime evidence:
- producer effective path;
- reader effective path;
- exact path equality;
- path resolves to the intended observational database location;
- path is not PPL event storage;
- path is not legacy paper-trade storage;
- path is not an exchange credential/config path;
- parent directory is writable by the Advisor service user;
- artifact is a regular file after first successful write;
- atomic temporary files are created only in the same destination directory;
- API reads the exact artifact produced by R3;
- stale/missing artifact remains honest 503/STALE behavior.

No second FIN-02 artifact path may silently become an alternative authority.

## 6. Required proof track D — single active PPL writer

R2 source certification proved in-process causal coherence under the
single-authority runtime contract.

R4 must add runtime evidence that there is no second active PPL writer.

The proof must cover:
- one active `crypto-advisor.service` process / MainPID;
- no duplicate Advisor process;
- no orphan process running the same repository/runtime;
- no SHADOW writer attached while PPL_AUTHORITY is active;
- no migration/import/replay tool concurrently writing the active PPL store;
- no second process holding an authority-writer role;
- active PPL store path identified explicitly;
- PPL event sequence remains monotonic;
- writer ownership matches the active authoritative runtime.

Evidence should include process/service facts and store-level facts.

A simple statement that "only one process should exist" is insufficient.

If writer exclusivity cannot be demonstrated, R4 must fail closed.

## 7. Required proof track E — fail-passive behavior in the real process

R3 proved fail-passive behavior in source tests.

R4 must prove it in the actual Advisor runtime.

At minimum, runtime evidence must demonstrate both:

### Successful production

- Advisor remains active;
- FIN-02 artifact is created/refreshed;
- generated timestamp advances according to bounded cadence;
- PPL epoch/source/config identity remains coherent;
- financial reconciliation document passes the closed schema reader;
- API returns the artifact without recomputation.

### Forced/controlled observational failure

A safe, reversible failure mode must be used to prove:
- FIN-02 producer returns/logs failure;
- Advisor cycle continues;
- service remains active;
- no order/execution authority changes;
- no PPL append occurs because of FIN-02 failure;
- simulator state is not changed by FIN-02;
- last valid artifact is not replaced by an invalid build result.

The failure injection must not involve corrupting PPL or exchange state.

## 8. Required proof track F — F00 restart/source/config/epoch governance

Runtime activation cannot silently violate F00 experiment governance.

Before any restart or deployment, capture a pre-activation evidence bundle:
- active service MainPID;
- active source SHA evidence;
- worktree state;
- active F00/PPL epoch id;
- PPL EPOCH_CREATED source code SHA;
- PPL config snapshot hash;
- last PPL sequence;
- current PPL stream digest;
- current simulator quiescence evidence;
- existing FIN-02 artifact state, if any.

Then classify the activation.

### Case 1 — no process restart

If activation can be proven without changing the active process:
- active source/config/epoch must remain bit-identical;
- runtime proof must explain how the new producer code is present without
  changing the process image.

This case is expected to be uncommon and must not be asserted without evidence.

### Case 2 — governed restart/deployment

If new FIN-02 source must be deployed into Advisor:
- restart requires explicit operator authorization;
- deployed Git SHA must be recorded;
- worktree must be clean or explicitly classified;
- process_instance_id / MainPID transition must be recorded;
- F00 config must be compared pre/post;
- active paper epoch handling must be explicit;
- no silent epoch rotation is allowed;
- if the governance contract requires a new epoch because source changed, that
  requirement must be followed rather than bypassed;
- if epoch continuity is permitted across a source-only observational change,
  that permission must be explicitly justified and recorded before restart.

R4 must not decide this by convenience.

## 9. Runtime source SHA versus financial semantic identities

R4 must preserve the identity separation certified in R1:

```
active F00/PPL source identity
!= FIN-01 certified semantic implementation identity
!= FIN-02 reconciliation implementation identity
```

Deployment SHA is runtime evidence.

It must not silently overwrite:
- FIN-01 certified semantic SHA;
- PPL EPOCH_CREATED source SHA;
- reconciliation code identity.

Any mapping between repository/deployment SHA and one of these semantic
identities must be explicit.

## 10. Runtime reconciliation-code identity

Before activation, R4 must define exactly what value is supplied as:

`reconciliation_code_sha`

The value must identify the FIN-02 reconciliation implementation actually
executing.

It must be:
- non-empty;
- reproducible from governed deployment evidence;
- distinct from the certified FIN-01 semantic implementation SHA;
- recorded in the produced artifact;
- traceable to the deployed source.

No placeholder or test SHA is permitted in runtime evidence.

## 11. Valuation evidence activation

R2/R3 accept explicit valuation observations and never fetch marks themselves.

R4 must identify the real source of valuation evidence, if enabled.

Required proof:
- source object already exists in Advisor;
- FIN-02 does not instantiate a second market/exchange client;
- mark source id / venue / market type are explicit;
- source timestamp is evidence-backed;
- unavailable marks remain unavailable;
- no stale mark is relabeled fresh;
- valuation failure remains fail-passive.

If no certified runtime valuation source is available, R4 must activate with
missing valuation evidence rather than fabricate marks.

## 12. External account evidence

External real-account evidence is optional.

R4 must not block PAPER financial reconciliation merely because real-account
evidence is absent.

If external evidence is connected:
- it must come from an already-existing read-only observer;
- FIN-02 must not instantiate a new exchange client;
- PAPER versus real account remains NOT_APPLICABLE as a subtraction;
- external evidence failure must not fail the PPL/FIN/simulator capture.

## 13. Required source tests before VPS activation

Before any runtime deployment, source tests must prove:
- exact caller placement contract;
- cadence skip/write behavior;
- no background thread;
- no new simulator/runtime/exchange construction;
- fail-passive caller wrapper;
- canonical producer/reader path equality;
- R1/R2/R3 semantic continuity;
- artifact closed-schema compatibility;
- producer failure cannot alter Advisor cycle result/control flow;
- no write outside the FIN-02 artifact writer.

Full maintained CI and Semgrep must be green on the exact R4 source candidate
HEAD before VPS activation.

## 14. Required pre-restart runtime evidence

Before a governed restart, record:
- UTC timestamp;
- hostname;
- service state;
- MainPID;
- ExecMainStartTimestamp;
- command line;
- deployed repository HEAD;
- worktree status;
- active PPL epoch id;
- PPL source SHA;
- PPL config hash;
- PPL last sequence;
- PPL stream digest;
- simulator cash;
- simulator open-position count;
- lifecycle transitions in flight;
- pending-order count;
- active FIN-02 artifact path;
- artifact hash/mtime if present.

This becomes the immutable pre-activation comparison point.

## 15. Required post-restart runtime evidence

After restart/deployment, record:
- new MainPID/process instance;
- deployed source SHA;
- service active state;
- F00 config comparison;
- epoch continuity/rotation verdict;
- PPL last sequence and digest;
- simulator quiescence;
- FIN-02 producer first eligible run;
- FIN-02 artifact path;
- artifact SHA-256;
- artifact mtime;
- artifact schema validation;
- API read result;
- artifact freshness;
- reconciliation overall status;
- producer error state if any.

No final verdict may rely only on journal text.

## 16. Controlled fail-passive runtime proof

R4 must include one reversible observational failure proof.

Acceptable categories include:
- temporarily unwritable dedicated FIN-02 artifact target in an isolated test
  path;
- deliberately invalid dedicated FIN-02 output path in a controlled source/test
  activation;
- injected writer failure through a test-only/runtime-proof mechanism that
  cannot affect PPL or exchange state.

The proof must demonstrate:
- failure observed;
- Advisor remains healthy;
- PPL authority remains healthy;
- no PPL event is attributable to the failed FIN-02 write;
- no simulator mutation is attributable to FIN-02;
- recovery on the next valid eligible refresh.

Do not corrupt the canonical PPL store to test fail-passivity.

## 17. Documentation requirements

Every R4 execution step must be recorded in #247.

At minimum record:
- exact source candidate HEAD;
- source test/CI evidence;
- operator authorization for any restart/deployment;
- pre-runtime evidence bundle;
- deployment/restart evidence;
- post-runtime evidence bundle;
- fail-passive proof;
- final R4 verdict.

PR #254 must retain:
- certified R1 HEAD;
- certified R2 HEAD;
- certified R3 HEAD;
- R4 candidate/runtime HEAD;
- explicit statement that final FIN-02 certification is still separate.

## 18. R4 stop conditions

Stop and issue a remediation verdict if any of the following occurs:
- second active PPL writer cannot be excluded;
- PPL epoch/source/config governance becomes ambiguous;
- producer path differs from API reader path;
- FIN-02 failure propagates into Advisor cycle control flow;
- producer creates a second simulator/PPL runtime/exchange client;
- artifact schema becomes invalid;
- PPL or simulator state is mutated by FIN-02;
- active F00 source/config/epoch changes without governed authorization;
- runtime reconciliation code identity cannot be proven.

## 19. R4 exit criteria

R4 may be certified only when all six required proof tracks are complete:

1. **Caller placement** — exact passive end-of-cycle production call site proven.
2. **Cadence** — bounded process-local cadence proven.
3. **Artifact path** — one canonical producer/reader path proven.
4. **Single PPL writer** — source + runtime exclusivity evidence proven.
5. **Fail-passive runtime** — successful and controlled-failure behavior proven.
6. **F00 governance** — restart/source/config/epoch handling explicitly
   authorized and evidenced.

Target verdict:

`FIN_02_R4_GOVERNED_RUNTIME_ACTIVATION_CERTIFIED`

R4 certification still does not automatically imply final FIN-02 closure.
After R4, FIN-02 must receive one explicit final mission-level certification
verdict against the complete FIN-00 → FIN-02 contract chain.


## 20. Source-side implementation boundary

The R4 source candidate introduces the runtime activation boundary without
activating it.

Implemented source components:

- `observability/financial_paths.py`
  - one neutral canonical artifact path contract;
  - default `databases/financial_reconciliation_snapshot.json`;
  - existing `FINANCIAL_RECONCILIATION_SNAPSHOT_PATH` override preserved;
  - producer and API reader consume the same path contract.

- `observability/financial_runtime_writer.py`
  - activation OFF by default through `FIN02_RUNTIME_ENABLED`;
  - explicit required provenance inputs when enabled;
  - process-local 30-second default bounded cadence;
  - cadence advances on failed eligible attempts, preventing retry bursts;
  - no thread, simulator, PPL runtime or exchange-client construction;
  - missing valuation/external evidence remains missing;
  - R2 capture and R3 producer failures are returned as observational FAILED
    results rather than escaping into trading control flow.

- `core/advisor_loop.py`
  - one bootstrap of the passive writer before the main loop;
  - exact caller placement after the canonical operator snapshot attempt and
    before end-of-cycle watchdog completion;
  - existing live `_virtual_portfolio` is injected;
  - no new trading/runtime authority is constructed;
  - defense-in-depth `try/except` prevents observer failure from escaping the
    Advisor cycle.

- `tests/financial_institute/test_fin_02_r4_runtime_activation_source.py`
  - disabled-by-default activation;
  - mandatory explicit provenance;
  - canonical producer/reader path equality;
  - first-write / cadence-skip / next-eligible-write behavior;
  - no retry burst after failure;
  - producer/capture failure passivity;
  - no background or authority constructors;
  - source assertion for exact Advisor end-of-cycle placement.

Runtime remains explicitly unstarted:

`ADVISOR_RESTART=NO`
`VPS_DEPLOYMENT=NO`
`ACTIVE_F00_MUTATION=NO`
`RUNTIME_PRODUCER_ACTIVATION=NO`

The source candidate must receive exact-HEAD maintained CI and Semgrep evidence
before any runtime activation can be considered.  Runtime tracks D/E/F remain
separate and require the pre-activation evidence bundle plus explicit operator
authorization before any restart or deployment.


## 20. Source-side forensic findings

R4 source audit identified one existing dormant integration rather than a need
for a new caller.

### Bootstrap

In `core/advisor_loop.py`, FIN-02 bootstrap:
- imports `build_financial_runtime_writer_from_env(...)`;
- constructs no simulator, PPL runtime or exchange client;
- returns `None` when `FIN02_RUNTIME_ENABLED` is absent/false;
- catches configuration/bootstrap failure and leaves the observer disabled.

Runtime activation is therefore OFF by default.

### Exact caller

The single Advisor caller is located in the end-of-cycle observational block:

`_fin02_runtime_writer.maybe_refresh(_virtual_portfolio)`

It executes:
- after the canonical operator snapshot block;
- after decision/execution work for the cycle;
- before the existing watchdog end-of-cycle marker;
- inside a defensive `try/except`.

The caller passes exactly one positional runtime object:
the already-existing `_virtual_portfolio`.

It passes no valuation observer, no external-account observation and no second
runtime object.

### Cadence

`FinancialReconciliationRuntimeWriter` owns process-local cadence with:
- default interval: 30 seconds;
- monotonic clock for eligibility;
- wall clock only for observation timestamps;
- cadence advanced on every eligible attempt, including failure;
- no retry burst after failure/delay;
- no background thread.

R4 source hardening now rejects a configured interval <= 0.
Enabled runtime cadence must therefore be finite and strictly positive.

### Artifact path

Producer and API reader share:

`observability.financial_paths`

Canonical default:

`databases/financial_reconciliation_snapshot.json`

Override:

`FINANCIAL_RECONCILIATION_SNAPSHOT_PATH`

R4 source hardening now rejects an empty/whitespace-only override instead of
allowing it to collapse to the current directory.

## 21. Source-side proof tests

Dedicated source tests:

`tests/financial_institute/test_fin_02_r4_runtime_activation_source.py`

prove:
- disabled-by-default activation;
- explicit provenance required when enabled;
- shared producer/reader path contract;
- first eligible write then cadence skip;
- next eligible write only after interval;
- failed attempt advances cadence and does not burst;
- producer failure returns FAILED rather than raising;
- no background thread / simulator / PPL-runtime / ccxt constructor in the
  runtime writer;
- Advisor caller ordering at the end-of-cycle boundary;
- defensive outer fail-passive wrapper;
- AST proof that the Advisor caller passes exactly one argument:
  `_virtual_portfolio`;
- AST proof that the runtime writer imports no exchange, MexcSimulator or
  PPLAuthorityRuntime module;
- enabled runtime rejects zero/negative/non-finite cadence;
- empty artifact-path override fails closed.

## 22. Source-side certification boundary

Source-side certification may conclude only:

`FIN_02_R4_SOURCE_ACTIVATION_READY`

This verdict means:
- caller placement is source-proven;
- cadence is source-proven;
- fail-passive wiring is source-proven;
- canonical path contract is source-proven;
- source CI is green.

It does **not** mean:
- runtime enabled;
- VPS deployed;
- Advisor restarted;
- second-writer exclusivity proven at runtime;
- F00 epoch/source/config governance completed;
- fail-passive behavior proven in the real process.

The full R4 verdict remains:

`FIN_02_R4_GOVERNED_RUNTIME_ACTIVATION_CERTIFIED`

and requires the VPS/runtime evidence defined earlier in this contract.
