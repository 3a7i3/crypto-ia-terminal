# Audit Pack `service_trigger_matrix`

## Purpose

`service_trigger_matrix` explains why three `static` oneshot services can be
inactive without being broken. It observes their fixed systemd timers, runtime
relationships, safe dependencies, last trigger and next scheduled activation.

It answers these narrow questions:

1. Is each expected timer installed and active?
2. Is the timer waiting for a future activation?
3. Does it target the expected oneshot service?
4. When did it last trigger and when is its next known elapse?
5. Are the service and timer dependency names consistent with the fixed pair?

It does not read unit-file contents, environment files, commands, journals or
application output. It does not prove that a completed oneshot produced fresh
or scientifically correct data.

## Static hypothesis established from Git

The repository declares these three pairs:

| Timer | Service | Expected cadence |
|---|---|---|
| `crypto-market-observer.timer` | `crypto-market-observer.service` | every 15 minutes after boot |
| `crypto-market-radar.timer` | `crypto-market-radar.service` | daily at 06:00 UTC |
| `crypto-market-horizons.timer` | `crypto-market-horizons.service` | daily at 06:15 UTC |

The cadence labels are catalog expectations. Runtime systemd metadata remains
the authoritative observation. A mismatch is reported rather than repaired.

## Fixed authority boundary

The caller cannot select a timer, service, path or property. The program
accepts no arguments and invokes only `/usr/bin/systemctl show` for the six
fixed unit names.

Safe timer properties:

- load, active, sub and unit-file states;
- `Unit`, `Triggers`, `Wants`, `Requires`, `After`, `Before`;
- last trigger, next realtime/monotonic elapse;
- persistence, accuracy, randomized delay and result.

Safe service properties:

- load, active, sub and unit-file states;
- service type and `TriggeredBy`;
- `Wants`, `Requires`, `After`;
- last state change, last active entry, result and numeric main status.

The pack excludes `Environment*`, `ExecStart*`, `ExecStop`, paths, drop-ins,
command lines, cgroup content, journals and raw stderr. Each query has a
three-second timeout. Each dependency list is restricted to 32 valid unit-name
tokens. Total stdout is limited to 24,000 bytes.

## Function reference

### `utc_now()`

Produces the second-resolution UTC timestamp attached to the observation.

### `catalog_sha256(catalog)`

Hashes the ordered timer, service, role and expected-cadence catalog as
canonical JSON. This identifies the exact pair definition used by a result.

### `parse_properties(stdout, allowed_properties)`

Parses `key=value` systemd output. Unexpected properties are discarded before
they can enter the evidence document.

### `bounded_scalar(value)`

Accepts only short, control-character-free scalar values. Missing, oversized or
invalid values become explicit normalized markers.

### `bounded_unit_list(value)`

Splits a dependency field into at most 32 tokens matching a strict systemd
unit-name syntax. Paths, assignments and arbitrary text are rejected.

### `bounded_integer(value)`

Converts only short unsigned decimal status fields. Unexpected text becomes
JSON `null`.

### `query_unit(unit, properties, run_command)`

Runs one fixed `systemctl show` query with a minimal environment and a
three-second timeout. It returns `ok`, `not_found`, `timeout`,
`command_unavailable` or `command_failed`. Raw stderr is never retained.

### `timer_state(properties, query_status)`

Normalizes the observed timer into `scheduled_waiting`, another bounded active
substate, `inactive`, `failed`, `not_found` or `unknown`. It does not claim that
the triggered application is healthy.

### `relationship_status(spec, timer_query, service_query)`

Compares the timer's `Unit`/`Triggers` and the service's `TriggeredBy` metadata
against the fixed expected pair. It emits `match`, `mismatch`, `timer_not_found`,
`service_not_found` or `unknown`.

### `build_pair_record(spec, timer_query, service_query)`

Builds the stable public schema for one pair: scheduling state, relationship,
last/next activation fields and bounded dependency names.

### `collect_matrix(catalog, run_command, observed_at_utc)`

Queries all three timer/service pairs and calculates completeness, scheduled,
inactive, failed, absent, mismatch and query-error counts.

### `render_matrix(payload)`

Renders deterministic sorted JSON and fails closed above the 24,000-byte
stdout ceiling.

### `main(argv)`

Rejects all caller arguments, emits one matrix and returns the collection exit
code without traceback or unbounded error content.

## Interpretation contract

Evidence supporting normal inactivity requires all of the following:

- service type is `oneshot` and currently `inactive/dead`;
- last service result is `success` with main status `0`;
- paired timer is loaded, active and waiting;
- relationship status is `match`;
- last trigger is known;
- a realtime or monotonic next elapse is known.

If one condition is absent, the verdict is `INCONCLUSIF` or `À SURVEILLER`, not
an instruction to restart the service.

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Complete observation, including explicit absent-unit states |
| `64` | Caller attempted to provide an argument |
| `69` | Partial collection due to timeout or systemctl failure |
| `70` | Output would exceed the hard size limit |

## Tests and negative guarantees

`tests/test_claude_service_trigger_matrix.py` verifies:

- the exact three-pair catalog;
- exclusion of sensitive properties and raw stderr;
- correct matching and mismatch detection;
- explicit absent-timer behavior;
- partial evidence on timeout;
- dependency syntax and count bounds;
- rejection of caller-controlled arguments;
- fail-closed output limiting.

`tests/test_vps_audit_request.py` verifies the same action token across the
request validator, GitHub workflow and forced-command dispatcher.

## Governed deployment and certification

After merge:

1. Download the pack and dispatcher from the exact merge commit.
2. Verify independently supplied SHA-256 hashes and syntax.
3. Back up the current dispatcher to one explicit path.
4. Install the pack root-owned in `/usr/local/bin`.
5. Run it directly as `claude-audit` and inspect only a compact summary.
6. Install the matching dispatcher.
7. Submit one commit-bound `service_trigger_matrix` request.
8. Verify the envelope, request hash, catalog hash, exit code and three records.

No service or timer is started, stopped, restarted, enabled, disabled or
reloaded during deployment or certification.

## Rollback

Restore the exact saved dispatcher and remove only the exact installed pack
path. Deployment-specific mobile commands must name those paths explicitly;
wildcards and recursive deletion are prohibited.
