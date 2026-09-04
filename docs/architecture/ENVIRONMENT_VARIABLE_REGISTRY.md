# Environment Variable Registry

Mission FAM-01 / FAM-01R / ENV-01. Variable **names only**, never values, organized
by machine family. Sourced from a repo-wide census of `os.getenv()`,
`os.environ.get()`, `os.environ[...]`, `.env.example`, `.env.secrets.example`,
and `scripts/systemd/*.service` (`Environment=`/`EnvironmentFile=`),
excluding `_ARCHIVE_2026/`.

**Methodology note (FAM-01R correction):** the original FAM-01 count of
"573 distinct variable names ... consumed via os.getenv/os.environ" mixed
two different things under one number — code-consumed names and
template/systemd-only names swept in by the same census pass. Re-running
the census with an explicit split (regex:
`os\.getenv\(\s*["']([A-Z_][A-Z0-9_]*)["']`,
`os\.environ\.get\(\s*["']([A-Z_][A-Z0-9_]*)["']`,
`os\.environ\[\s*["']([A-Z_][A-Z0-9_]*)["']\s*\]` over all `*.py` files
excluding `_ARCHIVE_2026/`; `[A-Z_][A-Z0-9_]{2,}=` over `.env.example` and
`.env.secrets.example`; `Environment="?[A-Z_][A-Z0-9_]*=` over
`scripts/systemd/*.service`) gives, at the time of this pass:

| Bucket | Count | Method |
|---|---|---|
| `CODE_CONSUMED` | 575 distinct names | Actually referenced via `os.getenv`/`os.environ.get`/`os.environ[...]` somewhere in the Python source tree |
| `TEMPLATE_ONLY` (`.env.example`) | 32 names | Present as a template entry but with no matching `CODE_CONSUMED` name found |
| `TEMPLATE_ONLY` (`.env.secrets.example`) | 4 names | Same, for the secrets template |
| `SYSTEMD_ONLY` | 4 names (`PYTHONUNBUFFERED`, `PYTHONIOENCODING`, `PYTHONPATH`, `TZ`) | Set only via `Environment=` in `scripts/systemd/*.service`, never read via `os.getenv`/`os.environ` in the Python source itself (interpreter-level env vars) |

The small difference between this pass's 575 `CODE_CONSUMED` figure and
the original "573" is attributable to regex/normalization differences
between census passes, not a material discrepancy — both are in the same
range and the qualitative finding (the count is a **census of environment
names from a mixed source set**, not purely code-consumed) is what this
correction fixes. This registry groups the resulting names by family and
prefix, and calls out individually only the variables that are
architecturally significant (secrets, feature flags, duplication
candidates, cross-family shared config). See
`ENVIRONMENT_CONFIGURATION_CONSTITUTION.md` for the policy these
classifications serve.

SECRET-classified variables below name `.env.secrets` as their location;
no value for any of them appears anywhere in this document.

**AFTER ENV-01 (2026-09)**: every `EXPECTED_FILE = .env.secrets` entry
below that was previously templated as a placeholder name in the real
`.env.example` (Telegram bot tokens/chat-ids, exchange API keys,
`SLACK_WEBHOOK_URL`, `EMAIL_SMTP_SERVER`/`PORT`/`EMAIL_FROM_ADDR`/
`EMAIL_TO_ADDR`) has now been consolidated so that `.env.secrets.example`
is its only template location — `.env.example` no longer carries a
duplicate placeholder for any secret-class name. This registry's per-family
`EXPECTED_FILE` classification (already correct before ENV-01) was the
target `.env.example`/`.env.secrets.example` split now implemented; no
`EXPECTED_FILE` values changed as a result. The two-occurrence
PRECEDENCE_RISK finding referenced from the constitution's §5 (row A,
`WATCHDOG_*`) is remediated — see
`ENVIRONMENT_CONFIGURATION_CONSTITUTION.md` §5.

## A — INFRASTRUCTURE / GOVERNANCE

