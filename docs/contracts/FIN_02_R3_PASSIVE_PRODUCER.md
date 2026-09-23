# FIN-02R3 — Passive Financial Producer

Status: **SOURCE IMPLEMENTATION CANDIDATE**

Parent mission: #247 — FIN-02
Parent architecture: #150
Governance: #148
Reference PR: #254

Dependencies:

`FIN_02_R1_RUNTIME_PROVENANCE_SOURCE_CERTIFIED`

`FIN_02_R2_COHERENT_PASSIVE_CAPTURE_SOURCE_CERTIFIED`

Certified R2 HEAD:

`280fb1c9a42b645871e5fc423a19d0c9724ea04a`

## 1. Scientific question

R1 certified runtime financial provenance.

R2 certified one coherent passive capture of:
- authoritative PPL;
- independent MEXC_SIM accounting state;
- explicit valuation evidence.

R3 must answer:

> Can one immutable R2 capture be transformed into FIN-01 financial truth,
> reconciled with FIN-02, and atomically published as the existing closed
> FIN-02 artifact without creating new authority or propagating failures into
> the active PAPER runtime?

## 2. Source flow

The only certified R3 source flow is:

```
R2 CoherentFinancialCapture
        |
        v
R1 provenance -> reconstruct FIN FinancialContext
        |
        v
verify FIN_CONTEXT_V1 digest
        |
        v
FIN-01 build_financial_snapshot()
        |
        v
FIN-02 reconcile_financial_snapshot()
        |
        v
FIN-02 build_financial_reconciliation_document()
        |
        v
atomic presentation artifact write
```

R3 does not reproduce accounting equations.

It composes already-certified FIN-01/FIN-02 functions.

## 3. No independent FinancialContext input

R3 does not accept a caller-supplied `FinancialContext`.

The context is reconstructed exclusively from:

`capture.runtime_provenance`

including:
- FIN-01 certified implementation SHA;
- asset;
- source authority;
- financial model;
- funding status/evidence;
- strategy attribution;
- experiment attribution;
- venue;
- market type.

R3 then recomputes:

`FIN_CONTEXT_V1`

and requires exact equality with:

`capture.runtime_provenance.semantic_context_digest`

Mismatch fails closed.

This prevents a caller from pairing:
- R2 financial facts from context A;
- with FIN projection semantics from context B.

## 4. R2 capture validation

Before financial projection, R3 reasserts:

- object is `CoherentFinancialCapture`;
- R2 schema version is certified;
- R2 lock-order identity is certified;
- R1 provenance epoch equals R2 PPL observation epoch;
- R1 source-stream digest equals R2 PPL observation digest;
- R1 last source sequence equals R2 PPL observation sequence.

R3 does not assume a dataclass is trustworthy merely because it was constructed
successfully earlier. A mutated/replaced test or deserialized object must still
pass these identity checks.

## 5. FIN-01 projection

R3 calls the existing certified:

`build_financial_snapshot(...)`

Inputs are only:
- frozen R2 PPL events;
- reconstructed R1 FinancialContext;
- frozen R2 valuation observations;
- R2 capture timestamp as `valuation_as_of`;
- explicit `max_mark_age_s`.

No mark is fetched.

No missing valuation is fabricated.

After projection, R3 additionally requires exact identity continuity for:
- paper epoch id;
- source-stream digest;
- last source sequence;
- semantic-context digest;
- FIN-01 code identity;
- PPL source code identity;
- PPL config hash.

## 6. Reconciliation time semantics

Two times are intentionally distinct:

### valuation_as_of

`capture.captured_at`

This is the instant against which the valuation evidence frozen in R2 is
classified by FIN-01.

### reconciliation/generated_at

Explicit `generated_at` supplied to R3.

This is used as:
- FIN-02 reconciliation `as_of`;
- artifact generation time.

R3 requires:

`generated_at >= capture.captured_at`

This means a delayed producer cannot make old PPL/simulator observations look
fresh merely by reusing the capture timestamp.

## 7. FIN-02 reconciliation

R3 calls:

`reconcile_financial_snapshot(...)`

with:
- FIN-01 snapshot produced from the same R2 capture;
- R2 PPL observation;
- reconciliation code SHA from R1 provenance;
- explicit reconciliation policy;
- generated_at as reconciliation as_of;
- R2 simulator observation;
- optional caller-supplied external read-only observation.

R3 performs no auto-correction.

A coherent simulator/PPL divergence remains a FIN-02 divergence.

## 8. External account boundary

R3 never calls an exchange.

An `ExternalFinancialObservation` may be supplied explicitly by a future
caller.

If supplied, it remains governed by existing FIN-02 semantics:
PAPER versus real account is NOT_APPLICABLE as an accounting subtraction.

