# MACHINE-MATURITY-01 — L1 Formal Review v1

Status: `UNDER_FORMAL_REVIEW`  
Parent mission: #365  
Framework: #362  
Roadmap: #285  
L0 certificate PR: #372

## Entry condition

The Phase B entry condition is satisfied:

- `LEVEL_0_CERTIFIED`
- `FORMAL_CERTIFIED_FRONTIER = L0`
- L0 effective main/merge SHA: `747114daa9c7c0bef4992d2dba19f7dd402a423a`
- L0 certification hash: `d17b9b5c6be627aef559f82651d4421506b91aa3208e7284cab6348a38152eb0`

This document starts L1 review only. It does **not** emit `LEVEL_1_CERTIFIED`.

## Frozen identities

- Catalog: `MACHINE-MATURITY-CATALOG-v0.1`
- Catalog Git blob: `2c8392c24bb8be1078f9570111b9364034686af3`
- Evidence Ledger: `MACHINE-MATURITY-EVIDENCE-LEDGER-v0.1`
- Evidence Ledger Git blob: `267680f65f620c329dc0ef989ae7fbce329ef142`
- MM-01 Input Manifest Git blob: `f42ce8783152ee88de8ae3b90af2dd870c75e0df`
- Review branch base: `main@747114daa9c7c0bef4992d2dba19f7dd402a423a`

Evidence addition policy remains:

`FROZEN_AFTER_R0; additions require explicit EvidenceCorpusAmendment with new content identity before verdict`.

## L1 purpose

Prove that the machine can expose its state and decisions in a structured,
provenance-bound, fail-closed and non-authoritative form, with sufficient
runtime proof to distinguish real, stale, absent and degraded state.

## Frozen L1 evidence subset

| EvidenceRecord | Source | Verdict/state | Primary | Disposition |
|---|---|---|---|---|
| MM-EV-L1-001 | #154 / PR #155 | PPL_02B_SOURCE_CERTIFIED | SOURCE_PROOF | ADMISSIBLE |
| MM-EV-L1-002 | #162 | WEB_01_FINAL_CERTIFIED | RUNTIME_PROOF | ADMISSIBLE |
| MM-EV-L1-003 | #164 / PR #166 | WEB_01B_PRIVATE_PWA_RUNTIME_CERTIFIED | RUNTIME_PROOF | ADMISSIBLE |
| MM-EV-L1-004 | #167 | PPL_02D_SHADOW_CERTIFIED | RUNTIME_PROOF | ADMISSIBLE |
| MM-EV-L1-005 | #174 | OPS_C_RUNTIME_RECERTIFIED | RUNTIME_PROOF | SUPPORTING_ONLY |
| MM-EV-L1-006 | #175 | WEB_02_PPL_COMPARATOR_CERTIFIED | RUNTIME_PROOF | ADMISSIBLE |
| MM-EV-L1-007 | #223 | WALLET_PPL_PROVENANCE_OBSERVABILITY_CERTIFIED | RUNTIME_PROOF | ADMISSIBLE |
| MM-EV-L1-008 | #287 | ARCH_CONSOLIDATION_FORENSIC_CERTIFIED | ARCHITECTURE_PROOF | SUPPORTING_ONLY |
| MM-EV-L1-009 | #309 | ARCH_CONSOLIDATION_RUNTIME_UNKNOWN_EVIDENCE_CERTIFIED | RUNTIME_PROOF | SUPPORTING_ONLY |
| MM-EV-L1-010 | #319 | SEC_CRYPTORADAR_02_RUNTIME_CERTIFIED | RUNTIME_PROOF | SUPPORTING_ONLY |

Historical limitations remain part of the evidence:
- MM-EV-L1-002 preserves its historical `UNRESOLVED / SNAPSHOT_MISSING` limitation.
- MM-EV-L1-004 was SHADOW observation evidence and did not itself transfer PAPER authority.
- MM-EV-L1-009 resolves runtime UNKNOWNs but authorizes no cleanup.
- MM-EV-L1-010 is a CryptoRadar runtime precedent, not APP-UNIFY runtime certification.

## Mandatory criterion matrix — review state

