# ARCH-CONSOLIDATE-01 — Forensic des surfaces Web, APIs, Telegram, services et code legacy

**Mission**: #287 (read-only forensic). Roadmap: #285. Garde-fou burn-in: #286.
Observation runtime en cours: #282, epoch `BURN-IN-EPOCH-01-20260926T064144Z`.

**Verdict**: `ARCH_CONSOLIDATION_FORENSIC_IN_PROGRESS`

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
- **No independent CryptoRadar website exists** as a separate hosted site.
  "CryptoRadar" today is: (a) a calculation module reused by
  `scripts/radar_bot.py` (Telegram) and by
  `observability/market_radar_snapshot.py` (Operator API MARKET bridge, per
  `docs/contracts/WEB_01_MARKET_CRYPTORADAR_CONTRACT.md`). There is therefore
  no separate "site" to retire — the open item is retiring the **Telegram**
  transport (`@RadarCrypto1_bot`), not a website.
- **Four Telegram bots** are documented with clear evidence in
  `docs/observability/TELEGRAM_BOT_REGISTRY.md`: `@QuantCrpto_bot` (Quant
  Observer), `@mon_portfolio_bot` (Portfolio/Command Center), `@PaperArena_bot`,
  `@Telemetrie_IA_bot`/CMVK/Sim Bot (identity unresolved, no systemd evidence),
  and `@RadarCrypto1_bot` (CryptoRadar). A fifth reference,
  `capital_deployment/command_center_bot.py`, is the implementation behind
  `@mon_portfolio_bot`.
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
  lists 10 audited units, while `scripts/systemd/` on disk holds 15 unit/timer
  files — several units in `scripts/systemd/` (`crypto-operator-web.service`,
  `crypto-market-snapshot.service`, and the three `.timer` files) are **not**
  in the service_matrix's fixed catalog, meaning the audit pack's official
  "what runs on the VPS" list is now stale relative to the repo's own
  systemd unit definitions — a governance gap, not a code defect.
- No direct evidence of raw JSONL/DB reads from the canonical frontend or
  Operator API bypassing governed projections was found; the one documented
  bypass pattern is inside the **Telegram** layer (`scripts/radar_bot.py`
  reading `databases/decision_packets_{date}.jsonl` directly, and
  `capital_deployment/command_center_bot.py` closing over live
  advisor-loop/paper-trading in-process state) — both already flagged in the
  existing Telegram registry, not newly discovered here.

## 1bis. Answers to the 13 special questions

1. **How many distinct web surfaces exist?** Three at the code level: (1)
   the canonical Operator Web App (`frontend/`), (2) the parallel SDOS
   Terminal stack (`sdos_terminal/`), (3) the legacy Windows panel/dashboard
   layer (`dashboard/`, `infra/panels/`, root `.bat` launchers) — the last one
   already shown broken in `panel_test_report.txt`.
