# RL-CANDIDATE-01 — Candidate Artifact, Registry & Promotion Boundary Contract

Status: SOURCE CONTRACT V1 / candidate creation NOT YET AUTHORIZED

Parent architecture: #237  
Governance: #148  
Mission: #240  
Upstream:
- #238 — `RL_DATA_01_SOURCE_CERTIFIED`
- #239 — `RL_REPLAY_01_SOURCE_CERTIFIED`
- #248 — `RL_DIAG_01_PERFORMANCE_DIAGNOSTICS_SOURCE_CERTIFIED`

Certified upstream RL-DIAG head:

`35febd7d392071feaac3f79fea454b6f106bedf8`

Certified F00 source evidence used to define this contract:

- dataset_id:
  `4ea633a6a4e2ee0bc01a6fe855526d7c42451883ec0b6f3914cf21ea8e91cc8b`
- source_boundary_id:
  `2e6b478cd0cead58c1bcf25c168254b0a63daaa2722c6c108613eb81e283812e`
- factual research_run_id:
  `225368c15b6848936caf7fbd4433b8f713ef1333d547047c6bb55bd0777847ed`
- factual diagnostic_run_id:
  `3bcba4e0976f187bfcc20da70b306c2aaa2d03e3affc84bc2630598b50c3b08c`
- F00 diagnostic population:
  `N=13 / LOW_SAMPLE / DESCRIPTIVE_ONLY`

---

## 1. Mission

RL-CANDIDATE-01 converts Research findings into explicit, immutable,
provenance-bound candidate artifacts.

Canonical direction:

`CERTIFIED RESEARCH EVIDENCE → CANDIDATE ARTIFACT → EVALUATION EVIDENCE → PROMOTION REQUEST`

Never:

`RESEARCH FINDING → SILENT ACTIVE-RUNTIME CHANGE`

A candidate is a hypothesis-bearing Research object.

It is NOT:

- a PAPER fact;
- an active strategy;
- a runtime override;
- an authorization to change risk/sizing/gates;
- an authorization to open a new epoch;
- an authorization to start burn-in;
- an authorization for TESTNET/LIVE/exchange writes.

---

## 2. Core scientific doctrine

A candidate must make five things explicit:

1. **what evidence it came from**;
2. **what exactly changes**;
3. **what hypothesis the change is meant to test**;
4. **what evidence would support or falsify the hypothesis**;
5. **what separate gate is required before the change can ever reach a new experiment**.

No candidate may be created by silently copying a recommendation into runtime
configuration.

No candidate may rewrite the baseline that generated its parent evidence.

---

## 3. Candidate classes

Every candidate MUST declare exactly one primary `candidate_class`.

Allowed V1 values:

- `CONFIG`
- `STRATEGY`
- `FEATURE`
- `HYBRID`

### 3.1 CONFIG

A change expressible as deterministic configuration differences without changing
algorithmic source semantics.

Examples:

- threshold;
- cap;
- timeout;
- max positions;
- explicit enable/disable switch.

A CONFIG candidate MUST bind:

- baseline config identity;
- exact parameter paths;
- old values;
- proposed values;
- value types;
- materiality classification.

### 3.2 STRATEGY

A change to algorithmic decision logic.

Examples:

- signal logic;
- regime logic;
- gate logic;
- risk logic;
- sizing policy;
- execution policy.

A STRATEGY candidate MUST bind:

- exact baseline source SHA;
- exact proposed source SHA once implementation exists;
- changed paths;
- canonical patch/diff digest;
- semantic target domain.

A prose-only strategy proposal may exist in `CANDIDATE` state, but it may not
advance to `REPLAYED` until an exact implementation identity exists.

### 3.3 FEATURE

A new or modified Research/decision feature whose semantics are explicitly
versioned.

A FEATURE candidate MUST declare:

- feature name;
- source inputs;
- derivation;
- units/range;
- missing-value policy;
- intended consumer;
- whether it can change selection, sizing, risk or execution.

A feature that changes runtime decisions is promotable only through the same
promotion boundary as a strategy/config candidate.

### 3.4 HYBRID

