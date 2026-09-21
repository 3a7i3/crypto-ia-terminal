# FIN-01 — PAPER Financial Institute v1

Status: **SOURCE IMPLEMENTATION CANDIDATE**

Parent: #150  
Mission: #245  
Governance: #148  
Dependency: #244 FIN-00  
Baseline: `main@ab6d08f525230f9ce21bd5ce07354849f4d672d0`

## 1. Mission

Implement a deterministic PAPER Financial Institute over certified PPL facts.

FIN-01 remains source-only. It does not deploy to the active F00 runtime and
does not become an execution or exchange authority.

Canonical flow:

```text
PPL durable events
    ↓
PPL → FinancialEvent adapter
    ↓
double-entry FIN ledger
    ↓
Treasury projection
    + explicit valuation observations
    ↓
immutable FinancialSnapshot
```

## 2. Authority boundary

PPL remains authoritative for lifecycle facts:

- EPOCH_CREATED;
- POSITION_OPENED;
- POSITION_CLOSED;
- POSITION_UNRESOLVED;
- RECOVERY_COMPLETED.

FIN is authoritative only for the deterministic financial interpretation of
those facts under the FIN-00 contract.

FIN never rewrites PPL.

FIN-01 contains no:

- BUY/SELL route;
- exchange write client;
- strategy mutation;
- risk/sizing mutation;
- active F00 config mutation;
- runtime service activation.

## 3. Supported financial model

FIN-01 implements only:

`PAPER_LINEAR_PRINCIPAL_V1`

Current PPL does not durably carry the complete facts required for
exchange-faithful spot or derivative accounting.

Therefore:

- `SPOT_QUANTITY` fails closed;
- `DERIVATIVE_CONTRACT` fails closed.

A swap/futures market label does not authorize FIN to invent quantity,
contract-size, leverage, margin or funding semantics.

## 4. Explicit projection context

Every projection receives an immutable `FinancialContext`.

Required/provenance-bearing fields include:

- FIN implementation code SHA;
- reporting asset;
- source authority;
- financial model;
- funding evidence status;
- optional explicit strategy id/version;
- optional explicit experiment id;
- optional venue/market type.

Strategy, experiment, venue and market-type fields are never inferred from
today's runtime configuration after the fact.

## 5. PPL → FinancialEvent adapter

The adapter first validates the complete PPL epoch through canonical PPL replay.

Financially material mappings:

### EPOCH_CREATED

- Debit CASH_AVAILABLE
- Credit EPOCH_CAPITAL

### POSITION_OPENED

- Debit CAPITAL_RESERVED
- Debit FEES_EXPENSE when entry fee > 0
- Credit CASH_AVAILABLE

### POSITION_CLOSED

- release CAPITAL_RESERVED to CASH_AVAILABLE;
- post gross price gain/loss against REALIZED_TRADING_PNL;
- post exit fee to FEES_EXPENSE.

Gross price PnL uses the certified PPL linear principal formula.

### POSITION_UNRESOLVED

- Debit CAPITAL_UNRESOLVED
- Credit CAPITAL_RESERVED

No cash release and no synthetic PnL.

### RECOVERY_COMPLETED

No financial posting under FIN-00.

The marker remains present in the source-stream digest and last source
sequence, so it still changes snapshot provenance.

## 6. Source stream identity

FIN-01 computes SHA-256 over canonical PPL JSON records in sequence order.

The digest binds the complete source population used for a snapshot.

A financially non-material PPL marker still changes the digest.

## 7. Double-entry ledger

The ledger applies only deterministic `FinancialEvent` postings.

Rules:

- exact Decimal arithmetic;
- one PAPER epoch per replay;
- strictly increasing source sequence;
- no duplicate financial event id;
- debit == credit for every financial event;
- no negative CASH_AVAILABLE;
- no negative CAPITAL_RESERVED;
- no negative CAPITAL_UNRESOLVED;
- no negative EPOCH_CAPITAL;
- no negative FEES_EXPENSE.

A replay violation fails closed.

## 8. Treasury projection

Treasury exposes:

- initial epoch capital;
- cash available;
- capital reserved;
- capital deployed;
- unresolved capital;
- gross realized price PnL;
- fees paid;
- funding status/value;
- FIN realized PnL.

For PAPER v1:

`capital_deployed == capital_reserved`

but capital deployed is a measure, not an additional asset.

### Funding

