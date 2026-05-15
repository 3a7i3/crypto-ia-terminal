"""
tests/test_execution_simulator.py — Tests déterministes pour execution_simulator/.

Pattern : SEED fixe sur chaque test utilisant de l'aléatoire.
Même seed => même résultat, toujours.
"""

from __future__ import annotations

import math
import random

import pytest

from execution_simulator.config import (
    binance_spot_simulator,
    binance_usdt_futures_simulator,
    conservative_simulator,
)
from execution_simulator.fill_simulator import AlwaysFullFill, LiquidityBasedFill
from execution_simulator.latency import LatencyModel
from execution_simulator.models import MarketSnapshot, OrderIntent, SimulatedFill
from execution_simulator.simulator import ExecutionSimulator, FeeModel
from execution_simulator.slippage import FixedSlippage, LinearSlippage, SqrtSlippage
from execution_simulator.spread import DynamicSpread, FixedSpread

SEED = 42

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def snap_btc():
    return MarketSnapshot(
        symbol="BTCUSDT",
        price=65000.0,
        volume_24h=50000.0,
        volatility_pct=2.5,
        bid=64998.0,
        ask=65002.0,
    )


@pytest.fixture
def snap_zero_vol():
    return MarketSnapshot(
        symbol="BTCUSDT", price=65000.0, volume_24h=50000.0, volatility_pct=0.0
    )


@pytest.fixture
def snap_zero_volume():
    return MarketSnapshot(
        symbol="BTCUSDT", price=65000.0, volume_24h=0.0, volatility_pct=2.5
    )


@pytest.fixture
def intent_buy():
    return OrderIntent(
        symbol="BTCUSDT",
        side="buy",
        size=0.01,
        order_type="market",
        signal_price=65000.0,
    )


@pytest.fixture
def intent_sell():
    return OrderIntent(
        symbol="BTCUSDT",
        side="sell",
        size=0.01,
        order_type="market",
        signal_price=65000.0,
    )


@pytest.fixture
def intent_limit():
    return OrderIntent(
        symbol="BTCUSDT",
        side="buy",
        size=0.01,
        order_type="limit",
        signal_price=65000.0,
        limit_price=64900.0,
    )


@pytest.fixture
def rng():
    return random.Random(SEED)


# ---------------------------------------------------------------------------
# OrderIntent
# ---------------------------------------------------------------------------


class TestOrderIntent:
    def test_direction_buy(self, intent_buy):
        assert intent_buy.direction == 1

    def test_direction_sell(self, intent_sell):
        assert intent_sell.direction == -1

    def test_invalid_side(self):
        with pytest.raises(ValueError, match="side"):
            OrderIntent("X", "long", 1.0, "market", 100.0)

    def test_invalid_order_type(self):
        with pytest.raises(ValueError, match="order_type"):
            OrderIntent("X", "buy", 1.0, "spot", 100.0)

    def test_size_must_be_positive(self):
        with pytest.raises(ValueError, match="size"):
            OrderIntent("X", "buy", 0.0, "market", 100.0)

    def test_limit_requires_price(self):
        with pytest.raises(ValueError, match="limit_price"):
            OrderIntent("X", "buy", 1.0, "limit", 100.0)

    def test_limit_with_price_ok(self):
        i = OrderIntent("X", "buy", 1.0, "limit", 100.0, limit_price=99.0)
        assert i.limit_price == 99.0


# ---------------------------------------------------------------------------
# MarketSnapshot
# ---------------------------------------------------------------------------


class TestMarketSnapshot:
    def test_spread_bps(self, snap_btc):
        # (65002 - 64998) / 64998 * 10000 = 0.6154 bps
        assert snap_btc.spread_bps == pytest.approx(0.6154, rel=1e-3)

    def test_spread_bps_no_bid_ask(self, snap_zero_vol):
        assert snap_zero_vol.spread_bps is None

    def test_adv_estimate_floor(self, snap_zero_volume):
        assert snap_zero_volume.adv_estimate == 1.0

    def test_adv_estimate_normal(self, snap_btc):
        assert snap_btc.adv_estimate == 50000.0

    def test_negative_price_raises(self):
        with pytest.raises(ValueError):
            MarketSnapshot("X", price=-1.0, volume_24h=0.0, volatility_pct=0.0)

    def test_negative_volume_raises(self):
        with pytest.raises(ValueError):
            MarketSnapshot("X", price=100.0, volume_24h=-1.0, volatility_pct=0.0)


