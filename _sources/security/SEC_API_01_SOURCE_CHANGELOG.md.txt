# SEC-API-01 — Source remediation changelog

Base: `101359db3993801f2290a0e0fefa3226fb939574`

## Changed

- `infra/stream_bus.py`: public CCXT Pro configuration; private auth fields stripped.
- `quant_hedge_ai/agents/market/historical_fetcher.py`: public OHLCV client; exchange credentials no longer consulted.
- market observer/radar/horizons units: source aligned with already-clean VPS runtime (`.env` only).
- Quant Observer: global `.env.secrets` removed; mandatory `/etc/crypto-ai/secrets/quant-observer.env`.
- Radar Bot: global `.env.secrets` removed; mandatory `/etc/crypto-ai/secrets/radar-bot.env`.
- Dashboard: global `.env.secrets` removed; mandatory `/etc/crypto-ai/secrets/dashboard.env`; virtualenv ExecStart retained.
- Paper Arena: global `.env.secrets` removed; mandatory `/etc/crypto-ai/secrets/paper-arena.env`.\n- Watchdog: global `.env.secrets` removed; mandatory `/etc/crypto-ai/secrets/watchdog.env`.
- Source-boundary tests and post-deploy READ-ONLY evidence tooling are included.
- Verdict vocabulary corrected to `SEC_API_01_CERTIFIED` / `SEC_API_01_REMEDIATION_REQUIRED`.

## Deliberately unchanged

- `crypto-advisor.service`
- private account readers
- exchange factory / execution authority
- strategies, signals, risk, sizing, portfolio admission and order logic
- real credential values
- F-00 / burn-in state
