# WEB-DIR-01 / D5A — Operator Decision Queue Governance Contract

**Mission:** #307  
**Parent:** #288  
**Active roadmap:** #285  
**Burn-in guard:** #286  
**Agent Economy architecture:** #284  
**Forensic consolidation:** #287  
**D4 baseline:** `WEB_DIR_01_D4_FINAL_SOURCE_CERTIFIED`  
**Source baseline:** `3fe983ded551b3d42347a4e5fff56af33acc0837`  
**Date:** 2026-09-27 UTC  
**Status:** CONTRACT DEFINED — NO PRODUCER — NO RUNTIME AUTHORITY

## 1. Purpose

Define the future **Operator Decision Queue** before any producer, mutation API,
or interactive owner workflow is implemented.

Mandatory future chain:

`evidence/source -> governed decision candidate -> OperatorDecision -> human action -> governed workflow state -> separate future gate`

Never:

`queue click -> active PAPER/runtime mutation`

The queue is not the trading decision pipeline, a strategy/execution queue,
the cold-start pending-decision invariant, an agent task queue, or a raw
GitHub PR/Issue mirror.

## 2. Current source finding

No governed Operator Decision Queue producer exists at this baseline.

Explicit non-equivalents:

- `GET /api/operator/v1/decision-pipeline` = trading decision-pipeline
  observation, not human governance;
- cold-start `decision_queue` = startup safety invariant, not owner governance;
- #287 forensic findings = evidence/inventory, not runtime decision truth.

Until a governed producer exists:

`Operator Decision Queue = NON DÉPLOYÉ`

No fake rows, synthetic counts, inferred priorities, fabricated reviewers, or
pretend mutation actions may appear.

## 3. Authority model

Future workflow projection may present item existence, status, provenance,
evidence, and prior human actions.

Recommended future presentation authority label:

`GOVERNANCE_WORKFLOW_PRESENTATION`

This label is reserved only; it is not active today.

Decision authority is:

`HUMAN_OPERATOR`

Human acceptance still cannot bypass CI, review, branch protection, runtime
gates, epoch gates, deployment gates, security controls, or TESTNET/LIVE
authorization.

## 4. OperatorDecision minimum schema

```text
OperatorDecision
- decision_id
- schema_version
- decision_type
- title
- summary
- status
- priority
- created_at_utc
- updated_at_utc
- source
- authority
- evidence
- proposed_change
- risk
- validation
- rollback
- human_decision
- version
```

Missing governed values remain unavailable; React never synthesizes them.

## 5. Identity and provenance

`decision_id` is globally unique and immutable.

Minimum source block:

```text
source
- source_type
- source_id
- source_ref
- source_sha
- source_generated_at_utc
- producer
- producer_authority
```

Future candidate sources may include certified registries for:

- Proposed Evolutions;
- Problems;
- Bounties;
- Research Candidates;
- Security/Debt;
- Incidents;
- Architecture migrations;
- Runtime-change requests.

These producers do not all exist today.

The queue MUST NOT silently infer canonical decisions from raw GitHub,
Telegram, logs, JSONL, databases, exchange state, #287 inventory, or free-form
LLM output.

## 6. Decision types

Reserved future types:

- `PROPOSED_EVOLUTION`
- `BOUNTY_RESULT`
- `RESEARCH_CANDIDATE`
- `SECURITY_FINDING`
- `ARCHITECTURE_CHANGE`
- `INCIDENT_FOLLOWUP`
- `RUNTIME_CHANGE_REQUEST`
- `COST_GOVERNANCE`
- `OTHER_GOVERNED`

Reservation is not proof that any producer is deployed.

## 7. Canonical queue statuses

- `TO_VALIDATE`
- `TO_READ`
- `BLOCKED`
- `TO_PLAN`
- `REMEDIATION_REQUESTED`
- `ACCEPTED_FOR_FUTURE_GATE`
- `REFUSED`
- `SUPERSEDED`
- `CLOSED`

