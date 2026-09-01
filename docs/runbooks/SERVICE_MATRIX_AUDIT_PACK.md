# Audit Pack `service_matrix`

## Purpose

`service_matrix` is a bounded READ-ONLY observation of the systemd services
that make up the research infrastructure. It answers four narrow questions:

1. Is each known unit installed?
2. What are its current systemd active/sub states?
3. Is it enabled, failed, restarting, or waiting for a daemon reload?
4. Was the complete fixed catalog observed without query errors?

It does **not** prove application health, data freshness, Telegram delivery,
HTTP reachability, correct parameters, or correct scientific outputs. Those
questions belong to later, separate Audit Packs.

The source file is `scripts/claude-service-matrix.py`. On the VPS it is
installed root-owned as `/usr/local/bin/claude-service-matrix` and is reached
only through the exact dispatcher token `service_matrix`.

## Fixed service catalog

The caller cannot provide a unit name. Version 1 contains exactly these units:

| Unit | Role | Tier |
|---|---|---|
| `crypto-advisor.service` | decision engine | core |
| `crypto-watchdog.service` | runtime safety | safety |
| `crypto-dashboard.service` | web interface | interface |
| `crypto-lmi-observatory.service` | live-market observation | observation |
| `crypto-market-horizons.service` | market horizons | observation |
| `crypto-market-observer.service` | market observer | observation |
| `crypto-market-radar.service` | market radar | observation |
| `crypto-quant-observer.service` | Telegram quant observer | interface |
| `crypto-radar-bot.service` | Telegram radar | interface |
| `paper-arena.service` | paper-execution interface | interface |

An absent unit is reported as `not_found`; it is not silently removed from the
matrix. Changing the catalog requires a reviewed code change and a new
deployment.

## Safe observation contract

The pack invokes only `/usr/bin/systemctl show` and requests this closed
property list:

- `LoadState`, `ActiveState`, `SubState`, `UnitFileState`;
- `MainPID`, `NRestarts`;
- `ExecMainCode`, `ExecMainStatus`, `Result`;
- `ActiveEnterTimestamp`, `StateChangeTimestamp`;
- `NeedDaemonReload`.

It never requests or emits `Environment`, `EnvironmentFiles`, `ExecStart*`,
`ExecStop`, command lines, journal entries, service logs, or raw stderr. Each
unit query has a three-second timeout. Total rendered stdout is limited to
24,000 bytes.

The pack accepts no arguments, performs no restart/start/stop/reload/enable,
does not write systemd state, and does not use `sudo`.

## Function reference

### `utc_now()`

Produces the observation timestamp in second-resolution UTC. It does not read
application state and is used only to timestamp the matrix.

### `catalog_sha256(catalog)`

Hashes the ordered `(unit, role, tier)` catalog as canonical JSON. This lets an
auditor prove which catalog definition produced a result without exposing
runtime content.

### `parse_properties(stdout)`

Parses `key=value` output from systemd. Unknown keys are discarded even if
systemd returns them unexpectedly. Only `SAFE_PROPERTIES` can enter evidence.

### `operational_state(properties, query_status)`

Normalizes states into `active`, `inactive`, `activating`, `deactivating`,
`failed`, `reloading`, `maintenance`, `not_found`, or `unknown`. It deliberately
does not translate `active` into `healthy`.

### `query_service(spec, run_command)`

Queries one `ServiceSpec` from the fixed catalog using an argument array, a
minimal environment, and a three-second timeout. It classifies the collection
as `ok`, `not_found`, `timeout`, `command_unavailable`, or `command_failed`.
Raw stderr is discarded.

### `_bounded_integer(value)`

Converts only short unsigned decimal values, such as PID, restart count and
exit status. Unexpected or oversized text becomes JSON `null`.

### `_service_record(spec, properties, query_status, command_exit_code)`

Builds the stable public record for one unit. It fills missing safe properties
with `unknown` and cannot add arbitrary systemd fields.

### `collect_matrix(catalog, run_command, observed_at_utc)`

Queries every catalog entry, calculates summary counts and returns the payload
plus an exit code. `not_found` is a complete observation. Timeout or command
failure marks the collection `partial`.

### `render_matrix(payload)`

Renders deterministic, sorted, indented JSON and fails closed if UTF-8 stdout
would exceed 24,000 bytes.

### `main(argv)`

Rejects every caller argument, performs one collection and writes one JSON
document. It emits no traceback or unbounded error content.

## Result schema

Top-level fields:

- `schema_version`: schema contract version;
- `pack`: always `service_matrix`;
- `observed_at_utc`: observation timestamp;
- `collection_status`: `complete` or `partial`;
- `catalog_sha256`: fixed-catalog fingerprint;
- `contract`: timeout, output ceiling and negative disclosure assertions;
- `summary`: catalog/active/inactive/failed/not-found/query-error counts;
- `services`: one record per fixed unit, in catalog order.

Important interpretation rule: `active_state=active` proves only the systemd
state at observation time. It is not proof that the process produces fresh,
correct or complete scientific data.

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Complete matrix; installed and absent units were observed normally |
| `64` | Caller attempted to pass an argument |
| `69` | Partial matrix due to timeout or systemctl failure |
| `70` | Hard output-size contract would be exceeded |

The GitHub bridge always commits the envelope before marking a non-zero remote
action as failed, so partial evidence remains attributable.

## Tests and negative guarantees

`tests/test_claude_service_matrix.py` verifies:

- catalog uniqueness and fixed `.service` names;
- exclusion of environment and command properties;
- bounded output and raw-stderr non-disclosure;
- correct handling of absent units and timeouts;
- rejection of caller-controlled arguments;
- fail-closed output-size behavior.

`tests/test_vps_audit_request.py` verifies that the request validator, workflow
choice list and dispatcher contain the same exact action token.

## Governed deployment and runtime certification

After the PR is merged:

1. Download the script and dispatcher from the exact merge commit.
2. Verify independently supplied SHA-256 hashes and syntax.
3. Back up the current dispatcher with an explicit non-wildcard path.
4. Install the pack as `root:root` mode `0755` in `/usr/local/bin`.
5. Install the matching dispatcher as `root:root` mode `0755`.
6. Run the pack directly as `claude-audit` to confirm systemd metadata access.
7. Submit one commit-bound `service_matrix` request through BRIDGE-04.
8. Certify the envelope, output bound, catalog hash and exit code.

No production service is restarted during deployment or certification.

## Rollback

Rollback removes only the newly installed pack and restores the exact saved
dispatcher. Because the installed targets and backup timestamp are deployment
specific, mobile rollback commands must be generated only after those paths
have been observed and named explicitly. No wildcard deletion is permitted.
