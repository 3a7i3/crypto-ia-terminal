# Telegram Notification Audit
> Generated: 2026-08-28 | Phase 3.2 — Message Inventory

## Objective
Map every Telegram message sent by the system. Classify each as KEEP, SUMMARIZE, REMOVE, or ALERT.
This is a read-only forensic document. No code changes follow from this document alone.

> This document complements two existing governance documents and does not
> replace them: `docs/architecture/TELEGRAM_BOT_REGISTRY.md` (functional
> contract per bot, v2.0) and `docs/TELEGRAM_ARCHITECTURE_AUDIT.md` (Phase
> A-E forensic audit, per-bot rollup). Where those documents already give a
> per-bot classification, this document goes one level deeper: **every
> individual `sendMessage`/`sendPhoto`/`sendDocument` call site**, with
> `file:line` citation, trigger condition, and estimated frequency. Two
> findings below (`REAL_ACCOUNT_BOT_TOKEN`, the `S3/01_telegram_alerts.py`
> duplicate) are not present in the prior audit and are flagged as new.

## Summary Statistics

| Bot | Total Messages Found | KEEP | SUMMARIZE | REMOVE | ALERT | Noise Level |
|---|---|---|---|---|---|---|
| 📡 CryptoRadar (`scripts/radar_bot.py`) | 8 (reactive, all on-demand) | 8 | 0 | 0 | 0 | Low (user-triggered only) |
| 💼 Portfolio / CommandCenter (`capital_deployment/command_center_bot.py`) | 2 (auto) + ~20 (on-demand) | 21 | 1 | 1 | 0 | Low-Medium |
| 🔬 Quant Observer (`src/telegram/quant_observer/bot.py` + bootstrap script) | 4 (3 on-demand + 1 auto-refresh) + 1 one-time | 3 | 1 | 0 | 0 | Medium (10-min pin refresh) |
| 🧠 Rapport Automatique / Intel (`core/advisor_loop.py::_send_intel`, `scripts/test_intel_report.py`) | 1 auto + 1 manual test | 1 | 0 | 0 | 0 | Low (6h cadence) |
| 🧪 Paper Arena (`src/paper/paper_report.py`, `src/paper/paper_runner.py`) | 3 message types | 1 | 2 | 0 | 0 | Medium-High (per-trade push) |
| ⚠️ Generic Alerts (`TELEGRAM_BOT_TOKEN` — `core/advisor_loop.py`, `scripts/telegram_alerts.py`) | 24 call sites in `advisor_loop.py` + 7 methods in `telegram_alerts.py` | 10 | 8 | 4 | 6 | **High** (main noise source) |
| 🔴 Real Account Bot (`REAL_ACCOUNT_BOT_TOKEN` — **undocumented**, `core/advisor_loop.py::_telegram_real`) | 4 call sites | 3 | 1 | 0 | 0 | Low, but ungoverned |
| ⚪ Standalone CLI scripts (manual/cron, generic token) | 6 scripts, 1 send site each | 3 | 0 | 3 | 0 | Low (manual invocation) |
| ⚪ Legacy/dead code (`S3/01_telegram_alerts.py`, `supervision/kill_switch.py`) | 2 files, not wired to a live token | 0 | 0 | 2 | 0 | None (dead code risk only) |
| ⚪ CMVK Sim Bot (`src/telegram/sim_bot.py`) | 1 (`SimNotifier`, all on-demand) | 1 | 0 | 0 | 0 | Low — control commands already removed in this session (Task 1) |

---

## Notification Inventory

### 📡 CryptoRadar (`@RadarCrypto1_bot`, `RADAR_BOT_TOKEN`)

All messages are replies to a user command (`poll_loop()` in
`scripts/radar_bot.py:281-321`, dispatched via `send_message()` at
`scripts/radar_bot.py:35`). No proactive/periodic push exists in this bot.

