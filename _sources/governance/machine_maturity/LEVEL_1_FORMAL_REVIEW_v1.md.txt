# MACHINE-MATURITY-01 — L1 Formal Review v1

Status: `FORMAL_REVIEW_COMPLETE / CANDIDATE_ONLY`  
Parent mission: #365  
Framework: #362  
Roadmap: #285  
L0 effective via: #372

## Decision candidate

`LEVEL_1_CERTIFIED`

This is a **formal-review candidate only**. It is not yet an effective
MachineLevelCertification(L1) and does not advance the effective Formal
Certified Frontier beyond L0.

Effective frontier remains:

`FORMAL_CERTIFIED_FRONTIER = L0`

until a separate immutable MachineLevelCertification(L1) artifact is reviewed
and merged under the frozen catalog rules.

## Entry condition

PASS.

- `LEVEL_0_CERTIFIED`
- effective L0 main SHA:
  `747114daa9c7c0bef4992d2dba19f7dd402a423a`
- L0 certification hash:
  `d17b9b5c6be627aef559f82651d4421506b91aa3208e7284cab6348a38152eb0`

## Frozen identities

- Catalog: `MACHINE-MATURITY-CATALOG-v0.1`
- catalog blob: `2c8392c24bb8be1078f9570111b9364034686af3`
- Evidence Ledger: `MACHINE-MATURITY-EVIDENCE-LEDGER-v0.1`
- ledger blob: `267680f65f620c329dc0ef989ae7fbce329ef142`
- MM-01 Input Manifest blob:
  `f42ce8783152ee88de8ae3b90af2dd870c75e0df`
- review base: `main@747114daa9c7c0bef4992d2dba19f7dd402a423a`
- bounded L1 EvidenceRecords: `MM-EV-L1-001…MM-EV-L1-010`

No post-R0 evidence was admitted as new positive criterion evidence. Later
changes were inspected only for contradiction, supersession and revocation.
No EvidenceCorpusAmendment is required for this review.

## Source forensic reviewed

Frozen sources were re-read:

- #154 / PR #155 — PPL-02B durable event truth
- #162 — WEB-01 FINAL
- #164 / PR #166 — WEB-01B private PWA + runtime remediation
- #167 — PPL-02D SHADOW runtime
- #174 — OPS-C runtime recertification
- #175 — WEB-02 PPL comparator
- #223 — truthful PPL scientific-capital provenance
- #287 — architecture surface forensic
- #309 — bounded VPS runtime UNKNOWN evidence
- #319 — secure CryptoRadar runtime precedent

## Criterion decisions

### L1-G1 — Structured machine observation & decision provenance

**Verdict: SATISFIED**

Requirement:
`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`.

Accepted frozen evidence:
- MM-EV-L1-007 / #223
- MM-EV-L1-006 / #175

#223 demonstrates source + runtime provenance for critical scientific capital:
explicit PPL authority, exact epoch, `provenance=PPL_REPLAY`, and
`legacy_fallback=disabled`. #175 demonstrates timestamped producer materialization,
authority/provenance and transport of producer-authored observations.

Dependencies L0-G2/L0-G3 are certified through effective L0.

No current state without provenance/timestamp was found as a canonical
substitute. Narrative logs or screenshots were not used alone.

### L1-G2 — Durable event truth & deterministic replay

**Verdict: SATISFIED**

Requirement:
`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`.

Accepted frozen evidence:
- MM-EV-L1-001 / #154 / PR #155
- MM-EV-L1-004 / #167

#154/#155 establish append-only durability, canonical event identity,
idempotent append, per-epoch sequence ordering, POSIX locking, fsync,
fail-closed corruption handling and deterministic replay. #167 provides real
runtime restart/replay, ON→OFF→ON same-epoch continuity, exact OPEN/CLOSE
capture, no duplicate semantic lifecycle and DEGRADED→ACTIVE recovery.

The historical authority state in #167 is superseded: PPL later became the
governed PAPER authority. That supersession does not invalidate the replay,
identity, durability or recovery proof and is not reused as a current authority
claim.

Current-main source inspection still contains the certified store invariants.
No duplicate-identity or replay-divergence revocation evidence was found.

### L1-G3 — Read-only operator observation surface

**Verdict: SATISFIED**

Requirement:
`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF, UX_PROOF)`.

Accepted frozen evidence:
- MM-EV-L1-002 / #162
- MM-EV-L1-003 / #164/#166
- MM-EV-L1-006 / #175
- MM-EV-L1-010 / #319 as supporting-only precedent

#162 proves the canonical local Operator API/Web read-only runtime and real
browser surface. #164/#166 prove the private PWA path, runtime-data cache
exclusion, fail-closed disconnect semantics and real Chromium remediation.
#175 proves producer→API→frontend comparison fidelity without trading mutation.

Current-main inspection found 15 route decorators in
`observability/operator_api/app.py`, all GET. No POST/PUT/DELETE/PATCH
operator route was found. The PWA service-worker blob remains identical to the
#166 certified version.

No direct frontend trading-store access or observation-side trading action was
accepted as evidence.

### L1-G4 — Provenance / freshness / uncertainty visible

**Verdict: SATISFIED**

Requirement:
`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`.

Accepted frozen evidence:
- MM-EV-L1-002, -004, -006, -007
- MM-EV-L1-008/-009 as supporting evidence

#162 historically proves explicit `SNAPSHOT_MISSING / UNRESOLVED` semantics.
#175 proves raw provenance, PARTIAL/UNRESOLVED states and an observed
STALE→FRESH transition without fabricated convergence. #223 proves exact
authority/epoch/provenance labelling.

The historical SNAPSHOT_MISSING state is not asserted as current availability;
it is retained only as fail-closed evidence.

