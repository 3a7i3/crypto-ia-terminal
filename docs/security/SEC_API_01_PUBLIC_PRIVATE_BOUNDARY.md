# SEC-API-01 — PUBLIC DATA / PRIVATE KEY SEPARATION

Status: SOURCE REMEDIATION IN PROGRESS  
Reference base: `101359db3993801f2290a0e0fefa3226fb939574`  
Mission branch: `master/sec-api-01-public-private-boundary`

## 1. Scope and invariant

SEC-API-01 establishes that public/passive processes receive only the authority required by their domain.

Target invariant:

> PUBLIC_MARKET_DATA receives zero exchange private credentials. Passive service identities receive only their own dedicated secret fragment. PRIVATE_ACCOUNT_READ and explicitly governed execution boundaries retain private credentials where required.

Out of scope: F-00, burn-in, Cross-Venue Observatory implementation, strategy, signal, risk, sizing, order logic, credential rotation/revocation and `crypto-advisor.service` runtime changes.

## 2. Boundary classes

- **PUBLIC_MARKET_DATA** — LMI, market observer, market radar, horizons, StreamBus, public historical OHLCV.
- **PASSIVE_SERVICE_IDENTITY** — Quant Telegram, Radar Telegram, dashboard authentication.
- **PRIVATE_ACCOUNT_READ** — balances, positions, private trades and account observation.
- **EXECUTION / TREASURY / RECONCILIATION** — explicitly private authority.

## 3. SOURCE PROOF

At reference base `101359db3993801f2290a0e0fefa3226fb939574`:

- StreamBus opportunistically read exchange credentials from its environment for public streams.
- HistoricalDataFetcher opportunistically attached exchange credentials to public OHLCV clients.
- tracked market observer/radar/horizon units loaded the global `.env.secrets` store.
- Quant Observer and Radar Bot loaded the global `.env.secrets` store.
- dashboard source loaded `.env.secrets`, while the audited VPS copy had already removed it.

The mission branch makes StreamBus/HistoricalDataFetcher public-only and aligns public market units to `.env` only.

## 4. RUNTIME PROOF — pre-remediation, VPS 2026-09-14 UTC

Runtime provenance:

- branch: `main`
- HEAD: `101359db3993801f2290a0e0fefa3226fb939574`

Direct `/proc/<PID>/environ` inspection reported states only, never secret values.

### Healthy public boundary

`crypto-lmi-observatory.service` received none of the inspected exchange credential names.

Deployed market observer, market radar and market horizons units already loaded `.env` only. This was a healthy runtime drift relative to source and is preserved by SEC-API-01.

### Proven Quant/Radar overexposure

Both `crypto-quant-observer.service` and `crypto-radar-bot.service` received non-empty:

- `MEXC_API_KEY`
- `MEXC_API_SECRET`
- `BINANCE_API_KEY`
- `BINANCE_API_SECRET`

They also received each other's Telegram identity and `DASHBOARD_PASSWORD` because both loaded the shared global `.env.secrets` store.

### Dashboard fail-open observation

The running dashboard loaded only `.env`; `DASHBOARD_PASSWORD` was absent from its process environment even though that variable name exists in `.env.secrets`.

Source code bypasses authentication when `DASHBOARD_PASSWORD` is empty. Therefore the audited runtime shape disables dashboard authentication.

## 5. Defects

- **SEC-API-DEF-001** — Quant inherits private exchange credentials.
- **SEC-API-DEF-002** — Radar inherits private exchange credentials.
- **SEC-API-DEF-003** — StreamBus opportunistically authenticates public data.
- **SEC-API-DEF-004** — HistoricalDataFetcher opportunistically authenticates public OHLCV.
- **SEC-API-DEF-005** — tracked public-data units could reintroduce the global secret store.
- **SEC-API-DEF-006** — Quant/Radar share unrelated service identities through the global secret store.
- **SEC-API-DEF-007** — dashboard runtime does not receive its configured password and source fails open when it is absent.

