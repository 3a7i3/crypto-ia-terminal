# FIN-00 — Financial Semantics Contract

Status: **SOURCE CONTRACT CANDIDATE**

Parent architecture: #150  
Mission: #244  
Governance: #148  
Baseline: `main@84b2170700294c3137f8c5bdb053c5c0cc2ca56e`

## 1. Purpose

FIN-00 freezes the meaning of PAPER money before FIN-01 implements a
Financial Institute runtime projection.

The authority split is explicit:

- **PPL** answers: *what lifecycle fact happened?*
- **Financial Institute** answers: *what does that fact mean financially?*
- **Risk** owns risk limits.
- **Execution** owns order placement/fill mechanics.
- **Strategies** produce hypotheses/opportunities.
- **FIN does not generate signals and does not place orders.**

FIN-00 is contract-only. It grants no runtime authority.

## 2. Current F00 boundary

The active epoch `F00-EPOCH-01-20260920T084335Z` remains immutable evidence
under the administrative state `F00_ACTIVE_PRE_FIN_VALIDATION`.

FIN-00 MUST NOT:

- change F00 parameters;
- change strategy/signal/risk/sizing/execution;
- alter PPL events;
- rewrite the active epoch;
- deploy GitHub `main` to the active F00 runtime;
- promote TESTNET/LIVE.

The current F00 run may continue collecting lifecycle evidence while FIN-00 is
source-only. Final `F00_CERTIFIED` remains blocked by FIN-00 -> FIN-01 ->
PPL-RECOVERY-01 -> FIN-02.

## 3. PPL is not the Financial Institute

Existing PPL fields remain valid for their certified lifecycle semantics, but
their names MUST NOT be treated as a complete financial accounting model.

In particular, the PPL handoff formula:

`epoch.initial_virtual_capital + projection.realized_pnl`

is a certified **scientific-capital handoff semantic**, not a complete
mark-to-market equity statement.

Example: after an OPEN, PPL can have:

- reduced `available_cash`;
- positive `reserved_principal`;
- an already-paid entry fee;
- `projection.realized_pnl == 0` until the lifecycle settles.

FIN therefore derives accounting truth from the immutable PPL facts instead of
renaming the PPL projection as "equity".

No existing PPL fact is rewritten.

## 4. Canonical monetary unit and precision

FIN-00 PAPER v1 records postings per asset.

For the current F00 epoch the reporting/capital asset is USDT, but the contract
does not hard-code USDT as the only future asset.

Rules:

1. FIN-01 MUST normalize durable numeric facts into decimal arithmetic.
2. No hidden binary-float epsilon is an accounting rule.
3. No rounding is permitted merely for UI convenience.
4. Display formatting is not ledger quantization.
5. If exchange/asset precision is required later, that precision must arrive as
   explicit metadata/provenance.
6. Non-finite values fail closed.

## 5. Financial vocabulary

### 5.1 Initial epoch capital

`initial_epoch_capital` is the immutable capital introduced by the
authoritative PPL `EPOCH_CREATED` fact.

For one PAPER epoch there is exactly one initial-capital authority.

No legacy JSONL or exchange fallback may replace it under PPL authority.

### 5.2 Cash available

`cash_available` is unencumbered capital currently available inside the PAPER
financial model.

It is an **asset balance**.

### 5.3 Capital reserved

`capital_reserved` is historical principal/cost basis committed to currently
open PAPER positions and therefore unavailable as free cash.

For current PPL PAPER v1 it maps to the sum of durable open-position
`principal` facts.

It is an **asset balance**, not PnL and not a mark-to-market value.

### 5.4 Capital deployed

`capital_deployed` is an operational/exposure measure, not an additional
balance-sheet asset.

For current unleveraged-linear PPL v1:

`capital_deployed = SUM(open_position.principal)`

Therefore it may be numerically equal to `capital_reserved`, but it MUST NOT
be added to `capital_reserved` when computing equity.

Future leveraged derivative notional/margin semantics require a separate
contract. FIN-00 does not infer leverage, multiplier or notional that PPL does
not durably prove.

### 5.5 Unresolved capital

`capital_unresolved` is historical principal segregated because exact
financial settlement cannot be established.

