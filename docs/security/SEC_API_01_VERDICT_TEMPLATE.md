# SEC-API-01 — Verdict template

Source verdict and runtime verdict are separate.

## Source

- base SHA:
- branch/head SHA:
- tests:
- CI:
- diff scope:
- source verdict: `MERGEABLE` or `REMEDIATION_REQUIRED`

## Runtime

- deployed SHA:
- unit identity:
- passive process exchange-private state:
- required service-identity state:
- service health/restarts:
- public market observation health:
- private boundary regression check:

Final runtime verdict must be exactly one of:

`SEC_API_01_RUNTIME_CERTIFIED`

or

`SEC_API_01_REMEDIATION_REQUIRED`
