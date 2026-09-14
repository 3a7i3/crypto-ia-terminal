# SEC-API-01 — Runtime baseline — 2026-09-14 UTC

Captured READ-ONLY on VPS `crypto-advisor-2` before SEC-API-01 deployment.
No secret values were printed; only variable names and presence states.

## Proven source identity

`git rev-parse HEAD`:

`101359db3993801f2290a0e0fefa3226fb939574`

## Public collectors already clean in deployed systemd

- `crypto-lmi-observatory.service`: `.env` only
- `crypto-market-observer.service`: `.env` only
- `crypto-market-radar.service`: `.env` only
- `crypto-market-horizons.service`: `.env` only

## Runtime leakage proven

### crypto-quant-observer.service

- `MEXC_API_KEY=NONEMPTY`
- `MEXC_API_SECRET=NONEMPTY`
- `BINANCE_API_KEY=NONEMPTY`
- `BINANCE_API_SECRET=NONEMPTY`
- required Telegram identity variables were also non-empty

### crypto-radar-bot.service

- `MEXC_API_KEY=NONEMPTY`
- `MEXC_API_SECRET=NONEMPTY`
- `BINANCE_API_KEY=NONEMPTY`
- `BINANCE_API_SECRET=NONEMPTY`
- required Radar Telegram identity variables were also non-empty

### crypto-lmi-observatory.service

All inspected exchange credential names were absent.

### crypto-dashboard.service

All inspected exchange credential names were absent, but
`DASHBOARD_PASSWORD=ABSENT` in the running process. This is a separate
interface-authentication observation; SEC-API-01 does not claim a dashboard
security certification from this fact.

## Source/runtime drift

Tracked source still loaded `.env.secrets` for market observer/radar/horizons,
while the deployed VPS unit files did not. Therefore a future naive unit-file
redeploy could have reintroduced exchange credentials into public collectors.

Tracked Quant Observer / Radar Bot source and runtime both loaded the global
secret store, matching the proven credential leakage.

`crypto-feed.service` was not installed on the VPS, so no runtime claim is made
for that service.
