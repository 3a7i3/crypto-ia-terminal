from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Protocol


class DecisionState(str, Enum):
    ACTIVE = "ACTIVE"
    WAIT = "WAIT"
    BLOCKED = "BLOCKED"


class ReasonCode(str, Enum):
    NONE = "R000"
    CONFIDENCE_TOO_LOW = "R001"
    EXPOSURE_LIMIT = "R002"
    RISK_EXCEEDED = "R003"
    COOLDOWN_ACTIVE = "R004"
    DAILY_LOSS_LIMIT = "R005"
    EXCHANGE_UNAVAILABLE = "R006"


class PipelineStageStatus(str, Enum):
    OK = "OK"
    WAIT = "WAIT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    READY = "READY"


@dataclass(frozen=True)
class SnapshotMeta:
    snapshot_id: str
    timestamp_utc: str
    cycle: int
    engine_version: str


@dataclass(frozen=True)
class HealthSnapshot:
    api: bool
    database: bool
    telegram: bool
    market: bool
    strategy: bool


@dataclass(frozen=True)
class PortfolioSnapshot:
    paper_equity: float
    paper_cash: float
    free_cash: float
    portfolio_exposure_pct: float
    open_pnl_usd: float
    open_positions: int
    correlation_risk_pct: float
    # Affichage uniquement (WalletSync.session_pnl_since_restart()) — repart de
    # zéro à chaque redémarrage par construction, contrairement à paper_equity
    # (grand livre continu). Ne jamais utiliser pour le sizing/risque.
    session_pnl_usd: float = 0.0


@dataclass(frozen=True)
class AIDecisionSnapshot:
    decision_id: str
    state: DecisionState
    reason_code: ReasonCode
    reason_text: str
    blocking_module: str
    confidence_pct: int
    highest_candidate_symbol: str
    highest_candidate_score: float
    required_score: float
    next_evaluation_sec: int
    brain_score_pct: int


@dataclass(frozen=True)
class MarketSnapshot:
    regime: str
    exchange_latency_ms: float
    exchange_uptime_pct: float


@dataclass(frozen=True)
class PipelineStage:
    name: str
    status: PipelineStageStatus
    duration_ms: float
    message: str


