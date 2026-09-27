# WEB-DIR-01 / D4A — Direction Data and Authority Contract

**Mission:** #294  
**Parent:** #288  
**Active roadmap:** #285  
**Related UX:** #283  
**Burn-in guard:** #286  
**Source baseline:** `fa6f6cd15a7afc3f057355b17a431f8e809e55b2`  
**Baseline tree:** `dad88d768d6a952940d880a422f41fc9717aaf03`  
**Date:** 2026-09-27 UTC  
**Status:** CONTRACT DEFINED — NOT SOURCE CERTIFIED — NOT RUNTIME CERTIFIED

## 1. Purpose

Define the exact data, authority, freshness, provenance, and absence semantics
for Direction level-one cards before D4 adds executable presentation code.

The required chain for every displayed fact is:

`display field -> endpoint -> producer field -> authority -> freshness -> absence/error state`

D4A is documentation-only. It creates no new data producer, endpoint, metric,
runtime authority, or deployment permission.

## 2. Protected boundary

The active burn-in remains immutable:

- epoch: `BURN-IN-EPOCH-01-20260926T064144Z`;
- runtime source: `116634be0d3c015cce1cfa58be7da7255414fbfd`;
- config hash:
  `9d9de1af4ac5aa5afc030ff64b08eeada0e1388a5d87c6475cb39c042be230d4`;
- admission: `PB_MAX_POSITIONS=2`.

D4 MUST NOT change or control strategy, signals, thresholds, risk, sizing,
capital, epoch, manifest, PPL, FIN, Advisor, systemd, Watchdog, TESTNET, LIVE,
Research promotion, or exchange access.

## 3. Verified source boundaries

### 3.1 Canonical advisor presentation

`GET /api/operator/v1/snapshot`

Provides one validated snapshot envelope containing:

- runtime/source identity evidence;
- portfolio presentation;
- decision-pipeline presentation;
- system-health presentation;
- reader-authored instance relation, runtime state, age, stale reason, and
  freshness classification.

The endpoint is atomic only within its own envelope.

### 3.2 Financial observation

`GET /api/operator/v1/financial-reconciliation`

Provides one FIN-02 atomic presentation artifact plus reader-authored age and
freshness. It is `FINANCIAL_OBSERVATION`, not execution authority.

### 3.3 Market observation

`GET /api/operator/v1/market`

Provides one CryptoRadar observational artifact. It is a separate process and
observation boundary with authority `OBSERVATIONAL_TELEMETRY`.

### 3.4 Research presentation

`GET /api/operator/v1/research-lab`

Provides one Research presentation artifact with authority
`RESEARCH_NON_AUTHORITATIVE`. It has its own dataset and run boundary.

### 3.5 Missing Direction projection

No `GET /api/operator/v1/direction` atomic projection exists.

D4B–D4D may build a federated page from independent cards, but MUST NOT:

- claim cross-card atomicity;
- derive one global timestamp;
- select the newest value across sources and call it canonical;
- derive a global health state;
- recompute scientific or financial metrics;
- hide disagreement, stale state, or source failure.

## 4. Direction page model

Direction is a **federated presentation surface**, not an aggregate producer.

Every governed card MUST display or make inspectable:

- its endpoint/domain;
- authority;
- producer timestamp;
- reader freshness when supplied;
- source identity/provenance;
- evidence or availability state;
- source-specific failure state.

The page-level banner MUST say that cards may have different observation times.

## 5. Global state card contract