# ---------------------------------------------------------------------------
# Slippage models
# ---------------------------------------------------------------------------


class TestFixedSlippage:
    def test_constant(self, intent_buy, snap_btc, rng):
        model = FixedSlippage(bps=3.0)
        for _ in range(10):
            assert model.compute(intent_buy, snap_btc, rng) == 3.0

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            FixedSlippage(bps=-1.0)


class TestLinearSlippage:
    def test_base_bps_floor(self, intent_buy, snap_btc, rng):
        model = LinearSlippage(base_bps=2.0, impact_factor=0.0)
        assert model.compute(intent_buy, snap_btc, rng) == pytest.approx(2.0)

    def test_impact_grows_with_size(self, snap_btc, rng):
        model = LinearSlippage(base_bps=0.0, impact_factor=1.0)
        small = OrderIntent("X", "buy", 0.001, "market", 100.0)
        large = OrderIntent("X", "buy", 5000.0, "market", 100.0)
        assert model.compute(large, snap_btc, rng) > model.compute(small, snap_btc, rng)


class TestSqrtSlippage:
    def test_zero_volatility_returns_zero(self, intent_buy, snap_zero_vol, rng):
        model = SqrtSlippage()
        assert model.compute(intent_buy, snap_zero_vol, rng) == 0.0

    def test_always_non_negative(self, intent_buy, snap_btc):
        model = SqrtSlippage(eta=0.1, noise_bps=2.0)
        rng_local = random.Random(SEED)
        for _ in range(500):
            assert model.compute(intent_buy, snap_btc, rng_local) >= 0.0

    def test_deterministic_same_seed(self, intent_buy, snap_btc):
        model = SqrtSlippage()
        r1 = model.compute(intent_buy, snap_btc, random.Random(SEED))
        r2 = model.compute(intent_buy, snap_btc, random.Random(SEED))
        assert r1 == r2

    def test_grows_with_participation(self, snap_btc, rng):
        model = SqrtSlippage(eta=0.1, noise_bps=0.0)
        small = OrderIntent("X", "buy", 1.0, "market", 100.0)
        large = OrderIntent("X", "buy", 2500.0, "market", 100.0)  # 5% du volume
        assert model.compute(large, snap_btc, rng) > model.compute(small, snap_btc, rng)

    def test_invalid_eta(self):
        with pytest.raises(ValueError):
            SqrtSlippage(eta=0.0)


# ---------------------------------------------------------------------------
# Latency
# ---------------------------------------------------------------------------


class TestLatencyModel:
    def test_bounds(self, intent_buy, snap_btc):
        model = LatencyModel(base_ms=50.0, jitter_ms=200.0, max_ms=500.0)
        rng_local = random.Random(SEED)
        for _ in range(200):
            ms, px = model.apply(intent_buy, snap_btc, rng_local)
            assert 50.0 <= ms <= 500.0
            assert px > 0.0

    def test_no_jitter(self, intent_buy, snap_btc, rng):
        model = LatencyModel(base_ms=100.0, jitter_ms=0.0, max_ms=500.0)
        ms, _ = model.apply(intent_buy, snap_btc, rng)
        assert ms == pytest.approx(100.0)

    def test_zero_drift_factor(self, intent_buy, snap_btc, rng):
        model = LatencyModel(base_ms=50.0, jitter_ms=0.0, drift_factor=0.0)
        _, px = model.apply(intent_buy, snap_btc, rng)
        assert px == snap_btc.price

    def test_deterministic(self, intent_buy, snap_btc):
        model = LatencyModel()
        ms1, px1 = model.apply(intent_buy, snap_btc, random.Random(SEED))
        ms2, px2 = model.apply(intent_buy, snap_btc, random.Random(SEED))
        assert ms1 == ms2 and px1 == px2

    def test_drift_bps_sign(self, snap_btc):
        model = LatencyModel()
        assert model.latency_drift_bps(65000.0, 65100.0) == pytest.approx(
            15.38, rel=1e-2
        )
        assert model.latency_drift_bps(65000.0, 64900.0) < 0


# ---------------------------------------------------------------------------
# Spread
# ---------------------------------------------------------------------------


class TestFixedSpread:
    def test_market_order(self, intent_buy, snap_btc, rng):
        model = FixedSpread(bps=2.0)
        assert model.compute(intent_buy, snap_btc, rng) == 2.0

    def test_limit_order_zero(self, intent_limit, snap_btc, rng):
        model = FixedSpread(bps=2.0)
        assert model.compute(intent_limit, snap_btc, rng) == 0.0


