# Telegram Ecosystem Map
> Generated: 2026-08-28 | Status: Read-Only Forensic Inventory

This document is a **read-only forensic scan** of every Telegram identity found
in the repository. It does not modify any bot behavior. It complements (and
does not replace) the two existing normative documents:
- `docs/architecture/TELEGRAM_BOT_REGISTRY.md` — the functional contract
- `docs/TELEGRAM_CONSTITUTION.md` — the constitutional principles
- `docs/TELEGRAM_ARCHITECTURE_AUDIT.md` — the prior forensic audit (2026-08-28)

Where this scan reconfirms prior findings, evidence is cited directly to the
source file/line so it can be re-verified independently at any time.

---

## Summary Table

| # | Identity | Token Variable | Chat Variable | Entrypoint | Service | getUpdates | Mission Status |
|---|---|---|---|---|---|---|---|
| 1 | CryptoRadar | `RADAR_BOT_TOKEN` | `RADAR_CHAT_ID` | `scripts/radar_bot.py` | `crypto-radar-bot.service` | YES | ACTIVE |
| 2 | Portfolio Command Center | `P10_PORTFOLIO_BOT_TOKEN` | `P10_PORTFOLIO_CHAT_ID` | `capital_deployment/command_center_bot.py` | in-process `crypto-advisor.service` (no dedicated `.service` file found) | YES | ACTIVE |
| 3 | Quant Observer | `QC_BOT_TOKEN` | `QC_CHAT_ID` | `src/telegram/quant_observer/bot.py` | `crypto-quant-observer.service` | YES | ACTIVE |
| 4 | Rapport Automatique / Intel | `INTEL_BOT_TOKEN` | `INTEL_BOT_CHAT_ID` | `quant_hedge_ai/agents/intelligence/system_intel_reporter.py` (report builder) + `core/advisor_loop.py::_send_intel` (sender) | in-process `crypto-advisor.service` (no dedicated `.service` file found) | NO | ACTIVE |
| 5 | Paper Arena | `PAPER_ARENA_TG_TOKEN` | `PAPER_ARENA_TG_CHAT_ID` | `src/paper/paper_runner.py` + `src/paper/paper_report.py` | `paper-arena.service` | NO | ACTIVE |
| 6 | CMVK / Sim Bot | `CMVK_BOT_TOKEN` | `CMVK_CHAT_ID` | `src/telegram/bot_runner.py` + `src/telegram/sim_bot.py` | NONE found | YES | UNKNOWN — PENDING AUDIT |
| 7 | KillSwitch (legacy) | `KILLSWITCH_BOT_TOKEN` (never wired to `os.getenv`) | `KILLSWITCH_CHAT_ID` (never wired) | `supervision/kill_switch.py::TelegramKillSwitch` (class never instantiated with a real token) | NONE | YES (in dead code only) | DEAD_CODE |
| 8 | Generic alerts channel | `TELEGRAM_BOT_TOKEN` | `TELEGRAM_CHAT_ID` | `scripts/telegram_alerts.py`, `S3/01_telegram_alerts.py`, `infra/notifications/notifications.py`, `config/settings.py`, `supervision/*` (multiple independent senders) | none dedicated — used in-process by several scripts/services | NO (no `getUpdates` found on this token in current code) | ACTIVE (push-only, not a "bot identity" with commands) |
| — | Channel | UNKNOWN | UNKNOWN | none found | none found | — | NOT FOUND — no dedicated broadcast channel identity found in the repo |

Notes on the summary table:
- "Mission Status" reflects proof found in code, not intent. `ACTIVE` means
  wired to a real token variable, has a sender/poller, and (where applicable)
  a systemd unit or clear in-process host.
