# SEC-API-01 — Controlled deployment plan

This document is operational guidance only. It does not authorize a deploy by itself.

## Pre-deploy

1. Verify the approved SEC-API-01 PR is merged to `main`; record merged SHA.
2. Verify VPS working tree is clean and fast-forwardable.
3. Back up affected installed unit files to a timestamped operator directory.
4. Do not rotate, revoke or print exchange credentials.
5. Before restarting any affected passive identity service, provision its dedicated runtime-only fragment:
   - `/etc/crypto-ai/secrets/quant-observer.env`
   - `/etc/crypto-ai/secrets/radar-bot.env`
   - `/etc/crypto-ai/secrets/dashboard.env`\n   - `/etc/crypto-ai/secrets/paper-arena.env`\n   - `/etc/crypto-ai/secrets/watchdog.env`
6. Populate fragments HUMAN_ONLY from existing authorized values; never commit or echo values.
7. Restrict fragment permissions appropriately.

## Deploy source

Fast-forward the VPS repository to the merged SHA.

## Synchronize affected unit files

Candidate tracked units:

- `crypto-market-observer.service`
- `crypto-market-radar.service`
- `crypto-market-horizons.service`
- `crypto-quant-observer.service`
- `crypto-radar-bot.service`
- `crypto-dashboard.service`
- `paper-arena.service`
- `crypto-watchdog.service`

Only copy a unit if installed or intentionally managed on this VPS. Never install an absent service solely to satisfy SEC-API-01.

Run `systemd-analyze verify` before replacing runtime copies, then `systemctl daemon-reload`.

## Restart policy

Restart only persistent passive services whose unit definition changed and that were already running. Do not restart `crypto-advisor.service`.

Oneshot market services remain timer-driven unless separately authorized.

## Runtime evidence

Run:

```bash
bash docs/security/SEC_API_01_POST_DEPLOY_READ_ONLY.sh
```

Expected persistent passive result:

- exchange private credential names: `ABSENT` or otherwise non-usable according to probe contract;
- Quant identity present only in Quant;
- Radar identity present only in Radar;
- `DASHBOARD_PASSWORD` present only in Dashboard;\n- Paper Arena identity present only in Paper Arena;\n- Watchdog identity present only in Watchdog;
- no cross-service identities;
- no restart loop or new authentication failure.

Private execution/account boundaries remain outside this stripping rule.

## Rollback

If a passive service loses legitimate identity or enters a restart loop:

1. restore its backed-up unit;
2. restore its previous EnvironmentFile wiring;
3. `systemctl daemon-reload`;
4. restart only that passive service;
5. record `SEC_API_01_REMEDIATION_REQUIRED`;
6. do not restart `crypto-advisor.service` or alter exchange keys as a workaround.
