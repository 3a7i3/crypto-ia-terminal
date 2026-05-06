"""
Decision Trace — Log complet de chaque décision
Explique: contexte → logique → choix → résultat
"""

from typing import Any
from pathlib import Path
from datetime import datetime, timezone
import json


class DecisionTrace:
    """Enregistre une décision individuelle."""

    def __init__(
        self,
        trade_id: str,
        symbol: str,
        context: dict[str, Any],
        decision: dict[str, Any],
        execution: dict[str, Any],
        result: dict[str, Any],
    ):
        self.trade_id = trade_id
        self.symbol = symbol
        self.context = context
        self.decision = decision
        self.execution = execution
        self.result = result
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def get_summary(self) -> str:
        """Résumé lisible."""
        return f"""
Trade: {self.symbol} ({self.trade_id})
Context: regime={self.context.get('regime')}, vol={self.context.get('volatility', 0.0):.4f}
Decision: tp={self.decision.get('tp', 0.0):.4f}, sl={self.decision.get('sl', 0.0):.4f}
Execution: entry={self.execution.get('entry_price', 0.0):.8f}
Result: pnl={self.result.get('pnl_pct', 0.0):+.2%}, quality={self.result.get('quality')}
"""

    def as_dict(self) -> dict[str, Any]:
        """Export as dict."""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "context": self.context,
            "decision": self.decision,
            "execution": self.execution,
            "result": self.result,
        }


class DecisionTraceLog:
    """Log de toutes les décisions."""

    def __init__(self, log_file: Path = Path("logs/decision_trace.jsonl")):
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log_trade(self, trace: DecisionTrace) -> None:
        """Log une décision."""
        with open(self.log_file, "a") as f:
            f.write(json.dumps(trace.as_dict()) + "\n")

    def load_traces(self) -> list[DecisionTrace]:
        """Charge tous les traces."""
        if not self.log_file.exists():
            return []

        traces = []
        with open(self.log_file, "r") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    trace = DecisionTrace(
                        trade_id=data.get("trade_id"),
                        symbol=data.get("symbol"),
                        context=data.get("context", {}),
                        decision=data.get("decision", {}),
                        execution=data.get("execution", {}),
                        result=data.get("result", {}),
                    )
                    traces.append(trace)
        return traces

    def get_decision_stats(self, regime: str | None = None) -> dict[str, Any]:
        """Stats des décisions."""
        traces = self.load_traces()

        if regime:
            traces = [t for t in traces if t.context.get("regime") == regime]

        if not traces:
            return {}

        qualities = {}
        results = []
        for trace in traces:
            quality = trace.result.get("quality")
            qualities[quality] = qualities.get(quality, 0) + 1
            results.append(float(trace.result.get("pnl_pct", 0.0)))

        total = len(traces)
        wins = sum(1 for r in results if r > 0)

        return {
            "total": total,
            "winrate": wins / total if total else 0.0,
            "avg_result": sum(results) / total if total else 0.0,
            "quality_breakdown": qualities,
            "best_decision": max(results) if results else 0.0,
            "worst_decision": min(results) if results else 0.0,
        }

    def get_improvement_trend(self, window: int = 10) -> list[dict[str, Any]]:
        """Trend d'amélioration."""
        traces = self.load_traces()
        if len(traces) < window:
            return []

        trend = []
        for i in range(window, len(traces) + 1):
            window_traces = traces[i - window : i]
            results = [float(t.result.get("pnl_pct", 0.0)) for t in window_traces]
            wins = sum(1 for r in results if r > 0)

            trend.append({
                "period": i,
                "avg_pnl": sum(results) / window,
                "winrate": wins / window,
            })

        return trend