Later APP-UNIFY source work (#330/#332/#334/#361/#368/#370) continues to make
missing/null/zero/stale distinctions explicit and remains source-only. It was
reviewed only as revocation-negative evidence, not admitted as new frozen L1
positive evidence.

### L1-G5 — Runtime health / recovery observability

**Verdict: SATISFIED**

Requirement:
`RUNTIME_PROOF`.

Accepted frozen runtime evidence:
MM-EV-L1-002…010 as applicable.

The frozen corpus contains repeated runtime witnesses for:
- service/process identity;
- restart/recovery;
- same-epoch replay;
- artifact continuity;
- fail-closed degradation/recovery;
- listener/runtime identity;
- controlled start/stop and quiescence.

Notable witnesses include #162, #164/#166, #167, #174, #175, #223, #309 and
#319.

These are dated runtime proofs. They are treated as durable inherited
certification evidence only because the current-main revocation sweep found no
later change demonstrating loss of the capability. No source-only service
template was substituted for runtime evidence.

### L1-G6 — Observability is non-authoritative

**Verdict: SATISFIED**

Requirement:
`ALL_OF(SOURCE_PROOF, RUNTIME_PROOF, GOVERNANCE_PROOF)`.

Accepted frozen evidence:
- MM-EV-L1-002
- MM-EV-L1-003
- MM-EV-L1-004
- MM-EV-L1-006
- MM-EV-L1-010 supporting-only

#162/#164 keep Web/PWA presentation read-only. #167 demonstrates that SHADOW
failure cannot take over or corrupt the then-authoritative lifecycle. #175
declares comparator authority `OBSERVATIONAL_TELEMETRY` and prohibits
repair/reconstruction from becoming truth.

The later governed PPL authority cutover supersedes the historical authority
labels from #167/#175 but not the invariant that observability remains
downstream/non-authoritative.

Current main still has no operational OperatorDecision path:
#315 Gate O remains `OPEN / NON_RESOLVED`, `operational=True` remains
blocked, and no Operator API mutation route was found.

## Contradiction / supersession review

Two historical states were explicitly superseded without invalidating L1:

1. **PPL SHADOW / authority NONE in #167/#175**  
   Later governed cutover changed PAPER authority. The historical authority
   value is not reused as current truth. Replay/recovery and
   non-authoritative-observation evidence remains valid.

2. **WEB-01 canonical SNAPSHOT_MISSING in #162**  
   This remains historical fail-closed evidence, not a current availability
   assertion.

No historical FAIL/remediation sequence was erased or rewritten.

## Revocation sweep through current main

Reviewed through:

`main@747114daa9c7c0bef4992d2dba19f7dd402a423a`

Post-freeze material changes examined for L1 impact include:
- #315 — OperatorDecision prototype remains source-only/non-operational;
- #330 — source-only read-only RuntimeService projection;
- #332 — source-only observational Scanner;
- #334 — source-only read-only microstructure projection;
- #361 — source-only GET-only Event Center;
- #368 — source-only GET-only storage metadata;
- #370 — source-only GET-only LMI detail;
- #372 — governance-only L0 certificate.

Current-source negative revocation checks:
- Operator API route decorators inspected: GET-only;
- no mutating OperatorDecision activation;
- PWA runtime-data cache exclusion remains;
- durable PPL store retains fsync/locking/idempotence/sequence/corruption guards;
- PPL scientific-capital provenance labels remain;
- no evidence found of observer→PPL/FIN/Research authority inversion.

**Active L1 revocation findings: 0.**

## Independent re-verification (Phase B, exact main 747114da)

This section records a second, independent pass over the frozen sources and
current main. It adds no positive evidence and changes no criterion verdict.

Corrections to the first pass:

1. **#171 / #172 (WEB-OBS-TIME-01) was not examined.** The ledger omits it from
   the frozen L1 subset although the catalog lists it under L1-G4. #171 found,
   after the #162/#164 certifications, that MARKET could show `FRESH` while the
   source provenance timestamp was a timezone-naive UTC string rendered as ~+7h
   in the future. It was remediated and runtime-certified in #172
   (`WEB_OBS_TIME_01_RUNTIME_CERTIFIED`).
   Disposition: `SUPERSEDED` for the MARKET provenance-label defect.
   MM-EV-L1-002/-003 are therefore **not** accepted as evidence that MARKET
   source timestamps were sound; they remain accepted for read-only/loopback
   behaviour. #172 is **not** admitted as positive evidence (post-R0, no
   amendment). L1-G4 does not rest on MARKET: it rests on #175 (STALE→FRESH,
   PARTIAL/UNRESOLVED), #162 (explicit 503 SNAPSHOT_MISSING) and #223. Current
   main source retains `SNAPSHOT_CLOCK_SKEW_FUTURE_TIMESTAMP`
   (`observability/operator_api/reader.py`), UTC normalization
   (`observability/market_radar_snapshot.py`) and naive-timestamp rejection
   (`observability/operator_api/market_reader.py`).
   An optional EvidenceCorpusAmendment adding #171/#172 would strengthen G4; it
   is not required for the verdict.

