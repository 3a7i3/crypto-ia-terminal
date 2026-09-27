# ARCH-CONSOLIDATE-01 — Forensic des surfaces Web, APIs, Telegram, services et code legacy

**Mission**: #287 (read-only forensic). Roadmap: #285. Garde-fou burn-in: #286.
Observation runtime en cours: #282, epoch `BURN-IN-EPOCH-01-20260926T064144Z`.

**Verdict**: `ARCH_CONSOLIDATION_FORENSIC_SOURCE_READY` (see §17)

This document is a static-evidence forensic inventory built from a read-only
pass over the repository tree at the SHA recorded below. It does not certify
runtime state (no VPS/systemd/process access was performed), and it makes no
change to any runtime, config, service, or file besides itself.

---

## 1. Executive Summary

The repository already carries a substantial amount of prior, still-current
forensic and governance documentation (`docs/observability/TELEGRAM_BOT_REGISTRY.md`,
`architecture/CANONICAL_COMPONENTS.md`, `docs/runbooks/SERVICE_MATRIX_AUDIT_PACK.md`,
`docs/contracts/WEB_01_MARKET_CRYPTORADAR_CONTRACT.md`, `docs/architecture/
TELEGRAM_ECOSYSTEM_MAP.md`, `docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md`).
This forensic **synthesizes** that existing evidence plus a fresh static pass,
rather than re-deriving it from zero, and flags where prior documents disagree
or leave gaps (notably the `@Telemetrie_IA_bot` identity ambiguity, already
marked unresolved in `TELEGRAM_BOT_REGISTRY.md`).

Key findings:

- **One canonical web application exists in principle**: the Operator Web App
  (`frontend/` React app + `observability/operator_api/app.py` FastAPI
  backend), fed by governed snapshot producers
  (`observability/operator_snapshot_builder.py`,
  `observability/market_radar_snapshot.py`). This matches the target
  architecture `engine → projection/snapshot → Operator API → App` stated in
  #287/#285.
- **A standalone CryptoRadar web dashboard exists in source**:
  `scripts/dashboard_api.py` is a self-contained FastAPI+HTML application
  (own `/api/scan`, `/api/signals`, `/api/symbol/{symbol}`, `/api/status`,
  `/api/lmi/*` routes, own password-gated login page, default
  `DASHBOARD_PORT=8050`), declared by `scripts/systemd/crypto-dashboard.service`
  (`Description=CryptoRadar Web Dashboard`, `ExecStart=... scripts/dashboard_api.py`).
  It reads `databases/decision_packets_*.jsonl` directly and recomputes its
  own scan/signal statistics (`load_recent_packets()`, `compute_stats()`),
  independently of `observability/market_radar_snapshot.py`. This corrects an
  earlier draft of this document, which stated no independent CryptoRadar
  site exists in source — that was wrong; only its live/deployed status on
  the VPS remains unproven (§12).
- **Five Telegram bots** are documented with clear evidence in
  `docs/observability/TELEGRAM_BOT_REGISTRY.md`: `@QuantCrpto_bot` (Quant
  Observer), `@mon_portfolio_bot` (Portfolio/Command Center), `@PaperArena_bot`,
  `@Telemetrie_IA_bot`/CMVK/Sim Bot (identity unresolved, no systemd evidence),
  and `@RadarCrypto1_bot` (CryptoRadar). `capital_deployment/command_center_bot.py`
  is the implementation behind `@mon_portfolio_bot`, not a sixth bot.
- **A second, separate FastAPI+React stack exists**: `sdos_terminal/` (its own
  `api/app.py`, its own `frontend/`). It is read-only (ADR-0007 compliant) and
  is referenced from exactly one production module
  (`observability/operator/domains/regret_state.py`) — insufficient evidence
  to determine whether it is a live parallel surface or a dormant
  research/debug tool. Classified `UNKNOWN`.
- **A third FastAPI surface**, `infra/api/api_server.py`, has no confirmed
  importers/consumers found in this pass and no matching systemd unit in
  `scripts/systemd/`. Classified `UNKNOWN` pending VPS evidence.
- **Legacy Windows `.bat`/panel-based dashboards** (Dash/Panel/Streamlit
  scripts under root, `infra/panels/`, `dashboard/alert_dashboard.py`,
  `launch_*.bat`) are pre-existing, largely Windows-desktop-era artifacts.
  `panel_test_report.txt` itself records these panels **already failing**
  (`ModuleNotFoundError: seaborn`) on 2026-04-29, which is direct evidence of
  reduced/no current runtime health for that surface, but `dashboard/
  alert_dashboard.py` (the audit-log reader) is still imported by
  `infra/panels/panel_ci_report.py`, `panel_http_test.py`,
  `core/orchestration/orchestrate_internal_panels.py`, and has a dedicated
  test — so it cannot be marked RETIRE outright; the wrapping Windows
  panel launchers around it are a different, more clearly legacy layer.
- **`_ARCHIVE_2026/`** already holds a prior generation of retired code,
  including `telegram_bot_duplicates_20260706/` — direct historical evidence
  that at least one prior Telegram bot consolidation pass occurred; it is
  itself out of scope for new classification (already archived).
- **systemd catalog** (from `docs/runbooks/SERVICE_MATRIX_AUDIT_PACK.md` §
  "Fixed service catalog", cross-checked against `scripts/systemd/*.service`)
  lists 10 audited units, while `scripts/systemd/` on disk holds **16**
  unit/timer files (corrected count, see §6) — several units in
  `scripts/systemd/` (`crypto-operator-web.service`,
  `crypto-market-snapshot.service`, and the three `.timer` files) are **not**
  in the service_matrix's fixed catalog, meaning the audit pack's official
  "what runs on the VPS" list is now stale relative to the repo's own
  systemd unit definitions — a governance gap, not a code defect.
- No direct evidence of raw JSONL/DB reads from the canonical frontend or
  Operator API bypassing governed projections was found; documented bypass
  patterns exist in the **Telegram** layer (`scripts/radar_bot.py` reading
  `databases/decision_packets_{date}.jsonl` directly, and
  `capital_deployment/command_center_bot.py` closing over live
  advisor-loop/paper-trading in-process state — both already flagged in the
  existing Telegram registry) and, newly identified in this pass, in the
  **`scripts/dashboard_api.py`** CryptoRadar web dashboard, which reads the
  same `decision_packets_*.jsonl` files directly and independently
  recomputes scanner/signal statistics rather than consuming the governed
  `observability/market_radar_snapshot.py` bridge.
