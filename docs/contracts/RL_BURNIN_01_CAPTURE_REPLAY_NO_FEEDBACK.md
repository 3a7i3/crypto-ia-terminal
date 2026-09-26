# RL-BURNIN-01 — Burn-in Capture, Replayability & No-Feedback Contract

Status: A1 FORENSIC / SOURCE CONTRACT DRAFT / BURN-IN NOT AUTHORIZED

Mission: #242
Parent architecture: #237
Governance: #148

Certified Research upstream:
- #238 — `RL_DATA_01_SOURCE_CERTIFIED`
- #239 — `RL_REPLAY_01_SOURCE_CERTIFIED`
- #248 — `RL_DIAG_01_PERFORMANCE_DIAGNOSTICS_SOURCE_CERTIFIED`
- #240 — `RL_CANDIDATE_PROMOTION_BOUNDARY_CERTIFIED`
- #241 — `WEB_RL_01_THREE_DOMAIN_SOURCE_CERTIFIED`

Certified stacked source base:

`WEB-RL@6bc2096c0edd0207750efe1cc37cfedc60dcbb81`

Target verdict:

`RL_BURNIN_NO_FEEDBACK_CERTIFIED`

---

## 1. Mission

RL-BURNIN-01 certifies that a future PAPER burn-in can become a reproducible
Research dataset without allowing Research findings, candidate state, test
activity or legacy measurement paths to alter that same burn-in.

This mission is a pre-burn-in gate.

It does NOT start a burn-in.

Canonical doctrine:

```text
FROZEN FUTURE PAPER EPOCH
        ↓
AUTHORITATIVE PPL FACTS
        ↓
IMMUTABLE RL-DATA CAPTURE(S)
        ↓
DETERMINISTIC RL-REPLAY / RL-DIAG
        ↓
NON-AUTHORITATIVE CANDIDATES
        ↓
SEPARATE PROMOTION AUTHORIZATION
        ↓
FUTURE EPOCH ONLY
```

Forbidden:

```text
RESEARCH / TESTS / LEGACY REPORTERS
        ↓
mutation of the same active burn-in
```

---

## 2. Source facts already certified

The current Research source chain already provides important parts of the
required boundary.

### 2.1 RL-DATA

RL-DATA is offline and explicit-path only.

Certified properties include:

- no environment discovery in the Research exporter;
- no runtime/service discovery;
- read-only validation of the canonical PPL epoch file;
- source bytes fingerprinted before publication;
- append-only source prefix re-verified before export completion;
- Research output forbidden from overlapping protected source storage;
- immutable dataset publication;
- deterministic `source_boundary_id` and `dataset_id`;
- explicit `paper_epoch_id`, source/config/code identities and source digests.

This means accumulating PAPER evidence can be captured as immutable Research
boundaries without mutating the source.

### 2.2 RL-REPLAY / RL-DIAG

Certified properties include:

- replay operates offline from immutable Research evidence;
- publication is write-once under a caller-supplied Research root;
- replay output carries `dataset_id`, `source_boundary_id`,
  `paper_epoch_id`, `research_run_id`, code/config identity and population;
- unsupported scientific metrics remain explicit `NOT_AVAILABLE`;
- unresolved lifecycles are excluded from closed-performance populations rather
  than converted to numeric zero.

### 2.3 RL-CANDIDATE

Certified properties include:

- candidate artifacts are Research-side and non-authoritative;
- candidate lifecycle does not imply PAPER activation;
- qualification does not grant runtime authority;
- promotion requires a separate explicit promotion request/boundary;
- no candidate may silently mutate the active PAPER experiment.

### 2.4 WEB-RL

The operator presentation already preserves MARKET / PAPER / RESEARCH domain
separation and cannot turn Research evidence into PAPER authority.

---

## 3. A1 forensic blockers

A1 found three pre-certification blockers.

### B1 — HERM-02 / #267

Status: CONFIRMED.

Root pytest isolation uses ambient-preserving `setdefault` for several durable
runtime paths. A test process launched from an operator/VPS shell may therefore
inherit a real external path and mutate it while the repository-scoped
Scientific Data Guard remains blind.

Affected exposed variables identified by #267:

- `OBS_LOG_ROOT`;
- `REJECTION_STORE_DIR`;
- `BB_PATH`;
- `LMI_DIR`;
- `ORDER_INTENT_JOURNAL_PATH`;
- `DECISION_IDENTITY_JOURNAL_PATH`.

This is incompatible with a no-feedback burn-in guarantee.

Required before final #242 certification:

`HERM_02_TEST_PERSISTENCE_ISOLATION_CERTIFIED`

