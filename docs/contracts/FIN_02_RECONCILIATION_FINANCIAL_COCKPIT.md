# FIN-02 — Reconciliation & Financial Cockpit Contract

Status: **SOURCE IMPLEMENTATION CANDIDATE**

Parent architecture: #150
Mission: #247
Governance: #148
Dependencies:
- FIN-00 — certified
- FIN-01 — certified
- PPL-RECOVERY-01 — certified

Baseline:
`main@ab7b73597e98e2962b1650449b3d60d4fb51054f`

Runtime provenance sub-contract:
`docs/contracts/FIN_02_R1_RUNTIME_PROVENANCE.md`

Coherent passive capture sub-contract:
`docs/contracts/FIN_02_R2_COHERENT_PASSIVE_CAPTURE.md`

Passive producer sub-contract:
`docs/contracts/FIN_02_R3_PASSIVE_PRODUCER.md`

R1 rule:
PPL/F00 source identity, certified FIN-01 implementation identity and FIN-02
reconciliation implementation identity are separate provenance dimensions and
must never be silently substituted for one another.

## 1. Mission

FIN-02 reconciles and exposes financial truth without silent correction.

The operator surface must answer:
- what FIN projects;
- what PPL durably says happened;
- what the PAPER simulator currently observes;
- what external read-only observations exist when applicable;
- which facts agree;
- which differ within explicit tolerance;
- which diverge;
- which remain unresolved or semantically non-comparable.

Target verdict:

`FIN_02_RECONCILIATION_COCKPIT_CERTIFIED`

## 2. Authority boundary

FIN-02 is observational.

It does not:
- append PPL events;
- alter FIN ledger balances;
- release/reserve capital;
- modify simulator state;
- submit/cancel orders;
- call an exchange to repair a delta;
- tune strategy/risk/sizing/execution;
- infer missing marks;
- replace UNKNOWN with zero.

Reconciliation evidence can inform an operator. It cannot auto-correct accounting.

## 3. Source flow

```text
PPL durable lifecycle
        ↓
FIN-01 FinancialSnapshot
        ↓
FIN-02 reconciliation engine
   ↙          ↓             ↘
PPL replay   MEXC_SIM    exchange/API observation
              read-only      read-only / when applicable
        ↓
FinancialReconciliationSnapshot
        ↓
atomic JSON presentation artifact
        ↓
GET /api/operator/v1/financial-reconciliation
        ↓
Financial Cockpit
```

API/UI must not recompute financial truth.

## 4. Reconciliation statuses

Closed vocabulary inherited from FIN-00:
- `EXACT`
- `WITHIN_TOLERANCE`
- `DIVERGENT`
- `UNRESOLVED`

Delta sign is always:

`observed - projected`

A delta never creates a posting.

## 5. Comparability

FIN-02 adds an orthogonal comparability classification:
- `COMPARABLE`
- `NON_COMPARABLE`
- `UNAVAILABLE`
- `NOT_APPLICABLE`

`NON_COMPARABLE` and `NOT_APPLICABLE` evidence remains visible but is
excluded from the aggregate reconciliation verdict.

`UNAVAILABLE` is material unresolved evidence and therefore prevents an
aggregate certified result.

## 6. Explicit tolerance

No hidden epsilon exists.

Policy carries:
- absolute tolerance;
- relative tolerance;
- stale-after TTL.

The FIN-00 formula is used:

`abs(observed - projected) <= max(abs_tol, rel_tol * max(abs(observed), abs(projected)))`

Exact zero delta remains `EXACT`.

A non-zero delta inside explicit policy is `WITHIN_TOLERANCE`.

A known live delta outside policy is `DIVERGENT`.

## 7. Freshness

Observation freshness:
- `LIVE`
- `STALE`
- `UNAVAILABLE`
- `NOT_APPLICABLE`

A stale value may be displayed with its raw delta but cannot certify the
reconciliation record.

Future-dated observations are UNAVAILABLE, not silently clamped to LIVE.

## 8. FIN ↔ PPL semantic boundary

Directly comparable:
- cash available;
- capital reserved;
- capital unresolved;
- fees paid;
- open-position count;
- settled-position count;
- unresolved-position count.

FIN `realized_pnl` and PPL lifecycle `realized_pnl` are deliberately
`NON_COMPARABLE` while their recognition semantics differ.

FIN recognizes charged fees when they become durable financial facts.

PPL lifecycle realized PnL recognizes trade-level lifecycle outcome at close.

Displaying both is required. Subtracting them and calling the result a financial
divergence is forbidden.

## 9. Coherent capture boundary

FIN-02 runtime evidence must originate from one R2-certified passive capture.

Required lock order:

`MEXC_SIM._lock -> PPLAuthorityRuntime._lock`

The capture must:
- use the PPL authority runtime already owned by the simulator;
- freeze PPL events and simulator accounting inside one simulator critical section;
- require PPL runtime READY;
- prove simulator generation stability;
- require zero lifecycle transitions in flight;
- preserve simulator/PPL divergence rather than hiding it;
- accept valuation evidence only as explicit caller-supplied observations.

No separate PPL runtime may be injected into the capture boundary.

## 10. Passive producer boundary

FIN-02 artifact production must satisfy the R3 passive producer contract.

