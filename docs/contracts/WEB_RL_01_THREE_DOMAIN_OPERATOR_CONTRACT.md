# WEB-RL-01 — Three-Domain Operator Contract

Status: SOURCE CONTRACT V1 / WR1 REVIEW

Mission: #241  
Parent architecture: #237  
Governance: #148

Certified upstream:
- #238 — `RL_DATA_01_SOURCE_CERTIFIED`
- #239 — `RL_REPLAY_01_SOURCE_CERTIFIED`
- #248 — `RL_DIAG_01_PERFORMANCE_DIAGNOSTICS_SOURCE_CERTIFIED`
- #240 — `RL_CANDIDATE_PROMOTION_BOUNDARY_CERTIFIED`

Certified upstream RL-CANDIDATE head:

`7294d9b03b682a35edec919215375e3be49d372c`

Target verdict:

`WEB_RL_01_THREE_DOMAIN_SOURCE_CERTIFIED`

---

## 1. Mission

WEB-RL-01 makes the Operator Web App separate three scientific domains that
must never be visually or semantically conflated:

1. `MARKET_OBSERVATORY`
2. `PAPER_SCIENCE`
3. `RESEARCH_LAB`

The Web layer is presentation only.

It MUST NOT:

- become a second accounting engine;
- become a second market-analysis engine;
- recompute PAPER authority;
- recompute Research metrics;
- mutate candidate state;
- authorize promotion;
- mutate PAPER/runtime state;
- write to PPL;
- write to exchanges.

Canonical doctrine:

```text
SOURCE OWNER
   ↓
GOVERNED PRESENTATION ARTIFACT
   ↓
STRICT READ-ONLY API READER
   ↓
STRICT FRONTEND VALIDATOR
   ↓
DOMAIN-LABELED VIEW
```

Never:

```text
React → infer/recompute scientific truth
```

---

## 2. Top-level operator domains

Canonical top-level navigation:

```text
OVERVIEW
MARKET OBSERVATORY
PAPER SCIENCE
RESEARCH LAB
SYSTEM / GOVERNANCE
```

Existing lower-level views may remain internally reusable, but every rendered
metric belongs to exactly one source domain.

A metric MUST NOT migrate between domains merely for layout convenience.

---

## 3. Domain identities and authority

### 3.1 MARKET_OBSERVATORY

Purpose:

external market observations and market-discovery telemetry.

Canonical authority label:

`OBSERVATIONAL_TELEMETRY`

Allowed facts include only facts already produced by governed MARKET sources,
for example:

- source exchange/venue;
- source timestamp/freshness;
- symbol coverage;
- spot/perp/mark/index observations;
- producer-authored ranking/confidence;
- spread/depth/imbalance/microprice when certified;
- funding/basis/OI when certified;
- gaps/data-quality state.

Forbidden in MARKET_OBSERVATORY:

- PAPER equity/PnL;
- candidate qualification;
- PAPER trade admission;
- execution authority;
- strategy promotion.

The existing WEB-01 CryptoRadar route remains an independent read-only
observational boundary.

### 3.2 PAPER_SCIENCE

Purpose:

authoritative/current experiment facts and their governed passive
reconciliations.

Canonical source authorities may include:

- `PPL_AUTHORITY`
- other explicitly certified PAPER authority/provenance;
- passive `OBSERVATIONAL_TELEMETRY` comparison/reconciliation artifacts that
  describe PAPER but do not own PAPER.

Allowed facts include:

- paper_epoch_id;
- exact source/config identity;
- PPL available cash/reserved/open positions;
- OPEN/CLOSE/UNRESOLVED lifecycle;
- current PAPER population metrics when materialized by an authoritative
  producer;
- FIN reconciliation;
- passive PPL comparison evidence;
- current decisions/gates/admissions only with their existing authority labels.

Required banner:

`PAPER SCIENCE · ACTIVE EXPERIMENT · NOT REAL MONEY`

PAPER_SCIENCE MUST NOT ingest Research results as if they were active PAPER
facts.

### 3.3 RESEARCH_LAB

Purpose:

offline/non-authoritative Research evidence.

Canonical authority label:

`RESEARCH_NON_AUTHORITATIVE`

Allowed facts:

