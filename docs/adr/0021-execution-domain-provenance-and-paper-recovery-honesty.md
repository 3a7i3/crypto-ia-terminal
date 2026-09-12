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

---

## R1.1 — MASTER correction round (2026-09-11)

**Addendum to the above, not a rewrite.** MASTER review of the R1 PR (#139,
head `027cb0c71ce291209794ba929bff729ab71876c0`) found five residual
defects in R1's own implementation of this ADR's stated intent. All five
are corrected here, on the same PR/branch, without touching R2/R3/R4 scope.

### Finding A — `exchange is not None` is not proof of REAL

R1's `PositionManager.__init__()` inferred `domain=REAL` whenever a
non-None `exchange` argument was passed and neither `domain=` nor
`paper_mode=True` was given. This is false: the real advisor construction
site (`core/advisor_loop.py`) passes
`exchange=_get_exchange_futures(exec_engine)`, and
`ExecutionEngine._init_futures_demo()` (`quant_hedge_ai/agents/execution/
execution_engine.py`) returns a non-None value ONLY for `EXCHANGE_ID=
krakenfutures`, in which case it is **the same object** as
`exec_engine._exchange` (the spot exchange) — not a distinct "futures
demo" sandbox. That object's actual domain (REAL vs TESTNET) is exactly
`exec_engine._mode` ("live"/"testnet"/"paper", set by
`infra.exchange_factory.detect_mode()` from `EXCHANGE_TESTNET`), never
something the handle's mere non-nullness proves. For every other
exchange (MEXC included), `_exchange_futures` is always `None` and that
branch is `paper_mode=True` regardless.

**Correction.** `PositionManager.__init__()` no longer infers anything
from `exchange`'s nullness: `domain=` explicit argument wins, else
`paper_mode=True` -> `PAPER`, else `UNKNOWN` (fails closed). A new
`core/advisor_loop.py::_futures_position_domain(exec_engine, paper_mode)`
resolves the proven domain from `exec_engine._mode` and is passed
explicitly as `domain=` at the one production construction site. Per the
mission's evidence: `_mode == "live"` -> `REAL`, `"testnet"` -> `TESTNET`,
anything else (including "paper" or missing) -> `UNKNOWN`. `FUTURES_DEMO`
is deliberately never produced by this call site — this codebase has no
execution path that connects to an actual sandboxed futures-demo venue
distinct from the spot exchange's own real/testnet mode; the "Futures
Demo" name in `ExecutionEngine` is a label, not a third connection this
function could honestly attest to. `FUTURES_DEMO` remains a defined
`ExecutionDomain` value for a future call site that does connect to one.

### Finding B — same domain label is not same account/exchange