The source flow is:

`R2 capture -> FIN-01 snapshot -> FIN-02 reconciliation -> atomic artifact`

R3 must:
- derive FIN context only from certified R1 provenance;
- reverify FIN_CONTEXT_V1 before projection;
- use R2 capture time for valuation_as_of;
- use explicit generated_at for reconciliation freshness;
- preserve the existing closed artifact schema;
- convert ordinary build/path/write failures into a fail-passive result;
- have no production Advisor call site during source certification.

## 11. Simulator reconciliation

A simulator observation is read under the simulator's existing lock and exposes:
- cash available;
- reserved principal derived from live position principals;
- exact open trade identities;
- pending-order count;
- lifecycle transitions in flight;
- observation timestamp/provenance.

No mutation method is called.

The observation is not certifiable unless pending orders and in-flight
transitions are both explicitly known.

Exact trade identity is compared, not symbol-only membership.

## 12. Unreconciled capital

FIN-02 must not sum multiple correlated deltas and label the sum as missing
capital.

The single designated PAPER capital reconciliation metric is:

`book_capital_at_cost`

Projected FIN side:

`cash_available + capital_reserved + capital_unresolved`

Observed simulator side, only when unresolved FIN capital is zero:

`simulator_cash + simulator_reserved_principal`

`unreconciled_capital = abs(observed - projected)`

This is reconciliation evidence, not an asset and not an automatic adjustment.

If the simulator observation is absent/stale/unavailable or FIN contains
unresolved capital, `unreconciled_capital` is unavailable rather than invented.

## 13. PAPER versus real exchange

Current FIN-02 scope is PAPER.

A real exchange/account observation may be displayed read-only, but PAPER and
real-account capital are separate accounting scopes.

Therefore:

`PAPER_FINANCIAL_SNAPSHOT - REAL_EXCHANGE_ACCOUNT`

is `NOT_APPLICABLE`.

No PAPER-vs-real cash/equity delta may be used as reconciliation capital.

Future FIN-04 may define TESTNET/REAL Treasury reconciliation under a separate
certified accounting scope.

## 14. Valuation and equity

FIN-02 transports FIN-01 valuation truth unchanged.

If marks are unavailable:
- valuation status remains `UNAVAILABLE`;
- unrealized PnL remains null when not certifiable;
- certified equity remains null.

UNKNOWN != ZERO.

The cockpit must visibly distinguish unresolved/unavailable equity from numeric
zero equity.

## 15. Presentation artifact

Canonical artifact default:

`databases/financial_reconciliation_snapshot.json`

Schema:
`1.0.0`

Product:
`FIN02FinancialCockpit`

Domain:
`financial_reconciliation`

Authority:
`FINANCIAL_OBSERVATION`

Monetary Decimal values are serialized as decimal strings, not JSON floats.

The artifact binds:
- FIN snapshot identity;
- FIN-02R1 runtime provenance identity;
- certified FIN-01 source identity;
- PPL/F00 epoch source identity and configuration binding;
- explicit FIN-02 reconciliation code SHA, distinct from the FIN-01 code SHA;
- PPL source-stream digest;
- source sequence;
- FIN/source/config provenance;
- financial values;
- reconciliation policy/status;
- observation digests;
- every reconciliation record and provenance.

Writes are atomic and own only this presentation artifact.

## 16. API boundary

Endpoint:

`GET /api/operator/v1/financial-reconciliation`

The API:
- validates a closed schema;
- adds only reader-authored artifact freshness;
- does not import the FIN ledger/reconciliation engine;
- does not read PPL JSONL;
- does not instantiate MexcSimulator;
- does not call an exchange;
- does not recompute PnL/equity/deltas;
- returns structured 503 when evidence is absent/invalid.

## 17. Cockpit boundary

The Financial domain exposes:
- cash available;
- reserved/deployed capital;
- certified equity or UNAVAILABLE;
- realized/unrealized PnL;
- fees/funding;
- unresolved capital;
- unreconciled capital;
- divergence/unresolved counts;
- per-record projected/observed/delta/status;
- provenance;
- freshness;
- epoch/source identities.

The browser must not perform financial arithmetic.

## 18. Exit gates

Source:
- deterministic reconciliation identity;
- exact/tolerance/divergence semantics;
- stale/unavailable fail-closed semantics;
- semantic NON_COMPARABLE proof;
- no double-counted unreconciled capital;
- simulator exact identity comparison;
- PAPER/real scope isolation;
- passive atomic producer;
- closed-schema API;
- frontend no-fabrication behavior;
- maintained backend/frontend/cross-stack CI.

Runtime:
- FIN-02R1 runtime provenance contract satisfied;
- FIN-02R2 coherent passive capture contract satisfied;
- FIN-02R3 passive producer contract satisfied;
- active F00 source/config/epoch preserved until an explicit governed runtime activation step;
- coherent PPL/FIN/simulator snapshot produced;
- API transport fidelity;
- browser transport/render fidelity;
- freshness refresh;
- no Advisor/PPL/strategy/risk/sizing/execution mutation attributable to FIN-02.

Final verdict only after required source + runtime evidence:

`FIN_02_RECONCILIATION_COCKPIT_CERTIFIED`
