# Machine Family Architecture

Mission FAM-01, building on Mission G/G-R/G-R2/G-R3
(`G_MACHINE_CARTOGRAPHY_CERTIFIED`) and on the O-01/O-01R observability
census (`docs/observability/OBSERVABILITY_MODULE_REGISTRY.md`). This
document is the durable, docs-only contract for which family a module
belongs to. It does not change any scientific behavior; it records what
Mission G already found so future agents stop re-discovering it.

Companion documents: `MODULE_FAMILY_REGISTRY.md` (per-module table),
`../observability/OPERATOR_VISIBILITY_MATRIX.md` (what deserves to reach a
human), `ENVIRONMENT_CONFIGURATION_CONSTITUTION.md` +
`ENVIRONMENT_VARIABLE_REGISTRY.md` (config/secret separation), and
`../operations/PRE_RESTART_RUNTIME_CONTRACT.md` (T-1 checklist).

## Configuration layers (read top to bottom)

```
SOURCE ARCHITECTURE (this document + MODULE_FAMILY_REGISTRY.md)
        │  "what family does this code belong to, statically"
        ▼
CANONICAL SCIENTIFIC OBSERVABILITY (O-01 domains, regret_repository, CRI)
        │  "what is the certified truth about the system's own behavior"
        ▼
OPERATOR VISIBILITY MATRIX (../observability/OPERATOR_VISIBILITY_MATRIX.md)
        │  "of that truth, what deserves to reach a human, and how urgently"
        ▼
PRESENTATION CONFIGURATION (a handful of OPERATOR_*_ENABLED flags)
        │  "is this family's presentation surface turned on right now"
        ▼
TELEGRAM / DASHBOARD / NARRATIVE (Radar bot, Quant Observer, Paper Arena,
Rapport Automatique, future dashboard/telemetry-narrative surfaces)
```

Presentation principle (see `ENVIRONMENT_CONFIGURATION_CONSTITUTION.md` for
the full statement): family membership is static architecture, decided in
this document and in `MODULE_FAMILY_REGISTRY.md` — it is never re-decided
by an environment variable. What a small number of family-level switches
(`OPERATOR_QUANT_ENABLED`, `OPERATOR_PORTFOLIO_ENABLED`,
`OPERATOR_MACHINE_HEALTH_ENABLED`, …) may do is turn a presentation surface
on or off. **PROPOSED / FUTURE PRESENTATION CONFIG**: none of these three
names exist today in source (verified — no `os.getenv`/`os.environ` call
site references them anywhere in the repository); they are a proposed
future switch family for O-02, not currently-live environment variables.
They must never redefine which family owns a metric, its
scientific meaning, which source is canonical, or who holds decision/risk
authority.

## The certified top-level tree