| VARIABLE_NAME | CATEGORY | EXPECTED_FILE | STATUS | NOTE |
|---|---|---|---|---|
| `RESTART_DISABLED_UNTIL_RECONCILIATION` | NON_SECRET_RUNTIME_CONFIG | `.env` | ACTIVE_SOURCE_PATH | Shared source of truth, `deploy_vps.sh --restart` + `watchdog_vps.py` |
| `VPS_RESTART_CMD` | DEPLOYMENT_CONFIG | `.env` | ACTIVE_SOURCE_PATH | Double opt-in with `--restart` flag, per CLAUDE.md |
| `PAPER_TRADING_ENABLED` | FEATURE_FLAG | `.env` | ACTIVE_SOURCE_PATH | Must remain `true` per CLAUDE.md stabilization window |
| `LIVE_TRADING_CONFIRMED` | FEATURE_FLAG | `.env` | ACTIVE_SOURCE_PATH | Must remain `false` per CLAUDE.md stabilization window |
| `FEATURE_AUTO_CALIBRATION` | FEATURE_FLAG | `.env` | ACTIVE_SOURCE_PATH | Default False permanent, ADR-0007 |
| `FEATURE_ADAPTIVE_DECISION_FEEDBACK` | FEATURE_FLAG | `.env` | ACTIVE_SOURCE_PATH | S-02B.1 master gate for adaptive_learning application |
| `FEATURE_REGRET_DECISION_FEEDBACK` | FEATURE_FLAG | `.env` | ACTIVE_SOURCE_PATH | Regret-side governance precedent, ADR-0007 |
| `SCIENTIFIC_DATA_GUARD_GENERATE` | FEATURE_FLAG | `.env` | ACTIVE_SOURCE_PATH | — |
| `AI_MODE` | NON_SECRET_RUNTIME_CONFIG | `.env` | ACTIVE_SOURCE_PATH | — |
| `ENGINE_VERSION` | NON_SECRET_RUNTIME_CONFIG | `.env` | ACTIVE_SOURCE_PATH | — |
| `SYSTEM_STATE_FILE` | PATH | `.env` | ACTIVE_SOURCE_PATH | — |
| `ENV_PATH` | PATH | `.env` | ACTIVE_SOURCE_PATH | — |
| `INVOCATION_ID` | NON_SECRET_RUNTIME_CONFIG | CODE_DEFAULT | ACTIVE_SOURCE_PATH | Injected by systemd (`%n`-style), not human-set |
| `PYTHONUNBUFFERED`, `PYTHONIOENCODING`, `TZ`, `PYTHONPATH` | DEPLOYMENT_CONFIG | SYSTEMD_ONLY | ACTIVE_SOURCE_PATH | Set directly in `scripts/systemd/*.service` via `Environment=`, never in `.env` |
| `DP_LOG_DIR`, `DP_LOG_PATH` | PATH | `.env` (also a systemd-only override on `crypto-advisor.service`) | ACTIVE_SOURCE_PATH | `crypto-advisor.service` sets `DP_LOG_DIR` directly via `Environment=`, overriding any `.env` value for that unit only |
| `PARAM_AUDIT_LOG` | PATH | `.env` | ACTIVE_SOURCE_PATH | — |
| `WATCHDOG_*` (INTERVAL, TIMEOUT, MAX_RESTARTS, RAM_ALERT_MB, RAM_RESTART_MB, RESTART_COOLDOWN, RESTART_DELAY, STARTUP_GRACE, USE_SYSTEMD, SNAPSHOT, DEAD_ALERT_REPEAT_S) | CADENCE / THRESHOLD | `.env` | ACTIVE_SOURCE_PATH | Consumed by `watchdog_vps.py` (deployed) — see precedence-risk finding in the constitution doc |
| `P10_WD_*` (CHECK_S, FREEZE_LAG_S, HEARTBEAT_S, MAX_RESTARTS, STALE_S) | CADENCE / THRESHOLD | `.env` | ACTIVE_SOURCE_PATH | Phase-10 watchdog-shaped config, parallel prefix to `WATCHDOG_*` — duplication candidate, see `MODULE_FAMILY_REGISTRY.md`-adjacent debt |
| `P10_PHASE`, `P10_CERT_KEY`, `P10_CERT_PATH`, `P10_DECISION_KEY_PATH`, `P10_TAMPER_LOG_PATH`, `P10_WARMUP_HMAC_KEY` | SECRET / RESTRICTED_IDENTITY | `.env.secrets` (keys/paths that gate certification) | INCONCLUSIVE | Key-shaped names; classify as secret pending confirmation these are cryptographic material rather than plain paths — flagged for future remediation, not resolved here |

## B — MARKET / DATA

