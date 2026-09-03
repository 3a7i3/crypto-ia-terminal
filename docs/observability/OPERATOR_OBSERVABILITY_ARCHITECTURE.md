# Operator Observability Architecture

Mission O-01 · Base SHA `c560efc51a5180d5bd7e9ec179c2a8b6d1ea8fc4` · 2026-09-03

## 1. Purpose

Crypto AI Terminal already produces a large amount of observability data —
`SystemSnapshot`, `DecisionObservation`, `RejectionStore`, Regret v2,
portfolio/execution state, DA-01 disk audits, Telegram renderers. The
problem this mission addresses is not a lack of data; it is fragmentation:
different components expose different metrics, some Telegram code
calculates presentation-specific values instead of reading a canonical
source, and metric meanings are not always explicit for the operator.

O-01 establishes a canonical **Operator Observability Architecture**: eleven
observation domains, a shared snapshot contract, and a metric dictionary,
so that Telegram, dashboards, APIs and future scientific reports can all
consume the same definitions instead of recomputing them independently.

## 2. Scientific principles

1. **Source of truth != presentation layer.** Telegram — and any future
   dashboard/API — is a *consumer*, never the place a metric is computed.
2. **Passivity (ADR-0007).** Nothing in this architecture feeds a trading
   decision. Every contract in `observability/operator/` is read-only,
   deterministic, and side-effect-free at import time.
3. **No invented metrics (mission §7, §18).** A metric that does not exist
   in the codebase today is marked `NOT_CURRENTLY_AVAILABLE` or
   `FUTURE_PROVIDER` — never approximated.
4. **Explicit null/unknown semantics (mission §27).** `0`, `false`, `empty`,
   `unknown`, `unavailable`, `stale`, and `not_applicable` are distinct,
   testable states (`observability/operator/contracts.py::NullSemantics`),
   not conventions someone has to remember.
5. **Domain-specific freshness (mission §28).** There is no single global
   "snapshot age." Each dataset registers its own freshness clock and
   threshold, because they are frequently and meaningfully different
   (e.g. Regret's canonical-evaluated-horizon clock vs. market-pulse
   tick age).
6. **Reuse before creation (mission §26).** Every canonical module
   documented here wraps an *existing* producer. Nothing recomputes a
   metric that already has an owner; see
   [`OBSERVABILITY_MODULE_REGISTRY.md`](./OBSERVABILITY_MODULE_REGISTRY.md)
   for the reuse decision behind each entry.

## 3. Source-of-truth vs. presentation separation

```
MACHINE / SCIENTIFIC DATA
  (system/module_registry, observability/*, RejectionStore,
   tools/regret_repository, infra/wallet_sync, DA-01 packs, ...)
        |
        v
CANONICAL OBSERVABILITY MODULES  (existing, wrapped, not duplicated)
        |
        v
CANONICAL SNAPSHOT / METRIC CONTRACT   <-- observability/operator/
        |
        v
PRESENTATION ADAPTERS  (none exist yet inside this package — O-01 ships
  contracts only; O-02 builds the adapters)
        +-- Telegram   (src/telegram/quant_observer/, future O-02 target)
        +-- dashboards (visualization/api/*)
        +-- API
        +-- scientific reports
```

O-01 stops at the canonical contract layer. It does not implement, wire,
or activate a presentation adapter — see §9 (Non-goals) and
[`OPERATOR_DISPLAY_CONTRACT.md`](./OPERATOR_DISPLAY_CONTRACT.md) for the
rules the *future* adapters must follow.

## 4. Domain model

Eleven domains, each with a documented purpose and responsibility
boundary (mission §5-§16). No "everything snapshot" — domains compose,
they do not merge.

| # | Domain | Question it answers | Module |
|---|---|---|---|
| A | SYSTEM HEALTH | Is the machine alive *and* scientifically healthy? | `domains/system_health.py` |
| B | MARKET STATE | Is market data fresh and is the exchange reachable? | `domains/market_state.py` |
| C | DECISION PIPELINE | Is the decision pipeline progressing, and where? | `domains/decision_pipeline.py` |
| D | ATTRITION / REJECTIONS | Where are candidates disappearing? | `domains/attrition.py` |
| E | PORTFOLIO STATE | What does the operator actually hold — paper vs. real? | `domains/portfolio_state.py` |
| F | EXECUTION STATE | Is order execution healthy? | `domains/execution_state.py` |
| G | DATA FRESHNESS | Is each critical dataset fresh, by its own clock? | `domains/data_freshness.py` |
| H | REGRET STATE | Is the certified S-01/v2 Regret pipeline scientifically fresh? | `domains/regret_state.py` |
| I | ADAPTIVE LEARNING STATE | Is adaptive learning passive or already decision-active? | `domains/adaptive_learning.py` |
| J | DISK / I-O | Is storage healthy, per the DA-01 reference architecture? | `domains/disk_io.py` |
| K | OPERATOR SUMMARY | Composition-only synthesis of the above 10 | `domains/operator_summary.py` |