2. **`paper_trading/durable_event_store.py` changed after #155.** The blob on
   main (`cd457fc3…`) differs from the #155 merge (`a2b54537…`). The change adds
   schema version 2 (`_SUPPORTED_SCHEMA_VERSIONS = {1, 2}`; POSITION_OPENED
   gains `tp_price`, `sl_price`, `timeout_at`, `recovery_eligible_until`, with
   validation). Schema 1 validation is unchanged; fsync, locking, identity,
   idempotence, sequence and corruption guards are untouched by the diff.
   Disposition: `NO_REVOCATION` with `LIMITATION`: the frozen runtime proof
   (#167) exercised schema 1 only; schema 2 runtime replay is not covered by the
   frozen corpus and is not claimed.
   `paper_trading/ppl_authority_runtime.py` (explicit burn-in epoch identity,
   a5e95c2) was also inspected: additive, no store-semantics change.

3. Source re-run on main for the store/replay/provenance suites
   (`test_durable_event_store`, `test_ppl_02e_r2_replay`,
   `test_ppl_recovery_01_replay_certification`,
   `test_obs_wallet_ppl_01_provenance`): 87 passed. This is SOURCE evidence only.

Historical versus current:

- Durable historical capability evidence: MM-EV-L1-001…007 (Sept 15–20) and
  -009/-010 (Sept 28–30), each with its original source/runtime identity.
- Current deployment claims: **none made.** No current runtime witness was
  collected in this review (read-only, no VPS access). `HISTORICAL_RUNTIME_PROOF
  != CURRENT_DEPLOYMENT_PROOF`; a certificate must not be read as stating that
  the present runtime runs these versions.
- Unavailable current claims: schema 2 runtime replay; current Operator API /
  PWA process identity; current canonical snapshot availability.

Other verified points: 15 route decorators in `observability/operator_api/app.py`,
all GET; no file-write primitive in `observability/operator_api/*.py`; `sw.js`
blob identical to the #166 merge (`af92fb95…`); L0 identities and certificate
hash recomputed and matching; main still equals 747114da; #373 untouched
(`STALE_HANDOFF_CANDIDATE`).

## Aggregate result

- mandatory criteria: 6
- SATISFIED: 6
- UNRESOLVED: 0
- NOT_AVAILABLE: 0
- active revocation findings: 0

Formal review decision candidate:

`LEVEL_1_CERTIFIED`

Again: this candidate is not effective until the review itself passes its exact
head controls and is merged, followed by a separate immutable
MachineLevelCertification(L1) artifact and its own governed effectivity gate.

## Guardrails

Certification-only / documentation-governance scope.

No Advisor restart/deploy, runtime checkout movement, PAPER/PPL/FIN mutation,
epoch/config mutation, strategy/signal/risk/sizing change, PB_MAX_POSITIONS,
Watchdog, TESTNET/LIVE, exchange write, OperatorDecision operational
activation, agent/bounty/AIC activation, or #282 finalization.

## Exact frozen-evidence identity audit and completed protocol

Additional source review at `main@747114daa9c7c0bef4992d2dba19f7dd402a423a` from existing candidate
`06a6157f12392b58275640eb6393ebd3eb783466`. The branch already contained the completed review and
manifest; no new mission, remote branch or PR was created.

All ten records were checked against their original issues, full comment
threads, exact source PR metadata and versioned evidence. Publication timestamps
below are GitHub timestamps, not fabricated command/witness times. Missing
command times, source identities and process IDs remain explicit limitations.
No newly collected positive runtime evidence was used.

### MM-EV-L1-001

**Proof classes:** SOURCE_PROOF.
**Original verdict:** `PPL_02B_SOURCE_CERTIFIED`.
**Time:** Source merge 2026-09-14T22:46:52Z; final checkpoint publication 2026-09-16T00:39:14Z.

**Original evidence:** https://github.com/3a7i3/crypto-ia-terminal/issues/154#issuecomment-5690267300; PR #155.

**Exact source identity:** `{"merge_sha": "cb20d6c04f3d471dad24f401cec0b25378236268", "reviewed_head": "ba633aa6288991218b3a66dbc2836fab0a68493e"}`.

**Runtime identity:** `{"reason": "This is source certification, not PPL runtime proof.", "state": "NOT_APPLICABLE"}`.

**Demonstrates:** Durable append, event identity/idempotence, epoch sequence, locking/fsync, detectable corruption, deterministic replay source contract.

**Does not demonstrate:** PAPER authority Runtime deployment or current runtime replay

**Limitations:** 57 store / 160 projector-store / 274 PAPER tests are historical source gates, not runtime witnesses.

**Supersession/current relevance:** NO_REVOCATION: schema 1 store semantics retained; later schema 2 is additive, outside frozen runtime coverage.

### MM-EV-L1-002

**Proof classes:** RUNTIME_PROOF, SOURCE_PROOF, UX_PROOF, GOVERNANCE_PROOF.
**Original verdict:** `WEB_01_FINAL_CERTIFIED`.
**Time:** 2026-09-15; exact time of consolidated commands NOT_AVAILABLE; publication 2026-09-15T22:36:00Z.

**Original evidence:** https://github.com/3a7i3/crypto-ia-terminal/issues/162#issuecomment-5689016236; docs/certification/WEB_01_FINAL_CERTIFICATION.md.

**Exact source identity:** `{"certification_merge_sha": "16e8b17b6275612baa9a57367906cb68b2e1c5bb", "certification_record_sha": "5935d565393207599a5d6e87278ac166e768bce4", "functional_runtime_sha": "aeebdd1744e54ccc95bd93002af0e3944f4a7618"}`.

**Runtime identity:** `{"listeners": ["127.0.0.1:8090", "127.0.0.1:8181"], "market_snapshot_pid": 2218746, "operator_api_pid": 2208782, "operator_web_pid": 2224150, "web_restart_pids": [2217390, 2224150]}`.

**Demonstrates:** Real local read-only browser/API transport; POST 405; service restart/recovery; explicit 503 SNAPSHOT_MISSING.

**Does not demonstrate:** Canonical snapshot availability Sound MARKET source timestamp before #171/#172 Current deployment

**Limitations:** UNRESOLVED / SNAPSHOT_MISSING retained. GENERAL_CI = NON_GREEN / PRE_EXISTING_DEBT retained. No remote/PWA certification at this stage.

**Supersession/current relevance:** LIMITATION: snapshot missing is historical, not silently superseded by availability. SUPERSEDED: #171 MARKET provenance-label defect; not accepted as MARKET source-time soundness evidence. NO_REVOCATION: read-only/missing-state/recovery evidence remains bounded and admissible.

### MM-EV-L1-003

**Proof classes:** RUNTIME_PROOF, SECURITY_PROOF, UX_PROOF.
**Original verdict:** `WEB_01B_PRIVATE_PWA_RUNTIME_CERTIFIED`.
**Time:** 2026-09-16; final attestation published 2026-09-16T00:34:44Z (not an exact command timestamp).

**Original evidence:** https://github.com/3a7i3/crypto-ia-terminal/issues/164#issuecomment-5690150760; https://github.com/3a7i3/crypto-ia-terminal/issues/164#issuecomment-5690228028; https://github.com/3a7i3/crypto-ia-terminal/issues/164#issuecomment-5690233371; PR #166.

**Exact source identity:** `{"deployed_sha": "f86a561eb487954b2b9e770a4238298e0db022cf", "reviewed_remediation_head": "64ac3ac3fc4f6013b05c82beed5020f74a5893d7"}`.

**Runtime identity:** `{"browser": "Real Chromium replacement proof and installed Android PWA", "listeners": ["127.0.0.1:8181", "127.0.0.1:8090"], "pids": "NOT_AVAILABLE in final compact attestation", "services": ["crypto-operator-web.service: active", "crypto-operator-api.service: active"]}`.

**Demonstrates:** Runtime-data cache exclusion (CACHED_RUNTIME_URLS=0); private-link failure/recovery; replacement causes one reload; loopback boundary.

**Does not demonstrate:** Trading authority Current APP-UNIFY deployment MARKET source-time soundness before #171/#172

**Limitations:** Original CONTROLLERCHANGE_WITHOUT_APP_RELOAD failure retained; causally remediated by #166. Canonical snapshot missing remains explicit.

**Supersession/current relevance:** SUPERSEDED: worker defect by #166 and MARKET label defect by #172. NO_REVOCATION: current sw.js/pwa-policy.js match the deployed #166 source.

### MM-EV-L1-004

**Proof classes:** RUNTIME_PROOF, SOURCE_PROOF.
**Original verdict:** `PPL_02D_SHADOW_CERTIFIED`.
**Time:** 2026-09-17 through 2026-09-18; recovery boot 2026-09-18T00:04:14Z; final publication 2026-09-18T00:24:35Z.

**Original evidence:** https://github.com/3a7i3/crypto-ia-terminal/issues/167#issuecomment-5710356607; https://github.com/3a7i3/crypto-ia-terminal/issues/167#issuecomment-5723098301; https://github.com/3a7i3/crypto-ia-terminal/issues/167#issuecomment-5723107540; PR #168.

**Exact source identity:** `{"deployed_sha": "cdedbf41fb1579feedac355cd8d1b2d0ff94ffa2", "merge_sha": "4bdc9eeb33e0a18b4724808efd4475814973b017", "reviewed_head": "57834fac6e3ef2a2dc46decb5f62c626689bceab"}`.

**Runtime identity:** `{"authority": "Legacy PAPER only; PPL SHADOW/NONE", "boot_timestamp_utc": "2026-09-17T06:56:47Z", "durable_sequences": [1, 2, 3], "durable_store_sha256": "a9b2829a67259faeec4531013b2f5cb0d5d9599afb4d2acec08a97eb838e1842", "epoch": "PPL02D-SHADOW-001-20260917T064605Z", "on_off_on_pids": [2360637, 2361599, 2362068, 2362407], "process_instance_id": "6150e997-f16b-4ea3-983b-dae686725161", "recovery_pid": 2432921}`.

**Demonstrates:** Same-epoch runtime restart/replay and ON/OFF/ON; exact OPEN/CLOSE; no duplicate lifecycle; DEGRADED isolation/recovery; unchanged store.

**Does not demonstrate:** PPL authority transfer Schema 2 runtime lifecycle replay Current deployment

**Limitations:** SHADOW proof only; historical runtime schema 1. Legacy PnL rounding boundary is explicit, not silent normalization.

**Supersession/current relevance:** SUPERSEDED: authority-state labels by separately governed #180/#184; SHADOW epoch never promoted. NO_REVOCATION: durable replay/identity/isolation capability remains, with schema/version limits.

### MM-EV-L1-005

**Proof classes:** RUNTIME_PROOF.
**Original verdict:** `OPS_C_RUNTIME_RECERTIFIED`.
**Time:** 2026-09-16; publication 2026-09-16T08:28:32Z; exact command time NOT_AVAILABLE.

**Original evidence:** https://github.com/3a7i3/crypto-ia-terminal/issues/174#issuecomment-5694460643.

**Exact source identity:** `{"context_is_exact_witness_attestation": false, "historical_context_sha": "4bdc9eeb33e0a18b4724808efd4475814973b017", "witness_source_sha": "NOT_AVAILABLE in the compact #174 witness"}`.

**Runtime identity:** `{"config_and_live_fingerprint_sha256": "e13ea29cc0e7db839d7c0f4291ed1468897ab21872f57a34477af7d8d0e33108", "execution_evidence_sha256": "a8933dcbe09fe95d68ef9f95b472594c1d695c6be593249f2b249a17e725ef18", "scan_evidence_sha256": "d7b8b5ed615004841893cc6d3772c5f81372fbddd8f4e8f4c150ebac7ef3f70f", "universe_count": 124}`.

**Demonstrates:** Attributed 135→125→124 population correction; config/live equality and independent domain evidence; fail-closed boot gate.

**Does not demonstrate:** Current universe/config Standalone satisfaction of mandatory L1-G5

**Limitations:** SUPPORTING_ONLY; exact process/source identity not fully repeated in compact witness; never infer it from a nearby source commit.

**Supersession/current relevance:** LIMITATION: retained as context only; no current configuration or primary runtime proof inferred.

### MM-EV-L1-006

**Proof classes:** RUNTIME_PROOF, SOURCE_PROOF, UX_PROOF.
**Original verdict:** `WEB_02_PPL_COMPARATOR_CERTIFIED`.
**Time:** Producer materialization 2026-09-18T05:40:11Z; final publication 2026-09-18T06:29:00Z.

**Original evidence:** https://github.com/3a7i3/crypto-ia-terminal/issues/175#issuecomment-5725712454; https://github.com/3a7i3/crypto-ia-terminal/issues/175#issuecomment-5725730597; https://github.com/3a7i3/crypto-ia-terminal/issues/175#issuecomment-5725777513; https://github.com/3a7i3/crypto-ia-terminal/issues/175#issuecomment-5726113855; PR #176; PR #179.

**Exact source identity:** `{"deployed_sha": "992cf7ca509ef2173d220c93f571cf335a6210a0", "implementation_merge_sha": "28a3dbf5d1ca27d991d904e0d752f21a354f0292", "remediation_head": "982ab1dba01b81af1b2f9fa1b0db543896610a97"}`.

**Runtime identity:** `{"advisor_pids": [13258, 19434], "browser_ci_run": 35310346436, "browser_scope": "Synthetic responsive browser proof on exact deployed SHA, combined with separately observed production-served bundle; not a production browser fault injection.", "comparison_snapshot_sha256": "d49780f9c103e6237636f91319e4763ff94a73c21e93541dc8854bdfa0e40e2d", "durable_store_sha256": "e8dc5032b9a4ed8da723c607c1fa8e0a54e894c251e3059de767dd127054453d", "epoch": "PPL02D-SHADOW-002-20260918T040705Z", "operator_snapshot_sha256": "ed8b3b5e3826ca0c4c38721a5227cf7d79a94294c9dc507b0dd4dd659e375aba", "process_instance_id": "2fb3ae82-c78f-446e-8908-388cc05be9fd", "web_pid": 11940}`.

**Demonstrates:** Structured producer artifacts with source/process/cycle/epoch identity; producer→API→proxy raw payload fidelity; STALE→FRESH and PARTIAL/UNRESOLVED; unchanged financial journals.

**Does not demonstrate:** Current Legacy/PPL authority labels Production OFF/DEGRADED fault injection Perfectly isolated live codepath test Current APP-UNIFY deployment

**Limitations:** OFF/DEGRADED assertions used deployed codepaths; concurrent Scientific Data Guard artifact changes were observed. Domain aggregate decision counters/freshness and boot_alive remain UNKNOWN; per-symbol decision projection is PARTIAL. A responsive fixture alone is not accepted as runtime proof.

**Supersession/current relevance:** SUPERSEDED: authority labels and Legacy-vs-SHADOW comparison mode by #180/#184; current mode explicitly AUTHORITY_STATUS. NO_REVOCATION: current builder blob unchanged from deployed #175; later close-transition guard preserves fail-passive behavior.

### MM-EV-L1-007

**Proof classes:** RUNTIME_PROOF, SOURCE_PROOF.
**Original verdict:** `WALLET_PPL_PROVENANCE_OBSERVABILITY_CERTIFIED`.
**Time:** 2026-09-20; publication 2026-09-20T09:30:53Z; exact command timestamp NOT_AVAILABLE.

**Original evidence:** https://github.com/3a7i3/crypto-ia-terminal/issues/223#issuecomment-5748963658; PR #224.

**Exact source identity:** `{"deployed_sha": "8ff542a7dee2a9c1159ba3f7518ed34633ec1ac1", "reviewed_head": "09960a7fdaaedd722790e30725a49e59042f6012"}`.

**Runtime identity:** `{"epoch": "F00-EPOCH-01-20260920T084335Z", "epoch_sha256": "9e7fb63d85f7e9849f4a53ae8c297613987f46bd05e5b42bc28e1cbcaade17ac", "manifest_sha256": "1d7a3386b2eb2ec7a0f253500ecd2431379c45047698b33f84ae0e08644553af", "post_stop": "Advisor and Watchdog MainPID=0, NRestarts=0, inactive/dead", "start_pid": 225981}`.

**Demonstrates:** Observed PPL scientific-capital authority/epoch/PPL_REPLAY/legacy_fallback=disabled; controlled start/stop and unchanged artifacts.

**Does not demonstrate:** Structured decision observation by log line alone Current deployed epoch or capital Any new admission authority

**Limitations:** Narrative provenance line cannot alone satisfy structured L1-G1; paired with #175 structured artifacts and exact source. PB_MAX_POSITIONS=0 belongs to the historical witness, not current #286 admission value.

**Supersession/current relevance:** NO_REVOCATION: source provenance wording retained; later explicit burn-in epoch differs and is not overwritten.

### MM-EV-L1-008

**Proof classes:** ARCHITECTURE_PROOF, GOVERNANCE_PROOF.
**Original verdict:** `ARCH_CONSOLIDATION_FORENSIC_CERTIFIED`.
**Time:** Source-forensic September 27–28; closure publication 2026-09-28T02:06:38Z.

**Original evidence:** https://github.com/3a7i3/crypto-ia-terminal/issues/287#issuecomment-5862018997; PR #306; docs/forensics/ARCH_CONSOLIDATE_01_FORENSIC.md.

**Exact source identity:** `{"merge_sha": "71bdda7bd786a5e7dc39d8d845b233ed9b0b1640", "reviewed_head": "59b02c17dffc3b7d4fcef2623c666c9c644c8f8f"}`.

**Runtime identity:** `{"reason": "Static forensic, no runtime observation by this record.", "state": "NOT_APPLICABLE"}`.

**Demonstrates:** Inventory, scope, UNKNOWN boundaries, competing observational presentation paths and consumers.

**Does not demonstrate:** Runtime health/recovery Deployed service availability Cleanup authorization

**Limitations:** SUPPORTING_ONLY. Architecture evidence rejected as RUNTIME_PROOF for L1-G5. Source-present dormant components do not become available.

**Supersession/current relevance:** SUPERSEDED: some runtime UNKNOWNs answered by -009; historical inventory not overwritten. LIMITATION: parallel presentation aggregation is not certified PPL/FIN/Research truth.

### MM-EV-L1-009

**Proof classes:** RUNTIME_PROOF, GOVERNANCE_PROOF.
**Original verdict:** `ARCH_CONSOLIDATION_RUNTIME_UNKNOWN_EVIDENCE_CERTIFIED`.
**Time:** 2026-09-28T01:41:18Z

**Original evidence:** https://github.com/3a7i3/crypto-ia-terminal/issues/309#issuecomment-5861857789; https://github.com/3a7i3/crypto-ia-terminal/issues/309#issuecomment-5862015364; PR #311; docs/forensics/ARCH_CONSOLIDATE_01B_RUNTIME_EVIDENCE.md.

**Exact source identity:** `{"checkout_is_current_main_or_loaded_process_sha": false, "evidence_head": "32362fcf1c44ed0f547dd7ac50fa185cb61609db", "evidence_merge_sha": "c932544d5be74f2216ec4898da710b961074a57f", "vps_checkout_sha": "116634be0d3c015cce1cfa58be7da7255414fbfd"}`.

**Runtime identity:** `{"advisor_pid": 882633, "dashboard_pid": 425, "host": "crypto-advisor-2", "market_snapshot_pid": 490629, "operator_api_pid": 502983, "operator_api_source_sha256": "e475c3888b901513124935a4cb5c9286d45bbb17a4a09c41067a4add7ddb2496", "operator_web_pid": 11940}`.

**Demonstrates:** Eight bounded service/process/listener/timer mappings, including canonical Operator API/Web; explicit absent/failed components.

**Does not demonstrate:** Current process identity Cleanup/retirement All services healthy Audit checkout equals every loaded process version

**Limitations:** SUPPORTING_ONLY. Narrator failed; dormant services not running; no implicit zero/healthy. Exact deployed source fingerprints are distinct from Git checkout identity.

**Supersession/current relevance:** SUPERSEDED: dashboard 0.0.0.0:8050 exposure/PID by -010 isolated release; do not reuse as current bind. NO_REVOCATION: bounded Operator mapping evidence remains dated.

### MM-EV-L1-010

**Proof classes:** RUNTIME_PROOF, SECURITY_PROOF.
**Original verdict:** `SEC_CRYPTORADAR_02_RUNTIME_CERTIFIED`.
**Time:** Cutover start 2026-09-30T02:59:15Z; final commands around 18:40–18:43Z, exact command times not captured; later publication 2026-10-01T01:30:41Z.

**Original evidence:** https://github.com/3a7i3/crypto-ia-terminal/issues/319#issuecomment-5917618369; https://github.com/3a7i3/crypto-ia-terminal/issues/319#issuecomment-5918725039; https://github.com/3a7i3/crypto-ia-terminal/issues/319#issuecomment-5922896261.

**Exact source identity:** `{"advisor_checkout_sha": "116634be0d3c015cce1cfa58be7da7255414fbfd", "isolated_release_sha": "0c0c6212e104a4b1742ebc79d8e9d99ef7cfea7b"}`.

**Runtime identity:** `{"advisor_pid": 882633, "advisor_start_utc": "2026-09-27T03:03:57Z", "dashboard_pid_at_cutover": 1168303, "dashboard_pid_later_attestation": 1236604, "listener": "127.0.0.1:8050", "release_path": "/opt/cryptoradar-dashboard/releases/0c0c6212e104", "tailnet_route": "8443→8050; existing 443→8181 preserved"}`.

**Demonstrates:** Isolated authenticated loopback CryptoRadar runtime, nonempty DP/LMI, bounded restart with unchanged Advisor.

**Does not demonstrate:** APP-UNIFY runtime certification Scientific burn-in completion GCP ingress proof Independent off-tailnet test Current process identity

**Limitations:** SUPPORTING_ONLY; operator-provided historical output, not a VPS connection in this review. Consumed #286 exception grants no new mutation. Later PID differs; do not collapse distinct historical witnesses.

**Supersession/current relevance:** SUPERSEDED: old CryptoRadar public bind in -009; secure isolated predecessor replaces that fact only. NO_REVOCATION: observer remains separate from trading authority.

### Mandatory criterion protocol completion

Each criterion is mandatory. Final vocabulary is exactly SATISFIED,
UNRESOLVED or NOT_AVAILABLE; all six bounded capability verdicts remain
SATISFIED. The machine-readable manifest mirrors the requirements, accepted
records, rejected uses, dependencies, forbidden-state checks, revocation and
limitations below.

#### L1-G1 — final SATISFIED

**Requirement:** `ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`.

**Accepted frozen evidence:** MM-EV-L1-007, MM-EV-L1-006.

**Accepted basis:** #223 proves runtime scientific-capital provenance with explicit authority, epoch and provenance=PPL_REPLAY while source tests prove the same authority-specific semantics. #175 provides producer-authored runtime observation with explicit authority/provenance and timestamped materialization through the read-only transport chain.

**Rejected evidence/uses:** MM-EV-L1-007 log wording alone: not a structured decision record. MM-EV-L1-008 static inventory alone: no runtime witness.

**Rejected substitutions:** narrative log text alone screenshot alone source-only implementation as runtime proof

**Forbidden states checked:** No source-less substitute accepted: #175 binds source SHA/process/cycle/epoch and raw producer artifacts. Decision aggregate remains PARTIAL/UNKNOWN; no fabricated complete decision pipeline.

**Limitations:** Retrospective structured-observation capability, not proof every current decision has a non-null identity. The #175 exact-source builder exposes packet_id/context_id/created_cycle_id/created_at and source-declared UNKNOWN for unavailable values; materialized operator snapshot bound by SHA-256.

**Dependencies checked:** L0-G2: SATISFIED: effective L0 certificate; L0-G3: SATISFIED: effective L0 certificate.

**Revocation result:** `NO_REVOCATION / NONE_FOUND` within the bounded inherited capability; no current-deployment assertion.

#### L1-G2 — final SATISFIED

**Requirement:** `ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`.

**Accepted frozen evidence:** MM-EV-L1-001, MM-EV-L1-004.

**Accepted basis:** #154/#155 certify durable append, event identity/idempotence, sequence ordering, fsync/locking, fail-closed corruption handling and deterministic replay. #167 proves real runtime ON/OFF/ON same-epoch continuity, deterministic projection/replay, exact OPEN/CLOSE capture, failure isolation and recovery without duplicate lifecycle effects.

**Rejected evidence/uses:** MM-EV-L1-001 source certification alone cannot supply runtime proof. Later #180/#184/#196/#203 not admitted as new positive L1 evidence.

**Rejected substitutions:** legacy JSONL coherence alone mutable snapshot process memory source replay without runtime witness

**Forbidden states checked:** Current store rejects identity collisions, physical duplicate IDs, malformed/partial records, epoch mismatch and sequence gaps/regressions. Schema 1 durable source and SHADOW replay retained; current projector adds schema 2 with strict same-epoch version checks.

**Limitations:** Frozen runtime proof exercised schema 1; schema 2 authoritative OPEN/CLOSE and present deployment not certified by this review. #195/#196 adverse CLOSE replay risk was real; superseded in current source by #203 prospective project-before-append. No runtime recertification of #203 inferred.

**Dependencies checked:** L0-G1: SATISFIED: effective L0 certificate; L0-G4: SATISFIED: effective L0 certificate.

**Revocation result:** `NO_REVOCATION / NONE_FOUND` within the bounded inherited capability; no current-deployment assertion.

#### L1-G3 — final SATISFIED

**Requirement:** `ALL_OF(SOURCE_PROOF, RUNTIME_PROOF, UX_PROOF)`.

**Accepted frozen evidence:** MM-EV-L1-002, MM-EV-L1-003, MM-EV-L1-006, MM-EV-L1-010.

**Accepted basis:** #162 certifies local Operator Web/API runtime, loopback listeners, real browser navigation and mutation rejection. #164/#166 certify private PWA runtime, network-fail-closed behavior, no runtime API caching, real Chromium update behavior and continued loopback-only API/Web listeners. #175 certifies read-only comparator producer→API→frontend fidelity. #319 is supporting secure-runtime precedent; it is not substituted for Operator App runtime certification.

**Rejected evidence/uses:** MM-EV-L1-010 supporting CryptoRadar precedent cannot replace canonical Operator runtime/UX evidence. Synthetic screenshot or CI visual proof alone is not a production runtime witness.

**Rejected substitutions:** frontend source-only mutating API presented as observation direct React reads of trading stores CryptoRadar runtime as substitute for Operator App runtime

**Forbidden states checked:** 15 current canonical Operator route decorators, all GET; no observation trading write path found. Native frontend proxy excludes mutating API methods; current clients request GET and consume producer values.

**Limitations:** #162 canonical snapshot remained UNRESOLVED / SNAPSHOT_MISSING. #175 responsive CI is an exact-source synthetic browser adjunct to independent production-service/payload observations, not a production browser fault-injection test. No APP-UNIFY deployment claim.

**Dependencies checked:** L1-G1: SATISFIED: this bounded L1 criterion matrix.

**Revocation result:** `NO_REVOCATION / NONE_FOUND` within the bounded inherited capability; no current-deployment assertion.

#### L1-G4 — final SATISFIED

**Requirement:** `ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`.

**Accepted frozen evidence:** MM-EV-L1-002, MM-EV-L1-004, MM-EV-L1-006, MM-EV-L1-007, MM-EV-L1-008, MM-EV-L1-009.

**Accepted basis:** #162 preserves SNAPSHOT_MISSING/UNRESOLVED rather than fabricating healthy replacement values. #175 proves raw provenance, explicit PARTIAL/UNRESOLVED states and live STALE→FRESH classification without fake convergence. #223 proves authority/epoch/provenance labelling for scientific capital. #287/#309 provide supporting runtime/source topology evidence and preserve UNKNOWN boundaries.

**Rejected evidence/uses:** MM-EV-L1-002/-003 cannot prove pre-remediation MARKET source timestamps sound (#171). #172 corrected runtime result not admitted as positive evidence without amendment. MM-EV-L1-008 architecture alone cannot prove runtime freshness.

**Rejected substitutions:** UI-invented freshness UNKNOWN hidden as zero/healthy stale rendered as live future-skew/unattributed data treated healthy

**Forbidden states checked:** #175 live STALE cycle 1 (~174s) then FRESH cycle 2 with distinct process/cycle/epoch attribution; PARTIAL=3 and UNRESOLVED=1 retained. Current canonical readers reject future generation time, keep missing manifest identity UNKNOWN/LAST_KNOWN, and do not infer health from freshness. Current MARKET UTC normalization/naive rejection inspected only for active contradiction; no old #171 defect remains in source.

**Limitations:** Historical missing snapshot preserved; no current snapshot availability inferred. Source-domain aggregate timestamps/freshness and boot_alive remain UNKNOWN when no producer exists. No new positive #171/#172 record used; G4 rests on independently frozen #175/#223 and missing-state #162 evidence.

**Dependencies checked:** L0-G3: SATISFIED: effective L0 certificate; L1-G1: SATISFIED: this bounded L1 criterion matrix.

**Revocation result:** `NO_REVOCATION / NONE_FOUND` within the bounded inherited capability; no current-deployment assertion.

#### L1-G5 — final SATISFIED

**Requirement:** `RUNTIME_PROOF`.

**Accepted frozen evidence:** MM-EV-L1-002, MM-EV-L1-003, MM-EV-L1-004, MM-EV-L1-006, MM-EV-L1-007, MM-EV-L1-009, MM-EV-L1-010.

**Context only:** MM-EV-L1-005, MM-EV-L1-008; neither is mandatory runtime proof.

**Accepted basis:** #162/#164 establish service/listener/browser runtime and controlled recovery evidence. #167 establishes runtime identity, same-epoch restart/replay, DEGRADED→ACTIVE recovery and artifact continuity. #174 provides bounded runtime recertification with exact live/config fingerprints and fail-closed universe evidence. #175 records governed Advisor restart/process identity and unchanged critical PAPER/PPL artifacts. #223 proves controlled start/stop, process quiescence and artifact invariance. #309/#319 provide supporting process/service/listener identity evidence.

**Rejected evidence/uses:** MM-EV-L1-008 has ARCHITECTURE_PROOF/GOVERNANCE_PROOF only; rejected as RUNTIME_PROOF. MM-EV-L1-005 incomplete compact source/process identity: supporting context only, not mandatory proof. Source-only RuntimeService projection, systemd templates and existing source tests cannot replace runtime witnesses.

**Rejected substitutions:** systemd template without observation source tests alone assumed-running service without witness

**Forbidden states checked:** #162 actual service/PID/listener restart; #167 process UUID/source/boot/epoch plus unchanged replay stream; #175 governed restart/materialization; #223 controlled quiescence. No service running claim derived from source existence, snapshot freshness or boot_alive UNKNOWN.

**Limitations:** No current VPS witness collected; current service/process health remains NOT_AVAILABLE to this review. #309 includes failed narrator and not-running components; no all-services-healthy certification. #174 remains supporting-only with identity gap explicitly retained.

**Dependencies checked:** L1-G1: SATISFIED: this bounded L1 criterion matrix.

**Revocation result:** `NO_REVOCATION / NONE_FOUND` within the bounded inherited capability; no current-deployment assertion.

#### L1-G6 — final SATISFIED

**Requirement:** `ALL_OF(SOURCE_PROOF, RUNTIME_PROOF, GOVERNANCE_PROOF)`.

**Accepted frozen evidence:** MM-EV-L1-002, MM-EV-L1-003, MM-EV-L1-004, MM-EV-L1-006, MM-EV-L1-010.

**Accepted basis:** #162/#164 certify observation-only Web/PWA paths without trading authority. #167 demonstrates SHADOW failure isolation and explicitly non-authoritative observation. #175 comparator authority is OBSERVATIONAL_TELEMETRY and cannot repair or mutate PAPER/PPL truth. #319 is supporting secure observation precedent and does not create new authority.

**Rejected evidence/uses:** MM-EV-L1-010 cannot certify APP-UNIFY runtime or give trading authority. Standalone CryptoRadar/Telegram presentation aggregation is not authoritative PPL/FIN/Research truth. Current source implementation or merged status alone cannot create operational OperatorDecision authority.

**Rejected substitutions:** React/UI accounting as truth observer writer mutating PPL/FIN observation result becoming execution authority supporting CryptoRadar proof replacing canonical Operator evidence

**Forbidden states checked:** Current API is GET-only; transports producer artifacts; no UI/API ledger mutation path found. Current comparison AUTHORITY_STATUS identifies PPL authority and Legacy compatibility; observation mode does not perform authority selection. #315 Gate O remains OPEN/NON_RESOLVED; operational=True remains blocked; Agent/Forest contract certification grants no worker authority.

**Limitations:** Certification concerns non-authoritative observation, not every historical bot/control surface. Historical Legacy/PPL SHADOW authority labels superseded; original failure-isolation facts remain bounded. No runtime trading/Research/FIN/PAPER/TESTNET/LIVE authority is granted.

**Dependencies checked:** L0-G1: SATISFIED: effective L0 certificate; L1-G3: SATISFIED: this bounded L1 criterion matrix.

**Revocation result:** `NO_REVOCATION / NONE_FOUND` within the bounded inherited capability; no current-deployment assertion.

### Additional negative revocation findings

- **SUPERSEDED — #195, #196, #203:** Real P0 authoritative CLOSE could persist before semantic replay rejected it. e8e37202429d2542327d74edeecbe0cd9d65bcea; prospective project before append, durable projection checked after reload; current source retains this. Limitation: Not a defect demonstrated in frozen SHADOW schema 1. No #203 runtime deployment or new schema 2 positive proof admitted.
- **SUPERSEDED — #197/#205, #198/#206, #268/#273:** Epoch/population/metadata baseline, notification provenance and missing-PnL measurement defects retained in historical issues. Current epoch-aware population, provenance-aware notification and UNRESOLVED/None/BREAKEVEN semantics inspected; no current canonical inversion accepted. Limitation: Source remediation is not current runtime certification; no new positive L1 records admitted.
- **NO_REVOCATION — 7270728f1b3314dab8436f313b8182d69edad360, #190/#194:** Legacy quiescence extension renamed transition observation; guard extended to explicit lifecycle_transitions_in_flight > 0. Current coherent capture still withholds artifacts mid-CLOSE, refuses fake comparison, keeps unavailable observations distinct. Limitation: Original #175 runtime proof does not cover every later authority/quiescence schema.
- **SUPERSEDED — MM-EV-L1-009, MM-EV-L1-010:** CryptoRadar 0.0.0.0:8050/PID425 in Sept 28 pack replaced by isolated loopback release in Sept 30/Oct 1 witnesses. Source default loopback/security boundary retained; latest historical PID1236604 distinguished from cutover PID1168303. Limitation: No present PID/bind claim; no GCP ingress/off-tailnet test fabricated; consumed exception not renewed.
- **LIMITATION — #287, #309, #315:** Dormant components, failed narrator, presentation duplication and non-operational OperatorDecision prototype remain bounded facts, not fabricated healthy/available. Canonical Operator observation retains GET-only and no authority inversion found. Limitation: No cleanup, all-services health, runtime Registry/Forest or OperatorDecision activation certified.
- **UNRESOLVED — Current deployment at review time:** No current VPS collection; historical source/process evidence cannot establish present deployment. Excluded from certification scope; not a mandatory durable-capability criterion failure. Limitation: Current process identity, canonical snapshot availability and schema 2 runtime lifecycle remain unclaimed.

These later refs are contradiction/supersession checks only. In particular,
#172 and #203 are not admitted as new positive runtime proof. No
EvidenceCorpusAmendment is required or used. If a future claim needs either
new runtime record, stop for an explicit governed amendment before admission.

Current-source comparison also confirms that the operator snapshot builder
blob is unchanged from deployed #175 (`7a6b3ceefcd3bbb8ca2a22302e368983ed16ff87`);
current store/projector blobs are respectively
`cd457fc33ba020f55eed3d09ada3c4c8102dbcd8` and
`20f421fef9885f9c412d57f3b8eff9bddb4b539c`. Version 2 adds lifecycle terms
and rejects mixed versions; it does not remove schema 1 or weaken identity,
sequence, fsync/locking/corruption guards. These are negative source checks,
not a present-runtime proof.

No active contradiction or revocation found in the reviewed source/history.
Current deployment remains outside this review. L0 remains effective; the
formal frontier stays L0. The six-criterion decision remains the review
candidate `LEVEL_1_CERTIFIED`; exact final-head CI and governed review merge
are required, followed by a separate L1 certificate mission.
