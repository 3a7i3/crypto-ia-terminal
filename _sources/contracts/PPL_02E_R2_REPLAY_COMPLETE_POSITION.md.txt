# PPL-02E-R2 — Replay-Complete PAPER Position Contract

Status: **SOURCE IMPLEMENTATION CANDIDATE**

Parent: #180  
Mission issue: #182  
Baseline: `main@69d32fb1240d05e6ea90fc2d7ff6cb3a4f0fa4ff`

## 1. Purpose

R2 makes future authoritative PAPER positions restartable from durable PPL
evidence without consulting current environment defaults or
`paper_trades.jsonl`.

It does not promote PPL and does not wire the production runtime.

## 2. Schema generations

### Schema v1

Historical/SHADOW schema.

`POSITION_OPENED` contains:

- symbol
- side
- principal
- entry_price
- entry_fee

It remains readable exactly as historical evidence.

An open v1 position is **not replay-complete**. Missing TP/SL/timeout facts are
not inferred.

### Schema v2

Future authoritative/replay-complete schema.

`POSITION_OPENED` adds:

- `tp_price`
- `sl_price`
- `timeout_at`
- `recovery_eligible_until`

The event timestamp remains the sole `opened_at` authority.

One epoch cannot mix v1 and v2 events.

## 3. Deadline invariants

For v2:

- TP and SL are finite and strictly positive;
- `timeout_at > opened_at`;
- `recovery_eligible_until >= timeout_at`.

No current runtime configuration may alter these values during replay.

## 4. Restart planning

`paper_trading.ppl_recovery.plan_restart_recovery()` is pure and performs no
I/O.

For each replay-complete open position:

- `now < timeout_at` -> `RESTORE_MONITORING`
- `timeout_at <= now <= recovery_eligible_until` -> `RESTORE_TIMEOUT_DUE`
- `now > recovery_eligible_until` -> `UNRESOLVED_REQUIRED`

The planner does not fabricate a price, close, PnL, or inverse event.

## 5. Historical honesty

A v1 open position cannot be passed through authoritative restart planning.
It raises `ReplayIncompletePositionError`.

This is deliberate:

**missing historical facts remain missing.**

## 6. Boundaries

R2 does not:

- create an authority epoch;
- change scientific capital;
- change legacy compatibility JSONL;
- perform cutover or rollback;
- alter LIVE execution;
- authorize F-00 or burn-in.

Those responsibilities remain R3/R4 or later missions.
