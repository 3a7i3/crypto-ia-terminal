"""Scientific object models — typed outputs of the SDOS Data API.

Each dataclass is the canonical Python representation of one SDOS concept.
The VES maps these types to their SVL canonical renderers.
No client module instantiates these directly — use the loader functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class HealthSnapshot:
    """Aggregated system health — canonical input for RadarChart renderer."""

    ts: datetime

    # Six SVL radar axes (0-100 float)
    observer_pct: float  # Heartbeat recency + exchange sync
    dataset_pct: float  # Universe coverage + data freshness
    knowledge_pct: float  # Burn-in progress toward N=50 milestone
    evidence_pct: float  # Cumulative evidence quality (N / 100)
    capital_pct: float  # Current capital / initial capital
    drift_pct: float  # Scientific drift score (lower = better)

    # Raw values for V1/V2 display
    system_state: str  # "NORMAL" | "HALTED" | "DEGRADED"
    trading_enabled: bool
    capital_usd: float
    n_trades: int
    win_rate_pct: float
    profit_factor: float
    last_heartbeat_at: Optional[datetime]
    heartbeat_age_seconds: Optional[float]
    top_root_cause: Optional[str]
    top_root_cause_pct: Optional[float]


@dataclass
class PipelineSnapshot:
    """Decision pipeline state — canonical input for HorizontalPipeline renderer."""

    ts: datetime
    n_signals: int
    n_traded: int
    n_refused: int
    refusal_breakdown: dict[str, int]  # layer_name → count
    regime_distribution: dict[str, int]  # regime_name → count
    capital_usd: float
    cycle: int

    @property
    def pass_rate_pct(self) -> float:
        if self.n_signals == 0:
            return 0.0
        return round(self.n_traded / self.n_signals * 100, 1)

    @property
    def top_layer(self) -> Optional[str]:
        if not self.refusal_breakdown:
            return None
        return max(self.refusal_breakdown, key=self.refusal_breakdown.get)


@dataclass
class QuantLiveSnapshot:
    """READ-ONLY SDOS projection for the @QuantCrypto_bot LIVE panel (Q1).

    Answers only the Quant Observer question: *what does the engine currently
    see, what decision does it produce, where does attrition occur, and is the
    decision chain healthy?* — nothing else.

    Deliberately excluded, because they are semantically wrong or out of domain
    for this bot:
      * portfolio / capital / PnL / win-rate / N-trades  → Portfolio Bot domain
      * observer/dataset/knowledge/evidence/drift %       → misleading proxies
        (they measured health booleans, brain score, block counters and
        exchange uptime under names that did not match their computation)
      * host metrics (RAM/CPU/PID)                        → not SDOS signal
      * health.telegram / main_channel                    → generic historical
        channel, not this bot's delivery health

    Pure projection of ``system_snapshot`` (databases/live_snapshot.json via the
    canonical source adapter). ADR-0007 passivity: observes, never decides.
    """

    ts: datetime
    cycle: int
    engine_version: str
    snapshot_age_s: Optional[float]

    # DATA — raw observed health booleans (never an aggregate %)
    health_market: bool
    health_api: bool
    health_database: bool

    # MARKET — what the engine currently sees
    regime: str
    exchange_latency_ms: float
    exchange_uptime_pct: float

    # DECISION — what the engine currently produces
    state: str
    top_candidate_symbol: str
    top_candidate_score: float
    required_score: float
    confidence_pct: int
    reason_text: str
    gate_reason: str
    next_evaluation_sec: int

    # ATTRITION — current cycle only (block_stats.current_cycle): layer → count
    refusal_breakdown: dict[str, int] = field(default_factory=dict)

    # PIPELINE — real per-stage status ({name, status, message})
    pipeline_stages: list[dict] = field(default_factory=list)

    # DECISION TRACE — real nodes ({node, decision, score, reason_code})
    decision_trace: list[dict] = field(default_factory=list)

    @property
    def total_refusals(self) -> int:
        return sum(self.refusal_breakdown.values())

    @property
    def dominant_filter(self) -> Optional[str]:
        if not self.refusal_breakdown:
            return None
        return max(self.refusal_breakdown, key=self.refusal_breakdown.get)

    @property
    def dominant_filter_pct(self) -> float:
        total = self.total_refusals
        dominant = self.dominant_filter
        if total == 0 or dominant is None:
            return 0.0
        return round(self.refusal_breakdown[dominant] / total * 100, 1)


@dataclass
class PortfolioSnapshot:
    """Trade performance metrics — canonical input for EquityCurve renderer."""

    ts: datetime
    n_trades: int
    n_wins: int
    n_losses: int
    win_rate_pct: float
    profit_factor: float
    expectancy_pct: float
    max_drawdown_pct: float
    sharpe: float
    total_pnl_usd: float
    avg_pnl_usd: float
    avg_duration_h: float
    capital_usd: float
    trade_history: list[dict] = field(default_factory=list)


@dataclass
class RegimeSnapshot:
    """Market regime distribution — canonical input for ColoredTimeline renderer."""

    ts: datetime
    distribution: dict[str, int]  # regime_name → count
    dominant: str
    dominant_pct: float
    total_signals: int


@dataclass
class ScientificSnapshot:
    """Scientific state — observer certification + DIP knowledge layer."""

    ts: datetime
    certification_level: int
    certification_name: str
    iii: float  # Instrumentation Index (0-100)
    ocs: float  # Observer Certification Score (0-100)
    n_decisions_production: int  # Decisions indexed in DIP
    n_knowledge_entries: int  # Entries in dip_knowledge
    n_alerts_active: int  # Active (unacknowledged) DIP alerts
    n_counterfactuals: int  # Counterfactuals computed
    last_cert_at: Optional[datetime]
    cert_decision: str  # Human-readable gate decision
    checks: list[dict]  # IV-LIVE check results


@dataclass
class TimelineEvent:
    """One entry in the decision event stream."""

    packet_id: str
    ts: datetime
    symbol: str
    event_category: str  # "TRADE" | "SYSTEM" | etc.
    lifecycle_state: str  # "REJECTED" | "EXECUTED" | etc.
    regime: str
    conviction: str
    reason: str  # Primary reasoning message


@dataclass
class TimelineSnapshot:
    """Recent decision packet stream — canonical input for TimelinePage."""

    ts: datetime
    events: list[TimelineEvent]
    total_packets: int
    n_trade: int
    n_system: int
    n_rejected: int
    n_executed: int


@dataclass
class DatasetCertification:
    """One observer certification record."""

    certification_id: str
    generated_at: datetime
    level: int
    level_name: str
    iii: float
    ocs: float
    n_live_passed: int
    n_live_failed: int
    n_decisions_production: int
    decision: str
    checks: list[dict]


@dataclass
class DatasetsSnapshot:
    """All dataset certifications — canonical input for DatasetsPage."""

    ts: datetime
    certifications: list[DatasetCertification]
    latest_level: int
    latest_iii: float
    latest_ocs: float


@dataclass
class BurnInSnapshot:
    """Burn-in progress vs the statistician thresholds (CLAUDE.md — Règle du
    statisticien). CRI is intentionally left unset: tools/cri_calculator.py
    does not exist yet (docs/blueprint_v2.md gate S3, not reached)."""

    ts: datetime
    generated_at: Optional[datetime]

    trades_count: int
    trades_min: int
    wins: int
    wins_min: int
    losses: int
    losses_min: int
    missed_win_count: int
    missed_win_min: int
    good_refusal_count: int
    good_refusal_min: int
    per_regime_min: int
    per_layer_min: int

    win_rate_pct: float
    profit_factor: float
    expectancy_pct: float
    coverage_pct: float

    cri: Optional[float]
    cri_min: int
    calibration_locked: bool

    go_no_go: str
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class RegretInvestigationSnapshot:
    """Read-only breakdown of RegretEngine records for one regret_type —
    answers *why* a regret category dominates, not whether to recalibrate.
    Pure aggregation over databases/regret_analysis.jsonl (ADR-0007)."""

    ts: datetime
    regret_type: str
    n_total: int
    by_layer: dict[str, int]  # bloqueur (refused_by) → count
    by_regime: dict[str, int]  # régime marché → count
    by_score_bin: dict[str, int]  # bin de score → count
    by_week: dict[str, int]  # semaine ISO (YYYY-Www) → count
    first_evaluated_at: Optional[datetime]
    last_evaluated_at: Optional[datetime]
