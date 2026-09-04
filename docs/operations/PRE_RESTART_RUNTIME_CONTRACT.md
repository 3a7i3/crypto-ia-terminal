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

The restart procedure must never activate a source-defined service merely
because its `.service` file exists under `scripts/systemd/`. Every unit
must first be classified along three distinct axes before a restart
touches it:

- `SOURCE_DEFINED_UNIT` — a `.service` file exists under
  `scripts/systemd/` for this component. This is a static fact about the
  repository, never proof the unit is currently running.
- `CURRENT_RUNTIME_ACTIVE` (flagged `RUNTIME_PROOF_REQUIRED`) — whether
  the unit is actually enabled/running on the VPS *right now*. This
  mission cannot assert this from source alone; it must be confirmed
  against the real VPS at T-1, never assumed from the unit file's
  existence.
- `EXPECTED_AFTER_RESTART` — what the unit's state should be once the
  restart completes. This must be explicitly approved from T-1 evidence
  (the `CURRENT_RUNTIME_ACTIVE` check above), never assumed equal to
  `SOURCE_DEFINED_UNIT`.

Classify each unit as ACTIVE / INACTIVE_EXPECTED / LEGACY / UNKNOWN before
the restart, and preserve that intended state through the restart unless a
separately authorized change says otherwise. The candidate set of
source-defined units for this project (existence in `scripts/systemd/`,
not proof of current activity) is: `crypto-advisor`, `crypto-dashboard`,
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
- Inventory **both** automatic-restart mechanisms found in source — do
  not claim either one is the sole automatic restart actor:
  - **(A)** `watchdog_vps.py` — external process/service-level watchdog,
    deployed as `crypto-watchdog.service` (a `.service` file for this
    unit is verified present under `scripts/systemd/`).
    `infra/monitoring/watchdog_vps.py` is an undeployed duplicate and must
    not be independently invoked (see
    `docs/architecture/MODULE_FAMILY_REGISTRY.md`).
  - **(B)** `supervision/self_healing_bot.py` — an in-process
    component/process wrapper, verified present in source. It has no
    independent Telegram identity and no dedicated systemd unit (none
    found under `scripts/systemd/`).
  - Neither mechanism's *actual runtime activity* (which one, if either,
    is actually firing restarts on the real VPS right now) is something
    this source-only pass can confirm — treat both as
    `RUNTIME_PROOF_REQUIRED` until confirmed against the real VPS at T-1.

## 6. Effective non-secret feature flags (masked read only)

Confirm, by masked check only, the effective value of each governance flag
that must hold during the stabilization window per CLAUDE.md:
`PAPER_TRADING_ENABLED=true`, `LIVE_TRADING_CONFIRMED=false`,
`FEATURE_AUTO_CALIBRATION=false`. Also confirm
`FEATURE_ADAPTIVE_DECISION_FEEDBACK` and
`FEATURE_REGRET_DECISION_FEEDBACK` are at their intended values — these are
non-secret, but must still never be checked via `env`/`printenv` dumps or
via **any** form of `systemctl show <unit> -p Environment`, even
"restricted and filtered to just the variable name of interest": that raw
command can materialize the full environment (including secrets) before
any filtering is applied, so it must never be prescribed at all, even
conditionally. The only acceptable technique is a trusted human/
operator-side verifier that itself exposes only these explicitly-approved
non-secret fields (plus masked `SET`/`UNSET` outcomes for anything
secret-adjacent) — an AI only ever receives that verifier's already-
sanitized result, never a raw environment dump, and never runs
`systemctl show ... -p Environment` itself.

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

- An AI agent MUST NOT itself open, read, or parse the real `.env.secrets`
  file — not even to produce a `SET`/`UNSET` outcome, a key-name listing,
  or a hash. This holds under every framing ("masked", "names only",
  "existence check"): opening the file at all is forbidden, regardless of
  what is done with its contents afterward. The same restriction applies
  to the real, currently-quarantined `.env` (see §8/Constitution) until the
  human secret-purge certification is complete.
- The only source of truth for a duplicate-key check is a trusted
  HUMAN/operator-side verifier that inspects the real files independently
  of any AI process and hands back only sanitized, pre-computed results —
  e.g. `SECRET_DUPLICATE_COUNT=0`, `MEXC_API_KEY=SET`,
  `QUANT_CRYPTO_BOT_TOKEN=SET`. An AI agent may receive and record such
  outputs but must never generate them by opening the files itself.
- Cross-reference the returned names only against
  `docs/architecture/ENVIRONMENT_VARIABLE_REGISTRY.md`'s non-secret/secret
  name lists to confirm no name expected to be single-sourced appears in
  both — this comparison is name-list bookkeeping, not file access.

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

**CURRENT roster (verified — 5 active bot roles, not 7):**
`@RadarCrypto1_bot` (radar), `@mon_portfolio_bot` (Portfolio/Command
Center), `@QuantCrpto_bot` (Quant Observer), `@rapport_automatique_bot`
(Rapport Automatique, `RAPPORT_AUTOMATIQUE_BOT_TOKEN`/
`RAPPORT_AUTOMATIQUE_CHAT_ID`), `@PaperArena_bot`. `@Telemetrie_IA_bot`
("CMVK/Sim Bot", `TELEMETRIE_IA_BOT_TOKEN`) is retired/inactive per
`docs/observability/TELEGRAM_BOT_REGISTRY.md` — no systemd unit
references it, and no `.env.example` entry exists for it — kept for
historical audit only, not one of the 5 active roles.
**TARGET-FUTURE-TELEMETRY/NARRATIVE**: a future O-02+ telemetry/narrative
surface (`FUTURE_TELEMETRY_NARRATIVE`) may repurpose or replace this slot;
this contract does not assume that surface exists today.

Confirm each of these 5 active bot roles is expected to reconnect
cleanly — in particular that no two processes are about to poll
(`getUpdates`) the same token simultaneously post-restart (the documented
HTTP 409 failure mode in `.env.secrets.example`'s own header comment).
Only `@QuantCrpto_bot` (Quant Observer) and `@RadarCrypto1_bot` (Radar —
distinct dedicated bot identities, never conflate the two) and
`@mon_portfolio_bot` (Portfolio) actually own a polling (`getUpdates`)
loop; `@PaperArena_bot` and `@rapport_automatique_bot` are push-only
(fresh `sendMessage` calls only, verified in source — neither owns a
polling loop), so they are not part of the 409-polling-collision surface.
Canonical restart invariant: for each polling token, exactly one polling
owner may run at a time. This applies only to the three polling services
above (`@QuantCrpto_bot`, `@RadarCrypto1_bot`, `@mon_portfolio_bot`).
Push-only services (`@PaperArena_bot`, `@rapport_automatique_bot`) are not
members of the `getUpdates`/HTTP-409 collision surface and are not subject
to this invariant. This contract does not prescribe a mandatory restart
order beyond that invariant; invent no ordering requirement unless a
specific source or runtime finding establishes one.

## Explicit prohibition

This contract never prescribes a command that dumps full environment
variables (`env`, `printenv`, or an unfiltered `systemctl show -p
Environment`). Every check above that touches configuration state is a
named-variable, masked-outcome check only, per
`docs/architecture/ENVIRONMENT_CONFIGURATION_CONSTITUTION.md` §8.
