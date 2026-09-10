# Telegram Observation Boundary & Safe Cutover Contract

Mission O-02W-E1 · Base SHA `17a2f70537ee48f70500974dddf5f0458c02cc50` ·
2026-09-10 · Documentation-only mission (no runtime code changes, no
Telegram sender/poller/token/chat/command changed, no VPS access, no
deployment, no cockpit controls added).

Final certification of this contract belongs exclusively to the
independent ChatGPT MASTER reviewer. This document is a proposal for
that review, not a self-certified conclusion.

---

## 0. Scope and non-goals

This contract governs the future relationship between the existing
Telegram bot ecosystem and the new read-only web cockpit
(`observability/operator_snapshot_builder.py`,
`observability/operator_api/app.py`, `frontend/src/App.tsx`), produced
by missions O-02W-C/D1/D2/D3 and merged in
[PR #129](https://github.com/3a7i3/crypto-ia-terminal/pull/129) at
`17a2f70537ee48f70500974dddf5f0458c02cc50`.

It is **not** a Telegram deletion mission, **not** a VPS audit, and
**not** the cockpit deployment mission. No Telegram sender, poller,
token, chat, command, or service was changed to produce this document.
The cockpit itself remains observation-only and this mission adds no
control surface to it (§8, §11).

### Evidence classes used throughout

| Class | Meaning |
|---|---|
| `SOURCE_PROVEN` | Verified directly against source at this commit (file:line cited). |
| `DOCUMENTED_BUT_NOT_SOURCE_PROVEN` | Asserted by an existing doc, not independently re-verified here. |
| `RUNTIME_UNKNOWN` | Code exists; whether it is currently running/deployed on the VPS cannot be determined without VPS access, which this mission does not have. |
| `DEAD_CODE_SOURCE_PROVEN` | Code exists but is verifiably unreachable from any active entrypoint (no import chain, no systemd unit, no scheduler reference). |
| `OPERATOR_DECISION_REQUIRED` | A human judgment call this document cannot resolve on its own. |

Repository presence never proves deployment. A systemd unit file never
proves a service is currently running. An environment-variable name
never proves a token is configured. A sender function never proves a
message is currently delivered. No claim in this document asserts any
bot is live on the VPS — that would require VPS inspection, which is
out of scope for O-02W-E1.

---

## 1. Reconciliation with existing documents

This contract builds directly on, and does not replace, the existing
Telegram documentation set. Their identity/bot inventories were
independently re-verified against source at the current commit
(`17a2f70537ee48f70500974dddf5f0458c02cc50`) rather than trusted
as-is. Findings:

- **`docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md`** (2026-08-28) —
  the most complete and current single source. Every identity claim
  checked (IDENTITY-01 through IDENTITY-10) is still accurate at this
  commit. One drift: its absolute line-number citations for
  `core/advisor_loop.py`'s Real Account Bot / `_telegram_real` (cited
  as `796-797, 1009-1027, 3483, 3495, 3516, 7233`) have shifted — the
  code now lives at lines `965-974` (constants) and `1186-1205`
  (`_telegram_real`). The code moved; it did not disappear or change
  behavior. `DOCUMENTED_BUT_NOT_SOURCE_PROVEN` → now `SOURCE_PROVEN`
  at corrected line numbers, this document's §9.
- **`docs/architecture/TELEGRAM_BOT_REGISTRY.md`** (v2.0, 2026-08-28) —
  the 5 active bots it documents (CryptoRadar, Portfolio, Quant
  Observer, Rapport Automatique, Paper Arena) match current source
  exactly. Its own "Governance Gap" appendix already flagged the
  undocumented `REAL_ACCOUNT_BOT_TOKEN` merge; that merge is confirmed
  **complete** at this commit (`SOURCE_PROVEN`: no `REAL_ACCOUNT_BOT_TOKEN`
  reference remains anywhere in source or `.env.secrets.example`).
- **`docs/TELEGRAM_CONSTITUTION.md`** (v1.0, 2026-08-28) — Principle 5
  ("Telegram Cannot Silently Control the Machine") and Principle 3
  ("No Cross-Identity Token Fallback") both match current code exactly
  (`SOURCE_PROVEN`, §9/§13 below).
- **`docs/TELEGRAM_BOT_CONSTITUTION.md`** (2026-08-28) — command lists
  for the 5 active bots match current code. Its Bot 6 (Sim Bot) section
  frames KEEP-and-deploy vs. REMOVE as an open decision; still open at
  this commit — no systemd unit or `.env.example` entry has been added
  for it since. Carried forward as `OPERATOR_DECISION_REQUIRED` (§9,
  Sim Bot row).
- **`docs/TELEGRAM_ARCHITECTURE_AUDIT.md`** — explicitly superseded on
  identity questions by `TELEGRAM_IDENTITY_REGISTRY.md` per its own
  header. One passage (describing a `RADAR_BOT_TOKEN` → `TELEGRAM_BOT_TOKEN`
  fallback as "currently present, ÉLEVÉ risk") is stale: current
  `scripts/radar_bot.py:21-22` has no such fallback. This staleness is
  already known and explained by `TELEGRAM_IDENTITY_REGISTRY.md`'s own
  before/after note, so it is not a new finding, only reconfirmed.