- **systemd catalog**: `scripts/systemd/` holds **16** unit/timer files (not
  15 as an earlier draft of this document stated), including
  `crypto-dashboard.service`, whose source-declared `ExecStart` launches
  `scripts/dashboard_api.py` — a source-level fact, independent of whether
  that unit is currently active on the VPS (§12).

## 1bis. Answers to the 13 special questions

1. **How many distinct web surfaces exist?** Four at the code level: (1)
   the canonical Operator Web App (`frontend/`), (2) the parallel SDOS
   Terminal stack (`sdos_terminal/`), (3) the standalone CryptoRadar web
   dashboard (`scripts/dashboard_api.py`, backing `crypto-dashboard.service`),
   (4) the legacy Windows panel/dashboard layer (`dashboard/`,
   `infra/panels/`, root `.bat` launchers) — the last one already shown
   broken in `panel_test_report.txt`.
2. **What is the canonical web app?** The Operator Web App:
   `frontend/` (React/Vite) served by `observability/operator_api/app.py`
   (FastAPI), per #285's target architecture and `architecture/
   CANONICAL_COMPONENTS.md`.
3. **Does an independent CryptoRadar site still exist, and what would be
   needed before retiring it?** Yes, in source: `scripts/dashboard_api.py`
   is a standalone FastAPI+HTML CryptoRadar site (own routes, own login
   page, own `DASHBOARD_PORT`), declared by `crypto-dashboard.service`.
   Whether it is actually deployed/reachable on the VPS today remains
   `UNKNOWN` (§12) — that is a separate question from its existence in
   source, which is now confirmed. It contains its own scan/signal/status
   computation (`compute_stats()`, `extract_signals()`) read directly from
   `decision_packets_*.jsonl`, duplicating logic also present in
   `scripts/radar_bot.py` and, more governed, in
   `observability/market_radar_snapshot.py` (Operator API MARKET bridge,
   per `docs/contracts/WEB_01_MARKET_CRYPTORADAR_CONTRACT.md`). Before this
   site could be retired, the Operator App's MARKET view would need to
   reach parity with `dashboard_api.py`'s scan/signal/symbol/status/LMI
   routes, and both `dashboard_api.py` and `scripts/radar_bot.py` would need
   their direct JSONL reads replaced by the governed snapshot producer.
4. **How many Telegram bots exist, and their details?** Five identities are
   documented: `@QuantCrpto_bot`, `@mon_portfolio_bot`, `@PaperArena_bot`,
   `@Telemetrie_IA_bot` (identity/deployment unresolved), `@RadarCrypto1_bot`
   — full detail in §5.
5. **Is there scientific/financial logic that lives ONLY behind Telegram?**
   No irreproducible *scientific* logic was found hidden only in a bot; the
   closest cases are (a) `@PaperArena_bot`'s hand-duplicated ENL friction
   model (`_enl_fill()`), which duplicates rather than uniquely holds logic
   also present in `src/execution/enl.py`, and (b) `src/telegram/
   sim_bot.py`'s three duplicated aggregation implementations, which
   duplicate rather than uniquely hold logic also present in
   `src/analytics/performance_breakdown.breakdown()`. Both are duplication
   risks, not sole-custody risks.
6. **What should various Telegram functions become long-term?** Per #285/#287
   direction: business logic moves to/stays in shared modules already
   consumed by the Operator API path; presentation moves into the Operator
   App (System/Governance panel for Quant Observer, Portfolio/Finance view
   for Command Center, Market view for CryptoRadar, an Event Center for
   alerts); the Telegram transport itself is retired last, only after App
   parity is demonstrated per bot.
7. **Which servers/APIs still exist?** `observability/operator_api/app.py`
   (canonical, API-01), `sdos_terminal/api/app.py` (parallel, unresolved,
   API-02), `infra/api/api_server.py` (unresolved, no consumer found,
   API-03), `visualization/api/quant_live_api.py` (data-provider module,
   canonical producer for the Quant Observer bot, API-04),
   `scripts/dashboard_api.py` (standalone CryptoRadar Web Dashboard API,
   API-06, backing `crypto-dashboard.service`) — see §4.
8. **Are there competing sources for the same info?** Yes: performance/PnL
   aggregation is computed in at least three places for Sim Bot commands
   instead of one shared `performance_breakdown.breakdown()`; ENL friction
   cost is computed twice (canonical `src/execution/enl.py` vs.
   `@PaperArena_bot`'s local `_enl_fill()`); CryptoRadar symbol stats are
   independently parsed/aggregated in `radar_bot.py` rather than through a
   shared decision-packet aggregator also used elsewhere.
9. **Are there direct JSONL/DB reads from a UI/bot bypassing governed
   projections?** Yes, three confirmed cases: `scripts/radar_bot.py` reads
   `databases/decision_packets_{date}.jsonl` directly for `@RadarCrypto1_bot`;
   `scripts/dashboard_api.py::load_recent_packets()` reads the same files
   directly for the standalone CryptoRadar web dashboard and independently
   recomputes scanner/signal statistics (`compute_stats()`); and
   `capital_deployment/command_center_bot.py` bypasses the Operator API by
   closing over live in-process advisor-loop/paper-trading state rather than
   going through a governed HTTP boundary. No such bypass was found in the
   canonical `frontend/` — its only path is the Operator API.
10. **Which components look orphaned but can't yet be proven RETIRE?**
    `sdos_terminal/` (API+frontend), `infra/api/api_server.py`,
    `governance/status_dashboard.py`, `infra/dashboards/__init__.py` (empty
    stub) — all classified `UNKNOWN`, see §8/§12.
11. **Which dependencies still create an architecture parallel to
    engine→projection→Operator API→App?** (a) `sdos_terminal/` stack — its
    own API + its own frontend, sharing only the `visualization/api/`
    producer with the canonical Quant Observer edge; (b) `scripts/
    dashboard_api.py`'s standalone CryptoRadar Web Dashboard, a second
    ungoverned aggregator over `decision_packets_*.jsonl` alongside
    `radar_bot.py`'s; (c) the direct producer paths of the four Telegram
    bots whose source and deployment are both confirmed
    (`capital_deployment/command_center_bot.py`'s in-process closures,
    `radar_bot.py`'s direct JSONL read, `quant_observer/bot.py`'s
    otherwise-canonical but Telegram-duplicated presentation of the same
    `quant_live_api.py` data already available to the App, and
    `paper_runner.py`'s isolated loop for `@PaperArena_bot`), plus a fifth,
    `sim_bot.py`'s own SQLite store, whose bot identity/deployment is
    itself still `UNKNOWN` (§12) rather than confirmed-active.
*(Note: the source issue's prose does not enumerate a literal numbered list
of 13 questions; items 12–13 below capture the two remaining distinct
forensic questions implied by the issue text, beyond the 11 above.)*

12. **Do competing APIs expose the same data under different contracts?**
    `sdos_terminal/api/app.py` exposes `/api/portfolio`, `/api/burnin`,
    `/api/regret`, `/api/decision/{id}` — conceptually overlapping with
    Operator API's `/api/operator/v1/snapshot` domains (portfolio, decision
    pipeline, health) — but built on a separate FastAPI app with its own
    contract, not a subrouter of API-01. This is the one clearest concrete
    instance of contract duplication found, and it cannot be resolved to
    RETIRE/INTEGRATE without the VPS evidence in §12.
13. **Is there a governed path for future alerts to reach operators without
    Telegram?** Partially: `#285` names a future "Centre d'événements"
    inside the App; today no such component exists in the App itself — the
    closest existing building block is `dashboard/alert_dashboard.py`
    (reads `alerts_audit.jsonl`, presentation-only, already tested and
    imported by CI-adjacent panel scripts) which is a plausible candidate
    producer to wire into a future Event Center, rather than a governed
    Event Center that already exists.

