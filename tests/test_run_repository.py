import uuid
from datetime import datetime, timezone

import pytest

from src.domain.trade_event import MarketRegime, TradeEvent
from src.storage.run_repository import RunRepository

_UTC = timezone.utc
_NOW = datetime(2025, 1, 1, tzinfo=_UTC)


def _make_trade(pnl: float, symbol: str = "BTC") -> TradeEvent:
    return TradeEvent(
        trade_id=str(uuid.uuid4()),
        run_id="test-run",
        strategy_id="SMA_TEST",
        symbol=symbol,
        side="buy",
        entry_price=100.0,
        exit_price=100.0 + pnl,
        quantity=1.0,
        execution_mode="backtest",
        gross_pnl_usd=pnl,
        fees_usd=0.0,
        slippage_usd=0.0,
        opened_at=_NOW,
        closed_at=_NOW,
        regime=MarketRegime.SIDEWAYS,
        signal_score=None,
    )


def _sample_report(
    run_id="test_001", regime="trending", pnl=100.0, wr=0.6, dd=0.05, trades=5
):
    return {
        "run_id": run_id,
        "strategy_id": "SMA_TEST",
        "regime": regime,
        "regime_atr": 0.012,
        "regime_slope": 0.05,
        "total_trades": trades,
        "final_balance": 10000.0 + pnl,
        "total_pnl": pnl,
        "win_rate": wr,
        "max_drawdown": dd,
        "trades": [_make_trade(pnl)],
    }


@pytest.fixture
def repo(tmp_path):
    db = str(tmp_path / "test_runs.sqlite")
    return RunRepository(db_path=db)


# -- save & retrieve --


def test_save_and_count(repo):
    repo.save_run(_sample_report("r1"))
    assert repo.count() == 1


def test_save_multiple(repo):
    for i in range(5):
        repo.save_run(_sample_report(f"r{i}"))
    assert repo.count() == 5


def test_last_runs_limit(repo):
    for i in range(10):
        repo.save_run(_sample_report(f"r{i:03d}"))
    assert len(repo.last_runs(3)) == 3


def test_last_runs_order_desc(repo):
    for i in range(5):
        repo.save_run(_sample_report(f"r{i:03d}"))
    runs = repo.last_runs(5)
    timestamps = [r["created_at"] for r in runs]
    assert timestamps == sorted(timestamps, reverse=True)


def test_runs_by_regime(repo):
    repo.save_run(_sample_report("t1", regime="trending"))
    repo.save_run(_sample_report("t2", regime="trending"))
    repo.save_run(_sample_report("r1", regime="sideways"))
    assert len(repo.runs_by_regime("trending")) == 2
    assert len(repo.runs_by_regime("sideways")) == 1
    assert len(repo.runs_by_regime("volatile")) == 0


def test_runs_by_strategy(repo):
    r = _sample_report("s1")
    r["strategy_id"] = "SMA_FAST"
    repo.save_run(r)
    assert len(repo.runs_by_strategy("SMA_FAST")) == 1
    assert len(repo.runs_by_strategy("SMA_SLOW")) == 0


# -- aggregate --


def test_aggregate_empty(repo):
    a = repo.aggregate([])
    assert a["n_runs"] == 0
    assert a["avg_pnl"] == 0.0


def test_aggregate_avg_pnl(repo):
    runs = [
        _sample_report("r1", pnl=100.0),
        _sample_report("r2", pnl=200.0),
    ]
    for r in runs:
        repo.save_run(r)
    a = repo.aggregate(repo.last_runs(10))
    assert a["avg_pnl"] == 150.0


def test_aggregate_profit_factor(repo):
    runs = [
        _sample_report("r1", pnl=200.0),
        _sample_report("r2", pnl=-100.0),
    ]
    for r in runs:
        repo.save_run(r)
    a = repo.aggregate(repo.last_runs(10))
    assert a["profit_factor"] == 2.0


# -- regime distribution --


def test_regime_distribution(repo):
    repo.save_run(_sample_report("t1", regime="trending"))
    repo.save_run(_sample_report("t2", regime="trending"))
    repo.save_run(_sample_report("r1", regime="sideways"))
    dist = repo.regime_distribution()
    assert dist["trending"] == 2
    assert dist["sideways"] == 1


# -- upsert --


def test_save_run_upsert(repo):
    r = _sample_report("dup")
    repo.save_run(r)
    r["total_pnl"] = 999.0
    repo.save_run(r)
    assert repo.count() == 1
    assert repo.last_runs(1)[0]["total_pnl"] == 999.0


# -- n_candles stored --


def test_n_candles_persisted(repo):
    repo.save_run(_sample_report("c1"), n_candles=200)
    runs = repo.last_runs(1)
    assert runs[0]["n_candles"] == 200
