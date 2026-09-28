# ARCH-CONSOLIDATE-01B — VPS read-only runtime evidence

Issue: #309  
Parent: #287  
Roadmap: #285  
Burn-in guard: #286  
Source-forensic prerequisite: PR #306, merged as `71bdda7bd786a5e7dc39d8d845b233ed9b0b1640`

## Scope and safety boundary

This document records a bounded, read-only VPS observation performed on 2026-09-28 UTC. No service start, stop, restart, enable, disable, daemon reload, deployment, file write, environment change, port change, package change, secret read, PPL/FIN/epoch/config/strategy/risk/sizing mutation, TESTNET/LIVE action, or exchange write was performed.

Observation timestamp: `2026-09-28T01:41:18Z`  
Host: `crypto-advisor-2`  
VPS checkout: detached `116634be0d3c015cce1cfa58be7da7255414fbfd`  
VPS worktree: clean (`dirty_count=0`)  
Checkout identity: `audit(vps): BURNIN-QUIESCE-01-VERIFY-20260926A`

The detached audit checkout is recorded as provenance. The runtime facts below describe the deployed VPS state; they do not claim that the VPS checkout equals current GitHub `main`.

## Evidence method

Allowed read-only observations were used: `systemctl show`, `systemctl list-timers`, `systemctl list-unit-files`, `systemctl list-units`, `ps`, `ss -ltnp`, bounded process matching, bounded cron/systemd reference searches, `readlink`, `sha256sum`, and Git identity/status reads. Environment values and secrets were not printed.

## Resolution matrix

| # | Runtime question | Observed evidence | Resolution | Classification impact |
|---|---|---|---|---|
| 1 | Is `sdos_terminal/` deployed/reachable? | No matching process; no listener on expected port `8765`. | No running deployment observed. | `WEB-02/API-02: NOT_RUNNING`; cleanup remains unauthorized. |
| 2 | Is `infra/api/api_server.py` deployed? | No matching process. The Python listener on `0.0.0.0:8080`, PID `882633`, belongs to `crypto-advisor.service` via cgroup `/system.slice/crypto-advisor.service`, not the legacy API. | Legacy API is not running. | `API-03: NOT_RUNNING`; port 8080 must not be attributed to it. |
| 3 | Is `crypto-dashboard.service` installed/enabled/active and source-aligned? | Loaded, enabled, active/running; PID `425`; ExecStart `.venv/bin/python scripts/dashboard_api.py`; listener `0.0.0.0:8050`. | Yes; deployed ExecStart matches the source-identified CryptoRadar dashboard. | `WEB-05/API-06: RUNTIME_CONFIRMED_ACTIVE`. |
| 4 | Are the three Market timers installed/enabled/active? | Horizons, observer, and radar timers are loaded, enabled, active/waiting and trigger their paired services. Horizons last/next: `2026-09-27 06:15:13Z` / `2026-09-28 06:15:00Z`; radar: `2026-09-27 06:00:13Z` / `2026-09-28 06:00:00Z`; observer last trigger `2026-09-28 01:30:20Z`. | All three timer paths are runtime-confirmed. | Timer runtime UNKNOWNs resolved. |
| 5 | Is `@Telemetrie_IA_bot` running, and under which process? | No `sim_bot.py` or `bot_runner.py` process and no dedicated matching unit. `crypto-narrator.service` is a distinct `observability.narrator` unit; it is enabled but failed, PID 0, result `exit-code`, status 1. Google OpenTelemetry is unrelated. | Historical Telemetrie bot is not running; no runtime identity/process mapping exists. Narrator failure is separate. | `@Telemetrie_IA_bot/sim_bot: NOT_RUNNING`; narrator remains a separately observed failed service. |
| 6 | Do Operator API/Web map 1:1 to the canonical Operator surfaces? | API: enabled, active/running, PID `502983`, ExecStart `uvicorn observability.operator_api.app:app --host 127.0.0.1 --port 8090 --no-access-log`, listener `127.0.0.1:8090`. Web: enabled, active/running, PID `11940`, ExecStart `node frontend/scripts/web01_local_frontend_server.mjs`, listener `127.0.0.1:8181`. | Yes, exact canonical API/App mapping is runtime-confirmed. | `API-01/WEB-01: RUNTIME_CONFIRMED_ACTIVE`. |
| 7 | Is `governance/status_dashboard.py` invoked? | No matching process, no readable system cron reference, no user-crontab reference, and no systemd unit reference. File exists but is not invoked by observed operator/runtime paths. | No invocation observed. | `WEB-04: DORMANT_SOURCE_PRESENT`; cleanup remains unauthorized. |
| 8 | Is `crypto-market-snapshot.service` active and source-aligned? | Loaded, enabled, active/running; PID `490629`; ExecStart `.venv/bin/python -m observability.market_radar_snapshot --interval 30`. | Yes; it directly backs `observability.market_radar_snapshot`. | Market snapshot runtime UNKNOWN resolved. |

## Deployed source fingerprints

| Path | SHA-256 |
|---|---|
| `scripts/dashboard_api.py` | `037f9fbc2d962154c2392e6529b43fcfdf28ff1435bf58a5e0a554bdd69f0860` |
| `infra/api/api_server.py` | `dd7e2fee6a8661a75e38ba36942541fd971e8e8d1cb293c6e59f558693343788` |
| `governance/status_dashboard.py` | `36ed8da376e66f2f5e84170b38bc20577083664b1fb8ae5270fa141547586eb8` |
| `src/telegram/sim_bot.py` | `792affa5921102a6c2aab340804852a22ba90d5fe239b16d2353eb4b97fa33b3` |
| `src/telegram/bot_runner.py` | `edbbcafd8c7caf1be7d118736853f7ccdf6af64fc926afb492be358beb3302d5` |
| `observability/operator_api/app.py` | `e475c3888b901513124935a4cb5c9286d45bbb17a4a09c41067a4add7ddb2496` |

## Residual findings and boundaries

1. `crypto-dashboard.service` listens on all interfaces at port `8050`. This is an observed fact, not authorization to change exposure.
2. `crypto-narrator.service` is enabled but failed. This is a separate operational finding and is not evidence that `@Telemetrie_IA_bot` runs.
3. Source files for dormant components remain present. This mission authorizes no archive, retirement, migration, deletion, or cleanup.
4. The VPS checkout is a clean detached audit commit and is not current GitHub `main`. No deployment or checkout change is authorized.

## Verdict

All eight runtime/VPS UNKNOWN questions defined by #309 have bounded read-only answers.

**`ARCH_CONSOLIDATION_RUNTIME_UNKNOWN_EVIDENCE_CERTIFIED`**

This verdict resolves the evidence questions only. It does not authorize retirement, migration, cleanup, deployment, restart, runtime mutation, or progression into TESTNET/LIVE.
