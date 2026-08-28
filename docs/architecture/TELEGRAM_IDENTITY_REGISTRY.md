# Telegram Identity Registry
> Phase 3.3.1 — Complete Identity Governance Audit | 2026-08-28
> Status: Read-Only Forensic Document

## Purpose
Single source of truth for all Telegram identities in CRYPTO_AI_TERMINAL.
This document supersedes the identity sections of `docs/TELEGRAM_ARCHITECTURE_AUDIT.md`
and `docs/architecture/TELEGRAM_ECOSYSTEM_MAP.md`. It does not replace the
functional contract in `docs/architecture/TELEGRAM_BOT_REGISTRY.md` (that
document remains authoritative for *intended* per-bot behavior); it exists to
answer one narrower question exhaustively: **how many distinct Telegram
token/chat identities exist in this repository, and what is the code-proven
evidence for each?**

This scan re-verified every claim below directly against the current
repository state (grep + line-level inspection on 2026-08-28) rather than
only citing prior documents. Where this scan found the code has changed
since a prior document was written (e.g. `RADAR_BOT_TOKEN`'s fallback
removal), the current code state is reported and the discrepancy is noted.

## Constitutional Reference
All bots are governed by `docs/TELEGRAM_CONSTITUTION.md`.
Constitutional rule: Telegram = read-only observation layer. Zero control commands.

## Complete Identity Count

**7 official identities** (6 bots + 1 generic push channel) — as of 2026-08-28 merge.

> **Architecture decision 2026-08-28**: `REAL_ACCOUNT_BOT_TOKEN` has been removed.
> It was confirmed to be the same physical BotFather token as `MON_PORTFOLIO_BOT_TOKEN`.
> All real-account push notifications in `core/advisor_loop.py::_telegram_real()`
> now route through `MON_PORTFOLIO_BOT_TOKEN` / `MON_PORTFOLIO_CHAT_ID`.
> The variable `REAL_ACCOUNT_BOT_TOKEN` has been deleted from `.env.secrets.example`
> and from `core/advisor_loop.py`.

Audit history: forensic scan found 10 distinct token-variable groups in the codebase,
reduced to 7 official identities after:
- merging `REAL_ACCOUNT_BOT_TOKEN` into `MON_PORTFOLIO_BOT_TOKEN` (same physical token, operator confirmed)
- classifying `NARRATOR_BOT_TOKEN` as dead code (commented-out placeholder only, never wired)
- classifying `KILLSWITCH_BOT_TOKEN` as dead code (prose reference only, never wired to `os.getenv`)

No dedicated Telegram *channel* (broadcast, as distinct from a bot/chat)
identity was found anywhere in the repository.

## Summary Table

| ID | Identity Name | Token Variable | Chat Variable | Type | Polling | Push | Service | Documented | Status |
|---|---|---|---|---|---|---|---|---|---|
| IDENTITY-01 | CryptoRadar | `RADAR_BOT_TOKEN` | `RADAR_CHAT_ID` | INTERACTIVE | YES | YES | `crypto-radar-bot.service` | YES | ACTIVE |
| IDENTITY-02 | Portfolio (CommandCenter) | `MON_PORTFOLIO_BOT_TOKEN` | `MON_PORTFOLIO_CHAT_ID` | INTERACTIVE | YES | YES | in-process `crypto-advisor.service` | YES | ACTIVE |
| IDENTITY-03 | Quant Observer | `QUANT_CRYPTO_BOT_TOKEN` | `QUANT_CRYPTO_CHAT_ID` | INTERACTIVE | YES | YES | `crypto-quant-observer.service` | YES | ACTIVE |
| IDENTITY-04 | Rapport Automatique / Intel | `RAPPORT_AUTOMATIQUE_BOT_TOKEN` | `RAPPORT_AUTOMATIQUE_CHAT_ID` | PUSH_ONLY | NO | YES | in-process `crypto-advisor.service` | YES | ACTIVE |
| IDENTITY-05 | Paper Arena | `PAPER_ARENA_BOT_TOKEN` | `PAPER_ARENA_CHAT_ID` | PUSH_ONLY | NO | YES | `paper-arena.service` | YES | ACTIVE |
| IDENTITY-06 | CMVK / Sim Bot | `TELEMETRIE_IA_BOT_TOKEN` | `TELEMETRIE_IA_CHAT_ID` | INTERACTIVE (code) | YES | YES | NONE found | PARTIAL | UNKNOWN |
| IDENTITY-07 | Generic Alerts (Moteur) | `TELEGRAM_BOT_TOKEN` | `TELEGRAM_CHAT_ID` / `TELEGRAM_BEHAVIOR_CHAT_ID` | PUSH_ONLY | NO | YES | in-process `crypto-advisor.service` + standalone scripts | PARTIAL | ACTIVE |
| IDENTITY-08 | ~~Real Account Bot~~ | ~~`REAL_ACCOUNT_BOT_TOKEN`~~ | ~~`REAL_ACCOUNT_CHAT_ID`~~ | **MERGED** | — | — | — | — | **MERGED → IDENTITY-02** |
| IDENTITY-09 | KillSwitch (legacy, dead code) | `KILLSWITCH_BOT_TOKEN` (never wired) | `KILLSWITCH_CHAT_ID` (never wired) | DEAD_CODE | N/A | N/A | NONE | PARTIAL | DEAD_CODE |
| IDENTITY-10 | Narrator / Télémétrie IA | `NARRATOR_BOT_TOKEN` | `NARRATOR_CHAT_ID` | DEAD_CODE | UNKNOWN | UNKNOWN | NONE found | PARTIAL | DEAD_CODE |