R1's `PositionReconciler` verified only `pos_manager.domain ==
expected_domain`. Two independently-constructed `PositionManager`/
exchange pairs can both legitimately carry the label `REAL` while
representing different accounts or connections — a label match alone
must not authorize comparing their positions.

**Correction.** After the domain-label check passes, `reconcile()` now
additionally requires `pos_manager._exchange is <this reconciler's own
exchange_futures handle>` — object identity, the smallest proof this
architecture can make without inventing a new account-identifier concept.
`PositionManager` already stores its `exchange` argument as `self.
_exchange`; no new field was added to it. A missing `_exchange` attribute,
a different object, or `None` all fail closed identically to a domain
mismatch: `comparable=False`, empty ghost/orphan lists, an explicit
`error` naming the identity gap.

### Finding C — expired PAPER restore still faked the exit price

R1 already stopped fabricating `pnl_usd`/`pnl_pct` as `0.0` on a
downtime-window expiry, but the same code path still wrote
`exit_price=trade.entry_price` — false precision presenting "no price
movement" as if it were known.

**Correction.** `PaperTradeRecorder.record_close()`'s `exit_price`
parameter is now `Optional[float]`; `MexcSimulator._restore_positions()`'s
expiry path passes `exit_price=None`. `TradeEvent.exit_price`/
`CompleteTrade.exit_price` were already `Optional` from R1 — only the
call site's fabricated substitution needed removing.

### Finding D — unknown PnL was silently converted to LOSS

`PaperTradeRecorder.trades()` computed `is_win = (cl.pnl_usd or 0) > 0`.
For `pnl_usd=None` (genuinely unknown), Python's `or` coerces this to
`0 > 0` = `False` — UNKNOWN became LOSS, directly contradicting this
ADR's evidence-honesty rule.

**Correction.** `is_win = None if cl.pnl_usd is None else (cl.pnl_usd >
0)` in both aggregation branches (paired trades and orphaned closes). A
genuinely recorded `pnl_usd=0.0` still correctly resolves `is_win=False`
(a known non-win, distinct from an unknown outcome). Consumer inventory
(both `paper_trading.trades()`'s only two production call sites and
direct format-string readers of the newly-reachable `None`s):

- `paper_trading/status.py` (`main()`) — line rendering `wl = "WIN" if
  t.is_win else "LOSS"` would render every unknown trade as LOSS. Fixed to
  `"N/A" if t.is_win is None else ("WIN" if t.is_win else "LOSS")`. Its
  `pnl_pct`/`exit_price` formatting already guarded on `is not None`/
  truthiness before this round and needed no change.
- `paper_trading/dataset_validator.py::validate_corpus()` — already
  excludes `reason == "expired_on_restore"` from win/loss population
  stats before touching `pnl_usd` at all (unchanged, reverified by
  regression test); its `pnl = getattr(cl, "pnl_usd", 0.0) or 0.0` line is
  only reached for non-excluded (evidenced) trades, so the `or 0.0`
  coercion there is inert for genuinely-unknown records and was left
  alone rather than widened speculatively.
- No other direct production consumer of `CompleteTrade.is_win` or
  `PaperTradeRecorder.trades()` exists in this repository (grep-verified).
  This closes the finding without a broader analytics rewrite.

### Finding E — BootGate could clear trading on a non-comparable reconciliation

`system/boot_gate.py::BootGate.check()` copied `pos_report.ghost_positions`/
`orphan_positions` and computed its own `has_drift` from those (plus
order-tracker fields) — but a `comparable=False` `ReconcileReport` has
EMPTY ghost/orphan lists by design (R1's own invariant: never fabricate a
finding from an unproven comparison). `check()` never looked at
`pos_report.comparable` or `pos_report.is_clean` at all, so a reconciler
that could not prove domain/account compatibility — meaning NO comparison
happened — still let the gate clear.

**Correction.** `BootGateReport` gains `position_reconcile_comparable`
(copied from `pos_report.comparable`). `check()`'s final decision now
checks, in order: `not comparable` -> blocked (reason names the
domain/identity gap); `not position_reconcile_clean` -> blocked (reason
names the reconciler's own summary — this also closes a second,
previously-unnoticed gap where a `price_drifts`-only-dirty report,
which `is_clean` accounts for but the pre-existing local `has_drift`
variable did not, could have cleared the gate); `has_drift` -> blocked
(unchanged ghost/orphan/order-anomaly path). Only when all three pass does
the gate clear — identical outcome to before for every existing clean or
ghost/orphan-dirty scenario (regression-tested), newly fail-closed for the
non-comparable case.

### Section 6 — `ReconcileReport` must never read CLEAN for a skipped run

The rate-limited early return, `ReconcileReport(error="skipped — too
soon")`, left every other field at its default — including
`comparable=True`, `exchange_reachable=True`, empty ghost/orphan/drift
lists — so `is_clean` evaluated `True` for an operation that never ran at
all. `BootGate.check()` always calls `reconcile(force=True)` so this
specific gap does not currently reach it, but the report contract itself
was unsound, exactly as named in the mission's semantic-sweep instruction.

**Correction.** Added `ReconcileReport.performed: bool = True`; the
rate-limit skip path sets `performed=False`; `is_clean` now requires
`performed` in addition to `comparable`, `exchange_reachable`, and `not
has_drift`. No broader report-state-machine redesign — one field, one
call site, one property.

### Corrected framing (supersedes conflicting R1 wording above)

- **opaque exchange object != REAL provenance.** A non-None exchange
  handle is evidence a connection exists, never evidence of which domain
  it connects to.
- **same domain label != same account/exchange.** Two REAL-labeled
  managers can be different accounts; reconciliation requires exchange
  identity proof, not just a matching label.
- **MISSING EXIT EVIDENCE != ENTRY PRICE.** An unknown exit price is
  `None`, never the entry price presented as if nothing moved.
- **MISSING PNL != ZERO, and MISSING PNL != LOSS.** `pnl_usd=None` stays
  `None` through every layer, including the derived `is_win`, which must
  itself be `None` rather than falling back to `False`.

### Files changed (R1.1, in addition to R1's list)

- `quant_hedge_ai/agents/execution/position_manager.py` — removed the
  `exchange is not None -> REAL` inference.
- `core/advisor_loop.py` — added `_futures_position_domain()`; the
  `PositionManager` construction site now passes `domain=` explicitly.
- `system/position_reconciler.py` — exchange-identity check after the
  domain check; `ReconcileReport.performed` and the "skipped" path setting
  it `False`; `summary()`/`is_clean` updated accordingly.
- `system/boot_gate.py` — `position_reconcile_comparable`; fail-closed
  ordering in `check()`'s final decision.
- `paper_trading/recorder.py` — `record_close(exit_price: Optional[float]
  )`; `is_win` no longer coerces `None` to `False` in either aggregation
  branch.
- `paper_trading/mexc_simulator.py` — expiry path passes `exit_price=None`
  instead of `trade.entry_price`.
- `paper_trading/status.py` — `wl` rendering distinguishes `N/A` from
  `LOSS`.
- `tests/test_rem_c_r1_execution_domain.py` — 21 new tests (A1-A6, B1-B4,
  C, D1-D7, E1-E5, the `ReconcileReport.performed` regression).
- `tests/test_restart_safety.py` — `TestB2MidExecutionCrash`'s mocks now
  set `pm._exchange` to the same object passed to `PositionReconciler`
  (mechanical — these mocks exercise exactly the identity check this
  round adds).
- `.ci/ruff_baseline.json` — mechanical line-shift only (verified via
  `python scripts/ci/ruff_baseline_gate.py check`, 958/958, zero new).

No REM-C R2/R3/R4 functionality was implemented in this round either.

---

## R1.2 — MASTER correction round (2026-09-11)

**Addendum to R1/R1.1 above, not a rewrite.** MASTER review of R1.1 (head
`79cb77ebb77d202c8323509b0119cdd264f754a5`) found three residual defects
plus one evidence-audit item, all closed here on the same PR/branch.

### Finding A — UNRESOLVED != CLEAN

`ReconcileReport.unresolved_domain_positions` (added in R1) was correctly
kept out of `has_drift` — an unresolved-domain position is neither a ghost
nor an orphan claim, and fabricating either from it is exactly what R1-I4
forbids. But `is_clean` never checked `unresolved_domain_positions`
either, so `performed=True, comparable=True, exchange_reachable=True,
unresolved_domain_positions=["SOL/USDT"], ghost=[], orphan=[]` read as
`is_clean=True` — an unaccounted-for position certified the system clean.

**Correction.** `is_clean` now additionally requires
`not self.unresolved_domain_positions`, checked directly rather than
folded into `has_drift` — this keeps `has_drift`'s existing meaning (and
every caller reading it, e.g. `core/advisor_loop.py`'s ghost/orphan
Telegram alert) unchanged. `summary()` already never returned `"CLEAN"`
while `unresolved_domain_positions` was non-empty (it appends
`UNRESOLVED_DOMAIN=...` to the joined parts), so no change was needed
there.