| Display | Source field | Authority/evidence | Display rule |
|---|---|---|---|
| Global machine state | no producer | none | always `INCONNU`; never infer SAIN/ATTENTION/DÉGRADÉ/CRITIQUE |
| Mode | `snapshot.portfolio.mode` | `snapshot.portfolio.authority` | render exact enum; `UNKNOWN` remains `UNKNOWN` |
| Runtime source SHA | `snapshot.source_sha` | `snapshot.runtime_sha_evidence_status` | show SHA with evidence status; `CLAIMED_ONLY` must not be styled as verified |
| Worktree | `snapshot.worktree_state` | canonical envelope | show `CLEAN`, `DIRTY`, or `UNKNOWN` exactly |
| Runtime state | `snapshot.runtime_state` | reader-authored | show `CURRENT` or `LAST_KNOWN` exactly |
| Instance relation | `snapshot.instance_relation` | reader-authored | show exact relation; no current-instance inference |
| Snapshot age | `snapshot.snapshot_age_s` | reader-authored | render null as unavailable, never zero |
| Snapshot freshness | `snapshot.freshness_classification` | reader-authored | render exact value; do not invent thresholds in React |
| Stale reason | `snapshot.stale_reason` | reader-authored | show when non-null; do not replace with a generic healthy state |
| Advisor observation | `snapshot.system_health.boot_alive` | `ObservedValue<boolean>` | label as `boot_alive observation`; preserve semantics; do not broaden to service certification |
| Health level | `snapshot.system_health.health_level` | `ObservedValue<string>` | show producer value/semantics only; do not convert to global state |
| Watchdog | no governed field | none | `NON DÉPLOYÉ` |
| Critical alert count | no governed field | none | `NON DÉPLOYÉ`, never `0` |

### 5.1 Global-state prohibition

The card may show several producer-authored facts, but its headline remains:

`ÉTAT GLOBAL · INCONNU`

until a governed producer defines a global status contract.

## 6. Active experiment / burn-in card contract

FIN-02 is the preferred level-one source because it provides the active epoch,
financial observation, lifecycle counts, source/config identities, evidence,
and reconciliation in one atomic artifact.

| Display | FIN-02 field | Rule |
|---|---|---|
| Epoch | `paper_epoch_id` | exact string |
| Source SHA | `source_code_sha` | exact string; distinct from current app source |
| Config hash | `config_hash` | exact string |
| Generated at | `generated_at_utc` | exact producer timestamp |
| Financial freshness | `freshness_classification`, `snapshot_age_s` | exact reader evidence |
| Open positions | `financial.open_position_count` | producer integer; zero is valid when producer emits zero |
| Settled positions | `financial.settled_position_count` | label **Settled**, not `POSITION_CLOSED`, unless a future producer defines equivalence |
| Unresolved positions | `financial.unresolved_position_count` | producer integer; never merge with missing data |
| Cash available | `financial.cash_available` | render decimal text without binary-float recomputation |
| Capital reserved | `financial.capital_reserved` | render decimal text |
| Capital deployed | `financial.capital_deployed` | render decimal text |
| Capital unresolved | `financial.capital_unresolved` | render decimal text and status, never hide it |
| Realized PnL | `financial.realized_pnl` | if null, show `financial.evidence_status`; never substitute zero |
| Fees paid | `financial.fees_paid` | render decimal text |
| Reconciliation | `financial.reconciliation_status` and `reconciliation.overall_status` | show both if they differ; never collapse disagreement |
| Unreconciled capital | `reconciliation.unreconciled_capital` | null remains unavailable; never zero |
| Evidence status | `financial.evidence_status` | exact producer status |

### 6.1 Active experiment fields not currently governed

| Requested display | D4 status | Reason |
|---|---|---|
| Active burn-in population | `NOT_AVAILABLE` | no authoritative active-experiment population field identified |
| Profit factor | `NOT_AVAILABLE` | not in FIN-02 active-experiment contract |
| Win rate | `NOT_AVAILABLE` | not in FIN-02 active-experiment contract |
| Expectancy | `NOT_AVAILABLE` | not in FIN-02 active-experiment contract |
| Maximum drawdown | `NOT_AVAILABLE` | not in FIN-02 active-experiment contract |

Research metrics MUST NOT fill these active-PAPER fields. Research may describe
an immutable dataset only inside the Research card.

### 6.2 PPL comparison boundary

`GET /api/operator/v1/ppl-comparison` remains an observational comparison
surface. D4 MUST NOT use its comparison summary as trade population or its
comparison authority as PAPER financial authority.

## 7. Market card contract

