# SEC-API-01 — Source remediation changelog

Base: `101359db3993801f2290a0e0fefa3226fb939574`

## Changed

- `infra/stream_bus.py`: public CCXT Pro configuration; exchange auth fields are
  stripped even if explicitly supplied.
- `quant_hedge_ai/agents/market/historical_fetcher.py`: public OHLCV client;
  exchange key/secret environment variables are no longer consulted.
- `crypto-market-observer.service`, `crypto-market-radar.service`,
  `crypto-market-horizons.service`: tracked source aligned with already-clean
  VPS runtime (`.env` only).
- `crypto-quant-observer.service`, `crypto-radar-bot.service`,
  `paper-arena.service`, `crypto-watchdog.service`: retain service identity
  secrets while stripping exchange private credentials using
  `UnsetEnvironment=`.
- `crypto-dashboard.service`: retains `DASHBOARD_PASSWORD` access, strips
  exchange credentials, and aligns Python ExecStart with the observed VPS
  virtualenv path.
- Added source-boundary tests and a post-deploy READ-ONLY evidence collector.

## Deliberately unchanged

- `crypto-advisor.service`
- `infra/exchange_factory.py`
- private account readers (`mexc_reader`, `real_accounts`, `exchange_sync`)
- Treasury / reconciliation / execution authority
- strategies, signals, risk, sizing, portfolio admission and order logic
- real credential values
- F-00 / burn-in state