### Finding B — INTERNAL READ FAILURE != EMPTY INTERNAL STATE

Two related fail-open gaps in `PositionReconciler.reconcile()`'s internal-
position read:

1. `self._pm.get_open() if hasattr(self._pm, "get_open") else []` treated
   "the canonical API doesn't exist" identically to "it returned zero
   positions".
2. `except Exception: report.error = ...` then **continued** with
   `internal_pos = {}` — a raised exception from `get_open()` was treated
   the same as a successful empty read. With an empty exchange this could
   certify CLEAN despite the internal state never being read; with a
   non-empty exchange it would fabricate an ORPHAN finding for every real
   exchange position, purely because the internal side failed to load.

**Correction.** New `ReconcileReport.internal_state_readable: bool =
True` field, distinct from `exchange_reachable` (which only describes the
exchange side) and from `comparable` (domain/account proof, a different
axis). `reconcile()` now returns immediately — before any ghost/orphan/
price-drift computation — when `get_open` is missing or raises,
setting `internal_state_readable=False` and an explicit `error`.
`is_clean` requires it; `summary()` reports
`INTERNAL_STATE_UNREADABLE (...)` in that state, following the same
early-return pattern as `NOT_PERFORMED`/`NON_COMPARABLE`. A genuinely
empty `get_open() -> []` (no exception, API present) is unaffected and
remains distinguishable — it still reaches CLEAN when the exchange is
also genuinely empty.