French UI labels may map to:
À VALIDER, À LIRE, BLOQUÉ, À PLANIFIER, REMÉDIATION DEMANDÉE,
ACCEPTÉ POUR GATE FUTURE, REFUSÉ, REMPLACÉ, CLOS.

Machine status remains canonical.

## 8. Priority

Producer-authored only:

- `CRITICAL`
- `HIGH`
- `MEDIUM`
- `LOW`
- `UNKNOWN`

React MUST NOT derive priority from colour, PnL, comments, agent opinion, or
GitHub labels without a future explicit contract.

## 9. Evidence requirements

Any item requiring accept/refuse needs inspectable evidence.

Minimum block:

```text
evidence
- evidence_status
- evidence_refs[]
- source_hashes[]
- tests
- ci
- review
- limitations[]
```

For code/change proposals, where applicable:
branch, PR, candidate/source SHA, diff, artifacts, rollback, risk, expected
benefit, measured benefit when available, and governed cost when available.

Missing evidence remains missing.

## 10. Human actions

Reserved workflow actions:

- `ACKNOWLEDGE`
- `OPEN_EVIDENCE`
- `OPEN_DIFF`
- `OPEN_PREVIEW`
- `REQUEST_REMEDIATION`
- `REFUSE`
- `PLAN`
- `ACCEPT_FOR_FUTURE_GATE`

Inspection actions may be read-only.

## 11. Absolute side-effect boundary

These are NOT queue actions:

- `MERGE`
- `DEPLOY`
- `RESTART_ADVISOR`
- `CHANGE_SYSTEMD`
- `CHANGE_EPOCH`
- `CHANGE_CONFIG`
- `CHANGE_PB_MAX_POSITIONS`
- `CHANGE_STRATEGY`
- `CHANGE_RISK`
- `CHANGE_SIZING`
- `WRITE_PPL`
- `PROMOTE_RESEARCH_TO_ACTIVE_EPOCH`
- `ENABLE_WATCHDOG`
- `ENABLE_TESTNET`
- `ENABLE_LIVE`
- `WRITE_EXCHANGE`

`ACCEPT_FOR_FUTURE_GATE` means only that an item may proceed to a separately
governed next gate. It never means “apply now”.

## 12. Active burn-in rule

For active epoch:

`BURN-IN-EPOCH-01-20260926T064144Z`

Allowed:

`active PAPER facts -> evidence -> candidate -> OperatorDecision -> future gate`

Forbidden:

`OperatorDecision -> active PAPER mutation`

#286 remains superior.

## 13. Relationship to Agent Economy

#284 defines:

`CANDIDATE_PROBLEM -> VERIFIED_PROBLEM -> BOUNTY_OPEN -> CLAIMED -> WORKING -> SUBMITTED -> REVIEW -> VALIDATED -> HUMAN_DECISION -> ACCEPTED/REJECTED`

The queue may eventually present the `HUMAN_DECISION` boundary.

It MUST NOT collapse earlier lifecycle stages into an operator decision.

Agents may propose, provide evidence, and review. They may never create their
own human acceptance, merge, deploy, or buy authority through AIC/reputation.

## 14. Human-decision audit event

A future state-changing action must create an auditable event:

```text
OperatorDecisionEvent
- event_id
- decision_id
- event_type
- actor_type = HUMAN_OPERATOR
- actor_ref
- occurred_at_utc
- previous_status
- new_status
- expected_version
- reason
- evidence_refs[]
- event_hash
```

Exact cryptographic implementation is deferred, but prior actions must remain
inspectable.

## 15. Concurrency and idempotency

Future writes MUST provide:

- versioned decision state;
- expected-version or equivalent optimistic concurrency;
- unique action/event identity;
- idempotent duplicate handling or explicit rejection;
- stale-action fail-closed behavior;
- no silent last-write-wins overwrite.

## 16. Future API separation

D5A creates no endpoint.

Candidate future read endpoint:

`GET /api/operator/v1/operator-decisions`

