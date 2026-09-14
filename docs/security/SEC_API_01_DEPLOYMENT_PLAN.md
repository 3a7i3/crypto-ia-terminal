# SEC-API-01 — Controlled deployment plan

This document is operational guidance only. It does not authorize a deploy by
itself.

## Pre-deploy

1. Verify branch merged to `main` and record merged SHA.
2. On VPS verify tracked working tree clean and `HEAD` fast-forwardable.
3. Back up only the affected installed unit files to a timestamped operator
   directory.
4. Do not modify `.env.secrets` or rotate keys during this mission.

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

Only copy a unit if it is installed or intentionally managed on this VPS.
Never install a previously absent service merely to satisfy SEC-API-01.

Run `systemd-analyze verify` on the candidate unit files before replacing
runtime copies. Then `daemon-reload`.

## Restart policy

Restart only persistent passive services whose unit definition changed and
that were already running before deployment. Do not restart
`crypto-advisor.service` as part of SEC-API-01.

Oneshot market services are timer-driven; do not force a market run solely for
credential-boundary certification unless separately authorized.

## Runtime evidence

Run:

```bash
bash docs/security/SEC_API_01_POST_DEPLOY_READ_ONLY.sh
```

The collector prints names/states only, never secret values.

Expected passive persistent result:

- `exchange_private_nonempty=NONE`
- required service identity (`QUANT_CRYPTO_BOT_TOKEN`, `RADAR_BOT_TOKEN`, etc.)
  remains `NONEMPTY` when that service is configured/running
- no restart loop or new authentication failure

Private execution/account boundaries remain outside the stripping rule.

## Rollback

If a passive service loses its legitimate identity or enters a restart loop:
restore its backed-up unit file, run `daemon-reload`, restart only that passive
service and record `SEC_API_01_REMEDIATION_REQUIRED` until investigated.