## 6. Remediation design

### Public collectors

LMI, market observer, market radar and horizons load non-secret `.env` only. StreamBus and HistoricalDataFetcher remain zero-key by construction.

### Dedicated service identity fragments

The shared `.env.secrets` store is removed from all passive identity services in this mission. Each receives a mandatory runtime-only fragment:

- `/etc/crypto-ai/secrets/quant-observer.env`
- `/etc/crypto-ai/secrets/radar-bot.env`
- `/etc/crypto-ai/secrets/dashboard.env`\n- `/etc/crypto-ai/secrets/paper-arena.env`\n- `/etc/crypto-ai/secrets/watchdog.env`

Intended variable allow-list:

- Quant: `QUANT_CRYPTO_BOT_TOKEN`, `QUANT_CRYPTO_CHAT_ID`, `QC_PINNED_MSG_ID`.
- Radar: `RADAR_BOT_TOKEN`, `RADAR_CHAT_ID`.
- Dashboard: `DASHBOARD_PASSWORD`.\n- Paper Arena: `PAPER_ARENA_BOT_TOKEN`, `PAPER_ARENA_CHAT_ID`.\n- Watchdog: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

These files are HUMAN_ONLY runtime artifacts. Their values MUST NOT be stored in GitHub or printed in audit output.

The fragments are mandatory, not optional. Missing provisioning therefore fails at service startup rather than silently falling back to a shared store or an unauthenticated dashboard.

### Private boundary

`crypto-advisor.service` and legitimate private account/execution consumers are intentionally unchanged.

## 7. Source certification gates

1. `tests/test_sec_api_01_public_private_boundary.py` passes.
2. Relevant existing market/Telegram/dashboard tests remain green.
3. Public-data units do not load `.env.secrets`.
4. Quant, Radar and Dashboard do not load `.env.secrets`.
5. Each of those three units references only its dedicated mandatory fragment.
6. Private advisor credential access remains unchanged.
7. No real secret value appears in source/tests/docs.
8. No strategy, signal, risk, sizing or order logic changes.

## 8. Controlled deployment — NOT AUTOMATIC

Before any service restart:

1. merge an approved SEC-API-01 PR;
2. fast-forward VPS deliberately;
3. backup every affected deployed unit;
4. create `/etc/crypto-ai/secrets` as an operator-controlled directory;
5. create each required fragment from existing runtime secret values without printing those values or committing them;
6. restrict fragment permissions appropriately;
7. install only the affected tracked units;
8. run `systemctl daemon-reload`;
9. restart only directly affected passive services;
10. never restart `crypto-advisor.service` for SEC-API-01.

The exact value-transfer operation remains HUMAN_ONLY.

## 9. Rollback

For every changed unit, retain its timestamped pre-deployment copy.

If a passive service fails:

1. restore its previous unit;
2. restore the previous EnvironmentFile wiring;
3. run `systemctl daemon-reload`;
4. restart only that service;
5. record the failure;
6. do not revoke, print or move exchange credentials as an improvised fix.

## 10. Runtime certification gates

After deployment:

- VPS `HEAD == origin/main == merged SEC-API-01 SHA`.
- deployed affected units match source.
- public data functionality remains healthy.
- public/passive processes expose zero exchange private credential names.
- Quant receives its Quant identity and not Radar/Dashboard identity.
- Radar receives its Radar identity and not Quant/Dashboard identity.
- Dashboard receives `DASHBOARD_PASSWORD`, receives no exchange/Telegram credentials, and authenticated behavior is confirmed.
- authorized private account/execution paths retain required credentials.
- no restart loop or new critical traceback appears.

Runtime probes report only `NONEMPTY`, `EMPTY`, or `ABSENT`; never values.

## 11. Verdict vocabulary

Final mission verdict must be exactly one of:

- `SEC_API_01_CERTIFIED`
- `SEC_API_01_REMEDIATION_REQUIRED`

SOURCE PROOF alone can never produce `SEC_API_01_CERTIFIED`.