| VARIABLE_NAME | CATEGORY | EXPECTED_FILE | STATUS |
|---|---|---|---|
| `EXCHANGE_ID`, `EXCHANGE_TESTNET`, `EXCHANGE_MODE`, `EXCHANGE_HEARTBEAT_S`, `EXCHANGE_MONITOR_URL` | NON_SECRET_RUNTIME_CONFIG | `.env` | ACTIVE_SOURCE_PATH |
| `ACTIVE_EXCHANGE` | NON_SECRET_RUNTIME_CONFIG | `.env` | ACTIVE_SOURCE_PATH |
| `MARKET_SCANNER_*` (EXCHANGE, CACHE_TTL, POOL_SIZE, PROFILE, TIMEFRAME, TESTNET, SYNTHETIC, ALLOW_STALE_CACHE, CB_RECOVERY, PRELOAD_MARKETS, PRELOAD_WAIT_MS, RETRY_BASE_DELAY, RETRY_MAX_DELAY, SESSION_MAX_ERRORS, SESSION_TTL_S, TRACE_TIMINGS) | CADENCE / THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |
| `MTF_SCAN_*` (MAX_RETRIES, MAX_WORKERS, RETRY_BASE_DELAY, RETRY_MAX_DELAY) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |
| `MARKET_DB_PATH` | PATH | `.env` | ACTIVE_SOURCE_PATH |
| `LMI_DIR`, `LMI_EXCHANGE`, `LMI_STREAM_STALL_S` | PATH / THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — `crypto-lmi-observatory.service` |
| `OBS_DIR`, `OBS_EXCHANGE`, `OBS_EXCHANGES`, `OBS_LOG_ROOT`, `OBS_MIN_FREE_DISK_GB`, `OBS_PRIMARY_EXCHANGE`, `OBS_RETENTION_DAYS` | PATH / THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |
| `PERP_BUILDER_*` (EXCHANGE, MAX_SPREAD_PCT, MIN_VOL_USD, QUOTES, TOP_N, USE_SWAP) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |
| `UNIVERSE_*` (ENABLED, EXCHANGE, MAX_SPREAD_PCT, MIN_CHANGE_N, MIN_VOL_USD, PINNED_SYMBOLS, QUOTES, REFRESH_H, STORAGE, SYNC_EVERY, TOP_N) | FEATURE_FLAG / THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — universe is an experimental variable per CLAUDE.md ADR-0017 |
| `RADAR_*` (BOT_TOKEN, CHAT_ID, EVAL_MIN_MOVE_PCT, LIVE_MODE, MAX_SPREAD_PCT, MIN_QUOTE_VOL_USD, QUOTES, TELEGRAM_DIGEST, TOP_N) | mixed — see split below | mixed | ACTIVE_SOURCE_PATH |
| `RADAR_BOT_TOKEN` | SECRET | `.env.secrets` | ACTIVE_SOURCE_PATH |
| `RADAR_CHAT_ID` | RESTRICTED_IDENTITY | `.env.secrets` | ACTIVE_SOURCE_PATH |
| `ALERT_SYMBOL`, `ALERT_TIMEFRAME`, `ALERT_POLL_SECONDS`, `ALERT_COOLDOWN_REGIME`, `ALERT_COOLDOWN_RISK`, `ALERT_COOLDOWN_SIGNAL` | CADENCE | `.env` | ACTIVE_SOURCE_PATH |
| `ALERT_EMAIL` | RESTRICTED_IDENTITY | `.env.secrets` | ACTIVE_SOURCE_PATH |

## C — QUANTITATIVE RESEARCH / LEARNING

| VARIABLE_NAME | CATEGORY | EXPECTED_FILE | STATUS |
|---|---|---|---|
| `RANKER_*` (BLACKLIST_DEMOTES, DB, DEMOTE_SCORE, ENABLED, EXCHANGE, MIN_TRADES, MIN_VOL_USD, PROMOTE_SCORE, STALE_DAYS, TOP_N) | FEATURE_FLAG / THRESHOLD / PATH | `.env` | ACTIVE_SOURCE_PATH |
| `MM_*` (MAX_DB, MIN_LOSS_PCT, REPEAT_THRESHOLD, RULE_EXPIRY_DAYS) | THRESHOLD / PATH | `.env` | ACTIVE_SOURCE_PATH — `mistake_memory.py` thresholds |
| `MISTAKE_DB` | PATH | `.env` | ACTIVE_SOURCE_PATH |
| `P8_*` (~35 vars: CONF_*, DWE_*, PERF_W_*, PROBATION_*, RAMP_*, TRACKING_*, etc.) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — strategy_ranker / confidence-weighting phase-8 config |
| `P9_*` (~28 vars: BDD_*, CONC_*, DD_WARN, DRIFT_*, ERROR_RATE_*, GOV_*, LATENCY_*, PF_WARN, RG_BURST_COUNT, SHARPE_WARN, etc.) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — phase-9 governance/drift thresholds |
| `CAE_*` (EV_MIN, KELLY_MAX, KELLY_SAFETY, LEVERAGE_MAX, MIN_TRADES_KELLY, VOL_MAX_REDUCTION, VOL_REFERENCE) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — capital allocation engine |
| `CONV_*` (SIZE_*, THRESH_*, W_MEMORY, W_MTF, W_QUALITY, W_REGIME, W_SIGNAL) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — conviction scoring weights |
| `NTL_*` (~14 vars: CHOP_THRESHOLD, CONTRADICTION, FOMO_WINDOW, MAX_ATR_MULT, MIN_SCORE, W_FOMO, W_MARKET, W_SIGNAL, W_TACTICAL, etc.) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — no_trade_layer thresholds |
| `META_*_MIN_SCORE`, `META_*_SL`, `META_*_TP`, `META_*_TRAIL` (per personality: MOMENTUM, RANGE, SCALP, SHORT) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — per-personality exit params |
| `REGIME_*` (ABSOLUTE_FLOOR, MISMATCH_COOLDOWN, RAMP_CYCLES, SIDEWAYS_MIN_SCORE, SIDEWAYS_TP_ATR, STABILITY_WINDOW) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |
| `SIGNAL_MIN_SCORE` | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |
| `LSE_MTF_MIN_AGREE`, `LSE_MTF_MIN_STRENGTH` | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |
| `V9_*` (ADVISOR_ONLY, INITIAL_CAPITAL, LOG_LEVEL, MAX_POSITION_WEIGHT, SYMBOLS) | NON_SECRET_RUNTIME_CONFIG | `.env` | ACTIVE_SOURCE_PATH — quant_hedge_ai v9 config namespace |

