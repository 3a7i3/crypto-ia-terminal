"""
tests/integration/test_p4_pipeline.py — P4.3 : Tests d'integration bout-en-bout.

Pipeline complet teste sans reseau ni service externe :
  market_data models → ReplayEngine (JSONL synthetique) → FlowSnapshot
  → ExecutionSimulator → exchange_constraints → FillErrorMetric
  → WalkForwardEngine → WalkForwardReporter → monitoring

Tous les tests sont deterministes (SEED=42), reproductibles et autonomes.
"""

from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path

import pytest

# exchange_constraints
from exchange_constraints.binance_rules import get_symbol_info
from exchange_constraints.order_validator import OrderValidator

# execution_simulator
from execution_simulator.config import binance_usdt_futures_simulator
from execution_simulator.fill_error_metric import FillErrorMetric, FillMatcher, RealFill
from execution_simulator.models import MarketSnapshot, OrderIntent
from market_data.metrics.flow import CumulativeDeltaTracker, FlowSnapshot

# market_data
from market_data.models import MarketEvent, NormalizedOrderBook, NormalizedTrade
from market_data.replay_engine import ReplayEngine

# metrics / monitor
from metrics.oos_metrics import TradeResult, compute_oos_metrics
from monitor.degradation_tracker import DegradationTracker
from monitoring.logger import null_sink
from monitoring.metrics import MetricsRegistry
from monitoring.pipeline_monitor import PipelineMonitor

# walk_forward
from walk_forward.engine import WalkForwardEngine
from walk_forward.reporter import WalkForwardReporter
from walk_forward.walk_forward_loop import WalkForwardLoop
from walk_forward.window_splitter import WindowSplitter

SEED = 42


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trade_jsonl(n: int, rng: random.Random, symbol: str = "BTCUSDT") -> str:
    """Genere N lignes JSONL de trades synthetiques."""
    lines = []
    ts = 1_700_000_000_000
    price = 50_000.0
    for i in range(n):
        ts += rng.randint(50, 500)
        price += rng.gauss(0, 20)
        price = max(40_000.0, min(60_000.0, price))
        side = "buy" if rng.random() > 0.5 else "sell"
        lines.append(
            json.dumps(
                {
                    "event_type": "trade",
                    "exchange": "binance",
                    "symbol": symbol,
                    "timestamp_ms": ts,
                    "data": {
                        "price": round(price, 2),
                        "size": round(rng.uniform(0.01, 2.0), 4),
                        "side": side,
                        "trade_id": str(i),
                        "is_liquidation": False,
                    },
                }
            )
        )
    return "\n".join(lines)


def _make_book_jsonl(ts: int, symbol: str = "BTCUSDT") -> str:
    """Genere un snapshot d'orderbook."""
    bids = [[50000 - i * 10, round(0.5 + i * 0.1, 3)] for i in range(10)]
    asks = [[50010 + i * 10, round(0.5 + i * 0.1, 3)] for i in range(10)]
    # Ajouter un mur
    bids[3][1] = 50.0
    return json.dumps(
        {
            "event_type": "orderbook",
            "exchange": "binance",
            "symbol": symbol,
            "timestamp_ms": ts,
            "data": {
                "bids": bids,
                "asks": asks,
                "sequence": 1,
                "is_snapshot": True,
            },
        }
    )


# ---------------------------------------------------------------------------
# Test 1 : market_data → ReplayEngine → FlowSnapshot
# ---------------------------------------------------------------------------


