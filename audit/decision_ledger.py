"""
Decision Ledger — immutable append-only log of every trading decision.

Every signal that enters decision_router produces a DecisionRecord,
whether approved or rejected. Records are persisted to JSONL and
queryable in-memory.

Answers the question: "Why was this trade taken (or rejected)?"

DecisionRecord contains:
    trace_id, timestamp, strategy, confidence, market_state,
    signal_source, risk_score, violations, pipeline_steps,
    execution_result, outcome_label

Usage:
    from audit.decision_ledger import decision_ledger

    # Append (called automatically by decision_router integration)
    decision_ledger.append(record)

    # Query
    decision_ledger.recent(n=20)
    decision_ledger.by_symbol("BTCUSDT", limit=50)
    decision_ledger.by_trace("abc123...")
    decision_ledger.summary()
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional

from observability.json_logger import get_logger

log = get_logger("decision_ledger", category="audits")

LEDGER_PATH = Path(__file__).resolve().parent.parent / "logs" / "decisions"
LEDGER_PATH.mkdir(parents=True, exist_ok=True)


class DecisionOutcome(Enum):
    """Post-hoc label (filled after trade closes or signal expires)."""

    PENDING = auto()  # not yet evaluated
    VALIDATED = auto()  # good signal, good result
    UNLUCKY = auto()  # good signal, bad market outcome
    LUCKY = auto()  # poor signal, good market outcome
    MISTAKE = auto()  # bad signal, bad result — AI should learn from this
    REJECTED = auto()  # signal was blocked by pipeline


@dataclass
class PipelineStep:
    stage: str
    passed: bool
    detail: str
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "passed": self.passed,
            "detail": self.detail,
            "duration_ms": self.duration_ms,
        }


@dataclass
class DecisionRecord:
    trace_id: str
    timestamp: float = field(default_factory=time.time)

    # Signal metadata
    source: str = ""
    strategy: str = ""
    symbol: str = ""
    side: str = ""
    size_usd: float = 0.0
    confidence: float = 0.0
    market_regime: str = ""

    # Risk snapshot at decision time
    current_drawdown: float = 0.0
    daily_pnl: float = 0.0
    portfolio_exposure_pct: float = 0.0
    risk_score: float = 0.0

    # Pipeline audit trail
    pipeline_steps: List[PipelineStep] = field(default_factory=list)
    approved: bool = False
    rejection_reason: str = ""
    violations: List[str] = field(default_factory=list)

    # Execution result (filled after execution)
    order_id: Optional[str] = None
    fill_price: Optional[float] = None
    slippage_bps: Optional[float] = None
    execution_ms: Optional[float] = None

    # Post-trade outcome (filled when position closes)
    outcome: DecisionOutcome = DecisionOutcome.PENDING
    realized_pnl: Optional[float] = None
    hold_duration_sec: Optional[float] = None

    # AI reasoning (optional, from chief_officer/advisor)
    ai_reasoning: Optional[str] = None
    features: Dict[str, Any] = field(default_factory=dict)

    def add_step(
        self, stage: str, passed: bool, detail: str, duration_ms: float = 0.0
    ) -> None:
        self.pipeline_steps.append(PipelineStep(stage, passed, detail, duration_ms))

    def to_dict(self) -> dict:
        d = {
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "strategy": self.strategy,
            "symbol": self.symbol,
            "side": self.side,
            "size_usd": self.size_usd,
            "confidence": self.confidence,
            "market_regime": self.market_regime,
            "current_drawdown": self.current_drawdown,
            "daily_pnl": self.daily_pnl,
            "portfolio_exposure_pct": self.portfolio_exposure_pct,
            "risk_score": self.risk_score,
            "pipeline_steps": [s.to_dict() for s in self.pipeline_steps],
            "approved": self.approved,
            "rejection_reason": self.rejection_reason,
            "violations": self.violations,
            "order_id": self.order_id,
            "fill_price": self.fill_price,
            "slippage_bps": self.slippage_bps,
            "execution_ms": self.execution_ms,
            "outcome": self.outcome.name,
            "realized_pnl": self.realized_pnl,
            "hold_duration_sec": self.hold_duration_sec,
            "ai_reasoning": self.ai_reasoning,
            "features": self.features,
        }
        return d


class DecisionLedger:
    """
    Append-only in-memory ledger with JSONL persistence.
    Thread-safe. Queryable. Survives restarts.
    """

    MAX_MEMORY = 10_000  # keep last N records in memory

    def __init__(self) -> None:
        self._records: List[DecisionRecord] = []
        self._by_trace: Dict[str, DecisionRecord] = {}
        self._lock = threading.RLock()
        self._file_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def append(self, record: DecisionRecord) -> None:
        """Append a decision record. Persists to JSONL immediately."""
        with self._lock:
            self._records.append(record)
            self._by_trace[record.trace_id] = record
            if len(self._records) > self.MAX_MEMORY:
                oldest = self._records.pop(0)
                self._by_trace.pop(oldest.trace_id, None)

        self._persist(record)
        log.audit(
            "decision_recorded",
            trace_id=record.trace_id,
            symbol=record.symbol,
            side=record.side,
            approved=record.approved,
            outcome=record.outcome.name,
        )

    def update_execution(
        self,
        trace_id: str,
        order_id: str,
        fill_price: float,
        slippage_bps: float = 0.0,
        execution_ms: float = 0.0,
    ) -> bool:
        """Fill execution details after an order is confirmed."""
        with self._lock:
            rec = self._by_trace.get(trace_id)
            if rec is None:
                return False
            rec.order_id = order_id
            rec.fill_price = fill_price
            rec.slippage_bps = slippage_bps
            rec.execution_ms = execution_ms
        return True

    def update_outcome(
        self,
        trace_id: str,
        outcome: DecisionOutcome,
        realized_pnl: float,
        hold_duration_sec: float,
    ) -> bool:
        """Label a decision after the position closes."""
        with self._lock:
            rec = self._by_trace.get(trace_id)
            if rec is None:
                return False
            rec.outcome = outcome
            rec.realized_pnl = realized_pnl
            rec.hold_duration_sec = hold_duration_sec
        return True

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def by_trace(self, trace_id: str) -> Optional[DecisionRecord]:
        with self._lock:
            return self._by_trace.get(trace_id)

    def recent(self, n: int = 20) -> List[DecisionRecord]:
        with self._lock:
            return list(self._records[-n:])

    def by_symbol(self, symbol: str, limit: int = 50) -> List[DecisionRecord]:
        with self._lock:
            return [r for r in reversed(self._records) if r.symbol == symbol][:limit]

    def by_outcome(
        self, outcome: DecisionOutcome, limit: int = 50
    ) -> List[DecisionRecord]:
        with self._lock:
            return [r for r in reversed(self._records) if r.outcome == outcome][:limit]

    def mistakes(self, limit: int = 20) -> List[DecisionRecord]:
        return self.by_outcome(DecisionOutcome.MISTAKE, limit)

    def approved_today(self) -> List[DecisionRecord]:
        cutoff = time.time() - 86400
        with self._lock:
            return [r for r in self._records if r.approved and r.timestamp >= cutoff]

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self, window_sec: float = 86400) -> Dict[str, Any]:
        cutoff = time.time() - window_sec
        with self._lock:
            recent = [r for r in self._records if r.timestamp >= cutoff]

        total = len(recent)
        approved = sum(1 for r in recent if r.approved)
        rejected = total - approved
        outcomes: Dict[str, int] = {}
        for r in recent:
            outcomes[r.outcome.name] = outcomes.get(r.outcome.name, 0) + 1

        pnl_records = [r for r in recent if r.realized_pnl is not None]
        total_pnl = sum(r.realized_pnl for r in pnl_records)

        return {
            "window_sec": window_sec,
            "total_decisions": total,
            "approved": approved,
            "rejected": rejected,
            "approval_rate": round(approved / total, 3) if total else 0.0,
            "outcome_distribution": outcomes,
            "total_realized_pnl": round(total_pnl, 2),
            "records_in_memory": len(self._records),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, record: DecisionRecord) -> None:
        from datetime import datetime, timezone

        date_str = datetime.fromtimestamp(record.timestamp, tz=timezone.utc).strftime(
            "%Y-%m-%d"
        )
        path = LEDGER_PATH / f"{date_str}.jsonl"
        line = json.dumps(record.to_dict(), ensure_ascii=False, default=str)
        with self._file_lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def load_from_disk(self, date_str: str) -> List[DecisionRecord]:
        """Load records from a specific date for replay / analysis."""
        path = LEDGER_PATH / f"{date_str}.jsonl"
        if not path.exists():
            return []
        records = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    rec = DecisionRecord(
                        trace_id=d["trace_id"],
                        timestamp=d.get("timestamp", 0.0),
                        source=d.get("source", ""),
                        strategy=d.get("strategy", ""),
                        symbol=d.get("symbol", ""),
                        side=d.get("side", ""),
                        size_usd=d.get("size_usd", 0.0),
                        confidence=d.get("confidence", 0.0),
                        approved=d.get("approved", False),
                        outcome=DecisionOutcome[d.get("outcome", "PENDING")],
                    )
                    records.append(rec)
                except Exception:
                    pass
        return records


# Singleton
decision_ledger = DecisionLedger()
