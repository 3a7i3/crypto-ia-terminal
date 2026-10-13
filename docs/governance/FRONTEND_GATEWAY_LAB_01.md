# FRONTEND-GATEWAY-LAB-01 — synthetic single-use ledger

Mission #434 ; dependency #432/#433. G1 isolated prototype only, no broker.

[Ledger](../../observability/frontend_gateway_lab.py) creates its own fresh private
laboratory directory and fixed SQLite filename. Existing directories cannot be
adopted by create. Reopening checks the lab scope and current-user private dir.
No production/root ticket store is accessed. The same user owns the fixtures and
database: this is not a requester-independent trust root or authenticity proof.

Admission explicitly uses `admit_synthetic`, not an operator grant. Approval and
receipt are bound by the pure candidate verifier. Bundle bytes are hashed before
consumption. Up to 128 tickets, 8192-byte JSON documents, four-MB bundle and five-
second SQLite busy timeout. SQL values are parameterized. Revocation refuses an
already consumed or unknown ticket; consumption refuses revoked/unknown/replayed.

`BEGIN IMMEDIATE` serializes claims; one transaction changes APPROVED→CONSUMED
and inserts one receipt. WAL/FULL are SQLite settings, not independently observed
fsync or power-loss certification. State is CONSUMED_NO_EXECUTION: there is no
callback, command, privilege, network listener or service action in the module.
No exact-once external execution is inferred from unique ticket consumption.

[Tests](../../tests/test_frontend_gateway_lab.py) actually run two spawned local
processes against an owned temporary DB, with bounded waits and cleanup of those
children only. One claim succeeds and the other is refused. Receipt is read after
reopening. Negative cases cover unknown/revoked/expired/substituted bundle and
directory adoption. No crash/power-loss/tracer-drop or peer identity is injected.
The lab clock is caller-supplied; real trusted time remains unqualified.

Hostile directory replacement/ancestor custody, authentic approvals, atomic
ledger under privileged service/crash recovery, anti-rollback, connector policy
admission and deployment executor remain unimplemented/unqualified. No current
VPS, permission, sudoers, Desktop Commander config or operational queue changes.
#315 remains NON_DEPLOYED; #286 ACTIVE. Collection/stress PAPER DENIED.

Next: qualify issuer/store separation, actual peer identity and crash/idempotency
contract in an admitted isolated environment. Any privileged capability still
requires supported connector policy admission and operator installation; this
prototype cannot be used to relay a blocked command.
