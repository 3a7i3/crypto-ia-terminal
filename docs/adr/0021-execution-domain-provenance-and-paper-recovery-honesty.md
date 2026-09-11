# ADR-0021 — Execution-domain provenance and PAPER recovery honesty (O-02W-PRE-T1-E REM-C R1)

Status: Accepted (implementation scope, not runtime certification)
Date: 2026-09-11
Supersedes: none. Extends ADR-0019 (REM-A), ADR-0020 (REM-B).

## Context

REM-C R0/R0.1 established that the repository mixes or incompletely
distinguishes REAL, PAPER, SHADOW, BURN-IN and OBSERVATION execution
state, and that the reconciliation/recovery logic has source-proven
honesty defects:

1. `system/position_reconciler.py`'s `PositionReconciler.reconcile()`
   calls `pos_manager.get_open_positions()`, a method that never existed
   on the canonical `PositionManager`
   (`quant_hedge_ai/agents/execution/position_manager.py`, which only
   exposes `get_open()`). A `hasattr()` guard made this silently return an
   empty internal-position set in production for the life of the code — a
   second, identical instance of the same defect existed in
   `core/advisor_loop.py`'s boot-time heartbeat amorçage.
2. Nothing in the `Position`/`PositionManager` model records which
   execution domain a position belongs to. Simply renaming
   `get_open_positions()` to `get_open()` without first closing this gap
   would let a PAPER-mode `PositionManager`'s internal state be compared,
   by symbol string alone, against a REAL exchange's `fetch_positions()`
   result.
3. `MexcSimulator._restore_positions()`
   (`paper_trading/mexc_simulator.py`) — the production PAPER restart
   path — fabricates certainty where none exists: `pnl_usd=0.0`/
   `pnl_pct=0.0` for positions expired during a downtime window (as if
   nothing happened while the process was down), a hardcoded 4%/2%
   TP/SL recompute presented indistinguishably from the position's actual
   original TP/SL, and `fee_entry_usd=0.0` because the ledger never
   captured it.

This mission (REM-C R1) is deliberately narrow: it is not the fill-engine
implementation (`ExecutionEvidence`/`FillRecord`, partial-fill ingestion,
`fetch_order()`/`fetch_my_trades()` production integration — REM-C
R2/R3/R4), not exchange reconciliation certification, and not
testnet/live enablement.

## Decision

### 1. `ExecutionDomain` — minimal provenance enum

```python
class ExecutionDomain(str, Enum):
    REAL = "real"
    TESTNET = "testnet"
    FUTURES_DEMO = "futures_demo"
    PAPER = "paper"
    SHADOW = "shadow"
    UNKNOWN = "unknown"
```

Added directly to `position_manager.py` alongside the existing
`PositionSide`/`CloseReason` enums (no new module — this repository
already keeps execution-state enums colocated with `Position`). Only
domains reachable from actual construction call sites are included; no
domain is added speculatively.

`Position.domain: ExecutionDomain = ExecutionDomain.UNKNOWN` — `UNKNOWN`
is the safe default. It is never silently upgraded to `REAL` (the
majority of historical positions were not created with a domain in mind)
nor to `PAPER` (T-1 being paper-only is not proof an individual position
is), per the mission's explicit instruction.

`PositionManager.__init__(..., domain: Optional[ExecutionDomain] = None)`
resolves its own `.domain`:

