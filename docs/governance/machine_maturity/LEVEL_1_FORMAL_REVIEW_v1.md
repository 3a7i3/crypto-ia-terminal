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