- **`docs/TELEGRAM_NOTIFICATION_AUDIT.md`** — its Real Account Bot
  governance-gap finding is now resolved by the same merge noted above.
- **`docs/architecture/TELEGRAM_ECOSYSTEM_MAP.md`** — covers 8 of the
  10 historically-identified token groups; does not cover the (now
  merged/moot) Real Account identity or the (dead) Narrator identity.
  No correction needed, just a coverage note.
- **`docs/SYSTEM_DEGRADATION_POLICY.md`** §3.4 — its Telegram-alert
  rules (`CRITICAL → immediate alert`, `SAFE_MODE → critical alert +
  email`) map to the generic `TELEGRAM_BOT_TOKEN` push-only channel and
  are consistent with current code. No interactive/control claim is
  made there, so no contradiction.
- **`docs/GLOBAL_STATE_MACHINE.md`** — two passages need correction,
  flagged here as new findings from this mission:
  - Line ~30/35 attributes `NORMAL ↔ SAFE_MODE` transitions to
    `"commande manuelle | KillSwitch / Telegram"`. `SOURCE_PROVEN`
    contradiction: the only live transition mechanism is
    `KillSwitchHardened.force_safe_mode()` / `.force_resume()`
    (`supervision/killswitch_hardened.py`, bound as
    `TelegramKillSwitch` via `core/advisor_runtime_adapters.py:109`),
    called **programmatically only**. No Telegram command handler
    calls either method anywhere in source (§9, KillSwitch row). This
    document does not edit `GLOBAL_STATE_MACHINE.md` (out of scope,
    §12), but records the contradiction as required by §13.
  - Line ~124 (`HALTED → Telegram (à câbler)`) already self-flags as
    "to be wired," i.e. aspirational, not a current-state claim — no
    contradiction, just noted for completeness.
- **`docs/contracts/O-02W-B_CANONICAL_OPERATOR_API_CONTRACT.md`** — the
  direct predecessor contract. §16 (`SECURITY_READ_ONLY_CONTRACT`)
  already states the operator API must never trigger Telegram
  send/edit/delete. §21.2 explicitly names a future "O-02W-E" mission
  for "Telegram notification/retirement work" — this document is that
  mission's first deliverable (O-02W-E1). §12
  (`MARKET_API_CONTRACT`) establishes that CryptoRadar and the
  pre-existing `scripts/dashboard_api.py` are both constitutionally
  observational-only and never feed `analyze_symbol()` — the same
  non-feedback boundary this contract extends to every other Telegram
  identity in §9.

No document reviewed makes a claim about current source that this
mission's independent re-verification found false, other than the
staleness items listed above (all already narrow, already
self-acknowledged by the identity registry, or newly noted here for
`GLOBAL_STATE_MACHINE.md` and one stale operator-instruction string in
`supervision/exchange_monitor.py:255`, §9).

---

## 2. Governing constitutional constraints (unchanged by this mission)

- **ADR-0007 (absolute observer passivity):** every component other
  than the decision engine — including every Telegram bot and the
  cockpit — may observe, record, explain, and recommend, but never
  influence a real-time trading decision. This contract does not
  change that; it only maps *which surface currently duplicates which
  observation*.
- **Scientific Debt Rule (architectural freeze):** this mission adds
  zero new indicators, strategies, decision rules, or threshold
  changes. It is a measurement/audit artifact, permitted under the
  current phase.
- **Stabilization Lab window** (`2026-09-02` → `2026-09-16`,
  `docs/governance/STABILIZATION_WINDOW_2026-09-03_2026-09-16.md`):
  this mission proposes no VPS deployment or restart and does not
  affect burn-in certification status.

---

## 3. Required message classification (definitions)

Every Telegram call site or message family in §9 is classified into
exactly one of:

- `CRITICAL_SAFETY_ALERT` — reports a real safety-relevant state
  transition (exchange down/up, session halt, crash, degradation).
- `STATE_CHANGE_ALERT` — reports a real mode/phase/config transition
  that is not itself a safety emergency (STANDBY↔LIVE, probation).
- `PERIODIC_STATUS_SUMMARY` — scheduled recurring report, no
  transition implied (heartbeat, daily/periodic summary).
- `RESEARCH_EXPERIMENT_REPORT` — reports simulation/backtest/paper
  results, not live account state.
- `ON_DEMAND_READ_ONLY_QUERY` — served only in response to an
  operator-issued command, never pushed unsolicited.
- `ROUTINE_TELEMETRY_DUPLICATED_BY_COCKPIT` — status data now also
  computable from the cockpit's read-only snapshot.
- `FORBIDDEN_CONTROL_SURFACE` — a command that would mutate trading,
  execution, configuration, or service state.
- `DEAD_OR_UNREACHABLE_CODE` — implemented but not reachable from any
  active entrypoint at this commit.
