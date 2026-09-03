# Telegram Bot Registry

Mission O-01 · Factual inventory/migration map, built from a read-only
forensic pass over `src/telegram/`, `capital_deployment/
command_center_bot.py`, `scripts/radar_bot.py`, `src/paper/`,
`scripts/systemd/*.service`, and `.env.example`/`.env.secrets.example`.
No Telegram bot code was modified to produce this document, and none is
modified by O-01.

## @QuantCrpto_bot — "Quant Observer"

- **Role**: read-only visualization client for the decision engine's
  microstructure state. Docstring: "The bot contains ZERO business
  logic" (`src/telegram/quant_observer/bot.py:1-8`).
- **Current producer**: none in-bot — delegates to
  `visualization.api.load_quant_live_snapshot()` and
  `visualization.ves.VisualizationEngine`.
- **Current data sources**: `QuantLiveSnapshot` projection object only.
- **Current metrics**: engine version/cycle, snapshot age, market/API
  health, regime, exchange latency/uptime, decision state, top candidate
  score vs. required score, mean signal score, reason/gate text, refusal
  breakdown + total, dominant filter %, pipeline stage status (already
  self-labeled "REPORTED/PARTIAL" by the bot), decision trace (already
  self-labeled "PARTIAL"). Explicitly excludes portfolio/capital/PnL/
  win-rate.
- **Duplicated calculations**: none found — `render_quant_live_panel()`
  is a pure formatter.
- **Message lifecycle**: commands send fresh messages; the pinned LIVE
  panel is edited in place via a SHA-256 change-driven fingerprint, plus
  a 1800s safety refresh. Pin is created once by a manual bootstrap
  script (`scripts/quant_observer_pin_bootstrap.py`), not by the running
  service itself. `/portfolio` is explicitly redirected/refused.
- **Canonical O-01 modules it should consume**: `system_health`,
  `market_state`, `decision_pipeline`, `attrition`, `data_freshness`,
  `operator_summary`.
- **Gaps**: not documented in `.env.example` despite heavy use in
  systemd comments.
- **O-02 migration priority**: **highest** — this is the bot with the
  already-approved single-message/no-pin/French-labels requirement (see
  `OPERATOR_DISPLAY_CONTRACT.md`).

## @mon_portfolio_bot — "Portfolio" (Command Center)

- **Role**: read-only KPI/capital/positions surface — "Répond à une
  seule question : Est-ce que ma machine gagne de l'argent ?"
  (`capital_deployment/command_center_bot.py:5`). All write commands are
  hard-blocked with a fixed refusal message.
- **Current producer**: `CommandDataProvider` callbacks injected from
  `core/advisor_loop.py`.
- **Current data sources**: in-process closures over live advisor-loop
  state — `PhaseKPITracker`, `exec_engine.fetch_available_capital()`,
  `_paper_equity_display()`, `paper_trading.recorder`, `black_box`,
  `gate._last_snapshot`, `.env` (for `/config`/`/get`), log files (for
  `/logs`).
- **Current metrics**: win rate, Sharpe, max/current drawdown, total
  trades (`/status`, `/kpis`); spot/futures balances (`/balance`);
  position detail (`/positions`); risk-engine snapshots (`/eo`, `/gate`);
  ASCII PnL curve and history (`/perf`, `/recap`, `/history`).
- **Duplicated calculations**: minimal for core metrics (reads
  `PhaseKPITracker` rather than recomputing win-rate/Sharpe/DD itself);
  presentation-layer arithmetic only (bar charts, % distance from entry,
  cumulative-PnL sampling).
- **Critical finding — unlabeled paper/real pairing**: the `/kpis`/
  `/status` KPI block (win rate, Sharpe, drawdown, total trades) is
  computed exclusively from **paper trades**
  (`paper_trading.recorder.get_recorder().get_trades()`), yet
  `PhaseKPITracker` is initialized with `initial_capital=real_capital`
  (the **real** allocated capital shown in the same message). Neither
  block states "paper" or "real" next to the numbers — a reader could
  reasonably assume the KPIs apply to the real-capital figure shown
  above them. See `METRIC_DICTIONARY.md` Part 2 and
  `OPERATOR_DISPLAY_CONTRACT.md` rule 6.