Absence of external evidence is allowed.

## 9. Artifact schema

R3 deliberately does not change the existing closed artifact schema:

- schema version: `1.0.0`;
- product: `FIN02FinancialCockpit`;
- authority: `FINANCIAL_OBSERVATION`.

No `capture_id` field is injected into the browser/API document.

Reason:
the existing artifact already cryptographically binds:
- FIN snapshot identity;
- FIN semantic/valuation state through `financial_snapshot_id`;
- PPL and simulator observation digests through `reconciliation_id`;
- source stream digest;
- code/config identities.

Adding a new top-level field would require an API/frontend schema migration with
no new financial meaning.

R3 therefore keeps explicit:
- `capture_id`;
- `runtime_provenance_id`;
- `product_id`;

inside the internal `PassiveFinancialProduct`.

## 10. R3 product identity

Namespace:

`FIN02_PASSIVE_FINANCIAL_PRODUCT_V1`

The R3 product id binds:
- R3 schema version;
- R2 capture id;
- R1 runtime provenance id;
- FIN-01 financial snapshot id;
- FIN-02 reconciliation id;
- generated_at;
- max mark age;
- absolute tolerance;
- relative tolerance;
- stale-after threshold.

Same inputs must reproduce the same product id.

## 11. Pure build versus artifact I/O

R3 has two explicit layers.

### Pure layer

`build_passive_financial_product(...)`

Properties:
- deterministic;
- no file write;
- no environment read;
- no wall-clock read;
- no exchange read;
- no simulator mutation;
- no PPL append;
- no FIN ledger mutation.

### I/O layer

`run_passive_financial_producer(...)`

Only allowed owned mutation:
atomic replacement of the FIN-02 presentation artifact.

It uses the existing certified writer:

`write_financial_reconciliation_document(...)`

## 12. Fail-passive contract

`run_passive_financial_producer(...)` must not raise an ordinary exception to
its future runtime caller.

Failures are converted to:

`PassiveFinancialProducerStatus.FAILED`

with:
- capture id when available;
- runtime provenance id when available;
- target artifact path;
- exception type;
- exception message.

Examples:
- provenance mismatch;
- invalid R2 boundary;
- invalid temporal ordering;
- FIN projection failure;
- reconciliation failure;
- document construction failure;
- invalid artifact path;
- filesystem/write failure.

A producer failure must never:
- append PPL;
- alter simulator capital/positions/orders;
- alter FIN ledger truth;
- submit/cancel an exchange order;
- affect strategy/risk/sizing/execution state.

## 13. Existing artifact on build failure

All financial construction occurs before artifact write.

Therefore a build/provenance/reconciliation failure must not replace a
previously-valid artifact.

The atomic writer remains responsible for file-level replacement semantics.

An I/O durability error may concern the observational artifact itself; such an
error is still fail-passive with respect to all trading/accounting authorities.

## 14. Runtime activation boundary

R3 source certification does not wire the producer into Advisor.

R3 must have no production call site during this subphase.

`ADVISOR_RESTART=NO`

`ACTIVE_F00_MUTATION=NO`

`PPL_APPEND=NO`

`EXCHANGE_READ_OR_WRITE=NO`

`FIN_LEDGER_MUTATION=NO`

`STRATEGY_RISK_SIZING_EXECUTION_CHANGE=NO`

`RUNTIME_PRODUCER_ACTIVATION=NO`

## 15. Runtime threat boundary carried from R2

R3 inherits the R2 threat boundary.

Source certification proves composition against the single in-process
PPL_AUTHORITY runtime model.

It does not prove that an unauthorized second external process is incapable of
writing the active DurableEventStore.

That remains a runtime proof requirement.

## 16. Source exit criteria

R3 is source-certified only when:

- R1 remains certified;
- R2 remains certified;
- FinancialContext is derived only from R1 provenance;
- FIN_CONTEXT_V1 is reverified;
- FIN-01 snapshot identity continuity is reverified;
- valuation_as_of is the R2 capture instant;
- reconciliation as_of is explicit generated_at;
- generated_at cannot predate capture;
- no external market/exchange fetch exists;
- simulator divergence is preserved;
- closed artifact schema 1.0.0 remains accepted;
- product identity is deterministic;
- build failures leave previous artifact untouched;
- write/path failures return FAILED without propagation;
- no production caller is introduced;
- full maintained CI is green on the exact candidate HEAD;
- Semgrep is green;
- no active F00 runtime mutation occurs.

Target sub-verdict:

`FIN_02_R3_PASSIVE_PRODUCER_SOURCE_CERTIFIED`

This is not the final FIN-02 verdict and does not authorize runtime activation.