or an equivalently explicit certified verdict closing #267.

### B2 — ACC-01 / #268

Status: CONFIRMED on the LEGACY population path.

When `PAPER_LIFECYCLE_AUTHORITY` is unset, LEGACY is the default. The current
legacy loader can retain a CLOSE with `pnl_usd=None`; downstream `or 0`
coercion can then classify that unresolved outcome as a winner or silently
dilute scientific metrics.

The canonical PPL/RL-REPLAY/RL-DIAG path is already fail-closed and certified
clean. The defect must nevertheless be closed before a future burn-in can be
certified, because an ad-hoc operator measurement must not silently fall back
to a contradictory population contract.

Required before final #242 certification:

`ACC_01_UNRESOLVED_ACCOUNTING_BOUNDARY_CERTIFIED`

or an equivalently explicit certified verdict closing #268.

### B3 — future burn-in epoch identity

RB3 implements an explicit burn-in identity candidate without reusing F00
semantics:

- `epoch_role=BURN_IN_EXPERIMENT`;
- authority manifest schema v3;
- PPL event schema v2;
- predecessor authority epoch required;
- event-identity domain `BURN-IN-EPOCH-AUTHORITY-V1`;
- event-id prefix `burnin-`;
- config snapshot schema `BURN_IN_EXPERIMENT_CONFIG_V1`.

Backward compatibility is structural and explicit:

- v1 / `PPL_AUTHORITY_TRANSITION` remains accepted unchanged;
- v2 / `F00_EXPERIMENT` remains accepted unchanged;
- F00 continues to use `F00-EPOCH-AUTHORITY-V1` and the `f00-` prefix;
- the F00 config CLI still defaults to `F00_EXPERIMENT_CONFIG_V1`;
- RL-DATA accepts only explicitly enumerated scientific role/schema pairs.

The deterministic F00 config-freeze engine is reused through an explicit
snapshot-schema parameter. The burn-in wrapper adds semantic identity only; it
does not duplicate configuration-discovery, secret-filtering, hashing,
immutability or drift-validation algorithms.

This section describes the implemented source candidate. It is not a PASS
claim until RB3 source tests and exact-head governance evidence are complete.

---

## 4. Legacy burn-in reporters are not Research scientific authority

Existing scripts such as `scripts/burnin_calibration_v3.py` and
`scripts/prelive_gate.py` are legacy/operator measurement surfaces.

They may remain useful operationally, but #242 MUST NOT use them as the
authoritative Research evidence path.

In particular:

- `burnin_calibration_v3.py` currently derives an approximate annualized
  Sharpe from per-trade `pnl_pct`;
- certified Research presentation correctly declares annualized/time-series
  Sharpe `NOT_AVAILABLE` when the required time-series basis is absent;
- #242 must preserve the Research definition and must not upgrade a legacy
  approximation into certified scientific truth.

Canonical #242 performance evidence must come from the governed
RL-DATA → RL-REPLAY/RL-DIAG path and its declared population/limitations.

---

## 5. Burn-in identity contract

Before burn-in authorization, the future experiment must have one immutable
identity envelope containing at minimum:

- `paper_epoch_id`;
- explicit experiment role;
- manifest schema version;
- initial virtual capital;
- exact runtime `code_sha`;
- exact governed configuration hash;
- predecessor authority epoch identity;
- creation timestamp;
- PPL event schema version;
- immutable manifest digest;
- immutable config snapshot digest.

No burn-in statistic is scientifically valid without binding to this identity.

A future burn-in epoch MUST NOT reuse the certified F00 `paper_epoch_id`.

---

## 6. Accumulating capture contract

During an active burn-in, Research may create immutable prefix captures.

Each capture must:

- bind to exactly one `paper_epoch_id`;
- record exact source byte boundary and SHA-256;
- preserve event sequence and lifecycle validity;
- preserve exact manifest/config identities;
- expose one deterministic `source_boundary_id`;
- expose one deterministic `dataset_id`;
- never truncate, rewrite or lock the active PPL store;
- never write below PAPER/runtime source roots;
- never become a PAPER authority artifact.

Two captures of the exact same source boundary and scientific components must
resolve to the same scientific identities independent of extraction wall time.

A later appended PPL prefix must resolve to a different source boundary.

---

## 7. Final burn-in dataset contract

After the burn-in is stopped at a governed boundary, one final immutable
Research export may be designated the burn-in dataset of record.

Designation requires:

- burn-in epoch stopped/quiescent;
- no lifecycle transition in flight;
- exact final PPL event count and SHA-256;
- exact final manifest/config fingerprints;
- complete/unresolved lifecycle counts;
- final `source_boundary_id`;
- final `dataset_id`;
- explicit `FINAL_BURN_IN_DATASET` designation in governance evidence.

