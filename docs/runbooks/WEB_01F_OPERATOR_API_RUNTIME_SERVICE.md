# WEB-01F — Operator API durable local runtime

## Purpose

Industrialize the already-existing read-only Operator API as one independent,
loopback-only systemd service on the production VPS.

This mission does **not** expose HTTP publicly and does not modify Advisor,
Risk, Execution, strategy, sizing, portfolio, PAPER/REAL authority, Telegram
identity, or exchange connectivity.

The durable WEB-01 MARKET path becomes:

```text
DecisionPacket JSONL
        |
        v
crypto-market-snapshot.service
        |
        v
cryptoradar_market_snapshot.json
        |
        v
crypto-operator-api.service  (127.0.0.1:8090 only)
        |
        v
GET /api/operator/v1/market
```

MARKET authority remains `OBSERVATIONAL_TELEMETRY` / `OBSERVATION`.

## Scope boundary

WEB-01F certifies the **local API transport runtime** and its read-only MARKET
route. It does not certify a public web deployment, frontend/PWA deployment,
authentication, TLS, reverse proxying, or remote access.

The canonical advisor snapshot route is intentionally independent from MARKET.
If `/api/operator/v1/snapshot` returns an explicit `503` because its governed
snapshot/manifest artifact is absent or invalid, WEB-01F records that evidence
without fabricating state. Such a result does not invalidate a healthy
`/healthz` transport or a valid `/api/operator/v1/market` route.

## Committed unit

`scripts/systemd/crypto-operator-api.service`

Required properties:

- its own systemd cgroup;
- `User=mathieu`;
- exact project working directory and venv Python;
- Uvicorn launches `observability.operator_api.app:app`;
- bind address hard-coded to `127.0.0.1`;
- fixed local port `8090`;
- no `--reload`;
- explicit canonical snapshot, manifest and MARKET artifact paths;
- no `.env`, `.env.secrets` or dedicated secret fragment;
- no Telegram token/chat identity;
- no exchange API credential;
- no `Wants=`, `Requires=` or `BindsTo=` authority edge;
- `Restart=on-failure`;
- `NoNewPrivileges=true`;
- `PrivateTmp=true`;
- `ProtectSystem=full`;
- journal stdout/stderr.

## Read-only API semantics

The existing application remains authoritative for route semantics:

- `/healthz` means only that the API transport process is ready;
- `/api/operator/v1/market` reads only the atomic CryptoRadar MARKET artifact;
- MARKET freshness is classified from `generated_at_utc`;
- `source_updated_at_utc` remains independent source provenance;
- invalid/missing artifacts fail explicitly instead of being inferred;
- business routes are GET-only;
- no CORS middleware, write route, exchange call, Telegram call, or trading
  authority is introduced by WEB-01F.

## Source acceptance

Before merge, at minimum run:

```bash
pytest -q \
  tests/test_web01f_operator_api_runtime_service.py \
  tests/test_operator_market_api.py \
  tests/test_market_radar_snapshot.py \
  tests/test_claude_service_matrix.py \
  tests/test_sec_api_01_public_private_boundary.py
```

General repository CI remains authoritative for regression acceptance.

## Governed VPS deployment

Deployment is an explicit operator action only after the WEB-01F PR is merged
and its exact merge SHA is certified. Never deploy a floating `main`.

Preconditions:

```bash
cd /home/mathieu/crypto_ai_terminal
git status --short
git fetch --no-tags origin main
git rev-parse HEAD
git rev-parse origin/main
systemctl is-active crypto-market-snapshot.service
ss -ltnp | grep ':8090 ' || true
```

The production worktree must be clean. Port `8090` must be free before the new
unit is started. The deployment update must be fast-forward only to the exact
certified merge SHA.

After source synchronization:

```bash
systemd-analyze verify scripts/systemd/crypto-operator-api.service
sudo install -m 0644 \
  scripts/systemd/crypto-operator-api.service \
  /etc/systemd/system/crypto-operator-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now crypto-operator-api.service
```

No pre-existing service needs to be restarted merely to install WEB-01F.

## Post-deployment runtime proof

Collect at minimum:

```bash
systemctl is-active crypto-operator-api.service
systemctl show crypto-operator-api.service \
  -p LoadState -p ActiveState -p SubState -p MainPID -p NRestarts -p Result \
  --no-pager
ss -ltnp | grep ':8090 '
curl -fsS http://127.0.0.1:8090/healthz
curl -fsS http://127.0.0.1:8090/api/operator/v1/market
curl -sS -o /tmp/web01f-snapshot.json -w '%{http_code}\n' \
  http://127.0.0.1:8090/api/operator/v1/snapshot
```

A valid WEB-01F runtime proof requires:

- service active/running;
- no restart loop;
- listener exactly on loopback port `8090`, never `0.0.0.0:8090` or `[::]:8090`;
- `/healthz` HTTP 200 with transport-only readiness semantics;
- `/api/operator/v1/market` HTTP 200;
- MARKET authority remains `OBSERVATIONAL_TELEMETRY`;
- MARKET mode remains `OBSERVATION`;
- MARKET closed-schema/read-only validation remains intact;
- a currently publishing MARKET snapshot is classified `FRESH`;
- no mutating business route is introduced;
- pre-existing production services remain unaffected.

The canonical `/snapshot` response must be recorded separately. An explicit
503 is preserved as unresolved canonical-artifact evidence, not rewritten as a
successful state.

Only after those observations may the service be marked:

`WEB_01F_OPERATOR_API_RUNTIME_CERTIFIED`

## Rollback

Rollback affects only the new local API unit:

```bash
sudo systemctl disable --now crypto-operator-api.service
sudo rm /etc/systemd/system/crypto-operator-api.service
sudo systemctl daemon-reload
sudo systemctl reset-failed crypto-operator-api.service || true
```

No MARKET artifact, canonical snapshot, or production trading state is deleted
by this rollback.

## Out of scope

- `0.0.0.0` / public HTTP exposure;
- TLS, reverse proxy, VPN or tunnel exposure;
- authentication/authorization for remote clients;
- frontend/PWA deployment;
- Scores domain;
- strategy/risk/execution changes;
- PAPER or REAL authority changes;
- restart of Advisor, CryptoRadar, dashboard, LMI or MARKET publisher merely
  because WEB-01F exists.