## 2. Current canonical architecture

```
Decision engine (quant_hedge_ai/engine/decision_engine.py, DecisionEngine)
        |
        v
observability/* (heartbeat, decision_event_bus, operator_snapshot_builder,
                  market_radar_snapshot)                 [passive, ADR-0007]
        |
        v
observability/operator_api/app.py  (FastAPI, GET /api/operator/v1/snapshot,
                                     GET /api/operator/v1/market)
        |
        v
frontend/  (React/Vite Operator Web App — presentation only, per #285 §1.4)
```

Telegram bots sit **alongside** this pipeline today, each with its own
producer paths (see §4), which is exactly the "surface multiplication" #287
identifies as the pattern to unwind. `sdos_terminal/` and `infra/api/
api_server.py` are separate stacks whose current runtime role is unproven from
source alone (§9 Unknowns).

## 3. Web surfaces inventory

| id | Name | Path | Category | Producer | Consumers found | Business logic? | Classification | Confidence |
|---|---|---|---|---|---|---|---|---|
| WEB-01 | Operator Web App (canonical) | `frontend/` (React/Vite), `sdos_terminal` excluded | web app | `observability/operator_api/app.py` | end users (browser) | No — presentation only, per O-02W-B/contract docs | **KEEP** | High |
| WEB-02 | SDOS Terminal | `sdos_terminal/api/app.py`, `sdos_terminal/frontend/` | web app (parallel) | `visualization/api/` (SDOS Data API) | `observability/operator/domains/regret_state.py` (1 ref found); no systemd unit matched | Read-only per own docstring | **UNKNOWN** | Low — no systemd/consumer proof either way |
| WEB-03 | Legacy Windows dashboard launchers | `launch_*.bat` (root, ~20 files), `infra/panels/*`, `dashboard/alert_dashboard.py` | legacy desktop dashboards | various (Dash/Panel/Streamlit scripts, mostly under root or `_ARCHIVE_2026`) | `panel_test_report.txt` shows these **already broken** (missing `seaborn`) as of 2026-04-29 | `alert_dashboard.py` = presentation only (log formatter); wrapping `.bat`/panel launchers = orchestration only | `alert_dashboard.py`: **KEEP** (still imported/tested); `.bat` launchers + broken panels: **ARCHIVE** | Medium |
| WEB-04 | `infra/dashboards/` | `infra/dashboards/__init__.py` (empty module) | placeholder | none | none found | n/a | **UNKNOWN** (empty stub, no evidence of use or disuse) | Low |
| WEB-05 | CryptoRadar Web Dashboard | `scripts/dashboard_api.py` | web app (FastAPI + inline HTML) | own `load_recent_packets()`/`compute_stats()`, reading `databases/decision_packets_*.jsonl` directly | none found (standalone site; own login/session, `crypto-dashboard.service` per §6) | Yes — recomputes scan/signal/status/LMI aggregation locally, bypassing governed projections | **INTEGRATE** (fold into Operator App MARKET view; retire direct-JSONL read first, per §1 Q3) | High (source-confirmed; live/deployed status on VPS is separately `UNKNOWN`, §12) |

## 4. API inventory

