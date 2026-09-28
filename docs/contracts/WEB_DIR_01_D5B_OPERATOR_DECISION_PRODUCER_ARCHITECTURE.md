# WEB-DIR-01 / D5B — Governed OperatorDecision producer architecture

Mission: #310 · Parent: #288 · Roadmap: #285 · D5A: #307  
Forensic: #287 and #309 · Agent Economy: #284 · Burn-in guard: #286  
Evidence baseline: `main@c932544d5be74f2216ec4898da710b961074a57f` (PR #311 merged)  
Status: **architecture proposal for review; no producer, endpoint or projection deployed**

## 1. Decision and scope

Adopt a **separate governance workflow boundary**: upstream registries own their
source facts; a future canonical OperatorDecision Registry owns decision identity,
append-only decision events and the materialized read projection. A normalization
adapter may submit candidates, but cannot create human decisions or infer them
from raw telemetry. This is a proposed ownership contract, not a claim that the
registry, adapters, event store or API exist.

The canonical chain is:

`certified source fact → governed candidate → admission/identity gate → append-only OperatorDecision events → deterministic read projection → future D5C read-only UI`

A human action, if ever implemented in a separate authorized phase, only
advances the governance workflow toward a separate future gate. It cannot
merge, deploy, restart or alter active PAPER. #286 remains superior.

D5A's `OperatorDecision` fields, statuses, priority enum, authority rules and
availability distinctions are inherited, not replaced. In particular,
`GET /api/operator/v1/decision-pipeline` is trading telemetry; the cold-start
`decision_queue` invariant is an internal safety mechanism; #287/#309 are
evidence, not a decision producer. None is an admissible queue substitute.

## 2. Source ownership matrix

"Owner" means the future authoritative registry/workflow for that source fact,
**not** the OperatorDecision Registry. A row marked "proposed" is not deployed.
Every admission needs a versioned source snapshot and an explicit owner-approved
handoff; merely finding an issue, PR, log or artifact does not admit it.

| Source class | Source-of-truth / owner | Candidate admission boundary | Forbidden shortcut |
|---|---|---|---|
| Problem | #284 future Problem Registry (proposed) | `VERIFIED_PROBLEM` with evidence and explicit human-decision request; `CANDIDATE_PROBLEM` remains upstream | Forensic finding or agent detection → queue |
| Proposed Evolution | Future governed Proposed Evolution Registry (proposed) | Reviewed proposal version with rationale, risk, validation and rollback | Free-form LLM suggestion or GitHub issue → queue |
| Bounty result | #284 future Bounty Registry (proposed), linked to verified Problem | `VALIDATED` result with independent review, evidence and explicit `HUMAN_DECISION` handoff | `CLAIMED`, `SUBMITTED` or AIC reward → human acceptance |
| Research | Governed Research candidate registry (proposed) | Reproducible, independently reviewed candidate and future-epoch request | Diagnostic, leaderboard or profit estimate → active epoch |
| Security/debt | Governed security/remediation workflow (proposed) | Validated finding with redacted evidence, risk and authorized owner | Vulnerability scan, raw log or secret-bearing artifact → queue |
| Incident follow-up | Governed incident register (proposed) | Reviewed follow-up and bounded remediation request | Alert or runtime UNKNOWN → automatic action |
| Architecture migration | Reviewed architecture change register (proposed) | Versioned ADR/change request with dependency and rollback evidence | #287 inventory classification → retirement |
| Runtime/config/cost request | Separately governed change/cost workflow (proposed) | Explicit scoped request and future gate, never a runtime command | Queue action → systemd, PPL, FIN, exchange or billing mutation |

No listed registry is declared deployed by this document. GitHub issue/PR
references can be **evidence pointers**, never ownership or authority on their
own. Source conflicts, unknown owner, unverifiable revision, stale evidence,
missing permission to expose evidence or ambiguous lineage fail closed. One
source fact may have multiple proposals, but duplicate admission of the same
source revision and decision purpose must be idempotent; supersession is
explicit, never silent.

## 3. OperatorDecisionCandidate contract (proposed)

A candidate is a *request for admission*, not an `OperatorDecision` and not an
operator action. The upstream owner signs off its factual contents; the future
admission gate validates them and assigns a distinct immutable `decision_id`.
No client, agent or upstream registry may assign authoritative status or human
acceptance.

```text
OperatorDecisionCandidate {
  schema_version, candidate_id, candidate_revision,
  source: {
    source_type, source_id, source_ref, source_sha,
    source_generated_at_utc, producer, producer_authority,
    owner_registry, owner_record_version
  },
  decision_type, title, summary, proposed_change,
  requested_initial_status, requested_priority,
  risk, validation, rollback,
  evidence: {
    evidence_status, evidence_refs[], source_hashes[],
    tests, ci, review, limitations[]
  },
  requested_by, requested_at_utc, decision_purpose,
  upstream_approval_ref, correlation_ref
}
```

Required: globally scoped `candidate_id`, version, stable source identity
and exact revision/hash where available, accountable owner registry, purpose,
summary, risk, evidence status and inspectable evidence references. Redacted or
unavailable evidence is stated explicitly; an empty list is not proof of
absence. `requested_initial_status` and `requested_priority` are requests,
not authority. Allowed priority vocabulary is D5A's
`CRITICAL/HIGH/MEDIUM/LOW/UNKNOWN`; never derive it from PnL, colour,
GitHub labels, AIC, agent opinion or UI. The admission gate records its
approved values and reasons, or rejects the candidate with a traceable reason.

Candidate identity and admission idempotency key:
`(owner_registry, source_type, source_id, owner_record_version, decision_purpose)`.
A changed source version is not an in-place edit to an admitted decision;
it requires a new reviewed amendment event or explicit superseding candidate.
No direct reads of raw JSONL/DB, Telegram, exchange, runtime process state or
free-form LLM output are allowed for candidate normalization.

## 4. Canonical registry and event contract (proposed)

The future OperatorDecision Registry alone assigns globally unique,
non-reusable `decision_id`, sequential `version` and canonical status.
Its append-only log is authoritative for workflow facts; a read projection is
derived and may be rebuilt. It must preserve D5A's minimum
`OperatorDecision` schema and source/evidence provenance. Corrections append
compensating/amendment events; prior events are never edited or erased.

```text
OperatorDecisionEvent {
  schema_version, event_id, decision_id, decision_version,
  event_type, actor_type, actor_ref, occurred_at_utc,
  previous_status, new_status, expected_version,
  candidate_id, source_revision_ref, reason,
  evidence_refs[], idempotency_key,
  previous_event_hash, event_hash
}
```

`event_id` and `idempotency_key` are unique within their defined scopes.
Hash-chain canonicalization, signing, storage and key management are deferred
to an implementation/security review; hashes do not themselves authenticate a
human. `previous_event_hash` anchors an ordered chain (with an explicit
genesis marker), and gap/hash/version failures invalidate projection
certification. Event timestamps are UTC; registry sequence/version, not wall
clock alone, defines order.

Proposed event categories:

- `CANDIDATE_ADMITTED`, `EVIDENCE_AMENDED`, `PRIORITY_REVIEWED`,
  `BLOCKED`, `UNBLOCKED`, `SUPERSEDED`, `CLOSED`: governance-service
  events with accountable actor and authorization, never presented as human
  acceptance.
- `HUMAN_ACKNOWLEDGED`, `HUMAN_REMEDIATION_REQUESTED`,
  `HUMAN_REFUSED`, `HUMAN_PLANNED`,
  `HUMAN_ACCEPTED_FOR_FUTURE_GATE`: require
  `actor_type=HUMAN_OPERATOR`, authenticated/authorized `actor_ref`,
  expected version, explicit intent, reason and evidence visibility. No agent
  impersonation. Their write interface is **outside D5B and D5C**.

The D5A status enum remains
`TO_VALIDATE`, `TO_READ`, `BLOCKED`, `TO_PLAN`,
`REMEDIATION_REQUESTED`, `ACCEPTED_FOR_FUTURE_GATE`, `REFUSED`,
`SUPERSEDED`, `CLOSED`. A transition table, action authorization,
authn/authz, CSRF/session and anti-replay design require a separate D5D
review. Until that gate, these event categories are **contracts only**.
Reject stale `expected_version`, invalid transitions, duplicate IDs with
different payloads, missing actor proof and last-write-wins updates. An exact
idempotent retry returns the original result without a new event.

## 5. Governed read projection and D5C boundary

A future projection builder consumes only the certified registry event stream,
checks ordered versions/hash links and joins immutable, authorized source
references. It never discovers decisions from a trading pipeline, dashboard,
GitHub search, #287 inventory or UI heuristics. The Operator API may later
expose this projection read-only; D5C renders it and never recomputes status,
priority, counts, availability or authority.

Proposed response envelope (not an implemented endpoint):

```text
{
  schema_version, product="OPERATOR_DECISION_QUEUE",
  domain="GOVERNANCE", authority="GOVERNANCE_WORKFLOW_PRESENTATION",
  generated_at_utc, as_of_event_version, source_watermark,
  freshness, availability, decision_count, counts_by_status,
  items: OperatorDecision[], limitations[], projection_hash
}
```

The reserved authority label becomes valid only after a real producer and
projection are certified; it is not active now. Counts are exact, mutually
consistent with the full unfiltered item set and version/watermark, including
terminal statuses under the declared counting scope. Filtered/paginated
responses must specify scope and totals and must not masquerade as global
counts. Ordering is producer-authored and stable (explicit sort key plus
`decision_id` tie-break), not a React governance score. A snapshot must
carry its provenance, freshness, limitations and projection version.
Consumers reject incompatible schemas, missing fields, stale or partial
watermarks and integrity failure; the UI shows unavailability rather than
a synthetic zero. Sensitive evidence references require separate access
control; no secret content is embedded in the projection.

Availability is a discriminated state, never inferred from an empty array:

| State | Required proof | Presentation |
|---|---|---|
| `NON DÉPLOYÉ` | No certified governed producer/projection | No count or items asserted; current #310 state |
| Explicit zero | Certified producer healthy, complete watermark and scope, exact `decision_count=0`, empty items, zero counts, freshness within contract | Real empty queue with provenance |
| `NOT_AVAILABLE` | Producer exists, requested optional field unavailable with reason | Field-level unavailable; no fabricated default |
| `UNKNOWN` | Producer/projection exists but cannot establish completeness, integrity or state | No trusted count; fail closed |
| `BLOCKED` | Concrete decision event/status with unmet prerequisite | Item status, not global availability |

A missing endpoint, timeout, error, absent file or empty array is **not** an
explicit zero. The current Direction card remains `File de décisions —
NON DÉPLOYÉ` until a separate deployment proof; source architecture
certification does not change it.

## 6. Examples and negative tests (contract-only)

1. A #284 `CANDIDATE_PROBLEM` detected from forensic evidence stays in the
   Problem Registry workflow. It emits no decision and no bounty.
2. A reviewed `VERIFIED_PROBLEM` explicitly requesting human planning may
   submit a versioned candidate. Admission creates a new `decision_id` and
   `TO_PLAN` only if the source owner, revision, evidence and policy pass.
3. A bounty at `SUBMITTED` cannot become a decision. A later independently
   `VALIDATED` result may request `HUMAN_DECISION`; a human
   `ACCEPT_FOR_FUTURE_GATE` only advances to another gate, not merge or
   payment.
4. A Research candidate referencing an immutable dataset cannot promote to
   the active burn-in epoch. Rejected evidence or a stale source version
   blocks admission or appends a reviewed amendment.
5. Duplicate identical admission is idempotent; a duplicate key with changed
   payload, stale event version, missing human identity or broken hash link
   fails closed and does not alter the projection.
6. A healthy, complete certified producer with no decisions may report zero.
   Today no producer exists, so zero is false and `NON DÉPLOYÉ` is required.

## 7. Review gates and non-impact

Before any architecture verdict: review this ownership matrix against #284,
D5A and forensic #287/#309; verify all four contracts and negative examples;
verify the Git diff contains only documentation; record exact base/head,
checks and limitations. Certification is **source architecture only** and
does not certify deployment, runtime truth, security of a future write API,
or implementation correctness.

Before any executable producer: separate explicit authorization, schema and
owner sign-off, storage/integrity/security design, transition table, data
protection, test vectors and fail-closed validation. Before D5C: certified
producer and read projection with availability/freshness proof. Before D5D:
authenticated human write contract, authorization, concurrency, idempotency
and auditable events. Before deployment: separate #286-compatible runtime
gate and proof.

No endpoint, producer, writer, worker, UI action, systemd/cron/timer change,
deployment, restart, active PAPER/epoch/config/risk/sizing/PB_MAX_POSITIONS,
PPL/FIN, Research promotion, Watchdog, TESTNET/LIVE or exchange write is
authorized here. No cleanup of #287/#309 components is authorized.

**Target, pending review and evidence:**  
`WEB_DIR_01_D5B_PRODUCER_ARCHITECTURE_CERTIFIED`
