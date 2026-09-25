# RL-DIAG-01 — Performance Attribution & Incoherence Diagnostics Contract

Status: SOURCE CONTRACT V1 / implementation pending

Parent: #237  
Governance: #148  
Mission: #248  
Upstream: #238 RL-DATA-01 + #239 RL-REPLAY-01

Certified upstream identities:

- RL-DATA head: `8ad566de7521402c34a240b14fa9a036893c5ca3`
- RL-REPLAY head: `0e6c38de211192fadfd2f1470df468afdc92f666`
- dataset_id: `4ea633a6a4e2ee0bc01a6fe855526d7c42451883ec0b6f3914cf21ea8e91cc8b`
- source_boundary_id: `2e6b478cd0cead58c1bcf25c168254b0a63daaa2722c6c108613eb81e283812e`
- factual research_run_id: `225368c15b6848936caf7fbd4433b8f713ef1333d547047c6bb55bd0777847ed`
- certified factual CLOSED population: `N=13`

---

## 1. Mission

RL-DIAG-01 explains the certified factual Research result without mutating PAPER.

Canonical direction:

`IMMUTABLE RESEARCH RESULT → PROVENANCE-BOUND DIAGNOSTICS`

Never:

`DIAGNOSTIC RESULT → ACTIVE PAPER/F00 MUTATION`

The diagnostic layer is descriptive and analytical. It does not own lifecycle,
capital, admission, execution, strategy promotion, burn-in authority or exchange
write authority.

---

## 2. Scientific status model

Every diagnostic output MUST carry two independent classifications.

### 2.1 Evidence status

Allowed values:

- `COMPLETE`
- `PARTIAL`
- `NOT_AVAILABLE`
- `NOT_APPLICABLE`
- `UNRESOLVED`

Evidence status answers:

> Does the certified dataset contain enough provenance-bound evidence to compute
> this quantity under the declared definition?

### 2.2 Statistical strength

Allowed values:

- `DESCRIPTIVE_ONLY`
- `LOW_SAMPLE`
- `ADEQUATE_FOR_DECLARED_TEST`
- `NOT_EVALUATED`

Evidence completeness MUST NOT be confused with statistical confidence.

Example:

`realized_pnl_by_symbol = COMPLETE evidence / LOW_SAMPLE`

is valid for the F00 N=13 population.

A COMPLETE metric over N=13 is not a profitability certification.

---

## 3. Canonical population

The default v1 performance population is:

`POSITION_CLOSED_FOR_PERFORMANCE`

It contains only exact factual PPL lifecycles with:

- one certified POSITION_OPENED;
- one certified POSITION_CLOSED;
- exact trade_id linkage;
- non-fabricated entry/exit prices;
- non-fabricated entry/exit fees.

UNRESOLVED lifecycles are never converted to zero-PnL observations.

OPEN residuals are never silently dropped from lifecycle integrity diagnostics.

The current certified F00 factual population contains:

- source events: 27;
- CLOSED lifecycles: 13;
- OPEN residual: 0;
- UNRESOLVED residual: 0.

---

## 4. Provenance requirements

Every published diagnostic result MUST identify at minimum:

- `dataset_id`;
- `source_boundary_id`;
- `paper_epoch_id`;
- upstream factual `research_run_id`;
- RL-DIAG code SHA;
- diagnostic contract/schema version;
- population definition;
- record/sample count;
- derivation;
- evidence status;
- statistical strength.

If a diagnostic consumes the optional DecisionPacket component, it MUST also
record the exact component digest and the field-profile evidence used to establish
availability.

No metric may be detached from its source population identity.

---

## 5. COMPLETE diagnostics supported by authoritative PPL

The following families are supported by the current certified factual lifecycle
without requiring optional market evidence.

### 5.1 Lifecycle integrity

- OPEN/CLOSE/UNRESOLVED counts;
- duplicate/missing lifecycle resolution checks;
- source sequence monotonicity;
- trade_id linkage;
- open residual count;
- unresolved residual count;
- source event population reconciliation.

### 5.2 Realized financial attribution

Per CLOSED lifecycle:

- principal;
- entry_price;
- exit_price;
- entry_fee;
- exit_fee;
- total fees;
- gross realized PnL;
- net realized PnL;
- realized return on principal.

Aggregations may be produced by exact factual dimensions:

- symbol;
- side LONG/SHORT;
- UTC open date/hour bucket;
- UTC close date/hour bucket;
- declared holding-duration bucket;
- declared principal/size bucket.

Any bucket definition MUST be deterministic and included in diagnostic config
identity.

### 5.3 Position geometry

For schema-v2 POSITION_OPENED events:

- take-profit price;
- stop-loss price;
- timeout_at;
- recovery_eligible_until;
- entry-to-TP distance;
- entry-to-SL distance;
- initial reward/risk geometry;
- holding duration;
- close-before/after-timeout timing relation.

These are geometry/timing facts only. They do NOT prove the market touched TP/SL
or that a timeout caused the close.

### 5.4 Factual performance metrics

Supported over the exact CLOSED population:

- trade count;
- win count / loss count / flat count;
- win rate;
- gross profit;
- gross loss;
- Profit Factor;
- expectancy;
- average win;
- average loss;
- payoff ratio where denominator is valid;
- median trade PnL;
- realized PnL distribution summaries;
- realized close-to-close drawdown under the certified RL-REPLAY definition;
- cumulative realized equity from initial capital + ordered closed-trade net PnL.

Metric denominator-zero cases MUST remain explicit states, never fabricated
finite values.

### 5.5 Concentration / descriptive fragility

Supported descriptive diagnostics include:

- top-k trade contribution to total realized PnL;
- symbol concentration;
- side concentration;
- time-bucket concentration;
- principal concentration;
- winner concentration;
- loser concentration;
- leave-one-trade-out realized PnL sensitivity;
- leave-one-trade-out PF/expectancy sensitivity when mathematically defined.

These remain `DESCRIPTIVE_ONLY` / `LOW_SAMPLE` for N=13.

---

## 6. PARTIAL diagnostics

PARTIAL means some certified evidence exists, but a full scientific interpretation
requires additional semantics or field-completeness proof.

### 6.1 DecisionPacket contextual attribution

The certified optional DecisionPacket component contains exactly 13 packet records
selected by exact PPL OPEN decision_id == packet_id.

The source DecisionPacket schema can carry:

- timeframe;
- regime;
- confidence;
- confidence_raw;
- adjusted_confidence;
- expected_value;
- risk_score;
- allocation_pct;
- conviction;
- entry_price;
- stop_loss;
- take_profit;
- r_multiple;
- state_history;
- source_agents;
- reasoning;
- features;
- metadata.

RL-DIAG MUST NOT assume these fields are scientifically usable merely because the
class schema defines them.

Before any field is promoted to COMPLETE for the real F00 dataset, a READ-ONLY
field-profile MUST establish, over the exact 13 exported packet records:

- present_count;
- null_count;
- empty_count;
- UNKNOWN/default count where applicable;
- type consistency;
- distinct categorical values where safe;
- numeric finite-value count;
- packet_id uniqueness;
- exact packet_id linkage back to the 13 PPL OPEN records.

No heuristic field recovery is allowed.

### 6.2 Entry/exit quality

Available:

- initial entry/TP/SL geometry;
- realized close price;
- holding time;
- realized PnL.

Unavailable path evidence prevents full execution-quality claims.

Therefore v1 may describe realized entry/exit geometry, but MUST NOT label it
MFE, MAE, slippage, adverse selection or optimal exit quality.

### 6.3 Sharpe

Current RL-DATA v1 has no certified continuous mark-to-market equity series and
RL-REPLAY intentionally leaves Sharpe NOT_AVAILABLE.

RL-DIAG may later define a non-annualized trade-return dispersion statistic if:

- return definition is explicit;
- population is explicit;
- sample frequency is declared as per-trade rather than time-periodic;
- no annualization is implied;
- N is exposed;
- statistical strength remains LOW_SAMPLE for N=13.

Annualized/time-series Sharpe remains NOT_AVAILABLE for current F00 v1.

### 6.4 Turnover

A deterministic principal-deployment proxy may be defined from the sum of opened
principal relative to a declared capital denominator.

It MUST be named as a proxy and MUST NOT be silently presented as conventional
NAV/time-weighted portfolio turnover.

---

## 7. NOT_AVAILABLE diagnostics for current F00 v1

The following MUST fail closed unless a future certified dataset adds the required
evidence.

### 7.1 Market-path dependent diagnostics

NOT_AVAILABLE:

- mark-to-market equity trajectory;
- mark-to-market MaxDD;
- MFE;
- MAE;
- intratrade excursion;
- certified bid/ask spread at entry/exit;
- slippage versus certified reference quote;
- adverse-selection trajectory;
- latency-to-price-impact attribution;
- path-dependent execution quality.

Reason:

RL-DATA v1 contains no certified complete market trajectory bound to the F00
population.

### 7.2 Exit-cause attribution

POSITION_CLOSED authoritative payload contains only:

- exit_price;
- exit_fee.

No canonical close-cause field exists.

Therefore RL-DIAG MUST NOT infer:

- TP close;
- SL close;
- TIMEOUT close;
- recovery close;
- manual/other close