| # | File:Line | Trigger | Content Template | Frequency | Human Value | Classification | Proposed Action |
|---|---|---|---|---|---|---|---|
| 1 | `scripts/radar_bot.py:308` | Any recognized command (`/scan /top50 /longs /shorts /symbol /lmi /help`) | Handler-specific (top opportunities, LMI, etc.) | On-demand (user-triggered) | High — answers "where is something happening in the market" | KEEP | None |
| 2 | `scripts/radar_bot.py:312` | Exception raised while handling a command | `Erreur: {exc}` | On-demand, rare (error path) | Low (diagnostic only) | KEEP | None — legitimate error surfacing to the requester |
| 3 | `scripts/radar_bot.py:314` | Unrecognized `/command` | `Commande inconnue: /{cmd}\nTape /help` | On-demand | Low | KEEP | None |
| 4 | `scripts/radar_bot.py:341` | `--once` CLI mode, same dispatch as above | Same as row 1 | On-demand (batch flush mode) | High | KEEP | None |

### 💼 Portfolio / CommandCenter (`@mon_portfolio_bot`, `MON_PORTFOLIO_BOT_TOKEN`)

| # | File:Line | Trigger | Content Template | Frequency | Human Value | Classification | Proposed Action |
|---|---|---|---|---|---|---|---|
| 1 | `capital_deployment/command_center_bot.py:1180` | Bot startup (`start()`) | "Mon Portefeuille — connecté" + auto-report cadence reminder | Once per process start | Medium | KEEP | None |
| 2 | `capital_deployment/command_center_bot.py:1357` | `_report_loop()` — every `P10_PORTFOLIO_REPORT_H` (default 1h) | `_fmt_rapport()` full status block | Hourly (default) | High — core "is the machine making money" answer | KEEP | None |
| 3 | `capital_deployment/command_center_bot.py:1284-1342` | Any read-only command (`/status /kpis /balance /positions /pnl /phase /regime /risk /health /eo /gate /perf /certif /charts /config /get /logs /trades /blackbox /history /recap`) | Handler-specific formatted block | On-demand | High | KEEP | None |
| 4 | `capital_deployment/command_center_bot.py:1332` | `/pause /resume /set /setphase /maxorder /reset /restart /confirm /cancel` | "🔒 Commande de contrôle désactivée — Constitution 2026-08-28" | On-demand (attempted control command) | Low (informational refusal) | SUMMARIZE | Message is correct and intentional, but the module docstring (`capital_deployment/command_center_bot.py:33-39`, "🔧 CONTRÔLE" section) still lists `/pause /resume /setphase /maxorder /confirm /cancel` as if active — **documentation is stale relative to the code**, which already blocks them. Update the docstring to match the runtime behavior (out of scope for this audit; flagged for follow-up, not fixed here per task rules). |
| 5 | `capital_deployment/command_center_bot.py:1346` | Exception during command routing | `Erreur: {exc}` | On-demand, rare | Low | KEEP | None |

### 🔬 Quant Observer (`@QuantCrpto_bot`, `QUANT_CRYPTO_BOT_TOKEN`)

| # | File:Line | Trigger | Content Template | Frequency | Human Value | Classification | Proposed Action |
|---|---|---|---|---|---|---|---|
| 1 | `src/telegram/quant_observer/bot.py:228` (`edit_message`) | Every `QC_PINNED_UPDATE` (default 600s = 10 min) | Pinned "SDOS LIVE" health/pipeline block (`_build_pinned_text()`) | Every 10 min, continuously | Medium — useful for research but is a stream, not an event | SUMMARIZE | Already flagged in `docs/TELEGRAM_CONSTITUTION.md` Principe 6; consider refreshing only on significant state change or lengthening to 30-60 min |
| 2 | `src/telegram/quant_observer/bot.py:185` | `/start` or `/help` | Command list | On-demand | Medium | KEEP | None |
| 3 | `src/telegram/quant_observer/bot.py:189,201,204,206` | `/portfolio` (redirect), `/snapshot /health /pipeline` (render error or unknown command) | Redirect / render / error text | On-demand | Medium | KEEP | None |
| 4 | `src/telegram/quant_observer/bot.py:201` (`send_photo`) | `/snapshot /health /pipeline` | Rendered PNG chart with caption | On-demand | High | KEEP | None |
| 5 | `scripts/quant_observer_pin_bootstrap.py:83-86` | One-time manual bootstrap script (operator runs it once to create the pinned message) | "SDOS LIVE — bootstrap" placeholder | One-time (manual operator action, not recurring) | N/A (setup utility, not a notification) | KEEP | None — not a recurring notification, exempt from noise concerns |

