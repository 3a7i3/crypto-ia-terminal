# FRONTEND-GATEWAY-LAB-02 — signature fixtures

Mission #436; dependency #434/#435. Offline source only.

Ed25519 verification uses a verifier-supplied pinned public key. The envelope
cannot supply a replacement public key. Domain-separated, sorted compact ASCII
JSON binds all ticket fields. The existing validator checks exact fields, expiry,
service and request binding; fixture revocation and peer mismatch are refused.
No signing command, stored key, real operator approval, listener or executor.

Tests generate ephemeral keys in memory. Passing signature verification proves
only possession of the matching fixture private key. It does not identify Mathieu
or establish independent key custody. The caller also supplies clock, pin,
revocation and peer fixture. Real peer credentials, trusted time, rollback-proof
revocation, issuer/store separation and source/CI authority remain NOT_PROVEN.
The synthetic ledger is unchanged and is not wired to this verifier as authority.

Before runtime admission: operator separately controls issuer key; requester
cannot read it or change the verifier pin; actual OS peer credentials bind actor;
key rotation/revocation and artifact custody are reviewed; connector explicitly
admits the named capability. No privilege installer is provided by this mission.
Power-loss/fsync and external action recovery remain unqualified.

Dedicated CI runs candidate, ledger process-exit/concurrency and signature tests
on dependent ops PR branches, with read-only token, no service/market secrets or
VPS connection. CI success remains source proof only. #315 NON_DEPLOYED;
burn-in intact, collection and stress PAPER DENIED, L4/U8 NOT_CERTIFIED.