Designation does not rewrite earlier prefix captures.

---

## 8. Deterministic replay contract

The final burn-in dataset must replay deterministically.

For the same:

- dataset;
- replay code SHA;
- replay configuration;
- replay method;
- declared population;

the scientific replay identity and scientific components must be identical.

Publication time is provenance only and must not alter the scientific
`research_run_id`.

Replay must not open runtime/PPL sources or perform exchange writes.

---

## 9. No-feedback contract

During the same active burn-in:

Research MAY:

- export immutable prefixes;
- replay exported prefixes;
- run diagnostics;
- create candidates;
- create promotion requests for later governance review.

Research MUST NOT:

- modify the active PAPER config;
- modify strategy/signal/risk/sizing/execution parameters;
- mutate PPL events;
- write to runtime journals used by the active experiment;
- activate a candidate;
- change the active epoch identity;
- change PAPER capital;
- restart/deploy the runtime as a consequence of Research output;
- promote a candidate into the same active burn-in.

Any accepted Research improvement must target a separately identified future
epoch.

---

## 10. Test-process non-feedback requirement

A test process executed on the same host as the burn-in must be unable to mutate
burn-in/runtime persistence through inherited ambient paths.

Therefore #267 is a hard #242 prerequisite.

Required proof includes at least:

- ambient sentinel paths are overwritten by pytest isolation before collection;
- external pre-existing order-intent/decision-identity evidence remains
  byte-identical after targeted tests;
- `BB_PATH` is redirected per test;
- Scientific Data Guard remains a secondary detector, not the primary
  prevention mechanism.

---

## 11. Accounting fail-closed requirement

Any metric consumer used in burn-in governance must satisfy:

`UNRESOLVED != ZERO`

`NOT_AVAILABLE != ZERO`

`MISSING_PNL != WIN`

A missing/unresolved PnL must either:

- be excluded from a declared CLOSED-performance population; or
- produce an explicit unresolved/not-available status.

It must never be numerically coerced for convenience.

Therefore #268 is a hard #242 prerequisite.

The treatment of an exact realized `pnl_usd == 0.0` must also be explicit and
tested; it must not be conflated with missing PnL.

---

## 12. Certification gates

### RB1 — CONTRACT / FORENSIC REVIEW

PASS requires:

- exact upstream Research source heads identified;
- existing certified one-way Research boundaries mapped;
- #267 and #268 explicitly recognized as blockers;
- future burn-in epoch-role gap explicitly recognized;
- legacy burn-in reporters excluded from Research scientific authority.

Target:

`RB1_BURNIN_CONTRACT_FORENSIC_PASS`

### RB2 — BLOCKER REMEDIATION

PASS requires certified closure of:

- #267 HERM-02;
- #268 ACC-01.

Target:

`RB2_PRE_BURNIN_DEBT_CLOSED`

### RB3 — BURN-IN EPOCH IDENTITY

PASS requires an explicit, backward-compatible representation of a future
burn-in experiment manifest/config identity.

Implemented source candidate:

- `BURN_IN_EXPERIMENT` / manifest v3;
- `BURN_IN_EXPERIMENT_CONFIG_V1`;
- distinct burn-in event domain/prefix;
- explicit RL-DATA role/schema validation;
- F00 v2 output names preserved for backward compatibility;
- burn-in Research exports use distinct authoritative file/component names.

Target:

`RB3_BURNIN_EPOCH_IDENTITY_CERTIFIED`

Status: `RB3_BURNIN_EPOCH_IDENTITY_CERTIFIED`.

Certification requires the dedicated `RL-BURNIN Source Proof` gate to be
SUCCESS on the exact RB3 head. The exact certified SHA and workflow run are
recorded in #242 / #148 governance evidence; this contract does not authorize
runtime creation of the represented burn-in epoch.

### RB4 — CAPTURE / FINALIZATION

PASS requires deterministic immutable prefix capture plus governed final dataset
designation from an isolated synthetic burn-in fixture.

Target:

`RB4_BURNIN_CAPTURE_CERTIFIED`

### RB5 — REPLAY / NO-FEEDBACK

PASS requires:

- deterministic replay of the governed burn-in dataset;
- Research output writes confined to Research roots;
- active PAPER/PPL/runtime inputs byte-identical across Research/test activity;
- candidate artifacts unable to activate or mutate the same epoch.

Target:

`RB5_BURNIN_REPLAY_NO_FEEDBACK_CERTIFIED`

### RB6 — EXACT-HEAD CI