### Finding C — MISSING RAW EVENT PRICE != ZERO

R1.1 correctly made the *derived* `exit_price`/`pnl_usd`/`pnl_pct`/
`is_win` all `None` for an `expired_on_restore` close, but the *raw*
`PaperTradeRecorder.record_close()` still wrote `TradeEvent.price = 0.0`
for that same event — R1.1's own comment called this an "unread legacy
placeholder", which is not sufficient for a durable scientific ledger:
`MISSING EVIDENCE != ZERO` must apply to the raw event, not only to
fields derived from it later.

**Correction, after consumer audit.** Grepped every reader of
`TradeEvent.price`/`evt.price`/`op.price`/`cl.price` in this repository:
the only production reader is `paper_trading/recorder.py`'s own
`trades()`, and only for OPEN events (`entry_price=op.price` — OPEN
always carries a real evidenced price, unaffected). No reader anywhere
requires a CLOSE event's `price` to be a non-null float.
`paper_trading/dataset_validator.py::_check_core_fields()` already guards
`val is not None` before its NaN check, so it already tolerates `None`
without modification. Given zero broad-impact consumers, `TradeEvent.price`
is now `Optional[float]` (schema-compatible — no field reordering, no
default added) and `record_close()` passes `exit_price` straight through
instead of substituting `0.0`. No
`REM_C_R1_2_TRADEEVENT_PRICE_NULLABILITY_SCOPE_EXPANSION_REQUIRES_MASTER_DECISION`
was needed — the audit found the change genuinely narrow.

### Finding 4 — fee-entry evidence audit (defect found, smallest fix applied)

Traced `MexcPosition.fee_entry_usd` → `_close_position()`'s
`pnl_usd = pos.qty_usd * gross_pct - fee - pos.fee_entry_usd` →
`PaperTradeRecorder.record_close()` → `trades()`/`status.py` display.
Answer to the mission's question ("can an old restored position whose
entry fee is UNKNOWN later close and produce a normal-looking
authoritative PnL that assumes entry fee = 0?"): **YES** — confirmed by
direct trace, not assumption. A pre-schema-v4-restored position's
`fee_entry_usd=0.0` (the documented fallback, flagged only in the
in-memory `MexcPosition.restored_evidence_gaps`, R1.1) flowed unflagged
into `pnl_usd`, and `record_close()` recorded that PnL as ordinary,
fully-evidenced data — indistinguishable from a trade whose fee was
genuinely known to be zero.

**Smallest fix applied** (no `MexcPosition`/PnL-architecture redesign):
schema v5 adds one CLOSE-only field,
`pnl_fee_evidence_incomplete: bool = False`, to `TradeEvent` and
`CompleteTrade`. `record_close()` gained a matching parameter;
`MexcSimulator._close_position()` sets it to
`"fee_entry_unknown" in pos.restored_evidence_gaps` when calling
`record_close()`. The PnL number itself is unchanged — it is real
arithmetic against the best available (assumed) fee, not fabricated —
but it can no longer be silently read as fully evidenced.
`paper_trading/status.py`'s W/L column appends `*` when the flag is set
(smallest possible display change; no population-statistics exclusion
was added — that would have been a broader, unrequested behavior change
to `dataset_validator.py`'s win/loss counting, not the narrow boundary
this finding asked for).

### Finding 5 — TESTNET reconciliation status (documented, not implemented)

