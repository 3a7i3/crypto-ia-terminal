# Environment & Configuration Constitution

Mission FAM-01. Documentation only — no code, no `.env*` file, no systemd
unit is modified by this document. It records the target configuration
constitution, the precedence forensic performed source-only, and the
policies future remediation work must follow. Findings here point to a
future remediation mission; this mission does not fix any of them.

## 1. Purpose of each file

| File | Purpose |
|---|---|
| `.env` | Non-secret runtime configuration only: feature flags, thresholds, cadences, timeframes, paths, modes, presentation settings. |
| `.env.secrets` | Secret/restricted values only: tokens, API keys/secrets, passwords, webhooks, SMTP credentials, and (per `scripts/split_env.sh`'s explicit, cautious classification) Telegram chat IDs and email addresses. |
| `.env.secrets.example` | Public template: variable names + descriptions only, no real values. |
| `.env.example` | Public template for non-secret config, names + defaults/examples only. |
| `.env.smtp.example` | Public template for SMTP notification config (small, separate concern from the main secrets file). |

**Invariants:**
- NO SECRET VALUE SHALL EXIST IN `.env`.
- NO NON-SECRET CONFIG SHOULD NEED TO LIVE IN `.env.secrets` unless it is
  explicitly classified RESTRICTED (see §6).

## 2. AI secret-access prohibition

No AI agent session may read `.env.secrets`, `.env.smtp`, or any real
runtime `.env` by any means (`cat`, `head`, `tail`, `grep`, `sed`, `awk`,
`source`, a wildcard sweep like `cat .env*`, or any other tool). An agent
may inspect `.env.example`, `.env.secrets.example`, `.env.smtp.example`,
`.gitignore`, `scripts/split_env.sh`, `scripts/systemd/*.service`,
`docs/SECURITY_SECRETS.md`, and variable **names** referenced in source
(`os.getenv`, `os.environ.get`, `load_dotenv`, `EnvironmentFile=`) — never
runtime values. No AI agent session may SSH to any VPS to read these files
either. This mission (FAM-01) complied with this prohibition throughout;
see the confirmation in the mission's final report.

## 3. Systemd load order

Every long-running service unit under `scripts/systemd/` declares, in this
order:

```
EnvironmentFile=-/home/mathieu/crypto_ai_terminal/.env
EnvironmentFile=-/home/mathieu/crypto_ai_terminal/.env.secrets
```

(the leading `-` marks the file optional; `crypto-dashboard.service` is the
only unit that requires `.env` — no `-` on that line.) Per systemd
semantics, when both files are loaded in sequence and define the same key,
**the file loaded later wins**: `.env.secrets` overrides `.env` on any
duplicate key. This is the intended precedence: secrets always win over a
non-secret file that should never contain them in the first place.

## 4. Variable precedence rules (target)

1. Systemd `EnvironmentFile=` order above is the baseline precedence for
   every service process.
2. No source-code `load_dotenv()` call may reverse that precedence for a
   process that is started under systemd. A call is safe under systemd
   only if it never overrides an already-set variable (`override=False`,
   the `python-dotenv` default) — it may then fill in variables systemd
   did not inject, but it may not overwrite what systemd already set.
3. `load_dotenv(override=True)` in a module that a systemd unit executes
   directly is a **precedence risk** per definition: it re-reads `.env`
   after systemd already injected `.env` + `.env.secrets`, and on any key
   duplicated in both files, the freshly-read `.env` value silently wins
   over the `.env.secrets` value systemd set. See §5 for the concrete
   finding.

## 5. `load_dotenv()` policy and precedence forensic (source-only)

Every active `load_dotenv()` call site found in this repository (excluding
`_ARCHIVE_2026/` and test fixtures), classified:

| Call site | Path arg | override | Started under systemd? | Classification |
|---|---|---|---|---|
| `core/advisor_loop.py:677` | default (`.env`) | `True` | Yes — `crypto-advisor.service` | **PRECEDENCE_RISK** |
| `watchdog_vps.py:38` | default (`.env`) | `True` | Yes — `crypto-watchdog.service` | **PRECEDENCE_RISK** |
| `infra/monitoring/watchdog_vps.py:42` | default (`.env`) | `True` | No — this file is not referenced by any systemd unit (duplicate of the root watchdog, see `MODULE_FAMILY_REGISTRY.md`) | **LEGACY** (dead code path in production; risky only if ever wired to a unit) |
| `observation/market_observer.py:314` | `".env"` | `False` (default) | Yes — `crypto-market-observer.service` | **REDUNDANT_UNDER_SYSTEMD** |
| `observation/market_radar.py:338` | `".env"` | `False` (default) | Yes — `crypto-market-radar.service` | **REDUNDANT_UNDER_SYSTEMD** |
| `observation/horizon_evaluator.py:267` | `".env"` | `False` (default) | Yes — `crypto-market-horizons.service` | **REDUNDANT_UNDER_SYSTEMD** |
| `infra/monitoring/surveillance_continue.py:15` | explicit path next to file | `False` (default) | INCONCLUSIVE — no systemd unit found referencing this module directly | **INCONCLUSIVE** |
| `infra/exchange_factory.py:376` | default (`.env`) | `False` (default) | Used by multiple entrypoints (CLI + service code); not itself a systemd `ExecStart` target | **REQUIRED_RUNTIME_LOADER** for CLI paths, **REDUNDANT_UNDER_SYSTEMD** for service paths that import it after systemd already injected env |
| `infra/mexc_reader.py:190` | explicit `env_file` param | `False` (default) | Not itself a systemd `ExecStart` target | **CLI_ONLY_LOADER** |
| `lm_studio/status.py:14` | explicit `PROJECT_ROOT / ".env"` | `False` (default) | No systemd unit found for this module | **CLI_ONLY_LOADER** |
| `core/warm_boot.py:60` | default (`.env`) | `False` (default) | Imported by `core/advisor_loop.py`'s boot sequence (systemd) | **REDUNDANT_UNDER_SYSTEMD** |
| `scripts/quant_observer_pin_bootstrap.py:40` | default | `False` (default) | No — invoked manually per its own docstring/usage | **CLI_ONLY_LOADER** |
| `scripts/boot_system_validator.py:34` | default | `False` (default) | No — CLI validator script | **CLI_ONLY_LOADER** |
| `scripts/runtime_validator.py:31` | default | `False` (default) | No — CLI validator script | **CLI_ONLY_LOADER** |
| `scripts/stress_test_cli.py:24` | default | `False` (default) | No — CLI tool | **CLI_ONLY_LOADER** |
| `scripts/seed_strategy_memory.py:20` | default | `False` (default) | No — CLI tool | **CLI_ONLY_LOADER** |
| `scripts/backfill_ohlcv.py:52` | default | `False` (default) | No — CLI tool | **CLI_ONLY_LOADER** |
| `scripts/vps_burn_in_collector.py:749` | default | `True` | No — invoked as a CLI collector, not a systemd `ExecStart` target found in this repo | **CLI_ONLY_LOADER** (would become PRECEDENCE_RISK if ever wired to a systemd unit — flag for any future such wiring) |
| `scripts/data_verifier.py:32` | default | `False` (default) | No — CLI tool | **CLI_ONLY_LOADER** |
| `scripts/replay_cli.py:22` | default | `False` (default) | No — CLI tool | **CLI_ONLY_LOADER** |
| `scripts/burnin_calibration_v3.py:300,346` | default | `False` (default) | No — CLI tool | **CLI_ONLY_LOADER** |
| `scripts/prelive_gate.py:51` | default | `False` (default) | No — CLI gate script | **CLI_ONLY_LOADER** |
| `scripts/test_intel_report.py:30` | default | `False` (default) | No — test/report CLI | **CLI_ONLY_LOADER** |
| `paper_trading/sandbox_validator.py:122` | default | `False` (default) | No — validator CLI | **CLI_ONLY_LOADER** |

**Headline finding (PRECEDENCE_RISK, two occurrences):**
`core/advisor_loop.py` (the process `crypto-advisor.service` runs) and the
deployed `watchdog_vps.py` (the process `crypto-watchdog.service` runs)
both call `load_dotenv(override=True)` after systemd has already loaded
`.env` then `.env.secrets` in that order. Because `override=True` forces
`python-dotenv` to overwrite any environment variable already set, any key
present in **both** `.env` and `.env.secrets` is re-set from `.env` at this
point in each process's own startup — silently reversing the precedence
systemd intended. Today this is a *latent* risk rather than a *confirmed*
incident: it depends on `.env` and `.env.secrets` actually sharing a
duplicate key on the real VPS, which this source-only mission cannot
verify (RUNTIME_PROOF_REQUIRED) and must not attempt to verify by reading
real secret files. **No code fix is proposed here** — this is a forensic
finding for a future remediation mission, per the mission's explicit
constraint ("do not fix any code — just document findings").

## 6. Duplicate-variable prohibition and secret naming/classification policy

- A variable name must be defined in exactly one canonical file family
  (`.env` xor `.env.secrets`), never both, going forward. See
  `ENVIRONMENT_VARIABLE_REGISTRY.md` for the target per-family location of
  every variable name census this mission found.
- Classification test for "is this a secret": matches `_TOKEN`,
  `_API_KEY`, `_API_SECRET`, `_SECRET`, `_PASS`/`_PASSWORD` by suffix, **or**
  appears in `scripts/split_env.sh`'s explicit `SECRET_EXACT_NAMES` list
  (chat IDs, `EMAIL_FROM_ADDR`, `EMAIL_TO_ADDR`, `EMAIL_SMTP_SERVER`,
  `EMAIL_SMTP_PORT`, `SLACK_WEBHOOK_URL` — treated as RESTRICTED_IDENTITY
  out of caution even though they are not credentials in the strict sense).
- RESTRICTED (non-secret-but-sensitive) values — e.g. chat IDs that
  identify a private Telegram group, or an internal email address — belong
  in `.env.secrets` by this project's existing convention
  (`scripts/split_env.sh`), even though they are not literal credentials.
  This mission does not change that convention; it documents it.

## 7. Human-only credential rotation boundary

Rotating a real secret value (Telegram bot token, exchange API key/secret,
SMTP password, webhook URL) is a human-only action performed directly on
the VPS or in BotFather/exchange consoles, following
`.env.secrets.example`'s own recovery steps (see §9 for a caveat about that
file's current wording). No agent session may generate, propose, or write
a candidate secret value into any file, log, commit, or PR.

## 8. Safe runtime verification policy (masked only)

Any future check of "is this secret configured" must report only a masked
`SET` / `UNSET` outcome per variable name — for example, a script may test
`[[ -n "${TELEGRAM_BOT_TOKEN:-}" ]]` and print `TELEGRAM_BOT_TOKEN=SET`,
never the value, never a partial value, never a hash of the value (a hash
is still an oracle). Bare `env`/`printenv` and
`systemctl show <unit> -p Environment` must never be run where the output
could reach a log, a commit, a PR, or an agent transcript, because both
can print real values.

## 9. No-secret logging / PR / CI artifact rule

No real secret value may ever appear in application logs, commit messages,
pull-request bodies/diffs, CI output, or any file under `docs/`. This
constitution document and its companions contain zero real secret values —
only variable **names** and, where useful, masked-verification technique
descriptions.

## 10. Stale documentation finding: `.env.secrets.example`

**OLD CLAIM** (as currently written at the top of `.env.secrets.example`,
verbatim intent): *"Ce fichier est un TEMPLATE. Ne le renseignez pas ici —
ces valeurs vont dans le vrai `.env` du VPS (chargé par les units systemd
via `EnvironmentFile=`)."* — i.e. the template's own header tells a human
to copy real secret values into the real `.env` file.

**CURRENT TARGET**: per `scripts/split_env.sh`'s own purpose (`.env` →
non-secret; `.env.secrets` → secrets, `chmod 600`) and per §1 of this
constitution, real secret values belong in the real `.env.secrets` file,
never in `.env`.