@dataclass(frozen=True)
class APIAccountSnapshot:
    api_equity_usdt: float
    api_free_cash_usdt: float
    api_positions: int
    api_assets: tuple[tuple[str, float], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BlockStatsSnapshot:
    current_cycle: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    session: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    lifetime: tuple[tuple[str, int], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DecisionTraceNode:
    node: str
    ts_utc: str
    duration_ms: float
    decision: str
    reason_code: ReasonCode
    score: float


@dataclass(frozen=True)
class SystemSnapshot:
    meta: SnapshotMeta
    health: HealthSnapshot
    portfolio: PortfolioSnapshot
    ai_decision: AIDecisionSnapshot
    market: MarketSnapshot
    pipeline: tuple[PipelineStage, ...]
    api_account: APIAccountSnapshot
    block_stats: BlockStatsSnapshot
    decision_trace: tuple[DecisionTraceNode, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "meta": {
                "snapshot_id": self.meta.snapshot_id,
                "timestamp_utc": self.meta.timestamp_utc,
                "cycle": self.meta.cycle,
                "engine_version": self.meta.engine_version,
            },
            "health": {
                "api": self.health.api,
                "database": self.health.database,
                "telegram": self.health.telegram,
                "market": self.health.market,
                "strategy": self.health.strategy,
            },
            "portfolio": {
                "paper_equity": self.portfolio.paper_equity,
                "paper_cash": self.portfolio.paper_cash,
                "free_cash": self.portfolio.free_cash,
                "portfolio_exposure_pct": self.portfolio.portfolio_exposure_pct,
                "open_pnl_usd": self.portfolio.open_pnl_usd,
                "open_positions": self.portfolio.open_positions,
                "correlation_risk_pct": self.portfolio.correlation_risk_pct,
                "session_pnl_usd": self.portfolio.session_pnl_usd,
            },
            "ai_decision": {
                "decision_id": self.ai_decision.decision_id,
                "state": self.ai_decision.state.value,
                "reason_code": self.ai_decision.reason_code.value,
                "reason_text": self.ai_decision.reason_text,
                "blocking_module": self.ai_decision.blocking_module,
                "confidence_pct": self.ai_decision.confidence_pct,
                "highest_candidate_symbol": self.ai_decision.highest_candidate_symbol,
                "highest_candidate_score": self.ai_decision.highest_candidate_score,
                "required_score": self.ai_decision.required_score,
                "next_evaluation_sec": self.ai_decision.next_evaluation_sec,
                "brain_score_pct": self.ai_decision.brain_score_pct,
            },
            "market": {
                "regime": self.market.regime,
                "exchange_latency_ms": self.market.exchange_latency_ms,
                "exchange_uptime_pct": self.market.exchange_uptime_pct,
            },
            "pipeline": [
                {
                    "name": p.name,
                    "status": p.status.value,
                    "duration_ms": p.duration_ms,
                    "message": p.message,
                }
                for p in self.pipeline
            ],
            "api_account": {
                "api_equity_usdt": self.api_account.api_equity_usdt,
                "api_free_cash_usdt": self.api_account.api_free_cash_usdt,
                "api_positions": self.api_account.api_positions,
                "api_assets": list(self.api_account.api_assets),
            },
            "block_stats": {
                "current_cycle": list(self.block_stats.current_cycle),
                "session": list(self.block_stats.session),
                "lifetime": list(self.block_stats.lifetime),
            },
            "decision_trace": [
                {
                    "node": n.node,
                    "ts_utc": n.ts_utc,
                    "duration_ms": n.duration_ms,
                    "decision": n.decision,
                    "reason_code": n.reason_code.value,
                    "score": n.score,
                }
                for n in self.decision_trace
            ],
        }


def reason_label(code: ReasonCode) -> str:
    return {
        ReasonCode.NONE: "No blocker",
        ReasonCode.CONFIDENCE_TOO_LOW: "Confidence too low",
        ReasonCode.EXPOSURE_LIMIT: "Portfolio full / exposure limit",
        ReasonCode.RISK_EXCEEDED: "Risk exceeded",
        ReasonCode.COOLDOWN_ACTIVE: "Cooldown active",
        ReasonCode.DAILY_LOSS_LIMIT: "Daily loss limit",
        ReasonCode.EXCHANGE_UNAVAILABLE: "Exchange unavailable",
    }.get(code, "Unknown reason")


def build_system_snapshot(
    *,
    cycle: int,
    engine_version: str,
    health: HealthSnapshot,
    portfolio: PortfolioSnapshot,
    ai_decision: AIDecisionSnapshot,
    market: MarketSnapshot,
    pipeline: tuple[PipelineStage, ...],
    api_account: APIAccountSnapshot,
    block_stats: BlockStatsSnapshot,
    decision_trace: tuple[DecisionTraceNode, ...] = (),
    now_ts: Optional[float] = None,
) -> SystemSnapshot:
    ts = now_ts if now_ts is not None else time.time()
    iso = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    base = f"{cycle}:{iso}:{engine_version}:{ai_decision.decision_id}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
    meta = SnapshotMeta(
        snapshot_id=f"{cycle}-{digest}",
        timestamp_utc=iso,
        cycle=cycle,
        engine_version=engine_version,
    )
    return SystemSnapshot(
        meta=meta,
        health=health,
        portfolio=portfolio,
        ai_decision=ai_decision,
        market=market,
        pipeline=pipeline,
        api_account=api_account,
        block_stats=block_stats,
        decision_trace=decision_trace,
    )


class SnapshotProvider(Protocol):
    def get_latest(self) -> Optional[SystemSnapshot]: ...

    def set_latest(self, snapshot: SystemSnapshot) -> None: ...


class InMemorySnapshotProvider:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: Optional[SystemSnapshot] = None

    def get_latest(self) -> Optional[SystemSnapshot]:
        with self._lock:
            return self._latest

    def set_latest(self, snapshot: SystemSnapshot) -> None:
        with self._lock:
            self._latest = snapshot


class BlockStatsAccumulator:
    def __init__(
        self, lifetime_path: str = "databases/block_stats_lifetime.json"
    ) -> None:
        self._lock = threading.Lock()
        self._session: dict[str, int] = {}
        self._lifetime: dict[str, int] = {}
        self._lifetime_path = Path(lifetime_path)
        self._load_lifetime()

    def _load_lifetime(self) -> None:
        try:
            if self._lifetime_path.exists():
                self._lifetime = {
                    str(k): int(v)
                    for k, v in json.loads(
                        self._lifetime_path.read_text(encoding="utf-8")
                    ).items()
                }
        except Exception:
            self._lifetime = {}

    def _save_lifetime(self) -> None:
        try:
            self._lifetime_path.parent.mkdir(parents=True, exist_ok=True)
            self._lifetime_path.write_text(
                json.dumps(self._lifetime, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def update(self, current_cycle: dict[str, int]) -> BlockStatsSnapshot:
        with self._lock:
            for k, v in current_cycle.items():
                self._session[k] = self._session.get(k, 0) + int(v)
                self._lifetime[k] = self._lifetime.get(k, 0) + int(v)
            self._save_lifetime()
            return BlockStatsSnapshot(
                current_cycle=tuple(
                    sorted((k, int(v)) for k, v in current_cycle.items())
                ),
                session=tuple(sorted((k, int(v)) for k, v in self._session.items())),
                lifetime=tuple(sorted((k, int(v)) for k, v in self._lifetime.items())),
            )