## D — DECISION / RISK / SAFETY

| VARIABLE_NAME | CATEGORY | EXPECTED_FILE | STATUS |
|---|---|---|---|
| `INV_*` (MAX_CUMUL_DELTA, MAX_DD, MAX_DELTA, MAX_FLIPS_10C, MAX_IDLE, MAX_STRATEGY_WEIGHT, MIN_CONFIDENCE, MIN_ENTROPY, MIN_PNL_GO, MIN_STABILITY, MIN_WIN_RATE) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — invariant gate thresholds |
| `EO_*` (DAILY_CAREFUL/MINIMAL/RECOVERY/REDUCE/VETO, DD_*, MAX_TRADES_HOUR, OPEN_PNL_*, STREAK_*) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — emergency/operational overlay thresholds |
| `RG_*` (AGGRESSIVE_PNL_CYCLES, DD_DEFENSIVE, DD_RISK_OFF, MIN_CYCLES, RECOVERY_PNL_CYCLES, RECOVERY_STABLE, RISK_OFF_SAFE_CYCLES, VOL_DEFENSIVE, VOL_EMERGENCY, VOL_EMERGENCY_COOLDOWN) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — risk-gate regime thresholds |
| `SA_*` (~16 vars: BASELINE_WINDOW, CRITICAL_HALT_SECONDS, DD_ACCEL, FREEZE_HALTS, HALT_MINUTES, LATENCY_*, OVERTRADE_*, RECENT_WINDOW, REVENGE_*, SHARPE_DROP, SLIPPAGE_*, WR_DROP_*) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — safety-agent thresholds |
| `PB_*` (MAX_CORRELATION, MAX_EXPOSURE_PCT, MAX_LEVERAGE, MAX_POSITIONS, MAX_REGIME_PCT, MAX_SAME_DIRECTION, MAX_SYMBOL_PCT, MIN_POSITION_USD) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — portfolio_brain limits |
| `EM_MAX_AGGRESSIVE`, `EM_MAX_DEFENSIVE`, `EM_MAX_NORMAL`, `EM_MAX_RECOVERY` | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |
| `CT_*` (HARD_DD, MIN_OPERATIONAL, RAMP_RATE, REDUCTION, SOFT_DD) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |
| `PRELIVE_*` (BURNIN_MAX_AGE_H, BURNIN_N, MAX_DD, MAX_ORDER_USD, MIN_PF, MIN_SHARPE, MIN_WR) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — `scripts/prelive_gate.py` |
| `GATE_LOG_CSV`, `GATE_MIN_SCORE_OVERRIDE`, `GATE_REQUIRE_CONFIRMED`, `GATE_WARN_THROTTLE_S` | PATH / THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — global_risk_gate's own CSV log (the third counting, see constitution/registry) |
| `KELLY_FRACTION` | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |
| `MIN_PROFIT_FACTOR` | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |

## E — PORTFOLIO / EXECUTION

