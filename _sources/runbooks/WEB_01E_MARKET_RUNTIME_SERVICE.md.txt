# WEB-01E — MARKET continuous runtime service

## Purpose

Industrialize the already-certified WEB-01 / MARKET CryptoRadar publisher as
one independent, passive systemd process.

This mission does **not** deploy the Operator API or frontend and does not
change Advisor, Risk, Execution, strategy, sizing, portfolio, PAPER authority,
Telegram identity, or exchange connectivity.

Data flow remains one-way:

```text
DecisionPacket JSONL
        |
        v
CryptoRadar aggregation
        |
        v
cryptoradar_market_snapshot.json  (atomic os.replace)
        |
        v
Operator API / MARKET view (separate deployment mission)
```

Authority remains `OBSERVATIONAL_TELEMETRY` / `OBSERVATION`.

## Certified pre-service runtime evidence — 2026-09-15

Before creation of this unit, the merged WEB-01 MARKET implementation at
`0fbd197f9ec0f24ae9b1cd196c7abf7a745487e0` was exercised on the real VPS
against real DecisionPacket files from `/home/mathieu/crypto_ai_terminal/databases`.

Observed evidence included:

- producer contract: `MARKET_CONTRACT=PASS`;
- execution-field guard: `EXECUTION_LEAK_CHECK=PASS`;
- API route: HTTP 200 with `MARKET_API_CONTRACT=PASS`;
- API bound only to `127.0.0.1` during the isolated test;
- isolated API stopped cleanly;
- continuous producer published at least two successive snapshots;
- observed inode change across publications: `ATOMIC_REPLACE_OBSERVED=PASS`;
- reader immediately after the second publication: `FRESH`, age about 1.65 s;
- `CONTINUOUS_FRESHNESS=PASS`;
- `PRODUCER_STOP=PASS`;
- Advisor, CryptoRadar bot, dashboard and LMI services remained active.

One observed second-cycle snapshot contained 36,550 packets, 135 symbols and
114 CryptoRadar threshold-qualified symbols. These values are evidence from
that observation only, not constants or expected future counts.

## Freshness semantics

`freshness_classification` is intentionally **transport snapshot freshness**.
It is derived from `generated_at_utc` and does not claim that the upstream
DecisionPacket stream itself is current.

`source_updated_at_utc` is separate provenance: it is the newest genuine
DecisionPacket `created_at` seen by the publisher. Operators must use both
fields when diagnosing a stale upstream producer. WEB-01E must not replace an
old or missing source timestamp with generation time.

## Unit security contract

Committed unit:

`scripts/systemd/crypto-market-snapshot.service`

Required properties:

- its own systemd cgroup;
- `User=mathieu`;
- exact project working directory and venv Python;
- explicit `DP_LOG_DIR` and `RADAR_MARKET_SNAPSHOT_PATH` only;
- no `.env.secrets` or dedicated secret fragment;
- no Telegram token/chat identity;
- no exchange API credential;
- no `Wants=`, `Requires=` or `BindsTo=` edge that could start an authority
  process merely because the observational service is enabled;
- `Restart=on-failure`;
- `NoNewPrivileges=true`;
- `PrivateTmp=true`;
- `ProtectSystem=full`;
- journal stdout/stderr;
- 30-second publisher cadence.

The unit may use `After=crypto-advisor.service` only as ordering metadata when
both units are already part of the transaction. It must not pull Advisor into
the transaction.

## Source acceptance

Before merge, at minimum run:

```bash
pytest -q tests/test_web01e_market_runtime_service.py \
  tests/test_market_radar_snapshot.py \
  tests/test_operator_market_api.py \
  tests/test_sec_api_01_public_private_boundary.py
```

General repository CI remains authoritative for regression acceptance.

## Governed VPS deployment

Deployment is an explicit operator gesture **after** the WEB-01E PR is merged
and its exact merge SHA is certified.

Do not substitute a floating `main` for the expected SHA.

Preconditions:

```bash
cd /home/mathieu/crypto_ai_terminal
git status --short
git fetch --no-tags origin main
git rev-parse HEAD
git rev-parse origin/main
```

The production worktree must be clean. The deployment operator must establish
that the selected merged SHA is the exact intended release and that the local
update is fast-forward only.

After synchronizing the worktree to that exact release, validate and install:

```bash
systemd-analyze verify scripts/systemd/crypto-market-snapshot.service
sudo install -m 0644 \
  scripts/systemd/crypto-market-snapshot.service \
  /etc/systemd/system/crypto-market-snapshot.service
sudo systemctl daemon-reload
sudo systemctl enable --now crypto-market-snapshot.service
```

No existing service needs to be restarted merely to install this publisher.

## Post-deployment runtime proof

Collect at minimum:

```bash
systemctl is-active crypto-market-snapshot.service
systemctl show crypto-market-snapshot.service \
  -p LoadState -p ActiveState -p SubState -p MainPID -p NRestarts -p Result \
  --no-pager
```

After more than one 30-second cadence, verify that the artifact exists and is
parseable, then use the committed `MarketSnapshotReader` to inspect transport
freshness. Also record `generated_at_utc` and `source_updated_at_utc` separately.

A valid service runtime proof requires:

- service active/running;
- no restart loop;
- at least two successful publications;
- parseable closed-schema artifact;
- authority remains `OBSERVATIONAL_TELEMETRY`;
- no execution-shaped fields;
- recent transport snapshot is `FRESH` while the service is publishing;
- source timestamp is reported independently, never inferred;
- pre-existing production services remain unaffected.

Only then may the durable service be marked `WEB_01E_MARKET_SERVICE_RUNTIME_CERTIFIED`.

## Rollback

Rollback affects only the new publisher unit:

```bash
sudo systemctl disable --now crypto-market-snapshot.service
sudo rm /etc/systemd/system/crypto-market-snapshot.service
sudo systemctl daemon-reload
sudo systemctl reset-failed crypto-market-snapshot.service || true
```

The last generated `databases/cryptoradar_market_snapshot.json` is not deleted
automatically. It remains historical evidence and will naturally classify
`STALE` once no new publisher generation occurs. Removal or archival of that
artifact is a separate explicit operator action.

## Out of scope

- permanent Operator API systemd unit;
- external/public HTTP exposure;
- frontend/PWA deployment;
- authentication design for a future remote web surface;
- Scores domain;
- strategy/risk/execution changes;
- PAPER or REAL authority changes.
