# Telegram Bot Constitution
> Last updated: 2026-08-28

This document defines the mission profile for each proven-active Telegram bot
in this repository, based strictly on code evidence gathered in
`docs/architecture/TELEGRAM_ECOSYSTEM_MAP.md`. It complements the existing
`docs/TELEGRAM_CONSTITUTION.md` (constitutional principles) and
`docs/architecture/TELEGRAM_BOT_REGISTRY.md` (functional contract) — it does
not supersede either.

---

## Constitutional Rule (applies to ALL bots)

Telegram bots are STRICTLY read-only observation interfaces.

They MUST NOT: modify parameters, start/stop strategies, change portfolio,
execute trades, modify config files, restart services.

They MUST: observe, filter, summarize, alert humans.

Any bot or code path found violating this rule (even if currently inactive or
undeployed) is a constitutional risk and must be flagged, not silently
tolerated. See Bot 6 (CMVK/Simulation) below for one such flagged risk.

---

## Bot 1 — CryptoRadar

### Mission
Detect unusual market phenomena that merit human attention — "Where is
something happening in the market right now?"

### Must Do
- Scan market data (universe regime, per-symbol confidence scores, dominant
  direction, LMI microstructure)
- Filter noise (only exceptional/aggregated events)
- Send anomaly summaries on request

### Must Never Do
- Send per-symbol routine status spam (BTC bullish, ETH bearish for every
  symbol on a timer)
- Expose Entry/SL/TP or portfolio/equity/PnL data (explicitly out of domain —
  redirects `/signals` and `/status` to the correct bot, per
  `scripts/radar_bot.py` and `docs/architecture/TELEGRAM_BOT_REGISTRY.md`)
- Control trading decisions or modify parameters

### Inputs
- Market/universe scan data consumed by `scripts/radar_bot.py` (regime,
  per-symbol confidence, direction, LMI microstructure) from the databases
  under `DP_LOG_DIR` (see `scripts/radar_bot.py:16`)

### Outputs
- On-demand command replies only: `/scan [N]`, `/top50`, `/longs`, `/shorts`,
  `/symbol TICKER`, `/lmi [TICKER]`, `/help` (via `sendMessage`,
  `scripts/radar_bot.py:49`)
- No automatic/unsolicited push messages found in code

### Target Message Format
```
📡 CryptoRadar — Top 5 opportunités (conf ≥ 60)
1. BTCUSDT  LONG  conf=78  régime=trend
2. ETHUSDT  SHORT conf=71  régime=range
...
```

### Human Value
Answers "where is something happening in the market right now?" without
requiring the operator to watch every symbol manually.

### Noise Reduction Target
Already LOW (fully reactive, no scheduled push) — no reduction needed;
maintain current behavior.

---

## Bot 2 — Portfolio Command Center

### Mission
Show whether the machine is actually making money — "Is my machine really
earning money?"

### Must Do
- Report capital, phase, KPIs (win rate, Sharpe, drawdown, trade count),
  positions, PnL, risk state (read-only)
- Send periodic performance reports and drawdown alerts