Type: INTERACTIVE (polling+push) / PUSH_ONLY / DEAD_CODE / UNKNOWN
Documented: YES (in TELEGRAM_BOT_REGISTRY.md) / NO / PARTIAL
Status: ACTIVE / INACTIVE / DEAD_CODE / UNKNOWN

---

## Identity Profiles

### [IDENTITY-01] CryptoRadar
- **Token Variable**: `RADAR_BOT_TOKEN`
- **Chat Variable**: `RADAR_CHAT_ID`
- **Type**: INTERACTIVE
- **Entrypoint**: `scripts/radar_bot.py`
- **Service**: `crypto-radar-bot.service` (`scripts/systemd/crypto-radar-bot.service`)
- **Polling (getUpdates)**: YES — `scripts/radar_bot.py:286` (main long-poll loop, `timeout=30`), `scripts/radar_bot.py:328` (startup flush, `timeout=0`)
- **Push (sendMessage)**: YES — `scripts/radar_bot.py:49` (`tg_request("sendMessage", ...)`)
- **In .env.example**: YES — `.env.example:56-57`
- **In TELEGRAM_BOT_REGISTRY.md**: YES — full profile present ("BOT: CryptoRadar" section)
- **Call sites**: `scripts/radar_bot.py:20` (`TOKEN = os.getenv("RADAR_BOT_TOKEN", "").strip()`), `scripts/radar_bot.py:21` (`CHAT_ID = os.getenv("RADAR_CHAT_ID", "").strip()`)
- **Mission (evidence-based)**: Market opportunity scanner, read-only. Module docstring (`scripts/radar_bot.py:1-7`): "Bot Telegram interactif CryptoRadar. LECTURE SEULE... Il n'affiche jamais d'Entry/SL/TP, de données portfolio, ni de métriques système."
- **Owner**: UNKNOWN (not documented)
- **Status**: ACTIVE
- **Governance gaps**: None found. Note (state-change vs. prior audits): `scripts/radar_bot.py:20` currently reads **only** `RADAR_BOT_TOKEN`, with an explicit code comment citing "Constitution Principle 3: No Cross-Identity Token Fallback." This confirms the fallback to `TELEGRAM_BOT_TOKEN` that `docs/TELEGRAM_ARCHITECTURE_AUDIT.md` (Phase A/B, same date) recorded as a collision risk has since been removed in this same repository state — the two documents are not contradictory, they represent before/after of the same fix.

---

### [IDENTITY-02] Portfolio (CommandCenter)
- **Token Variable**: `MON_PORTFOLIO_BOT_TOKEN`
- **Chat Variable**: `MON_PORTFOLIO_CHAT_ID`
- **Type**: INTERACTIVE
- **Entrypoint**: `capital_deployment/command_center_bot.py`, instantiated from `core/advisor_loop.py:3633-3718` (`CommandCenterBot.from_env(...)` then `.start()`)
- **Service**: in-process `crypto-advisor.service` (`scripts/systemd/crypto-advisor.service`, `ExecStart=... python core/advisor_loop.py`) — no dedicated `.service` file exists for this bot specifically.
- **Polling (getUpdates)**: YES — `capital_deployment/command_center_bot.py:1235`
- **Push (sendMessage)**: YES — `capital_deployment/command_center_bot.py:1200`
- **In .env.example**: YES — `.env.example:63-64`
- **In TELEGRAM_BOT_REGISTRY.md**: YES — full profile present ("BOT: Portfolio" section)
- **Call sites**: `capital_deployment/command_center_bot.py:1132` (`token = os.getenv("MON_PORTFOLIO_BOT_TOKEN", "")`), `capital_deployment/command_center_bot.py:1133` (`chat_id = os.getenv("MON_PORTFOLIO_CHAT_ID", os.getenv("TELEGRAM_CHAT_ID", ""))` — chat has a fallback to the generic `TELEGRAM_CHAT_ID`; the token does not)
- **Mission (evidence-based)**: Capital/performance reporting — read-only commands `/status /kpis /balance /positions /pnl /phase /regime /risk /health /eo /gate /perf /recap /history /logs /config /get /certif /charts /help` per `docs/architecture/TELEGRAM_BOT_REGISTRY.md:152-202`.
- **Owner**: UNKNOWN (not documented)
- **Status**: ACTIVE
- **Governance gaps**: Chat variable has a partial fallback to the generic `TELEGRAM_CHAT_ID` (token does not) — low risk of a misdirected message if `MON_PORTFOLIO_CHAT_ID` is unset, but not a polling collision since only the token identifies the poller.

