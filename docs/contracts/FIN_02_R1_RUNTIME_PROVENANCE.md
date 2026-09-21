# FIN-02R1 — Runtime Financial Provenance Contract

Status: **SOURCE IMPLEMENTATION CANDIDATE**

Parent mission: #247 — FIN-02  
Parent architecture: #150  
Governance: #148  
Reference PR: #254

## 1. Scientific question

Before FIN-02 can produce a runtime financial reconciliation artifact, the
system must be able to answer exactly:

> Which implementation interpreted the PPL lifecycle, which implementation
> performed reconciliation, which PPL population was interpreted, and which
> explicit semantic context was applied?

A financial value without that binding is observationally insufficient for
FIN-02 certification.

## 2. R1 scope

FIN-02R1 freezes provenance only.

It does **not**:
- wire a producer into Advisor;
- restart F00;
- mutate the active epoch/configuration;
- append PPL events;
- read or write exchange state;
- generate marks;
- change FIN-01 accounting formulas;
- change reconciliation arithmetic;
- grant BUY/SELL or capital-allocation authority.

## 3. Three identities that must never be conflated

### 3.1 PPL/F00 source identity

Source: authoritative PPL `EPOCH_CREATED.code_sha`.

Meaning:
the source identity under which the lifecycle epoch itself was created.

It is owned by PPL lifecycle provenance.

It is **not** the FIN implementation identity.

### 3.2 FIN-01 implementation identity

Canonical FIN-01 PAPER v1 source:

`c639ac397122929769be2a1ce7654e3a1bc24cfe`

Certified verdict:

`FIN_01_PAPER_FINANCIAL_INSTITUTE_SOURCE_CERTIFIED`

This exact identity was certified in #245 and was the FIN source identity used
by the deterministic financial replay proof in #246.

Meaning:
the certified implementation of the FIN-01 semantic adapter, ledger, treasury,
valuation contract and FinancialSnapshot construction.

This identity remains the FIN-01 semantic implementation identity even when a
later repository/deployment commit contains that already-certified code.

It must never be replaced silently by:
- the active F00 source SHA;
- the current branch HEAD;
- the PPL epoch source SHA;
- the FIN-02 reconciliation SHA.

A future FIN implementation requires an explicit new certification contract;
FIN-02R1 PAPER v1 fails closed on any other `fin_code_sha`.

### 3.3 FIN-02 reconciliation implementation identity

`reconciliation_code_sha` identifies the exact FIN-02 reconciliation
implementation that produced the reconciliation evidence.

It is supplied explicitly by the producer/deployment boundary.

R1 does not infer it from PPL, FIN-01 or an environment default.

It must identify FIN-02 separately from the certified FIN-01 implementation.

## 4. PPL-owned binding

FIN-02R1 accepts the authoritative PPL event population and derives from that
population only:

- `paper_epoch_id`;
- PPL source code identity from `EPOCH_CREATED.code_sha`;
- PPL configuration hash from `EPOCH_CREATED.config_snapshot_hash`;
- exact PPL source-stream digest;
- exact last source sequence.

The caller cannot supply duplicate copies of these fields.

This prevents a runtime caller from presenting one event stream while attaching
the epoch/config/source identity of another.

## 5. Explicit semantic inputs

PPL lifecycle does not carry every financial semantic attribution.

The runtime producer must supply explicitly:

- `reconciliation_code_sha`;
- `experiment_id`;
- `venue`;
- `market_type`;
- optional `strategy_id`;
- optional `strategy_version`.

No inference is allowed from:
- epoch naming;
- symbol naming;
- process mode;
- exchange client presence;
- current working tree;
- UI labels.

For PAPER v1, the following semantics are inherited from the certified FIN-01
contract:

- `asset = USDT`;
- `source_authority = PPL_AUTHORITY`;
- `financial_model = PAPER_LINEAR_PRINCIPAL_V1`;
- FIN source = certified FIN-01 HEAD above;
- funding is either:
  - `NOT_APPLICABLE` with the certified
    `FIN-00:PAPER_LINEAR_PRINCIPAL_V1:FUNDING_NOT_MODELED` evidence reference;
    or
  - `UNRESOLVED` when the producer cannot certify applicability.

UNKNOWN/UNRESOLVED is never converted to zero.

## 6. Deterministic semantic-context binding

The explicit semantic inputs are materialized through the existing FIN-01
`FinancialContext`.

Its existing `FIN_CONTEXT_V1` digest remains the canonical financial semantic
context identity.

FIN-02R1 does not introduce a competing context formula.

Therefore:

same semantic inputs
→ same `semantic_context_digest`.

Changing experiment/strategy/venue/market/funding semantics
→ changes `semantic_context_digest`.

Changing only FIN-02 reconciliation implementation
→ does **not** change FIN-01 semantic context, but **does** change the R1
runtime provenance identity.

## 7. Runtime provenance identity

Namespace:

`FIN02_RUNTIME_PROVENANCE_V1`

The deterministic identity binds:

- schema version;
- PPL epoch id;
- PPL stream digest;
- PPL last sequence;
- PPL source code identity;
- PPL config hash;
- certified FIN-01 source identity;
- FIN-01 certification verdict;
- FIN-02 reconciliation code identity;
- FIN semantic-context digest;
- asset;
- source authority;
- financial model;
- funding status/reference;
- experiment id;
- strategy id/version;
- venue;
- market type.

Any material change produces a different `provenance_id`.

## 8. Fail-closed rules

R1 rejects:

- empty PPL stream;
- missing PPL epoch;
- empty reconciliation identity;
- missing experiment id;
- missing venue;
- missing market type;
- FIN source identity different from the certified FIN-01 PAPER v1 identity;
- FIN-02 identity aliased to FIN-01 identity;
- unsupported asset/model/source authority;
- unsupported funding status;
- NOT_APPLICABLE funding without its certified evidence reference;
- strategy version without strategy identity.

## 9. Runtime activation boundary

R1 is **not** runtime activation.

The next phase must prove how a passive producer obtains:

1. one coherent authoritative PPL view;
2. one coherent simulator observation;
3. explicit valuation evidence;
4. this R1 provenance binding;

without mutating PPL, FIN, simulator, strategy, risk, sizing or execution.

No Advisor restart or active F00 deployment is authorized by this contract.

## 10. Source exit criteria

FIN-02R1 source is ready only when:

- the three source identities are explicitly separated;
- the certified FIN-01 identity is pinned;
- PPL-owned provenance is taken only from authoritative PPL facts;
- missing experiment/venue/market attribution fails closed;
- the existing FIN-01 semantic context remains canonical;
- runtime provenance identity is deterministic;
- tests prove semantic and stream changes affect the correct identities;
- full maintained CI is green on the exact candidate HEAD.

Candidate sub-verdict:

`FIN_02_R1_RUNTIME_PROVENANCE_SOURCE_READY`

This is not the final FIN-02 verdict.