### Must Never Do
- Expose per-symbol trading signals (explicitly removed — see
  `docs/architecture/TELEGRAM_BOT_REGISTRY.md`, "Anomalies résolues" #5)
- Accept any write command (`/pause`, `/resume`, `/set`, `/setphase`,
  `/maxorder`, `/reset`, `/restart` — all explicitly removed per the
  Registry's "Anomalies résolues" #7)
- Expose Paper Arena experiment data (separate domain)

### Inputs
- Capital, phase, KPI, and position state consumed by
  `capital_deployment/command_center_bot.py` from the trading engine's
  read-only state stores

### Outputs
- Periodic report on interval `P10_PORTFOLIO_REPORT_MINS`/`_H`
- On-demand command replies: `/status`, `/kpis`, `/balance`, `/positions`,
  `/pnl`, `/phase`, `/regime`, `/risk`, `/health`, `/eo`, `/gate`, `/perf`,
  `/recap [N]`, `/history [N]`, `/logs [N]`, `/config`, `/get PARAM`,
  `/certif`, `/charts`, `/help` (all read-only)

### Target Message Format
```
💼 Portfolio — Recap
Phase: F-12 | Capital: <paper> | Régime: trend
Win Rate: 58% | Sharpe: 1.2 | DD: 4.1% | Trades: 212
```

### Human Value
Answers "is my machine really earning money?" with a single glance, without
needing to inspect raw logs or databases.

### Noise Reduction Target
From MEDIUM (configurable periodic report + drawdown alerts) to LOW —
ensure the periodic report interval is wide enough that each message
represents a meaningful state change rather than a routine heartbeat.

---

## Bot 3 — Quant Observer

### Mission
Document what is happening in the decision engine's microstructure —
"What is happening in the microstructure of the decision system?"

### Must Do
- Report scanned universe size, dominant regime (global + distribution),
  aggregated signal scores, actionable candidates (without Entry/SL/TP),
  meta-strategy state, decision pipeline health

### Must Never Do
- Expose portfolio equity/PnL/balances or real positions (Portfolio's domain)
- Expose raw RAM/CPU/PID system metrics
- Expose Paper Arena experiment data
- Accept any control command

### Inputs
- Universe/regime/signal-score/meta-strategy state consumed by
  `src/telegram/quant_observer/bot.py`

### Outputs
- Auto-refreshed pinned message (`QC_PINNED_UPDATE`, default 600s = 10 min)
- On-demand command replies: `/snapshot`, `/health`, `/pipeline`, `/help`

### Target Message Format
```
🔬 Quant Observer — Snapshot
Universe: 135 paires | Régime dominant: trend (62%)
Candidats actionnables: 4 | Pipeline: nominal
```

### Human Value
Answers "what is happening in the microstructure of the decision system?" —
a research-facing view that does not touch capital or execution.

### Noise Reduction Target
From MEDIUM (10-minute pinned refresh is a continuous stream) to LOW —
refresh the pinned message only on significant regime/state change, or widen
the interval (e.g. 30–60 min), per the recommendation already recorded in
`docs/TELEGRAM_ARCHITECTURE_AUDIT.md`.

---

## Bot 4 — Rapport Automatique / Intel

### Mission
Deliver a periodic AI-generated natural-language synthesis of system state —
no interaction, pure information.

### Must Do
- Send one periodic synthesis briefing (~every 6 hours) summarizing system
  state in natural language

### Must Never Do
- Accept any interactive command (confirmed: no `getUpdates` call exists in
  either `quant_hedge_ai/agents/intelligence/system_intel_reporter.py` or the
  sender in `core/advisor_loop.py`)
- Dump raw logs instead of a conclusion

### Inputs
- System-wide state aggregated by
  `quant_hedge_ai/agents/intelligence/system_intel_reporter.py::SystemIntelReporter.build_report`

### Outputs
- Single push message per cycle via `core/advisor_loop.py::_send_intel`
  (`sendMessage`, `core/advisor_loop.py:1046`)

### Target Message Format
```
🧠 Rapport Automatique — Synthèse 6h
Régime dominant stable depuis 18h. Aucune anomalie critique détectée.
CRI: 42/100 (calibration toujours interdite, N insuffisant).
```

### Human Value
Gives the operator a periodic high-level "state of the system" narrative
without requiring them to actively check anything.

### Noise Reduction Target
Already LOW-MEDIUM (fixed 6h cadence, push-only, no polling) — ensure content
stays a statistical conclusion, never a raw log dump, per Constitution
Principle 10.

---

## Bot 5 — Paper Arena

### Mission
Report whether a research hypothesis survives contact with real data — "Does
this research hypothesis survive real data?"

### Must Do
- Report the outcome of one isolated experiment (RSI ETH/4H): entry/exit
  events, periodic aggregate summary, gate status
  (`INSUFFICIENT_SAMPLE` → `CONCLUSIVE`)

### Must Never Do
- Expose global system state, portfolio balances, or global PnL (explicitly
  scoped to the experiment only, per
  `docs/architecture/TELEGRAM_BOT_REGISTRY.md` "FORBIDDEN" section)
- Accept any interactive command (confirmed: no `getUpdates` found in
  `src/paper/paper_runner.py` or `src/paper/paper_report.py`)

### Inputs
- Experiment trade events and metrics from `src/paper/paper_runner.py`
  (`PaperMetrics`, gate status via `src/paper/paper_gate.py`)

### Outputs
- `notify_entry`, `notify_exit`, `notify_summary` — all `sendMessage` calls
  in `src/paper/paper_report.py`

### Target Message Format
```
🧪 Paper Arena — Résumé (N=87)
WR: 54% | PF: 1.3 | PnL exp.: +2.1%
Gate: INSUFFICIENT_SAMPLE (N<500)
```

### Human Value
Answers "does this research hypothesis survive real data?" with statistical
conclusions rather than trade-by-trade noise.

### Noise Reduction Target
From MEDIUM-HIGH (per-trade entry/exit notifications) to LOW — replace
trade-by-trade push with a daily/weekly aggregate (N trades, WR, PF), and
keep gate-status changes as the only rare, high-value event, per the
recommendation already recorded in `docs/TELEGRAM_ARCHITECTURE_AUDIT.md`.

---

## Bot 6 — CMVK/Simulation

### Status: UNKNOWN — PENDING AUDIT

### What We Know
- Token/chat variables `CMVK_BOT_TOKEN` / `CMVK_CHAT_ID` are wired end-to-end:
  a full polling loop exists in `src/telegram/bot_runner.py` (`getUpdates`,
  `sendMessage`, `deleteWebhook` for 409-conflict recovery), dispatching to
  `src/telegram/sim_bot.py::SimBot.handle`.
- `src/telegram/sim_bot.py` docstring (lines 2-3) states: "SimBot — Telegram
  bot exclusivement dédié au noyau de simulation CMVK."
- Command surface includes read-only inspection commands (`/status`, `/pnl`,
  `/trades`, `/runs`, `/history`, `/compare`, `/score`, `/distrib`, `/robust`,
  `/race`, `/validate`, `/overall`, `/breakdown`, `/market`) **and two control
  commands, `/kill` and `/resume`** (`src/telegram/sim_bot.py:1174-1180`),
  which trigger/release a kill-switch object — a constitutional violation of
  "read-only observation only" if this bot is ever activated, regardless of
  the fact that the kill-switch scope appears limited to the CMVK simulation
  core rather than live trading.
- `CMVK_BOT_TOKEN`/`CMVK_CHAT_ID` appear only in `.env.secrets.example`
  (line 117-118), not in `.env.example`.
- No systemd `.service` file references this bot anywhere under
  `scripts/systemd/`.
- `docs/architecture/TELEGRAM_BOT_REGISTRY.md` ("Bots supprimés" table) lists
  `@FtnTrading_bot` (SimBot) as **removed — "non utilisé en production"**,
  which appears to match this same code by description, though the exact
  BotFather username could not be independently confirmed from code alone.
- `docs/TELEGRAM_ARCHITECTURE_AUDIT.md` independently reached the same
  UNKNOWN/likely-inactive conclusion for this bot in the prior audit.

### What We Don't Know
- Mission (is it still needed for CMVK simulation research, or fully retired?)
- Owner
- Active usage (no deployment evidence — no service file, no
  `.env.example` entry, no reference outside its own module and
  `tests/test_sim_bot.py`)

### Decision Required
Operator must decide: **KEEP** (define mission, add a dedicated systemd
service, and remove or gate the `/kill`/`/resume` control commands to
restore constitutional compliance) or **REMOVE** (delete
`src/telegram/bot_runner.py` and `src/telegram/sim_bot.py`, or move them to
an archive folder consistent with other retired duplicates in
`_ARCHIVE_2026/`).