---

### [IDENTITY-03] Quant Observer
- **Token Variable**: `QUANT_CRYPTO_BOT_TOKEN`
- **Chat Variable**: `QUANT_CRYPTO_CHAT_ID`
- **Type**: INTERACTIVE
- **Entrypoint**: `src/telegram/quant_observer/bot.py` (also bootstrapped once by `scripts/quant_observer_pin_bootstrap.py`)
- **Service**: `crypto-quant-observer.service` (`scripts/systemd/crypto-quant-observer.service`, `ExecStart=... python -m src.telegram.quant_observer.bot`)
- **Polling (getUpdates)**: YES — `src/telegram/quant_observer/bot.py:73`
- **Push (sendMessage)**: YES — `src/telegram/quant_observer/bot.py:56`; also `sendPhoto` at `src/telegram/quant_observer/bot.py:48`
- **In .env.example**: NO — only present in `.env.secrets.example` (also `QC_PINNED_MSG_ID`, `QC_POLL_INTERVAL`, `QC_PINNED_UPDATE`)
- **In TELEGRAM_BOT_REGISTRY.md**: YES — full profile present ("BOT: Quant Observer" section)
- **Call sites**: `src/telegram/quant_observer/bot.py:25` (`QUANT_CRYPTO_BOT_TOKEN = os.getenv("QUANT_CRYPTO_BOT_TOKEN", "")`), `src/telegram/quant_observer/bot.py:26` (`QUANT_CRYPTO_CHAT_ID = os.getenv("QUANT_CRYPTO_CHAT_ID", "")`), guard raises at `src/telegram/quant_observer/bot.py:213-216` if either is unset
- **Mission (evidence-based)**: Decision-engine microstructure observer — universe scanned, dominant regime, aggregated signal scores, meta-strategy state; explicitly excludes capital/equity/PnL per Registry.
- **Owner**: UNKNOWN (not documented)
- **Status**: ACTIVE
- **Governance gaps**: `.env.example` (the public/onboarding template) does not include this identity, only `.env.secrets.example` does — inconsistent with identities 01/02/04/05/07, which appear in both files.

---

### [IDENTITY-04] Rapport Automatique / Intel
- **Token Variable**: `RAPPORT_AUTOMATIQUE_BOT_TOKEN`
- **Chat Variable**: `RAPPORT_AUTOMATIQUE_CHAT_ID`
- **Type**: PUSH_ONLY
- **Entrypoint**: `quant_hedge_ai/agents/intelligence/system_intel_reporter.py` (builds report content) + `core/advisor_loop.py::_send_intel` (`core/advisor_loop.py:1031-1053`, actual sender)
- **Service**: in-process `crypto-advisor.service` — no dedicated `.service` file.
- **Polling (getUpdates)**: NO — no `getUpdates` call found in either file.
- **Push (sendMessage)**: YES — `core/advisor_loop.py:1048` (`requests.post(f".../bot{token}/sendMessage", ...)`), guarded by `core/advisor_loop.py:1040-1044` (silent no-op + debug log if unset)
- **In .env.example**: YES — `.env.example:74-75`
- **In TELEGRAM_BOT_REGISTRY.md**: YES — full profile present ("BOT: Rapport Automatique" section)
- **Call sites**: `core/advisor_loop.py:792` (`INTEL_TOKEN = os.getenv("RAPPORT_AUTOMATIQUE_BOT_TOKEN", "")`), `core/advisor_loop.py:793` (`INTEL_CHAT = os.getenv("RAPPORT_AUTOMATIQUE_CHAT_ID", "")`)
- **Mission (evidence-based)**: One periodic AI-generated natural-language briefing every ~6h (`INTEL_INTERVAL_S = int(os.getenv("INTEL_REPORT_EVERY_H", "6")) * 3600`, `core/advisor_loop.py:794`), no interactive commands, no polling — comment at `core/advisor_loop.py:1031-1035` explicitly states "Utilise exclusivement RAPPORT_AUTOMATIQUE_BOT_TOKEN + RAPPORT_AUTOMATIQUE_CHAT_ID... Si non configuré : silencieux (pas de fallback vers @QuantCrpto_bot)."
- **Owner**: UNKNOWN (not documented)
- **Status**: ACTIVE
- **Governance gaps**: None found.