A candidate that necessarily combines code + configuration and/or feature
changes.

HYBRID MUST enumerate every component and MUST NOT hide a material code change
inside a config-only label.

---

## 4. Target domains

Each candidate MUST declare one or more target domains from this bounded set:

- `SIGNAL`
- `STRATEGY`
- `REGIME`
- `GATE`
- `RISK`
- `SIZING`
- `EXECUTION`
- `FEATURE_PIPELINE`
- `RESEARCH_ONLY`

`RESEARCH_ONLY` means the candidate cannot alter a PAPER population.

If any component can change:

- trade admission;
- side;
- entry/exit timing;
- principal;
- TP/SL/timeout;
- capital exposure;
- order routing;

then the candidate MUST NOT be classified as `RESEARCH_ONLY`.

---

## 5. Immutable candidate artifact

The canonical candidate artifact is an immutable JSON document.

Logical path:

`research_candidate/candidates/<candidate_id>/candidate.json`

Creation uses write-once semantics.

A candidate artifact is never rewritten to update evaluation status.

Evaluation and lifecycle progression are recorded in separate immutable events /
artifacts.

Required top-level fields:

```text
candidate_schema
candidate_id
candidate_class
target_domains
parents
baseline
proposal
hypothesis
evaluation_plan
known_limitations
promotion_policy
created_at_utc
```

`created_at_utc` is provenance metadata and MUST NOT participate in
`candidate_id`.

---

## 6. Parent evidence bindings

Every candidate MUST identify the exact evidence that motivated it.

Required `parents` fields:

- `dataset_ids[]`
- `source_boundary_ids[]`
- `research_run_ids[]`
- `diagnostic_run_ids[]`

Optional, when applicable:

- `paper_epoch_ids[]`
- exact Research artifact digests;
- exact DecisionPacket component digest;
- exact capability-matrix version.

Rules:

- arrays are canonicalized in sorted order;
- duplicate identities are forbidden;
- at least one `dataset_id` is required;
- at least one `research_run_id` or `diagnostic_run_id` is required;
- a candidate may bind multiple datasets/runs only when the evaluation question
  explicitly spans them;
- no heuristic parent relationship is allowed.

For the current first candidate generation, F00 evidence remains LOW_SAMPLE and
must be represented as such in `known_limitations`.

---

## 7. Baseline identity

A candidate is meaningless without an explicit baseline.

Required `baseline` fields:

- `source_code_sha`
- `config_hash`
- `paper_epoch_id` when derived from PAPER;
- `strategy_id` if and only if a canonical certified strategy identity exists;
- `baseline_semantics_version`
- `baseline_population_definition`

If no canonical strategy_id exists, the field MUST be:

`NOT_AVAILABLE`

It MUST NOT be invented from filenames or informal strategy labels.

For a config proposal, the baseline parameter value MUST be evidence-bound.

For a code proposal, the baseline source SHA MUST be exact.

---

## 8. Canonical proposal diff

A proposal MUST be machine-readable.

### 8.1 CONFIG diff

Canonical record:

```json
{
  "kind": "CONFIG_SET",
  "path": "MEXC_SIM_MAX_POSITION_USD",
  "old_value": "10",
  "new_value": "20",
  "value_type": "float",
  "materiality": "SIZING"
}
```

Allowed CONFIG operations:

- `CONFIG_SET`
- `CONFIG_ADD`
- `CONFIG_REMOVE`

A CONFIG diff MUST contain the baseline value where one exists.

### 8.2 CODE diff

Canonical record:

```json
{
  "kind": "CODE_PATCH",
  "baseline_source_sha": "<sha40>",
  "proposed_source_sha": "<sha40-or-NOT_IMPLEMENTED>",
  "changed_paths": ["..."],
  "patch_sha256": "<sha256-or-NOT_IMPLEMENTED>",
  "semantic_domain": "SIZING"
}
```

A candidate with `NOT_IMPLEMENTED` code identity may remain `CANDIDATE` only.

### 8.3 FEATURE diff

Canonical record binds:

- feature name;
- feature semantic version;
- derivation specification digest;
- input schema;
- output schema;
- missing/UNKNOWN behavior;
- intended decision consumer;
- whether the feature affects population or capital.