`core/advisor_loop.py`'s `PositionReconciler(...)` construction still
passes no explicit `expected_domain`, so it defaults to `REAL` (per R1.1).
A krakenfutures `PositionManager` correctly labeled `TESTNET` (via
R1.1's `_futures_position_domain()`) will therefore fail closed as
`NON_COMPARABLE` against that REAL-expecting reconciler today. **This is
intentional and safe for the current PAPER-only T-1 scope**: no code
change was made. TESTNET reconciliation is explicitly **not certified**
and remains fail-closed until a future REM-C round adds a genuine
TESTNET-capability certification path — this round makes no claim that
TESTNET reconciliation works, only that it correctly refuses to run.

### Files changed (R1.2, in addition to R1/R1.1's lists)

- `system/position_reconciler.py` — `is_clean` requires
  `not unresolved_domain_positions`; new `internal_state_readable` field
  and fail-closed early return in `reconcile()`'s internal-read step;
  `summary()`'s `INTERNAL_STATE_UNREADABLE` branch.
- `paper_trading/recorder.py` — `TradeEvent.price: Optional[float]`;
  `record_close()` passes `exit_price` through directly; schema v5
  (`pnl_fee_evidence_incomplete`) on `TradeEvent`/`CompleteTrade`,
  propagated in `trades()`.
- `paper_trading/mexc_simulator.py` — `_close_position()` computes and
  passes `pnl_fee_evidence_incomplete`.
- `paper_trading/status.py` — `*` suffix on the W/L column when
  `pnl_fee_evidence_incomplete`.
- `paper_trading/dataset_validator.py` — `_VALID_SCHEMA_VERSIONS`
  extended to include `5` (mechanical).
- `tests/test_rem_c_r1_execution_domain.py` — 14 new tests (A1-A3, B1-B5,
  C1-C4, the two fee-evidence tests).
- `.ci/ruff_baseline.json` — mechanical line-shift only.

No REM-C R2/R3/R4 functionality was implemented in this round either.

---

## R1.3 — MASTER final evidence-semantics round (2026-09-12)

**Addendum to R1/R1.1/R1.2 above, not a rewrite.** MASTER review of R1.2
(head `50fd9631a303efe1c431a379292ba2897d879bd2`) found that R1.1's own
`personality` distinction had drifted out of sync with a downstream
provenance-visible consumer, and that two aggregate-statistics surfaces
still let unevidenced/unknown outcomes contaminate certified metrics.

### Finding A — RESTORED != EVIDENCE_COMPLETE

R1.1 set `MexcPosition.personality = "restored_evidence_incomplete"` for
a restored position with any evidence gap, `"restored"` otherwise. But
`observability/operator_snapshot_builder.py`'s
`is_restored = personality == "restored"` — a provenance-visible
structure consumed by the frontend (`frontend/src/types.ts`'s
`OpenPosition.restored`/`tp_sl_source`) — predates that distinction and
was never updated to match it. Two failure directions resulted:

1. An evidence-incomplete restored position read `restored=False` —
   silently misrepresented as a normally-opened position.
2. A **fully-evidenced** restored position (durable TP/SL recovered via
   schema v4) kept `personality="restored"` and so was labeled
   `tp_sl_source="restored_default"` — falsely claiming a 4%/2%
   reconstruction that never happened.

**Correction.** `personality` now stays `"restored"` for every
ledger-restored position regardless of evidence completeness — "was this
position restored from the ledger" (A) and "is its evidence complete" (D)
are different facts, and only `restored_evidence_gaps` (unchanged, R1)
carries the second one; `personality` is not overloaded to carry both.
`operator_snapshot_builder.py`'s `tp_sl_source` now derives from
`restored_evidence_gaps` directly: `"original"` (never restored,
unchanged), `"restored_default"` (restored AND
`"tp_sl_reconstructed_default"` present — genuinely reconstructed),
`"restored_original"` (new — restored AND that gap absent: durably
recovered TP/SL, evidence-tier B in the mission's A/B/C/D framing, never
conflated with either "original" or "restored_default"). The materialized
position dict also now exposes `restored_evidence_gaps` directly (a
transparent passthrough — no new state, no redesign). Checked against
`frontend/src/lib/snapshotValidation.ts` and `frontend/src/types.ts`
before changing: `tp_sl_source`'s type was already `"original" |
"restored_default" | string` (the `| string` fallback already tolerated
new values) and validation only checks it is a non-blank string, so
adding `"restored_original"` and an optional `restored_evidence_gaps?`
field required no Web contract redesign — both were extended additively.
`docs/contracts/O-02W-B_CANONICAL_OPERATOR_API_CONTRACT.md`'s `tp_price`/
`sl_price` row (which previously documented only the binary
`"original"`/`"restored_default"` split) is corrected to describe all
three tiers.

### Finding B — HISTORICAL RECORD != CERTIFIED PERFORMANCE SAMPLE

`PaperTradeRecorder.summary()` computed `win_rate = len(wins) /
len(closed)`, `target_30_trades`, and `go_live_ready` over ALL closed
trades — including `is_win is None` (unknown outcome, e.g.
`expired_on_restore`) ones. An unknown outcome was never counted as a WIN
(correct, R1.1) but still inflated the denominator (diluting win_rate),
still advanced the 30-trade target, and could still flip
`go_live_ready=True` on 30 genuinely unknown closes. Production consumer
audit: the only reader of `PaperTradeRecorder.summary()` in this
repository is `paper_trading/status.py` (CLI display) — no other
production code depends on its keys.

**Correction.** `summary()` now computes a `certified` subset of `closed`
— trades with `is_win is not None` AND
`not pnl_fee_evidence_incomplete` (R1.2) — and derives `win_rate`, every
PnL aggregate, `target_30_trades`, and `go_live_ready` from `certified`
only. `total_closed` (existing key, unchanged meaning: raw historical
count) is preserved for backward compatibility — nothing is deleted from
the historical record. Two new keys, `certified_closed` and
`excluded_unevidenced_count`, make the exclusion explicit rather than
silent. `paper_trading/status.py` updated to print the excluded count
when non-zero and to compute its "EN COURS (x/30)" progress line from
`certified_closed`, not the raw count.

### Finding C — INCOMPLETE FEE EVIDENCE != FULLY-EVIDENCED PNL (dataset corpus)

`paper_trading/dataset_validator.py::validate_corpus()`'s population loop
already excluded `expired_on_restore` from WIN/LOSS/TP/SL/duration
statistics, but a `pnl_fee_evidence_incomplete=True` close (R1.2) — a
real, chronologically valid, paired trade whose realized PnL assumed an
unevidenced entry fee — was still counted as an ordinary certified
observation.

**Correction.** A new `CorpusReport.fee_evidence_incomplete` counter and
a `continue` in the population loop (mirroring the existing
`expired_on_restore` pattern exactly) exclude such closes from
`win_count`/`loss_count`/`tp_count`/`sl_count`/`win_rate`/`tp_rate`/
`mean_duration_s`. Paired-trade/integrity accounting is unaffected — the
exclusion happens only inside the population-statistics loop, after
`paired_trades`/`integrity_pct` are already computed from the full paired
set. Not treated as corrupted data (no `violations` entry): an explicit
`warnings` entry names the count and rate, matching the existing
`expired_on_restore` warning's style. `report()` and `to_metadata()`
surface the new counter.

### Files changed (R1.3)

- `paper_trading/mexc_simulator.py` — `personality` no longer varies by
  evidence completeness.
- `observability/operator_snapshot_builder.py` — `tp_sl_source` derives
  from `restored_evidence_gaps`; `restored_evidence_gaps` passthrough
  added to the materialized position dict.
- `frontend/src/types.ts` — `tp_sl_source` union extended with
  `"restored_original"`; optional `restored_evidence_gaps?: string[]`
  added to `OpenPosition`.
- `docs/contracts/O-02W-B_CANONICAL_OPERATOR_API_CONTRACT.md` — `tp_price`/
  `sl_price` row corrected to the three-tier model.
- `paper_trading/recorder.py` — `summary()` computes a certified subset;
  `certified_closed`/`excluded_unevidenced_count` keys added.
- `paper_trading/status.py` — displays the excluded count;
  GO/LIVE progress uses `certified_closed`.
- `paper_trading/dataset_validator.py` — `fee_evidence_incomplete`
  counter, population-loop exclusion, warning, `report()`/`to_metadata()`
  surfacing.
- `tests/test_operator_snapshot_builder.py` — `_FakePosition` gains
  `restored_evidence_gaps`; existing restored-position test updated to
  set it explicitly; two new tests (A2/A3-shaped).
- `tests/test_rem_c_r1_execution_domain.py` — one existing R1.1 test
  updated (`personality` assertion), 15 new tests (B1-B5, C1-C6, plus the
  b/c fee-evidence coverage).
- `.ci/ruff_baseline.json` — mechanical line-shift, plus one incidental
  fix (`f"0 / 30"` → `"0 / 30"`, a stray f-string-without-placeholders
  removed during the `summary()` rewrite — count dropped 958→957).

No REM-C R2/R3/R4 functionality was implemented in this round either.