---

### [IDENTITY-05] Paper Arena
- **Token Variable**: `PAPER_ARENA_BOT_TOKEN`
- **Chat Variable**: `PAPER_ARENA_CHAT_ID`
- **Type**: PUSH_ONLY
- **Entrypoint**: `src/paper/paper_runner.py` (event triggers) + `src/paper/paper_report.py` (sender)
- **Service**: `paper-arena.service` (`scripts/systemd/paper-arena.service`, `ExecStart=... python3 -m src.paper.paper_runner`)
- **Polling (getUpdates)**: NO — no `getUpdates` call found in either file.
- **Push (sendMessage)**: YES — `src/paper/paper_report.py:23` (`requests.post(f".../bot{_TOKEN}/sendMessage", ...)`)
- **In .env.example**: YES — `.env.example:80-81`
- **In TELEGRAM_BOT_REGISTRY.md**: YES — full profile present ("BOT: Paper Arena" section)
- **Call sites**: `src/paper/paper_report.py:11` (`_TOKEN = os.getenv("PAPER_ARENA_BOT_TOKEN", "")`), `src/paper/paper_report.py:12` (`_CHAT = os.getenv("PAPER_ARENA_CHAT_ID", "")`)
- **Mission (evidence-based)**: Reports the outcome of one isolated research experiment (RSI ETH/4H) — entry/exit notifications, periodic summary, gate status (`INSUFFICIENT_SAMPLE` → `CONCLUSIVE`), scoped strictly to experiment metrics.
- **Owner**: UNKNOWN (not documented)
- **Status**: ACTIVE
- **Governance gaps**: None found. (Noise level flagged elsewhere — `docs/TELEGRAM_NOTIFICATION_AUDIT.md` recommends batching per-trade pushes — but that is a message-volume concern, not an identity governance gap.)

---

### [IDENTITY-06] CMVK / Sim Bot
- **Token Variable**: `TELEMETRIE_IA_BOT_TOKEN`
- **Chat Variable**: `TELEMETRIE_IA_CHAT_ID`
- **Type**: INTERACTIVE (fully wired in code: polling + push + command dispatch)
- **Entrypoint**: `src/telegram/bot_runner.py` (polling loop, `if __name__ == "__main__"` block) + `src/telegram/sim_bot.py` (command handler class `SimBot`)
- **Service**: NONE found — no `.service` file under `scripts/systemd/` references this bot; module docstring at `src/telegram/bot_runner.py:1-6` documents manual invocation only (`python -m src.telegram.bot_runner`).
- **Polling (getUpdates)**: YES — `src/telegram/bot_runner.py:69` (`_call(token, "getUpdates", {"timeout": 0, "offset": -1})`), `src/telegram/bot_runner.py:92` (main long-poll loop)
- **Push (sendMessage)**: YES — `src/telegram/bot_runner.py:39,50` (`_call(..., "sendMessage", ...)`)
- **In .env.example**: NO
- **In TELEGRAM_BOT_REGISTRY.md**: PARTIAL — the Registry's "Bots supprimés" (removed bots) table lists `@FtnTrading_bot` (SimBot) as "Retiré — non utilisé en production" (`docs/architecture/TELEGRAM_BOT_REGISTRY.md:29`), but never names the `TELEMETRIE_IA_BOT_TOKEN`/`TELEMETRIE_IA_CHAT_ID` variables or describes the current READ-ONLY command surface actually present in `src/telegram/sim_bot.py`.
- **Call sites**: `src/telegram/bot_runner.py:148` (`_token = os.environ.get("TELEMETRIE_IA_BOT_TOKEN", "")`), `src/telegram/bot_runner.py:149` (`_chat = os.environ.get("TELEMETRIE_IA_CHAT_ID", "")`), `src/telegram/bot_runner.py:151` (`raise SystemExit(...)` if either is unset)
- **Mission (evidence-based)**: Read-only inspection surface for a simulation/backtesting core: `/run /status /pnl /trades /runs /stress /history /compare /friction /score /distrib /robust /race /validate /overall /breakdown /market /help`. Module docstring in `src/telegram/sim_bot.py` states: "CMVK Experimental Observer — READ-ONLY... This bot observes simulations. It does not control production." Former `/kill`/`/resume` control-command handlers have been removed (verified by `tests/test_sim_bot.py::test_kill_command_removed` / `test_resume_command_removed`, both asserting "Commande inconnue").
- **Owner**: UNKNOWN (not documented)
- **Status**: UNKNOWN — code is wired end-to-end (polling + handler + tests), but there is no deployment evidence: no systemd unit, absent from `.env.example`, and the Registry's own removed-bots table implies it is not used in production under its BotFather name (`@FtnTrading_bot`). The variable pair only appears in `.env.secrets.example`.
- **Governance gaps**: `TELEMETRIE_IA_BOT_TOKEN`/`TELEMETRIE_IA_CHAT_ID` are not named anywhere in `TELEGRAM_BOT_REGISTRY.md`; the Registry entry that plausibly corresponds to this identity uses a different name (`@FtnTrading_bot`) and does not reflect the current read-only command set. Recommend either formally documenting this identity under its real variable names or confirming and recording its retirement in the Registry itself (not just by BotFather username).

