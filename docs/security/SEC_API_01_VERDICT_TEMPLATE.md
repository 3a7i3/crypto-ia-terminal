# SEC-API-01 — Verdict template

SOURCE PROOF and RUNTIME PROOF remain separate.

## Source

- base SHA:
- branch/head SHA:
- tests:
- CI:
- diff scope:
- public-data boundary:
- service-identity boundary:
- private-boundary regression check:
- source assessment: `MERGEABLE` or `REMEDIATION_REQUIRED`

## Runtime

- deployed SHA:
- deployed unit identity:
- public/passive exchange-private state:
- Quant-only identity state:
- Radar-only identity state:
- Dashboard-only password state:
- dashboard authentication behavior:
- service health/restarts:
- public market observation health:
- private boundary regression check:

Final mission verdict must be exactly one of:

`SEC_API_01_CERTIFIED`

or

`SEC_API_01_REMEDIATION_REQUIRED`

A source-only review can never produce `SEC_API_01_CERTIFIED`.