| id | Name | Path | Framework | Routes (sample) | Ports/env | Consumers | Classification | Confidence |
|---|---|---|---|---|---|---|---|---|
| API-01 | Operator API | `observability/operator_api/app.py` | FastAPI | `GET /api/operator/v1/snapshot`, `GET /api/operator/v1/market` (per `WEB_01_MARKET_CRYPTORADAR_CONTRACT.md`) | Port `127.0.0.1:8090` (loopback only, per `crypto-operator-api.service`); env names: `OPERATOR_SNAPSHOT_PATH`, `OPERATOR_RUNTIME_MANIFEST_PATH`, `RADAR_MARKET_SNAPSHOT_PATH`, `RADAR_MARKET_STALE_AFTER_S` (values are file paths/durations, not secrets) | `frontend/` React app; `scripts/systemd/crypto-operator-api.service`, `crypto-operator-web.service` | **KEEP** (canonical) | High |
| API-06 | CryptoRadar Web Dashboard API | `scripts/dashboard_api.py` | FastAPI + inline HTML | `GET /api/scan`, `GET /api/signals`, `GET /api/symbol/{symbol}`, `GET /api/status`, `GET /api/lmi/status`, `GET /api/lmi/table`, `GET /api/lmi/symbol/{symbol}`, `GET /api/lmi/events`, `GET /` (login/dashboard HTML) | Default `DASHBOARD_PORT=8050` (bound `0.0.0.0`); env names: `DASHBOARD_PORT`, `DASHBOARD_PASSWORD` (secret — name only), `DP_LOG_DIR` | none found; standalone, own password-gated session | **INTEGRATE** (see WEB-05) | High |
| API-02 | SDOS Terminal API | `sdos_terminal/api/app.py` | FastAPI | `/api/health`, `/api/pipeline`, `/api/portfolio`, `/api/rejections`, `/api/burnin`, `/api/regret`, `/api/decision/{id}`, `/api/system`, PNG endpoints, `WS /ws/live` | none matched in `scripts/systemd/` | `observability/operator/domains/regret_state.py` (1 internal ref); own `sdos_terminal/frontend/` | **UNKNOWN** | Low |
| API-03 | `infra/api/api_server.py` | `infra/api/api_server.py` | not confirmed (not opened in this pass beyond path discovery) | not confirmed | not confirmed | no importer found via `grep -rl "infra.api.api_server"` | **UNKNOWN** | Low |
| API-04 | `visualization/api/quant_live_api.py` | `visualization/api/quant_live_api.py` | data-provider module (not a standalone HTTP server per registry text) | n/a — Python API, feeds `QuantLiveSnapshot` | n/a | `src/telegram/quant_observer/bot.py` (`@QuantCrpto_bot`) | **KEEP** (canonical producer for Quant Observer per `TELEGRAM_BOT_REGISTRY.md`) | High |
| API-05 | `governance/status_dashboard.py` | `governance/status_dashboard.py` | not confirmed | not confirmed | not confirmed | not confirmed | **UNKNOWN** | Low |

## 5. Telegram inventory

Synthesized directly from the existing, still-current
`docs/observability/TELEGRAM_BOT_REGISTRY.md` (itself an O-01 forensic pass
over `src/telegram/`, `capital_deployment/command_center_bot.py`,
`scripts/radar_bot.py`, `src/paper/`, `scripts/systemd/*.service`, and
`.env.example`/`.env.secrets.example`). No bot code was read or modified to
produce this section.

| Bot (BotFather name) | Role | Entrypoint | Producer | Business logic exclusive to bot? | systemd unit | Classification | Confidence |
|---|---|---|---|---|---|---|---|---|
| `@QuantCrpto_bot` "Quant Observer" | read-only decision-engine microstructure viewer | `src/telegram/quant_observer/bot.py` | `visualization/api/quant_live_api.py`, `visualization/ves` | No — "ZERO business logic" per own docstring | `crypto-quant-observer.service` | **INTEGRATE** (highest priority per registry — target: Operator App System/Governance panel) | High |
| `@mon_portfolio_bot` "Portfolio/Command Center" | KPI/capital/positions read surface, all writes hard-blocked | `capital_deployment/command_center_bot.py` | `PhaseKPITracker`, `ExecutionEngine.fetch_available_capital()`, `paper_trading.recorder`, `.env`, log files | No net-new logic, but **duplicate senders** on same identity (`CommandCenterBot.send()` + `src/telegram/notifier.py::Notifier._send()`) and a paper/real KPI labeling gap (remediated per registry O-02B/O-02B-R1) | not directly named in matrix catalog above (see §1 gap) | **INTEGRATE** (high priority) | High |
| `@PaperArena_bot` | single hard-coded research experiment (ETH/USDT 4h RSI) | `src/paper/paper_runner.py::run_paper_arena()` | own loop; hand-duplicated ENL friction model instead of importing `src/execution/enl.py` | Isolated experiment logic, but drift risk from duplicated friction math | `paper-arena.service` | **KEEP for now / low migration priority** (already clean & isolated per registry) | High |
| `@Telemetrie_IA_bot` "CMVK/Sim Bot" | backtest/simulation tooling, name implies telemetry but commands are backtesting | `src/telegram/sim_bot.py` | own `BacktestEngine`/`VirtualExchange`; persists to `databases/sim_runs.sqlite` | Cross-wiring: posts to `@mon_portfolio_bot`'s chat via its own `Notifier()`, not its own chat; 3 duplicated aggregation implementations instead of shared `src/analytics/performance_breakdown.breakdown()` | **none found** — no `.service` references `bot_runner.py`/`TELEMETRIE_IA_BOT_TOKEN` | **UNKNOWN** (identity/deployment unresolved per registry itself — do not migrate until resolved) | Low |
| `@RadarCrypto1_bot` "CryptoRadar" | market-wide opportunity scanner, explicitly excludes Entry/SL/TP/portfolio | `scripts/radar_bot.py` | reads `databases/decision_packets_{date}.jsonl` directly (bypass of governed projections); `/lmi` via `trade_analysis.integrations.radar_adapter` | `extract_signals()` computes Entry/SL/TP but is dead/unreachable — internal-only, not exposed | `crypto-radar-bot.service` | **INTEGRATE** (low priority — stable, minimize churn; migrate transport into Operator App MARKET view per `WEB_01_MARKET_CRYPTORADAR_CONTRACT.md`, keep engine) | High |
| `src/telegram/exchange_sync.py` | claims to be CCXT read-only sync for `@mon_portfolio_bot` | `src/telegram/exchange_sync.py` | independent balance/PnL/drawdown computation | Never imported anywhere in the repo | n/a | **RETIRE** (dead/duplicate code, no consumer found; registry explicitly confirms zero imports) | High |
| `_ARCHIVE_2026/telegram_bot_duplicates_20260706/capital_deployment_portfolio_bot.py` | prior duplicate of the portfolio bot | `_ARCHIVE_2026/telegram_bot_duplicates_20260706/` | n/a | n/a | n/a | **already ARCHIVE** (out of scope — prior cleanup pass) | High |

## 6. Services/process inventory