### 🧠 Rapport Automatique / Intel (`@rapport_automatique_bot`, `RAPPORT_AUTOMATIQUE_BOT_TOKEN`)

| # | File:Line | Trigger | Content Template | Frequency | Human Value | Classification | Proposed Action |
|---|---|---|---|---|---|---|---|
| 1 | `core/advisor_loop.py:7139` (via `_send_intel`, defined `core/advisor_loop.py:1031-1055`) | `_now - _last_intel_ts >= INTEL_INTERVAL_S` (`INTEL_REPORT_EVERY_H`, default 6h) — `core/advisor_loop.py:7099-7101` | `SystemIntelReporter.build_report()` — full 6h AI briefing (awareness, regret, mistakes, dataset quality) | Every 6h (default) | High — matches Principe 10 ("scientific conclusion over raw event") as long as content stays a summary | KEEP | None, provided report content remains a synthesis (already the stated design) |
| 2 | `scripts/test_intel_report.py:80` (`send_to_intel`) | Manual CLI invocation (`python scripts/test_intel_report.py`) | Identical content to production report (calls the same `SystemIntelReporter.build_report()`) | Manual / on-demand (diagnostic tool) | N/A (test utility) | KEEP | None — not a production notification path |

### 🧪 Paper Arena (`@PaperArena_bot`, `PAPER_ARENA_BOT_TOKEN`)

| # | File:Line | Trigger | Content Template | Frequency | Human Value | Classification | Proposed Action |
|---|---|---|---|---|---|---|---|
| 1 | `src/paper/paper_report.py:31-50` (`notify_entry`), called `src/paper/paper_runner.py:181` | Every new paper position opened | "🟢/🔴 PAPER ENTRY" — symbol, side, price, size, RSI, equity | Event-driven, per-trade (4h timeframe strategy → UNKNOWN absolute rate, likely a few per week) | Medium — useful in research but is a per-trade event, not a conclusion | SUMMARIZE | Per Constitution Principe 10 and prior audit: batch entries/exits into a periodic digest, keep only the gate-status transition as a rare high-value event |
| 2 | `src/paper/paper_report.py:53-71` (`notify_exit`), called `src/paper/paper_runner.py:146` | Every closed paper position | "🟢/🔴 PAPER EXIT" — entry/exit price, PnL, equity, run # | Event-driven, per-trade | Medium | SUMMARIZE | Same as above — batch into periodic digest |
| 3 | `src/paper/paper_report.py:74-89` (`notify_summary`), called `src/paper/paper_runner.py:156,161,187` | Every `SUMMARY_EVERY_N` (=10) closed trades, on gate pass, or on manual interrupt (`KeyboardInterrupt`) | "📊 PAPER ARENA — Rapport" — equity, WR, PF, expectancy, gate status | Every 10 trades (event-driven) + on gate transition + on shutdown | High — aggregated statistics, matches Principe 10 | KEEP | None — already the "conclusion" format the constitution recommends |

### ⚠️ Generic Alerts channel (`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` / `TELEGRAM_BEHAVIOR_CHAT_ID`)

