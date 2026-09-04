# Pre-Restart Runtime Contract (T-1)

Mission FAM-01. A checklist for the moment right before any controlled VPS
restart during the stabilization window (or after it), per
`docs/governance/STABILIZATION_WINDOW_2026-09-03_2026-09-16.md` and the
deliberate-deploy gesture in CLAUDE.md (`scripts/deploy_vps.sh --confirm
[--restart]`). This is a checklist, not a script to run unattended — every
item below is something a human (or an agent acting for a human, within
the secret-boundary rules of `ENVIRONMENT_CONFIGURATION_CONSTITUTION.md`)
confirms before pressing go. **No command below may dump full environment
variable values — only masked `VARIABLE_NAME=SET/UNSET` outcomes are ever
acceptable.**

## 1. Deployed SHA

- Confirm the commit SHA the VPS is currently running matches the most
  recent `deploy-YYYYMMDD-HHMM` git tag (`git tag -l "deploy-*"` is the
  audit log per CLAUDE.md).
- Confirm the SHA about to be deployed/restarted-into is the one the PR
  merge produced — never restart onto an unmerged or force-pushed branch.

## 2. Dirty / clean tree

- `git status` on the deploy source must be clean before running
  `scripts/deploy_vps.sh --confirm`. A dirty tree risks deploying
  uncommitted, uncertified changes during a scientific-freeze window.

## 3. Service inventory

Confirm the expected set of `systemctl` units for this project is the one
being restarted, no more, no less: `crypto-advisor`, `crypto-dashboard`,
`crypto-lmi-observatory`, `crypto-market-horizons`(+`.timer`),
`crypto-market-observer`(+`.timer`), `crypto-market-radar`(+`.timer`),
`crypto-quant-observer`, `crypto-radar-bot`, `crypto-watchdog`,
`paper-arena`. Per CLAUDE.md, the double opt-in for any restart is
`VPS_RESTART_CMD` set AND `--restart` passed explicitly — never implicit.

## 4. Process / PID inventory

Before restart, record which of the above units are actually running (PID,
uptime) so a post-restart comparison can confirm each one actually cycled
rather than silently staying on its old PID (the exact failure mode the
2026-07-08 silent-partial-deploy incident documented in CLAUDE.md
illustrates for file transfer — the same discipline applies to process
restart).

## 5. Automatic restart mechanisms

- Confirm `RESTART_DISABLED_UNTIL_RECONCILIATION` state (masked
  `SET`/`UNSET`+non-secret value only, this variable is non-secret) before
  assuming any automatic restart mechanism is or is not armed.
- Confirm the `.git/hooks/post-commit` deploy hook remains
  `post-commit.disabled` (per the 2026-07-04 abolition in CLAUDE.md) — a
  restored hook would silently reintroduce automatic deploy-on-commit.
- Confirm the watchdog (`watchdog_vps.py`, deployed as
  `crypto-watchdog.service`) is the only automatic process-restart actor;
  `infra/monitoring/watchdog_vps.py` is an undeployed duplicate and must
  not be independently invoked (see `docs/architecture/MODULE_FAMILY_REGISTRY.md`).

## 6. Effective non-secret feature flags (masked read only)

Confirm, by masked check only, the effective value of each governance flag
that must hold during the stabilization window per CLAUDE.md:
`PAPER_TRADING_ENABLED=true`, `LIVE_TRADING_CONFIRMED=false`,
`FEATURE_AUTO_CALIBRATION=false`. Also confirm
`FEATURE_ADAPTIVE_DECISION_FEEDBACK` and
`FEATURE_REGRET_DECISION_FEEDBACK` are at their intended values — these are
non-secret and may be read directly (never via `env`/`printenv` dumps; a
targeted single-variable read, e.g. `systemctl show <unit> -p Environment`
restricted and filtered to just the variable name of interest, or a
process-level check that only prints `NAME=value` for named non-secret
flags, is acceptable — the same technique must never be pointed at a
secret-classified name).

## 7. `.env` / `.env.secrets` wiring

- Confirm both files exist at the paths every systemd unit expects
  (`/home/mathieu/crypto_ai_terminal/.env` and `.env.secrets`) — do not
  open either file; existence and permission checks only (see §8).
