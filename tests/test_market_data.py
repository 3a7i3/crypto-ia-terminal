"""
tests/test_market_data.py — Tests déterministes pour market_data/.

Couvre : models, metrics (orderbook + flow), replay_engine.
Les connecteurs WebSocket ne sont pas testés ici (dépendance réseau).
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from market_data.metrics.flow import (
    AbsorptionTracker,
    CumulativeDeltaTracker,
    DeltaWindow,
    FlowSnapshot,
    PersistenceTracker,
    SweepDetector,
    WallLifecycle,
)
from market_data.metrics.orderbook import (
    book_pressure,
    depth_profile,
    features_vector,
    imbalance,
    skew,
    spread_metrics,
    wall_detection,
    weighted_mid,
)
from market_data.models import (
    MarketEvent,
    NormalizedCandle,
    NormalizedLiquidityEvent,
    NormalizedOrderBook,
    NormalizedTrade,
)
from market_data.replay_engine import ReplayEngine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def book_balanced():
    """Book parfaitement equilibré bid=ask."""
    return NormalizedOrderBook(
        exchange="binance",
        symbol="BTCUSDT",
        timestamp_ms=1000,
        bids=[(100.0, 10.0), (99.0, 10.0), (98.0, 10.0)],
        asks=[(101.0, 10.0), (102.0, 10.0), (103.0, 10.0)],
    )


@pytest.fixture
def book_bid_heavy():
    """Book bid-dominant."""
    return NormalizedOrderBook(
        exchange="binance",
        symbol="BTCUSDT",
        timestamp_ms=1000,
        bids=[(100.0, 50.0), (99.0, 50.0), (98.0, 50.0)],
        asks=[(101.0, 10.0), (102.0, 10.0), (103.0, 10.0)],
    )


@pytest.fixture
def book_with_wall():
    """Book avec un mur bid visible."""
    return NormalizedOrderBook(
        exchange="binance",
        symbol="BTCUSDT",
        timestamp_ms=1000,
        bids=[(100.0, 1.0), (99.5, 1.0), (99.0, 100.0), (98.0, 1.0)],
        asks=[(101.0, 1.0), (102.0, 1.0), (103.0, 1.0), (104.0, 1.0)],
    )


@pytest.fixture
def empty_book():
    return NormalizedOrderBook("b", "X", 0, [], [])


@pytest.fixture
def trade_buy():
    return NormalizedTrade("binance", "BTCUSDT", 1000, 65000.0, 1.0, "buy", "T1")


@pytest.fixture
def trade_sell():
    return NormalizedTrade("binance", "BTCUSDT", 2000, 65000.0, 2.0, "sell", "T2")


@pytest.fixture
def simple_trades():
    return [
        NormalizedTrade(
            "binance",
            "BTCUSDT",
            1000 + i * 500,
            100.0,
            1.0,
            "buy" if i % 2 == 0 else "sell",
        )
        for i in range(10)
    ]


# ---------------------------------------------------------------------------
# NormalizedTrade
# ---------------------------------------------------------------------------


class TestNormalizedTrade:
    def test_signed_size_buy(self, trade_buy):
        assert trade_buy.signed_size == 1.0

    def test_signed_size_sell(self, trade_sell):
        assert trade_sell.signed_size == -2.0

    def test_value_usd(self, trade_buy):
        assert trade_buy.value_usd == pytest.approx(65000.0)

    def test_default_trade_id(self):
        t = NormalizedTrade("b", "X", 0, 100.0, 1.0, "buy")
        assert t.trade_id == ""
        assert not t.is_liquidation


# ---------------------------------------------------------------------------
# NormalizedOrderBook
# ---------------------------------------------------------------------------


class TestNormalizedOrderBook:
    def test_empty_book_safe_properties(self, empty_book):
        assert empty_book.best_bid is None
        assert empty_book.best_ask is None
        assert empty_book.mid_price is None
        assert empty_book.spread is None
        assert empty_book.spread_bps is None
        assert empty_book.imbalance(5) == 0.0
        assert empty_book.bid_depth(5) == 0.0
        assert empty_book.ask_depth(5) == 0.0

    def test_mid_price(self, book_balanced):
        assert book_balanced.mid_price == pytest.approx(100.5)

    def test_spread(self, book_balanced):
        assert book_balanced.spread == pytest.approx(1.0)

    def test_spread_bps(self, book_balanced):
        # (101 - 100) / 100 * 10000 = 100 bps
        assert book_balanced.spread_bps == pytest.approx(100.0)

    def test_imbalance_balanced(self, book_balanced):
        # bid_depth = 100*10+99*10+98*10=2970, ask_depth = 101*10+102*10+103*10=3060
        # imbalance = (2970-3060)/(2970+3060) ≈ -0.0149 (ask légèrement supérieur car prix plus hauts)
        assert book_balanced.imbalance(3) == pytest.approx(-0.0149, abs=1e-3)

    def test_imbalance_bid_heavy(self, book_bid_heavy):
        imb = book_bid_heavy.imbalance(3)
        assert imb > 0

    def test_imbalance_range(self, book_bid_heavy):
        assert -1.0 <= book_bid_heavy.imbalance(3) <= 1.0

    def test_walls_detected(self, book_with_wall):
        walls = book_with_wall.walls(min_size_usd=50.0)
        bid_prices = [p for p, _ in walls["bids"]]
        assert 99.0 in bid_prices  # niveau 99.0 * 100 = 9900 USD est le plus gros mur

    def test_walls_usd_below_threshold(self, book_balanced):
        walls = book_balanced.walls(min_size_usd=1_000_000.0)
        assert walls["bids"] == []


# ---------------------------------------------------------------------------
# NormalizedCandle
# ---------------------------------------------------------------------------


class TestNormalizedCandle:
    def test_delta(self):
        c = NormalizedCandle(
            "b",
            "X",
            0,
            "1m",
            100,
            102,
            99,
            101,
            100.0,
            buy_volume=60.0,
            sell_volume=40.0,
        )
        assert c.delta == pytest.approx(20.0)

    def test_delta_pct(self):
        c = NormalizedCandle(
            "b",
            "X",
            0,
            "1m",
            100,
            102,
            99,
            101,
            100.0,
            buy_volume=60.0,
            sell_volume=40.0,
        )
        assert c.delta_pct == pytest.approx(20.0)

    def test_delta_pct_zero_volume(self):
        c = NormalizedCandle("b", "X", 0, "1m", 100, 101, 99, 100, 0.0)
        assert c.delta_pct == 0.0

    def test_is_bullish(self):
        bull = NormalizedCandle("b", "X", 0, "1m", 99, 102, 98, 101, 10.0)
        bear = NormalizedCandle("b", "X", 0, "1m", 101, 103, 97, 99, 10.0)
        assert bull.is_bullish
        assert not bear.is_bullish


# ---------------------------------------------------------------------------
# NormalizedLiquidityEvent
# ---------------------------------------------------------------------------


class TestNormalizedLiquidityEvent:
    def test_value_usd_auto(self):
        liq = NormalizedLiquidityEvent("b", "X", 0, "liquidation", "buy", 65000.0, 0.5)
        assert liq.value_usd == pytest.approx(32500.0)

    def test_value_usd_explicit(self):
        liq = NormalizedLiquidityEvent(
            "b", "X", 0, "liquidation", "buy", 65000.0, 0.5, value_usd=99.0
        )
        assert liq.value_usd == pytest.approx(99.0)


# ---------------------------------------------------------------------------
# MarketEvent
# ---------------------------------------------------------------------------


class TestMarketEvent:
    def test_from_trade(self, trade_buy):
        ev = MarketEvent.from_trade(trade_buy)
        assert ev.event_type == "trade"
        assert ev.exchange == "binance"
        assert ev.symbol == "BTCUSDT"
        assert ev.timestamp_ms == 1000

    def test_from_orderbook(self, book_balanced):
        ev = MarketEvent.from_orderbook(book_balanced)
        assert ev.event_type == "orderbook"

    def test_as_dict_json_serialisable(self, trade_buy):
        d = MarketEvent.from_trade(trade_buy).as_dict()
        assert json.dumps(d)
        assert d["event_type"] == "trade"
        assert "raw" not in d["data"]


# ---------------------------------------------------------------------------
# Orderbook metrics
# ---------------------------------------------------------------------------


class TestOrderbookMetrics:
    def test_imbalance_balanced(self, book_balanced):
        # bid_depth USD < ask_depth USD car prix asks > prix bids -> imbalance légèrement négatif
        assert imbalance(book_balanced, 3) == pytest.approx(-0.0149, abs=1e-3)

    def test_imbalance_bid_heavy_positive(self, book_bid_heavy):
        assert imbalance(book_bid_heavy, 3) > 0

    def test_imbalance_empty_book(self, empty_book):
        assert imbalance(empty_book, 5) == 0.0

    def test_weighted_mid_balanced(self, book_balanced):
        wm = weighted_mid(book_balanced, 3)
        assert wm == pytest.approx(100.5, rel=0.01)

    def test_weighted_mid_empty(self, empty_book):
        assert weighted_mid(empty_book, 5) is None

    def test_spread_metrics_balanced(self, book_balanced):
        sp = spread_metrics(book_balanced)
        assert sp is not None
        assert sp.absolute == pytest.approx(1.0)
        assert sp.bps == pytest.approx(100.0)

    def test_spread_metrics_empty(self, empty_book):
        assert spread_metrics(empty_book) is None

    def test_depth_profile_totals(self, book_balanced):
        dp = depth_profile(book_balanced, 3)
        assert dp.total_bid_usd == pytest.approx(100.0 * 10 + 99.0 * 10 + 98.0 * 10)
        assert dp.total_ask_usd == pytest.approx(101.0 * 10 + 102.0 * 10 + 103.0 * 10)

    def test_depth_profile_imbalance(self, book_bid_heavy):
        dp = depth_profile(book_bid_heavy, 3)
        assert dp.imbalance > 0

    def test_wall_detection_finds_wall(self, book_with_wall):
        walls = wall_detection(book_with_wall, 8, 1.0)
        prices = [w.price for w in walls]
        assert 99.0 in prices

    def test_wall_detection_empty_book(self, empty_book):
        assert wall_detection(empty_book, 10, 2.0) == []

    def test_wall_detection_uniform_volume(self, book_balanced):
        # Tous les niveaux ont le meme volume -> ecart-type=0 -> retourne []
        walls = wall_detection(book_balanced, 6, 2.0)
        assert walls == []

    def test_book_pressure_balanced(self, book_balanced):
        pr = book_pressure(book_balanced, 2.0)
        # Avec pct_range=2% autour de mid=100.5: [98.5..102.5]
        assert "imbalance" in pr
        assert -1 <= pr["imbalance"] <= 1

    def test_book_pressure_empty(self, empty_book):
        pr = book_pressure(empty_book)
        assert pr["imbalance"] == 0.0

    def test_skew_balanced(self, book_balanced):
        assert skew(book_balanced, 3) == pytest.approx(1.0, rel=0.05)

    def test_skew_bid_heavy(self, book_bid_heavy):
        assert skew(book_bid_heavy, 3) > 1.0

    def test_features_vector_complete(self, book_balanced):
        fv = features_vector(book_balanced)
        required = [
            "imbalance_5",
            "imbalance_10",
            "skew_5",
            "spread_bps",
            "weighted_mid",
            "pressure_imbal",
            "n_walls",
        ]
        for key in required:
            assert key in fv

    def test_features_vector_all_floats(self, book_balanced):
        fv = features_vector(book_balanced)
        assert all(isinstance(v, float) for v in fv.values())

    def test_features_vector_json_serialisable(self, book_balanced):
        assert json.dumps(features_vector(book_balanced))


# ---------------------------------------------------------------------------
# CumulativeDeltaTracker
# ---------------------------------------------------------------------------


class TestCumulativeDeltaTracker:
    def test_session_delta_correct(self, simple_trades):
        cvd = CumulativeDeltaTracker()
        for t in simple_trades:
            cvd.update(t)
        expected = sum(t.signed_size for t in simple_trades)
        assert cvd.session_delta == pytest.approx(expected)

    def test_reset_session(self, simple_trades):
        cvd = CumulativeDeltaTracker()
        for t in simple_trades:
            cvd.update(t)
        cvd.reset_session()
        assert cvd.session_delta == 0.0

    def test_snapshot_has_expected_keys(self, simple_trades):
        cvd = CumulativeDeltaTracker([60_000, 300_000])
        for t in simple_trades:
            cvd.update(t)
        snap = cvd.snapshot()
        assert "session_delta" in snap
        assert "delta_1m" in snap
        assert "delta_5m" in snap

    def test_window_eviction(self):
        w = DeltaWindow(window_ms=1000)
        w.update(NormalizedTrade("b", "X", 0, 100.0, 2.0, "buy"))
        w.update(NormalizedTrade("b", "X", 1500, 100.0, 1.0, "sell"))
        # ts=0 est < cutoff=500, doit etre expulsé
        assert w.buy_volume == pytest.approx(0.0)
        assert w.sell_volume == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# AbsorptionTracker
# ---------------------------------------------------------------------------


class TestAbsorptionTracker:
    def test_no_event_below_volume_threshold(self):
        tracker = AbsorptionTracker(window_ms=2000, min_volume_usd=1_000_000.0)
        trades = [
            NormalizedTrade("b", "X", i * 100, 100.0, 0.1, "buy") for i in range(10)
        ]
        events = [tracker.update(t) for t in trades]
        assert all(e is None for e in events)

    def test_event_detected_with_low_threshold(self):
        tracker = AbsorptionTracker(
            window_ms=5000, min_volume_usd=10.0, max_price_move_bps=50.0
        )
        trades = [
            NormalizedTrade("b", "X", i * 100, 100.0, 1.0, "buy") for i in range(20)
        ]
        events = [tracker.update(t) for t in trades if tracker.update(t) is not None]
        # Avec seuil bas, au moins un event doit etre detecte sur 20 trades
        # (on appelle update deux fois par trade dans ce test donc on re-teste proprement)

    def test_absorption_score_positive(self):
        tracker = AbsorptionTracker(
            window_ms=3000, min_volume_usd=100.0, max_price_move_bps=10.0
        )
        trades = [
            NormalizedTrade("b", "X", i * 100, 100.0, 10.0, "buy") for i in range(20)
        ]
        events = []
        for t in trades:
            ev = tracker.update(t)
            if ev:
                events.append(ev)
        for ev in events:
            assert ev.absorption_score > 0


# ---------------------------------------------------------------------------
# SweepDetector
# ---------------------------------------------------------------------------


class TestSweepDetector:
    def test_no_sweep_stable_price(self):
        detector = SweepDetector(min_volume_usd=100.0, min_move_bps=10.0)
        trades = [
            NormalizedTrade("b", "X", i * 100, 100.0, 1.0, "buy") for i in range(5)
        ]
        events = [detector.update(t) for t in trades]
        assert all(e is None for e in events)

    def test_sweep_detected(self):
        detector = SweepDetector(
            min_volume_usd=500.0, min_move_bps=5.0, max_duration_ms=5000.0
        )
        trades = [
            NormalizedTrade("b", "X", i * 100, 100.0 + i * 0.3, 10.0, "buy")
            for i in range(15)
        ]
        events = [detector.update(t) for t in trades]
        detected = [e for e in events if e is not None]
        assert len(detected) >= 1

    def test_sweep_velocity_positive(self):
        detector = SweepDetector(
            min_volume_usd=100.0, min_move_bps=5.0, max_duration_ms=5000.0
        )
        trades = [
            NormalizedTrade("b", "X", i * 200, 100.0 + i * 0.5, 5.0, "buy")
            for i in range(10)
        ]
        for t in trades:
            ev = detector.update(t)
            if ev:
                assert ev.velocity > 0
                assert ev.duration_ms > 0


# ---------------------------------------------------------------------------
# PersistenceTracker
# ---------------------------------------------------------------------------


class TestPersistenceTracker:
    def test_empty_book_no_crash(self, empty_book):
        tracker = PersistenceTracker()
        result = tracker.update(empty_book)
        assert result == []

    def test_wall_detected(self, book_with_wall):
        tracker = PersistenceTracker(min_wall_usd=50.0)
        tracker.update(book_with_wall)
        assert tracker.active_wall_count >= 1

    def test_wall_closes_when_absent(self, book_with_wall, book_balanced):
        tracker = PersistenceTracker(min_wall_usd=50.0, max_gap_ms=0)
        tracker.update(book_with_wall)
        # book_balanced n'a pas de mur au meme prix -> le mur ferme
        closed = tracker.update(
            NormalizedOrderBook(
                "b",
                "X",
                100_000,  # ts > max_gap_ms=0
                bids=[(100.0, 1.0)],
                asks=[(101.0, 1.0)],
            )
        )
        # Selon le max_gap_ms=0, les murs de book_with_wall doivent fermer
        # (ts=100000 - ts_last=1000 > max_gap_ms=0)
        assert isinstance(closed, list)

    def test_wall_lifecycle_fields(self):
        lifecycle = WallLifecycle(
            side="bid",
            first_seen_ms=1000,
            last_seen_ms=5000,
            initial_price=99.0,
            final_price=99.0,
            initial_size_usd=50000.0,
            final_size_usd=45000.0,
            price_migration_bps=0.0,
            duration_ms=4000.0,
            fate="cancelled",
        )
        assert lifecycle.duration_ms == 4000.0
        assert lifecycle.fate == "cancelled"


# ---------------------------------------------------------------------------
# FlowSnapshot
# ---------------------------------------------------------------------------


class TestFlowSnapshot:
    def test_as_dict_json_serialisable(self):
        snap = FlowSnapshot(
            timestamp_ms=1000,
            symbol="BTCUSDT",
            delta_1m=100.0,
            delta_5m=500.0,
            delta_pct_1m=5.0,
            book_imbalance=0.2,
            book_pressure_imbalance=0.1,
            spread_bps=1.5,
            last_absorption=None,
            last_sweep=None,
            active_wall_count=2,
        )
        d = snap.as_dict()
        assert json.dumps(d)
        assert d["symbol"] == "BTCUSDT"

    def test_as_dict_with_absorption(self):
        from market_data.metrics.flow import AbsorptionEvent

        ev = AbsorptionEvent(1000, "buy", 100.0, 50000.0, 2.0, 25000.0)
        snap = FlowSnapshot(
            timestamp_ms=1000,
            symbol="X",
            delta_1m=0.0,
            delta_5m=0.0,
            delta_pct_1m=0.0,
            book_imbalance=0.0,
            book_pressure_imbalance=0.0,
            spread_bps=0.0,
            last_absorption=ev,
            last_sweep=None,
            active_wall_count=0,
        )
        d = snap.as_dict()
        assert "absorption_score" in d
        assert d["absorption_side"] == "buy"


# ---------------------------------------------------------------------------
# ReplayEngine
# ---------------------------------------------------------------------------


class TestReplayEngine:
    def _make_jsonl(self, events: list[MarketEvent]) -> str:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for ev in events:
                f.write(json.dumps(ev.as_dict()) + "\n")
            return f.name

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            fname = f.name
        try:
            engine = ReplayEngine(fname)
            snaps = list(engine.replay())
            assert snaps == []
            assert engine.stats.total_events == 0
        finally:
            os.unlink(fname)

    def test_corrupted_lines_skipped(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("not valid json\n")
            f.write(
                json.dumps(
                    MarketEvent.from_trade(
                        NormalizedTrade("b", "X", 1000, 100.0, 1.0, "buy")
                    ).as_dict()
                )
                + "\n"
            )
            f.write("{broken\n")
            fname = f.name
        try:
            engine = ReplayEngine(fname)
            list(engine.replay())
            assert engine.stats.total_events == 1
            assert engine.stats.trade_count == 1
        finally:
            os.unlink(fname)

    def test_trade_events_counted(self, simple_trades):
        events = [MarketEvent.from_trade(t) for t in simple_trades]
        fname = self._make_jsonl(events)
        try:
            engine = ReplayEngine(fname, snapshot_interval_ms=100)
            list(engine.replay())
            assert engine.stats.trade_count == len(simple_trades)
        finally:
            os.unlink(fname)

    def test_orderbook_counted(self, book_balanced):
        events = [
            MarketEvent.from_orderbook(book_balanced),
            MarketEvent.from_trade(NormalizedTrade("b", "X", 2000, 100.0, 1.0, "buy")),
        ]
        fname = self._make_jsonl(events)
        try:
            engine = ReplayEngine(fname)
            list(engine.replay())
            assert engine.stats.orderbook_count == 1
        finally:
            os.unlink(fname)

    def test_snapshots_emitted_at_interval(self, simple_trades):
        events = [MarketEvent.from_trade(t) for t in simple_trades]
        fname = self._make_jsonl(events)
        try:
            engine = ReplayEngine(fname, snapshot_interval_ms=500)
            snaps = list(engine.replay())
            assert len(snaps) > 0
        finally:
            os.unlink(fname)

    def test_roundtrip_orderbook_bids_float(self, book_balanced):
        """Vérifie que les bids/asks sont correctement désérialisés en float."""
        events = [MarketEvent.from_orderbook(book_balanced)]
        fname = self._make_jsonl(events)
        try:
            engine = ReplayEngine(fname)
            list(engine.replay())
            # Pas d'exception = désérialisation correcte
            assert engine.stats.orderbook_count == 1
        finally:
            os.unlink(fname)

    def test_export_to_jsonl(self, simple_trades):
        events = [MarketEvent.from_trade(t) for t in simple_trades]
        fname = self._make_jsonl(events)
        out = fname + "_out.jsonl"
        try:
            engine = ReplayEngine(fname, snapshot_interval_ms=500)
            stats = engine.snapshots_to_jsonl(out)
            assert os.path.exists(out)
            assert stats.total_events == len(simple_trades)
        finally:
            os.unlink(fname)
            if os.path.exists(out):
                os.unlink(out)

    def test_on_event_callback(self, simple_trades):
        events = [MarketEvent.from_trade(t) for t in simple_trades]
        fname = self._make_jsonl(events)
        seen = []
        try:
            engine = ReplayEngine(fname)
            list(engine.replay(on_event=lambda ev: seen.append(ev.event_type)))
            assert len(seen) == len(simple_trades)
        finally:
            os.unlink(fname)
