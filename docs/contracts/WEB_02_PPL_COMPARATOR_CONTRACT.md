# WEB-02 — PPL Comparator Contract

Issue: #175
Parent governance: #148
Baseline: `main@cdedbf41fb1579feedac355cd8d1b2d0ff94ffa2`

## 1. Purpose

WEB-02 exposes a read-only comparison between authoritative legacy PAPER
(`MexcSimulator`) and non-authoritative PPL SHADOW
(`PPLShadowRuntime.projection`).

The comparator observes divergence. It never repairs either side and never
changes trading authority.

## 2. Authority

- Legacy PAPER: `PAPER_AUTHORITY`
- PPL: `NONE`
- Comparator/API/frontend: `OBSERVATIONAL_TELEMETRY`
- No BUY/SELL/close/restart/risk/sizing/strategy authority is introduced.
- PPL-02E is not authorized by WEB-02.

## 3. Process boundary

```text
existing MexcSimulator + existing PPLShadowRuntime
                  |
                  v
observability.ppl_comparison
                  |
                  v
atomic databases/ppl_comparison_snapshot.json
                  |
                  v
GET /api/operator/v1/ppl-comparison
                  |
                  v
PPL Compare React view
```

The Operator API never instantiates the simulator/PPL runtime and never reads
`paper_trades.jsonl` or the PPL durable store. It validates and transports the
atomic artifact only.

The frontend never recomputes accounting, PnL, fees, or deltas.

The producer applies two independent, bounded coherent-capture guards before
publication. Because MEXC_SIM commits the authoritative legacy mutation before
the downstream passive PPL observer call, a naive single read can land inside
that short hand-off window:

1. **Byte-semantic stability.** Two consecutive identical legacy+PPL
   source-pair captures are required. A continuously moving pair is withheld
   fail-passively.
2. **Causal coherence (generation).** Byte stability alone is insufficient: a
   PPL that permanently lags one mutation behind Legacy is byte-stable across
   any number of reads yet never describes the same instant as Legacy.
   `MexcSimulator` maintains a monotonic `legacy_generation` counter,
   advanced only after a complete OPEN (capital + position + order) or CLOSE
   (position removal + capital/`_closed`) mutation, read under
   `MexcSimulator._lock`. Each `ShadowOpenFact`/`ShadowCloseFact` carries the
   generation it was produced at; `PPLShadowRuntime` acknowledges a
   generation only once its durable append and projection succeed, and only
   along a contiguous prefix (generation 2 observed before generation 1 is
   parked until 1 also lands — 2 is never announced as fully acknowledged in
   the meantime). WEB-02 withholds the artifact fail-passively whenever:
   - a CLOSE mutation is mid-transition (the position has left
     `_positions` but capital/`_closed` are not yet credited — tracked by an
     in-flight counter read under the same lock), or
   - PPL is ACTIVE and its acknowledged generation does not equal the
     generation Legacy was captured at.

Either guard failing withholds the artifact fail-passively and the previous
atomic artifact remains untouched. A persistent, causally-coherent divergence
is still published exactly as observed. This generation/transition state is
runtime/memory only: it is never written into a durable PPL event and never
enters any financial computation.

## 4. Comparison vocabulary

### Classification

- `COMPARABLE`: both source facts have compatible semantics.
- `PARTIAL`: both raw facts may be useful, but scope/provenance differs.
- `UNRESOLVED`: a scientifically required source fact is absent or its
  provenance is insufficient.

### Relation

- `EQUAL`
- `DIFFERENT`
- `LEGACY_ONLY`
- `PPL_ONLY`
- `NOT_COMPARABLE`

A numeric `delta_ppl_minus_legacy` is emitted only when:
1. classification is `COMPARABLE`;
2. both raw values are finite numeric facts.

All other rows carry `delta_ppl_minus_legacy = null`.

## 5. Numeric rule

Comparable numeric values use:

```
rel_tol = 0
abs_tol = 1e-9
delta = ppl_value - legacy_value
```

No presentation rounding changes the raw producer value.

Side comparison uses canonical semantic equivalence only:

- `BUY == LONG`
- `SELL == SHORT`

Both raw side strings remain present in the record.

## 6. V1 comparison matrix

| Fact | V1 classification |
|---|---|
| free cash | COMPARABLE |
| open-position count | COMPARABLE |
| open trade identity | COMPARABLE |
| symbol / side / principal / entry price | COMPARABLE |
| entry fee | COMPARABLE only when legacy fee evidence is complete |
| restored unknown entry fee | UNRESOLVED |
| reserved principal | PARTIAL (legacy is explicit derivation from live positions) |
| epoch realized PnL vs legacy session realized PnL | PARTIAL |
| cumulative fees | UNRESOLVED |
| closed count epoch vs current session | PARTIAL |
| exit price | COMPARABLE when the same close exists in both live evidence sets |
| exit fee | UNRESOLVED on legacy side |
| per-trade realized PnL | PARTIAL; PPL has no per-trade realized map in V1 |
| unrealized PnL with open positions | UNRESOLVED in V1 |
| unrealized PnL with zero open positions | COMPARABLE zero |

`UNKNOWN != ZERO` applies throughout.

## 7. Known accounting divergence

Legacy MEXC_SIM debits `principal + entry_fee` on OPEN and later credits
`principal + pnl_usd`, while legacy `pnl_usd` already includes the entry
fee. PPL debits the entry fee once from cash and includes it in realized-PnL
reporting without re-debiting cash on CLOSE.

Therefore free-cash divergence after closes is expected scientific evidence.
WEB-02 must display it and must not normalize it away.

## 8. PPL lifecycle states

### ACTIVE

Comparison rows may be emitted from the current PPL projection.

### OFF

`comparison_available=false`. No convergence is inferred.

### WAITING_CLEAN_BOUNDARY / DEGRADED

`comparison_available=false`. Existing PPL raw event provenance may be shown,
but comparator rows are withheld rather than presenting a stale/degraded
projection as converged.

## 9. Artifact contract

Product: `PPLComparator`
Domain: `ppl_comparison`
Mode: `SHADOW_COMPARISON`
Authority: `OBSERVATIONAL_TELEMETRY`
Schema: `1.0.0`

The artifact carries:
- generated timestamp;
- process/cycle/source SHA;
- SHADOW status and epoch;
- explicit comparison availability;
- source authority/provenance;
- summary counts;
- comparison records;
- open/closed trade identity groupings;
- durable PPL event provenance.

The reader uses a closed-schema admission gate. Unknown top-level or comparison
fields are rejected.

## 10. Failure isolation

The comparison sidecar is invoked from the already-certified passive
`OperatorSnapshotWriter` boundary.

Its failure:
- is caught independently;
- increments a dedicated comparison write-error counter;
- never invalidates an already-written canonical operator snapshot;
- never propagates into the advisor loop;
- never changes PAPER/PPL state.

## 11. UI contract

The `PPL Compare` tab is independent from the canonical snapshot, analogous
to MARKET.

The UI:
- shows raw Legacy and PPL values side-by-side;
- shows producer-authored relation/classification/delta;
- exposes provenance;
- presents PARTIAL/UNRESOLVED explicitly;
- does not label equality as “good” or divergence as “bad”;
- does not recompute accounting;
- remains responsive on desktop/tablet/phone.

## 12. Exit boundary

WEB-02 certification permits observation only.

It does **not**:
- promote PPL to PAPER authority;
- authorize PPL-02E;
- start F-00;
- authorize burn-in;
- authorize live trading.
