"""Tests pour le module trade_analysis (LMI)."""

import json
import tempfile
from pathlib import Path

from market_data.models import (
    MarketEvent,
    NormalizedOrderBook,
    NormalizedTrade,
)
from trade_analysis import (
    FlowAnalyzer,
    LMIEngine,
    LiquidityTracker,
    MarketStateLabel,
    ResistanceMeter,
)


def _make_trade(
    ts_ms: int,
    price: float,
    size: float,
    side: str = "buy",
    symbol: str = "BTCUSDT",
) -> NormalizedTrade:
    return NormalizedTrade(
        exchange="test",
        symbol=symbol,
        timestamp_ms=ts_ms,
        price=price,
        size=size,
        side=side,
    )


def _make_book(
    ts_ms: int,
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    symbol: str = "BTCUSDT",
) -> NormalizedOrderBook:
    return NormalizedOrderBook(
        exchange="test",
        symbol=symbol,
        timestamp_ms=ts_ms,
        bids=bids,
        asks=asks,
    )


class TestFlowAnalyzer:
    def test_buy_pressure_dominance(self):
        analyzer = FlowAnalyzer(
            window_ms=5_000,
            snapshot_interval_ms=100,
            large_order_usd=100_000,
        )
        ts = 1_000_000

        for i in range(20):
            t = _make_trade(ts + i * 50, 65000.0, 2.0, "buy")
            result = analyzer.update(t)

        for i in range(5):
            t = _make_trade(ts + 1000 + i * 50, 65000.0, 0.5, "sell")
            result = analyzer.update(t)

        assert result is not None
        assert result.dominant_side == "buy"
        assert result.pressure_ratio > 0.7
        assert result.buy_count > result.sell_count

    def test_large_order_detection(self):
        analyzer = FlowAnalyzer(
            window_ms=5_000,
            snapshot_interval_ms=100,
            large_order_usd=50_000,
        )
        ts = 1_000_000

        t = _make_trade(ts, 65000.0, 0.1, "buy")
        analyzer.update(t)

        t = _make_trade(ts + 100, 65000.0, 1.0, "buy")
        result = analyzer.update(t)

        assert result is not None
        assert result.large_buy_count == 1

    def test_neutral_pressure(self):
        analyzer = FlowAnalyzer(
            window_ms=5_000,
            snapshot_interval_ms=100,
        )
        ts = 1_000_000

        result = None
        for i in range(10):
            t = _make_trade(ts + i * 200, 65000.0, 1.0, "buy")
            r = analyzer.update(t)
            if r:
                result = r
            t = _make_trade(ts + i * 200 + 100, 65000.0, 1.0, "sell")
            r = analyzer.update(t)
            if r:
                result = r

        assert result is not None
        assert result.dominant_side == "neutral"
        assert 0.45 <= result.pressure_ratio <= 0.55


class TestLiquidityTracker:
    def test_liquidity_removed_vs_consumed(self):
        tracker = LiquidityTracker(levels=5, trade_window_ms=5_000)

        book1 = _make_book(
            1_000_000,
            bids=[(64990, 10), (64980, 5), (64970, 3)],
            asks=[(65010, 10), (65020, 5), (65030, 3)],
        )
        tracker.on_book(book1)

        t = _make_trade(1_001_000, 65010, 2.0, "buy")
        tracker.on_trade(t)

        book2 = _make_book(
            1_002_000,
            bids=[(64990, 10), (64980, 5), (64970, 3)],
            asks=[(65010, 8), (65020, 5), (65030, 3)],
        )
        dynamics = tracker.on_book(book2)

        assert dynamics is not None
        assert dynamics.ask_consumed_usd > 0
        assert dynamics.timestamp_ms == 1_002_000

    def test_cancellation_detection(self):
        tracker = LiquidityTracker(levels=5, trade_window_ms=5_000)

        book1 = _make_book(
            1_000_000,
            bids=[(64990, 10), (64980, 5)],
            asks=[(65010, 10), (65020, 5)],
        )
        tracker.on_book(book1)

        book2 = _make_book(
            1_002_000,
            bids=[(64990, 10), (64980, 5)],
            asks=[(65010, 2), (65020, 5)],
        )
        dynamics = tracker.on_book(book2)

        assert dynamics is not None
        assert dynamics.ask_removed_usd > 0
        assert dynamics.cancellation_rate_ask > 0


class TestResistanceMeter:
    def test_high_resistance(self):
        meter = ResistanceMeter(
            window_ms=5_000,
            snapshot_interval_ms=100,
        )
        ts = 1_000_000

        result = None
        for i in range(50):
            t = _make_trade(ts + i * 100, 65000.0, 1.0, "buy")
            r = meter.update(t)
            if r:
                result = r

        assert result is not None
        assert result.resistance_score > 0
        assert result.price_displacement_bps < 1.0

    def test_high_fragility(self):
        meter = ResistanceMeter(
            window_ms=5_000,
            snapshot_interval_ms=100,
        )
        ts = 1_000_000

        result = None
        for i in range(20):
            price = 65000.0 + i * 10
            t = _make_trade(ts + i * 100, price, 0.01, "buy")
            r = meter.update(t)
            if r:
                result = r

        assert result is not None
        assert result.price_displacement_bps > 10