All Market values come from the same `MarketRadarSnapshot`.

| Display | Market field | Rule |
|---|---|---|
| Product | `product` | must remain `CryptoRadar` |
| Authority | `authority` | permanently show `OBSERVATIONAL_TELEMETRY` |
| Mode | `mode` | show `OBSERVATION` |
| Generated at | `generated_at_utc` | exact timestamp |
| Source updated at | `source_updated_at_utc` | null remains unavailable |
| Freshness | `freshness_classification`, `snapshot_age_s` | exact reader evidence |
| Window | `window_hours` | producer integer |
| Packets observed | `packets_observed` | producer integer |
| Market regime | `market_regime` | null remains unavailable |
| Universe | `universe_size` | producer integer |
| Actionable | `actionable_count` | producer integer; observational, not execution permission |
| Watchlist | `watchlist_count` | producer integer |

D4 must not convert `actionable_count` into orders, trade permission, or an
execution forecast.

## 8. Research card contract

All Research values come from one `ResearchLabSnapshot` and remain visibly
`RESEARCH NON-AUTORITAIRE`.

| Display | Research field | Rule |
|---|---|---|
| Authority | `authority` | permanently show `RESEARCH_NON_AUTHORITATIVE` |
| Research state | `research_state` | exact `AVAILABLE` or `EMPTY` |
| Generated at | `generated_at_utc` | exact timestamp |
| Dataset | `provenance.primary_context.dataset_id` | exact identity |
| Source boundary | `provenance.primary_context.source_boundary_id` | exact identity |
| PAPER epoch reference | `provenance.primary_context.paper_epoch_id` | null remains unavailable; reference is not feedback authority |
| Research run | `provenance.primary_context.research_run_id` | exact identity |
| Diagnostic run | `provenance.primary_context.diagnostic_run_id` | null remains unavailable |
| Population N | `population.n` | applies only to the Research dataset |
| Evidence | `population.evidence_status` | exact status |
| Statistical strength | `population.statistical_strength` | exact status |
| Candidates | `candidate_registry.candidate_count` | producer integer; zero is valid when explicitly emitted |

Individual performance/risk/cost metrics may appear only when D4C defines an
explicit named metric lookup with evidence status, statistical strength,
population N, derivation, and source reference. Missing metric names are
`NOT_AVAILABLE`, never zero.

## 9. Capabilities without producers

These Direction blocks have no governed product projection and MUST remain
`NON DÉPLOYÉ`:

- operator decision queue;
- Agent Registry;
- Bounty Registry;
- proposed-evolution workflow;
- AIC economy and wallets;
- Economy Ledger/hash chain;
- consolidated real costs;
- consolidated security/debt projection;
- consolidated incident registry.

No demonstration number or fake row may appear as current fact.

## 10. Availability semantics

### 10.1 Producer values

- explicit numeric `0` or `ObservedValue(..., ZERO)` is a real zero;
- `UNKNOWN != ZERO`;
- `UNRESOLVED != ZERO`;
- `NOT_AVAILABLE != ZERO`;
- `UNAVAILABLE != ZERO`;
- `NOT_APPLICABLE != ZERO`;
- `STALE` is still stale evidence, not current evidence and not absence;
- null must retain its producer-authored reason/status.

### 10.2 Product availability

- no product/producer exists: `NON DÉPLOYÉ`;
- product exists but a requested metric is absent: `NOT_AVAILABLE`;
- governed global status absent: `INCONNU`;
- endpoint artifact missing: show structured API error;
- invalid HTTP 200 body: show contract/transport error;
- network failure: show transport error;
- loading: show loading state, never a previous value as current unless the
  client explicitly labels it last-known/stale.

French explanatory text may accompany exact machine statuses, but MUST NOT
replace or soften them.

## 11. Error and polling contract

Each independent client retains its current state machine:

`loading | success | api_error | transport_error`

Rules:

1. requests are GET-only;
2. validation failure on HTTP 200 is a contract/transport error;
3. one card failure does not fabricate values or erase evidence in another;
4. one card success does not make the page globally healthy;
5. polling intervals remain source-client concerns;
6. D4 must not synchronize independent polls and call them atomic;
7. error text must identify the failing domain.

## 12. Provenance presentation

Level one may abbreviate long identifiers, but the full value must remain
accessible via details, copy control, or secondary inspection.

Never abbreviate without access to the complete value for:

- source SHA;
- config hash;
- epoch ID;
- snapshot/dataset/source-boundary/run IDs;
- evidence refs;
- artifact hashes.

Source SHA categories must be labelled distinctly:

- application source;
- runtime source evidence;
- FIN source code;
- Research source code;
- presentation-builder source.

## 13. D4 implementation sequence

### D4B — Global and active experiment

- add canonical snapshot and FIN-02 card adapters;
- preserve exact statuses and decimal text;
- keep global headline `INCONNU`;
- add domain-specific error states;
- no Market or Research request yet.

### D4C — Market and Research

- add independent Market and Research cards;
- keep permanent authority labels;
- prevent Research-to-PAPER metric leakage.

### D4D — Cross-card provenance

- make independent timestamps/freshness visible;
- add full-identity inspection;
- explicitly label the page non-atomic/federated.

### D4E — Certification

- semantic tests;
- request/mutation tests;
- desktop/mobile visual proof;
- exact CI reporting;
- source certification;
- still no deployment.

## 14. Required test matrix

### Global state

- missing global producer renders `INCONNU`;
- `CLAIMED_ONLY` is not rendered as verified;
- `UNKNOWN`, null age, and stale reason are preserved;
- no synthetic health aggregation.

### Active experiment

- decimal text remains exact;
- null realized PnL uses evidence status, not zero;
- unresolved capital remains visible;
- FIN reconciliation statuses are not collapsed;
- PF/WR/expectancy/drawdown/population remain `NOT_AVAILABLE`;
- Research data cannot populate active-PAPER metrics.

### Market and Research

- Market remains `OBSERVATIONAL_TELEMETRY`;
- actionable market count never becomes trade permission;
- Research remains `RESEARCH_NON_AUTHORITATIVE`;
- Research N is labelled as dataset population;
- explicit candidate count zero may render zero;
- missing Research metric renders `NOT_AVAILABLE`.

### Transport and authority

- only documented GET endpoints are called;
- no POST/PUT/PATCH/DELETE;
- independent endpoint failures remain isolated;
- no direct JSONL/database/exchange read;
- no route or UI action mutates PAPER;
- no card claims cross-endpoint atomicity.

### Quality

- existing Vitest suite;
- cross-stack compatibility gate;
- `npm run build`;
- `npm test -- --run`;
- `npm run test:runtime`;
- desktop/mobile browser proof in D4E.

## 15. API decision

D4A–D4E do not require a new endpoint.

If a future product requirement demands an atomic Direction snapshot, it must
be a separate producer/API mission with versioned schema, per-block provenance,
availability, timestamp, authority, and fail-closed validation. React must not
become that producer.

## 16. D4A non-impact proof

| Protected surface | D4A effect |
|---|---|
| active runtime source | unchanged |
| epoch/config/admission | unchanged |
| strategy/risk/sizing | untouched |
| PPL/FIN/Research producers | untouched |
| Operator API | untouched |
| Advisor/systemd/Watchdog | untouched |
| TESTNET/LIVE/exchange | untouched |
| frontend executable source | untouched |
| deployment | none |
| modified surface | one documentation file |

## 17. Acceptance and verdict

D4A may be source-certified only after:

1. document review;
2. documentation-only diff proof;
3. exact base/head/tree recording;
4. CI reported exactly;
5. #294, #288, and #285 synchronization;
6. explicit human merge authorization;
7. post-merge tree equality verification.

Current status:

`WEB_DIR_01_D4A_DATA_CONTRACT_DEFINED`

Target verdict:

`WEB_DIR_01_D4A_DATA_CONTRACT_SOURCE_CERTIFIED`

There is no D4A runtime verdict.
