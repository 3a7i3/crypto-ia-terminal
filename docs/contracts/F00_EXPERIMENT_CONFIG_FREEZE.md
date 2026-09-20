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

The artifact is local runtime evidence and is never committed with environment
values.

Schema:

`F00_EXPERIMENT_CONFIG_V1`

The deterministic SHA-256 covers:
- schema;
- exact paper epoch id;
- exact runtime source SHA;
- EnvironmentFile paths in precedence order;
- every selected material parameter;
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
MEXC simulator, P6/P8/P9/P10, Kelly, PAPER and PPL namespaces plus specific
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

The remaining production tree is scanned.

## Pre-start invariants

Capture refuses to proceed unless:
- `PAPER_LIFECYCLE_AUTHORITY=PPL_AUTHORITY`;
- `PAPER_TRADING_ENABLED=true`;
- `PB_MAX_POSITIONS=0`;
- `PPL_AUTHORITY_EPOCH_ID` exactly matches the requested epoch;
- the git worktree is clean.

Thus the freeze cannot itself open admissions.

## Immutability

Snapshot creation uses exclusive creation and never overwrites an existing
snapshot.

If the file already exists, capture fails. Correction requires explicit
governance and a new artifact disposition; silent replacement is forbidden.

## Validation

`validate`:

1. verifies the stored snapshot SHA;
2. requires the repository to remain clean;
3. requires the exact runtime source SHA;
4. re-reads the same EnvironmentFiles in the frozen order;
5. re-scans production code defaults;
6. rebuilds the canonical payload;
7. requires byte-semantic equality and the same SHA-256.

Any source/config/default/precedence drift fails closed.

## Operator commands

Capture, while Advisor and Watchdog remain stopped and PB=0:

```bash
python3 -B scripts/f00_experiment_config_freeze.py capture \
  --epoch F00-EPOCH-01-20260920T084335Z \
  --env-file .env \
  --env-file .env.secrets \
  --env-file databases/ppl_authority/F00-EPOCH-01-20260920T084335Z.cutover.env
```

Validation:

```bash
python3 -B scripts/f00_experiment_config_freeze.py validate \
  --snapshot databases/ppl_authority/F00-EPOCH-01-20260920T084335Z.experiment-config.json
```

A PASS from this tool is necessary but not sufficient to start F-00. The parent
F00-START precheck must still certify the clean PPL population and the owner must
separately authorize opening PAPER admissions.

## Forbidden interpretation

This artifact does not:
- change or tune any parameter;
- declare any parameter optimal;
- mutate PPL;
- modify the 1000-USDT capital baseline;
- start F-00;
- authorize burn-in, TESTNET or LIVE.