### 8.4 HYBRID diff

A HYBRID proposal contains an ordered canonical list of component diffs.

All component diffs participate in candidate identity.

---

## 9. Deterministic candidate identity

The scientific identity document is:

```text
candidate_identity = {
  candidate_identity_schema,
  candidate_class,
  target_domains,
  parents,
  baseline,
  proposal,
  hypothesis_identity,
  evaluation_plan_identity,
  promotion_policy_version
}
```

Canonical serialization:

- UTF-8 JSON;
- keys sorted;
- compact separators `(",", ":")`;
- `allow_nan=false`;
- target domains sorted;
- parent identity arrays sorted;
- deterministic ordered proposal components.

Then:

`candidate_id = SHA256(canonical candidate_identity bytes)`

The following MUST NOT participate in `candidate_id`:

- creation timestamp;
- hostname;
- PID;
- absolute path;
- GitHub issue/PR number;
- human display name;
- lifecycle status;
- evaluation results;
- reviewer/operator name;
- promotion timestamp.

Invariant:

same parents + same baseline + same proposal + same hypothesis/evaluation
semantics ⇒ same `candidate_id`.

---

## 10. Candidate config hash

For candidates that produce a complete projected configuration:

`candidate_config_hash = SHA256(canonical projected material config)`

Rules:

- the projected config MUST be derived from an exact baseline config plus the
  declared config diff;
- no implicit environment default may silently participate;
- unresolved/dynamic values fail closed;
- secrets are excluded from Research artifacts;
- changing any material config value changes `candidate_config_hash`.

If the candidate does not define a complete projected config:

`candidate_config_hash = NOT_AVAILABLE`

No placeholder hash is allowed.

---

## 11. Hypothesis contract

Every candidate MUST state one falsifiable Research hypothesis.

Required fields:

- `question`
- `rationale`
- `mechanism`
- `primary_metric`
- `expected_direction`
- `guardrail_metrics[]`
- `minimum_evidence_requirements[]`
- `falsification_conditions[]`

Example form:

> If X is changed while Y remains fixed, metric M is expected to improve under
> population P without violating guardrails G.

The hypothesis MUST distinguish:

- observed factual evidence;
- Research inference;
- proposed causal mechanism.

A descriptive F00 association may motivate a candidate, but must not be relabeled
as causal evidence.

---

## 12. Evaluation plan

A candidate MUST define its evaluation plan before evaluation results exist.

Required fields:

- evaluation method(s);
- required dataset identities;
- population definition;
- primary metric semantics;
- guardrail metric semantics;
- minimum sample/evidence requirement;
- comparison baseline;
- missing-evidence behavior;
- determinism requirements.

Allowed V1 evaluation modes:

- `FACTUAL_BINDING_CHECK`
- `OFFLINE_REPLAY`
- `DESCRIPTIVE_COMPARISON`
- `COUNTERFACTUAL_REPLAY` only when required evidence is certified;
- `SHADOW` only after separate readiness certification;
- `NEW_PAPER_EPOCH` only after explicit promotion authorization.

If RL-DATA/RL-REPLAY evidence cannot support the declared counterfactual, the
candidate remains unevaluated for that claim.

Missing market-path evidence MUST NOT be replaced with synthetic prices unless a
separately certified SYNTHETIC dataset is explicitly declared.

---

## 13. Metric result contract

Evaluation results are separate immutable artifacts.

Each metric result MUST carry:

- `metric_name`
- `metric_semantics_version`
- `dataset_id`
- `population_definition`
- `n`
- `value` or explicit non-numeric status;
- `evidence_status`
- `statistical_strength`
- `baseline_value` where comparable;
- `candidate_value` where computed;
- `delta` only when the comparison is scientifically valid;
- `derivation`

Allowed evidence status values:

- `COMPLETE`
- `PARTIAL`
- `NOT_AVAILABLE`
- `NOT_APPLICABLE`
- `UNRESOLVED`

Allowed statistical strength values inherit RL-DIAG:

- `DESCRIPTIVE_ONLY`
- `LOW_SAMPLE`
- `ADEQUATE_FOR_DECLARED_TEST`
- `NOT_EVALUATED`

No aggregate score may hide unavailable guardrails.

---

## 14. Known limitations

Every candidate MUST carry a non-empty `known_limitations` array.

For candidates derived from current F00 evidence, at minimum include relevant
limitations such as:

- `N=13 / LOW_SAMPLE`;
- no general market-path counterfactual from RL-DATA v1;
- no certified rejected-opportunity universe;
- no annualized Sharpe basis;
- no mark-to-market MaxDD path;
- no canonical close cause;
- no canonical strategy_id when absent.

A candidate with no known limitations is invalid.

---

## 15. Candidate lifecycle

Canonical state machine:

`CANDIDATE → REPLAYED → SHADOW_READY → QUALIFIED → PROMOTED_TO_NEW_EPOCH`

Terminal/non-promoting states:

- `REJECTED`
- `DORMANT`
- `RETIRED`

### 15.1 CANDIDATE

Requirements:

- immutable candidate artifact valid;
- deterministic candidate_id;
- parent evidence valid;
- hypothesis and evaluation plan frozen.

No performance claim is implied.

### 15.2 REPLAYED

Requirements:

- at least one governed evaluation run;
- exact evaluation identity;
- baseline/candidate comparison only where evidence supports it;
- all missing evidence explicit.

`REPLAYED` does NOT mean better.

### 15.3 SHADOW_READY

Requirements:

- source implementation identity exact;
- required offline tests/CI green;
- no unsupported evidence dependency;
- shadow experiment contract defined;
- no PAPER authority.

`SHADOW_READY` does NOT authorize starting SHADOW.

### 15.4 QUALIFIED

Requirements:

- declared evaluation plan satisfied;
- primary metric condition satisfied under its declared semantics;
- every mandatory guardrail satisfied;
- sample/evidence minimum satisfied;
- no unresolved safety/provenance blocker;
- qualification evidence immutable.

`QUALIFIED` does NOT authorize runtime mutation.

### 15.5 PROMOTED_TO_NEW_EPOCH

This state may be recorded only AFTER a separate promotion gate creates and
certifies a new experimental boundary.

Required binding:

- promoted candidate_id;
- exact promoted source SHA;
- exact promoted config hash;
- new paper_epoch_id;
- promotion authorization evidence;
- previous baseline epoch;
- rollback boundary;
- creation/cutover evidence.

Promotion NEVER mutates the parent F00 epoch.

---

## 16. Terminal states

### REJECTED

Use when evidence falsifies the hypothesis, a mandatory guardrail fails, or the
candidate is scientifically invalid.

Reason is required.

### DORMANT

Use when the hypothesis remains potentially useful but required evidence is not
currently available or the candidate is intentionally deferred.

DORMANT is preferable to fabricating a counterfactual.

### RETIRED

Use for a previously useful/qualified candidate that is superseded or no longer
eligible for promotion.

Retirement reason and successor candidate_id, when applicable, are recorded.

Terminal status changes are lifecycle events; the immutable candidate artifact
is not rewritten.

---

## 17. Candidate lifecycle event log

Candidate status is event-sourced.

Logical layout:

```text
research_candidate/
  candidates/
    <candidate_id>/
      candidate.json
      evaluations/
        <evaluation_run_id>/
          manifest.json
          metrics.json
  registry/
    candidate_events.jsonl
```

Canonical event fields:

- event_id;
- sequence;
- candidate_id;
- event_type;
- previous_state;
- new_state;
- evidence_refs[];
- reason;
- timestamp_utc.

`event_id` is deterministic from candidate_id + event semantics + exact evidence
refs where feasible.

The registry MUST fail closed on:

- duplicate sequence;
- duplicate event_id;
- illegal state transition;
- unknown candidate_id;
- promotion without exact new-epoch binding.

---

## 18. Promotion request boundary

Promotion is a separate object from the candidate.

Logical object:

`promotion_request.json`

Required fields:

- promotion_request_id;
- candidate_id;
- candidate_state;
- qualification evidence refs;
- target environment;
- target source SHA;
- target config hash;
- requested new paper_epoch_id or epoch-creation intent;
- baseline epoch;
- rollback plan;
- required operator authorization;
- required preflight checks;
- status.

Allowed V1 target environment:

`PAPER_NEW_EPOCH`

Not allowed by RL-CANDIDATE-01:

- direct LIVE promotion;
- direct TESTNET promotion;
- mutation of active/certified F00;
- in-place editing of a running burn-in;
- silent systemd/env mutation.

---

## 19. Promotion invariants

A promotion request MUST fail closed unless all are true:

1. candidate state is `QUALIFIED`;
2. candidate artifact identity is valid;
3. parent Research evidence remains available and immutable;
4. exact implementation source SHA exists;
5. exact candidate config hash exists when material configuration changes;
6. mandatory evaluation/guardrail evidence is complete;
7. no unresolved promotion blocker remains;
8. target is a new explicit experimental boundary;
9. operator authorization is separately recorded;
10. runtime preflight is performed by the future promotion mission, not by this
    registry.

Even with all conditions satisfied, RL-CANDIDATE-01 itself does not execute the
promotion.

---

## 20. F00/A5 sizing-specific implication

RL-DIAG A5 proved:

- DecisionPacket/CapitalEngine sizing context varied between 30 and 37.5 USDT;
- PAPER passed `qty_usd=0.0`;
- MexcSimulator independently auto-sized from PPL available cash;
- frozen `MEXC_SIM_MAX_POSITION_USD=10`;
- all 13 authoritative PPL principals were exactly 10 USDT;
- 13/13 sizing formula reconciliation passed.

Therefore:

- this is valid candidate-generating evidence for a future SIZING architecture
  hypothesis;
- it is NOT evidence that executing the 30–37.5 USDT decision size would improve
  PnL;
- no alternate-size PnL may be fabricated from F00 v1;
- any sizing-unification candidate must define a future evaluation path capable
  of observing variable executed principal under a new experiment boundary.

---

## 21. First-candidate prohibition

This contract MUST be source-certified before creating the first actual candidate.

Until then:

`CANDIDATE_CREATION_AUTHORIZED = NO`

The first candidate must not be embedded into this contract commit.

Contract correctness and candidate merit are separate gates.

---

## 22. Hard safety boundary

RL-CANDIDATE source/contracts MUST NOT:

- modify certified F00 artifacts;
- append to PPL;
- mutate RL-DATA datasets;
- mutate RL-REPLAY/RL-DIAG published evidence;
- modify production `.env`;
- modify systemd;
- start/stop/restart Advisor or Watchdog;
- create a PAPER epoch;
- change runtime strategy/signal/gate/risk/sizing;
- call exchange write APIs;
- authorize burn-in;
- authorize TESTNET/LIVE.

Static tests MUST eventually enforce these boundaries for executable registry
code.

---

## 23. Source-certification gates for RL-CANDIDATE-01

Before target verdict:

`RL_CANDIDATE_PROMOTION_BOUNDARY_CERTIFIED`

the mission must prove at minimum:

1. candidate schema/identity determinism;
2. immutable candidate artifact behavior;
3. parent-evidence validation;
4. strict candidate class/diff validation;
5. config-hash determinism where applicable;
6. hypothesis/evaluation-plan validation;
7. lifecycle legal-transition enforcement;
8. illegal transition rejection;
9. evaluation artifact identity/provenance;
10. promotion-request validation;
11. promotion fail-closed without QUALIFIED state;
12. new-epoch-only promotion invariant;
13. no runtime/PPL/exchange mutation dependencies;
14. deterministic publication proof;
15. exact-head repository CI.

Only after the contract and implementation boundary are certified may actual
candidate creation/promotion workflows be used.

---

## 24. Immediate next gate

`RC1_CANDIDATE_CONTRACT_REVIEW`

This gate must verify:

- identity fields;
- canonical serialization;
- candidate classes;
- diff semantics;
- hypothesis schema;
- evaluation semantics;
- lifecycle state machine;
- promotion boundary;
- F00/A5 limitations;
- hard non-mutation boundary.

No actual candidate is created at RC1.