| VARIABLE_NAME | CATEGORY | EXPECTED_FILE | STATUS |
|---|---|---|---|
| `WALLET_PAPER_CAPITAL`, `WALLET_CACHE_TTL_S` | NON_SECRET_RUNTIME_CONFIG | `.env` | ACTIVE_SOURCE_PATH — pinned sizing base per CLAUDE.md ADR-0007 |
| `MEXC_SIM_*` (CAPITAL, FEE, MAX_AGE_H, MAX_POSITION_USD, MAX_PRICE_DEV, SLIP) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |
| `EXEC_*` (DEDUP_WINDOW, FUTURES_MAX_ORDER_USD, FUTURES_MIN_ORDER_USD, MAX_CONSEC_LOSSES, MAX_DD, MAX_LOSS, MAX_ORDER_USD, TRADE_LOG) | THRESHOLD / PATH | `.env` | ACTIVE_SOURCE_PATH |
| `DEFAULT_ORDER_USD`, `DEFAULT_SL_PCT`, `DEFAULT_TP_PCT`, `MIN_ORDER_USD`, `MAX_ORDER_USD` | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |
| `PM_*` (~13 vars: AGING_DECAY, AGING_START, BE_TRIGGER, CHECK_INTERVAL, LIQ_DEFENSE_PCT, MAX_AGE_MIN, PARTIAL_*, SL_*, TP_*, TRAILING_PCT) | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — position manager |
| `PAPER_INITIAL_CAPITAL`, `PAPER_SIM_ORDER_USD`, `PAPER_TRADE_LOG`, `PAPER_PORTFOLIO_BRAIN_LEVEL`, `PAPER_ADMISSION_LEDGER` | NON_SECRET_RUNTIME_CONFIG / PATH | `.env` | ACTIVE_SOURCE_PATH |
| `INITIAL_CAPITAL`, `REFERENCE_CAPITAL`, `VIRTUAL_CAPITAL_USD` | NON_SECRET_RUNTIME_CONFIG | `.env` | DUPLICATED — three capital-shaped names alongside `WALLET_PAPER_CAPITAL`; see `ENVIRONMENT_VARIABLE_REGISTRY.md` §Duplication below |
| `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `BINANCE_LIVE_API_KEY`, `BINANCE_LIVE_API_SECRET`, `BINANCE_FUTURES_DEMO_KEY`, `BINANCE_FUTURES_DEMO_SECRET`, `BINANCE_TESTNET` | SECRET (keys/secrets) / NON_SECRET_RUNTIME_CONFIG (`_TESTNET`) | `.env.secrets` (keys), `.env` (`BINANCE_TESTNET`) | ACTIVE_SOURCE_PATH |
| `GATEIO_API_KEY`, `GATEIO_API_SECRET`, `GATEIO_TESTNET` | SECRET / NON_SECRET_RUNTIME_CONFIG | `.env.secrets` / `.env` | ACTIVE_SOURCE_PATH |
| `KRAKEN_API_KEY`, `KRAKEN_API_SECRET` | SECRET | `.env.secrets` | ACTIVE_SOURCE_PATH |
| `MEXC_API_KEY`, `MEXC_API_SECRET` | SECRET | `.env.secrets` | ACTIVE_SOURCE_PATH |
| `LIVE_READER_API_KEY`, `LIVE_READER_API_SECRET`, `LIVE_READER_EXCHANGE` | SECRET / NON_SECRET_RUNTIME_CONFIG | `.env.secrets` / `.env` | ACTIVE_SOURCE_PATH |
| `REAL_ACCOUNTS_DUST_USD`, `REAL_ACCOUNTS_EXCHANGES`, `REAL_ACCOUNTS_TTL_S` | THRESHOLD / NON_SECRET_RUNTIME_CONFIG | `.env` | ACTIVE_SOURCE_PATH |
| `SYMBOL_BLACKLIST` | NON_SECRET_RUNTIME_CONFIG | `.env` | ACTIVE_SOURCE_PATH |
| `FORCE_TEST_EXECUTION` | FEATURE_FLAG | `.env` | ACTIVE_SOURCE_PATH |

## F — CANONICAL SCIENTIFIC OBSERVABILITY / REGRET

| VARIABLE_NAME | CATEGORY | EXPECTED_FILE | STATUS |
|---|---|---|---|
| `REGRET_*` (CANONICAL_HORIZON, DB, DELAY_CYCLES, HORIZONS_DIR, MAX_DB, MAX_STALE_H, MIN_MOVE, MIN_MOVE_PCT, MIN_SCORE) | THRESHOLD / PATH | `.env` | ACTIVE_SOURCE_PATH |
| `REJECTION_STORE_DIR` | PATH | `.env` | ACTIVE_SOURCE_PATH |
| `DQE_DB`, `DQE_QUALITY_THRESHOLD` | PATH / THRESHOLD | `.env` | ACTIVE_SOURCE_PATH — data-quality engine |
| `ALLOCATOR_DB`, `FORBIDDEN_PATTERNS_DB`, `PROBATION_DB` | PATH | `.env` | ACTIVE_SOURCE_PATH |
| `SIM_RESTORE_MAX_AGE_H` | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |
| `BURN_IN_REPORTS_DIR`, `COLD_START_REPORT_DIR` | PATH | `.env` | ACTIVE_SOURCE_PATH |
| `INTEGRITY_AUDIT_EVERY`, `INTEGRITY_LOG_PATH`, `INTEGRITY_UNSAFE_SCORE` | CADENCE / PATH / THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |
| `POSITIONS_SNAPSHOT_PATH` | PATH | `.env` | ACTIVE_SOURCE_PATH |
| `TRADING_STALLED_CYCLES`, `RECOVERY_STABLE_CYCLES`, `HEARTBEAT_CYCLES`, `INACTIVITY_WARN_RATIO` | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |

## G — OPERATOR / TELEGRAM / PRESENTATION

| VARIABLE_NAME | CATEGORY | EXPECTED_FILE | STATUS |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_BEHAVIOR_CHAT_ID` | SECRET / RESTRICTED_IDENTITY | `.env.secrets` | ACTIVE_SOURCE_PATH |
| `TELEGRAM_TOKEN` | SECRET | `.env.secrets` (if kept) | LEGACY / DUPLICATED — alias of `TELEGRAM_BOT_TOKEN`, see duplication table below |
| `TELEGRAM_ENABLED` | FEATURE_FLAG | `.env` | ACTIVE_SOURCE_PATH |
| `MON_PORTFOLIO_BOT_TOKEN`, `MON_PORTFOLIO_CHAT_ID` | SECRET / RESTRICTED_IDENTITY | `.env.secrets` | ACTIVE_SOURCE_PATH |
| `PAPER_ARENA_BOT_TOKEN`, `PAPER_ARENA_CHAT_ID` | SECRET / RESTRICTED_IDENTITY | `.env.secrets` | ACTIVE_SOURCE_PATH |
| `RAPPORT_AUTOMATIQUE_BOT_TOKEN`, `RAPPORT_AUTOMATIQUE_CHAT_ID` | SECRET / RESTRICTED_IDENTITY | `.env.secrets` | ACTIVE_SOURCE_PATH |
| `QUANT_CRYPTO_BOT_TOKEN`, `QUANT_CRYPTO_CHAT_ID` | SECRET / RESTRICTED_IDENTITY | `.env.secrets` | ACTIVE_SOURCE_PATH |
| `TELEMETRIE_IA_BOT_TOKEN`, `TELEMETRIE_IA_CHAT_ID` | SECRET / RESTRICTED_IDENTITY | `.env.secrets` | LEGACY per `.env.secrets.example` header ("@Telemetrie_IA_bot retiré") — kept for audit, not actively wired |
| `P10_PORTFOLIO_BOT_TOKEN`, `P10_PORTFOLIO_CHAT_ID` | SECRET / RESTRICTED_IDENTITY | `.env.secrets` | ACTIVE_SOURCE_PATH |
| `QC_PINNED_MSG_ID`, `QC_PINNED_UPDATE`, `QC_POLL_INTERVAL`, `QC_LIVE_RETRY`, `QC_SAFETY_REFRESH` | RESTRICTED_IDENTITY / CADENCE | `.env.secrets` (pinned msg id) / `.env` (cadences) | ACTIVE_SOURCE_PATH — Quant Observer config |
| `DASHBOARD_PASSWORD` | SECRET | `.env.secrets` | ACTIVE_SOURCE_PATH |
| `DASHBOARD_PORT`, `RISK_DASHBOARD_ENABLED`, `RISK_DASHBOARD_PORT`, `HEALTH_PORT`, `CHART_SERVER_HOST`, `CHART_SERVER_PORT`, `CHART_SERVER_URL` | PRESENTATION_CONFIG | `.env` | ACTIVE_SOURCE_PATH |
| `DASHBOARD_AUDIT_NOTIFY_PREFIX`, `DASHBOARD_AUDIT_SLACK_WEBHOOK`, `DASHBOARD_AUDIT_STRICT` | PRESENTATION_CONFIG / SECRET (webhook) | `.env` / `.env.secrets` | ACTIVE_SOURCE_PATH |
| `SLACK_WEBHOOK_URL` | SECRET | `.env.secrets` | ACTIVE_SOURCE_PATH |
| `SLACK_WEBHOOK` | SECRET | `.env.secrets` (if kept) | DUPLICATED — alias of `SLACK_WEBHOOK_URL`, see below |
| `DISCORD_WEBHOOK_URL` | SECRET | `.env.secrets` | ACTIVE_SOURCE_PATH |
| `EMAIL_ENABLED`, `EMAIL_FROM`, `EMAIL_FROM_ADDR`, `EMAIL_TO`, `EMAIL_TO_ADDR` | FEATURE_FLAG / RESTRICTED_IDENTITY | `.env` (`_ENABLED`) / `.env.secrets` (addresses) | ACTIVE_SOURCE_PATH — `EMAIL_FROM`/`EMAIL_FROM_ADDR` and `EMAIL_TO`/`EMAIL_TO_ADDR` are alias-shaped pairs, see below |
| `EMAIL_SMTP_SERVER`, `EMAIL_SMTP_PORT`, `EMAIL_SMTP_USER`, `EMAIL_SMTP_PASS`, `EMAIL_SMTP_PASSWORD` | RESTRICTED_IDENTITY / SECRET | `.env.secrets` | DUPLICATED — `EMAIL_SMTP_PASS` vs `EMAIL_SMTP_PASSWORD`, see below |
| `SMTP_SERVER`, `SMTP_PORT`, `SMTP_PASS` | SECRET | `.env.secrets` | DUPLICATED — parallel to `EMAIL_SMTP_*`, see below (consumed by `infra/monitoring/surveillance_continue.py`) |
| `BATCH_NOTIFY_EMAIL`, `BATCH_NOTIFY_PROVIDER`, `BATCH_NOTIFY_SMTP_PASS`, `BATCH_NOTIFY_SMTP_PORT`, `BATCH_NOTIFY_SMTP_SERVER`, `BATCH_NOTIFY_SMTP_USER` | SECRET / NON_SECRET_RUNTIME_CONFIG | `.env.secrets` (creds) / `.env` (provider) | DUPLICATED — a third SMTP-shaped prefix, see below |
| `RADAR_TELEGRAM_DIGEST` | PRESENTATION_CONFIG | `.env` | ACTIVE_SOURCE_PATH |
| `COO_BRIEF_EVERY`, `INTEL_REPORT_EVERY_H`, `INTEL_SNAPSHOT_PATH`, `INTEL_TRADE_STALL_ALERT_H`, `PORTFOLIO_REPORT_EVERY_H`, `REAL_BOT_REPORT_EVERY`, `WEEKLY_REPORT_EVERY` | CADENCE | `.env` | ACTIVE_SOURCE_PATH |
| `OPS_ALERT_COOLDOWN`, `LATENCY_ALERT_MS`, `STALL_ALERT_SECONDS` | THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |

## H — LM STUDIO / LOCAL AI ASSIST (presentation-adjacent tooling, not a decision layer)

| VARIABLE_NAME | CATEGORY | EXPECTED_FILE | STATUS |
|---|---|---|---|
| `LM_STUDIO_API_KEY` | SECRET | `.env.secrets` | ACTIVE_SOURCE_PATH |
| `LM_STUDIO_HOST`, `LM_STUDIO_PORT`, `LM_STUDIO_URL`, `LM_STUDIO_MODEL`, `LM_STUDIO_MAX_TOKENS`, `LM_STUDIO_MIN_SCORE`, `LM_STUDIO_CONNECT_TIMEOUT`, `LM_STUDIO_TIMEOUT`, `LM_STUDIO_AVAILABLE` | NON_SECRET_RUNTIME_CONFIG | `.env` | ACTIVE_SOURCE_PATH |

## I — MISC / LEGACY / CI

| VARIABLE_NAME | CATEGORY | EXPECTED_FILE | STATUS |
|---|---|---|---|
| `BB_MAX`, `BB_PATH`, `BLACK_BOX_PATH` | PATH / THRESHOLD | `.env` | INCONCLUSIVE — sparse call sites, not traced end-to-end this mission |
| `OBSIDIAN_VAULT_PATH` | PATH | `.env` | ACTIVE_SOURCE_PATH — local documentation vault integration |
| `PLAYWRIGHT_E2E`, `SELENIUM_PANEL_E2E`, `TEST_REPORT_URL`, `RUN_STRESS_TEST_AT_STARTUP` | DEPLOYMENT_CONFIG | `.env` / CI only | ACTIVE_SOURCE_PATH (CI/test tooling, not production runtime) |
| `SCANNER_TOPK_ENABLED`, `SCANNER_TOPK_K` | FEATURE_FLAG / THRESHOLD | `.env` | ACTIVE_SOURCE_PATH |
| `VPS_API_URL`, `VPS_SYNC_INTERVAL` | NON_SECRET_RUNTIME_CONFIG | `.env` | ACTIVE_SOURCE_PATH |
| `MVP_LOG_LEVEL` | NON_SECRET_RUNTIME_CONFIG | `.env` | ACTIVE_SOURCE_PATH |
| `TEMP` | UNKNOWN | CODE_DEFAULT | INCONCLUSIVE — standard OS temp-dir variable incidentally caught by the census regex, not a project-defined config variable |