- **Related orphaned module**: `src/telegram/exchange_sync.py` claims in
  its own docstring to be the "CCXT read-only sync pour
  @mon_portfolio_bot" with its own independent balance/PnL/drawdown
  computation, but is never imported anywhere in the repository —
  dead/duplicate code, not wired into `command_center_bot.py`.
- **Two independent senders on one identity**: `CommandCenterBot.send()`
  and the separate `src/telegram/notifier.py::Notifier._send()` both post
  to the same bot/chat with no shared rate limiting or dedup.
- **Message lifecycle**: every reply is a fresh `sendMessage`; no
  edit/pin/delete. An auto "connected" banner is throttled to once per
  5 minutes; an auto report loop sends a new message every
  `P10_PORTFOLIO_REPORT_H` (default 1h).
- **Canonical O-01 modules it should consume**: `portfolio_state`,
  `execution_state`, `system_health` (real-account connectivity).
- **Gaps**: `MON_PORTFOLIO_CHAT_ID` silently falls back to the generic
  `TELEGRAM_CHAT_ID` if unset — could misroute to the wrong chat.
- **O-02 migration priority**: **high** — the paper/real KPI pairing is
  a scientific-communication risk that should be fixed early.

## @PaperArena_bot

- **Role**: a single hard-coded research experiment — "L'edge observé en
  recherche survit-il à des données réelles ?" (ETH/USDT 4h RSI 15/85).
- **Current producer**: `src/paper/paper_runner.py::run_paper_arena()` —
  its own loop, its own hand-duplicated ENL friction model (`_enl_fill()`
  mirrors `src/execution/enl.py`'s `ENLConfig.light` rather than
  importing it), `PaperPositionManager`, `PaperMetrics`.
- **Current data sources**: public MEXC candle API only; no exchange
  keys, no shared engine state.
- **Current metrics**: entry/exit fields explicitly prefixed "Paper
  Equity"/"PAPER ENTRY/EXIT" (`src/paper/paper_report.py`); summary
  block with equity, signal/trade counts, win rate, profit factor,
  expectancy, avg/median trade, max DD %, avg hold, ENL cost, gate
  status. No paper/real ambiguity here — every figure is explicitly
  labeled paper.
- **Duplicated calculations**: `_enl_fill()` reimplements ENL friction
  math by hand instead of importing `src/execution/enl.py` — a drift
  risk if the canonical friction model changes.
- **Message lifecycle**: independent `sendMessage` per notification; no
  edit/pin/delete.