---

### [IDENTITY-07] Generic Alerts (Moteur)
- **Token Variable**: `TELEGRAM_BOT_TOKEN`
- **Chat Variable**: `TELEGRAM_CHAT_ID` (primary) / `TELEGRAM_BEHAVIOR_CHAT_ID` (behavioral sub-channel, falls back to `TELEGRAM_CHAT_ID` if unset)
- **Type**: PUSH_ONLY
- **Entrypoint**: Not a single bot — many independent in-process senders, principally `core/advisor_loop.py` (`_telegram`, `_telegram_behavior`), plus standalone scripts: `scripts/telegram_alerts.py`, `supervision/performance_watchdog.py`, `supervision/exchange_monitor.py`, `scripts/daily_signal_report.py`, `scripts/trend_scanner.py`, `watchdog_vps.py`, `scripts/vps_burn_in_collector.py`, `scripts/data_verifier.py` (diagnostic only), `scripts/test_intel_report.py` (diagnostic only), and `config/telegram_config.json` (an alternate JSON config source for this same token, disabled by default — `"enabled": false`, placeholder values — per `scripts/telegram_alerts.py:9-11,36-58`).
- **Service**: None dedicated — consumed in-process by `crypto-advisor.service` and invoked ad hoc by standalone/cron scripts.
- **Polling (getUpdates)**: NO — no `getUpdates` call found against `TELEGRAM_BOT_TOKEN` anywhere in current code.
- **Push (sendMessage)**: YES — `core/advisor_loop.py:938` (`_telegram()`), `core/advisor_loop.py:999` (`_telegram_behavior()`), plus independent senders in the files listed above.
- **In .env.example**: YES — `.env.example:25,27,31`
- **In TELEGRAM_BOT_REGISTRY.md**: PARTIAL — `TELEGRAM_BOT_TOKEN` is named in the "Anomalies résolues" table (`docs/architecture/TELEGRAM_BOT_REGISTRY.md:216`, "`TELEGRAM_BOT_TOKEN` partagé entre KillSwitch et CryptoRadar") as a *historical collision source*, but this identity has no dedicated profile section, no mission statement, no command list, and is not one of the "5 bots actifs" the Registry governs.
- **Call sites**: `core/advisor_loop.py:789` (`TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")`), `core/advisor_loop.py:790` (`TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")`), `core/advisor_loop.py:791` (`TELEGRAM_BEHAVIOR_CHAT = os.getenv("TELEGRAM_BEHAVIOR_CHAT_ID", "")`)
- **Mission (evidence-based)**: Generic push-only alerting facility for the "Moteur" (engine) process — trade/danger/error/heartbeat/daily-summary alerts and behavioral-monitor transitions ([BEHAVIOR], REGIME_MISMATCH, BSM), per `docs/TELEGRAM_NOTIFICATION_AUDIT.md`'s per-call-site inventory (24 call sites in `core/advisor_loop.py` alone).
- **Owner**: UNKNOWN (not documented)
- **Status**: ACTIVE
- **Governance gaps**: This is the busiest identity in the codebase (highest call-site count per `docs/TELEGRAM_NOTIFICATION_AUDIT.md`) yet has no dedicated governance profile in `TELEGRAM_BOT_REGISTRY.md` comparable to identities 01-05 — no mission statement, no allowed/forbidden content list, no named owner. It was also the historical token-sharing source for the now-retired Telegram KillSwitch (`docs/architecture/TELEGRAM_BOT_REGISTRY.md:216`).

---

