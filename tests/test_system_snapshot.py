from dataclasses import FrozenInstanceError

import pytest

from observability.system_snapshot import (
    AIDecisionSnapshot,
    APIAccountSnapshot,
    BlockStatsAccumulator,
    DecisionState,
    HealthSnapshot,
    MarketSnapshot,
    PipelineStage,
    PipelineStageStatus,
    PortfolioSnapshot,
    ReasonCode,
    build_system_snapshot,
)
from observability.system_snapshot_renderers import (
    render_ai_decision_block,
    render_pipeline_block,
)


def _build_sample_snapshot(tmp_path):
    return build_system_snapshot(
        cycle=12,
        engine_version="v9.1",
        health=HealthSnapshot(
            api=True, database=True, telegram=True, market=True, strategy=True
        ),
        portfolio=PortfolioSnapshot(
            paper_equity=1000.0,
            paper_cash=900.0,
            free_cash=400.0,
            portfolio_exposure_pct=10.0,
            open_pnl_usd=2.5,
            open_positions=1,
            correlation_risk_pct=5.0,
        ),
        ai_decision=AIDecisionSnapshot(
            decision_id="120001",
            state=DecisionState.BLOCKED,
            reason_code=ReasonCode.EXPOSURE_LIMIT,
            reason_text="portfolio (1/3)",
            blocking_module="PortfolioBrain",
            confidence_pct=78,
            highest_candidate_symbol="BTC/USDT",
            highest_candidate_score=64.0,
            required_score=66.0,
            next_evaluation_sec=60,
            brain_score_pct=78,
        ),
        market=MarketSnapshot(
            regime="sideways", exchange_latency_ms=230.0, exchange_uptime_pct=99.5
        ),
        pipeline=(
            PipelineStage(
                name="Scanner",
                status=PipelineStageStatus.OK,
                duration_ms=10.0,
                message="28/28",
            ),
        ),
        api_account=APIAccountSnapshot(
            api_equity_usdt=6.8,
            api_free_cash_usdt=6.8,
            api_positions=0,
            api_assets=(("USDT", 6.8),),
        ),
        block_stats=BlockStatsAccumulator(
            lifetime_path=str(tmp_path / "block_stats.json")
        ).update({"risk": 2}),
    )


def test_system_snapshot_is_frozen(tmp_path):
    snap = _build_sample_snapshot(tmp_path)
    with pytest.raises(FrozenInstanceError):
        snap.meta.cycle = 99  # type: ignore[misc]


def test_system_snapshot_has_metadata(tmp_path):
    snap = _build_sample_snapshot(tmp_path)
    assert snap.meta.snapshot_id
    assert snap.meta.timestamp_utc.endswith("Z")
    assert snap.meta.engine_version == "v9.1"


def test_renderers_use_snapshot_payload(tmp_path):
    snap = _build_sample_snapshot(tmp_path)
    ai = render_ai_decision_block(snap)
    pipe = render_pipeline_block(snap)
    assert "R002" in ai
    assert "Decision ID: #120001" in ai
    assert "Scanner" in pipe