- `UNCLASSIFIED_REQUIRES_DECISION` — evidence insufficient for the
  above; an operator call is needed.

## 4. Required cutover classification (definitions)

- `KEEP_PERMANENT_CRITICAL_ALERT`
- `KEEP_RESEARCH_INTERFACE`
- `KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED`
- `RETIRE_AFTER_CERTIFIED_CUTOVER`
- `DEAD_CODE_REMOVAL_CANDIDATE`
- `OPERATOR_DECISION_REQUIRED`
- `FORBIDDEN_MUST_NEVER_REACTIVATE`

Per the mission mandate: duplication by cockpit *source code* alone
never justifies `RETIRE_AFTER_CERTIFIED_CUTOVER` today — the cockpit is
not yet deployed or runtime-certified (§7, Phase 0). That transition
state is reserved for flows that will become eligible **once** the
Phase 3 criteria in §11 are met; nothing is retired by this document.

---

## 5. Protected decisions (restated, unchanged)

- **CryptoRadar** (`scripts/radar_bot.py`, `@RadarCrypto1_bot`): not
  modified by this mission, and not proposed for automatic retirement
  merely because the cockpit exists. Its unique on-demand
  market-scanning value (`/scan /top50 /longs /shorts /symbol /lmi`)
  is classified separately from any cockpit-duplicated status
  telemetry in §9/§10 — it carries no overlap with the cockpit's
  portfolio/decision/system domains and is classified
  `KEEP_RESEARCH_INTERFACE`.
- **Cockpit**: remains observation-only. This document proposes no
  buttons, controls, parameter changes, start/stop/restart actions,
  order controls, or Telegram control proxy of any kind. Confirmed by
  source inspection (§8): `observability/operator_api/app.py` exposes
  only `GET` routes (`/healthz`, `/api/operator/v1/snapshot`,
  `/portfolio`, `/decision-pipeline`, `/system-health`) — zero
  `@app.post/@app.put/@app.delete` anywhere under
  `observability/operator_api/`.
- **Real portfolio observations**: read-only real-account values may
  be displayed by both cockpit and Telegram, but remain observational
  only per ADR-0007 — never feeding signals, indicators, strategies,
  risk decisions, execution authorization, or paper-equity
  calculations. No source evidence found of any violation of this at
  the current commit.

---

## 6. Consistency search results (summary)

Full repository greps were run for every literal listed in the O-02W-E1
mandate (`api.telegram.org`, `sendMessage`, `sendPhoto`, `editMessage`,
`getUpdates`, `deleteWebhook`, `_BOT_TOKEN`, `_CHAT_ID`,
`TELEGRAM_BOT_TOKEN`, `MON_PORTFOLIO_BOT_TOKEN`, `QUANT_CRYPTO_BOT_TOKEN`,
`TELEMETRIE_IA_BOT_TOKEN`, `RADAR_BOT_TOKEN`, `KILLSWITCH`, `/resume`,
`/kill`, `/restart`, `/set`, `/pause`, `/STOP_ALL`, `/CLOSE_ALL`,
`/SAFE_MODE`). Every hit was reviewed in context (not classified by
grep count alone). Headline findings:

- `getUpdates` (polling) appears in exactly 5 files: `scripts/radar_bot.py`,
  `capital_deployment/command_center_bot.py`,
  `src/telegram/quant_observer/bot.py`, `src/telegram/bot_runner.py`
  (Sim Bot), and the dead `supervision/kill_switch.py`. No other file
  polls Telegram.
- `deleteWebhook` appears only in `src/telegram/bot_runner.py`
  (409-conflict recovery) — irrelevant to any other identity.
- `sendPhoto`/`editMessage` are concentrated almost entirely in
  `src/telegram/quant_observer/bot.py` (pinned-panel live refresh) —
  no other bot edits or sends photos.
- `/STOP_ALL`, `/CLOSE_ALL`, `/SAFE_MODE` occur only inside: (a) the
  dead `supervision/kill_switch.py` implementation, (b) docstrings in
  `supervision/killswitch_hardened.py` stating these commands were
  "retirées" (removed), (c) one **stale** operator-facing email string
  in `supervision/exchange_monitor.py:255` instructing the operator to
  "send `/STOP_ALL` on Telegram" — this instruction is currently
  non-actionable, since no live poller implements that command
  against a real token (§9, Generic Alerts row; correction recorded,
  file not edited — out of mission scope), (d) tests asserting these
  are now rejected.
- `/resume`, `/kill`, `/restart`, `/set`, `/pause` hits outside
  Telegram code are unrelated non-Telegram Python syntax
  (`config/settings.py`, `risk/circuit_breaker.py`) or
  `capital_deployment/command_center_bot.py`'s explicit blocked-command
  set, which returns a fixed refusal string and never calls
  `CommandDataProvider.set_param` or any mutator.
- No `.py` file outside `supervision/kill_switch.py` implements a live
  dispatcher for any of the eight command-mutation literals against a
  real token. `supervision/kill_switch.py` itself is confirmed
  unreachable (§9).
