# FRONTEND-GATEWAY-LAB-03 — signed admission composed with atomic use

Dependency #437 (signature) over #435 (ledger). Source/lab only.

`SignedLabLedger` reuses the LAB-01 ledger and LAB-02 verifier; no second
mechanism. Admission stores only envelopes that verify against the verifier's
pin. Claim re-verifies the stored bytes inside the same `BEGIN IMMEDIATE`
transaction that flips APPROVED to CONSUMED, so a row altered after admission is
refused and a failed check leaves the ticket reusable. The claim also binds the
bundle hash and requires `previous_release_sha` to be in a verifier-supplied
known-release set (bounds rollback to a known release).

| Property | A contract | B lab tests | C system integration | D runtime |
|---|---|---|---|---|
| Single use under concurrency | yes | 2 processes, 1 claim | NOT_VERIFIED | NOT_OBSERVED |
| Signature verified at use time | yes | yes (tamper after admit) | NOT_VERIFIED | NOT_OBSERVED |
| Bundle/hash/service/op binding | yes | yes | NOT_VERIFIED | NOT_OBSERVED |
| Rollback bound to known release | yes | yes (fixture set) | NOT_VERIFIED | NOT_OBSERVED |
| Operator key custody | defined | NOT_PROVEN | NOT_PROVEN | NOT_OBSERVED |
| OS peer identity, trusted clock | defined | fixtures only | NOT_PROVEN | NOT_OBSERVED |
| Interrupted real deployment recovery | open | no executor exists | NOT_VERIFIED | NOT_OBSERVED |

A valid ephemeral-key signature proves possession of that fixture key, not
independent custody. A consumed lab ticket does not show an interrupted
deployment is recoverable. No executor, listener, sudo, unit or VPS change.
#315 NON_DEPLOYED; burn-in intact; U8/L4 NOT_CERTIFIED.
