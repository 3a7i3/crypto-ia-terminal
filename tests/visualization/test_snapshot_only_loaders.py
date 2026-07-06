from __future__ import annotations

import json

from visualization.api.health_api import load_health_snapshot
from visualization.api.pipeline_api import load_pipeline_snapshot
from visualization.api.portfolio_api import load_portfolio_snapshot
from visualization.api import system_snapshot_source


def test_visualization_loaders_use_system_snapshot_only(tmp_path, monkeypatch):
    live_snapshot = tmp_path / "live_snapshot.json"
    live_snapshot.write_text(
        json.dumps(
            {
                "system_snapshot": {
                    "meta": {
                        "snapshot_id": "42-abc",
                        "timestamp_utc": "2026-07-06T10:00:00Z",
                        "cycle": 42,
                        "engine_version": "v91",
                    },
                    "health": {
                        "api": True,
                        "database": True,
                        "telegram": False,
                        "market": True,
                        "strategy": True,
                    },
                    "portfolio": {
                        "paper_equity": 1234.5,
                        "paper_cash": 1100.0,
                        "free_cash": 1000.0,
                        "portfolio_exposure_pct": 10.0,
                        "open_pnl_usd": 12.3,
                        "open_positions": 2,
                        "correlation_risk_pct": 5.0,
                    },
                    "ai_decision": {
                        "state": "BLOCKED",
                        "reason_code": "R001",
                        "reason_text": "Confidence too low",
                        "brain_score_pct": 72,
                    },
                    "market": {
                        "regime": "bull_trend",
                        "exchange_latency_ms": 299.0,
                        "exchange_uptime_pct": 99.5,
                    },
                    "block_stats": {
                        "current_cycle": [["confidence", 2], ["risk", 1]],
                        "session": [["confidence", 4], ["risk", 3]],
                        "lifetime": [["confidence", 40], ["risk", 30]],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(system_snapshot_source, "_LIVE_SNAPSHOT", live_snapshot)

    health = load_health_snapshot()
    pipeline = load_pipeline_snapshot()
    portfolio = load_portfolio_snapshot()

    assert health.capital_usd == 1234.5
    assert health.trading_enabled is False
    assert health.knowledge_pct == 72.0
    assert health.top_root_cause == "R001"

    assert pipeline.cycle == 42
    assert pipeline.n_refused == 3
    assert pipeline.n_traded == 0
    assert pipeline.regime_distribution == {"bull_trend": 3}

    assert portfolio.capital_usd == 1234.5
    assert portfolio.total_pnl_usd == 12.3
    assert portfolio.n_trades == 0
