# Operator Visibility Matrix

Mission FAM-01. This answers "what deserves to be shown to a human, and
how urgently" — not "how should Telegram look". It classifies human value
per family/metric/data product and names candidate presentation surfaces.
It does not redesign any Telegram bot, dashboard, or narrative; changing a
presentation surface's actual layout/copy is out of scope for this
document and this mission.

Grounded in `docs/architecture/MODULE_FAMILY_REGISTRY.md`,
`docs/observability/OBSERVABILITY_MODULE_REGISTRY.md`, and
`docs/observability/OPERATOR_OBSERVABILITY_ARCHITECTURE.md`.

## Human-value vocabulary

| Value | Meaning |
|---|---|
| `MACHINE_ONLY` | Internal state consumed by code, no operator value even if surfaced. |
| `SCIENTIFIC_RESEARCH` | Valuable to a researcher validating a hypothesis, not to day-to-day operating. |
| `HUMAN_DIAGNOSTIC` | Helps a human understand *why* something happened; not urgent. |
| `HUMAN_PRIMARY` | The main thing an operator checks day to day. |
| `HUMAN_ACTION_REQUIRED` | Demands a human decision or action soon. |
| `HISTORICAL_ONLY` | Valuable for audit/history, not for present-tense operating. |
| `NOISE_DO_NOT_DISPLAY` | Known to be misleading or duplicated; must not be surfaced as-is. |

## Candidate presentation surfaces

`QUANT_OBSERVER` (`src/telegram/quant_observer/bot.py`) · `PORTFOLIO`
(portfolio-facing Telegram/dashboard surfaces) · `RADAR`
(`scripts/radar_bot.py`) · `PAPER_ARENA` (paper-arena Telegram channel) ·
`RAPPORT_AUTO` (Rapport Automatique bot) · `FUTURE_TELEMETRY_NARRATIVE`
(O-02+, not yet built) · `DASHBOARD` (`sdos_terminal/`, `visualization/api/*`).

## Matrix

