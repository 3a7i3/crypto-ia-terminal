# PPL-02D — SHADOW MODE Contract

Status: **IMPLEMENTATION IN PROGRESS**

Mission: PPL-02D — parallel legacy/PPL projection with zero PPL authority

Baseline SHA: `f86a561eb487954b2b9e770a4238298e0db022cf`

Issue: `#167`

## 1. Purpose

PPL-02D runs the existing legacy PAPER accounting path and the PPL event-sourced accounting projection in parallel from the same MEXC simulator semantic facts.

The mission is observational. It does not promote PPL to PAPER authority and does not change execution, risk, sizing, strategy, admission, exchange, Telegram, or REAL behavior.

The required outcome is:

```text
same MEXC_SIM semantic OPEN/CLOSE facts
        |                    |
        v                    v
legacy PAPER             PPL SHADOW
(authoritative)          (non-authoritative)
```

Any divergence is evidence for WEB-02 and later authority-transition work. PPL-02D never repairs legacy accounting by mutating the legacy path.

## 2. Certified forensic baseline

The Phase-0 forensic investigation established:

- the production process is `core/advisor_loop.py`;
- current PAPER positions are held by `_virtual_portfolio` / `MexcSimulator`;
- the PAPER decision path calls `_virtual_portfolio.place_market_order(...)`;
- `MexcSimulator._fill_market()` knows the exact entry fill and entry fee;
- `MexcSimulator._close_position()` knows the exact exit fill and exit fee;
- both transitions currently persist the legacy `PaperTradeRecorder` journal;
- a separate PositionManager/ExecutionEngine recorder path exists in `advisor_loop`, but its OPEN does not carry explicit `fee_entry_usd` and its CLOSE does not carry explicit exit fee;
- `advisor_loop::_remediate_orphan_opens()` can rewrite the legacy journal during startup but is not a financial semantic OPEN/CLOSE producer;
- the active legacy journal contains no `paper_epoch_id` or `decision_id` and no explicit exit fee records;
- the legacy JSONL is therefore not a complete SHADOW input boundary.

Consequently, PPL-02D observes the **MEXC_SIM semantic transition**, never the legacy JSONL.

## 3. Absolute authority boundary

PPL-02D MUST NOT:

- call `place_market_order`, `_fill_market`, `_close_position`, execution engines, exchange APIs, strategy code, risk gates, admission policy, sizing, or PortfolioBrain;
- create, resize, close, reject, approve, or otherwise influence a legacy position;
- modify `paper_trades.jsonl`;
- derive missing fees, prices, capital, identity, or provenance from current configuration or historical PnL;
- create a new paper epoch on restart, deploy, pull, process start, or service restart;
- become a source for any execution decision;
- be used by REAL trading.

Legacy PAPER remains authoritative throughout PPL-02D.

## 4. Shadow source domain

The only certified source domain for PPL-02D is:

```text
MEXC_SIM
```

A PositionManager/ExecutionEngine recorder event is not automatically equivalent to a MEXC_SIM financial event and must not be silently mixed into the PPL shadow stream.

If the runtime cannot prove that an observed fact belongs to MEXC_SIM, the fact is not appended to PPL.

## 5. Semantic fact contract

PPL-02D receives immutable facts produced by an already-completed legacy simulator transition.

### OPEN fact

Required fields:

- `trade_id`
- `symbol`
- canonicalizable side (`BUY`/`SELL`/`LONG`/`SHORT`)
- `principal`
- exact `entry_price`
- exact `entry_fee`
- semantic timestamp
- optional explicit `decision_id`

The OPEN fact maps to PPL `POSITION_OPENED`.

### CLOSE fact

Required fields:

- matching `trade_id`
- exact `exit_price`
- exact `exit_fee`
- semantic timestamp
- optional explicit `decision_id`

The CLOSE fact maps to PPL `POSITION_CLOSED`.

No caller-supplied gross or realized PnL is stored in the PPL CLOSE event. PPL derives PnL through `paper_portfolio_ledger.project()`.

## 6. Observation point

The observation point is inside `MexcSimulator`, after the legacy transition has produced the complete semantic facts.

For OPEN, observation occurs only after the simulator has:

1. validated the order;
2. computed fill/slippage and exact entry fee;
3. mutated legacy capital/position state;
4. created the `MexcPosition` identity.

For CLOSE, observation occurs only after the simulator has:

1. selected the position;
2. computed exit fill and exact exit fee;
3. computed legacy PnL;
4. mutated legacy capital/closed-position state;
5. stamped the position closed.

The observer is downstream of legacy truth production and upstream of no authority path.

## 7. Failure isolation

SHADOW failures are never legacy failures.

Any exception from:

- manifest validation;
- durable-store load/append;
- event construction;
- replay/projection;
- startup reconciliation;
- identity/sequence validation;
- filesystem durability;

must transition the shadow runtime to a fail-closed degraded state for the current process.

After degradation:

- no further PPL events are appended by that shadow runtime;
- legacy PAPER continues unchanged;
- the error is observable through logs/status;
- no automatic reset/new epoch is attempted.

## 8. Explicit epoch bootstrap

SHADOW is OFF by default.

Activation requires both:

- an explicit operator-provided shadow epoch manifest;
- an explicit PPL store root.

There is no production default for either.

The manifest contains, at minimum:

- `paper_epoch_id`
- `created_at`
- `initial_virtual_capital`
- `code_sha`
- `config_snapshot_hash`
- schema version

The runtime may consume these explicit facts; it may not invent or infer them.

## 9. Clean-boundary first activation

If the configured epoch does not yet exist in the durable store, first activation is allowed only when:

- MEXC_SIM has zero open positions;
- the simulator free capital matches the manifest's explicit `initial_virtual_capital` under the frozen numeric comparison rule;
- no prior event exists for the configured `paper_epoch_id`;
- the manifest passes strict validation.

Only then may the shadow runtime append sequence 1 `EPOCH_CREATED`.

If any condition fails, SHADOW remains inactive/degraded and legacy PAPER continues.

This avoids inventing a historical PPL epoch around pre-existing open positions.

## 10. Restart contract

`RESTART != RESET`, `DEPLOY != RESET`, `PULL != RESET`.

When a configured durable epoch already exists:

1. load the exact epoch from `DurableEventStore`;
2. replay it with `project()`;
3. never append a second `EPOCH_CREATED`;
4. reconcile the PPL open-position set against MEXC_SIM restore state;
5. continue only if the certified reconciliation contract passes.

A mismatch fails SHADOW closed. It never mutates the simulator to force convergence.

## 11. Startup reconciliation

For each open PPL trade, MEXC_SIM must expose a matching restored/live position with the same:

- trade identity;
- symbol;
- side;
- principal;
- entry price;
- entry-fee evidence when required by the implemented reconciliation rule.

The exact comparison/tolerance rules are frozen by tests before runtime deployment.

Extra/missing positions on either side are a reconciliation failure, not an automatic repair request.

## 12. Event identity

Event IDs are deterministic and domain-separated.

Conceptual identity input:

```text
PPL-02D-SHADOW-V1 | paper_epoch_id | event_type | trade_id
```

The resulting event ID must not equal `trade_id`.

The same semantic OPEN or CLOSE retried after an interrupted append must resolve to the same event identity.

Before assigning a new sequence, the shadow runtime checks whether that deterministic event already exists:

- identical existing event -> idempotent success;
- same event ID with different facts -> fail closed;
- absent event -> append at the next strict sequence.

## 13. Sequence contract

Sequence is per `paper_epoch_id`, starting at 1 with `EPOCH_CREATED`.

New semantic events use the next durable sequence only after the store has been loaded/validated.

No sequence is generated from wall-clock time, process PID, cycle number, or restart count.

## 14. Decision provenance

PPL `decision_id` is optional.

An explicit DecisionPacket decision identity may be propagated when it is available and proven.

`cycle_id`, `trace_id`, process ID, or order ID must not be silently relabeled as `decision_id`.

Absent explicit decision identity remains `None`.

## 15. Numeric contract

All financial inputs must be finite.

Required positive/non-negative semantics remain those enforced by the existing PPL event/projector contracts.

No NaN/Inf, clamp, zero substitution, current-config reconstruction, or inferred fee is permitted.

The first-activation capital match uses one frozen comparison rule covered by tests; the implementation must not use an ad-hoc tolerance that varies by call site.

## 16. Projection contract

After every successful append, the shadow runtime must be able to replay the full configured epoch through:

```python
paper_trading.paper_portfolio_ledger.project(events)
```

Projection failure after an append is a SHADOW degraded condition and must be visible. It never rolls back or rewrites durable event truth.

## 17. Expected divergence

PPL-02D does not require legacy and PPL values to be equal.

Known historical accounting defects were one motivation for PPL. For example, PPL-01R/PPL-02A explicitly hardened entry-fee treatment and the PPL projector charges entry fee exactly once.

Therefore a repeatable legacy-vs-PPL delta can be scientifically correct evidence.

PPL-02D captures independent projections. WEB-02 will display and attribute the deltas.

## 18. Runtime status vocabulary

At minimum, SHADOW runtime status must distinguish:

- `OFF`
- `WAITING_CLEAN_BOUNDARY`
- `ACTIVE`
- `DEGRADED`

Status is observational only and carries no execution authority.

## 19. Required proof matrix

- D01: default configuration leaves SHADOW OFF and performs no PPL I/O;
- D02: first activation without explicit manifest/store root is impossible;
- D03: first activation with open MEXC_SIM positions does not create an epoch;
- D04: first activation with capital mismatch does not create an epoch;
- D05: clean first activation appends exactly one `EPOCH_CREATED`;
- D06: restart reuses the same epoch and never creates a second epoch;
- D07: exact OPEN semantic fact appends one deterministic `POSITION_OPENED`;
- D08: exact CLOSE semantic fact appends one deterministic `POSITION_CLOSED` with exact exit fee;
- D09: duplicate retry is idempotent;
- D10: identity collision fails closed;
- D11: sequence gap/regression/corruption fails closed;
- D12: every successful append can be replayed through `project()`;
- D13: startup open-position mismatch fails SHADOW closed without mutating legacy;
- D14: shadow store I/O failure never changes legacy order/position/capital result;
- D15: shadow projector failure never changes legacy result;
- D16: no legacy JSONL reader is used as runtime SHADOW input;
- D17: no PositionManager recorder event is silently mixed into MEXC_SIM SHADOW;
- D18: no execution/risk/strategy/sizing module imports PPL shadow as an authority;
- D19: REAL mode cannot activate PPL-02D;
- D20: known legacy/PPL accounting delta remains observable rather than auto-repaired.

## 20. Exit criteria

PPL-02D is source-certifiable when:

- all proof-matrix tests pass;
- full existing CI remains causally green or any unrelated red is proven pre-existing/non-causal;
- runtime wiring is default-OFF and MEXC_SIM-only;
- no authority boundary is crossed;
- a controlled runtime test demonstrates same semantic OPEN/CLOSE facts producing a valid durable PPL projection while legacy remains authoritative.

PPL-02D completion does **not** authorize PPL-02E.

The next planned mission remains WEB-02, which will compare the two projections and expose divergence/provenance before any PAPER authority transition.
