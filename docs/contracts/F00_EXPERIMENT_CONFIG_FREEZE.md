# F00-CONFIG-FREEZE-01 — Effective Experiment Configuration Freeze

## Purpose

F-00 must be reproducible from an exact source revision, exact PPL epoch, and
an exact non-secret configuration surface.

The PPL epoch manifest remains immutable and continues to describe the epoch
birth/cutover contract. This freeze is a separate experiment-governance artifact;
it does not rewrite the manifest, EPOCH_CREATED, legacy boundary, or capital.

## Canonical artifact

For epoch `<paper_epoch_id>`:

`databases/ppl_authority/<paper_epoch_id>.experiment-config.json`

The snapshot and its admission overlay are local runtime evidence and are never committed with environment values. The admission overlay is created while inactive and MUST NOT be wired into systemd before separate owner authorization.

Schema:

`F00_EXPERIMENT_CONFIG_V1`

The deterministic SHA-256 covers:
- schema;
- exact paper epoch id;
- exact runtime source SHA;
- active pre-start EnvironmentFile paths in precedence order;
- immutable admission-overlay path, SHA-256 and planned override;
- the pre-start guard (`PB_MAX_POSITIONS=0`);
- every selected material parameter in its FINAL F-00 experiment value;
- value;
- provenance;
- source;
- production call-sites.

No timestamp is included in the hashed payload.

## Environment precedence

The capture command receives each EnvironmentFile in the same order as systemd.
Later files override earlier files.

For the current F-00 deployment this is expected to be:

1. `.env`
2. `.env.secrets`
3. the canonical F00 cutover overlay

The operator must verify this order against:

`systemctl show crypto-advisor.service -p EnvironmentFiles --value --no-pager`

before capture.

## Material parameter surface

The allowlist is intentionally bounded to namespaces that can alter the sampled
population, admission decision, sizing, exits, risk, universe, or PAPER/PPL
authority. It includes signal, gate, MTF, regime, portfolio, execution,
allocation, conviction, no-trade, meta-strategy, executive override, risk
governor, capital throttle, exposure, invariants, safety, V9, position manager,
MEXC simulator, P6/P8/P9, Kelly, PAPER and PPL namespaces plus specific
exchange/live-confirmation controls.

This is an experiment-governance allowlist, not a dump of the process
environment.

## Secret exclusion

Secret-looking keys are excluded before serialization. API keys, secrets,
tokens, passwords, private keys, credentials, webhooks, chat identifiers,
SMTP/email credentials and equivalent key names must never enter:
- the snapshot;
- GitHub comments;
- terminal proof output.

The tool prints only aggregate counts, epoch/source identity and snapshot hash.

## Explicit versus code-default values

For each material variable:

- if explicitly configured, the effective value and winning EnvironmentFile are
  recorded as `EXPLICIT_ENVIRONMENT_FILE`;
- if unset, production Python call-sites are scanned for
  `os.getenv(...)` / `os.environ.get(...)` literal defaults;
- one unambiguous default is recorded as `CODE_DEFAULT`;
- conflicting defaults fail closed;
- non-literal defaults fail closed when the variable is unset.

Explicit configuration intentionally resolves conflicting code defaults because
the service-level value wins at every call-site.

The runtime source SHA pins the exact implementation and all code-default
call-sites.

## Production scan boundary

Offline/test/documentation trees are excluded from default discovery:
- tests;
- scripts;
- tools;
- docs;
- notebooks;
- Obsidian material;
- archived source;
- virtual environments;
- S2 forensic scripts.

The remaining production tree is scanned, but materiality is still bounded to
the deployed F00 advisor runtime.

For the certified F00 runtime in this phase, `crypto-advisor.service` executes
`core/advisor_loop.py`. The P10/ColdStart namespace belongs to the strangler
path `runtime/advisor_main.py` and is not referenced by the deployed advisor
loop. Therefore `P10_*` is explicitly excluded from the F00 material namespace
until that runtime becomes the deployed execution path. This prevents inactive
future/alternate runtime defaults from blocking or contaminating the current
experiment fingerprint.

If the service entrypoint later migrates to `runtime/advisor_main.py`, the
material namespace contract must be revised and recertified before another
experiment freeze.

## Pre-start guard versus final experiment configuration

`PB_MAX_POSITIONS=0` is a temporary physical admission barrier, not the final
portfolio limit for the F-00 experiment. Freezing it as the final value would
make the snapshot invalid the moment admissions are opened.

Capture therefore requires the operator to declare a future positive
`PB_MAX_POSITIONS`. The tool creates, with O_EXCL, a separate inactive file:

`databases/ppl_authority/<paper_epoch_id>.admission.env`

containing only:

`PB_MAX_POSITIONS=<planned positive integer>`

The snapshot's parameter map represents the FINAL experiment configuration
after this overlay would be applied, while `prestart_guard` proves the current
active value is still zero. The overlay is not added to systemd by capture.

Capture refuses to proceed unless:
- `PAPER_LIFECYCLE_AUTHORITY=PPL_AUTHORITY`;
- `PAPER_TRADING_ENABLED=true`;
- currently active `PB_MAX_POSITIONS=0`;
- planned activation `PB_MAX_POSITIONS >= 1`;
- `PPL_AUTHORITY_EPOCH_ID` exactly matches the requested epoch;
- the git worktree is clean.

Thus configuration freeze and admission authorization remain separate acts.

## Immutability

Snapshot creation and admission-overlay creation both use exclusive creation and never overwrite existing files. If either exists, capture fails. Correction requires explicit governance and a new artifact disposition; silent replacement is forbidden.

## Validation

`validate`:

1. verifies the stored snapshot SHA;
2. requires the repository to remain clean;
3. requires the exact runtime source SHA;
4. re-reads the same active pre-start EnvironmentFiles in the frozen order;
5. verifies the inactive admission overlay byte hash;
6. re-scans production code defaults;
7. rebuilds the final experiment payload from the pre-start guard + frozen activation plan;
8. requires byte-semantic equality and the same SHA-256.

Any source/config/default/precedence drift fails closed.

## Operator commands

Capture, while Advisor and Watchdog remain stopped and PB=0:

```bash
python3 -B scripts/f00_experiment_config_freeze.py capture \
  --epoch F00-EPOCH-01-20260920T084335Z \
  --env-file .env \
  --env-file .env.secrets \
  --env-file databases/ppl_authority/F00-EPOCH-01-20260920T084335Z.cutover.env \
  --activation-pb-max-positions <OWNER_AUTHORIZED_VALUE>
```

Validation:

```bash
python3 -B scripts/f00_experiment_config_freeze.py validate \
  --snapshot databases/ppl_authority/F00-EPOCH-01-20260920T084335Z.experiment-config.json
```

A PASS from this tool is necessary but not sufficient to start F-00. The parent F00-START precheck must still certify the clean PPL population. Only after that PASS may the owner separately authorize wiring the already-frozen admission overlay into systemd. The wiring step must use the exact overlay hash recorded by the snapshot.

## Forbidden interpretation

This artifact does not:
- change or tune any parameter;
- declare any parameter optimal;
- mutate PPL;
- modify the 1000-USDT capital baseline;
- start F-00;
- authorize burn-in, TESTNET or LIVE.