PASS requires the complete materialized repository workflow surface to pass on
the exact certification SHA.

Final target:

`RL_BURNIN_NO_FEEDBACK_CERTIFIED`

---

## 13. Final authorization boundary

Even after:

`RL_BURNIN_NO_FEEDBACK_CERTIFIED`

burn-in remains NOT STARTED until a separate owner/governance authorization
creates the new experiment epoch.

#242 certification authorizes a capability boundary only.

It does not itself create:

- an epoch;
- runtime deployment;
- systemd changes;
- Watchdog activation;
- candidate promotion;
- TESTNET/LIVE;
- exchange writes;
- real-capital authority.

---

## 14. A1 disposition

Current A1 disposition:

`RL_BURNIN_01 = ACTIVE / RB1 FORENSIC COMPLETE / REMEDIATION REQUIRED`

Current prerequisite status:

- #267 HERM-02 — CLOSED / certified;
- #268 ACC-01 — CLOSED / certified;
- `RB2_PRE_BURNIN_DEBT_CLOSED`;
- RB3 explicit burn-in identity — source candidate implemented, certification pending.

Next work:

1. close RB3 source proof on the exact candidate head;
2. prove RB4 immutable prefix capture/finalization on isolated fixtures;
3. prove RB5 replay/no-feedback and future-epoch-only promotion;
4. run RB6 exact-head CI on the final composed source;
5. only then consider `RL_BURNIN_NO_FEEDBACK_CERTIFIED`.

Burn-in remains NOT AUTHORIZED.

## 13. RB4/RB5 implemented source boundary and certification limits

RB2 debt is closed on main at `b20a815e47e27f6bc55ed64b874f40684ef140f1`.
This branch composes that certified HERM-02/ACC-01 source by a non-destructive
merge. The upstream WEB-RL stack remains the PR base; #271 stays draft/unmerged.

RB4 provides `research_data.burn_in_finalization`:

- validates explicit burn-in role/version, dataset envelope, source boundary,
  copied manifest/config/PPL and optional evidence fingerprints;
- rejects changed code/config identities even when outer IDs are recomputed;
- requires typed quiescence evidence and zero open positions;
- writes one final designation per epoch **within the designated registry**;
- refuses replacement by a later capture and never rewrites prefix datasets;
- rejects output overlap and a symlinked finalization directory.

RB5 adds explicit burn-in component selection to RL-REPLAY and reuses the
existing factual replay/diagnostic/candidate algorithms. F00 component names
and historical output semantics remain supported. F00-specific forensic
conclusions are not presented as evidence about a new burn-in.

The canonical burn-in publication entry point is
`research_data.burn_in_research.BurnInResearchWorkspace`. It requires an explicit
Research output root and protected PAPER/runtime roots. Before publication it
validates the dataset and rejects overlap with the dataset, protected roots,
declared source parents and pre-existing output symlinks. It only reads the
Research copies; original source paths are exclusion metadata, never opened.
Candidates must bind to the same immutable dataset/epoch and frozen code/config
provenance; publishing one grants no execution authority. The existing promotion
validator rejects same-epoch targets and Research-side AUTHORIZED/EXECUTED states.
Missing DecisionPacket evidence fails diagnostics closed before publication.

The integrated synthetic proof covers capture → replay → diagnostic → candidate,
scientific identity stability independent of publication time, changed code/config
identity, future-only promotion validation, finalization and byte-identical PAPER
inputs/captures. HERM-02 and ACC-01 tests run in the same composition matrix.

Limits (SOURCE PROOF, not RUNTIME PROOF):

- quiescence is explicit owner-provided evidence; this offline code does not stop,
  discover or inspect a service, nor prove that a live source will never append;
- finality is governed per explicit registry; using another registry is not an
  implicit revocation or replacement of a designation in the first;
- roots must be operator-controlled, complete and stable while used. This is an
  application/API contract, not an OS sandbox against arbitrary Python code,
  concurrent hostile filesystem changes or a caller bypassing the canonical API;
- future deployment requires separately verified filesystem permissions,
  quiescence evidence and owner authorization. No deployment is performed here.

RB6 expands existing offline PR workflow branch filters to the WEB-RL stack base
so the full source surface can materialize on #271. No test, threshold or gate is
removed or weakened. Exact SHA, run IDs, conclusions and final verdict belong to
#242/#148 governance evidence, after all required checks pass. A local test pass
or the targeted source workflow alone is not final certification.

Rollback: before any separately authorized deployment, reverting the #242 source
commits removes these capabilities; preserve all existing F00/PPL/Research data.
No real epoch or dataset is created by this source-only certification.