Per `.env.example:20-38`, this token is an explicitly-documented "generic push
alert" channel, distinct from the 5 registered bots, used directly inside
`core/advisor_loop.py` (functions `_telegram`, `_telegram_behavior`, defined
`core/advisor_loop.py:931-1006`) and by the `TelegramAlert` helper class in
`scripts/telegram_alerts.py`.

| # | File:Line | Trigger | Content Template | Frequency | Human Value | Classification | Proposed Action |
|---|---|---|---|---|---|---|---|
| 1 | `core/advisor_loop.py:3509` | Real capital snapshot returns null (`_capital_x is None`) with an exchange object present | "⚠️ PORTEFEUILLE X = NULL" | On-event, boot-time only | High (blocks trading) | ALERT | None |
| 2 | `core/advisor_loop.py:3601` | `OperationalState` transitions to DEGRADED | "Mode DEGRADED — exchange instable" | On-event | High | ALERT | None |
| 3 | `core/advisor_loop.py:3609` | `OperationalState` transitions to HALTED | "P10-F HALTED — intervention requise" | On-event, rare | High | ALERT | None |
| 4 | `core/advisor_loop.py:3616` | Exchange recovers to RUNNING | "Exchange stabilisé — retour mode RUNNING" | On-event | Medium | KEEP | None |
| 5 | `core/advisor_loop.py:3758` | Process startup | Full startup banner (symbols, interval, capital, mode, active subsystems) | Once per process start | Medium | KEEP | None |
| 6 | `core/advisor_loop.py:3770` | Process startup (immediately after row 5) | `_build_guide()` — help/quickstart text | Once per process start | Low-Medium (duplicates startup banner content) | SUMMARIZE | Merge into the single startup banner message (row 5) instead of two separate `sendMessage` calls |
| 7 | `core/advisor_loop.py:4118` | Every closed trading position (`_on_position_close`) | "SORTIE {side} — {symbol}" full close block | Event-driven, per-trade | Medium-High | KEEP | None — legitimate trade-level event, core to "is the machine trading" |
| 8 | `core/advisor_loop.py:4180` | `SelfAwarenessEngine` reaches WARNING+ | "SELF-AWARENESS — {level}" | On-event | High | ALERT | None |
| 9 | `core/advisor_loop.py:4288` | `ExecutiveOverride` level changes | "EXECUTIVE OVERRIDE — {old}->{new}" | On-event | High | ALERT | None |
| 10 | `core/advisor_loop.py:4534` | `AutoDecisionOrchestrator` issues `REDUCE_RISK` | "[AUTO] REDUCE_RISK x{factor}" | On-event, cooldown 1800s | Medium | KEEP | None |
| 11 | `core/advisor_loop.py:5132` | Kill switch engaged (loop enters suspended wait) | "Boucle suspendue par Kill Switch..." | On-event | High | ALERT | None |
| 12 | `core/advisor_loop.py:5141` | Kill switch released | "Kill Switch levé — reprise du cycle normal." | On-event | Medium | KEEP | None |
| 13 | `core/advisor_loop.py:5171` | P10-F emergency-stop trigger fires | "P10-F EMERGENCY STOP\nCritère: ..." | On-event, rare | High | ALERT | None |
| 14 | `core/advisor_loop.py:6258` | Actionable signal, decision-event bus unavailable (legacy fallback path) | `_build_alert(r, cycle)` per-symbol alert | Event-driven, variable (per actionable signal, could be several/hour in volatile regimes) | Medium — legitimate signal alert, but frequency is uncontrolled | SUMMARIZE | Confirm the primary `_decision_event_bus` path (line ~6246) is reliably available in production; if this fallback fires often, consider batching multiple actionable signals from the same cycle into one message instead of one `sendMessage` per symbol |
| 15 | `core/advisor_loop.py:6720` | `RegretEngine.evaluate_pending()` returns new regrets | "REGRET DETECTE: {symbol} ..." | Event-driven, one message per regret detected (loop over `new_regrets`) | Medium — valuable for "what did we miss" but can fan out per-symbol per-cycle | SUMMARIZE | Batch all regrets from a single cycle into one message instead of N separate `sendMessage` calls in the `for reg in new_regrets` loop |
| 16 | `core/advisor_loop.py:7148` | `ranker.check_probation_alerts()` yields a probation message | "PROBATION STRATEGIE\n{msg}" | Event-driven, once per strategy per threshold crossing | Medium | KEEP | None |
| 17 | `core/advisor_loop.py:7209` | Every `ADVISOR_NOTIFY_EVERY` cycles (default 3 cycles × 300s interval ≈ 15 min) | Full cycle report: commandement, mistake memory, portfolio block, signal policy, top strategies | ~Every 15 min | High — main "cycle report", but overlaps in cadence with row 20 (heartbeat) | KEEP (content), SUMMARIZE (cadence overlap) | See "Priority Actions" — merge or de-duplicate against the heartbeat message (row 20), which fires on the same default cadence |
| 18 | `core/advisor_loop.py:7432` | System-state heartbeat detects `STALL` | "[ALERTE] Pipeline execution bloque" | On-event | High | ALERT | None |
| 19 | `core/advisor_loop.py:7450` | Position reconciliation detects ghost positions | "[ALERTE] Reconciliation positions" | On-event (hourly check) | High | ALERT | None |
| 20 | `core/advisor_loop.py:7478` | State-integrity audit finds an unsafe state | "[INTEGRITE] score={score}/100" | On-event (periodic check) | High | ALERT | None |
| 21 | `core/advisor_loop.py:7607` | Every `HEARTBEAT_CYCLES` cycles (default 3 cycles × 300s ≈ 15 min) | `render_heartbeat()` compact system snapshot | ~Every 15 min | Medium — **same default cadence as row 17** | SUMMARIZE | Likely redundant with the full cycle report (row 17) at default settings; either lengthen `HEARTBEAT_CYCLES` relative to `ADVISOR_NOTIFY_EVERY` or merge the compact heartbeat into the full report |
| 22 | `core/advisor_loop.py:7639` | Manual `KeyboardInterrupt` | "Crypto AI Terminal arrêté manuellement." | Manual, rare | Low | KEEP | None |
| 23 | `core/advisor_loop.py:7711` | 5 consecutive cycle exceptions | "CRASH — 5 erreurs consécutives..." | On-event, rare (also triggers `_send_email`, `core/advisor_loop.py:7712`) | High | ALERT | None |
| 24 | `core/advisor_loop.py:6349` (`_telegram_behavior`) | Regime-transition confirmed over `_REGIME_STABILITY` cycles | "🔄 TRANSITION RÉGIME" | Event-driven | Medium | KEEP | None |
| 25 | `core/advisor_loop.py:6404` | `ActivityTracker` detects stall, once per episode | "TRADING_STALLED [...]" | Event-driven, deduplicated (`_stalled_alerted` flag) | High | ALERT | None |
| 26 | `core/advisor_loop.py:6456` | Adaptation-tracking engine (ATE) finds inefficacy | "ADAPTATION_INEFFECTIVE" | Event-driven | Medium | KEEP | None |
| 27 | `core/advisor_loop.py:6484` | `REGIME_MISMATCH` (cooldown-gated, `cycle % 3 == 0`, 15-cycle cooldown) | "REGIME_MISMATCH — {n} cycles sans trade" | Event-driven, cooldown-limited | Medium | KEEP | None |
| 28 | `core/advisor_loop.py:6530` | Behavioral Stability Monitor detects oscillating/degraded state | "⚠️ BSM ALERTE" | Event-driven | High | ALERT | None |
| 29 | `core/advisor_loop.py:6540` | Every 50 cycles (~4h at default interval) | "📊 {behavior_log line}" — `[BEHAVIOR]` summary | Every 50 cycles (~4h) | Low-Medium — machine-log style line dumped to a human channel | SUMMARIZE | Consider whether this duplicates information already visible via `/health`-style commands or the 6h Intel report; if so, remove from the behavior channel and keep only in logs |
| 30 | `scripts/telegram_alerts.py:96-111` (`TelegramAlert.trade`) | Called by application code with a BUY/SELL event (no confirmed call site found in `advisor_loop.py` beyond the class import — see note below) | "🟢/🔴 TRADE {side}" | UNKNOWN (helper method; only one confirmed instantiation found, no confirmed call to `.trade()`) | UNKNOWN | UNKNOWN | Confirm whether `.trade()` is actually invoked anywhere in production; if unused, it is dead code duplicating row 7 |
| 31 | `scripts/telegram_alerts.py:113-117` (`.danger`) | Application-level danger event | "🚨/⚠️ {level}\n{reason}" | UNKNOWN, deduplicated 5 min | UNKNOWN | KEEP (if used) | None |
| 32 | `scripts/telegram_alerts.py:119-123` (`.error`) | Application-level error | "❌ ERREUR [{component}]" | UNKNOWN, deduplicated 5 min | UNKNOWN | KEEP (if used) | None |
| 33 | `scripts/telegram_alerts.py:125-126` (`.heartbeat`) | Manual call, deduplicated | "💓 Heartbeat — {status}" | UNKNOWN | Low if frequent | SUMMARIZE (if used) | Confirm no active caller before assuming risk; if wired up in parallel to rows 17/21 it would be a third redundant heartbeat channel |
| 34 | `scripts/telegram_alerts.py:128-142` (`.daily_summary`) | Manual call, `force=True` (bypasses dedup) | "📊 RÉSUMÉ JOURNALIER" | UNKNOWN (designed for daily cadence) | High (if used) | KEEP (if used) | None |