Each domain module exports:

- a frozen `*Snapshot` dataclass extending `DomainSnapshot`
  (`contracts.py`) — `schema_version`, `domain`, `observed_at_utc`,
  `source`, `source_version`, `freshness`, `status`, `evidence`;
- a pure `compose_*_snapshot()` function that accepts already-computed,
  primitive/`ObservedValue`-typed inputs — it never imports a producer
  module itself, so the package has zero import-time coupling to the
  engine;
- `METRICS`: the `MetricDefinition`s it contributes to
  `canonical_registry.DEFAULT_METRIC_REGISTRY`;
- `MODULES`: the `ModuleDescriptor`s recording the forensic inventory
  (which existing code is canonical/duplicated/legacy/unused for this
  domain).

## 5. Data flow

A future integration layer (out of O-01's scope — see §9) will:

1. read already-existing in-memory objects (a `SystemSnapshot`, a
   `RejectionStore` query result, `WalletSync.get_balance()`, a DA-01
   JSON pack, ...);
2. wrap each value in an `ObservedValue` with explicit `NullSemantics`;
3. call the relevant `compose_*_snapshot()` to build a domain snapshot;
4. optionally call `compose_operator_summary()` to fold several domain
   snapshots into one composition-only synthesis;
5. hand the resulting snapshot(s) to a presentation adapter, which
   formats but never reinterprets (§`OPERATOR_DISPLAY_CONTRACT.md`).

O-01 ships steps 2-4 as tested, passive code. Step 1 (wiring real
producers in) and step 5 (adapters) are explicitly out of scope — see §9.

## 6. Provenance model

Every `DomainSnapshot` carries `source` (the producing module),
`source_version` (when meaningful — e.g. `regret-v2`), `observed_at_utc`,
and an `evidence` mapping for domain-appropriate extra provenance.
Per mission §29, provenance is domain-appropriate: a `packet_id` is not
forced onto a system-health metric that has none.

## 7. Freshness model

`observability/operator/contracts.py::FreshnessStatus` defines
`FRESH | DEGRADED | STALE | UNKNOWN | NOT_APPLICABLE`. This is the first
general-purpose formalization of this vocabulary in the codebase — the
forensic pass found no prior unified freshness enum, only narrow,
domain-scoped precedents (`IncidentType.DATA_STALE`,
`AdmissionBlocker.REJECTED_STALE`, the Regret pipeline's
canonical-horizon concept). `freshness.py::classify_freshness()` never
invents a threshold: without an evidence-backed `fresh_threshold_s`/
`stale_threshold_s` pair it returns `UNKNOWN`, not a guess.

Freshness stays domain-specific per source (mission §28) — Regret's
`last_canonical_evaluated_utc` (evaluated-on-canonical-horizon clock) is
never conflated with Regret's `last_event_utc` (mere producer liveness),
let alone with market-pulse tick age or DA-01 snapshot age.

## 8. OperatorSummary composition

`domains/operator_summary.py::compose_operator_summary()` takes the ten
other domain snapshots (any subset — missing ones are marked
`UNAVAILABLE`, never invented as healthy) and produces a list of
`ComponentStatus` entries, each copying its source snapshot's own
`status`/`freshness` verbatim — it never recomputes a scientific truth.
There is no opaque global score: `OperatorSummary.status` is
`"OK"`/`"ATTENTION_REQUIRED"`, and `attention_items` names each
struggling domain explicitly (`"regret_state: DEGRADED (fraîcheur=STALE)"`),
never a bare number. Tests (`tests/observability/operator_o01/
test_operator_summary.py`) assert it does not mutate its inputs and does
not invent data for absent domains.

## 9. Telegram / dashboard / API adapter philosophy

O-01 documents the target philosophy; O-02 implements it.

- A presentation adapter reads a canonical snapshot and *formats* it —
  translates enum values to French labels via the metric dictionary,
  chooses emoji/color from the metric's documented severity semantics,
  and renders timestamps/freshness explicitly.
- It never recalculates a percentage, never infers a status from
  vibes, and never mixes fields from two domains into one number
  without both being explicitly labeled (paper vs. real capital is the
  sharpest example — see `portfolio_state.py`).
- The already-approved O-02 requirement for `@QuantCrpto_bot` (single
  continuously-edited LIVE message, no pin, no deletion of history,
  French labels, metric-dictionary-backed) is documented here as a
  downstream consumer contract, **not implemented** by O-01 — see
  [`OPERATOR_DISPLAY_CONTRACT.md`](./OPERATOR_DISPLAY_CONTRACT.md) §"Quant
  Observer O-02 migration contract" and
  [`TELEGRAM_BOT_REGISTRY.md`](./TELEGRAM_BOT_REGISTRY.md).

## 10. Known gaps (forensic findings, not fixed by O-01)

- **Dual decision pipeline.** `DecisionPacket`/`DecisionObservation`
  (canonical, ADR-0007) runs in parallel with the legacy dict pipeline
  that still actually drives execution
  (`core/advisor_loop.py:1488` comment); a measured disagreement rate
  exists (`core/advisor_loop.py:6274-6295`) but is unresolved.
  See `decision_pipeline.py::MODULES`.
- **Two divergent position stores.** `MexcSimulator` (real prices,
  populated) vs. `pos_manager` feeding `PortfolioBrain.portfolio_health()`
  (frequently empty) — exposure/free-capital figures inherit this
  divergence. See `portfolio_state.py::MODULES`.
- **Adaptive learning is decision-active today, not passive.**
  `MistakeMemory.check_before_trade()` and `MetaLearner.find_best()`/
  `learn()` gate/shape live trades without any `FEATURE_*` governance
  flag; `RECOMMENDED != APPLIED` is not distinguished for them (the
  recommendation *is* the applied value, same code path). ADR-0007's
  `FEATURE_AUTO_CALIBRATION`/`FEATURE_REGRET_DECISION_FEEDBACK` scope
  covers only the Regret-threshold auto-calibration path. See
  `adaptive_learning.py::MODULES`.
- **Regret freshness not surfaced over HTTP.** `tools/regret_repository.
  freshness()` exists and is correct, but `BurnInSnapshot`
  (`visualization/api/burnin_api.py`) omits it — only the CLI
  (`tools/cri_calculator.py`) sees it today. See `regret_state.py::MODULES`.
- **Disk/IO is on-demand only.** DA-01 and the disk_growth pack are
  `workflow_dispatch`-triggered forensic audits, never continuous; no
  operator-facing snapshot (`SystemSnapshot`, `MetricsSnapshot`) carries
  a disk field today. See `disk_io.py::MODULES`.
- **Regime confidence/entropy computed but not exposed.** `RegimePacket`
  fields exist and are logged but never reach `SystemSnapshot.market`.
  See `market_state.py::MODULES`.
- **`portfolio_api.py` is defective, not just incomplete.** 8 of 10
  fields are hardcoded to `0.0`, and `total_pnl_usd` silently substitutes
  *open* PnL for *total* PnL. Flagged `PRESENTATION_ONLY` in the module
  registry — do not treat as canonical until fixed.
- **`/kpis` on `@mon_portfolio_bot` mixes paper-derived metrics with a
  real-capital base with no "paper" label** — see
  [`TELEGRAM_BOT_REGISTRY.md`](./TELEGRAM_BOT_REGISTRY.md) for the full
  finding. Not fixed by O-01 (Telegram runtime is out of scope); flagged
  as a priority for O-02.

## 11. Migration plan O-01 -> O-02

1. O-01 ships contracts, registries, domain adapters and docs (this PR).
   No runtime wiring.
2. A future integration mission wires real producers (SystemSnapshot,
   RejectionStore, WalletSync, tools/regret_repository, DA-01 packs,
   etc.) into the `compose_*_snapshot()` functions — read-only, still no
   Telegram/dashboard changes.
3. O-02 builds presentation adapters, starting with `@QuantCrpto_bot`'s
   single-message LIVE panel (French labels, canonical metric IDs, no
   duplicated computation, no pin, no deletion of history — see
   `OPERATOR_DISPLAY_CONTRACT.md`).
4. Remaining bots (`@mon_portfolio_bot`, `@PaperArena_bot`,
   `@Telemetrie_IA_bot`, `@RadarCrypto1_bot`) migrate per the priority
   order in `TELEGRAM_BOT_REGISTRY.md`.

## 12. Explicit non-goals (O-01)

O-01 does not: implement background services, polling loops, Telegram
send/edit code, exchange calls, new database writers, new retention
policies, new trading/strategy/risk logic, new systemd services, or any
wiring into `core/advisor_loop.py`. It does not modify
`src/telegram/quant_observer/` or any other Telegram bot code. It does
not redesign Regret or DA-01 — it consumes their existing semantics. It
does not touch the S-02B.1-protected files
(`config/feature_flags.py`, `core/advisor_loop.py`,
`quant_hedge_ai/agents/intelligence/mistake_memory.py`,
`quant_hedge_ai/ai_evolution/strategy_memory.py`,
`tracker_system/meta_learner.py`, `tracker_system/meta_memory.py`,
their passivity test files, `.ci/ruff_baseline.json`) — confirmed by
`git diff origin/main...HEAD` (see PR description).