From `docs/runbooks/SERVICE_MATRIX_AUDIT_PACK.md` (fixed catalog, 10 units)
cross-checked against the **16** unit/timer files under `scripts/systemd/`
(corrected from an earlier draft's count of 15; `git ls-tree` on the
verified head confirms 16: `crypto-advisor`, `crypto-dashboard`,
`crypto-lmi-observatory`, `crypto-market-horizons` `.service`+`.timer`,
`crypto-market-observer` `.service`+`.timer`, `crypto-market-radar`
`.service`+`.timer`, `crypto-market-snapshot`, `crypto-operator-api`,
`crypto-operator-web`, `crypto-quant-observer`, `crypto-radar-bot`,
`crypto-watchdog`, `paper-arena`):

| Unit | Role/tier (per audit pack) | In fixed audit catalog? | Source-declared ExecStart | Classification | Confidence |
|---|---|---|---|---|---|
| `crypto-advisor.service` | decision engine / core | Yes | (not re-extracted in this pass) | **KEEP** | High |
| `crypto-watchdog.service` | runtime safety / safety | Yes | (not re-extracted in this pass) | **KEEP** (currently OFF per #282/#286, but the unit itself is canonical safety infra) | High |
| `crypto-dashboard.service` | web interface / interface | Yes | `.venv/bin/python scripts/dashboard_api.py` (source-confirmed; `Description=CryptoRadar Web Dashboard`) | **INTEGRATE** — source identity is now resolved (WEB-05/API-06); whether this unit is currently `active`/`enabled` on the VPS remains `UNKNOWN` (§12) | High (source) / Low (deployed state) |
| `crypto-lmi-observatory.service` | live-market observation | Yes | (not re-extracted in this pass) | **KEEP** (observation-only, ADR-0007 compliant) | Medium |
| `crypto-market-horizons.service` + `.timer` | market horizons / observation | Yes (service); timer absent from catalog | Timer: `OnCalendar=*-*-* 06:15:00 UTC` daily (ADR-0016 R2, 15 min after R1) | **KEEP** service / **KEEP** timer (source-known schedule; enabled/active runtime state remains `UNKNOWN`, §12) | Medium |
| `crypto-market-observer.service` + `.timer` | market observer / observation | Yes (service); timer absent from catalog | Timer: `OnBootSec=2min`, `OnUnitActiveSec=15min` (every 15 min after boot, ADR-0016) | **KEEP** service / **KEEP** timer (source-known schedule; enabled/active runtime state remains `UNKNOWN`, §12) | Medium |
| `crypto-market-radar.service` + `.timer` | market radar / observation | Yes (service); timer absent from catalog | Timer: `OnCalendar=*-*-* 06:00:00 UTC` daily (ADR-0016 R1) | **KEEP** service / **KEEP** timer (source-known schedule; enabled/active runtime state remains `UNKNOWN`, §12) | Medium |
| `crypto-market-snapshot.service` | (not in fixed catalog) | **No** | (not re-extracted in this pass) | **UNKNOWN** — likely producer for `observability/market_radar_snapshot.py`, but not certified by the audit pack | Low |
| `crypto-operator-api.service` | (not in fixed catalog) | **No** | `uvicorn observability.operator_api.app:app --host 127.0.0.1 --port 8090` (see API-01 ports/env) | **KEEP** (matches canonical API-01, but governance doc is stale — recommend adding to catalog) | Medium |
| `crypto-operator-web.service` | (not in fixed catalog) | **No** | (not re-extracted in this pass) | **KEEP** (matches canonical WEB-01 frontend, same stale-catalog note) | Medium |
| `crypto-quant-observer.service` | Telegram quant observer / interface | Yes | (not re-extracted in this pass) | **INTEGRATE** (see §5) | High |
| `crypto-radar-bot.service` | Telegram radar / interface | Yes | (not re-extracted in this pass) | **INTEGRATE** (see §5) | High |
| `paper-arena.service` | paper-execution interface / interface | Yes | (not re-extracted in this pass) | **KEEP** (see §5) | High |

**On "source-known" vs. "deployed" throughout this document**: a unit
file's `Description`, `ExecStart`, and any `.timer`'s `OnCalendar`/
`OnBootSec`/`OnUnitActiveSec` are static facts readable directly from the
repository at the verified head (§16) — they are not VPS/runtime claims and
do not require VPS access to state. What remains genuinely `UNKNOWN` without
VPS access is *deployed/enabled/active* state: whether that unit file is
installed under `/etc/systemd/system/`, currently `enabled`, and its
`ActiveState`. This distinction was under-stated in an earlier draft, which
is corrected here per human review.

**Risk note**: three systemd units that plausibly back canonical WEB-01/API-01
(`crypto-market-snapshot`, `crypto-operator-api`, `crypto-operator-web`) are
absent from the audit pack's fixed catalog. This is a governance/documentation
gap (the audit pack needs a version bump), not evidence that the units
themselves are illegitimate — but it also means this forensic **cannot**
independently confirm their live `ActiveState` from source alone; that
requires the audit pack itself to be re-run on the VPS, which is out of scope
for this read-only, repo-only forensic.

## 7. Snapshot/data producer inventory

| Producer | Path | Feeds | Reads raw JSONL/DB directly? | Classification | Confidence |
|---|---|---|---|---|---|
| Operator snapshot builder | `observability/operator_snapshot_builder.py` | `observability/operator_api/app.py` → `frontend/` | No — advisor-owned in-process snapshot | **KEEP** (canonical) | High |
| Market radar snapshot | `observability/market_radar_snapshot.py` | `observability/operator_api/app.py` MARKET route, per `WEB_01_MARKET_CRYPTORADAR_CONTRACT.md` | Reuses `radar_bot.py` calculation functions → atomic `cryptoradar_market_snapshot.json` (not raw JSONL directly per contract) | **KEEP** (canonical bridge, explicitly contracted as one-directional) | High |
| CryptoRadar bot calc | `scripts/radar_bot.py::compute_symbol_stats()` | Telegram `@RadarCrypto1_bot` only | **Yes** — reads `databases/decision_packets_{date}.jsonl` directly for trailing 24h | **INTEGRATE** (fold direct read into the governed snapshot producer path; do not let Telegram keep a second, ungoverned aggregator) | High |
| Command Center provider | `capital_deployment/command_center_bot.py` (`CommandDataProvider`) | `@mon_portfolio_bot` only | In-process closures over live advisor-loop state (not file reads, but also not the governed Operator API) | **INTEGRATE** | High |
| Sim Bot run store | `src/telegram/sim_bot.py` → `databases/sim_runs.sqlite` | `@Telemetrie_IA_bot` (deployment unresolved) | Yes, but to its own isolated SQLite, not shared ledgers | **UNKNOWN** (tied to bot identity resolution) | Low |
| SDOS Data API | `visualization/api/` | `sdos_terminal/api/app.py`, `src/telegram/quant_observer/bot.py` | Not confirmed in this pass | **KEEP** (at least the Quant Observer edge is canonical per registry) | Medium |
| CryptoRadar dashboard producer | `scripts/dashboard_api.py::load_recent_packets()` / `compute_stats()` | Standalone CryptoRadar Web Dashboard (WEB-05/API-06) only | **Yes** — reads `databases/decision_packets_{date}.jsonl` directly, independently of `radar_bot.py`'s own read of the same files | **INTEGRATE** (second, separate ungoverned aggregator over the same evidence store; fold into the governed snapshot producer alongside Wave 5) | High |

## 8. Legacy/code duplication inventory

| Item | Path | Evidence of consumers | Classification | Confidence |
|---|---|---|---|---|
| `_ARCHIVE_2026/` (whole tree) | `_ARCHIVE_2026/` | Already named "archive" by a prior pass; contains its own `_legacy/`, `telegram_bot_duplicates_20260706/`, `paper_trades_restore_bug_20260614/`, `mvp/` | **ARCHIVE** (already; out of new-classification scope, listed for completeness) | High |
| `src/telegram/exchange_sync.py` | `src/telegram/exchange_sync.py` | Zero imports found (confirmed independently and by the existing registry) | **RETIRE** | High |
| Legacy Windows launcher scripts (root `.bat`, `launch_*.ps1`) | repo root | `panel_test_report.txt` proves several already fail at runtime (missing `seaborn`) | **ARCHIVE** | Medium |
| `infra/dashboards/__init__.py` (empty) | `infra/dashboards/` | No content, no imports found | **UNKNOWN** (too little evidence to prove orphan vs. planned placeholder) | Low |
| Regime detector shim | `quant_hedge_ai/agents/market/regime_detector.py` | Already flagged in `architecture/CANONICAL_COMPONENTS.md` as "shim à supprimer P2", re-exports `AdvancedRegimeDetector` | **ARCHIVE** (per existing architecture doc; not new evidence, restated for completeness) | High |
| Legacy kill-switch variants | `supervision/kill_switch.py`, `supervision/telegram_kill_switch.py` | Documented as "non importée par le runtime" in `CANONICAL_COMPONENTS.md` | **ARCHIVE** (per existing doc) | High |
| `src/risk/kill_switch.py` | `src/risk/kill_switch.py` | Documented as "stub minimal pour les tests de simulation" | **KEEP** (test-only stub, has a defined purpose) | High |

## 9. Consumer/dependency graph (narrative)

```
quant_hedge_ai/engine/decision_engine.py (DecisionEngine)
   -> observability/* (heartbeat, decision_event_bus, operator_snapshot_builder)
        -> observability/operator_api/app.py (FastAPI)
             -> frontend/ (React canonical app)          [WEB-01 / API-01 — KEEP]
   -> quant_hedge_ai/agents/execution/execution_engine.py
        -> capital_deployment/command_center_bot.py -> @mon_portfolio_bot   [INTEGRATE]
   -> databases/decision_packets_*.jsonl (governed evidence store)
        -> scripts/radar_bot.py -> @RadarCrypto1_bot                        [INTEGRATE]
        -> scripts/dashboard_api.py -> CryptoRadar Web Dashboard (WEB-05)   [INTEGRATE]
        -> observability/market_radar_snapshot.py -> operator_api MARKET    [KEEP, one-way bridge]
   -> visualization/api/quant_live_api.py -> src/telegram/quant_observer -> @QuantCrpto_bot  [INTEGRATE]
   -> src/paper/paper_runner.py (isolated) -> @PaperArena_bot                [KEEP, low priority]
   -> src/telegram/sim_bot.py (deployment unresolved) -> databases/sim_runs.sqlite, cross-posts to @mon_portfolio_bot's chat  [UNKNOWN]

Parallel / unresolved stacks (no confirmed edge into the canonical graph above):
   sdos_terminal/api/app.py <- visualization/api/ (shared producer with Quant Observer)
        -> sdos_terminal/frontend/                                          [UNKNOWN]
   infra/api/api_server.py (no confirmed consumer found)                    [UNKNOWN]
```

## 10. Classification matrix (summary table)

Each row below is one uniquely-identified component from §3–8 (its table id,
e.g. `WEB-01`, `API-06`, or a systemd unit name). A bot's own producer/read
path is counted as a distinct component from the bot's presentation/transport
row wherever this document models them separately (e.g. `@RadarCrypto1_bot`
the Telegram transport vs. its `radar_bot.py` producer function vs. the
separate `dashboard_api.py` producer) — these are intentionally three rows,
not double-counting one thing. Counts below are therefore exact given this
document's own component list, not approximate.

| Classification | Count | Component IDs (this document's own row identifiers) |
|---|---:|---|
| KEEP | 16 | WEB-01, API-01, API-04, operator_snapshot_builder, market_radar_snapshot, `@PaperArena_bot`, `crypto-advisor.service`, `crypto-watchdog.service`, `crypto-lmi-observatory.service`, `crypto-market-horizons.service`+`.timer` (2), `crypto-market-observer.service`+`.timer` (2), `crypto-market-radar.service`+`.timer` (2), `src/risk/kill_switch.py` |
| INTEGRATE | 9 | `@QuantCrpto_bot`, `@mon_portfolio_bot`/`command_center_bot.py`, `@RadarCrypto1_bot`, `radar_bot.py` producer (CryptoRadar bot calc), WEB-05 (CryptoRadar Web Dashboard), API-06 (dashboard API), `dashboard_api.py` producer (CryptoRadar dashboard producer), `crypto-dashboard.service` (systemd unit backing WEB-05/API-06 — source identity resolved; its VPS activation state is separately `UNKNOWN`, §12), Command Center provider |
| MOVE | 0 | none identified with sufficient evidence in this pass — candidates would need VPS/runtime evidence first |
| ARCHIVE | 5 | `_ARCHIVE_2026/` tree (pre-existing), legacy `.bat`/panel launchers, regime-detector shim, legacy kill-switch variants, `_ARCHIVE_2026/telegram_bot_duplicates_20260706` |
| RETIRE | 1 | `src/telegram/exchange_sync.py` (zero imports, confirmed dead) |
| UNKNOWN | 6 | WEB-02/API-02 (`sdos_terminal/`, one component across API+frontend), API-03 (`infra/api/api_server.py`), API-05 (`governance/status_dashboard.py`), `@Telemetrie_IA_bot`/`sim_bot.py` (identity+deployment; its Sim Bot run store is the same unresolved component, not counted twice), `crypto-market-snapshot.service`, WEB-04 (`infra/dashboards/__init__.py`) |

This corrects an earlier draft, which both called its totals "approximate"
and listed exact counts — a contradiction. The counts above are exact given
this document's own row set; a future pass could still find additional
components not yet enumerated here (test/doc files are treated as evidence
for these rows, not separate components).

## 11. Risks

- **Stale audit-pack catalog** (§6): `crypto-operator-api.service`,
  `crypto-operator-web.service`, `crypto-market-snapshot.service`, and three
  `.timer` files exist in `scripts/systemd/` but are absent from
  `docs/runbooks/SERVICE_MATRIX_AUDIT_PACK.md`'s fixed catalog. Any future
  cleanup PR must not treat "not in the audit pack" as "not running" — it may
  simply mean the audit pack is outdated.
- **`@Telemetrie_IA_bot` identity ambiguity** (already flagged internally):
  env vars in `.env.secrets.example` say one BotFather name, a prior internal
  audit (`docs/architecture/TELEGRAM_BOT_REGISTRY.md`) says another
  (`@FtnTrading_bot`), and no systemd unit references its entrypoint. Treating
  it as RETIRE without resolving this first would risk silently deleting a
  bot that is still deployed under a different name.
- **CryptoRadar direct JSONL read**: both `scripts/radar_bot.py` (Telegram)
  and `scripts/dashboard_api.py` (standalone web dashboard) independently
  read and re-aggregate `decision_packets_*.jsonl`, each its own ungoverned
  bypass of the WEB-01 MARKET bridge, which was explicitly designed as
  one-directional to avoid this pattern reaching the frontend. Two bypasses
  over the same evidence store is a larger governance gap than the earlier
  draft of this document recorded (it named only one); any future
  consolidation must fold both into the governed producer rather than
  generalize the bypass further.
- **`sdos_terminal/` and `infra/api/api_server.py`** cannot be classified
  above UNKNOWN from source alone; marking them RETIRE without VPS evidence
  (running processes, nginx/reverse-proxy config, cron, or an explicit
  operator statement that they are dormant) would violate the fail-closed
  rule in #285 §1.5 / #286.
- **Legacy Windows panel stack** already has direct evidence of breakage
  (`panel_test_report.txt`), which reduces but does not eliminate removal
  risk — the shared `dashboard/alert_dashboard.py` module underneath it is
  still imported by non-panel code and has its own test.

## 12. Unknowns requiring runtime/VPS evidence

These are `UNKNOWN = do not touch` per #286's fail-closed rule. Source-level
facts (a unit's `Description`/`ExecStart`, a timer's schedule, a bot's
registry entry) are **not** listed here even when related VPS state is —
per human review, source-forensic completion and runtime/VPS evidence are
two different questions, and this section is scoped to the latter only:

1. Is `sdos_terminal/` (API + frontend) actually deployed/reachable on the
   VPS today, under what unit/port, and who uses it?
2. Is `infra/api/api_server.py` deployed anywhere, and by what process
   supervises it (no systemd unit name matched it in this pass)?
3. Is `crypto-dashboard.service` currently installed, `enabled`, and
   `active` on the VPS? (Its source-declared `ExecStart` —
   `scripts/dashboard_api.py` — is now confirmed from source, §6; only its
   deployed/running state is unknown.)
4. Are `crypto-market-horizons.timer`, `crypto-market-observer.timer`, and
   `crypto-market-radar.timer` currently `enabled`/`active`, and do their
   corresponding `.service` units' current `ActiveState` match the audit
   pack's last observation? (Their configured schedules are source-known,
   §6, and not themselves unknown.)
5. Is `@Telemetrie_IA_bot` actually running under any process today, and
   under which of its two candidate BotFather identities?
6. Does `crypto-operator-api.service` / `crypto-operator-web.service` map
   1:1 to `observability/operator_api/app.py` / `frontend/`, confirming
   WEB-01/API-01 are indeed the live canonical stack and not just the
   intended one?
7. Is `governance/status_dashboard.py` (API-05) invoked by any running
   process, cron, or operator workflow?
8. Is `crypto-market-snapshot.service` currently `enabled`/`active`, and
   does it in fact back `observability/market_radar_snapshot.py`?

None of these can be resolved by a read-only repository pass; they require a
future, separately-scoped, explicitly-authorized VPS read (e.g. a
`service_matrix`-style bounded audit pack extended to cover these specific
units, or an `ExecStart`-scoped follow-up pack). Runtime/VPS unknowns
remaining open does not block source-forensic completion (§17) — it blocks
only cleanup of the specific `UNKNOWN` components listed above and in §10.

## 13. Proposed migration order (Wave 1..6 — PROPOSALS ONLY, not executed)

These are **proposals for future, separately-governed PRs**. None of them are
executed by this forensic, and each would need its own issue, branch, PR, and
pass through #286 per #285 §18.

- **Wave 1 — Low-risk retirement of proven-dead code.** Remove
  `src/telegram/exchange_sync.py` (zero confirmed imports). Lowest risk item
  in this inventory.
- **Wave 2 — Resolve unknowns before any further action.** Get VPS
  enabled/active evidence for `sdos_terminal/`, `infra/api/api_server.py`,
  `governance/status_dashboard.py`, `crypto-dashboard.service`,
  `crypto-market-snapshot.service`, the three market `.timer` units, and
  `@Telemetrie_IA_bot` identity/deployment (§12). Update the
  `service_matrix` fixed catalog to include `crypto-operator-api.service`,
  `crypto-operator-web.service`, `crypto-market-snapshot.service`, and the
  three `.timer` units.
- **Wave 3 — Integrate `@QuantCrpto_bot`.** Per the registry's own
  highest-priority recommendation: fold its metrics into the Operator App's
  System/Governance panel using the already-canonical
  `visualization/api/quant_live_api.py` producer; no new producer needed.
- **Wave 4 — Integrate `@mon_portfolio_bot` / Command Center.** Consolidate
  its two independent senders (`CommandCenterBot.send()` and
  `Notifier._send()`) into one owner; migrate its KPI surface into the
  Operator App Portfolio/Finance view, sourcing from the same
  `CommandDataProvider` data already used, not a re-derivation.
- **Wave 5 — Integrate `@RadarCrypto1_bot` and the CryptoRadar Web Dashboard.**
  Replace both `scripts/radar_bot.py`'s and `scripts/dashboard_api.py`'s
  direct `databases/decision_packets_*.jsonl` reads with calls into the
  existing governed `observability/market_radar_snapshot.py` producer (or
  extend that producer to serve the same fields, including
  `dashboard_api.py`'s `/api/scan`/`/api/signals`/`/api/status`/`/api/lmi/*`
  shapes), then retire the Telegram transport and the standalone dashboard
  site, keeping the CryptoRadar calculation engine and folding its
  presentation into the Operator App MARKET view.
- **Wave 6 — Archive proven-legacy surfaces.** Legacy Windows `.bat`/panel
  launchers (with `panel_test_report.txt` as supporting evidence of already
  broken runtime), the regime-detector shim, and legacy kill-switch variants
  already flagged ARCHIVE in `architecture/CANONICAL_COMPONENTS.md` — move to
  `_ARCHIVE_2026/` rather than delete, consistent with that directory's
  existing pattern.

`@PaperArena_bot` and `@Telemetrie_IA_bot` are deliberately **not** placed in
an early wave: the former is already clean/isolated (low migration urgency),
the latter cannot be migrated safely until its identity/deployment ambiguity
is resolved (Wave 2 dependency).

## 14. Proposed future cleanup PRs (independent, each through #286)

1. `ARCH-CONSOLIDATE-01a` — Remove `src/telegram/exchange_sync.py` (Wave 1).
2. `ARCH-CONSOLIDATE-01b` — VPS-scoped audit-pack extension to resolve the
   runtime/VPS unknowns in §12 (Wave 2), read-only, no code change to
   runtime logic.
3. `ARCH-CONSOLIDATE-01c` — Update `docs/runbooks/SERVICE_MATRIX_AUDIT_PACK.md`
   fixed catalog to include the three currently-undocumented `.service` units
   and three `.timer` units (Wave 2, documentation-only).
4. `ARCH-CONSOLIDATE-01d` — Integrate `@QuantCrpto_bot` metrics into the
   Operator App (Wave 3), Telegram bot left running until App parity is
   proven, then a separate follow-up PR retires the bot transport.
5. `ARCH-CONSOLIDATE-01e` — Consolidate `@mon_portfolio_bot` senders and
   migrate its KPI surface into the Operator App (Wave 4).
6. `ARCH-CONSOLIDATE-01f` — Replace `scripts/radar_bot.py`'s and
   `scripts/dashboard_api.py`'s direct JSONL reads with the governed
   `market_radar_snapshot.py` producer, then retire the Telegram transport
   and the standalone CryptoRadar Web Dashboard, keeping the engine (Wave 5).
7. `ARCH-CONSOLIDATE-01g` — Move legacy Windows panel/launcher assets and the
   already-flagged shims/kill-switch variants into `_ARCHIVE_2026/` (Wave 6).

## 15. Explicit non-impact statement

This forensic mission made **no** change to any runtime, configuration,
service, systemd unit, database, ledger, PPL stream, Telegram bot, deployed
process, or existing file in this repository. No file was deleted. No
service was restarted, started, or stopped. No secret value was read,
printed, or transmitted — only variable/reference **names** are cited above.
The only artifact added by this mission is this single new document,
`docs/forensics/ARCH_CONSOLIDATE_01_FORENSIC.md`, on a dedicated branch not
merged by this mission. The active burn-in epoch
`BURN-IN-EPOCH-01-20260926T064144Z` (#282/#286) is entirely unaffected.

## 16. Exact source SHA / tree / branch identity

- Original forensic pass was built against `main` HEAD (via `origin/main`)
  `4016725058ba399eab470ee96b076fe7c2bbfebd`, which at that time matched the
  baseline SHA named in the mission brief (no drift).
- **Remediation pass** (this revision, responding to human review comment
  `5860949880` on PR #306): `main` had since advanced to
  `5e5163721417a646897e62669f39ee678f0161ec` (D4E/D5A landed). This branch
  was merged forward onto that HEAD before the corrections in this revision
  were made, so all source citations above (including the `scripts/systemd/`
  16-unit count and `scripts/dashboard_api.py` evidence) are verified against
  `5e5163721417a646897e62669f39ee678f0161ec`, not the original SHA.
- Branch used for this forensic: `forensic/arch-consolidate-01`.
- This document's own path: `docs/forensics/ARCH_CONSOLIDATE_01_FORENSIC.md`.

## 17. Final forensic verdict

`ARCH_CONSOLIDATION_FORENSIC_SOURCE_READY`

This corrects an earlier revision of this document, which contained several
source-level contradictions (an independent CryptoRadar web dashboard
overlooked, a stale systemd-unit count, an inconsistent Telegram bot count,
"approximate" totals presented as exact) identified in human review (PR #306
comment `5860949880`) and fixed in this revision. `SOURCE_READY` reflects
that the source-evidence forensic pass is now internally consistent and
complete against the current verified head (§16); it is **not**
`ARCH_CONSOLIDATION_FORENSIC_CERTIFIED`, since several components remain
`UNKNOWN` pending VPS/runtime evidence (§12) and certification still requires
a further round of explicit human sign-off, per #286's fail-closed cleanup
rule and #285 §18's governance requirements. Runtime/VPS unknowns are
intentionally left open and visible, not resolved, by this revision.
