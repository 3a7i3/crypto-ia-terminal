# SEC-API-01 — Runtime baseline — 2026-09-14 UTC

Captured READ-ONLY on VPS `crypto-advisor-2` before SEC-API-01 deployment.
No secret values were printed; only variable names and presence states.

## Proven source identity

`HEAD = 101359db3993801f2290a0e0fefa3226fb939574`  
`BRANCH = main`

## Public collectors already clean in deployed systemd

- `crypto-lmi-observatory.service`: `.env` only.
- `crypto-market-observer.service`: `.env` only.
- `crypto-market-radar.service`: `.env` only.
- `crypto-market-horizons.service`: `.env` only.

## Runtime leakage proven

### crypto-quant-observer.service

Non-empty exchange-private names:
- `MEXC_API_KEY`
- `MEXC_API_SECRET`
- `BINANCE_API_KEY`
- `BINANCE_API_SECRET`

Also non-empty:
- Quant identity;
- Radar identity;
- `DASHBOARD_PASSWORD`.

### crypto-radar-bot.service

The same four exchange-private variables were non-empty.

Also non-empty:
- Radar identity;
- Quant identity;
- `DASHBOARD_PASSWORD`.

### crypto-lmi-observatory.service

All inspected exchange credential names were absent.

### crypto-dashboard.service

All inspected exchange credential names were absent. `DASHBOARD_PASSWORD=ABSENT`.

The dashboard source bypasses authentication when `DASHBOARD_PASSWORD` is empty. Therefore the audited dashboard runtime was fail-open for authentication.

## Source/runtime drift classification

- Market observer/radar/horizons: runtime was safer than tracked `main`; this healthy drift must be versioned.
- Quant/Radar: runtime matched tracked `main` and loaded the global secret store; active violation.
- Dashboard: runtime excluded the global secret store, which prevented exchange-key exposure but also removed its required password.

`crypto-feed.service` was not installed; no runtime claim is made for it.