- certified dataset identities;
- source-boundary identities;
- deterministic replay identities;
- diagnostic identities;
- certified Research metrics;
- evidence status / statistical strength;
- attribution;
- candidate registry state;
- governed evaluation results;
- promotion-request state through
  `READY_FOR_AUTHORIZATION`.

Required banner:

`RESEARCH LAB · OFFLINE ANALYSIS · NOT PAPER CAPITAL`

Research Lab MUST NOT imply that a candidate is active PAPER merely because it
is REPLAYED, SHADOW_READY or QUALIFIED.

---

## 4. System / Governance domain

`SYSTEM_GOVERNANCE` is not a fourth scientific population.

It is a navigation/support domain for:

- system/read-only transport health;
- code/config provenance;
- certification state;
- known scientific debt;
- authority boundaries.

It MUST NOT compute or aggregate performance.

---

## 5. Overview doctrine

OVERVIEW may summarize domain status, but MUST NOT combine scientific
populations.

Allowed overview information:

- MARKET freshness/status;
- PAPER epoch/status;
- Research dataset/run/candidate counts;
- SYSTEM/governance status.

Forbidden overview information:

- combined MARKET + PAPER + Research PnL;
- combined WR/PF/Sharpe;
- one global "performance score" synthesized from different domains;
- one color-coded "good/bad" verdict that collapses domain-specific evidence.

Every overview card MUST carry a domain label.

---

## 6. Research Lab presentation boundary

Research Lab MUST consume one governed presentation artifact.

Logical product:

`ResearchLabSnapshot`

Logical read-only API route:

`GET /api/operator/v1/research-lab`

Logical atomic artifact:

`databases/research_presentation/research_lab_snapshot.json`

The path is a presentation artifact only.

The Operator API MUST NOT:

- read RL-DATA source JSONL directly;
- read PPL durable ledgers directly;
- scan arbitrary candidate directories;
- recompute diagnostic metrics;
- instantiate Research replay/diagnostic/candidate engines;
- write Research artifacts.

A future offline Research presentation builder may materialize the snapshot from
explicitly supplied certified Research artifacts.

The reader/API transports validated producer-authored facts only.

---

## 7. ResearchLabSnapshot closed schema

Normative schema:

`WEB_RL_RESEARCH_LAB_V1`

Required top-level fields:

```text
schema_version
product
domain
authority
generated_at_utc
presentation_builder_source_sha
research_state
provenance
population
performance
risk_stability
costs
attribution
candidate_registry
limitations
```

Required constants:

- `product = ResearchLabSnapshot`
- `domain = research_lab`
- `authority = RESEARCH_NON_AUTHORITATIVE`

Unknown top-level fields fail closed in V1.

---

## 8. Provenance envelope

Every Research Lab snapshot MUST carry one explicit `primary_context`.

The V1 primary context contains exactly one:

- `dataset_id`;
- `source_boundary_id`;
- `paper_epoch_id` when applicable;
- `research_run_id`;
- `diagnostic_run_id` when applicable;
- `research_source_code_sha`;
- `research_config_hash` when certified;
- `presentation_builder_source_sha`;
- `population_definition`
- `n`
- `evidence_status`
- `statistical_strength`
- source artifact identities/digests.

A Research metric MUST NOT be displayed without sufficient provenance to
identify its scientific population.

`research_source_code_sha` identifies the scientific code that produced the
Research evidence.

`presentation_builder_source_sha` identifies only the passive Web presentation
builder. These SHAs are different semantic identities and MUST NOT be
substituted for one another.

V1 does not aggregate multiple dataset populations into one primary context.
If several datasets/runs are presented in a future version, each metric group
must carry its own complete provenance and no combined performance total may be
computed.

The UI may collapse provenance visually, but the evidence must remain
expandable/inspectable.

---

## 9. Metric presentation object

Every Research metric uses a closed semantic wrapper:

```json
{
  "metric_name": "profit_factor",
  "value": 3.49,
  "unit": "ratio",
  "evidence_status": "COMPLETE",
  "statistical_strength": "LOW_SAMPLE",
  "population_n": 13,
  "derivation": "producer-authored description",
  "source_ref": "..."
}
```

Allowed evidence statuses inherit the certified Research contracts:

- `COMPLETE`
- `PARTIAL`
- `NOT_AVAILABLE`
- `NOT_APPLICABLE`
- `UNRESOLVED`

Allowed statistical-strength values:

- `DESCRIPTIVE_ONLY`
- `LOW_SAMPLE`
- `ADEQUATE_FOR_DECLARED_TEST`
- `NOT_EVALUATED`

Metric value semantics are fail-closed:

- `COMPLETE` or `PARTIAL`: `value` may be a producer-authored finite
  numeric/string fact compatible with the metric schema;
- `NOT_AVAILABLE`, `NOT_APPLICABLE`, or `UNRESOLVED`: `value = null`
  unless the contract for that specific metric explicitly permits a
  non-numeric explanatory value.

A non-finite numeric value is invalid.

If a metric is not scientifically available, the UI MUST render the explicit
status and reason.

It MUST NOT substitute:

- `0`
- `—` without semantic explanation;
- a guessed value;
- a neighboring metric.

---

## 10. Current F00 Research capability constraints

The first WEB-RL source implementation is constrained by currently certified
F00 Research evidence.

Currently supported/descriptive facts include:

- N = 13 CLOSED trades;
- realized net PnL;
- WR;
- PF;
- expectancy;
- realized close-to-close drawdown under its declared definition;
- fees where certified;
- regime/side/conviction attribution;
- distribution/concentration/leave-one-out diagnostics;
- provenance/integrity;
- A5 sizing architecture classification.

Current evidence is:

`LOW_SAMPLE / DESCRIPTIVE_ONLY`

The UI MUST make that limitation visible.

Currently NOT scientifically available for general F00 display include:

- annualized/time-series Sharpe;
- authoritative mark-to-market MaxDD;
- MFE/MAE;
- spread/slippage/adverse selection;
- funding decomposition;
- rejected-opportunity opportunity cost;
- general market-path counterfactual PnL;
- canonical strategy_id when absent.

A card for an unsupported metric may exist only if it displays
`NOT_AVAILABLE` with the evidence reason.

---

## 11. A5 sizing constraint

WEB-RL MUST preserve the certified A5 distinction:

- DecisionPacket / CapitalEngine sizing context varied between 30 and 37.5 USD;
- this was not forwarded as executed PAPER principal;
- PAPER used an independent simulator auto-size path;
- all authoritative F00 principals were 10 USD.

Therefore the UI MUST NOT:

- label 30–37.5 USD as executed size;
- compute hypothetical alternate PnL from it;
- imply that larger size would have improved F00;
- show the dual path as a financial incoherence.

Allowed label:

`EXPLAINED_DUAL_PATH_SIMULATOR_AUTO_SIZE`

---

## 12. Candidate Registry presentation

Candidate rows are Research objects.

Required fields for a candidate row:

- candidate_id;
- candidate_class;
- target_domains;
- lifecycle state;
- parent evidence refs;
- source/config identity;
- hypothesis summary;
- evaluation status;
- known limitations.

Allowed lifecycle vocabulary:

`CANDIDATE → REPLAYED → SHADOW_READY → QUALIFIED → PROMOTED_TO_NEW_EPOCH`

Terminal:

- `REJECTED`
- `DORMANT`
- `RETIRED`

UI semantics:

- `CANDIDATE` ≠ active;
- `REPLAYED` ≠ better;
- `SHADOW_READY` ≠ shadow started;
- `QUALIFIED` ≠ runtime authorization;
- `PROMOTED_TO_NEW_EPOCH` requires separate promotion evidence.

At present, no substantive candidate is implied by the certification of the
registry itself.

An empty candidate registry MUST render as an honest empty state, not a demo
candidate.

---

## 13. Baseline vs candidate comparison

Baseline/candidate deltas may be displayed only when producer-authored
evaluation evidence declares the comparison scientifically valid.

The frontend MUST NOT calculate:

`candidate_value - baseline_value`

unless the producer artifact already contains a certified delta.

If the evaluation contract says:

`NOT_COMPARABLE`

the UI renders exactly that state.

No aggregate ranking or candidate "winner" is computed by React.

---

## 14. Attribution

Research attribution may display only producer-authored certified dimensions.

Currently validated F00 examples include:

- categorical regime;
- side;
- conviction;
- selected DecisionPacket context;
- concentration.

Important semantic separation:

- `packet.regime` = categorical market regime;
- `features.regime` = numeric LSE regime component score.

These fields MUST NOT be merged into one "regime" value.

---

## 15. UNKNOWN / UNRESOLVED doctrine

Across all three domains:

`UNKNOWN != ZERO`

`UNRESOLVED != LOSS`

`UNRESOLVED != WIN`

`NOT_AVAILABLE != 0`

Frontend formatting MUST preserve semantic status.

React MUST NOT use transformations such as:

- `value || 0`
- `value ?? 0`

for scientific metrics unless zero is itself explicitly producer-authored.

This applies particularly to:

- PnL;
- fees;
- count denominators;
- WR;
- PF;
- expectancy;
- drawdown;
- candidate deltas.

---

## 16. PAPER vs Research hard separation

Forbidden:

- combined PAPER + Research equity curve;
- combined PnL;
- combined population N;
- combined WR/PF/Sharpe;
- Research diagnostic value displayed under a PAPER authority badge;
- PAPER current value displayed as Research evaluation evidence without an
  explicit Research binding;
- Research candidate state changing PAPER presentation state.

Any metric shown in multiple domains must carry independent domain-specific
provenance.

---

## 17. No scientific formulas in React

Frontend code may:

- format producer values;
- choose responsive layout;
- expand/collapse provenance;
- map explicit semantic status to presentation classes;
- filter/sort already-present rows for human browsing.

Frontend code MUST NOT:

- derive PnL;
- derive PF;
- derive WR;
- derive Sharpe;
- derive drawdown;
- derive candidate qualification;
- infer authority;
- normalize UNKNOWN to zero;
- generate counterfactual values;
- repair source inconsistencies.

---

## 18. Research presentation producer

A future WEB-RL Research presentation builder is passive/offline.

It may read only explicitly supplied, already-certified Research artifacts.

V1 MUST NOT discover inputs by recursively scanning arbitrary repository or VPS
directories.

Input identities are explicit.

Output is one atomic/immutable-at-publication presentation snapshot.

The builder does not modify its source artifacts.

The presentation builder MUST NOT recompute scientific performance facts.

Forbidden builder computations include:

- PnL;
- WR;
- PF;
- expectancy;
- Sharpe;
- drawdown;
- fees/funding/slippage;
- attribution totals;
- candidate metric deltas;
- qualification verdicts.

The builder may perform presentation-only structural operations such as:

- validating schema/identity;
- selecting explicitly requested producer-authored fields;
- preserving producer-authored ordering or applying deterministic display
  ordering;
- counting rows only when the count is labeled as a presentation inventory
  count, not a scientific population metric;
- writing atomic JSON.

Scientific metric values and scientific deltas must already exist in the
certified source artifact.

---

## 19. API boundary

The Research API reader MUST:

- read one configured presentation artifact;
- validate a closed schema;
- reject malformed/unknown semantic values;
- return structured 503 on missing/malformed/unsupported artifact;
- add only reader-authored freshness metadata if the contract declares it;
- never instantiate Research engines.

All operator API business routes remain GET-only.

WEB-RL does not add POST/PUT/PATCH/DELETE business routes.

---

## 20. Frontend validation boundary

The frontend Research client MUST validate:

- schema version;
- product/domain/authority constants;
- provenance identities;
- metric wrappers;
- evidence status;
- statistical strength;
- candidate lifecycle vocabulary.

Malformed Research payloads fail closed as transport/contract errors.

The view MUST NOT partially render an unvalidated Research payload.

---

## 21. Domain visual identity

Visual distinction is semantic, not decorative.

Required domain labels:

- `MARKET OBSERVATORY`
- `PAPER SCIENCE`
- `RESEARCH LAB`

Research Lab must visibly include:

`NON-AUTHORITATIVE`

PAPER Science must visibly include:

`NOT REAL MONEY`

Domain labels remain visible on mobile.

Color alone MUST NOT carry the domain distinction.

---

## 22. Desktop Research layout

Target hierarchy:

```text
RESEARCH LAB · NON-AUTHORITATIVE
dataset / run / epoch / N / evidence strength

POPULATION | PERFORMANCE | RISK/STABILITY | DATA QUALITY

PERFORMANCE ATTRIBUTION

COST / MECHANISM DIAGNOSTICS

REPLAY / EVALUATION EVIDENCE

CANDIDATE REGISTRY
```

Sections with unavailable evidence remain visible only when useful to explain
that the metric is unavailable.

No dense table is required as the primary view.

---

## 23. Mobile Research layout

Required:

- sticky/visible Research domain banner;
- provenance summary before metrics;
- metric cards;
- explicit evidence/status badges;
- expandable detailed provenance;
- candidate cards instead of desktop-wide tables;
- no horizontal dependency for core interpretation.

---

## 24. Existing view migration

WEB-RL source work may reorganize existing views under the new navigation
without changing their data authority.

Examples:

MARKET OBSERVATORY:
- current MarketView.

PAPER SCIENCE:
- current PAPER overview/portfolio/decisions;
- PPL comparison as passive PAPER-science reconciliation;
- FIN reconciliation.

SYSTEM / GOVERNANCE:
- system health;
- deployment/governance evidence.

Migration MUST NOT rewrite producer semantics.

---

## 25. Research availability/failure states

Research Lab has explicit states:

- `AVAILABLE`
- `EMPTY`
- `UNAVAILABLE`
- `MALFORMED`
- `STALE` only when a presentation-currency policy is explicitly defined.

Offline Research evidence does not become scientifically invalid merely because
wall-clock time passes. `generated_at_utc` is publication provenance, not a
performance-validity clock.

`EMPTY` means a valid Research artifact with no candidate/evaluation rows.

`UNAVAILABLE` means no valid presentation artifact exists.

The frontend MUST NOT substitute demo/sample Research data in either state.

---

## 26. Certification scope

WEB-RL source certification proves:

- domain navigation/source separation;
- Research presentation schema;
- strict read-only transport;
- frontend validation;
- provenance visibility;
- explicit unsupported-metric behavior;
- candidate non-authority semantics;
- responsive domain identity;
- repository CI.

It does NOT prove:

- Research profitability;
- candidate merit;
- runtime deployment;
- live browser reachability on VPS;
- burn-in readiness;
- TESTNET/LIVE readiness.

---

## 27. Hard non-authorizations

WEB-RL-01 does NOT authorize:

- merge of stacked Research PRs to main;
- production deployment;
- systemd changes;
- runtime restart;
- PAPER epoch creation;
- burn-in;
- candidate promotion;
- strategy/risk/sizing mutation;
- exchange writes;
- TESTNET/LIVE;
- FIN-03.

---

## 28. WR1 contract review criteria

Gate:

`WR1_THREE_DOMAIN_CONTRACT_REVIEW`

WR1 PASS requires explicit, non-ambiguous definitions for:

1. MARKET/PAPER/RESEARCH domain identities;
2. authority labels;
3. overview non-aggregation rule;
4. Research presentation artifact boundary;
5. single-population V1 primary context;
6. research-source SHA vs presentation-builder SHA separation;
7. provenance envelope;
8. metric evidence wrapper and null semantics;
9. current F00 capability/NOT_AVAILABLE constraints;
10. A5 sizing semantics;
11. candidate lifecycle display semantics;
12. baseline/candidate comparison rule;
13. UNKNOWN/UNRESOLVED doctrine;
14. no-scientific-formulas-in-React rule;
15. no-scientific-formulas-in-presentation-builder rule;
16. strict GET-only API reader boundary;
17. strict frontend validator boundary;
18. responsive domain visual identity;
19. empty/unavailable Research states;
20. hard non-authorizations.

WR1 PASS authorizes source implementation only.

It does not authorize deployment.

---

## 29. Post-WR1 implementation gates

After WR1 PASS:

`WR2_RESEARCH_PRESENTATION_SCHEMA_AND_READER`

Then:

`WR3_FRONTEND_THREE_DOMAIN_NAVIGATION_AND_RESEARCH_VIEW`

Then:

`WR4_CROSS_STACK_VISUAL_AND_EXACT_HEAD_CI`

Final target:

`WEB_RL_01_THREE_DOMAIN_SOURCE_CERTIFIED`