It is **not** a claim that the principal is still economically worth that
amount. The historical amount exists to preserve conservation and provenance.

If `capital_unresolved > 0`, certified economic equity is unavailable until an
explicit future reconciliation/resolution contract settles it.

`UNKNOWN != 0`.

### 5.6 Fees

Fees are realized financial expenses at the moment the durable fee fact exists.

Current PPL facts provide:

- entry fee on `POSITION_OPENED`;
- exit fee on `POSITION_CLOSED`.

A fee is never deferred merely because the position remains open.

A fee is never charged twice.

### 5.7 Funding

Funding is a signed realized cashflow:

- positive = funding received;
- negative = funding paid.

Current PPL lifecycle events do not provide a general funding event stream.
Therefore FIN MUST NOT silently assume `funding = 0` for a funding-applicable
instrument.

Funding may be:

- `COMPLETE` when supported by authoritative evidence;
- `NOT_APPLICABLE` only when the instrument contract proves that;
- `UNRESOLVED` when applicable evidence is missing.

FIN-01 may only implement funding sources explicitly covered by durable
evidence.

## 6. PnL semantics

FIN separates price performance from realized costs.

### 6.1 Gross realized price PnL

For the current PPL linear principal model:

LONG:

`gross_price_pnl = principal * (exit_price - entry_price) / entry_price`

SHORT:

`gross_price_pnl = principal * (entry_price - exit_price) / entry_price`

This mirrors the existing certified PPL price-return convention.

It is not a universal derivatives pricing formula.

### 6.2 Unrealized price PnL

For an open position the same formula is evaluated against a certified mark
instead of an exit price.

Unrealized PnL requires valid valuation evidence.

No mark -> no certified unrealized PnL.

### 6.3 Realized PnL to date

Canonical FIN realized PnL is:

`realized_pnl = gross_realized_price_pnl + funding_net - fees_paid`

Fees are recognized when charged. Funding is recognized when its authoritative
cashflow is known.

This intentionally differs from the lifecycle-oriented
`PPL.projection.realized_pnl`, which currently records a closed trade's net
outcome only when that lifecycle settles.

The two values MUST NOT be conflated.

### 6.4 Net total PnL / mark-to-market performance

When valuation is fully certified and no unresolved capital exists:

`net_pnl_mtm = realized_pnl + unrealized_pnl`

`certified_equity = initial_epoch_capital + net_pnl_mtm`

Equivalent asset-side form:

`certified_equity = cash_available + capital_reserved + unrealized_pnl`

for current PAPER v1, when `capital_unresolved == 0`.

## 7. Chart of accounts — PAPER v1

| Account | Kind | Meaning |
|---|---|---|
| `CASH_AVAILABLE` | ASSET | unencumbered PAPER cash |
| `CAPITAL_RESERVED` | ASSET | historical principal/cost basis of open positions |
| `CAPITAL_UNRESOLVED` | ASSET | segregated historical principal with unknown settlement |
| `EPOCH_CAPITAL` | EQUITY | immutable capital introduced at epoch creation |
| `REALIZED_TRADING_PNL` | INCOME | gross realized price PnL; may debit on loss |
| `FEES_EXPENSE` | EXPENSE | authoritative fees paid |
| `FUNDING_PNL` | INCOME | signed funding result; may debit when funding is paid |

No UI may invent a second chart of accounts.

## 8. Posting convention

FIN uses positive posting amounts and an explicit `DEBIT` / `CREDIT` side.

Every `FinancialEvent` MUST balance exactly within one asset after canonical
decimal normalization:

`SUM(debits) == SUM(credits)`

No event may silently create or destroy capital.

### 8.1 EPOCH_CREATED

For initial capital `C`:

- Debit `CASH_AVAILABLE C`
- Credit `EPOCH_CAPITAL C`

### 8.2 POSITION_OPENED

For principal `P` and entry fee `F_entry`:

- Debit `CAPITAL_RESERVED P`
- Debit `FEES_EXPENSE F_entry` when fee > 0
- Credit `CASH_AVAILABLE P + F_entry`

This is one economic interpretation of the immutable PPL facts; it does not
change the PPL event.

### 8.3 POSITION_CLOSED

First release historical principal:

- Debit `CASH_AVAILABLE P`
- Credit `CAPITAL_RESERVED P`

For gross gain `G > 0`:

- Debit `CASH_AVAILABLE G`
- Credit `REALIZED_TRADING_PNL G`

For gross loss `L > 0`:

- Debit `REALIZED_TRADING_PNL L`
- Credit `CASH_AVAILABLE L`

For exit fee `F_exit > 0`:

- Debit `FEES_EXPENSE F_exit`
- Credit `CASH_AVAILABLE F_exit`

### 8.4 POSITION_UNRESOLVED

For historical principal `P`:

- Debit `CAPITAL_UNRESOLVED P`
- Credit `CAPITAL_RESERVED P`

There is no fabricated cash release and no fabricated PnL.

### 8.5 RECOVERY_COMPLETED

The PPL recovery marker is lifecycle/recovery evidence.

By itself it creates **no financial posting** unless a future contract adds an
explicit financial fact.

## 9. Historical-cost conservation

For PAPER v1, ignoring unsupported external capital flows:

`book_equity_at_cost = cash_available + capital_reserved + capital_unresolved`

and:

`book_equity_at_cost = initial_epoch_capital + gross_realized_price_pnl + funding_net - fees_paid`

These equalities are accounting/conservation statements, not certified economic
valuation when unresolved capital exists.

No mid-epoch deposit/withdrawal event exists in the current PPL contract.
FIN-01 must fail closed if an unsupported capital-flow semantic appears.

## 10. Valuation contract

Every mark used by FIN carries at minimum:

- symbol/instrument identity;
- exchange/venue;
- market type;
- price;
- source identifier;
- source timestamp;
- observation/receipt timestamp when available;
- valuation timestamp;
- freshness threshold used;
- age;
- status;
- provenance.

Allowed status:

- `LIVE` — valid price and within the explicit freshness threshold;
- `STALE` — valid observed price but older than the threshold;
- `UNAVAILABLE` — missing, invalid, non-positive or otherwise unusable.

A stale mark may be displayed as indicative evidence, but it MUST NOT produce
`certified_equity`.

If any open position lacks a `LIVE` mark, certified equity is unavailable.

The valuation layer MUST NOT silently replace a missing mark with entry price,
last known price, zero or another venue's price.

## 11. Attribution

Every financial datum must remain attributable to its population.

Mandatory epoch-level provenance:

- `paper_epoch_id`;
- source authority;
- source PPL event identity/sequence where applicable;
- financial schema version;
- code SHA;
- config hash.

Trade/event attribution when known:

- `trade_id`;
- `decision_id`;
- symbol;
- exchange/venue;
- market type.

Strategy/experiment attribution:

- `strategy_id` and version only when durably evidenced;
- explicit `experiment_id` only when durably evidenced.

Missing strategy/experiment metadata is `UNRESOLVED`/null. FIN MUST NOT infer
it from current runtime configuration after the fact.

`paper_epoch_id` is a provenance anchor; it is not silently re-labeled as a
strategy id.

## 12. Evidence completeness

Allowed evidence classifications:

- `COMPLETE`;
- `PARTIAL`;
- `UNRESOLVED`;
- `NOT_APPLICABLE`.

Zero is a numeric fact. It is not a substitute for missing evidence.

Examples:

- known zero fee -> `0`, COMPLETE;
- missing applicable fee -> null, UNRESOLVED;
- funding impossible by explicit instrument contract -> NOT_APPLICABLE;
- funding applicable but absent -> null, UNRESOLVED.

## 13. Reconciliation

FIN-02 will compare:

- PPL lifecycle truth;
- FIN projection;
- simulator/read-only observations where applicable.

FIN-00 freezes the tolerance rule:

### Internal deterministic replay

FIN replay against the same durable inputs is **exact after canonical numeric
normalization**.

Default tolerance: zero.

A replay mismatch is not waived by a hidden epsilon.

### External/simulator reconciliation

Tolerance must be explicit and provenance-bearing per comparison:

- absolute tolerance;
- relative tolerance;
- unit/asset;
- compared source;
- timestamp/as-of;
- reason for the tolerance.

Comparison rule:

`abs(observed - projected) <= max(abs_tol, rel_tol * max(abs(observed), abs(projected)))`

No global undocumented tolerance is permitted.

Statuses:

- `EXACT`;
- `WITHIN_TOLERANCE`;
- `DIVERGENT`;
- `UNRESOLVED`.

A divergence is never silently corrected.

## 14. FinancialEvent identity

Every derived financial event must have:

- deterministic/stable `financial_event_id`;
- `source_domain`;
- `source_authority`;
- immutable `source_event_id`;
- `paper_epoch_id`;
- source sequence;
- financial schema version;
- code SHA;
- config hash.

FIN-01 must define the canonical serialization/hash recipe before emitting
durable FinancialEvents. Replaying the same source facts under the same FIN
schema must generate the same event identities.

No random identity may make identical replay produce a different financial
history.

## 15. FinancialSnapshot identity

An immutable FinancialSnapshot must bind at minimum:

- `snapshot_id`;
- `paper_epoch_id`;
- last included PPL/source sequence;
- source stream digest;
- FIN schema version;
- code SHA;
- config hash;
- valuation-set digest;
- valuation as-of time;
- evidence completeness;
- reconciliation status.

The snapshot identity must change when any bound input changes.

UI/API transport must expose the identity/provenance rather than recomputing the
accounting state independently.

## 16. Minimum FinancialSnapshot vocabulary

FIN-01 must be capable of projecting at least:

- initial epoch capital;
- cash available;
- capital reserved;
- capital deployed;
- unresolved capital;
- gross realized price PnL;
- fees paid;
- funding net + funding evidence status;
- FIN realized PnL;
- unrealized PnL + valuation status;
- certified equity or unavailable;
- open-position count;
- settled-position count;
- unresolved-position count;
- epoch/strategy/experiment attribution;
- reconciliation status;
- freshness/provenance.

## 17. Scientific invariants

The following are normative:

1. No silent capital creation/destruction.
2. Every ledger balance movement is explained by immutable FinancialEvents.
3. Every FinancialEvent balances debit == credit.
4. Same source facts + same FIN schema/config produce the same financial state.
5. No source event is applied twice.
6. Every realized price PnL links to an exact lifecycle settlement.
7. Entry fee is charged exactly once.
8. Exit fee is charged exactly once.
9. Reserved principal cannot be released twice.
10. UNRESOLVED never becomes zero by default.
11. Missing mark never becomes zero/entry/last-known price by default.
12. Capital deployed is not double-counted with capital reserved in equity.
13. Strategy/experiment attribution is never inferred without evidence.
14. Reconciliation deltas remain visible and attributable.
15. UI/API never create independent accounting formulas.
16. PPL remains lifecycle authority; FIN interpretation cannot rewrite PPL.
17. FIN has no signal, risk, sizing, order-placement or exchange-write authority.

## 18. F00 stop/continue decision rule

FIN-00 itself does not require stopping the active F00 process because it is
source-only and has no runtime interaction.

F00 SHOULD be paused/terminated through a separately governed runtime procedure
if any of the following becomes true:

- continuing F00 would mutate code/config/authority required by FIN work;
- a FIN implementation needs a quiescent cutover/replay proof;
- lifecycle evidence becomes internally inconsistent;
- PPL durable append/replay integrity fails;
- financial conservation cannot be established and continued activity would
  enlarge an uninterpretable population;
- governance requires deployment of source newer than the pinned F00 runtime.

Stopping F00 must preserve its epoch/event store and record an exact terminal
boundary. It must never delete or rewrite the accidental/pre-FIN evidence.

## 19. FIN-00 exit gate

FIN-00 may receive:

`FIN_00_FINANCIAL_SEMANTICS_CERTIFIED`

only when:

- this contract is reviewed against current PPL semantics;
- machine-readable semantic primitives/tests pass;
- debit/credit convention is frozen;
- PnL/fee/funding semantics are frozen;
- valuation/freshness semantics are frozen;
- unresolved/reconciliation semantics are frozen;
- provenance/identity requirements are frozen;
- no runtime/F00 mutation occurred;
- #148 is updated with the certified HEAD and verdict.

FIN-01 then implements the deterministic PPL -> Financial Institute projection.