| FAMILY / METRIC / DATA PRODUCT | SOURCE | HUMAN VALUE | CANDIDATE SURFACE(S) | NOTES |
|---|---|---|---|---|
| Market pulse (spot+swap tickers) | `observation/market_observer.py` | `SCIENTIFIC_RESEARCH` | `RADAR`, `DASHBOARD` | Raw pulse; a human wants the derived regime, not the ticks |
| Market regime + confidence/entropy | `market_regime_classifier.py` | `HUMAN_DIAGNOSTIC` | `QUANT_OBSERVER`, `DASHBOARD` | confidence/entropy not yet propagated to SystemSnapshot.market — a real gap, not a presentation choice |
| Legacy pipeline decision (trade_allowed/blockers) | `core/advisor_loop.py::analyze_symbol()` | `HUMAN_DIAGNOSTIC` | `QUANT_OBSERVER` | Already the real decision; showing it is diagnostic, not a duplicate authority |
| decision_packet shadow-track disagreement rate | `core/decision_packet.py` | `SCIENTIFIC_RESEARCH` | none currently | Research-only until it becomes authoritative; must not be shown as if it were the live decision |
| Global risk gate pass/fail | `risk/global_risk_gate.py` | `HUMAN_DIAGNOSTIC` | `QUANT_OBSERVER`, `RADAR` | Three parallel countings exist (RejectionStore, decision_packet.rejected_by, gate_rejections.csv) — reconcile before treating any single one as the canonical number to headline |
| RejectionStore actionable-rejection stats | `observability/rejection_store.py` | `HUMAN_DIAGNOSTIC` | `QUANT_OBSERVER` | HOLD excluded from this store — any ratio shown must state that scope explicitly |
| Circuit breaker / STOP_TRADING / RESUME_TRADING events | `auto_decision_engine.py` (system_controller_safety) | `HUMAN_ACTION_REQUIRED` | `QUANT_OBSERVER`, `RADAR` | Fully authoritative safety actions — always worth an immediate push |
| Adaptive learning RECOMMENDED actions (ADJUST_TP/SL, APPLY_META) | `auto_decision_engine.py` (system_controller_adaptive) | `HUMAN_DIAGNOSTIC` | `QUANT_OBSERVER` | Must always be labeled RECOMMENDED, never displayed as applied unless `FEATURE_ADAPTIVE_DECISION_FEEDBACK=true` |
| mistake_memory / strategy_memory / meta_learner / strategy_ranker state | adaptive_learning subsystems | `SCIENTIFIC_RESEARCH` | `QUANT_OBSERVER` (future) | Currently only readable as raw JSON/JSONL — no stats()/summary(); showing it today would require ad hoc parsing, a known debt (S02_PROVENANCE_DEBT) |
| Regret v2 evidence (HORIZON_EVIDENCE, CRI) | `tools/regret_repository.py`, `tools/cri_calculator.py` | `HUMAN_DIAGNOSTIC` (pre-gate) / `HUMAN_ACTION_REQUIRED` (once CRI≥90 and N thresholds met, per CLAUDE.md) | `QUANT_OBSERVER`, `DASHBOARD` | Not yet exposed via `visualization/api/burnin_api.py` HTTP surface — a real gap, not a presentation withholding |
| regret_engine (legacy v1) output | `quant_hedge_ai/agents/intelligence/regret_engine.py` | `HISTORICAL_ONLY` | none (explicit fallback in burnin_api.py only) | Must never be presented as current regret truth |
| Wallet / capital figure | `infra/wallet_sync.py` | `HUMAN_PRIMARY` | `PORTFOLIO`, `QUANT_OBSERVER` | Single canonical source; pinned to `WALLET_PAPER_CAPITAL` per CLAUDE.md — any equity-linked figure shown must say so |
| Paper position book (mexc_simulator) | `paper_trading/mexc_simulator.py` + `portfolio_status.py` | `HUMAN_PRIMARY` | `PORTFOLIO` | The honest, canonical portfolio view |
| portfolio_brain.portfolio_health() (pos_manager-derived) | `quant_hedge_ai/agents/risk/portfolio_brain.py` | `NOISE_DO_NOT_DISPLAY` (until reconciled) | none until fixed | Diverges from mexc_simulator (often empty); free_capital/exposure_pct potentially wrong — do not surface as a second portfolio figure |
| portfolio_api_static REST snapshot | `visualization/api/portfolio_api.py` | `NOISE_DO_NOT_DISPLAY` (until fixed) | none until fixed | 8/10 fields hardcoded 0.0; total_pnl_usd silently substitutes open PnL |
| PaperArena experiment metrics | `src/paper/paper_metrics.py`, `paper_report.py` | `SCIENTIFIC_RESEARCH` | `PAPER_ARENA` | Independent research track — must be labeled distinctly from the main portfolio in any surface that shows both |
| RunRepository/sim_runs | `src/storage/run_repository.py` | `SCIENTIFIC_RESEARCH` | `DASHBOARD` (future) | Generic simulation-run store, not PaperArena-specific |
| Order attempt journal (accepted/rejected) | `quant_hedge_ai/agents/execution/trade_logger.py` | `HUMAN_DIAGNOSTIC` | `QUANT_OBSERVER` | Unified "attempted/accepted/rejected over N cycles" view does not exist yet (FUTURE_PROVIDER per O-01 §F) |
| Latency / fill-error metrics | `quant_hedge_ai/agents/execution/latency_monitor.py`, `execution_simulator/fill_error_metric.py` | `SCIENTIFIC_RESEARCH` | `DASHBOARD` | Live call-site wiring for latency_monitor not fully confirmed — verify before headlining |
| System health score / module registry | `observability/health_score.py`, `system/module_registry.py` | `HUMAN_PRIMARY` | `QUANT_OBSERVER`, `RADAR` (WATCHDOG MOTEUR MORT alert) | BOOT vs SCIENTIFIC health distinction still implicit in calling code |
| Watchdog process-survival state | `watchdog_vps.py` | `HUMAN_ACTION_REQUIRED` | `RADAR` (kill switch, dead-engine alert) | Only the root `watchdog_vps.py` is deployed; `infra/monitoring/watchdog_vps.py` is an undeployed duplicate and must never be a data source for this |
| Disk usage / growth | `scripts/claude-disk-attribution.py`, `scripts/claude-disk-growth.py` | `HUMAN_DIAGNOSTIC` | `DASHBOARD` (future) | On-demand only today (workflow_dispatch), no continuous operator field — FUTURE_PROVIDER |
| Operator summary composite | `observability/operator/domains/operator_summary.py` | `HUMAN_PRIMARY` | `QUANT_OBSERVER`, `FUTURE_TELEMETRY_NARRATIVE` | Pure composition — every field must remain traceable to its source domain; no opaque single score |
| PMI / SDOS maturity index | `docs/blueprint_v2.md`, CLAUDE.md | `SCIENTIFIC_RESEARCH` | `DASHBOARD` (future) | Capability Score vs Evidence Score distinction must always travel together (Evidence Score = 0 today) |
| STABILIZATION_WINDOW status (`certified=false` data) | `docs/governance/STABILIZATION_WINDOW_2026-09-03_2026-09-16.md`, `experiments/EXP-001-pause-2026-09-02.yaml` | `HUMAN_ACTION_REQUIRED` | `QUANT_OBSERVER`, `RAPPORT_AUTO` | Any surface showing burn-in progress must label current-window data `certified=false` and must not let it silently feed N |

## Explicit non-goals of this document

- It does not specify Telegram message formats, dashboard layouts, or copy.
- It does not create new metrics — every row points to a metric or module
  that already exists per `MODULE_FAMILY_REGISTRY.md` or
  `OBSERVABILITY_MODULE_REGISTRY.md`.
- `NOISE_DO_NOT_DISPLAY` rows are pointers to existing, already-documented
  defects (O-01 findings); this document does not fix them.