### [IDENTITY-08] Real Account Bot
- **Token Variable**: `REAL_ACCOUNT_BOT_TOKEN`
- **Chat Variable**: `REAL_ACCOUNT_CHAT_ID`
- **Type**: PUSH_ONLY
- **Entrypoint**: `core/advisor_loop.py::_telegram_real` (`core/advisor_loop.py:1009-1027`)
- **Service**: in-process `crypto-advisor.service` — no dedicated `.service` file.
- **Polling (getUpdates)**: NO — no `getUpdates` call found in `core/advisor_loop.py` for this token.
- **Push (sendMessage)**: YES — `core/advisor_loop.py:1021` (`requests.post(f".../bot{REAL_BOT_TOKEN}/sendMessage", ...)`); called from `core/advisor_loop.py:3483`, `:3495`, `:3516` (boot-time STANDBY/LIVE/NULL-balance alerts) and `:7233` (periodic hourly report, gated by `REAL_BOT_REPORT_EVERY`, default 12 cycles)
- **In .env.example**: NO — absent from `.env.example`; present only in `.env.secrets.example:88-89`
- **In TELEGRAM_BOT_REGISTRY.md**: **NO** (confirmed by direct search — zero occurrences of `REAL_ACCOUNT_BOT_TOKEN` or `REAL_ACCOUNT_CHAT_ID` anywhere in `docs/architecture/TELEGRAM_BOT_REGISTRY.md`) — this is a real governance gap, not a documentation-style choice.
- **Call sites**: `core/advisor_loop.py:796` (`REAL_BOT_TOKEN = os.getenv("REAL_ACCOUNT_BOT_TOKEN", "")`), `core/advisor_loop.py:797` (`REAL_BOT_CHAT = os.getenv("REAL_ACCOUNT_CHAT_ID", "")`)
- **Mission (evidence-based)**: Reports real-exchange account status (MEXC/exchange API balance) — STANDBY while `PAPER_TRADING_ENABLED=true`, LIVE once real trading is active, plus an hourly status report. Docstring at `core/advisor_loop.py:1009-1013`: "Bot compte réel — solde API, STANDBY/LIVE, statut périodique. Canal séparé du bot paper (@QuantCrpto_bot)."
- **Owner**: UNKNOWN (not documented)
- **Status**: ACTIVE
- **Governance gaps (CRITICAL)**:
  1. Entirely undocumented in `TELEGRAM_BOT_REGISTRY.md` — not one of the "5 bots actifs", no mission/authority/criticality/allowed-forbidden section.
  2. Absent from `.env.example` (the public onboarding template) — a new operator following that file alone would never discover this identity exists.
  3. Per `.env.secrets.example:74-90` (Bot 5/8 section), `REAL_ACCOUNT_BOT_TOKEN` and `MON_PORTFOLIO_BOT_TOKEN` are documented as **receiving the same physical BotFather token** (`@mon_portfolio_bot`), used for two different send-only purposes on that one token: `_telegram_real()` (this identity) and the CommandCenter's periodic report (identity 02). The comment explicitly warns this is safe only because the CommandCenter (identity 02) is the sole `getUpdates` poller for that token ("UN SEUL poller autorisé par token"). This shared-token relationship is not recorded anywhere in `TELEGRAM_BOT_REGISTRY.md` and represents a latent 409-conflict risk if this were ever changed.
  - This finding matches and is independently corroborated by `docs/TELEGRAM_NOTIFICATION_AUDIT.md` ("🔴 Real Account Bot... **undocumented, new finding**").

---

