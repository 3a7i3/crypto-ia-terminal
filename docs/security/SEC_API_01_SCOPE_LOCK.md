# SEC-API-01 — Scope lock

IN SCOPE:
- public market-data collectors
- passive-service exchange credential exposure
- source/runtime unit-file drift that can reintroduce exchange credentials
- tests and read-only certification tooling

OUT OF SCOPE:
- key rotation/revocation
- changing real credential values
- live-trading enablement
- F-00 / burn-in
- strategy/signal/risk/sizing changes
- Treasury implementation
- Cross-Venue strategy implementation
- unrelated dashboard feature work