2. **What is the canonical web app?** The Operator Web App:
   `frontend/` (React/Vite) served by `observability/operator_api/app.py`
   (FastAPI), per #285's target architecture and `architecture/
   CANONICAL_COMPONENTS.md`.
3. **Does an independent CryptoRadar site still exist, and what would be
   needed before retiring it?** No independent CryptoRadar *website* exists
   in this repository. "CryptoRadar" is a calculation engine consumed by (a)
   `scripts/radar_bot.py` (Telegram `@RadarCrypto1_bot`) and (b)
   `observability/market_radar_snapshot.py` (Operator API MARKET bridge, per
   `docs/contracts/WEB_01_MARKET_CRYPTORADAR_CONTRACT.md`). What remains to
   retire is the **Telegram transport**, not a site; before that, the direct
   `databases/decision_packets_*.jsonl` read inside `radar_bot.py` must be
   replaced by the governed snapshot producer (Wave 5, §13).
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
   (canonical), `sdos_terminal/api/app.py` (parallel, unresolved),
   `infra/api/api_server.py` (unresolved, no consumer found),
   `visualization/api/quant_live_api.py` (data-provider module, canonical
   producer for the Quant Observer bot) — see §4.
8. **Are there competing sources for the same info?** Yes: performance/PnL
   aggregation is computed in at least three places for Sim Bot commands
   instead of one shared `performance_breakdown.breakdown()`; ENL friction
   cost is computed twice (canonical `src/execution/enl.py` vs.
   `@PaperArena_bot`'s local `_enl_fill()`); CryptoRadar symbol stats are
   independently parsed/aggregated in `radar_bot.py` rather than through a
   shared decision-packet aggregator also used elsewhere.
9. **Are there direct JSONL/DB reads from a UI/bot bypassing governed
   projections?** Yes, one confirmed case: `scripts/radar_bot.py` reads
   `databases/decision_packets_{date}.jsonl` directly for `@RadarCrypto1_bot`.
   `capital_deployment/command_center_bot.py` also bypasses the Operator API
   by closing over live in-process advisor-loop/paper-trading state rather
   than going through a governed HTTP boundary. No such bypass was found in
   the canonical `frontend/` — its only path is the Operator API.
10. **Which components look orphaned but can't yet be proven RETIRE?**
    `sdos_terminal/` (API+frontend), `infra/api/api_server.py`,
    `governance/status_dashboard.py`, `infra/dashboards/__init__.py` (empty
    stub) — all classified `UNKNOWN`, see §8/§12.
11. **Which dependencies still create an architecture parallel to
    engine→projection→Operator API→App?** (a) `sdos_terminal/` stack — its
    own API + its own frontend, sharing only the `visualization/api/`
    producer with the canonical Quant Observer edge; (b) all four active
    Telegram bots' direct producer paths (`capital_deployment/
    command_center_bot.py`'s in-process closures, `radar_bot.py`'s direct
    JSONL read, `sim_bot.py`'s own SQLite store, `quant_observer/bot.py`'s
    otherwise-canonical but Telegram-duplicated presentation of the same
    `quant_live_api.py` data already available to the App).
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
| WEB-05 | CryptoRadar "site" | *(no such directory found)* | n/a | n/a | n/a | n/a | **N/A — does not exist as a separate site** (see §1 CryptoRadar answer) | High |

## 4. API inventory

| id | Name | Path | Framework | Routes (sample) | Ports/env | Consumers | Classification | Confidence |
|---|---|---|---|---|---|---|---|---|
| API-01 | Operator API | `observability/operator_api/app.py` | FastAPI | `GET /api/operator/v1/snapshot`, `GET /api/operator/v1/market` (per `WEB_01_MARKET_CRYPTORADAR_CONTRACT.md`) | not confirmed from source alone (env var names not extracted in this pass) | `frontend/` React app; `scripts/systemd/crypto-operator-api.service`, `crypto-operator-web.service` | **KEEP** (canonical) | High |
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
cross-checked against the 15 files under `scripts/systemd/`:

| Unit | Role/tier (per audit pack) | In fixed audit catalog? | Classification | Confidence |
|---|---|---|---|---|
| `crypto-advisor.service` | decision engine / core | Yes | **KEEP** | High |
| `crypto-watchdog.service` | runtime safety / safety | Yes | **KEEP** (currently OFF per #282/#286, but the unit itself is canonical safety infra) | High |
| `crypto-dashboard.service` | web interface / interface | Yes | **UNKNOWN** — ambiguous which "dashboard" this serves (legacy panel stack vs. Operator App); needs VPS `ExecStart` evidence | Low |
| `crypto-lmi-observatory.service` | live-market observation | Yes | **KEEP** (observation-only, ADR-0007 compliant) | Medium |
| `crypto-market-horizons.service` + `.timer` | market horizons / observation | Yes (service); timer absent from catalog | **KEEP** service / **UNKNOWN** timer (undocumented in audit pack) | Medium |
| `crypto-market-observer.service` + `.timer` | market observer / observation | Yes (service); timer absent from catalog | **KEEP** service / **UNKNOWN** timer | Medium |
| `crypto-market-radar.service` + `.timer` | market radar / observation | Yes (service); timer absent from catalog | **KEEP** service / **UNKNOWN** timer | Medium |
| `crypto-market-snapshot.service` | (not in fixed catalog) | **No** | **UNKNOWN** — likely producer for `observability/market_radar_snapshot.py`, but not certified by the audit pack | Low |
| `crypto-operator-api.service` | (not in fixed catalog) | **No** | **KEEP** (matches canonical API-01, but governance doc is stale — recommend adding to catalog) | Medium |
| `crypto-operator-web.service` | (not in fixed catalog) | **No** | **KEEP** (matches canonical WEB-01 frontend, same stale-catalog note) | Medium |
| `crypto-quant-observer.service` | Telegram quant observer / interface | Yes | **INTEGRATE** (see §5) | High |
| `crypto-radar-bot.service` | Telegram radar / interface | Yes | **INTEGRATE** (see §5) | High |
| `paper-arena.service` | paper-execution interface / interface | Yes | **KEEP** (see §5) | High |

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

| Classification | Count (this forensic's component list, §3–8) | Representative items |
|---|---:|---|
| KEEP | 14 | Operator API, frontend, operator_snapshot_builder, market_radar_snapshot, `@PaperArena_bot`, `crypto-advisor.service`, `crypto-watchdog.service`, `crypto-lmi-observatory.service`, market-horizons/observer/radar `.service` units, `visualization/api/quant_live_api.py`, `src/risk/kill_switch.py`, `crypto-operator-api.service`, `crypto-operator-web.service` |
| INTEGRATE | 5 | `@QuantCrpto_bot`, `@mon_portfolio_bot`/command_center_bot, `@RadarCrypto1_bot`/radar_bot.py, CryptoRadar direct-JSONL read path, Command Center provider |
| MOVE | 0 | none identified with sufficient evidence in this pass — candidates would need VPS/runtime evidence first |
| ARCHIVE | 5 | `_ARCHIVE_2026/` tree (pre-existing), legacy `.bat`/panel launchers, regime-detector shim, legacy kill-switch variants, `_ARCHIVE_2026/telegram_bot_duplicates_20260706` |
| RETIRE | 1 | `src/telegram/exchange_sync.py` (zero imports, confirmed dead) |
| UNKNOWN | 9 | `sdos_terminal/` stack (API+frontend), `infra/api/api_server.py`, `@Telemetrie_IA_bot`/sim_bot.py, `crypto-dashboard.service`, `crypto-market-snapshot.service`, three undocumented `.timer` units, `infra/dashboards/__init__.py`, `governance/status_dashboard.py` |

Totals are approximate and reflect components with enough named evidence to
list individually in this pass; many smaller files (test files, doc files)
are evidence *for* these rows rather than separate components.

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
- **CryptoRadar direct JSONL read** (`scripts/radar_bot.py`) is a live
  precedent for bypassing governed projections specifically from a Telegram
  surface; the WEB-01 MARKET bridge was explicitly designed as one-directional
  to avoid this pattern reaching the frontend — any future consolidation must
  preserve that one-way boundary rather than generalize the bypass.
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

1. Is `sdos_terminal/` (API + frontend) actually deployed/reachable on the
   VPS today, under what unit/port, and who uses it?
2. Is `infra/api/api_server.py` deployed anywhere, and by what process
   supervises it (no systemd unit name matched it in this pass)?
3. What does `crypto-dashboard.service`'s `ExecStart` actually launch — the
   legacy panel stack, `dashboard/alert_dashboard.py` directly, or something
   else? (Blocked: audit pack intentionally excludes `ExecStart*` from safe
   properties, so this needs a separate, explicitly-scoped read.)
4. What do `crypto-market-horizons.timer`, `crypto-market-observer.timer`,
   and `crypto-market-radar.timer` actually schedule, and are their
   corresponding `.service` units' current `ActiveState` consistent with the
   audit pack's last observation?
5. Is `@Telemetrie_IA_bot` actually running under any process today, and
   under which of its two candidate BotFather identities?
6. Does `crypto-operator-api.service` / `crypto-operator-web.service` map
   1:1 to `observability/operator_api/app.py` / `frontend/`, confirming
   WEB-01/API-01 are indeed the live canonical stack and not just the
   intended one?

None of these can be resolved by a read-only repository pass; they require a
future, separately-scoped, explicitly-authorized VPS read (e.g. a
`service_matrix`-style bounded audit pack extended to cover these specific
units, or an `ExecStart`-scoped follow-up pack).

## 13. Proposed migration order (Wave 1..6 — PROPOSALS ONLY, not executed)

These are **proposals for future, separately-governed PRs**. None of them are
executed by this forensic, and each would need its own issue, branch, PR, and
pass through #286 per #285 §18.

- **Wave 1 — Low-risk retirement of proven-dead code.** Remove
  `src/telegram/exchange_sync.py` (zero confirmed imports). Lowest risk item
  in this inventory.
- **Wave 2 — Resolve unknowns before any further action.** Get VPS evidence
  for `sdos_terminal/`, `infra/api/api_server.py`, `crypto-dashboard.service`
  `ExecStart`, the three undocumented `.timer` units, and `@Telemetrie_IA_bot`
  identity/deployment. Update the `service_matrix` fixed catalog to include
  `crypto-operator-api.service`, `crypto-operator-web.service`, and
  `crypto-market-snapshot.service`.
- **Wave 3 — Integrate `@QuantCrpto_bot`.** Per the registry's own
  highest-priority recommendation: fold its metrics into the Operator App's
  System/Governance panel using the already-canonical
  `visualization/api/quant_live_api.py` producer; no new producer needed.
- **Wave 4 — Integrate `@mon_portfolio_bot` / Command Center.** Consolidate
  its two independent senders (`CommandCenterBot.send()` and
  `Notifier._send()`) into one owner; migrate its KPI surface into the
  Operator App Portfolio/Finance view, sourcing from the same
  `CommandDataProvider` data already used, not a re-derivation.
- **Wave 5 — Integrate `@RadarCrypto1_bot` / CryptoRadar transport.** Replace
  the bot's direct `databases/decision_packets_*.jsonl` read with a call into
  the existing governed `observability/market_radar_snapshot.py` producer (or
  extend that producer to serve the same fields), then retire only the
  Telegram transport, keeping the CryptoRadar calculation engine.
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
   six unknowns in §12 (Wave 2), read-only, no code change to runtime logic.
3. `ARCH-CONSOLIDATE-01c` — Update `docs/runbooks/SERVICE_MATRIX_AUDIT_PACK.md`
   fixed catalog to include the three currently-undocumented `.service` units
   and three `.timer` units (Wave 2, documentation-only).
4. `ARCH-CONSOLIDATE-01d` — Integrate `@QuantCrpto_bot` metrics into the
   Operator App (Wave 3), Telegram bot left running until App parity is
   proven, then a separate follow-up PR retires the bot transport.
5. `ARCH-CONSOLIDATE-01e` — Consolidate `@mon_portfolio_bot` senders and
   migrate its KPI surface into the Operator App (Wave 4).
6. `ARCH-CONSOLIDATE-01f` — Replace `scripts/radar_bot.py`'s direct JSONL
   read with the governed `market_radar_snapshot.py` producer, then retire
   the Telegram transport only (Wave 5).
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

- Verified real HEAD of `main` at the time of this forensic (via
  `origin/main`): `4016725058ba399eab470ee96b076fe7c2bbfebd` — this matches
  the baseline SHA named in the mission brief, so no baseline drift occurred;
  this SHA was independently re-verified rather than assumed.
- Branch used for this forensic: `forensic/arch-consolidate-01`.
- This document's own path: `docs/forensics/ARCH_CONSOLIDATE_01_FORENSIC.md`.

## 17. Final forensic verdict

`ARCH_CONSOLIDATION_FORENSIC_IN_PROGRESS`

This is intentionally **not** `ARCH_CONSOLIDATION_FORENSIC_CERTIFIED`. Several
components remain `UNKNOWN` pending VPS/runtime evidence (§12), and
certification requires explicit human review of this document plus resolution
of those unknowns, per #286's fail-closed cleanup rule and #285 §18's
governance requirements.