class TestMarketDataToReplay:

    def test_replay_produces_flow_snapshots(self):
        rng = random.Random(SEED)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(_make_trade_jsonl(200, rng))
            f.write("\n")
            f.write(_make_book_jsonl(1_700_001_000_000))
            path = f.name

        engine = ReplayEngine(path, symbol="BTCUSDT", snapshot_interval_ms=1000)
        snapshots = list(engine.replay())

        assert len(snapshots) > 0
        assert engine.stats.trade_count == 200
        for s in snapshots:
            assert isinstance(s, FlowSnapshot)
            assert s.symbol == "BTCUSDT"

    def test_replay_stats_coherent(self):
        rng = random.Random(SEED)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(_make_trade_jsonl(100, rng))
            path = f.name

        engine = ReplayEngine(path)
        list(engine.replay())
        assert engine.stats.total_events == 100
        assert engine.stats.trade_count == 100
        assert engine.stats.duration_ms > 0

    def test_replay_corrupted_lines_skipped(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(
                '{"event_type": "trade", "exchange": "binance", "symbol": "BTCUSDT", '
                '"timestamp_ms": 1700000000000, "data": {"price": 50000, "size": 1.0, '
                '"side": "buy", "trade_id": "1"}}\n'
            )
            f.write("CORRUPTED LINE\n")
            f.write(
                '{"event_type": "trade", "exchange": "binance", "symbol": "BTCUSDT", '
                '"timestamp_ms": 1700001000000, "data": {"price": 50100, "size": 0.5, '
                '"side": "sell", "trade_id": "2"}}\n'
            )
            path = f.name

        engine = ReplayEngine(path)
        list(engine.replay())
        assert engine.stats.trade_count == 2  # corrupted skipped


# ---------------------------------------------------------------------------
# Test 2 : ExecutionSimulator + exchange_constraints
# ---------------------------------------------------------------------------


class TestExecutionWithConstraints:

    def test_valid_order_fills(self):
        rng = random.Random(SEED)
        sim = binance_usdt_futures_simulator(seed=SEED)
        info = get_symbol_info("BTCUSDT")
        validator = OrderValidator()

        intent = OrderIntent(
            symbol="BTCUSDT",
            side="buy",
            size=0.01,
            order_type="market",
            signal_price=50_000.0,
        )
        snap = MarketSnapshot(
            symbol="BTCUSDT",
            price=50_000.0,
            volume_24h=50_000.0,
            volatility_pct=2.0,
        )

        # Valider via exchange_constraints
        result = validator.validate(info, qty=0.01, price=None, order_type="market")
        assert result.is_valid

        # Executer via simulateur
        fill = sim.execute(intent, snap)
        assert not fill.is_rejected
        assert fill.fill_price > 0
        assert fill.filled_size > 0

    def test_rejected_order_below_min_notional(self):
        info = get_symbol_info("BTCUSDT")
        validator = OrderValidator()
        # 0.000001 BTC * 50000 = 0.05 USD << min_notional=5 USD
        result = validator.validate(info, qty=0.000001, price=None, order_type="market")
        assert not result.is_valid

    def test_deterministic_fill_price(self):
        sim1 = binance_usdt_futures_simulator(seed=SEED)
        sim2 = binance_usdt_futures_simulator(seed=SEED)
        intent = OrderIntent("BTCUSDT", "buy", 0.1, "market", 50_000.0)
        snap = MarketSnapshot("BTCUSDT", 50_000.0, 50_000.0, 2.0)
        assert (
            sim1.execute(intent, snap).fill_price
            == sim2.execute(intent, snap).fill_price
        )


# ---------------------------------------------------------------------------
# Test 3 : FillErrorMetric pipeline
# ---------------------------------------------------------------------------


class TestFillErrorPipeline:

    def test_fill_matcher_pipeline(self):
        """OrderIntent → FillMatcher → RealFill → FillErrorMetric."""
        from dataclasses import dataclass

        @dataclass
        class _Trade:
            exchange: str
            symbol: str
            timestamp_ms: int
            price: float
            size: float
            side: str

        trades = [
            _Trade("binance", "BTCUSDT", 1_700_000_001_000, 50_010.0, 1.0, "buy"),
            _Trade("binance", "BTCUSDT", 1_700_000_002_000, 50_020.0, 1.0, "buy"),
        ]
        matcher = FillMatcher(trades, max_window_ms=5_000)
        sim = binance_usdt_futures_simulator(seed=SEED)
        metric = FillErrorMetric()

        for trade in trades:
            intent = OrderIntent("BTCUSDT", "buy", 0.5, "market", 50_000.0)
            snap = MarketSnapshot("BTCUSDT", 50_000.0, 50_000.0, 2.0)
            sim_fill = sim.execute(intent, snap)
            real = matcher.match(intent, signal_ts_ms=trade.timestamp_ms - 500)
            if real and not sim_fill.is_rejected:
                metric.record(sim_fill, real)

        assert metric.n_samples > 0
        stats = metric.summary()
        assert stats.n_samples == metric.n_samples


# ---------------------------------------------------------------------------
# Test 4 : WalkForward → Monitoring
# ---------------------------------------------------------------------------


class TestWalkForwardWithMonitoring:

    def _make_data(self, n: int = 1000) -> list[dict]:
        rng = random.Random(SEED)
        return [
            {"value": rng.gauss(0.15, 1.0), "regime": ["bull", "bear", "stable"][i % 3]}
            for i in range(n)
        ]

    def test_full_walk_forward_pipeline(self):
        """Walk-forward complet avec monitoring integre."""
        monitor = PipelineMonitor(sink=null_sink())
        data = self._make_data(1000)

        def optimizer(train):
            vals = [d["value"] for d in train]
            return {"thr": sum(vals) / max(len(vals), 1)}

        def validator(test, params):
            thr = params["thr"]
            results = []
            for i, d in enumerate(test):
                if abs(d["value"]) > abs(thr):
                    pnl = d["value"] * 0.05
                    t = TradeResult(i * 1000, pnl, regime=d["regime"])
                    results.append(t)
                    monitor.record_trade_processed(
                        "BTCUSDT",
                        latency_ms=50.0 + i * 0.1,
                        slippage_bps=2.0,
                        fill_ratio=1.0,
                    )
            return results

        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, step=100)
        loop = WalkForwardLoop(optimizer=optimizer, validator=validator)
        engine = WalkForwardEngine(splitter=sp, loop=loop)

        result = engine.run(data)

        # Enregistrer les folds dans le monitor
        for fold in result.folds:
            if fold.is_valid:
                monitor.record_fold_completed(
                    fold.fold.fold_index,
                    fold.oos_metrics.n_trades,
                    fold.oos_metrics.sharpe_ratio,
                    duration_s=0.05,
                    is_profitable=fold.oos_metrics.is_profitable,
                )

        snap = monitor.snapshot()

        assert result.n_folds == sp.n_folds
        assert snap["counters"]["folds_completed_total"]["value"] == result.n_folds
        assert snap["counters"]["trades_processed_total"]["value"] > 0

    def test_walk_forward_reporter_exports(self):
        """WalkForwardEngine → WalkForwardReporter (tous les exports)."""
        data = self._make_data(1000)

        def opt(train):
            return {"thr": sum(d["value"] for d in train) / max(len(train), 1)}

        def val(test, params):
            return [
                TradeResult(i * 1000, d["value"] * 0.05, regime=d["regime"])
                for i, d in enumerate(test)
                if abs(d["value"]) > abs(params["thr"])
            ]

        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, step=100)
        loop = WalkForwardLoop(optimizer=opt, validator=val)
        result = WalkForwardEngine(sp, loop).run(data)

        with tempfile.TemporaryDirectory() as tmp:
            reporter = WalkForwardReporter(
                project_os_dir=Path(tmp) / "project_os",
                reports_dir=Path(tmp) / "reports",
            )
            state_path = reporter.save_state(result)
            jsonl_path = reporter.export_jsonl(result, tag="integration")
            md_path = reporter.write_markdown(result)

            assert state_path.exists()
            assert jsonl_path.exists()
            assert md_path.exists()

            # Le state JSON doit etre valide
            state = json.loads(state_path.read_text())
            assert state["n_folds"] == result.n_folds

            # Le JSONL doit avoir une ligne par fold
            lines = jsonl_path.read_text().strip().split("\n")
            assert len(lines) == result.n_folds

            # Le Markdown doit contenir les sections attendues
            md = md_path.read_text()
            assert "Walk-Forward" in md
            assert "Sharpe" in md