### 🔴 Real Account Bot (`REAL_ACCOUNT_BOT_TOKEN` / `REAL_ACCOUNT_CHAT_ID`) — **undocumented, new finding**

Not listed in `docs/architecture/TELEGRAM_BOT_REGISTRY.md` ("5 bots actifs")
nor in `docs/TELEGRAM_ARCHITECTURE_AUDIT.md`'s identity table, and not
declared in `.env.example`. This channel exists solely inside
`core/advisor_loop.py` via `_telegram_real()` (defined
`core/advisor_loop.py:1009-1028`, env vars read at `core/advisor_loop.py:796-797`
as `REAL_ACCOUNT_BOT_TOKEN` / `REAL_ACCOUNT_CHAT_ID`).

| # | File:Line | Trigger | Content Template | Frequency | Human Value | Classification | Proposed Action |
|---|---|---|---|---|---|---|---|
| 1 | `core/advisor_loop.py:3483` | Boot, paper mode active, real API balance present | "🔴 STANDBY — Compte Réel" | Once per process start | Medium | KEEP | Add this bot to `TELEGRAM_BOT_REGISTRY.md` and `.env.example` (out of scope for this audit's code changes, but should be tracked as a governance gap) |
| 2 | `core/advisor_loop.py:3495` | Boot, live mode active | "🟢 LIVE — Compte Réel" | Once per process start | High (mode change is critical) | ALERT | Same as above |
| 3 | `core/advisor_loop.py:3516` | Boot, real API balance is null | "⚠️ COMPTE RÉEL — X = NULL" | Once per process start (on-event) | High | ALERT | Same as above |
| 4 | `core/advisor_loop.py:7233` | Every `REAL_BOT_REPORT_EVERY` cycles (default 12 × 300s = 1h) | `render_real_account_block()` + multi-exchange detail | Hourly (default) | Medium-High | KEEP | Same as above — document this bot identity |

### ⚪ Standalone CLI scripts (manual/cron invocation, generic `TELEGRAM_BOT_TOKEN`)

These are not part of any always-running bot process; each is a script a
human or a cron job runs on demand. None of them poll for commands
(`getUpdates`), they only push.

| # | File:Line | Trigger | Content Template | Frequency | Human Value | Classification | Proposed Action |
|---|---|---|---|---|---|---|---|
| 1 | `scripts/daily_signal_report.py:96-121` (`send_telegram`) | Manual/cron run of `daily_signal_report.py` (no `--dry-run`) | "📋 SIGNAUX {date}" — daily long/short signal digest | UNKNOWN cadence (script name implies daily; no systemd timer found for it) | Medium | KEEP | None |
| 2 | `scripts/trend_scanner.py:155-174` (`send_telegram`) | Manual/cron run of `trend_scanner.py` (no `--dry-run`) | Trend/S-R table across top symbols | UNKNOWN cadence (no systemd timer found) | Medium | KEEP | None |
| 3 | `scripts/data_verifier.py:462` (`test_telegram`) | Manual diagnostic invocation only | "🔍 Data Verifier — Test live" | Manual, on-demand (connectivity test) | N/A (diagnostic) | REMOVE (not a real notification — a test utility) | None — exempt from notification-noise scope, but should stay out of any automated schedule |
| 4 | `scripts/quant_observer_pin_bootstrap.py:83-86` | One-time manual bootstrap (see Quant Observer section, listed once for completeness) | Placeholder pin message | One-time | N/A | KEEP | None |
| 5 | `scripts/vps_burn_in_collector.py:817` | Manual/cron run with `--report --telegram` flag | Burn-in daily report (behavior, alpha, kill-switch triggers) | UNKNOWN cadence (comment says "rapport journalier"; no systemd timer found in `scripts/systemd/`) | Medium-High | KEEP | None |
| 6 | `scripts/test_intel_report.py:72,81` | Manual diagnostic invocation only | Identical to production Intel report | Manual, on-demand | N/A (diagnostic, duplicate of Intel row) | REMOVE (as a distinct notification path — it is a test tool, not production) | None — already covered under Rapport Automatique |

### ⚪ Legacy / dead code (no live token wired)

| # | File:Line | Trigger | Content Template | Frequency | Human Value | Classification | Proposed Action |
|---|---|---|---|---|---|---|---|
| 1 | `S3/01_telegram_alerts.py` (full file — near-duplicate of `scripts/telegram_alerts.py`) | Would fire identically to the generic-alerts rows above | Same templates as `scripts/telegram_alerts.py` | N/A — `S3/02_log_surveillance.py:267` imports `from S3.telegram_alerts import TelegramAlert`, a module path that does not exist (the real file is `S3/01_telegram_alerts.py`); this import appears broken/unused | None currently | REMOVE | Confirm the broken import is dead, then delete the duplicate file in a future cleanup (out of scope for this audit) |
| 2 | `supervision/kill_switch.py` (class `TelegramKillSwitch`, `sendMessage` inside `_send`) | Would fire on `/STOP_ALL /CLOSE_ALL /SAFE_MODE /RESUME /STATUS` if ever instantiated with a real token | Kill-switch confirmation messages | N/A — never instantiated with a real token in the active code path (`core/advisor_loop.py` uses `KillSwitchHardened` instead, per `docs/TELEGRAM_CONSTITUTION.md` Principe 5) | None currently, but constitutes latent control-command risk if re-wired | REMOVE | Already flagged in `docs/TELEGRAM_CONSTITUTION.md`; physical deletion recommended in a future cleanup, out of scope here |

### ⚪ CMVK Sim Bot (`src/telegram/sim_bot.py`, `SimNotifier` → `@mon_portfolio_bot` token)

| # | File:Line | Trigger | Content Template | Frequency | Human Value | Classification | Proposed Action |
|---|---|---|---|---|---|---|---|
| 1 | `src/telegram/sim_bot.py:185,307,526,859,965` (`Notifier.run_completed/stress_completed/info/robust_completed/race_completed`) | User runs `/run /stress /robust /race` inside the sim bot | Backtest run/stress/robustness/race summaries | On-demand (user-triggered simulation) | Medium (research tool) | KEEP | None. Control commands (`/kill`, `/resume`) were removed from this file in Task 1 of this session — see `src/telegram/sim_bot.py` diff; this bot is additionally marked "retiré — non utilisé en production" in `TELEGRAM_BOT_REGISTRY.md`, so its notification volume is not a production concern |

---

## Noise Reduction Potential

Estimate: **~20-25%** of current messages can be REMOVED or SUMMARIZED
without losing human value, concentrated almost entirely in the Generic
Alerts channel (`TELEGRAM_BOT_TOKEN`) and Paper Arena's per-trade pushes:

- The heartbeat (`core/advisor_loop.py:7607`) and the full cycle report
  (`core/advisor_loop.py:7209`) fire on the **same default 15-minute cadence**
  — one of the two is largely redundant at default settings.
- Per-symbol regret alerts (`core/advisor_loop.py:6720`) and the legacy
  per-symbol signal-alert fallback (`core/advisor_loop.py:6258`) can fan out
  multiple messages per cycle instead of one batched message.
- Paper Arena's per-trade entry/exit pushes (`src/paper/paper_report.py:31-71`)
  are already flagged in the existing `docs/TELEGRAM_ARCHITECTURE_AUDIT.md`
  as SUMMARIZE candidates.
- The Quant Observer pinned message refresh (every 10 min, continuously) is
  a stream rather than an event.
- Two standalone diagnostic scripts (`scripts/data_verifier.py`'s
  `test_telegram`, `scripts/test_intel_report.py`) are test utilities, not
  production notifications, and should never be scheduled automatically.

## Priority Actions

1. **De-duplicate the ~15-minute cadence collision** between the full cycle
   report (`core/advisor_loop.py:7209`, gated by `ADVISOR_NOTIFY_EVERY`,
   default 3 cycles) and the compact heartbeat
   (`core/advisor_loop.py:7607`, gated by `HEARTBEAT_CYCLES`, default 3
   cycles) — both resolve to ~15 minutes at default settings on the same
   generic channel. Merge or stagger them.
2. **Document the undocumented `REAL_ACCOUNT_BOT_TOKEN` / `REAL_ACCOUNT_CHAT_ID`
   channel** (`core/advisor_loop.py:796-797, 1009-1028`) in
   `docs/architecture/TELEGRAM_BOT_REGISTRY.md` and `.env.example` — it is a
   sixth live Telegram identity, invisible to both existing governance
   documents, sending STANDBY/LIVE mode-change alerts and hourly real-account
   reports.
3. **Batch per-symbol event fan-out** in `core/advisor_loop.py` — the
   `for reg in new_regrets` loop (line 6720) and the legacy per-symbol alert
   fallback (line 6258) can each send multiple `sendMessage` calls within a
   single cycle; batch them into one message per cycle.
4. **Retire genuinely dead code** carrying latent control-command risk:
   `supervision/kill_switch.py::TelegramKillSwitch` (never instantiated with
   a real token, superseded by `KillSwitchHardened`) and the duplicate
   `S3/01_telegram_alerts.py` (superseded by `scripts/telegram_alerts.py`,
   and referenced via a broken import path from `S3/02_log_surveillance.py`).
   Both are already implicitly flagged in `docs/TELEGRAM_CONSTITUTION.md`
   Principe 5; this document adds the concrete duplicate-file finding.

## Central Notification Policy — Conceptual Design
(Not yet implemented — classification only)

| Decision | Definition | Example |
|---|---|---|
| ALERT | Rare, critical, requires human attention | Infrastructure down, corruption detected |
| KEEP | Important, low-frequency, informative | Daily briefing, regime change |
| SUMMARIZE | Useful but too frequent — batch into digest | Per-trade updates → hourly summary |
| REMOVE | Machine log, zero human value | Cycle counter, neutral signal spam |