**FILES AFFECTED**: `.env.secrets.example` (the stale instruction);
indirectly, the real `.env` on the VPS if a human ever followed this
header literally (RUNTIME_PROOF_REQUIRED — this mission cannot and did not
check the real VPS file).

**RISK**: A human following the current header would put real secret
values in `.env`, which systemd loads *before* `.env.secrets` — so on any
duplicate key, `.env.secrets`'s (possibly-empty-or-stale) value would win
over the fresh value just placed in `.env`, or, if `.env.secrets` doesn't
define that key at all, the secret would sit unprotected in the
non-secret file (world-readable-by-convention, not `chmod 600`).

**FUTURE REMEDIATION**: a future mission should correct the header comment
in `.env.secrets.example` to say values belong in `.env.secrets` (not
`.env`), and should verify (via masked SET/UNSET checks only, per §8) that
the real VPS `.env` does not already contain secret-classified keys as a
result of the current wording. This mission does not edit
`.env.secrets.example` itself, per its explicit file-scope constraint.

## 11. Additional stale-documentation observation

`.env.secrets.example` also references `CONFIG_REFERENCE_V91.md` for the
"exhaustive" list of non-secret parameters. That file does exist at
`docs/CONFIG_REFERENCE_V91.md`, so this specific cross-reference is not
stale by itself; a future remediation mission should still reconcile it
against `ENVIRONMENT_VARIABLE_REGISTRY.md` (this mission) so the two do
not silently drift apart as new variables are added.
