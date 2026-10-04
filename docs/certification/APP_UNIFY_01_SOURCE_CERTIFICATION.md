# APP-UNIFY-01 U7 — Global Source Certification

Date: 2026-10-04
Repository: `3a7i3/crypto-ia-terminal`
Mission: #382
Parent: #323
Roadmap: #285
Guard: #286

## Verdict

`APP_UNIFY_01_SOURCE_CERTIFIED`

This verdict certifies only the source product boundary of the unified Operator App.
It does not certify a current VPS deployment, runtime publication, current data
availability, or retirement of a legacy transport.

## 1. Certified source identity

Functional source baseline reviewed:

`main@2926954ea789bc8279604513aab7364fcf298c28`

Last functional APP-UNIFY tranche before this global review:

- #370 / PR #371 — APP-LMI-DETAIL-01
- merge: `26dddfb01cdad68378bf98c83c1c242ceb8db31a`
- tested head: `d9ebae23e1cbc3683197372af491ee7ce01e292a`

Comparison `26dddfb… → 2926954…` contains only documentation,
Machine-Maturity certification artifacts and Agent-Economy contract documents.
No frontend, Operator API, observability producer/reader or application runtime
file changed after #371.

## 2. Included lineage

| Domain | Mission / PR | Source disposition |
|---|---|---|
| U0 data/parity contract | #324 / #325 | integrated |
| U1 owner view | #326 / #327 | integrated |
| U2 burn-in projection | #328 / #329 | APP_UNIFY_U2_BURN_IN_STATUS_SOURCE_READY |
| U2b runtime-service projection source | #330 / #331 | APP_UNIFY_U2B_RUNTIME_SERVICE_SOURCE_READY |
| U3a Scanner | #332 / #333 | APP_UNIFY_U3A_SCANNER_SOURCE_READY |
| U3b LMI | #334 / #335 | APP_UNIFY_U3B_MICROSTRUCTURE_SOURCE_READY |
| U4 Research publication reader | #336 / #337 | APP_UNIFY_U4_RESEARCH_PUBLICATION_SOURCE_READY |
| U6 Machine/Laboratoire | #338 / #339 | integrated source |
| Events | #361 / #364 | APP_EVENTS_01_SOURCE_READY |
| Storage | #368 / #369 | APP_STORAGE_01_SOURCE_READY |
| LMI detail/liquidity | #370 / #371 | APP_LMI_DETAIL_01_SOURCE_READY |
| Frontend dependency remediation | #346 | SEC_WEB_DEPS_01_REMEDIATED |

## 3. Global source gates

### U7-G1 — Authority chain — PASS

Canonical presentation follows:

`governed producer → bounded projection → strict reader → GET-only Operator API → frontend`.

The frontend does not gain PAPER, PPL, FIN, Research, exchange or deployment authority.

### U7-G2 — Epistemic fail-closed semantics — PASS

UNKNOWN, UNRESOLVED, NOT_AVAILABLE, NON_DEPLOYED, stale, missing and degraded
remain distinct from explicit zero, empty and healthy states.

### U7-G3 — No frontend scientific/financial recomputation — PASS

PnL, finance, lifecycle state, Research verdicts, rankings, criterion outcomes
and authority remain producer-published facts. React presents them; it is not a
competing scientific or financial authority.

### U7-G4 — Machine / Research domain separation — PASS

Machine and Laboratoire are visually integrated but remain separate truth
domains. Research publications and strategy assessments require explicit
admission and provenance. Missing real publications remain unavailable.

### U7-G5 — Market / CryptoRadar source parity boundary — PASS WITH EXPLICIT EXCLUSIONS

Integrated source capabilities include Scanner, search/filtering, safe symbol
detail, LMI status/table/detail, aggressive flow, bid/ask liquidity, resistance,
state components, Events and bounded storage metadata.

Intentional exclusions remain explicit:
- historical /api/signals Entry/SL/TP/R data is not promoted into Market authority;
- /api/lmi/events current notable states are not fabricated into a temporal history;
- unrestricted raw/private fields are not exposed;
- liquidity source values do not prove a book observation before the first real update.

### U7-G6 — Read-only transport — PASS

Operator API consumption is GET/read-only for the certified boundary. Frontend
code does not read PPL JSONL, databases, exchange APIs or VPS files directly to
bypass governed readers.

### U7-G7 — UX / mobile / provenance — PASS FOR SOURCE/UX SCOPE

Accumulated visual-proof workflows cover desktop/mobile presentation,
provenance/details, unavailable/error/degraded states and overflow across the
major Machine/Lab surfaces. Exact values remain inspectable.

### U7-G8 — Source security / dependency boundary — PASS

Frontend dependency remediation #346 is integrated. This certification adds no
credential path, exchange writer, runtime deployment path or mutation endpoint.

## 4. Exact-tree validation

DOC-CANON-02 head:

`1b25e8d3983ae3cdd88c1f4ce2812e00004595fa`

Its merge is `main@2926954…` and head→merge has zero file differences.

At that exact head the protected checks were successful:
- integrity
- LINT REGRESSION GATE
- TEST REGRESSION GATE
- CROSS-STACK COMPATIBILITY GATE

Successful source/visual workflows also included U2, U2b, U3a, U3b, U4,
Machine Lab U6, WEB-01 Market, WEB-02 PPL Comparator, WEB-RL Research,
WEB-DIR Direction, FIN-02 Financial Cockpit and panel screenshots.

Coverage/Codecov/Coveralls/panel workflows still running at the documentation
merge gate are not relabelled as completed evidence.

The U7 certification PR must itself pass the protected checks at its exact head.

## 5. Explicit non-claims

APP_UNIFY_01_SOURCE_CERTIFIED does not mean:
- APP_UNIFY_01_RUNTIME_CERTIFIED;
- the current VPS serves this source;
- current runtime artifacts are present or fresh;
- a specific real Research result has been admitted or published;
- CryptoRadar standalone can be retired;
- legacy transports have no consumers;
- OperatorDecision is operational;
- Gate O #315 is closed;
- burn-in #282 is finalized;
- #286 can be lifted;
- TESTNET or LIVE is authorized.

The 2026-10-04 #282 checkpoint attempt is NOT_OBSERVED; historical runtime
evidence is not promoted to current truth.

## 6. Runtime and retirement boundary

U8 remains separate and requires actual release-plane runtime, UX and security
proof. CryptoRadar retirement remains a separate decision after runtime parity,
consumer verification and rollback evidence.

## 7. Machine-Maturity consequence

After review and merge, this artifact may satisfy the SOURCE_PROOF required by
Machine-Maturity L4-G2. It does not satisfy L4-G3, L4-G5, L4-G7 or L4-G8.

## Final decision

All global mandatory U7 source gates are satisfied with explicit limitations and
no proof-class substitution.

`APP_UNIFY_01_SOURCE_CERTIFIED`

Runtime remains separate. #286 remains active.