```
CRYPTO AI TERMINAL
├── INFRASTRUCTURE / GOVERNANCE
│   ├── core/authority.py                       (GovernanceKernel — single point of entry to trading authority)
│   ├── quant_hedge_ai/runtime/runtime_state_machine.py  (RuntimeStateMachine / SystemState)
│   ├── core/initialization_contract.py         (boot-order contract: forbids load_dotenv/makedirs at import time)
│   ├── core/lifecycle.py, core/warm_boot.py    (boot sequencing)
│   ├── governance/                             (decision_trace, ADR machinery)
│   ├── config/feature_flags.py                 (FEATURE_* master switches — protected file)
│   └── scripts/deploy_vps.sh, scripts/systemd/* (deliberate-deploy gesture, unit files)
│
├── MAIN SCIENTIFIC SYSTEM
│   ├── MARKET / DATA
│   │   ├── observation/market_observer.py       (spot+swap ticker pulse — CANONICAL_EXISTING, ADR-0016 isolated)
│   │   ├── observation/market_radar.py          (radar scan, feeds crypto-market-radar.timer)
│   │   ├── observation/horizon_evaluator.py     (horizon evaluation cadence)
│   │   ├── market_data/                         (OHLCV storage/backfill)
│   │   └── supervision/exchange_monitor.py      (connectivity/latency, shared with system health)
│   │
│   ├── QUANTITATIVE RESEARCH
│   │   ├── quant_hedge_ai/agents/intelligence/market_regime_classifier.py (regime detection)
│   │   ├── quant_hedge_ai/strategy_factory/, quant_hedge_ai/strategy_lab/  (strategy research)
│   │   ├── quant_hedge_ai/ai_evolution/strategy_ranker.py, strategy_memory.py (PARTIAL, gated by
│   │   │   FEATURE_ADAPTIVE_DECISION_FEEDBACK per S-02B.1 — protected files, read-only here)
│   │   └── walk_forward/, backtest_real.py       (offline research, not decision-active)
│   │
│   ├── DECISION
│   │   ├── core/advisor_loop.py::analyze_symbol() (CANONICAL_EXISTING legacy dict pipeline —
│   │   │   the real execution pilot per O-01 §C)
│   │   ├── core/decision_packet.py               (PARTIAL — sealed hash-chain state machine,
│   │   │   shadow/candidate track, not yet the execution pilot)
│   │   └── quant_hedge_ai/agents/intelligence/no_trade_layer.py (no-trade filtering layer)
│   │
│   ├── RISK / SAFETY
│   │   ├── quant_hedge_ai/agents/risk/global_risk_gate.py (CANONICAL_SOURCE_PATH —
│   │   │   verified wired into the current SOURCE decision path:
│   │   │   `core/advisor_runtime_adapters.py` imports `GlobalRiskGate` from
│   │   │   this module, and `core/advisor_loop.py` invokes it via
│   │   │   `runtime.GlobalRiskGate(...)`. SOURCE PROOF != RUNTIME PROOF —
│   │   │   actual VPS runtime use of this path remains RUNTIME_PROOF_REQUIRED)
│   │   ├── risk/global_risk_gate.py (LEGACY — an older, incompatible `asyncio`-
│   │   │   based implementation whose own docstring targets the retired
│   │   │   `main_v91.py` loop; not imported by `core/advisor_runtime_adapters.py`
│   │   │   or any current SOURCE pipeline entrypoint — superseded, not
│   │   │   co-authoritative with the quant_hedge_ai gate above)
│   │   ├── risk/circuit_breaker.py, risk/risk_limits.py
│   │   ├── portfolio_brain.py
│   │   └── system/burn_in.py, tracker_system/autonomous/auto_decision_engine.py
│   │       (system_controller_safety = fully authoritative regardless of
│   │       FEATURE_ADAPTIVE_DECISION_FEEDBACK; system_controller_adaptive =
│   │       gated — see O-01 §I, ADR-0007)
│   │
│   ├── PORTFOLIO / EXECUTION
│   │   ├── infra/wallet_sync.py                  (CANONICAL_EXISTING — single capital/equity source)
│   │   ├── paper_trading/mexc_simulator.py       (CANONICAL_EXISTING real book of paper positions)
│   │   ├── paper_trading/portfolio_status.py     (CANONICAL_EXISTING honest portfolio view)
│   │   ├── quant_hedge_ai/agents/execution/execution_engine.py (CANONICAL_EXISTING order gate)
│   │   ├── quant_hedge_ai/agents/execution/trade_logger.py     (SQLite order-attempt journal)
│   │   └── quant_hedge_ai/agents/execution/paper_trading_engine.py (DUPLICATED — different
│   │       entrypoint, main_system.py/main_v91.py — not the current SOURCE-wired
│   │       path; actual deployed-engine status remains RUNTIME_PROOF_REQUIRED)
│   │
│   ├── LEARNING / INTELLIGENCE
│   │   ├── quant_hedge_ai/agents/intelligence/mistake_memory.py
│   │   ├── tracker_system/meta_learner.py, tracker_system/meta_memory.py
│   │   └── quant_hedge_ai/ai_evolution/strategy_memory.py, strategy_ranker.py
│   │       (RECOMMENDED != APPLIED per ADR-0007 / S-02B.1: observation always
│   │       on, application gated by FEATURE_ADAPTIVE_DECISION_FEEDBACK)
│   │
│   └── REGRET
│       ├── tools/regret_repository.py            (CANONICAL_EXISTING — Regret v2 read layer,
│       │   ADR-0018/MC-001, feeds tools/cri_calculator.py)
│       ├── observability/regret_scheduler.py      (HORIZON_EVIDENCE producer)
│       └── quant_hedge_ai/agents/intelligence/regret_engine.py (LEGACY — pre-v2, decertified
│           2026-07-10 per ADR-0018; kept for historical audit only, never canonical)
│
├── RESEARCH EXPERIMENTS
│   └── PAPER ARENA
│       ├── src/paper/paper_runner.py, paper_gate.py, paper_metrics.py,
│       │   paper_position_manager.py, paper_report.py
│       └── scripts/systemd/paper-arena.service
│       NOTE (certified distinction): PaperArena is an independent experiment
│       track. It is NOT the main paper dataset (paper_trading/mexc_simulator.py
│       + databases/paper_trades.jsonl remain the main-system paper book), and
│       it is NOT src/storage/run_repository.py (RunRepository/sim_runs is a
│       separate legacy-simulation store, consumed only by
│       `src/telegram/sim_bot.py` — see RESEARCH EXPERIMENTS / STORAGE below).
│       Verified by source: `PaperArena` (`src/paper/*.py`) has **no**
│       `run_repository`/`RunRepository` import anywhere — it does NOT use
│       RunRepository. Conflating the two is the single most common
│       architectural mistake found by prior missions.
│       │
│       └── src/storage/run_repository.py (RunRepository/sim_runs — CMVK
│           simulator persistence layer, default store
│           `databases/sim_runs.sqlite`; sole consumer is
│           `src/telegram/sim_bot.py`'s `SimBot`. NOT O-01 canonical
│           observability, NOT PaperArena persistence, NOT main paper-trading
│           persistence — reclassified here from a prior mistaken
│           ACTIVE_CANONICAL/O-01 placement. No systemd unit or
│           `.env.example` entry was found for the bot that consumes it
│           (RUNTIME_PROOF_REQUIRED), so its status is
│           SOURCE_DEFINED_RUNTIME_UNVERIFIED, not ACTIVE_CANONICAL. See
│           `MODULE_FAMILY_REGISTRY.md` for the full row.)
│
├── CANONICAL SCIENTIFIC OBSERVABILITY
│   └── O-01
│       ├── observability/operator/domains/*.py  (11 domains, DEFAULT_MODULE_REGISTRY)
│       └── observability/operator/domains/operator_summary.py (pure composition, no
│           independent recomputation — CANONICAL_NEW)
│
├── OPERATOR EXPERIENCE
│   ├── src/telegram/quant_observer/bot.py         (Quant Observer)
│   │   CURRENT (verified by source): a presentation client of the main
│   │   SystemSnapshot/live_snapshot architecture, NOT of O-01. Its actual
│   │   chain is `src/telegram/quant_observer/bot.py` →
│   │   `visualization/api/quant_live_api.py::load_quant_live_snapshot()` →
│   │   `visualization/api/system_snapshot_source.py` →
│   │   `databases/live_snapshot.json`. None of these three modules import
│   │   anything under `observability/operator/domains/`.
│   │   TARGET-O-02 (not yet implemented): Quant Observer should converge on
│   │   the canonical O-01 operator-observability contracts
│   │   (`system_health`, `market_state`, `decision_pipeline`, `attrition`,
│   │   `data_freshness`, `operator_summary`) instead of the SystemSnapshot
│   │   projection it reads today. This is a target, not a current fact.
│   │   Either way: Telegram != scientific source of truth — it renders
│   │   what a producer already computed, it never computes its own number.
│   ├── scripts/radar_bot.py                       (interactive radar bot — Telegram engine channel)
│   ├── scripts/quant_observer_pin_bootstrap.py
│   ├── visualization/api/*.py, sdos_terminal/, dashboard/ (REST/dashboard presentation)
│   NOTE: Telegram is never the source of scientific truth. It renders what the
│   canonical observability layer already certified; it must never compute its
│   own numbers (see `system_health.system_snapshot_bus_dead`-style findings for
│   what happens when a presentation surface silently substitutes computation).
│
└── STORAGE / RETENTION
    ├── databases/ (paper_trades.jsonl, regret/*.jsonl, ai_evolution/*.json, gate_rejections.csv, …)
    ├── src/storage/run_repository.py (sim_runs — see above)
    ├── observability/rejection_store.py (append-only actionable-rejection journal)
    └── logs/, cache/ (excluded from `scripts/deploy_vps.sh` transfer filter — VPS runtime state)
```

## Distinctions this document exists to preserve

| Pair | Relationship |
|---|---|
| PaperArena vs main paper dataset | Independent research track vs `paper_trading/mexc_simulator.py` + `databases/paper_trades.jsonl`. Never the same N. |
| Quant Observer vs PaperArena | Quant Observer (`src/telegram/quant_observer/bot.py`) is a **presentation client** — CURRENTLY of the main SystemSnapshot/live_snapshot architecture (`visualization/api/quant_live_api.py` → `system_snapshot_source.py` → `databases/live_snapshot.json`), TARGET-O-02 of canonical O-01 observability (not yet implemented). Either way it is not a data source and not PaperArena. |
| Regret v2 vs legacy ShadowTracker | `tools/regret_repository.py` (ADR-0018, MC-001) is canonical since 2026-07-10. `quant_hedge_ai/agents/intelligence/regret_engine.py` is the pre-v2 engine — LEGACY, historical-audit only. |
| RunRepository/sim_runs vs PaperArena | `src/storage/run_repository.py` (CMVK/sim_bot persistence) and PaperArena (`src/paper/*.py`) are separate simulation programs. Verified by source: PaperArena has **no** `run_repository`/`RunRepository` import anywhere — it does NOT use RunRepository. They are not aliases of each other. |
| Telegram vs source of scientific truth | Telegram surfaces (Radar bot, Quant Observer, Rapport Automatique, Paper Arena channel) render certified data; they never compute an independent number that becomes the record. |
| Learning vs Authority | `adaptive_learning.*` subsystems (mistake_memory, strategy_memory, meta_learner, strategy_ranker, system_controller_adaptive) may only ever be RECOMMENDED, gated by `FEATURE_ADAPTIVE_DECISION_FEEDBACK`. Only `core/authority.py` (GovernanceKernel) and the safety branch of `auto_decision_engine.py` (`system_controller_safety`) hold real decision authority — ADR-0007. |
| Recommended vs Applied | A subsystem "computing" or "learning" something is never evidence it is influencing a live decision — see the RECOMMENDED/APPLIED matrix in `docs/observability/OBSERVABILITY_MODULE_REGISTRY.md` §I. |

## Provenance

Family boundaries above are drawn from actually-existing source paths found
during this mission's exploration (directory listing, `grep` over
`os.getenv`/`load_dotenv`, `docs/observability/OBSERVABILITY_MODULE_REGISTRY.md`,
and `scripts/systemd/*.service`). No module name in this document is
invented; see `MODULE_FAMILY_REGISTRY.md` for the flat table with paths and
statuses.