from price proximity or timestamp heuristics.

### 7.3 Rejected-opportunity / blocker analysis

Current source statuses:

- DIP = `NOT_AVAILABLE / NOT_STARTED`;
- Regret = `UNRESOLVED_PROVENANCE`;
- RejectionStore = `UNBOUND`;
- AdmissionLedger = `UNBOUND`.

The certified optional decision population contains the 13 OPEN packet identities,
not a certified full rejected-opportunity universe.

Therefore NOT_AVAILABLE:

- first_blocker distribution for all F00 candidates;
- all_blockers distribution for all F00 candidates;
- gate suppression rate;
- rejection funnel;
- missed-opportunity population;
- blocker opportunity cost;
- counterfactual PnL of rejected trades.

Date/cycle/symbol heuristic attribution is forbidden.

### 7.4 General strategy counterfactuals

NOT_AVAILABLE for current F00 v1:

- candidate strategy market replay;
- alternative entry/exit rule PnL;
- alternative blocker/gate PnL;
- alternative sizing PnL requiring unobserved path data.

No synthetic market trajectory, fill or missing decision graph may be created.

### 7.5 Strategy attribution

No canonical `strategy_id` is part of the authoritative PPL lifecycle contract.

Strategy attribution remains NOT_AVAILABLE unless an exact certified field in an
included Research component is separately demonstrated and bound.

---

## 8. Incoherence diagnostics

RL-DIAG v1 may detect only incoherences supported by certified evidence.

Allowed examples:

- lifecycle count mismatch;
- duplicate trade_id;
- OPEN without resolution;
- resolution without OPEN;
- terminal state vs lifecycle record disagreement;
- sum of closed net PnL != terminal realized_pnl;
- fee sum != terminal fees_paid;
- source event count != manifest count;
- PPL symbol/side/entry fields disagreeing with an exact-linked DecisionPacket
  field when that packet field has first been certified COMPLETE;
- DecisionPacket packet_id / trace bridge integrity failures.

Cross-system disagreement MUST be reported as an observation with both sources
and authorities. RL-DIAG must not choose a new runtime authority.

---

## 9. Diagnostic output model

A v1 diagnostic bundle SHOULD separate:

1. `summary.json`
2. `trade_attribution.jsonl`
3. `concentration.json`
4. `incoherences.jsonl`
5. `capability_matrix.json`
6. `manifest.json`

The output is Research-owned and immutable.

A future deterministic `diagnostic_run_id` MUST bind:

- upstream factual research_run_id;
- RL-DIAG code SHA;
- diagnostic config hash;
- population definition;
- capability/semantics version.

Publication timestamp and absolute filesystem path MUST NOT affect scientific
identity.

---

## 10. Hard safety boundary

RL-DIAG source MUST NOT:

- import service/systemd control;
- start/stop/restart Advisor or Watchdog;
- append PPL events;
- write PAPER/legacy ledgers;
- mutate RL-DATA datasets;
- mutate RL-REPLAY published runs;
- call exchange write APIs;
- alter strategies;
- alter gates;
- alter risk parameters;
- alter sizing;
- create a new PAPER epoch;
- authorize burn-in;
- authorize TESTNET/LIVE.

Static tests MUST enforce forbidden-import and forbidden-mutation boundaries.

---

## 11. A2 field-profile gate

Before contextual DecisionPacket diagnostics are implemented, execute a
READ-ONLY field-profile against:

`optional/decision_packets.jsonl`

inside the certified dataset.

The profiler MUST:

- validate the dataset first through the certified RL-REPLAY validation path;
- read only the exact included component;
- never discover live source shards;
- never read mutable runtime databases directly;
- emit only aggregate field-completeness evidence;
- never rewrite the dataset;
- preserve source bytes exactly;
- keep the worktree clean.

Required profile fields for A2:

- packet_id;
- symbol;
- timeframe;
- side;
- regime;
- confidence;
- confidence_raw;
- adjusted_confidence;
- expected_value;
- risk_score;
- allocation_pct;
- conviction;
- entry_price;
- stop_loss;
- take_profit;
- r_multiple;
- state_history;
- reasoning;
- features;
- metadata.trace_id.

A field may move from PARTIAL to COMPLETE only after the real 13-record profile
supports that promotion.

---

## 12. Current governed verdict

`RL_DIAG_01_A1_FORENSIC_CAPABILITY_AUDIT = PASS_WITH_EXPLICIT_LIMITS`

`RL_DIAG_01_A2_SOURCE_CONTRACT = SPECIFIED`

Next gate:

`A2_REAL_F00_DECISION_PACKET_FIELD_PROFILE`

No performance-diagnostic implementation is authorized before that profile is
reviewed.