- Row 8 (generic `TELEGRAM_BOT_TOKEN`) is not one of the 5 constitutional
  bots — it is a shared push-only alerting facility used by multiple
  supervision/notification scripts. It is listed for completeness because it
  was historically a fallback/collision source for CryptoRadar (see
  `docs/TELEGRAM_ARCHITECTURE_AUDIT.md`, "PHASE C — Collisions identifiées").
  That fallback has since been removed from `scripts/radar_bot.py` (verified
  below).
- No evidence of a Telegram *Channel* (broadcast, not chat) identity was
  found anywhere in the repository.

---

## Identity Profiles

### 1. CryptoRadar

- **Token Variable**: `RADAR_BOT_TOKEN`
- **Chat Variable**: `RADAR_CHAT_ID`
- **Entrypoint**: `scripts/radar_bot.py`
- **Service**: `crypto-radar-bot.service` (`scripts/systemd/crypto-radar-bot.service`)
- **Polling (getUpdates)**: YES — `scripts/radar_bot.py:286` (long-poll loop, `timeout=30`) and `scripts/radar_bot.py:328` (startup flush, `timeout=0`)
- **Push (sendMessage)**: YES — `scripts/radar_bot.py:49` (`tg_request("sendMessage", ...)`)
- **Current Message Types**: Interactive command replies only: `/scan`, `/top50`, `/longs`, `/shorts`, `/symbol`, `/lmi`, `/help`. No automatic/unsolicited messages found.
- **Estimated Frequency**: On-demand only (fully reactive bot, no scheduled push found in the file).
- **Mission (Proven)**: Market opportunity scanner — surfaces aggregated confidence scores, dominant direction, and regime per symbol. Comment at `scripts/radar_bot.py:2-7` states explicitly: "Bot Telegram interactif CryptoRadar. LECTURE SEULE... Il n'affiche jamais d'Entry/SL/TP, de données portfolio, ni de métriques système."
- **Noise Assessment**: LOW (reactive only, no push spam).
- **Status**: ACTIVE
- **Evidence**: `scripts/radar_bot.py:20-21` (token/chat, no cross-identity fallback — comment at line 18-19 references Constitution Principle 3), `scripts/radar_bot.py:286,328` (getUpdates), `scripts/radar_bot.py:49` (sendMessage), `scripts/systemd/crypto-radar-bot.service`, `tests/scripts/test_radar_bot.py`.

---

### 2. Portfolio Command Center