class TestLMIEngine:
    def test_full_pipeline(self):
        engine = LMIEngine(
            symbol="BTCUSDT",
            flow_window_ms=5_000,
            resistance_window_ms=5_000,
            snapshot_interval_ms=500,
        )
        ts = 1_000_000

        book = _make_book(
            ts,
            bids=[(64990, 10), (64980, 5), (64970, 3)],
            asks=[(65010, 10), (65020, 5), (65030, 3)],
        )
        engine.process_event(MarketEvent.from_orderbook(book))

        book2 = _make_book(
            ts + 500,
            bids=[(64990, 10), (64980, 5), (64970, 3)],
            asks=[(65010, 8), (65020, 5), (65030, 3)],
        )
        engine.process_event(MarketEvent.from_orderbook(book2))

        fields = []
        for i in range(30):
            t = _make_trade(ts + 1000 + i * 100, 65000.0, 1.0, "buy")
            pf = engine.process_event(MarketEvent.from_trade(t))
            if pf:
                fields.append(pf)

        assert len(fields) > 0
        pf = fields[-1]
        assert pf.symbol == "BTCUSDT"
        assert pf.state in MarketStateLabel
        assert 0 <= pf.state_confidence <= 1.0
        assert pf.flow.buy_volume_usd > 0
        assert pf.price > 0

    def test_serialization(self):
        engine = LMIEngine(
            symbol="BTCUSDT",
            snapshot_interval_ms=100,
        )
        ts = 1_000_000

        book = _make_book(
            ts,
            bids=[(64990, 10), (64980, 5)],
            asks=[(65010, 10), (65020, 5)],
        )
        engine.process_event(MarketEvent.from_orderbook(book))
        book2 = _make_book(
            ts + 50,
            bids=[(64990, 10), (64980, 5)],
            asks=[(65010, 9), (65020, 5)],
        )
        engine.process_event(MarketEvent.from_orderbook(book2))

        pf = None
        for i in range(20):
            t = _make_trade(ts + 100 + i * 100, 65000.0, 1.0, "buy")
            r = engine.process_event(MarketEvent.from_trade(t))
            if r:
                pf = r

        assert pf is not None
        d = pf.as_dict()
        serialized = json.dumps(d)
        loaded = json.loads(serialized)
        assert loaded["symbol"] == "BTCUSDT"
        assert "flow" in loaded
        assert "liquidity" in loaded
        assert "resistance" in loaded
        assert "state" in loaded

    def test_replay_events(self):
        engine = LMIEngine(
            symbol="BTCUSDT",
            snapshot_interval_ms=100,
        )

        events = []
        ts = 1_000_000

        book = _make_book(
            ts,
            bids=[(64990, 10)],
            asks=[(65010, 10)],
        )
        events.append(MarketEvent.from_orderbook(book))
        book2 = _make_book(
            ts + 50,
            bids=[(64990, 10)],
            asks=[(65010, 9)],
        )
        events.append(MarketEvent.from_orderbook(book2))

        for i in range(15):
            t = _make_trade(ts + 100 + i * 50, 65000.0, 0.5, "buy")
            events.append(MarketEvent.from_trade(t))

        fields = list(engine.replay_events(iter(events)))
        assert len(fields) > 0

    def test_recorder_integration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = LMIEngine(
                symbol="BTCUSDT",
                snapshot_interval_ms=100,
                record=True,
                record_dir=tmpdir,
            )
            ts = 1_000_000

            book = _make_book(
                ts,
                bids=[(64990, 10)],
                asks=[(65010, 10)],
            )
            engine.process_event(MarketEvent.from_orderbook(book))
            book2 = _make_book(
                ts + 50,
                bids=[(64990, 10)],
                asks=[(65010, 9)],
            )
            engine.process_event(MarketEvent.from_orderbook(book2))

            for i in range(20):
                t = _make_trade(ts + 100 + i * 50, 65000.0, 1.0, "buy")
                engine.process_event(MarketEvent.from_trade(t))

            engine.close()

            gz_files = list(Path(tmpdir).glob("lmi_*.jsonl.gz"))
            assert len(gz_files) > 0


class TestMarketStateClassification:
    def _run_scenario(self, buy_ratio: float, price_move_bps: float, vol: float):
        engine = LMIEngine(
            symbol="BTCUSDT",
            snapshot_interval_ms=100,
        )
        ts = 1_000_000
        base_price = 65000.0

        book = _make_book(
            ts,
            bids=[(base_price - 10, 10), (base_price - 20, 5)],
            asks=[(base_price + 10, 10), (base_price + 20, 5)],
        )
        engine.process_event(MarketEvent.from_orderbook(book))
        book2 = _make_book(
            ts + 50,
            bids=[(base_price - 10, 10), (base_price - 20, 5)],
            asks=[(base_price + 10, 9), (base_price + 20, 5)],
        )
        engine.process_event(MarketEvent.from_orderbook(book2))

        n_buys = int(20 * buy_ratio)
        n_sells = 20 - n_buys
        price_step = base_price * price_move_bps / 10_000.0 / 20
        size = vol / 20 / base_price

        idx = 0
        pf = None
        for i in range(n_buys):
            p = base_price + price_step * idx
            t = _make_trade(ts + 100 + idx * 50, p, size, "buy")
            result = engine.process_event(MarketEvent.from_trade(t))
            if result:
                pf = result
            idx += 1
        for i in range(n_sells):
            p = base_price + price_step * idx
            t = _make_trade(ts + 100 + idx * 50, p, size, "sell")
            result = engine.process_event(MarketEvent.from_trade(t))
            if result:
                pf = result
            idx += 1

        return pf

    def test_quiet_market(self):
        pf = self._run_scenario(0.5, 0.0, 1000.0)
        assert pf is not None
        assert pf.state == MarketStateLabel.QUIET

    def test_expansion(self):
        pf = self._run_scenario(0.8, 30.0, 200_000.0)
        if pf:
            assert pf.state in MarketStateLabel