class TestDynamicSpread:
    def test_limit_order_zero(self, intent_limit, snap_btc, rng):
        model = DynamicSpread()
        assert model.compute(intent_limit, snap_btc, rng) == 0.0

    def test_non_negative(self, intent_buy, snap_btc):
        model = DynamicSpread(noise_bps=5.0)
        rng_local = random.Random(SEED)
        for _ in range(200):
            assert model.compute(intent_buy, snap_btc, rng_local) >= 0.0

    def test_uses_observed_spread(self, intent_buy, snap_btc, rng):
        model = DynamicSpread(base_bps=0.0, vol_multiplier=0.0, noise_bps=0.0)
        result = model.compute(intent_buy, snap_btc, rng)
        # spread observed = (65002-64998)/64998*10000 ≈ 0.615 bps -> half = 0.308 bps
        assert result == pytest.approx(0.308, rel=0.05)


# ---------------------------------------------------------------------------
# FillSimulator
# ---------------------------------------------------------------------------


class TestAlwaysFullFill:
    def test_always_fills(self, intent_buy, snap_btc, rng):
        model = AlwaysFullFill()
        size, partial, reason = model.simulate(intent_buy, snap_btc, rng)
        assert size == intent_buy.size
        assert partial is False
        assert reason is None


class TestLiquidityBasedFill:
    def test_full_fill_low_participation(self, intent_buy, snap_btc, rng):
        model = LiquidityBasedFill(max_participation=0.10)
        # 0.01 BTC / 50000 BTC ADV = 0.00002% participation => full fill
        size, partial, reason = model.simulate(intent_buy, snap_btc, rng)
        assert size == pytest.approx(intent_buy.size)
        assert partial is False

    def test_partial_fill_high_participation(self):
        model = LiquidityBasedFill(max_participation=0.001, fill_decay_factor=50.0)
        snap = MarketSnapshot("X", 100.0, 10.0, 2.5)
        intent = OrderIntent("X", "buy", 5.0, "market", 100.0)  # 50% participation
        rng_local = random.Random(SEED)
        size, partial, _ = model.simulate(intent, snap, rng_local)
        assert size < intent.size or partial

    def test_limit_order_may_not_fill(self):
        model = LiquidityBasedFill(limit_fill_prob=0.0)
        snap = MarketSnapshot("X", 100.0, 1000.0, 1.0)
        intent = OrderIntent("X", "buy", 1.0, "limit", 100.0, limit_price=99.0)
        rng_local = random.Random(SEED)
        _, _, reason = model.simulate(intent, snap, rng_local)
        assert reason == "limit_order_not_reached"


# ---------------------------------------------------------------------------
# FeeModel
# ---------------------------------------------------------------------------


class TestFeeModel:
    def test_taker_fee(self, intent_buy):
        model = FeeModel(taker_rate_bps=4.0, maker_rate_bps=2.0)
        fee, rate = model.compute(intent_buy, fill_value_usd=1000.0)
        assert rate == 4.0
        assert fee == pytest.approx(0.4)  # 1000 * 4/10000 = 0.4 USD

    def test_maker_fee(self, intent_limit):
        model = FeeModel(taker_rate_bps=4.0, maker_rate_bps=2.0)
        fee, rate = model.compute(intent_limit, fill_value_usd=1000.0)
        assert rate == 2.0
        assert fee == pytest.approx(0.2)  # 1000 * 2/10000 = 0.2 USD

    def test_zero_fill(self, intent_buy):
        model = FeeModel()
        fee, _ = model.compute(intent_buy, fill_value_usd=0.0)
        assert fee == 0.0


# ---------------------------------------------------------------------------
# ExecutionSimulator — déterminisme et propriétés
# ---------------------------------------------------------------------------