Future response must be versioned and include product/domain/authority,
generated_at, freshness, availability, exact status counts, ordered items,
provenance, and limitations.

A future human action API requires a separate mission/security contract.
Candidate shape only:

`POST /api/operator/v1/operator-decisions/{decision_id}/actions`

D5A does NOT authorize it.

Future write contract must cover authenticated human identity, authorization,
CSRF/session controls as applicable, expected version, idempotency key, audit
event, valid state transition, and explicit no-runtime-side-effect guarantees.

## 17. Availability semantics

### `NON DÉPLOYÉ`
No governed queue producer exists. This is the current state.

### Explicit zero
Only a certified producer emitting queue availability and decision_count=0 may
create a real empty queue.

### `NOT_AVAILABLE`
Producer exists; optional requested field unavailable.

### `UNKNOWN`
Producer cannot establish state.

### `BLOCKED`
A concrete governed decision exists but lacks a prerequisite.

These states are never interchangeable.

## 18. Ordering and filters

Canonical ordering belongs to the future producer, not React.

Future ordering may use producer-authored priority, required_by_utc,
created_at_utc, or sequence. Until defined, UI preserves producer order.

Filters are presentation-only and may use exact status/type/source.

No client-side governance score is authorized.

## 19. Level-one Direction presentation

Until D5B exists, current card remains:

`File de décisions — NON DÉPLOYÉ`

After a certified producer exists, Level 1 may show exact producer-authored
availability/counts, highest priority, oldest pending timestamp, freshness,
and action-required count.

Detailed evidence must be accessible before any state-changing human action.

## 20. Mobile and accessibility

Future interactive D5 must preserve:

- touch-safe targets;
- no required horizontal table;
- status text not colour-only;
- keyboard navigation;
- explicit confirmation for state-changing actions;
- evidence accessible before accept/refuse;
- no hidden default action;
- no destructive visually dominant default.

## 21. Security prerequisites for future D5B/D5D

Before write actions exist:

- authenticated operator identity;
- authorization boundary;
- anti-replay/idempotency;
- auditability;
- input validation;
- no arbitrary URL/path execution;
- no command/shell passthrough;
- no secret exposure;
- no GitHub/deployment/exchange credential exposure to browser actions.

## 22. D5 implementation gates

### D5A — Contract
Current mission.

Target:
`WEB_DIR_01_D5A_DECISION_QUEUE_CONTRACT_SOURCE_CERTIFIED`

### D5B — Governed producer
Blocked today. Separate source mission.

### D5C — Read-only Direction queue
Only after D5B source certification.

### D5D — Human workflow actions
Only after producer + authn/authz + auditable events + concurrency/idempotency
contracts + separate human authorization.

### D5E — Runtime/deployment proof
Separate mission. No source verdict implies deployment.

## 23. D5A non-impact proof

D5A is documentation-only.

It MUST NOT modify frontend executable source, Operator API, backend producers,
Advisor, systemd, PPL, FIN, Research, Market, active epoch, config, risk,
sizing, `PB_MAX_POSITIONS`, Watchdog, TESTNET, LIVE, or exchange access.

## 24. Acceptance criteria

D5A may be source-certified only when:

1. search confirms no existing governed owner queue producer;
2. trading decision-pipeline, cold-start queue, and forensic findings are
   rejected as substitutes;
3. lifecycle and authority boundaries are explicit;
4. accept is separated from merge/deploy/runtime mutation;
5. active burn-in mutation is prohibited;
6. `NON DÉPLOYÉ` is distinguished from explicit zero;
7. read/write API responsibilities are separated;
8. diff is documentation-only;
9. exact base/head/tree are recorded;
10. exact-head CI is reported;
11. #307, #288, and #285 are synchronized;
12. post-merge tree equality is verified.

## 25. Current verdict

`WEB_DIR_01_D5A_DECISION_QUEUE_CONTRACT_DEFINED`

No producer exists.  
No queue is deployed.  
No runtime authority is created.