### [IDENTITY-09] KillSwitch (legacy, dead code)
- **Token Variable**: `KILLSWITCH_BOT_TOKEN` (name only — never wired to `os.getenv` anywhere in the codebase)
- **Chat Variable**: `KILLSWITCH_CHAT_ID` (same — never wired)
- **Type**: DEAD_CODE
- **Entrypoint**: `supervision/kill_switch.py::TelegramKillSwitch` (class definition only; only instantiation found is in the class's own docstring example)
- **Service**: NONE
- **Polling (getUpdates)**: The class's own code contains a `getUpdates`-style polling method, but it is never executed in the live code path — `core/advisor_loop.py` imports `runtime.TelegramKillSwitch`, which resolves to `supervision/killswitch_hardened.py::KillSwitchHardened` (zero Telegram references in that file).
- **Push (sendMessage)**: Present in the class's own code (same dead-code caveat) — never reachable from the active kill-switch path.
- **In .env.example**: NO
- **In .env.secrets.example**: NO (confirmed by direct search — variable names appear in neither `.env` template file)
- **In TELEGRAM_BOT_REGISTRY.md**: PARTIAL — mentioned twice in prose, never as a governed identity profile: "Bots supprimés" table (`docs/architecture/TELEGRAM_BOT_REGISTRY.md:24`, "`@Connexion_VScode_bot` (KillSwitch) | Retiré — constitution 2026-08-28") and Phase 3 finalization notes (`docs/architecture/TELEGRAM_BOT_REGISTRY.md:345`, "Supprimer : KILLSWITCH_BOT_TOKEN / KILLSWITCH_CHAT_ID (plus utilisés)").
- **Call sites**: None — no `os.getenv("KILLSWITCH_BOT_TOKEN")` or `os.getenv("KILLSWITCH_CHAT_ID")` found anywhere in the repository.
- **Mission (evidence-based)**: Historical kill-switch control interface (`/STOP_ALL /CLOSE_ALL /SAFE_MODE /RESUME /STATUS`) — all control commands, which would violate the current constitutional read-only rule if ever reactivated. Explicitly retired per Registry.
- **Owner**: UNKNOWN
- **Status**: DEAD_CODE
- **Governance gaps**: The `TelegramKillSwitch` class and its `getUpdates`/`sendMessage` methods remain physically present in `supervision/kill_switch.py`, unreachable but not deleted — a latent risk if anyone re-instantiates it with a real token (flagged identically and independently in `docs/TELEGRAM_ARCHITECTURE_AUDIT.md` and `docs/architecture/TELEGRAM_ECOSYSTEM_MAP.md`). Physical removal is a code change and is out of scope for this read-only audit.

---

### [IDENTITY-10] Narrator / Télémétrie IA
- **Token Variable**: `NARRATOR_BOT_TOKEN`
- **Chat Variable**: `NARRATOR_CHAT_ID`
- **Type**: DEAD_CODE
- **Entrypoint**: NONE — no file in the current repository references `NARRATOR_BOT_TOKEN` or `NARRATOR_CHAT_ID` via `os.getenv`/`os.environ`. The only occurrences anywhere in the repository are two **commented-out** placeholder lines in `.env.secrets.example:51-52`.
- **Service**: NONE found.
- **Polling (getUpdates)**: UNKNOWN — no code exists to evaluate.
- **Push (sendMessage)**: UNKNOWN — no code exists to evaluate.
- **In .env.example**: NO
- **In .env.secrets.example**: YES, but commented out (`#NARRATOR_BOT_TOKEN=`, `#NARRATOR_CHAT_ID=`)
- **In TELEGRAM_BOT_REGISTRY.md**: PARTIAL — the underlying bot is referenced only under its BotFather username, not this variable pair: "Bots supprimés" table lists `@Telemetrie_IA_bot` | "Retiré — non utilisé (service inactif)" (`docs/architecture/TELEGRAM_BOT_REGISTRY.md:28`). The `NARRATOR_BOT_TOKEN`/`NARRATOR_CHAT_ID` variable names themselves do not appear in this document at all.
- **Call sites**: None found.
- **Mission (evidence-based)**: Per the surrounding comment in `.env.secrets.example:43-50` ("Bot 2/8 : @Telemetrie_IA_bot"): "Rôle CODE : AUCUN dans main. Module observability/narrator SUPPRIMÉ du disque, process PID 504 vit en mémoire depuis Aug 24 (zombie DS-002 v2). À tuer proprement — ne PAS renseigner de token ici tant que le code n'est pas restauré ou l'ADR 'narrateur retiré' signé." This scan confirms the code half of that claim: no `observability/narrator` module or file matching `*narrator*` exists anywhere in the current repository (`observability/` was enumerated directly — no narrator-related file present). The claim of a live zombie process (PID 504) is an operational/runtime assertion that cannot be verified or refuted from repository contents alone.
- **Owner**: UNKNOWN
- **Status**: DEAD_CODE (from the repository's point of view — the module has been deleted; the alleged live zombie process, if real, is a VPS runtime-state matter outside this repo's scope)
- **Governance gaps**:
  1. This is the only identity discovered during the broad sweep (`*_BOT_TOKEN`/`*_TOKEN`/`*_CHAT_ID`) that does not appear, under its actual variable names, in **any** of the five prior Telegram governance/audit documents (`TELEGRAM_BOT_REGISTRY.md`, `TELEGRAM_CONSTITUTION.md`, `TELEGRAM_BOT_CONSTITUTION.md`, `TELEGRAM_ARCHITECTURE_AUDIT.md`, `TELEGRAM_NOTIFICATION_AUDIT.md`, `TELEGRAM_ECOSYSTEM_MAP.md` — confirmed by direct search, zero hits for "NARRATOR" in any of them).
  2. The `.env.secrets.example` comment describes an unresolved operational hazard (an alleged running zombie process for code that has been deleted) that references an incident label (`DS-002 v2`) and an unsigned ADR ("l'ADR 'narrateur retiré' signé") — if that ADR does not yet exist, this is an explicit signal that formal retirement of this identity is incomplete even though the code is gone.

---

## Governance Gap Summary

| Identity | Issue | Severity | Recommended Action |
|---|---|---|---|
| IDENTITY-08 Real Account Bot | **MERGED** — `REAL_ACCOUNT_BOT_TOKEN` deleted; routes via `MON_PORTFOLIO_BOT_TOKEN` (same physical token, operator confirmed 2026-08-28) | RESOLVED | No further action required |
| IDENTITY-08 Real Account Bot | Shares the same physical BotFather token as IDENTITY-02 (Portfolio) per `.env.secrets.example:74-90`, relying on an unenforced "single poller" convention | HIGH | Document the shared-token relationship explicitly in `TELEGRAM_BOT_REGISTRY.md` so future changes to either bot's polling behavior are made with full awareness of the collision risk |
| IDENTITY-07 Generic Alerts | Busiest identity by call-site count (per `TELEGRAM_NOTIFICATION_AUDIT.md`), but has no dedicated mission/ownership profile comparable to identities 01-05 | HIGH | Add a profile section to `TELEGRAM_BOT_REGISTRY.md` defining scope, allowed content, and an owner for this channel |
| IDENTITY-06 CMVK / Sim Bot | Registry only references this bot by a different BotFather name (`@FtnTrading_bot`) and does not reflect its current read-only command set or actual env var names | MEDIUM | Either formally document `TELEMETRIE_IA_BOT_TOKEN`/`TELEMETRIE_IA_CHAT_ID` under their real names in the Registry, or explicitly record retirement decisions against those variable names |
| IDENTITY-10 Narrator | Variable names never documented anywhere; code deleted but comment implies an unresolved live-process hazard and an unsigned retirement ADR | MEDIUM | Confirm VPS process state out-of-repo; if confirmed dead, formally close via a signed ADR referenced from the Registry; if a zombie process is confirmed alive, escalate as an operational incident (out of scope for this document) |
| IDENTITY-09 KillSwitch | `TelegramKillSwitch` class remains in `supervision/kill_switch.py`, unreachable but not deleted | LOW | Track physical removal as a future cleanup item (code change, out of scope here) |
| IDENTITY-03 Quant Observer | Present in `.env.secrets.example` but not `.env.example`, unlike other active identities | LOW | Add `QUANT_CRYPTO_BOT_TOKEN`/`QUANT_CRYPTO_CHAT_ID` (and related `QC_*` tuning vars) to `.env.example` for onboarding consistency |
| IDENTITY-02 Portfolio | `MON_PORTFOLIO_CHAT_ID` falls back to generic `TELEGRAM_CHAT_ID` if unset (token has no such fallback) | LOW | No action required; documented behavior, low risk (misdirected message only, no polling collision) |

Severity: CRITICAL / HIGH / MEDIUM / LOW

---

## Identity Decision Matrix

| Identity | Decision | Rationale |
|---|---|---|
| IDENTITY-01 CryptoRadar | KEEP | Active, fully documented, isolated token, no fallback |
| IDENTITY-02 Portfolio (CommandCenter) | KEEP | Active, fully documented, minor chat-fallback is low risk |
| IDENTITY-03 Quant Observer | KEEP + DOCUMENT | Active and documented functionally; add to `.env.example` for consistency |
| IDENTITY-04 Rapport Automatique / Intel | KEEP | Active, fully documented, push-only, no anomalies found |
| IDENTITY-05 Paper Arena | KEEP | Active, fully documented; noise-reduction is a message-volume matter, not an identity issue |
| IDENTITY-06 CMVK / Sim Bot | DOCUMENT or REMOVE | Code is read-only compliant and fully wired, but no deployment evidence exists; operator should confirm intended use and update the Registry accordingly under the real variable names |
| IDENTITY-07 Generic Alerts (Moteur) | DOCUMENT | Active and heavily used; needs a formal Registry profile matching identities 01-05 |
| IDENTITY-08 Real Account Bot | MERGED → IDENTITY-02 | Same physical token as Portfolio; `REAL_ACCOUNT_BOT_TOKEN` variable deleted (2026-08-28) |
| IDENTITY-09 KillSwitch (legacy) | REMOVE (code, future) | Confirmed dead, constitutionally prohibited if reactivated; already recorded as retired |
| IDENTITY-10 Narrator | REMOVE (formalize) | Code confirmed deleted; needs a signed ADR to close the loop referenced in its own `.env.secrets.example` comment |

---

## Cross-Reference

| Document | Coverage |
|---|---|
| `docs/TELEGRAM_ARCHITECTURE_AUDIT.md` | 9 identities covered (01-07, 09, plus an archived-duplicates row and the `config/telegram_config.json` config-source note; does not cover IDENTITY-10 Narrator) |
| `docs/architecture/TELEGRAM_BOT_REGISTRY.md` | 5 identities covered with full governance profiles (01-05); IDENTITY-06, 07, 09, 10 mentioned only in prose/anomalies tables under different names or no name; IDENTITY-08 not covered at all |
| `docs/architecture/TELEGRAM_ECOSYSTEM_MAP.md` | 8 identities covered (01-07, 09, plus explicit "Channel: NOT FOUND"); does not cover IDENTITY-08 Real Account Bot or IDENTITY-10 Narrator |
| `docs/TELEGRAM_NOTIFICATION_AUDIT.md` | 10 message-source groups covered at the call-site level, including IDENTITY-08 Real Account Bot (flagged as its own "undocumented, new finding") and dead code rows; does not enumerate IDENTITY-10 Narrator (no code exists to inventory messages for) |
| **This document** | **7 official identities** (10 found, IDENTITY-08 merged, 09+10 dead code) |