### L1-G1 — Structured machine observation & decision provenance

Requirement: `ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`  
Dependencies: L0-G2, L0-G3.  
Frozen mapped evidence: MM-EV-L1-007; source refs accepted by catalog also include DecisionPacket/DecisionIdentity, operator snapshots, #223 and #175 producer artifacts.  
Forbidden state: current state without timestamp/provenance or unattributable origin.  
Review state: `UNDER_REVIEW`.

### L1-G2 — Durable event truth & deterministic replay

Requirement: `ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`  
Dependencies: L0-G1, L0-G4.  
Frozen mapped evidence: MM-EV-L1-001, MM-EV-L1-004.  
Forbidden states include duplicate event identity, divergent replay and silently accepted corruption.  
Review state: `UNDER_REVIEW`.

### L1-G3 — Read-only operator observation surface

Requirement: `ALL_OF(SOURCE_PROOF, RUNTIME_PROOF, UX_PROOF)`  
Dependency: L1-G1.  
Frozen mapped evidence: MM-EV-L1-002, MM-EV-L1-003, MM-EV-L1-006; MM-EV-L1-010 supporting only.  
Forbidden state: implicit mutation from a route/surface presented as observation.  
Review state: `UNDER_REVIEW`.

### L1-G4 — Provenance / freshness / uncertainty visible

Requirement: `ALL_OF(SOURCE_PROOF, RUNTIME_PROOF)`  
Dependencies: L0-G3, L1-G1.  
Frozen mapped evidence: MM-EV-L1-002, MM-EV-L1-004, MM-EV-L1-006, MM-EV-L1-007; MM-EV-L1-008 and MM-EV-L1-009 supporting only.  
Forbidden states include future-skew/unattributed source treated healthy and silent stale state.  
Review state: `UNDER_REVIEW`.

### L1-G5 — Runtime health / recovery observability

Requirement: `RUNTIME_PROOF`  
Dependency: L1-G1.  
Frozen mapped evidence: MM-EV-L1-002, MM-EV-L1-003, MM-EV-L1-004, MM-EV-L1-006, MM-EV-L1-007; MM-EV-L1-005, MM-EV-L1-008, MM-EV-L1-009 and MM-EV-L1-010 supporting only where applicable.  
Forbidden states include assumed-running service without witness and unattributed restart effects.  
Review state: `UNDER_REVIEW`.

### L1-G6 — Observability is non-authoritative

Requirement: `ALL_OF(SOURCE_PROOF, RUNTIME_PROOF, GOVERNANCE_PROOF)`  
Dependencies: L0-G1, L1-G3.  
Frozen mapped evidence: MM-EV-L1-002, MM-EV-L1-003, MM-EV-L1-004, MM-EV-L1-006; MM-EV-L1-010 supporting only.  
Forbidden state: authoritative dependency inverted from Operator/UI into PPL/FIN/Research.  
Review state: `UNDER_REVIEW`.

## Formal review procedure still required

Before any L1 verdict:

1. re-read each frozen EvidenceRecord source and preserve its original proof class and limitations;
2. verify every `all_of` proof requirement without substitution;
3. verify criterion dependencies;
4. distinguish historical runtime proof from current-state claims;
5. run contradiction / supersession / revocation sweep through the current main;
6. reject positive evidence added after R0 unless governed by an explicit EvidenceCorpusAmendment;
7. produce a bounded L1 evidence manifest;
8. record criterion-by-criterion findings and unresolved items;
9. only then decide between:
   - `LEVEL_1_CERTIFIED` candidate; or
   - `LEVEL_1_CERTIFICATION_REMEDIATION_REQUIRED`.

A review PASS still does not become effective certification until a separate immutable
`MachineLevelCertification(L1)` artifact is reviewed and merged under the catalog rules.

## Guardrails

Certification-only / documentation-governance scope.

No Advisor restart/deploy, runtime checkout movement, PAPER/PPL/FIN mutation,
epoch/config mutation, strategy/signal/risk/sizing change, PB_MAX_POSITIONS,
Watchdog, TESTNET/LIVE, exchange write, OperatorDecision operational activation,
agent/bounty/AIC activation, or #282 finalization.
