# SEC-API-01 — PUBLIC DATA / PRIVATE KEY SEPARATION

Status: SOURCE REMEDIATION IN PROGRESS  
Reference base: `101359db3993801f2290a0e0fefa3226fb939574`  
Mission branch: `master/sec-api-01-public-private-boundary`

## 1. Scientific question

Can the Crypto AI Terminal observe public market data without private exchange
credentials being present in, or opportunistically consumed by, passive
collector/observer processes?

The target invariant is:

> **PUBLIC_MARKET_DATA must work with zero exchange API credentials. Private
> exchange credentials may exist only inside explicitly private account,
> treasury, reconciliation or execution boundaries.**

This mission does not revoke keys, rotate keys, enable live trading, change
strategy logic, change risk logic or start F-00.

## 2. Boundary classes

### PUBLIC_MARKET_DATA

Examples:

- `trade_analysis.observatory` / LMI public MEXC stream
- `observation/market_observer.py`
- `observation/market_radar.py`
- `observation/horizon_evaluator.py`
- `infra/stream_bus.py`
- `HistoricalDataFetcher` OHLCV downloads
- future Cross-Venue passive collectors

These components MUST NOT require or opportunistically attach exchange private
credentials.

### PASSIVE_SERVICE_IDENTITY

Examples:

- Quant Observer Telegram bot
- Radar Telegram bot
- Paper Trade notifier
- watchdog alert transport
- read-only dashboard authentication

These services may require their own identity secret (Telegram token,
`DASHBOARD_PASSWORD`, etc.), but MUST NOT inherit exchange credentials simply
because the credentials share the same secret store.

### PRIVATE_ACCOUNT_READ

Examples:

- `infra/mexc_reader.py` when reading balances/positions
- `observability/real_accounts.py`
- `src/telegram/exchange_sync.py`
- explicit account-balance observation paths

Private exchange credentials are legitimate here because the operation targets
private account state.

### EXECUTION / TREASURY / RECONCILIATION

Examples:

- `ExchangeFactory` / `ExecutionEngine` private construction paths
- TESTNET/REAL execution paths
- future Treasury / Reconciliation authority

These domains are explicitly private and are not stripped by SEC-API-01.

## 3. Pre-remediation evidence

### Runtime baseline — VPS, 2026-09-14 UTC

Runtime source identity:

- `HEAD = 101359db3993801f2290a0e0fefa3226fb939574`

Already clean in runtime:

- `crypto-lmi-observatory.service`: `.env` only
- `crypto-market-observer.service`: `.env` only
- `crypto-market-radar.service`: `.env` only
- `crypto-market-horizons.service`: `.env` only

Proven runtime leakage:

- `crypto-quant-observer.service` had non-empty `MEXC_API_KEY`,
  `MEXC_API_SECRET`, `BINANCE_API_KEY`, `BINANCE_API_SECRET` in its process
  environment while also carrying its Telegram identity.
- `crypto-radar-bot.service` had the same exchange credentials in its process
  environment while also carrying its Telegram identity.

No values were printed during the audit; only variable names and
`NONEMPTY/ABSENT` states were inspected.

`crypto-feed.service` was not installed on the audited VPS and therefore has no
runtime claim in this mission.

### Source findings

`infra/stream_bus.py` automatically read `{EXCHANGE}_API_KEY` and
`{EXCHANGE}_API_SECRET` from the parent environment and injected them into a
CCXT Pro client whose observed operations are public order books, trades and
tickers.

`HistoricalDataFetcher` similarly attached exchange API credentials to public
OHLCV clients whenever credentials happened to exist.

Source copies of the market observer/radar/horizon systemd units still loaded
`.env.secrets`, despite the audited VPS copies already having removed that
line. This was a dormant regression risk: a future unit-file redeploy could
reintroduce private keys into public collectors.

## 4. Defects

- **SEC-API-DEF-001** — Quant Observer inherits exchange private credentials.
- **SEC-API-DEF-002** — Radar Bot inherits exchange private credentials.
- **SEC-API-DEF-003** — StreamBus opportunistically authenticates public data.
- **SEC-API-DEF-004** — HistoricalDataFetcher opportunistically authenticates
  public OHLCV.
- **SEC-API-DEF-005** — tracked public-data systemd units can regress runtime by
  reloading the global secret store.
- **SEC-API-DEF-006** — other passive secret-bearing services use the global
  secret store without an exchange-credential deny boundary.

The dashboard baseline additionally showed `DASHBOARD_PASSWORD=ABSENT` in the
running process because the runtime unit did not load `.env.secrets`. That is a
separate interface-authentication observation. SEC-API-01 fixes the source
least-privilege shape (dashboard password allowed, exchange credentials
stripped) but does not make a broader dashboard-security certification claim.

## 5. Remediation design

### Code boundary

- StreamBus constructs a public CCXT Pro configuration and strips common CCXT
  private-auth fields even when supplied explicitly.
- HistoricalDataFetcher constructs public CCXT clients and does not read API
  key/secret variables.

### systemd boundary

Public-data units that need no secret at all load `.env` only.

Passive services that legitimately need a service-specific secret may still
load `.env.secrets`, but `UnsetEnvironment=` removes known exchange credential
names before `ExecStart`.

The private `crypto-advisor.service` boundary is intentionally unchanged.

## 6. Source certification gates

SEC-API-01 is source-certifiable only if all are true:

1. `tests/test_sec_api_01_public_private_boundary.py` passes.
2. Existing relevant market/Telegram tests remain green.
3. Public-data units do not load `.env.secrets`.
4. Passive secret-bearing units carry an explicit exchange-secret deny list.
5. `crypto-advisor.service` keeps its private credential access.
6. No strategy, signal, risk, sizing or order logic is changed.

## 7. Runtime certification gates

After merge and controlled deployment:

1. VPS `HEAD == origin/main == merged SEC-API-01 SHA`.
2. Deployed unit files match tracked source for the units changed by this
   mission.
3. LMI / market observer / radar / horizons continue to operate without
   exchange credentials.
4. Quant Observer and Radar Bot retain their required Telegram identity but
   expose no exchange credential names with non-empty values.
5. Paper notifier and watchdog, if running, retain their required notification
   identity but expose no exchange credential values.
6. Dashboard, if restarted from the tracked unit, may receive
   `DASHBOARD_PASSWORD` but must not receive exchange credentials.
7. Private account/execution processes are not accidentally deprived of the
   credentials they are explicitly authorized to use.
8. No new service restart loop, traceback or loss of passive observation is
   introduced.

Runtime inspection MUST report only variable names/states — never values.

## 8. Rollback

Before replacing a deployed unit, copy the current `/etc/systemd/system/<unit>`
to a timestamped operator backup. If a passive service fails after deployment:

1. restore the previous unit file;
2. `systemctl daemon-reload`;
3. restart only the affected passive service;
4. record the failure as SEC-API remediation evidence;
5. do not touch `crypto-advisor.service` or exchange keys as a workaround.

## 9. Verdict vocabulary

Final runtime verdict must be exactly one of:

- `SEC_API_01_RUNTIME_CERTIFIED`
- `SEC_API_01_REMEDIATION_REQUIRED`

Source review/CI alone is never sufficient for the runtime verdict.