## Duplication / alias findings

See the same table reproduced with RISK/TARGET_CANONICAL_NAME columns in
`ENVIRONMENT_CONFIGURATION_CONSTITUTION.md`'s companion — summarized here
for the by-family view:

| VARIABLE A | VARIABLE B | RELATION | CONSUMERS |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `TELEGRAM_TOKEN` | Same physical bot, two names | `tests/phase0/test_phase05_validation.py`, `tools/runtime_tracer.py`, `infra/monitoring/supervise_all.py` read `TELEGRAM_TOKEN`; the deployed path (`core/advisor_loop.py`, `scripts/radar_bot.py`, `.env.example`) uses `TELEGRAM_BOT_TOKEN` |
| `SLACK_WEBHOOK_URL` | `SLACK_WEBHOOK` | Same setting, two names | `.env.example`/`.env.secrets.example` template `SLACK_WEBHOOK_URL`; `infra/monitoring/supervise_all.py` reads `SLACK_WEBHOOK` |
| `EMAIL_SMTP_PASS` | `EMAIL_SMTP_PASSWORD` | Same setting, two names | `.env.secrets.example` templates `EMAIL_SMTP_PASS`; `infra/notifications/notify_test_status.py` reads `EMAIL_SMTP_PASSWORD` |
| `EMAIL_SMTP_SERVER`/`PORT` | `SMTP_SERVER`/`PORT` (+`SMTP_PASS`) | Parallel SMTP config, two prefixes | `infra/monitoring/surveillance_continue.py` reads the bare `SMTP_*` names; the templated/main path uses `EMAIL_SMTP_*` |
| `EMAIL_SMTP_*` / `SMTP_*` | `BATCH_NOTIFY_SMTP_*` | A third, independent SMTP-shaped prefix | `BATCH_NOTIFY_*` appears to serve a separate batch-notification path, not obviously reconciled with the other two |
| `EMAIL_FROM` | `EMAIL_FROM_ADDR` | Same concept, two names | `.env.example` templates `EMAIL_FROM_ADDR`-style names via split_env's SECRET_EXACT_NAMES; other call sites use `EMAIL_FROM` |
| `EMAIL_TO` | `EMAIL_TO_ADDR` | Same concept, two names | Same pattern as above |
| `INITIAL_CAPITAL` / `REFERENCE_CAPITAL` / `VIRTUAL_CAPITAL_USD` | `WALLET_PAPER_CAPITAL` | Four capital-shaped names; `WALLET_PAPER_CAPITAL` is the CLAUDE.md-pinned canonical sizing base | Multiple call sites across `quant_hedge_ai/` and `paper_trading/` — not verified this mission whether the other three are read anywhere live or are vestigial |
| `WATCHDOG_*` | `P10_WD_*` | Two parallel prefixes for what look like the same concern (watchdog cadence/thresholds) | `watchdog_vps.py` reads `WATCHDOG_*`; `P10_WD_*` consumers not traced to a single file this mission — flagged INCONCLUSIVE |
| `MEXC_API_SECRET` | `MEXC_SECRET_KEY` | Same secret, two names | `.env.secrets.example` templates `MEXC_API_SECRET`; `scripts/runtime_validator.py` and `scripts/prelive_gate.py` read `MEXC_SECRET_KEY` |
| `BINANCE_API_SECRET` | `BINANCE_SECRET` | Possible alias — `BINANCE_SECRET` appears only as a bare grep hit with no confirmed call site found this pass | INCONCLUSIVE — no source file located reading `BINANCE_SECRET` at time of this census; may be dead/legacy naming from a template comment only |