Current PPL supplies no generic funding cashflow event.

FIN-01 therefore accepts only:

- `NOT_APPLICABLE` — explicitly declared PAPER model semantics; funding net = 0;
- `UNRESOLVED` — missing applicable evidence; funding net and FIN realized PnL unavailable.

PPL-only FIN-01 cannot claim `COMPLETE` funding evidence.

## 9. Valuation

Valuation receives explicit observations keyed by trade id.

Each observation carries:

- trade id;
- symbol;
- source id;
- venue;
- market type;
- price;
- source timestamp.

The caller supplies:

- valuation as-of time;
- maximum accepted mark age.

No wall-clock read occurs inside the valuation engine.

Classification:

- LIVE — valid, positive, non-future mark within freshness threshold;
- STALE — valid mark older than threshold;
- UNAVAILABLE — missing/invalid/future-skewed evidence.

No fallback to:

- entry price;
- last known mark;
- zero;
- another venue;
- symbol-derived assumptions.

## 10. FinancialSnapshot

The immutable snapshot binds:

- FIN snapshot id;
- PAPER epoch;
- source authority;
- PPL stream digest;
- last PPL sequence;
- FIN schema;
- FIN code SHA;
- source/PPL code SHA;
- config hash;
- financial model;
- Treasury fields;
- funding evidence;
- valuation set + digest;
- realized/unrealized/equity state;
- population counts;
- attribution evidence;
- reconciliation status.

Snapshot identity changes when a bound source/provenance/valuation input changes.

## 11. Certified equity

Certified equity exists only when:

- no unresolved capital exists;
- every open position has exactly one LIVE mark;
- funding status is COMPLETE or NOT_APPLICABLE.

Within FIN-01 PPL-only operation, funding can satisfy this only through explicit
NOT_APPLICABLE PAPER-model semantics.

STALE may be displayed as indicative evidence, but it cannot certify equity.

## 12. PPL ↔ FIN consistency gate

Before a snapshot is returned, FIN-01 compares its projection against PPL for
facts that must be exactly equivalent:

- available cash;
- reserved principal;
- unresolved capital;
- fees paid;
- initial epoch capital.

Any mismatch raises a snapshot error.

FIN never silently adjusts its ledger to make the values converge.

## 13. Evidence states

Snapshot evidence is:

- COMPLETE when required current evidence is complete;
- PARTIAL when only stale valuation evidence prevents certification;
- UNRESOLVED when lifecycle, mark or funding evidence is unresolved.

Unknown is never represented by numeric zero.

## 14. Reconciliation boundary

FIN-01 does not perform external/simulator reconciliation.

Snapshot reconciliation status remains:

`UNRESOLVED`

until #247 FIN-02 compares FIN against independent read-only observations.

## 15. Determinism contract

Given exactly the same:

- ordered PPL event stream;
- FIN schema;
- FIN code SHA;
- FinancialContext/provenance;
- valuation observations;
- valuation as-of;
- freshness threshold;

FIN-01 must reproduce exactly the same:

- FinancialEvents;
- postings;
- account balances;
- Treasury view;
- valuation set;
- snapshot fields;
- snapshot id.

No clock, randomness, API or environment lookup is permitted in the pure
projection path.

## 16. Restart/replay scope

FIN-01 proves source-level replay determinism.

Crash/restart runtime certification remains owned by:

#246 PPL-RECOVERY-01

FIN-01 must provide the pure deterministic substrate required for #246.

## 17. F00 boundary

Active F00 remains pinned independently to its certified runtime source.

FIN-01 source work MUST NOT:

- deploy to active F00;
- mutate the active epoch;
- modify strategy/signal/risk/sizing/execution;
- alter PPL durable events.

Any future FIN runtime activation requires a separately governed boundary.

## 18. Exit gate

Target verdict:

`FIN_01_PAPER_FINANCIAL_INSTITUTE_SOURCE_CERTIFIED`

Required evidence:

- FIN-00 dependency certified;
- adapter tests PASS;
- double-entry/replay tests PASS;
- Treasury tests PASS;
- valuation/freshness tests PASS;
- snapshot determinism tests PASS;
- unresolved/funding fail-closed tests PASS;
- full maintained CI PASS;
- exact certified HEAD recorded;
- no F00 deployment/mutation;
- #148 updated.

After FIN-01 certification, the blocking mission becomes:

#246 — PPL-RECOVERY-01.