- Confirm the precedence-risk finding in
  `docs/architecture/ENVIRONMENT_CONFIGURATION_CONSTITUTION.md` §5 remains
  understood: `core/advisor_loop.py` and the deployed `watchdog_vps.py`
  both call `load_dotenv(override=True)`, so any key duplicated between
  `.env` and `.env.secrets` on the real VPS will resolve to the `.env`
  value inside those two processes specifically, contrary to the systemd
  load order. No fix is prescribed here; this step exists so a restart is
  never mistaken for a moment when this risk was resolved.

## 8. Secret-file permission check (without reading contents)

- Confirm `.env.secrets` is not world-readable (per `scripts/split_env.sh`'s
  own intent, `chmod 600`) using a permission-only check (`stat` mode bits,
  never `cat`/`head`/`grep` on the file).
- Confirm `.gitignore` still excludes `.env`, `.env.*`, `*.env` while
  keeping `.env.example`/`.env.*.example` tracked, exactly as today.

## 9. Duplicate environment-key check (without exposing values)

- Using only variable **names** (never values), confirm no name appears in
  both the non-secret and secret variable-name lists in
  `docs/architecture/ENVIRONMENT_VARIABLE_REGISTRY.md` for a key expected
  to be single-sourced. A masked existence check (`SET`/`UNSET` per name)
  in each file's own scope is acceptable; comparing two masked booleans
  never exposes a value.

## 10. Market state

Confirm `observation/market_observer.py` / `market_radar.py` /
`horizon_evaluator.py` timers are current (last successful run timestamp
within their expected cadence) before assuming the restarted engine will
start with fresh market pulse rather than stale cache
(`MARKET_SCANNER_ALLOW_STALE_CACHE` should not be masking a genuinely stale
feed at restart time).

## 11. Portfolio state

Confirm `paper_trading/mexc_simulator.py`'s book and
`infra/wallet_sync.py`'s capital figure are readable and non-empty before
restart, so a post-restart comparison can catch a silent reset. Do not
conflate this with `quant_hedge_ai/agents/risk/portfolio_brain.py`'s
`pos_manager`-derived figure, which is documented as DUPLICATED/divergent
(`docs/architecture/MODULE_FAMILY_REGISTRY.md`) and must not be used as the
pre-restart reference.

## 12. Regret state

Confirm `tools/regret_repository.py` and `tools/cri_calculator.py` still
resolve `CLEAN_DATA_SINCE_ACTIVE` from `scripts/data_quality.py` (imported,
never a locally-copied constant, per CLAUDE.md) before restart, and that
any data produced during the current stabilization window is still
correctly tagged `certified=false` per
`docs/governance/STABILIZATION_WINDOW_2026-09-03_2026-09-16.md`.

## 13. Adaptive state

Confirm `config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK` remains
at its intended (default `False`, fail-closed) value unless an explicit,
ADR-backed exception exists — a restart must never be the moment this flag
silently flips due to `.env` precedence issues (see §7).

## 14. Storage writers / spools

Confirm the JSONL/SQLite writers this restart will resume (`databases/paper_trades.jsonl`,
`databases/regret/*.jsonl`, `quant_hedge_ai/agents/execution/trade_logger.py`'s
SQLite file, `observability/rejection_store.py`'s daily JSONL rotation) are
not mid-rotation and have no dangling lock/temp file that a fresh process
start would trip over.

## 15. Telegram state

Confirm each of the 7 active bot roles (per
`docs/observability/TELEGRAM_BOT_REGISTRY.md`) is expected to reconnect
cleanly — in particular that no two processes are about to poll
(`getUpdates`) the same token simultaneously post-restart (the documented
HTTP 409 failure mode in `.env.secrets.example`'s own header comment).
Confirm `crypto-quant-observer`, `crypto-radar-bot`, and `paper-arena`
restart in an order that does not race a shared-token bot's polling
process against itself.

## Explicit prohibition

This contract never prescribes a command that dumps full environment
variables (`env`, `printenv`, or an unfiltered `systemctl show -p
Environment`). Every check above that touches configuration state is a
named-variable, masked-outcome check only, per
`docs/architecture/ENVIRONMENT_CONFIGURATION_CONSTITUTION.md` §8.