- No `KILLSWITCH_BOT_TOKEN` / `KILLSWITCH_CHAT_ID` environment variable
  is read anywhere in source — the `KILLSWITCH` grep hits are entirely
  prose/class-name occurrences in docs and code comments.

---

## 7. Cockpit deployment status (current)

- **Cockpit deployment: not performed.** No systemd unit, deploy
  script invocation, or VPS reference for
  `observability/operator_api` or `frontend/` was found in this
  mission's source-only review. `RUNTIME_UNKNOWN` in the strict sense
  (VPS inspection is out of scope), but no `SOURCE_PROVEN` evidence of
  deployment exists either — consistent with O-02W-D3 having only
  landed a cross-stack **compatibility gate**, not a deployment.
- **T-1 (deployment mission): not started.** No branch, workflow run
  reference, or deployment artifact found.
- **F-00: not started.** No related branch or document found in this
  review.
- Both confirmed per the mission's mandatory preflight (§ Preflight,
  below the title block of this repository's mission instructions).

---

## 8. Cockpit read-only surface (for §10 overlap comparison)

`observability/operator_api/app.py` exposes exactly these routes, all
`GET`:

| Route | Domain(s) served |
|---|---|
| `GET /healthz` | liveness of the API process itself |
| `GET /api/operator/v1/snapshot` | full composite snapshot (all domains) |
| `GET /api/operator/v1/portfolio` | portfolio domain |
| `GET /api/operator/v1/decision-pipeline` | decision domain |
| `GET /api/operator/v1/system-health` | system domain |

`observability/operator_snapshot_builder.py` composes these via
`_build_portfolio_domain`, `_build_decision_domain`,
`_build_system_health_domain`, each carrying explicit
`domain_available` / `FreshnessStatus` / `UNKNOWN` fields — a
fail-closed design that never silently presents stale or unavailable
data as current.

`frontend/src/App.tsx` renders six tabs from a single
`useOperatorSnapshot()` hook: `overview, portfolio, decisions, system,
market, scores`. No `market` or `scores` domain is currently served by
`operator_api/app.py`'s enumerated routes above at this commit — those
tabs' data source was not further traced in this mission (out of
scope); this contract's §10 overlap matrix restricts itself to the
domains actually confirmed served: **portfolio, decisions, system**,
plus **overview** as the composite view of `snapshot`.

No `@app.post`, `@app.put`, or `@app.delete` exists anywhere under
`observability/operator_api/` — confirmed read-only by construction,
matching §16 of the O-02W-B contract.

---

## 9. Identity matrix

Line numbers below are re-verified at commit
`17a2f70537ee48f70500974dddf5f0458c02cc50` (not copied from older docs
without re-check).