- **Canonical O-01 modules it should consume**: `execution_state`,
  `portfolio_state` (as its own isolated-experiment scope, not conflated
  with the main system's paper equity).
- **Gaps**: none major.
- **O-02 migration priority**: low — already clean, isolated, and
  correctly labeled.

## @Telemetrie_IA_bot — "CMVK / Sim Bot"

- **Role**: "CMVK Experimental Observer — READ-ONLY... does not control
  production" (`src/telegram/sim_bot.py:6-9`). Runs synthetic/MEXC-replay
  backtests on command.
- **Current producer**: `SimBot` — builds its own `BacktestEngine`/
  `VirtualExchange`/`RunContext` per command; persists to
  `RunRepository` (`databases/sim_runs.sqlite`).
- **Current data sources**: synthetic candle generator or MEXC candle
  replay; local SQLite run history.
- **Current metrics**: PnL, win rate, max DD, regime, trade counts per
  run; stress/robustness/race tables; A/B expectancy deltas; PnL
  concentration/percentiles; Edge Scoring System matrix.
- **Duplicated calculations**: `_cmd_compare`, `_cmd_race`, and
  `_cmd_validate` each define a local `_agg()` reimplementing profit-
  factor/expectancy/avg-DD aggregation, **instead of** using the shared
  `src/analytics/performance_breakdown.breakdown()` that `_cmd_stress`/
  `_cmd_overall`/`_cmd_breakdown` already use in the same file — three
  near-identical, independently-maintained aggregation implementations.
- **Cross-wiring finding**: `SimBot` instantiates its own
  `Notifier()` internally, which posts a subset of its run/stress/
  robustness/race summaries to **@mon_portfolio_bot** rather than to
  Telemetrie_IA's own chat — an unlabeled identity crossover between two
  supposedly-separate bots.
- **Message lifecycle**: long-poll `getUpdates`, in-memory dedup
  (capped at 500 seen ids), fresh `sendMessage` per reply, Markdown with
  plaintext fallback.
- **Systemd/process ownership**: **none found.** No `.service` file
  references `bot_runner.py` or `TELEMETRIE_IA_BOT_TOKEN`.
- **Env**: `TELEMETRIE_IA_BOT_TOKEN`/`TELEMETRIE_IA_CHAT_ID` appear only
  in `.env.secrets.example` (commented "was: CMVK_BOT_TOKEN"), absent
  from `.env.example`. A prior internal audit
  (`docs/architecture/TELEGRAM_BOT_REGISTRY.md`) names this identity
  `@FtnTrading_bot` — a different BotFather name than the env vars
  imply. Status genuinely unresolved from code alone.
- **Canonical O-01 modules it should consume**: `system_health`,
  `data_freshness`, `disk_io` — **if** this bot is repurposed as the
  telemetry/health bot its name implies; today its actual commands are
  backtest/simulation tooling, not machine telemetry, and its metrics
  are marked `SOURCE_UNRESOLVED` in `METRIC_DICTIONARY.md` as operator-
  health signals.
- **Gaps**: no deployment evidence, identity/naming mismatch, unlabeled
  cross-posting to the Portfolio bot's chat.
- **O-02 migration priority**: **needs identity resolution before any
  migration** — cannot safely map to canonical modules until it is
  confirmed which bot this actually is and whether it is deployed at
  all.

## @RadarCrypto1_bot — "CryptoRadar"

- **Role**: market-wide opportunity scanner — "Où se passe-t-il quelque
  chose sur le marché ?" Explicitly excludes Entry/SL/TP, portfolio, and
  system metrics from its own commands.
- **Current producer**: `scripts/radar_bot.py` itself —
  `compute_symbol_stats()` aggregates confidence/side-dominance/regime
  directly from raw decision packets.
- **Current data sources**: reads `databases/decision_packets_{date}.
  jsonl` directly off disk for the trailing 24h; `/lmi` delegates to
  `trade_analysis.integrations.radar_adapter`.
- **Current metrics**: per-symbol avg/max confidence, dominant side %,
  regime (`/scan`, `/top50`); directional lists (`/longs`, `/shorts`);
  per-symbol detail (`/symbol`); microstructure overview (`/lmi`).
- **Duplicated calculations**: `compute_symbol_stats()` and
  `extract_signals()` independently parse and aggregate the same
  decision-packet files that other subsystems (advisor loop, dashboards)
  also read — no shared canonical decision-packet aggregator is used.
  `extract_signals()` even computes Entry/SL/TP risk/reward but is
  explicitly marked "internal use only" and is dead/unreachable from any
  Telegram command.
- **Message lifecycle**: fresh `sendMessage` per reply, chunked at 4000
  chars; no edit/pin/delete. Token isolation is enforced in code (exits
  if `RADAR_BOT_TOKEN` unset, no fallback to a generic token).
- **Canonical O-01 modules it should consume**: `market_state`
  (interactive market view) — currently stable, minimize future changes
  per the mission's own guidance.
- **Gaps**: none major; well isolated per its own "constitution"
  comments.
- **O-02 migration priority**: low — stable and correctly scoped;
  migration should be minimal.

## Cross-bot findings

- **No literal summation of paper and real capital** was found anywhere.
  `observability/real_accounts.py`'s isolation of real-account data is a
  designed guardrail, correctly preserved everywhere it's used.
- **The one real presentation-level ambiguity** is `@mon_portfolio_bot`'s
  `/kpis`/`/status` pairing (see above) — a labeling gap, not a
  computation bug.
- **Two independent senders on the Portfolio bot identity**
  (`CommandCenterBot` and `Notifier`, plus `SimBot`'s cross-posting)
  point to a broader need, for O-02, to define one send/edit owner per
  bot identity.
- **Three separate hand-duplicated performance-aggregation
  implementations** exist across `sim_bot.py` alone, alongside the
  shared `performance_breakdown.breakdown()` the same file already uses
  elsewhere — a concrete instance of the "presentation layer
  recalculates canonical metrics" anti-pattern `OPERATOR_DISPLAY_
  CONTRACT.md` rule 1 exists to prevent.