- **Token Variable**: `P10_PORTFOLIO_BOT_TOKEN`
- **Chat Variable**: `P10_PORTFOLIO_CHAT_ID`
- **Entrypoint**: `capital_deployment/command_center_bot.py`
- **Service**: UNKNOWN — no dedicated `.service` file found under `scripts/systemd/`; the Registry documents it as in-process, hosted by `crypto-advisor.service` (not found as a distinct systemd unit file in this scan either — `crypto_advisor.service` at repo root and `scripts/crypto_advisor.service` exist but were not opened to confirm they launch this bot; treat as UNKNOWN pending that confirmation).
- **Polling (getUpdates)**: YES — `capital_deployment/command_center_bot.py:1235`
- **Push (sendMessage)**: YES — `capital_deployment/command_center_bot.py:1200`
- **Current Message Types**: Periodic report (`P10_PORTFOLIO_REPORT_MINS`/`_H`) plus on-demand replies: `/status`, `/kpis`, `/balance`, `/positions`, `/pnl`, `/phase`, `/regime`, `/risk`, `/health`, `/eo`, `/gate`, `/perf`, `/recap`, `/history`, `/logs`, `/config`, `/get`, `/certif`, `/charts`, `/help` — all documented read-only in `docs/architecture/TELEGRAM_BOT_REGISTRY.md`.
- **Estimated Frequency**: Periodic (interval configurable via `P10_PORTFOLIO_REPORT_MINS`/`_H` env vars) + on-demand.
- **Mission (Proven)**: Capital/performance reporting — "Montrer si la machine gagne réellement de l'argent" per Registry. Confirms it is capital/KPI-scoped, not signal-scoped (per-symbol signals explicitly removed, see Registry "Anomalies résolues" #5).
- **Noise Assessment**: MEDIUM — periodic reports plus drawdown alerts; frequency is configurable so actual noise depends on VPS `.env` values (not verifiable from repo alone).
- **Status**: ACTIVE
- **Evidence**: `capital_deployment/command_center_bot.py:1132-1133` (token/chat with `TELEGRAM_CHAT_ID` fallback on chat only, not token), `capital_deployment/command_center_bot.py:1200,1235` (send/getUpdates), `docs/architecture/TELEGRAM_BOT_REGISTRY.md:152-202`.

---

### 3. Quant Observer

- **Token Variable**: `QC_BOT_TOKEN`
- **Chat Variable**: `QC_CHAT_ID`
- **Entrypoint**: `src/telegram/quant_observer/bot.py` (also bootstrapped by `scripts/quant_observer_pin_bootstrap.py`)
- **Service**: `crypto-quant-observer.service` (`scripts/systemd/crypto-quant-observer.service`)
- **Polling (getUpdates)**: YES — `src/telegram/quant_observer/bot.py:73`
- **Push (sendMessage)**: YES — `src/telegram/quant_observer/bot.py:56`; also `sendPhoto` referenced at `src/telegram/quant_observer/bot.py:48`
- **Current Message Types**: Auto-refreshed pinned message (`QC_PINNED_UPDATE`, default 600s = 10 min) + on-demand replies: `/snapshot`, `/health`, `/pipeline`, `/help`.
- **Estimated Frequency**: Pinned message refresh every ~10 minutes (default) + on-demand commands.
- **Mission (Proven)**: Decision-engine microstructure observer — universe scanned, dominant regime, aggregated signal scores, meta-strategy state, decision pipeline health. No capital/equity/PnL data (explicitly forbidden per Registry).
- **Noise Assessment**: MEDIUM — a 10-minute pinned refresh is a continuous stream rather than an event, flagged in `docs/TELEGRAM_ARCHITECTURE_AUDIT.md` ("Notification Inventory") as **SUMMARIZE** candidate.
- **Status**: ACTIVE
- **Evidence**: `src/telegram/quant_observer/bot.py:48,56,73,212,254`, `scripts/systemd/crypto-quant-observer.service`, `scripts/quant_observer_pin_bootstrap.py`.

---

### 4. Rapport Automatique / Intel

- **Token Variable**: `INTEL_BOT_TOKEN`
- **Chat Variable**: `INTEL_BOT_CHAT_ID`
- **Entrypoint**: `quant_hedge_ai/agents/intelligence/system_intel_reporter.py` (builds the report content via `SystemIntelReporter.build_report`) + `core/advisor_loop.py::_send_intel` (actual Telegram sender)
- **Service**: UNKNOWN — no dedicated `.service` file found; hosted in-process, invoked from `core/advisor_loop.py` (which is understood to run under `crypto-advisor.service`, not independently confirmed in this scan).
- **Polling (getUpdates)**: NO — no `getUpdates` call found in either file.
- **Push (sendMessage)**: YES — `core/advisor_loop.py:1046` (`requests.post(f".../bot{token}/sendMessage", ...)`), guarded by `core/advisor_loop.py:1039-1044` (silent no-op if `INTEL_BOT_TOKEN`/`INTEL_BOT_CHAT_ID` are unset).
- **Current Message Types**: One periodic AI-generated natural-language briefing ("ChiefOfficer briefing"), per `core/advisor_loop.py:1031-1032` docstring.
- **Estimated Frequency**: Every 6 hours (per `docs/architecture/TELEGRAM_BOT_REGISTRY.md` and matching comment intent in code; exact scheduling loop not located inside the two files reviewed here — treat schedule trigger site as UNKNOWN, content/frequency claim as documented).
- **Mission (Proven)**: Push-only synthesis report, no interactive commands, no polling.
- **Noise Assessment**: LOW-MEDIUM — fixed low frequency (6h) but content density unverified from code alone.
- **Status**: ACTIVE
- **Evidence**: `core/advisor_loop.py:792-793` (env vars), `core/advisor_loop.py:1030-1050` (`_send_intel`), `quant_hedge_ai/agents/intelligence/system_intel_reporter.py:15` (comment: "via INTEL_BOT_TOKEN — jamais mélangé avec @QuantCrpto_bot ou @mon_portfolio_bot").

---

### 5. Paper Arena

- **Token Variable**: `PAPER_ARENA_TG_TOKEN`
- **Chat Variable**: `PAPER_ARENA_TG_CHAT_ID`
- **Entrypoint**: `src/paper/paper_runner.py` (event triggers) + `src/paper/paper_report.py` (Telegram sender)
- **Service**: `paper-arena.service` (`scripts/systemd/paper-arena.service`)
- **Polling (getUpdates)**: NO — no `getUpdates` call found in either file.
- **Push (sendMessage)**: YES — `src/paper/paper_report.py:23` (`requests.post(f".../bot{_TOKEN}/sendMessage", ...)`)
- **Current Message Types**: `notify_entry`, `notify_exit`, `notify_summary` — position entry/exit events plus periodic experiment summary and gate status (`INSUFFICIENT_SAMPLE` → `CONCLUSIVE`), per `src/paper/paper_runner.py:22,146,156,161,181,187`.
- **Estimated Frequency**: Event-driven (per trade entry/exit) + periodic summary — exact interval not fixed in code reviewed, driven by strategy signal frequency.
- **Mission (Proven)**: Reports the outcome of one isolated research experiment (RSI ETH/4H), scoped strictly to experiment metrics — no global system/portfolio data (per Registry, "FORBIDDEN" section).
- **Noise Assessment**: MEDIUM-HIGH — per-trade notifications are a noise source at scale, flagged in `docs/TELEGRAM_ARCHITECTURE_AUDIT.md` as **SUMMARIZE** candidate (replace trade-by-trade push with daily/weekly aggregate).
- **Status**: ACTIVE
- **Evidence**: `src/paper/paper_report.py:11-27`, `src/paper/paper_runner.py:7-8,22,146-187`, `scripts/systemd/paper-arena.service`, `tests/test_paper.py`.

---

### 6. CMVK / Sim Bot

- **Token Variable**: `CMVK_BOT_TOKEN`
- **Chat Variable**: `CMVK_CHAT_ID`
- **Entrypoint**: `src/telegram/bot_runner.py` (polling loop) + `src/telegram/sim_bot.py` (command handler, class `SimBot`)
- **Service**: NONE found — no `.service` file under `scripts/systemd/` references this bot.
- **Polling (getUpdates)**: YES — `src/telegram/bot_runner.py` (`_call(token, "getUpdates", ...)`, called from `run_forever`); also calls `deleteWebhook` for conflict clearing.
- **Push (sendMessage)**: YES — `src/telegram/bot_runner.py::_send` (`_call(token, "sendMessage", ...)`)
- **Current Message Types**: Interactive commands for a simulation core (`CMVK`): `/start`, `/help`, `/run`, `/status`, `/pnl`, `/trades`, `/runs`, `/stress`, `/history`, `/compare`, `/friction`, `/score`, `/distrib`, `/robust`, `/race`, `/validate`, `/overall`, `/breakdown`, `/market`, **and `/kill` / `/resume`** (`src/telegram/sim_bot.py:1174-1180`).
- **Estimated Frequency**: On-demand only.
- **Mission (Proven, partial)**: Interactive control/inspection surface for a simulation ("CMVK") backtesting core — confirmed by command list in `src/telegram/sim_bot.py`. Not documented in `docs/architecture/TELEGRAM_BOT_REGISTRY.md`, which instead lists `@FtnTrading_bot` (SimBot) as **removed / not used in production**.
- **Noise Assessment**: UNKNOWN — no evidence of active deployment (no systemd unit, no `.env.example` entries for `CMVK_BOT_TOKEN`/`CMVK_CHAT_ID`, only present in `.env.secrets.example`).
- **Status**: UNKNOWN — code exists and is wired end-to-end (polling + handler), but no deployment evidence (no service file, not in `.env.example`, marked "removed" in the Registry's "Bots supprimés" table for a bot with a matching description).
- **Evidence**: `src/telegram/sim_bot.py:2-3` (docstring: "SimBot — Telegram bot exclusivement dédié au noyau de simulation CMVK. Token : CMVK_BOT_TOKEN / Chat : CMVK_CHAT_ID"), `src/telegram/sim_bot.py:1174-1180` (`_cmd_kill`/`_cmd_resume` — **this is a control command, not observation**, see Constitutional Risk note below), `src/telegram/bot_runner.py` (full polling loop, `getUpdates`/`sendMessage`/`deleteWebhook`), `docs/architecture/TELEGRAM_BOT_REGISTRY.md:26-28` ("Bots supprimés" table lists `@FtnTrading_bot` (SimBot) as removed), `docs/TELEGRAM_ARCHITECTURE_AUDIT.md` ("⚪ Sim/CMVK Bot" row — same UNKNOWN conclusion reached independently in the prior audit).

  **Constitutional risk note**: `src/telegram/sim_bot.py::_cmd_kill` / `_cmd_resume` trigger/release a kill-switch object (`self._kill_switch.trigger(...)` / `.release()`) in response to Telegram commands. This is a **control command**, not a read-only observation — a violation of the "Telegram bots are STRICTLY read-only" constitutional rule if this bot is ever activated in production, regardless of whether the underlying kill-switch only affects the CMVK simulation core (not live trading). This must be resolved as part of the CMVK decision (see Constitution doc, Bot 6 section).

---

### 7. KillSwitch (legacy)

- **Token Variable**: `TELEGRAM_BOT_TOKEN` (documented as originally shared) — dedicated `KILLSWITCH_BOT_TOKEN`/`KILLSWITCH_CHAT_ID` variables are referenced only as *removed* in `docs/architecture/TELEGRAM_BOT_REGISTRY.md:24-28`, and were never found wired to `os.getenv` anywhere in the current codebase.
- **Chat Variable**: `TELEGRAM_CHAT_ID` (same caveat as above)
- **Entrypoint**: `supervision/kill_switch.py::TelegramKillSwitch` (class definition only)
- **Service**: NONE
- **Polling (getUpdates)**: YES in the class's own code, but the class is **never instantiated with a real token** anywhere in the active code path — `core/advisor_loop.py` uses `runtime.TelegramKillSwitch`, which actually resolves to `supervision/killswitch_hardened.py::KillSwitchHardened` (no Telegram references found in that file).
- **Push (sendMessage)**: YES in the class's own code (same dead-code caveat).
- **Current Message Types**: `/STOP_ALL`, `/CLOSE_ALL`, `/SAFE_MODE`, `/RESUME`, `/STATUS` — all control commands (would be a constitutional violation if ever wired live).
- **Estimated Frequency**: N/A — dead code.
- **Mission (Proven)**: None currently active. Historical kill-switch control interface, explicitly retired per `docs/architecture/TELEGRAM_BOT_REGISTRY.md:23-28` ("Retiré — constitution 2026-08-28 : aucune commande de contrôle via Telegram").
- **Noise Assessment**: N/A (dead code, no active messages).
- **Status**: DEAD_CODE
- **Evidence**: `supervision/kill_switch.py` (class body, only instantiated in its own docstring example), `docs/TELEGRAM_ARCHITECTURE_AUDIT.md` ("🔴 KillSwitch Telegram (legacy, code mort)" row — same conclusion reached independently in the prior audit), `docs/architecture/TELEGRAM_BOT_REGISTRY.md:23-28`.

---

### 8. Generic Alerts Channel (`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`)

- **Token Variable**: `TELEGRAM_BOT_TOKEN`
- **Chat Variable**: `TELEGRAM_CHAT_ID` (some senders also reference `TELEGRAM_BEHAVIOR_CHAT_ID`)
- **Entrypoint**: Many independent senders, not a single bot — e.g. `scripts/telegram_alerts.py`, `S3/01_telegram_alerts.py`, `infra/notifications/notifications.py`, `infra/notifications/notify_test_status.py`, `config/settings.py`, `supervision/notifications/ops_notifier.py`, `supervision/performance_watchdog.py`, `supervision/self_healing_bot.py`, `pieuvre/tentacles/resilience.py`, `quant_hedge_ai/main_v91.py`, `scripts/daily_signal_report.py`, `scripts/trend_scanner.py`, `watchdog_vps.py`/`infra/monitoring/watchdog_vps.py`, `scripts/boot_system_validator.py`, `scripts/runtime_validator.py`, `scripts/data_verifier.py`, `scripts/vps_burn_in_collector.py`.
- **Service**: None dedicated — consumed in-process by multiple scripts/services (not a single bot identity).
- **Polling (getUpdates)**: NO — no `getUpdates` call found against `TELEGRAM_BOT_TOKEN` in current code (the one historical fallback path from CryptoRadar has been removed, see below).
- **Push (sendMessage)**: YES — many independent senders (see entrypoint list above).
- **Current Message Types**: trade / danger / error / heartbeat / daily_summary alerts (per `docs/TELEGRAM_ARCHITECTURE_AUDIT.md` "Notification Inventory").
- **Estimated Frequency**: Variable — event-driven for danger/error, potentially periodic for heartbeat/daily_summary depending on caller.
- **Mission (Proven)**: Generic push-only alerting facility shared by supervision/monitoring code; not one of the 5 constitutional "identity" bots documented in the Registry.
- **Noise Assessment**: LOW for danger/error (rare, high-value), potentially HIGH for heartbeat if triggered on every cycle rather than on state change (per prior audit's recommendation).
- **Status**: ACTIVE
- **Evidence**: `scripts/telegram_alerts.py`, `config/settings.py`, `.github/workflows/ci.yml` (used in CI as well), `docs/TELEGRAM_ARCHITECTURE_AUDIT.md` ("⚠️ TELEGRAM_BOT_TOKEN générique (push)" row).
  - **Prior collision, now resolved**: `docs/TELEGRAM_ARCHITECTURE_AUDIT.md` documents that `scripts/radar_bot.py` previously fell back to this token (`TOKEN = os.getenv("RADAR_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")`). This scan confirms the fallback is **no longer present** — `scripts/radar_bot.py:20` now reads only `os.getenv("RADAR_BOT_TOKEN", "")` with an explicit comment citing Constitution Principle 3 ("No Cross-Identity Token Fallback").

---

### Channel

- **Status**: NOT FOUND. No dedicated Telegram broadcast *channel* (as distinct from a chat/group bot) identity, token variable, or entrypoint was found anywhere in the repository during this scan.

---

## Cross-References

- Functional contract (source of truth for intended behavior): `docs/architecture/TELEGRAM_BOT_REGISTRY.md`
- Constitutional principles: `docs/TELEGRAM_CONSTITUTION.md`
- Prior forensic audit (2026-08-28, same date, independently corroborated by this scan): `docs/TELEGRAM_ARCHITECTURE_AUDIT.md`
- `.env.example` and `.env.secrets.example` contain placeholders (never values) for all token/chat variables listed above except `CMVK_BOT_TOKEN`/`CMVK_CHAT_ID`, which appear only in `.env.secrets.example`, and `KILLSWITCH_BOT_TOKEN`/`KILLSWITCH_CHAT_ID`, which appear in neither file.