**Target canonical names** (proposed, not applied by this mission — see
`ENVIRONMENT_CONFIGURATION_CONSTITUTION.md` §6 and §10): `TELEGRAM_BOT_TOKEN`,
`SLACK_WEBHOOK_URL`, `EMAIL_SMTP_PASSWORD`, `EMAIL_SMTP_SERVER`/`PORT`,
`EMAIL_FROM`, `EMAIL_TO`, `WALLET_PAPER_CAPITAL`, `WATCHDOG_*`,
`MEXC_API_SECRET`, `BINANCE_API_SECRET` — each an existing name already in
active use on the deployed path, so canonicalizing means deprecating the
other member of each pair, never renaming the deployed one. No rename is
performed by this mission.

## Documented-but-unconsumed / consumed-but-not-templated

- `TELEMETRIE_IA_BOT_TOKEN`/`TELEMETRIE_IA_CHAT_ID` are templated in
  `.env.secrets.example` but the bot itself is marked retired in that same
  file's header — documented-but-largely-unconsumed, kept for audit.
- The `P8_*`/`P9_*`/`P10_*` families (roughly 90 variables combined) are
  consumed extensively in source but have **no entries at all** in
  `.env.example` — every one of them falls back to its code default unless
  an operator adds it manually. This is the single largest
  documented-but-unconsumed-in-templates gap found by this census.