| Identity ID | Human/bot name | Token var | Chat var | Entrypoint | Process owner | Interaction model | Domain | Message category | Cockpit overlap | Runtime evidence | Transition state | Cutover prerequisite | Later mission |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TG-01 | CryptoRadar (`@RadarCrypto1_bot`) | `RADAR_BOT_TOKEN` | `RADAR_CHAT_ID` | `scripts/radar_bot.py` | `crypto-radar-bot.service` (independent) | BOTH (poll `getUpdates` + push) | MARKET | ON_DEMAND_READ_ONLY_QUERY | NONE | SOURCE_PROVEN (code); RUNTIME_UNKNOWN (VPS) | KEEP_RESEARCH_INTERFACE | n/a — protected, §5 | none |
| TG-02 | Portfolio / CommandCenter (`@mon_portfolio_bot`) | `MON_PORTFOLIO_BOT_TOKEN` | `MON_PORTFOLIO_CHAT_ID` (falls back to `TELEGRAM_CHAT_ID`) | `capital_deployment/command_center_bot.py`, instantiated by `core/advisor_loop.py:3991-3992` | `crypto-advisor.service` (in-process) | BOTH | PORTFOLIO | mixed: read commands = ON_DEMAND_READ_ONLY_QUERY; periodic auto-report (`_report_loop`) = PERIODIC_STATUS_SUMMARY; 9 blocked commands = FORBIDDEN_CONTROL_SURFACE (inert, see below) | PARTIAL (status/positions/pnl fields overlap cockpit `portfolio` domain; on-demand query semantics do not) | SOURCE_PROVEN | KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED (for the overlapping status commands); KEEP_PERMANENT_CRITICAL_ALERT n/a here (no critical alert in this bot) | T-1 deployment + Phase 2 parallel-observation window (§11) | E2 |
| TG-03 | Quant Observer (`@QuantCrpto_bot`) | `QUANT_CRYPTO_BOT_TOKEN` | `QUANT_CRYPTO_CHAT_ID` | `src/telegram/quant_observer/bot.py` | `crypto-quant-observer.service` (independent) | BOTH | DECISION (research) | mixed: `/snapshot /health /pipeline` = ON_DEMAND_READ_ONLY_QUERY; pinned-panel auto-refresh = PERIODIC_STATUS_SUMMARY; `/portfolio` = explicit redirect stub, `raise NotImplementedError` in `_render_portfolio` (323-331), not a live handler | PARTIAL (pipeline/health data overlaps cockpit `decisions`/`system`; pinned live-refresh UX does not) | SOURCE_PROVEN | KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED | T-1 + Phase 2 | E2 |
| TG-04 | Rapport Automatique / Intel | `RAPPORT_AUTOMATIQUE_BOT_TOKEN` | `RAPPORT_AUTOMATIQUE_CHAT_ID` | `core/advisor_loop.py::_send_intel` (1208-1232) | `crypto-advisor.service` (in-process) | PUSH_ONLY | SYSTEM (AI-generated periodic briefing) | PERIODIC_STATUS_SUMMARY | UNKNOWN — briefing content is AI-synthesized narrative, not a direct field mirror of any cockpit domain; no direct comparison performed in this mission | SOURCE_PROVEN | OPERATOR_DECISION_REQUIRED | operator must decide whether narrative-briefing value is replaced by cockpit or is unique | operator decision / E2 |
| TG-05 | Paper Arena | `PAPER_ARENA_BOT_TOKEN` | `PAPER_ARENA_CHAT_ID` | `src/paper/paper_runner.py`, `src/paper/paper_report.py` | `paper-arena.service` (independent) | PUSH_ONLY | EXPERIMENT | RESEARCH_EXPERIMENT_REPORT | NONE (cockpit serves live/paper-engine domains, not the separate paper-arena experiment) | SOURCE_PROVEN | KEEP_RESEARCH_INTERFACE | n/a | none |
| TG-06 | Generic / Engine Alerts | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_BEHAVIOR_CHAT_ID` | same | `core/advisor_loop.py` (`_telegram`, `_telegram_behavior`), `scripts/telegram_alerts.py`, `supervision/performance_watchdog.py`, `supervision/exchange_monitor.py`, `watchdog_vps.py` | `crypto-advisor.service` + independent scripts | PUSH_ONLY (highest call-site count, ~15+ sites) | SYSTEM (mixed: exchange degradation, halt/resume, crash, heartbeat, daily reports) | mixed: exchange down/up, halt/resume, crash = CRITICAL_SAFETY_ALERT; heartbeat/daily report = PERIODIC_STATUS_SUMMARY; some fields (e.g. daily-style report content) = ROUTINE_TELEMETRY_DUPLICATED_BY_COCKPIT candidates | PARTIAL (system-health/halt-state fields overlap cockpit `system` domain; the alert *push* itself has no cockpit equivalent — cockpit is pull-only) | SOURCE_PROVEN | KEEP_PERMANENT_CRITICAL_ALERT for safety-transition messages; KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED for the periodic/status subset | Phase 2 comparison must isolate which sub-messages are pure status vs. genuine safety transitions before any subset moves to RETIRE_AFTER_CERTIFIED_CUTOVER | operator decision (message-family split) / E2 |
| TG-07 | Real Account Bot (merged into TG-02) | — (uses `MON_PORTFOLIO_BOT_TOKEN`/`_CHAT_ID`) | same as TG-02 | `core/advisor_loop.py::_telegram_real` (1186-1205) | `crypto-advisor.service` (in-process) | PUSH_ONLY (shares TG-02's token; TG-02 remains the sole poller for that token) | PORTFOLIO (real-account sub-channel) | STATE_CHANGE_ALERT (STANDBY↔LIVE transitions) | PARTIAL — cockpit portfolio domain may carry live/real-account fields; not independently confirmed field-by-field in this mission | SOURCE_PROVEN (merge complete: no `REAL_ACCOUNT_BOT_TOKEN` reference remains anywhere in source, confirmed §6) | KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED | T-1 + Phase 2, plus explicit confirmation that cockpit portfolio domain surfaces real-account state at the same fidelity | operator decision / E2 |
| TG-08 | CMVK / Sim Bot | `TELEMETRIE_IA_BOT_TOKEN` | `TELEMETRIE_IA_CHAT_ID` | `src/telegram/bot_runner.py`, `src/telegram/sim_bot.py` | none — no systemd unit references this file; not called from `advisor_loop.py` or `paper_runner.py`; not in `.env.example` | BOTH (code fully implements polling+push if run manually) | EXPERIMENT (simulation/backtest inspection) | ON_DEMAND_READ_ONLY_QUERY (all ~18 commands read-only; former `/kill`/`/resume` control commands confirmed removed — docstring states "no control commands permitted", `tests/test_sim_bot.py` asserts rejection) | NONE (simulation-core inspection has no cockpit equivalent) | RUNTIME_UNKNOWN — code SOURCE_PROVEN, but no deployment entrypoint exists at this commit | OPERATOR_DECISION_REQUIRED (KEEP_RESEARCH_INTERFACE-and-deploy vs. DEAD_CODE_REMOVAL_CANDIDATE) | operator must decide deploy-or-remove; §TELEGRAM_BOT_CONSTITUTION.md Bot 6 section frames the same open question | operator decision |
| TG-09 | KillSwitch (legacy `supervision/kill_switch.py::TelegramKillSwitch`) | `KILLSWITCH_BOT_TOKEN`/`_CHAT_ID` — name only, **never read via `os.getenv` anywhere in source** | same | `supervision/kill_switch.py` | none — `core/advisor_loop.py` actually instantiates `KillSwitchHardened` (via `core/advisor_runtime_adapters.py:109` alias `TelegramKillSwitch = KillSwitchHardened`), which contains zero Telegram code | code implements BOTH (poll+push) but is never instantiated with a real token by any active caller | n/a | FORBIDDEN_CONTROL_SURFACE (would implement `/STOP_ALL /CLOSE_ALL /SAFE_MODE /RESUME /STATUS`, mutating `BotMode` and calling `_close_all_positions()`, if ever live) | n/a | DEAD_CODE_SOURCE_PROVEN | FORBIDDEN_MUST_NEVER_REACTIVATE | none — must never be wired to a real token; ADR-0007 forbids any observer-layer component from holding execution authority | none (constitutional prohibition, not a retirement candidate — it was never live) |
| TG-10 | Narrator | `NARRATOR_BOT_TOKEN`/`_CHAT_ID` — commented out, `.env.secrets.example:92-93` only | same | none — no module exists | none | NONE | n/a | DEAD_OR_UNREACHABLE_CODE | n/a | DEAD_CODE_SOURCE_PROVEN | DEAD_CODE_REMOVAL_CANDIDATE | none — nothing to remove beyond two commented-out env lines; cleanup is cosmetic and out of this mission's scope | dead-code hygiene (non-urgent, E2 or later) |
| TG-11 | Internal-only kill switch (`supervision/telegram_kill_switch.py`, name-collides with TG-09's class name but is a distinct, separate implementation) | none — docstring states Telegram polling was removed | none | `supervision/telegram_kill_switch.py` | referenced only by two `tests/phase0/` files and `tools/runtime_tracer.py`; **not imported by `core/advisor_loop.py`** | NONE (zero Telegram code; only a programmatic `force_halt()/force_resume()` API) | n/a | n/a (not a Telegram surface at all despite the class name) | n/a | SOURCE_PROVEN | DEAD_CODE_REMOVAL_CANDIDATE — appears superseded by `supervision/killswitch_hardened.py` | none — confirm superseded status before any removal | operator decision (low priority) |

**Total identities: 7 active-in-source token groups (TG-01 through
TG-06, TG-08) + 1 merged (TG-07 → TG-02's token) + 2 confirmed
dead-code-only (TG-09, TG-10) + 1 non-Telegram internal component
sharing a class name (TG-11) = 11 rows, consistent with the 10
token-groups the identity registry previously enumerated plus the
TG-11 disambiguation this mission adds.**

**Total distinct sender/poller call sites found:** 38 `api.telegram.org`
literal call sites across all identities (§6); of these, `getUpdates`
(polling) exists in exactly 5 files (TG-01, TG-02, TG-03, TG-08, and
the dead TG-09).

---

## 10. Cockpit-overlap matrix

Restricted to the cockpit domains confirmed served by
`observability/operator_api/app.py` at this commit: **overview,
portfolio, decisions, system** (§8). No claim of equivalence is made
where Telegram computes data independently or from a different source
than the snapshot builder — every row below is explicitly qualified.

| Cockpit domain | Duplicated Telegram source | Canonical cockpit field | Replacement exactness | Telegram unique alerting value? | Requires T-1? | Requires observed stable runtime window? |
|---|---|---|---|---|---|---|
| Overview | TG-06 heartbeat/daily-style reports (`core/advisor_loop.py:8162, 7669`) | `GET /api/operator/v1/snapshot` composite | PARTIAL — snapshot is pull-only; Telegram push reaches the operator without them opening the cockpit. Field-level content not verified line-by-line against the snapshot schema in this mission. | YES — push notification itself, independent of field content | YES | YES (Phase 2) |
| Portfolio | TG-02 `/status /kpis /balance /positions /pnl` on-demand queries; TG-02 periodic `_report_loop` | `GET /api/operator/v1/portfolio` | PARTIAL — likely field overlap for balance/positions/pnl, not independently confirmed field-by-field; cockpit is pull, Telegram is both pull (commands) and push (periodic report) | YES for the periodic push; NO added value for the on-demand query subset once cockpit is trusted | YES | YES (Phase 2) |
| Portfolio (real-account sub-channel) | TG-07 STANDBY/LIVE transition pushes | `GET /api/operator/v1/portfolio` (if it surfaces a real/paper distinction — not confirmed in this mission) | UNKNOWN — cockpit's real-account field coverage not independently verified | YES — STANDBY↔LIVE is a state-change alert, arguably `STATE_CHANGE_ALERT` not pure duplication | YES | YES, plus explicit field-parity confirmation (§9 TG-07) |
| Decisions | TG-03 `/snapshot /health /pipeline` on-demand queries; TG-03 pinned-panel periodic refresh | `GET /api/operator/v1/decision-pipeline` | PARTIAL — pipeline/health concepts likely overlap; pinned-message live-refresh UX (edit-in-place) has no cockpit equivalent (cockpit requires an active pull) | YES — the pinned auto-refresh UX itself, and any photo/chart delivery (`sendPhoto`, unique to TG-03) | YES | YES (Phase 2) |
| System | TG-06 exchange degradation/recovery, session halt/resume, crash alerts (`supervision/exchange_monitor.py`, `supervision/performance_watchdog.py`, `core/advisor_loop.py`) | `GET /api/operator/v1/system-health` | PARTIAL — likely status overlap; the *push* nature of a CRITICAL_SAFETY_ALERT has no cockpit equivalent by design (cockpit is pull-only) | YES, decisively — this is exactly the class of message §11/§9 marks `KEEP_PERMANENT_CRITICAL_ALERT` | NO — critical alerts must never wait on cockpit cutover | N/A — never retired |
| System | TG-04 Rapport Automatique AI-synthesized briefing | none confirmed — narrative content, not a direct field mirror | NONE / UNKNOWN | LIKELY YES — synthesized narrative is not a raw-field duplicate | UNKNOWN | operator decision (§9 TG-04) |
| — | TG-01 CryptoRadar (`/scan /top50 /longs /shorts /symbol /lmi`) | none — cockpit has no `market` scanning route confirmed in §8 | NONE | YES — protected, §5 | N/A | N/A |
| — | TG-05 Paper Arena | none — separate experiment track, not part of the live-engine cockpit domains | NONE | YES | N/A | N/A |
| — | TG-08 Sim Bot | none — simulation-core inspection has no cockpit equivalent | NONE | YES, if deployed | N/A | N/A |

No row above is asserted as `FULL` equivalence. The strongest claim
made anywhere in this matrix is `PARTIAL`, pending the Phase 2
side-by-side comparison defined in §11.

---

## 11. Safe cutover protocol (defined, not executed)

### Phase 0 — Current source-only state (this document's position)

- Cockpit source exists (`observability/operator_snapshot_builder.py`,
  `observability/operator_api/app.py`, `frontend/src/App.tsx`), merged
  at `17a2f70537ee48f70500974dddf5f0458c02cc50`.
- Telegram remains entirely unchanged by this mission.
- No runtime equivalence is claimed anywhere in this document — every
  overlap in §10 is `PARTIAL` or `UNKNOWN`, never `FULL`.

### Phase 1 — T-1 deployment

- Deploy snapshot producer, operator API, and cockpit under governed
  services (systemd units, per the repository's existing deployment
  conventions in `scripts/deploy_vps.sh`).
- Establish runtime identity and deployment evidence (a deployed-SHA
  record, post-restart verification — per this repository's existing
  `docs/operations/PRE_RESTART_RUNTIME_CONTRACT.md` conventions).
- **No Telegram retirement at this phase.** Every identity in §9
  continues operating exactly as today.

### Phase 2 — Parallel observation

- Cockpit and existing Telegram reporting run concurrently.
- For each `PARTIAL` row in §10, compare displayed facts from
  equivalent timestamps and sources; record mismatches in a dedicated
  observation log (mechanism to be defined by the T-1/E2 mission, not
  this one).
- Critical alerts (TG-06's safety-transition subset, `CRITICAL_SAFETY_ALERT`
  rows) remain enabled throughout, unconditionally.
- Minimum duration and mismatch-tolerance thresholds are not set by
  this document — they are an `OPERATOR_DECISION_REQUIRED` item for
  whoever executes Phase 2.

### Phase 3 — Retirement eligibility

A duplicated Telegram flow (i.e., any row in §9/§10 currently marked
`KEEP_UNTIL_COCKPIT_RUNTIME_CERTIFIED`) becomes eligible for
`RETIRE_AFTER_CERTIFIED_CUTOVER` only if **all** of the following hold:

1. Cockpit source is canonical (already true, Phase 0).
2. Runtime identity is verified (Phase 1 deliverable).
3. API/cockpit availability is demonstrated over the Phase 2 window.
4. No unexplained value divergence remains between the Telegram
   message and the cockpit field it would replace.
5. The operator explicitly approves retirement, flow by flow.
6. Rollback instructions exist for that specific flow.

`CRITICAL_SAFETY_ALERT` rows (§9 TG-06 safety subset) are **never**
eligible for this phase — they remain `KEEP_PERMANENT_CRITICAL_ALERT`
regardless of cockpit maturity, because a push-capable alert has no
pull-only cockpit equivalent by construction.

### Phase 4 — O-02W-E2 implementation (future mission, not this one)

- Disable or remove only the specific duplicated flows the operator
  approved in Phase 3.
- Preserve every `KEEP_PERMANENT_CRITICAL_ALERT` and
  `KEEP_RESEARCH_INTERFACE` row unconditionally.
- Never modify execution authority (ADR-0007 remains absolute).
- One bot/message family per reversible change — no batch retirement.

---

## 12. What this mission did not do

- Did not modify `scripts/radar_bot.py`, any other Telegram sender or
  poller, any `.env*` file, or any systemd unit.
- Did not deploy the cockpit, start T-1, or start O-02W-E2.
- Did not add any control, mutation route, or Telegram-control proxy
  to the cockpit.
- Did not read or print any real secret value — `.env.example` and
  `.env.secrets.example` were inspected for variable names and
  comments only; all values in `.env.secrets.example` at this commit
  are empty placeholders.
- Did not touch the VPS.
- Did not edit `docs/GLOBAL_STATE_MACHINE.md` or
  `supervision/exchange_monitor.py`, despite the two staleness items
  identified in §1/§6 — those corrections are recorded here as
  findings for a future documentation-hygiene mission, consistent with
  the mandate to keep this PR to one new contract document plus, at
  most, a short pointer in an existing index.

---

## 13. Contradictions discovered between current source and historical documentation

1. `docs/GLOBAL_STATE_MACHINE.md` (~line 30/35) attributes
   `NORMAL ↔ SAFE_MODE` transitions partly to "KillSwitch / Telegram."
   Current source shows these transitions are exclusively programmatic
   (`KillSwitchHardened.force_safe_mode()`/`.force_resume()`), never
   Telegram-triggered. Not corrected in this mission (out of scope);
   recorded for a future fix.
2. `supervision/exchange_monitor.py:255` tells the operator (via an
   email escalation body) to send `/STOP_ALL` on Telegram. No live
   Telegram poller implements that command against a real token — the
   only implementation (`supervision/kill_switch.py`) is dead code
   (TG-09). The instruction is currently non-actionable as written.
   Not corrected in this mission; recorded for a future fix.
3. `docs/TELEGRAM_ARCHITECTURE_AUDIT.md`'s description of an "ÉLEVÉ"
   risk `RADAR_BOT_TOKEN` → `TELEGRAM_BOT_TOKEN` fallback is stale
   (current `scripts/radar_bot.py` has no such fallback) — but this is
   already self-acknowledged by `TELEGRAM_IDENTITY_REGISTRY.md`'s own
   before/after note, so it is a reconfirmation, not a new
   contradiction.
4. `docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md`'s absolute
   line-number citations for the Real Account Bot in
   `core/advisor_loop.py` have drifted (code moved, not changed in
   behavior) — corrected in this document's §1/§9.

No contradiction found rises to the level of a safety concern — all
four are documentation/reference-accuracy issues, not evidence of an
active forbidden control surface.

---

## 14. Verification performed

- `git diff --check`: clean (no whitespace-conflict markers) on this
  mission's sole change (this new file plus, if added, a short pointer
  line in an existing index — see §15).
- Repository-wide searches (§6) confirm zero Telegram runtime source
  file was modified by this mission — only `docs/contracts/` gained
  one new file.
- Markdown structure reviewed manually for heading/table well-formedness.
- The cross-stack compatibility gate
  (`.github/workflows/cross-stack-compat.yml`) runs on every PR to
  `main` per its trigger configuration; it is expected to pass
  trivially for a documentation-only change (no `observability/` or
  `frontend/` source touched). Not modified by this mission. Its
  result on the PR opened for this mission should be read directly
  from the PR's checks by the reviewer.

---

## 15. Pointer

A short non-normative pointer to this contract has been added to
`docs/architecture/TELEGRAM_IDENTITY_REGISTRY.md` (see that file's
top-of-document cross-reference note), rather than duplicating this
document's content there.

---

## 16. Summary for MASTER review

- 11 identity rows resolved (§9): 1 protected/unchanged (CryptoRadar),
  1 merged (Real Account → Portfolio), 2 confirmed dead
  (KillSwitch legacy, Narrator), 1 non-Telegram component sharing a
  class name (internal kill switch), 1 undeployed-but-fully-coded
  (Sim Bot, operator decision pending), 1 mixed-message-family bot
  requiring a critical/periodic split decision (Generic Alerts), 4
  otherwise clean active bots.
- Zero flows classified `RETIRE_AFTER_CERTIFIED_CUTOVER` — none are
  eligible yet, correctly, since Phase 1-3 have not occurred.
- Critical safety alerts (TG-06 subset) classified
  `KEEP_PERMANENT_CRITICAL_ALERT`, never subject to cutover.
- CryptoRadar and Paper Arena classified `KEEP_RESEARCH_INTERFACE`,
  untouched, no overlap with cockpit domains.
- `OPERATOR_DECISION_REQUIRED` items: TG-04 (Intel briefing
  replacement value), TG-06 (which specific sub-messages are
  status-only vs. genuine safety transitions), TG-08 (Sim Bot
  deploy-or-remove), TG-11 (superseded-status confirmation before any
  removal).
- `FORBIDDEN_MUST_NEVER_REACTIVATE`: TG-09 (legacy KillSwitch) —
  confirmed dead and confirmed never reachable from any active entry
  point; this document proposes it stay that way permanently, not as
  a pending retirement but as a standing constitutional prohibition
  consistent with ADR-0007.

---

O02WE1_CONTRACT_COMPLETE_MASTER_REVIEW_REQUIRED