# ---------------------------------------------------------------------------
# Test 5 : Degradation detectee dans le pipeline complet
# ---------------------------------------------------------------------------


class TestDegradationInPipeline:

    def test_degrading_strategy_detected(self):
        """Strategie en degradation -> DegradationTracker signale."""
        rng = random.Random(SEED)
        tracker = DegradationTracker(
            sharpe_z_warning=-1.0,
            sharpe_z_critical=-2.0,
        )
        monitor = PipelineMonitor(sink=null_sink())

        # Simuler des folds avec Sharpe en forte baisse
        fold_sharpes = [2.0, 1.8, 1.5, 0.5, -0.5, -1.5]
        for i, sharpe in enumerate(fold_sharpes):
            from metrics.oos_metrics import OOSMetrics

            metrics = OOSMetrics(
                n_trades=30,
                total_return_pct=sharpe * 5,
                sharpe_ratio=sharpe,
                sortino_ratio=sharpe * 1.2,
                max_drawdown_pct=-10.0,
                win_rate=0.55,
                profit_factor=1.3 if sharpe > 0 else 0.8,
                avg_win_pct=2.0,
                avg_loss_pct=-1.5,
                expectancy_pct=0.3,
                calmar_ratio=abs(sharpe * 5 / 10),
            )
            events = tracker.record(i, metrics)
            for ev in events:
                monitor.record_degradation_alert(i, ev.metric, ev.severity, ev.message)

        assert tracker.is_degrading
        snap = monitor.snapshot()
        assert snap["counters"]["errors_total"]["value"] > 0
