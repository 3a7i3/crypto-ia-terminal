# FRONTEND-DEPLOY-GATEWAY-01 — capability contract for review

Mission #432 ; parents #430/#428/#285 ; #286 remains ACTIVE.
Operator explicitly requested a gateway for frontend deployments they authorize.

## Delivery and current limits

This source revision supplies a pure candidate request validator and negative
tests. No service, listener, privileged executor, command wrapper, sudoers entry,
Desktop Commander config or permission is installed or changed. Execution remains
NOT_IMPLEMENTED / DENIED. A structurally valid ticket is not authentic authority.

Desktop Commander currently blocks privileged commands and runs as chatgpt-ro.
We will not rename/encapsulate a blocked command to bypass that policy. Before
activation, a supported connector capability and its permissions must explicitly
admit this operation. If that admission is unavailable, the operator keeps the
manual activation path #430/#431; no hidden relay is enabled as a workaround.

## Target workflow

1. Agent prepares a frontend package, exact source/merge references and hashes.
2. Operator sees the concrete release, diff, validation, previous version and
   rollback. They explicitly approve this package and operation, not all future
   deploys. Permission remains scoped to this frontend.
3. An owner-controlled admission boundary issues a short-lived single-use ticket
   for the admitted caller and service. The requester cannot mint or edit it.
4. A future admitted service receives the named request; no shell text, arbitrary
   path, unit or command is accepted. It independently verifies the source gate,
   bundle bytes, ticket authenticity, expiry and actual peer identity.
5. Service atomically consumes the authorization and journals progress before
   activation. Only web can change; guard/Advisor/API/current remain protected.
6. Verify served bytes and protected baseline, then return an explicit receipt.
   A failed install may rollback that same approved release according to policy.

## Capability boundary

| Capability | Target | Authority |
|---|---|---|
| status | Named gateway receipt / web status | Read-only, no secret data |
| activate_frontend | crypto-operator-web.service | One specifically approved package |
| rollback_frontend | Same approved target and pinned previous release | Separate explicit policy/ticket |

Forbidden: Advisor/API restart, runtime checkout advancement, epoch/config,
PPL/FIN/risk/sizing, secrets, exchange, arbitrary filesystem or shell, service
retirement, account management, connector restrictions bypass, autonomous
approval or activation. No general administrative entitlement to the agent.

The process gaining privilege is separately administered by the operator;
Desktop Commander and chatgpt-ro retain their limited identity. Installation is
manual, reviewed and reversible. Do not install it through the current agent.

## Ticket bindings and source checks

Candidate v1 fields: ticket_id (32 lower hex), actor chatgpt-ro, audience
frontend-deploy-gateway, operation, fixed web service, source_sha and
source_merge_sha (40 hex), bundle_sha256 (64 hex), previous_release_sha (40 hex),
operator mathieu, explicit approved=true, issued_at/expires_at integer seconds.
Maximum validity one hour; expiry is exclusive. No additional fields or commands.
Request fields must match every binding exactly. Future identity owners may
change only via a versioned policy review, not requester data.

[Validator](../../observability/frontend_deploy_request.py) checks supplied
documents only. It does not verify GitHub, signatures, filesystem ownership,
peer credentials or a trusted clock. The supplied consumed set is a fixture/
adapter boundary, not an implemented atomic ledger. Its success returns
CANDIDATE_VALID_REQUIRES_TRUSTED_ADMISSION and privileged_execution=false.
Never expose this candidate result as a deploy permission.

## Decisions required before implementation of privilege

- Named policy owner and root of ticket authenticity, independent of requester.
- Supported connector route and explicit capability admission; no policy bypass.
- Local peer identification, nonce/expiry clock, revocation and actor binding.
- Root-controlled artifact custody, anti-substitution and path safety.
- Atomic consumption, crash/retry/idempotency semantics and durable receipts.
- Previous release and override custody; constrained rollback and recovery.
- Limits on package size, service load, concurrency and journal quota.
- Gates #430 and freeze exception scope, reviewed source, tests and runtime proof.

#315 OperatorDecision remains NON_DEPLOYED. This contract does not resolve its
Gate O or reuse its prototype as authority. If the gateway relies on that queue,
Gate O must be resolved first. An independent manual-ticket capability requires
its own explicit admission and trust review; it is not implicitly exempted.

## Exit gates

G0 contract/owner review → G1 isolated broker prototype → G2 fault/security and
atomic-use qualification → G3 connector/policy admission → G4 operator install
→ G5 exact approved package activation and runtime evidence. This revision
addresses part of G0 and candidate validation only. G1–G5 are NOT_IMPLEMENTED /
NOT_ADMITTED / NOT_OBSERVED. No promise of automatic future deploys.

Burn-in intact ; D1-D/E NOT_PROVEN ; collection/stress PAPER DENIED.