- explicit `domain=` argument always wins;
- else `paper_mode=True` -> `PAPER` (the caller's own explicit intent);
- else `exchange is not None` -> `REAL` (a live exchange handle was
  actually passed — this is the shape `core/advisor_loop.py:4122` uses
  for its real-futures construction path);
- else `UNKNOWN` (ambiguous construction context — fails closed).

`add_position()` stamps `self.domain` onto any position that still
carries the `UNKNOWN` default; a position explicitly constructed with a
different, non-`UNKNOWN` domain is never overwritten (this is what lets a
test — or a future caller with better information — assert a domain the
manager itself cannot infer).

This is the smallest representation that satisfies all of R1-I1 through
R1-I4 without introducing domains no reachable code needs (no
per-exchange-account or per-subaccount granularity was added — nothing in
the current call graph distinguishes those).

### 2. Reconciliation same-domain invariant

`PositionReconciler.__init__(..., expected_domain: ExecutionDomain =
ExecutionDomain.REAL)` — `REAL` by construction default, since
`exchange_futures.fetch_positions()` is definitionally a real/testnet
account call; nothing about `PositionReconciler` changes this.

`reconcile()` now checks `pos_manager.domain == expected_domain` *before*
calling `fetch_positions()` at all. On mismatch (including `UNKNOWN`):
returns immediately with `comparable=False`, `pm_domain`,
`expected_domain` populated, and empty `ghost_positions`/
`orphan_positions` — never a fabricated finding from an incompatible or
unproven comparison.

Only once domain-compatible does the corrected internal-position read run
— `pos_manager.get_open()`, replacing `get_open_positions()`. Individual
positions read back that still carry a non-matching or `UNKNOWN` domain
(e.g. a legacy position loaded outside the normal construction path) are
excluded from ghost/orphan comparison and reported separately via
`unresolved_domain_positions`, never folded into a ghost/orphan claim
(R1-I4).

`core/advisor_loop.py`'s structurally identical `get_open_positions()`
guard (boot-time heartbeat amorçage) is fixed to `get_open()` alongside
this — same root defect, same fix, no new domain logic needed there since
it only counts positions, it does not compare them against an exchange.

Reconciliation was already read-only (`fetch_positions()` plus a pure
comparison, no order/position mutation anywhere in the file); this
mission adds no mutation path (R1-I6).

### 3. PAPER restart evidence-honesty rule

`PaperTradeRecorder`'s `TradeEvent`/`CompleteTrade` (`paper_trading/
recorder.py`) gain schema v4: three new OPEN-only fields, `tp_price`,
`sl_price`, `fee_entry_usd`, all `Optional[float] = None`. `None` means
"not recorded" and must never be read as zero or as a default original
value by any consumer. `record_open()` accepts and persists them when the
caller has them; the live-order-fill call site
(`paper_trading/mexc_simulator.py`'s `_execute_market_order`-equivalent)
now passes the position's actual `tp_price`/`sl_price`/`fee_entry_usd`
through. `record_close()`'s `pnl_usd`/`pnl_pct` parameters become
`Optional[float]` so a caller can durably record "unknown", not merely
"zero".

`MexcSimulator._restore_positions()`:

- **Expired-during-downtime positions** are now closed with
  `pnl_usd=None`/`pnl_pct=None` (previously `0.0`/`0.0`). What happened to
  price/PnL during a downtime window is genuinely unknown; it stays
  unknown. The `reason="expired_on_restore"` string is preserved exactly
  (unchanged) because `paper_trading/dataset_validator.py` classifies on
  that literal.
- **TP/SL/fee reconstruction**: when a schema-v4 record's `tp_price`/
  `sl_price` are present, they are used verbatim — this is the actual
  original evidence, not a recompute. Only when genuinely absent (older
  records, or any future gap) does restoration fall back to the same
  4%/2% recompute as before — but now the position's new
  `restored_evidence_gaps: list[str]` field records exactly which values
  were reconstructed (`"tp_sl_reconstructed_default"`,
  `"fee_entry_unknown"`), and `personality` is set to
  `"restored_evidence_incomplete"` instead of the previously
  undifferentiated `"restored"`. A reconstructed value can no longer be
  mistaken for original evidence by any downstream reader (R1-I8), while
  genuinely-evidenced restorations remain fully functional and
  unflagged (R1-I9).

No nullable rewrite of `MexcPosition.tp_price`/`sl_price` (which would
ripple through every `hits_tp()`/`hits_sl()` comparison and the live
watch loop) was introduced — per the mission's explicit
smallest-alternative instruction, the honesty signal is carried
separately (`restored_evidence_gaps`) rather than by making the running
fields themselves optional.

`paper_trading/dataset_validator.py`'s `_VALID_SCHEMA_VERSIONS` is
extended `{1,2,3} -> {1,2,3,4}` — mechanical, matches the new
`SCHEMA_VERSION`.

## Consequences

- A PAPER position can never again be silently compared against a REAL
  account, and an unproven domain fails closed rather than defaulting to
  either REAL or PAPER.
- Reconciliation reads the canonical `PositionManager` API correctly once
  domain-compatibility is proven; a domain-incompatible or unproven
  pos_manager makes reconciliation report itself non-comparable rather
  than fabricate ghost/orphan findings.
- PAPER restart never again converts missing PnL evidence into a known
  zero, and never again claims an original TP/SL/fee value that was not
  durably recorded — a reconstructed value is now always distinguishable
  from a genuinely evidenced one.
- Scientific capital, sizing, signals, strategies, regimes, risk
  thresholds, Telegram, the frontend, and the Web API are all untouched.
  `PAPER_TRADING_ENABLED=true`/`LIVE_TRADING_CONFIRMED=false` are
  unchanged.

## Explicitly deferred (REM-C R2/R3/R4)

Canonical `ExecutionEvidence`/`FillRecord`; cumulative exchange fill
journal; partial-fill ingestion/deduplication; exchange fill polling
(`fetch_order()`/`fetch_my_trades()` production integration);
real-exchange fee accounting/VWAP reconstruction; exchange adapter
certification; resubmission policy; real position reconstruction from
exchange fills; full crash-window/partial-fill recovery (B8 remains only
restart-idempotent, per REM-B).
