# PPL-02E-R4 — Authority Cutover, Rollback & WEB-02 Contract

Status: **SOURCE IMPLEMENTATION CANDIDATE**

Parent: #180
Mission issue: #184
Baseline: `main@1a3d1df896613e3867b57aff8b8cc9c9fdb0bf80`

## Purpose

R4 implements the source contract required to move PAPER lifecycle authority
from Legacy/MexcSimulator-first semantics to durable PPL authority.

Merging R4 does not itself change production environment variables and does
not perform a VPS cutover.

## Quiescent cutover

A new authority manifest may be constructed only when all facts are true:

- legacy process is stopped;
- legacy open positions = 0;
- legacy pending orders = 0;
- legacy lifecycle transitions in flight = 0.

The manifest fingerprints the immutable legacy JSONL boundary with SHA-256 and
event count.

## Authority epoch identity

The authority epoch:

- is a new explicit `paper_epoch_id`;
- must differ from the predecessor SHADOW epoch;
- has role `PPL_AUTHORITY_TRANSITION`;
- uses PPL event schema v2;
- records explicit code SHA, config hash and initial scientific capital;
- is distinct from any future F-00/EPOCH-01.

The current SHADOW epoch is never promoted.

## Bootstrap

`PAPER_LIFECYCLE_AUTHORITY=PPL_AUTHORITY` requires:

- `PAPER_TRADING_ENABLED=true`;
- `PPL_AUTHORITY_MANIFEST`;
- `PPL_AUTHORITY_STORE_ROOT`;
- `PPL_AUTHORITY_EPOCH_ID`.

The configured epoch id must exactly match the manifest.

Bootstrap creates/replays the explicit authority epoch. Any manifest, store,
replay or capital error is fatal. There is no legacy fallback.

## Durable-first lifecycle

For certified MARKET operations:

OPEN:

1. determine fill/fee/TP/SL and durable timeout boundaries;
2. fsync PPL `POSITION_OPENED`;
3. replay PPL;
4. project simulator memory from the committed state;
5. project compatibility JSONL best-effort.

CLOSE:

1. determine fill/exit fee;
2. fsync PPL `POSITION_CLOSED`;
3. replay PPL;
4. project simulator memory from the committed state;
5. project compatibility JSONL best-effort.

A PPL append failure therefore leaves simulator lifecycle memory unchanged.

LIMIT and STOP_LIMIT remain fail-closed under PPL authority until their
pending-order lifecycle receives an independent durable contract.

## Restart

PPL is the only restart authority.

Schema-v2 OPEN facts restore:

- principal;
- side;
- entry price;
- entry fee;
- opened timestamp;
- TP;
- SL;
- timeout deadline;
- recovery deadline.

After the recovery window expires, restart writes
`POSITION_UNRESOLVED`; it never fabricates a CLOSE, price or zero PnL.

## Scientific capital

R3 remains authoritative for the handoff:

`initial_virtual_capital + realized_pnl`

No legacy JSONL or exchange fallback is permitted under PPL authority.
Unresolved capital fails closed.

## Compatibility ledger

`paper_trades.jsonl` is downstream-only after cutover.

A compatibility projection failure does not undo the authoritative PPL event.
The projector is idempotent and can catch up from the durable PPL stream.

## Retry/crash semantics

OPEN/CLOSE event ids are deterministic by epoch/type/trade.

If a crash occurs after durable append but before memory projection, a retry
reuses the original durable sequence and returns exact-event idempotence rather
than inventing a second lifecycle event.

## Rollback

There is no hot authority flip and no automatic fallback.

Rollback to Legacy/SHADOW is source-authorized only while the authority epoch
contains no lifecycle event beyond `EPOCH_CREATED`.

Once any authoritative OPEN/CLOSE/UNRESOLVED exists:

`BLOCKED_RECONCILIATION_REQUIRED`

A later rollback requires an explicit reconciliation mission; changing one
environment variable is not an authorized procedure.

## WEB-02

Before cutover:

- mode = `SHADOW_COMPARISON`;
- Legacy authority = `PAPER_AUTHORITY`;
- PPL authority = `NONE`.

After cutover:

- mode = `AUTHORITY_STATUS`;
- Legacy compatibility source authority = `NONE`;
- PPL authority = `PAPER_AUTHORITY`;
- legacy-vs-shadow comparison is disabled;
- the authoritative epoch and PPL events remain observable.

The API reader and frontend validator accept both truthful states.

## Boundaries

R4 does not:

- perform the production cutover;
- restart production services;
- create an F-00 epoch;
- authorize burn-in;
- authorize LIVE;
- implement Financial Institute semantics.

After source merge, an independent runtime cutover certification is still
required before PPL may be declared the production PAPER authority.