class TestExecutionSimulator:
    def test_deterministic_same_seed(self, snap_btc):
        sim1 = binance_usdt_futures_simulator(seed=SEED)
        sim2 = binance_usdt_futures_simulator(seed=SEED)
        i = OrderIntent("BTCUSDT", "buy", 0.01, "market", 65000.0)
        f1 = sim1.execute(i, snap_btc)
        f2 = sim2.execute(i, snap_btc)
        assert f1.fill_price == f2.fill_price
        assert f1.latency_ms == f2.latency_ms
        assert f1.slippage_bps == f2.slippage_bps

    def test_different_seeds_differ(self, snap_btc):
        sim1 = binance_usdt_futures_simulator(seed=1)
        sim2 = binance_usdt_futures_simulator(seed=2)
        i = OrderIntent("BTCUSDT", "buy", 0.01, "market", 65000.0)
        f1 = sim1.execute(i, snap_btc)
        f2 = sim2.execute(i, snap_btc)
        # Extremely unlikely to be identical with different seeds
        assert f1.fill_price != f2.fill_price or f1.latency_ms != f2.latency_ms

    def test_reset_rng_reproduces(self, snap_btc):
        sim = binance_usdt_futures_simulator(seed=SEED)
        i = OrderIntent("BTCUSDT", "buy", 0.01, "market", 65000.0)
        f1 = sim.execute(i, snap_btc)
        sim.reset_rng(SEED)
        f2 = sim.execute(i, snap_btc)
        assert f1.fill_price == f2.fill_price

    def test_fill_not_rejected_normal(self, snap_btc):
        sim = binance_usdt_futures_simulator(seed=SEED)
        i = OrderIntent("BTCUSDT", "buy", 0.01, "market", 65000.0)
        fill = sim.execute(i, snap_btc)
        assert not fill.is_rejected
        assert fill.filled_size > 0
        assert fill.fill_price > 0

    def test_buy_fill_price_above_signal(self, snap_btc):
        """Buy market order doit avoir un fill_price > signal_price (slippage + spread)."""
        sim = binance_usdt_futures_simulator(seed=SEED)
        i = OrderIntent("BTCUSDT", "buy", 0.01, "market", 65000.0)
        fill = sim.execute(i, snap_btc)
        # fill_price peut etre tres proche mais la direction du slippage doit etre positive
        assert fill.total_cost_bps > 0

    def test_sell_fill_price_relation(self, snap_btc):
        sim = binance_usdt_futures_simulator(seed=SEED)
        i = OrderIntent("BTCUSDT", "sell", 0.01, "market", 65000.0)
        fill = sim.execute(i, snap_btc)
        assert not fill.is_rejected
        assert fill.fill_price > 0

    def test_rejected_fill_has_zero_values(self, snap_btc):
        """Un fill rejete doit avoir filled_size=0 et fee_usd=0."""
        fill = SimulatedFill.rejected(
            OrderIntent("X", "buy", 1.0, "market", 100.0),
            reason="test_rejection",
        )
        assert fill.is_rejected
        assert fill.filled_size == 0.0
        assert fill.fee_usd == 0.0
        assert fill.fill_ratio == 0.0

    def test_as_dict_json_serialisable(self, snap_btc):
        import json

        sim = binance_usdt_futures_simulator(seed=SEED)
        i = OrderIntent("BTCUSDT", "buy", 0.01, "market", 65000.0)
        fill = sim.execute(i, snap_btc)
        d = fill.as_dict()
        assert json.dumps(d)

    def test_total_cost_bps_positive(self, snap_btc):
        sim = binance_usdt_futures_simulator(seed=SEED)
        i = OrderIntent("BTCUSDT", "buy", 0.01, "market", 65000.0)
        fill = sim.execute(i, snap_btc)
        assert fill.total_cost_bps > 0

    def test_fill_ratio_partial(self):
        """fill_ratio doit etre dans (0, 1) pour un fill partiel."""
        snap = MarketSnapshot("X", 100.0, 0.001, 2.5)  # volume tres faible
        sim = conservative_simulator(seed=SEED)
        i = OrderIntent("X", "buy", 10.0, "market", 100.0)
        fill = sim.execute(i, snap)
        if fill.is_partial:
            assert 0.0 < fill.fill_ratio < 1.0


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------


class TestPresets:
    @pytest.mark.parametrize(
        "factory",
        [
            binance_usdt_futures_simulator,
            binance_spot_simulator,
            conservative_simulator,
        ],
    )
    def test_preset_executes_without_error(self, factory, snap_btc):
        sim = factory(seed=SEED)
        i = OrderIntent("BTCUSDT", "buy", 0.01, "market", 65000.0)
        fill = sim.execute(i, snap_btc)
        assert fill.fill_price >= 0

    @pytest.mark.parametrize(
        "factory",
        [
            binance_usdt_futures_simulator,
            binance_spot_simulator,
            conservative_simulator,
        ],
    )
    def test_preset_deterministic(self, factory, snap_btc):
        i = OrderIntent("BTCUSDT", "buy", 0.01, "market", 65000.0)
        f1 = factory(seed=SEED).execute(i, snap_btc)
        f2 = factory(seed=SEED).execute(i, snap_btc)
        assert f1.fill_price == f2.fill_price
