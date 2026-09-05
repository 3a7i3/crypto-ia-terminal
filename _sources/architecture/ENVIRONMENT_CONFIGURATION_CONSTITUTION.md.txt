# Environment & Configuration Constitution

Mission FAM-01 (documentation-only forensic) + Mission ENV-01 (remediation).
FAM-01 recorded the target configuration constitution, the precedence
forensic performed source-only, and the policies future remediation work
must follow, without fixing any of its findings. **ENV-01 (2026-09) closes
the two PRECEDENCE_RISK findings from §5, splits `.env.example` /
`.env.secrets.example` per the target in §1b, corrects the stale header
documented in §10, and ships the human-only verifier described in §12a.**
Sections below are annotated BEFORE ENV-01 / AFTER ENV-01 /
RUNTIME_PROOF_REQUIRED where their content changed; sections not annotated
are unchanged FAM-01 findings, still accurate.

## 1. Purpose of each file

| File | Purpose |
|---|---|
| `.env` | See §1a for the CURRENT vs TARGET lifecycle classification — this file is not treated as a settled, AI-safe non-secret file yet. |
| `.env.secrets` | Secret/restricted values only: tokens, API keys/secrets, passwords, webhooks, SMTP credentials, and (per `scripts/split_env.sh`'s explicit, cautious classification) Telegram chat IDs and email addresses. HUMAN_ONLY forever — see §2. |
| `.env.secrets.example` | See §1b — currently a public template of secret-class variable names, no real values. |
| `.env.example` | See §1b — CURRENT reality is a mixture of non-secret config and secret-class placeholder names (verified by inspecting names only, e.g. Telegram bot tokens); TARGET is non-secret runtime config only. |
| `.env.smtp.example` | Public template for SMTP notification config (small, separate concern from the main secrets file). |

## 1a. `.env` current-vs-target lifecycle

**AFTER ENV-01 note**: the root cause named below (the stale
`.env.secrets.example` header telling humans to put secrets in `.env`) is
fixed as of ENV-01 (see §10). This does **not** by itself move `.env` out
of `QUARANTINED_RUNTIME_CONFIG` — the real, already-deployed VPS `.env` may
still carry secret keys written under the old, incorrect header before the
fix landed. `.env` remains `QUARANTINED_RUNTIME_CONFIG` until a human
operator runs `scripts/verify_env_separation.sh` against the real files and
certifies `SECRET_KEYS_IN_ENV_COUNT=0` per the Human `.env` Certification
Contract (§12a). RUNTIME_PROOF_REQUIRED.

`.env` is **not** permanently classified AI-forbidden, but it is also not
yet safe for an AI to inspect. Two distinct states:

- **CURRENT / BEFORE SECRET-PURGE CERTIFICATION** (today): `.env` =
  `QUARANTINED_RUNTIME_CONFIG`. Reason: historical documentation
  (`.env.secrets.example`'s own stale header, see §10) instructed humans to
  put real secret values into `.env`, so this mission cannot certify that
  the real, deployed `.env` contains non-secret content only. An AI agent
  must not inspect the real runtime `.env` until a human completes a
  secret-purge certification.
- **TARGET / AFTER HUMAN SECRET-PURGE CERTIFICATION** (future): `.env` =
  `NON_SECRET_RUNTIME_CONFIGURATION` — feature flags, thresholds, cadences,
  paths, modes, presentation settings only. Once a human operator certifies
  (via the masked SET/UNSET verification technique in §8, never by an AI
  opening the file) that no secret-classified key exists in the real
  `.env`, AI/automation MAY safely read it directly.

`.env.secrets` remains `HUMAN_ONLY` forever, in both states, regardless of
any certification of `.env` — see §2.

## 1b. `.env.example` current-vs-target

**BEFORE ENV-01** (FAM-01 finding, verified by inspecting `.env.example`'s
variable **names** only — template files are explicitly allowed reading,
this is not a secret-value read): it still contained names/placeholders
for secret-class variables, e.g. `TELEGRAM_BOT_TOKEN=`, `RADAR_BOT_TOKEN=`,
`MON_PORTFOLIO_BOT_TOKEN=`, `RAPPORT_AUTOMATIQUE_BOT_TOKEN=`,
`PAPER_ARENA_BOT_TOKEN=`, `KRAKEN_API_KEY=`/`KRAKEN_API_SECRET=`,
`GATEIO_API_KEY=`/`GATEIO_API_SECRET=`, `BINANCE_API_KEY=`/
`BINANCE_API_SECRET=`, and a commented `#SLACK_WEBHOOK_URL=` — a mixture of
non-secret config and secret-class placeholder names, not yet a clean
"public non-secret config template."

**AFTER ENV-01**: all of the above were removed from `.env.example` and
consolidated into `.env.secrets.example` (which already held the same
names with richer per-bot documentation — no credential was invented).
`EMAIL_SMTP_SERVER`/`EMAIL_SMTP_PORT`/`EMAIL_FROM_ADDR`/`EMAIL_TO_ADDR` were
also moved, per the project's own existing RESTRICTED_IDENTITY convention
(`scripts/split_env.sh::SECRET_EXACT_NAMES`) rather than a new judgment
call. `.env.example` = non-secret runtime config only;
`.env.secrets.example` = secret/restricted variable names only, with a
corrected header (§10).

**Invariants:**
- NO SECRET VALUE SHALL EXIST IN `.env`.
- NO NON-SECRET CONFIG SHOULD NEED TO LIVE IN `.env.secrets` unless it is
  explicitly classified RESTRICTED (see §6).

## 2. AI secret-access prohibition (ABSOLUTE)

No AI agent session — this agent, or any future agent — may ever read
`.env.secrets`, `.env.smtp`, or (until the §1a certification) any real
runtime `.env` by **any** means: not `cat`/`head`/`tail`/`grep`/`sed`/
`awk`/`source`, not a wildcard sweep like `cat .env*`, not any other tool,
and — critically — not under any framing that claims to make the read
safe. Specifically forbidden, with no exception: "key names only"
parsing of the real file, "masked" parsing of the real file, hashing a
real value, or determining SET/UNSET by directly opening the file
oneself. All of these still constitute the AI reading the secret file,
regardless of what it does with the result afterward.

An AI may only ever **receive the output** of an independently trusted
human/operator-side verification mechanism that the AI itself did not
run against the real secret file — for example a script a human runs
that prints `MEXC_API_KEY=SET`, `QUANT_CRYPTO_BOT_TOKEN=SET`,
`SECRET_DUPLICATE_COUNT=0`. The AI must never produce that output itself
by opening the file; it may only consume such an output already produced
by that trusted mechanism.

An agent may inspect `.env.example`, `.env.secrets.example`,
`.env.smtp.example`, `.gitignore`, `scripts/split_env.sh`,
`scripts/systemd/*.service`, `docs/SECURITY_SECRETS.md`, and variable
**names** referenced in source (`os.getenv`, `os.environ.get`,
`load_dotenv`, `EnvironmentFile=`) — never runtime values. No AI agent
session may SSH to any VPS to read these files either. This mission
(FAM-01, and this remediation pass FAM-01R) complied with this
prohibition throughout; see the confirmation in the mission's final
report.

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
| `core/advisor_loop.py:677` | default (`.env`) | `False` (ENV-01, was `True`) | Yes — `crypto-advisor.service` | **REMEDIATED** (was PRECEDENCE_RISK) |
| `watchdog_vps.py:38` | default (`.env`) | `False` (ENV-01, was `True`) | Yes — `crypto-watchdog.service` | **REMEDIATED** (was PRECEDENCE_RISK) |
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

**Headline finding, BEFORE ENV-01 (PRECEDENCE_RISK, two occurrences):**
`core/advisor_loop.py` (the process `crypto-advisor.service` runs) and the
deployed `watchdog_vps.py` (the process `crypto-watchdog.service` runs)
both called `load_dotenv(override=True)` after systemd had already loaded
`.env` then `.env.secrets` in that order. Because `override=True` forces
`python-dotenv` to overwrite any environment variable already set, any key
present in **both** `.env` and `.env.secrets` was re-set from `.env` at this
point in each process's own startup — silently reversing the precedence
systemd intended.

**AFTER ENV-01**: both call sites now use `load_dotenv(override=False)`,
the `python-dotenv` default — a variable already present in `os.environ`
(from systemd's `EnvironmentFile=.env` then `EnvironmentFile=.env.secrets`
injection, or from any pre-existing process/shell environment for manual
CLI runs) is never overwritten; only variables still absent afterward get
populated from `.env`. This restores `PRE-EXISTING PROCESS ENVIRONMENT >
dotenv file` for both systemd entrypoints while leaving manual/CLI
execution — which has no pre-existing value to protect — unaffected.
Proven deterministically with dummy fixtures (no real `.env`/`.env.secrets`
read) in `tests/test_dotenv_precedence.py` (CASE A/B/C, plus a
regression-documentation test reproducing the pre-ENV-01 defect). This is a
source-only proof: whether the real VPS `.env`/`.env.secrets` actually
share a duplicate key today, and whether the fix changes observed runtime
behavior there, is **RUNTIME_PROOF_REQUIRED** — to be confirmed only via
`scripts/verify_env_separation.sh`'s sanitized output (§12a), run by a human
operator, never by an AI opening either file.

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
is still an oracle). Bare `env`/`printenv` and **any** form of
`systemctl show <unit> -p Environment` — including a "filter afterward"
framing — must never be run or prescribed at all, even conditionally: the
raw command can materialize the full environment (secrets included)
before any filtering happens, so filtering after the fact does not make it
safe. The only acceptable design is a trusted human/operator-side
verifier that itself exposes only explicitly-approved non-secret fields
plus masked secret-presence outcomes (`SET`/`UNSET`); an AI agent only
ever receives that mechanism's already-sanitized result, never a raw
environment dump, and never runs `systemctl show ... -p Environment`
itself under any circumstance.

## 9. No-secret logging / PR / CI artifact rule

No real secret value may ever appear in application logs, commit messages,
pull-request bodies/diffs, CI output, or any file under `docs/`. This
constitution document and its companions contain zero real secret values —
only variable **names** and, where useful, masked-verification technique
descriptions.

## 10. Stale documentation finding: `.env.secrets.example` — FIXED (ENV-01)

**OLD CLAIM** (as written at the top of `.env.secrets.example` before
ENV-01, verbatim intent): *"Ce fichier est un TEMPLATE. Ne le renseignez
pas ici — ces valeurs vont dans le vrai `.env` du VPS (chargé par les units
systemd via `EnvironmentFile=`)."* — i.e. the template's own header told a
human to copy real secret values into the real `.env` file.

**STATUS: FIXED (ENV-01)**. The header now reads (paraphrased): real secret
values → `.env.secrets`; non-secret config → `.env`, matching §1/§4/§6 of
this constitution and `scripts/split_env.sh`'s own intent. See §1a for why
this fix does not, by itself, retroactively certify the already-deployed
real VPS `.env` as clean.

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

## 12a. Human-only environment verifier & `.env` certification contract (ENV-01)

**Verifier**: `scripts/verify_env_separation.sh` — a sanitized, counts/flags
-only report (`ENV_FILE_PRESENT`, `SECRETS_FILE_PRESENT`, `ENV_MODE_OK`,
`SECRETS_MODE_OK`, `SECRET_KEYS_IN_ENV_COUNT`, `DUPLICATE_WITHIN_ENV_COUNT`,
`DUPLICATE_WITHIN_SECRETS_COUNT`, `CROSS_FILE_DUPLICATE_KEY_COUNT`, and an
opt-in `--verbose-names` mode printing only `NAME=SET`/`NAME=UNSET`). It
never prints a value, never sources/exports/evaluates the files it reads,
and derives its secret-name registry from `.env.secrets.example` by
default. **THIS SCRIPT MUST BE RUN BY THE HUMAN OPERATOR** against the real
`.env`/`.env.secrets` — an AI agent must not invoke it against those real
files (per §2), and did not in this mission; it was tested only against
`tmp_path` dummy fixtures (`tests/test_verify_env_separation.py`).

ENV-01R correction: an earlier revision of this contract used a single
`DUPLICATE_KEY_COUNT` name for what the verifier actually computed as a
WITHIN-file duplicate count, while this contract's own wording ("no name
defined in both files") describes a CROSS-file property — a naming/property
mismatch. The verifier now emits three distinct, unambiguous metrics (see
above); `DUPLICATE_KEY_COUNT` no longer exists as an emitted name.

**Human `.env` Certification Contract** — required to transition `.env`:
`QUARANTINED_RUNTIME_CONFIG` → `NON_SECRET_RUNTIME_CONFIGURATION` (§1a):

1. Human operator runs `scripts/verify_env_separation.sh` on the real VPS
   files.
2. `SECRET_KEYS_IN_ENV_COUNT=0` (no secret-class name leaked into `.env`).
3. `CROSS_FILE_DUPLICATE_KEY_COUNT=0` (no name defined in both `.env` and
   `.env.secrets` — required minimum). `DUPLICATE_WITHIN_ENV_COUNT=0` and
   `DUPLICATE_WITHIN_SECRETS_COUNT=0` are preferred additional evidence of
   file hygiene (a within-file duplicate is not itself a cross-file
   precedence risk, but indicates a malformed file).
4. `ENV_MODE_OK=YES` (`.env` not world-writable).
5. `SECRETS_MODE_OK=YES` (`.env.secrets` is `600`/`400`).
6. Expected secret variables report `SET` where the deployment requires
   them (`--verbose-names`), with no value ever displayed.
7. The operator records the certification (date, verifier output, sign-off)
   in an operator-side log — never by having an AI agent draft or witness
   the real values.

Only after this certification is recorded may an AI agent read the real
`.env` directly (never `.env.secrets`, which remains `HUMAN_ONLY` forever
per §2).

## 11. Additional stale-documentation observation

`.env.secrets.example` also references `CONFIG_REFERENCE_V91.md` for the
"exhaustive" list of non-secret parameters. That file does exist at
`docs/CONFIG_REFERENCE_V91.md`, so this specific cross-reference is not
stale by itself; a future remediation mission should still reconcile it
against `ENVIRONMENT_VARIABLE_REGISTRY.md` (this mission) so the two do
not silently drift apart as new variables are added.
