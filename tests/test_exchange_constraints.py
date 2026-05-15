"""
tests/test_exchange_constraints.py — Tests déterministes pour exchange_constraints/.

Couvre : precision_rules, rate_limiter, order_validator, binance_rules, models.
"""

from __future__ import annotations

import threading
import time

import pytest

from exchange_constraints.binance_rules import BINANCE_FUTURES_SYMBOLS, get_symbol_info
from exchange_constraints.models import SymbolInfo, ValidationResult
from exchange_constraints.order_validator import OrderValidator
from exchange_constraints.precision_rules import (
    apply_lot_size,
    apply_min_notional,
    apply_price_filter,
    check_percent_price,
    compute_precision_from_step,
    round_step,
)
from exchange_constraints.rate_limiter import (
    ENDPOINT_WEIGHTS,
    OrderRateLimiter,
    TokenBucket,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def btc_info():
    return get_symbol_info("BTCUSDT")


@pytest.fixture
def eth_info():
    return get_symbol_info("ETHUSDT")


@pytest.fixture
def validator():
    return OrderValidator()


# ---------------------------------------------------------------------------
# round_step
# ---------------------------------------------------------------------------


class TestRoundStep:
    @pytest.mark.parametrize(
        "value,step,expected",
        [
            (0.1234, 0.01, 0.12),
            (0.1299, 0.01, 0.12),
            (0.1300, 0.01, 0.13),
            (50123.7, 10.0, 50120.0),
            (1.0, 1.0, 1.0),
            (0.999, 1.0, 0.0),
            (0.001, 0.001, 0.001),
            (0.0014, 0.001, 0.001),
        ],
    )
    def test_values(self, value, step, expected):
        assert round_step(value, step) == pytest.approx(expected)

    def test_zero_step_raises(self):
        with pytest.raises(ValueError):
            round_step(1.0, 0)

    def test_negative_step_raises(self):
        with pytest.raises(ValueError):
            round_step(1.0, -0.01)


# ---------------------------------------------------------------------------
# compute_precision_from_step
# ---------------------------------------------------------------------------


class TestComputePrecision:
    @pytest.mark.parametrize(
        "step,expected",
        [
            (0.001, 3),
            (0.01, 2),
            (0.1, 1),
            (1.0, 0),
            (10.0, 0),
        ],
    )
    def test_values(self, step, expected):
        assert compute_precision_from_step(step) == expected


# ---------------------------------------------------------------------------
# apply_lot_size
# ---------------------------------------------------------------------------


class TestApplyLotSize:
    def test_rounds_down(self, btc_info):
        # 0.0059 doit donner 0.005 (step=0.001, round vers le bas)
        assert apply_lot_size(0.0059, btc_info) == pytest.approx(0.005)

    def test_clamps_to_max(self, btc_info):
        assert apply_lot_size(2000.0, btc_info) == btc_info.max_qty

    def test_exact_step_unchanged(self, btc_info):
        assert apply_lot_size(0.005, btc_info) == pytest.approx(0.005)

    def test_market_uses_market_rules(self, btc_info):
        result = apply_lot_size(0.005, btc_info, is_market=True)
        assert result == pytest.approx(0.005)


# ---------------------------------------------------------------------------
# apply_price_filter
# ---------------------------------------------------------------------------


class TestApplyPriceFilter:
    def test_rounds_to_tick(self, btc_info):
        # tick_size=0.1 -> 65000.15 -> 65000.1 or 65000.2
        result = apply_price_filter(65000.15, btc_info)
        assert result == pytest.approx(65000.2) or result == pytest.approx(65000.1)

    def test_exact_tick_unchanged(self, btc_info):
        assert apply_price_filter(65000.0, btc_info) == pytest.approx(65000.0)

    def test_zero_price_unchanged(self, btc_info):
        assert apply_price_filter(0.0, btc_info) == 0.0


# ---------------------------------------------------------------------------
# apply_min_notional
# ---------------------------------------------------------------------------


class TestApplyMinNotional:
    def test_above_min_unchanged(self, btc_info):
        # 0.01 BTC @ 65000 = 650 USDT > 5 USDT min
        result = apply_min_notional(0.01, 65000.0, btc_info)
        assert result == pytest.approx(0.01)

    def test_below_min_adjusted_up(self, btc_info):
        # 0.001 BTC @ 1 USDT = 0.001 USDT < 5 USDT min -> doit ajuster
        result = apply_min_notional(0.001, 1.0, btc_info)
        assert result * 1.0 >= btc_info.min_notional

    def test_zero_price_unchanged(self, btc_info):
        result = apply_min_notional(0.001, 0.0, btc_info)
        assert result == pytest.approx(0.001)


# ---------------------------------------------------------------------------
# check_percent_price
# ---------------------------------------------------------------------------


class TestCheckPercentPrice:
    def test_within_bounds(self, btc_info):
        ok, reason = check_percent_price(65000.0, 65000.0, btc_info)
        assert ok and reason == ""

    def test_below_lower_bound(self, btc_info):
        # 65000 * 0.95 = 61750, tester 61749
        ok, reason = check_percent_price(61749.0, 65000.0, btc_info)
        assert not ok
        assert "below" in reason

    def test_above_upper_bound(self, btc_info):
        # 65000 * 1.05 = 68250, tester 68251
        ok, reason = check_percent_price(68251.0, 65000.0, btc_info)
        assert not ok
        assert "above" in reason

    def test_zero_price_passes(self, btc_info):
        ok, _ = check_percent_price(0.0, 65000.0, btc_info)
        assert ok

    def test_zero_mark_passes(self, btc_info):
        ok, _ = check_percent_price(65000.0, 0.0, btc_info)
        assert ok


# ---------------------------------------------------------------------------
# TokenBucket
# ---------------------------------------------------------------------------


class TestTokenBucket:
    def test_allows_up_to_capacity(self):
        bucket = TokenBucket(capacity=5.0, refill_rate=1.0)
        results = [bucket.acquire(1.0)[0] for _ in range(7)]
        assert sum(results) == 5

    def test_refills_over_time(self):
        bucket = TokenBucket(capacity=5.0, refill_rate=10.0)
        for _ in range(5):
            bucket.acquire(1.0)
        time.sleep(0.11)  # 10 tokens/s * 0.1s = 1 token
        ok, _ = bucket.acquire(1.0)
        assert ok

    def test_thread_safe(self):
        bucket = TokenBucket(capacity=10.0, refill_rate=100.0)
        results = []
        lock = threading.Lock()

        def worker():
            ok, _ = bucket.acquire(1.0)
            with lock:
                results.append(ok)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sum(results) == 10

    def test_reset_restores_capacity(self):
        bucket = TokenBucket(capacity=3.0, refill_rate=1.0)
        for _ in range(3):
            bucket.acquire(1.0)
        assert not bucket.acquire(1.0)[0]
        bucket.reset()
        assert bucket.acquire(1.0)[0]

    def test_stats_fill_pct(self):
        bucket = TokenBucket(capacity=4.0, refill_rate=1.0, name="test")
        bucket.acquire(1.0)
        stats = bucket.stats()
        assert stats["fill_pct"] == pytest.approx(75.0)

    def test_invalid_capacity(self):
        with pytest.raises(ValueError):
            TokenBucket(capacity=0, refill_rate=1.0)

    def test_invalid_refill_rate(self):
        with pytest.raises(ValueError):
            TokenBucket(capacity=10.0, refill_rate=0)


# ---------------------------------------------------------------------------
# OrderRateLimiter
# ---------------------------------------------------------------------------


class TestOrderRateLimiter:
    def test_order_limit_enforced(self):
        limiter = OrderRateLimiter(
            order_capacity=5.0,
            order_rate_per_s=5.0,
            weight_capacity=1200.0,
            weight_rate_per_s=20.0,
        )
        results = [limiter.acquire().allowed for _ in range(10)]
        assert sum(results) == 5

    def test_weight_limit_enforced(self):
        limiter = OrderRateLimiter(
            order_capacity=1000.0,
            order_rate_per_s=100.0,
            weight_capacity=10.0,
            weight_rate_per_s=1.0,
        )
        results = [
            limiter.acquire_weight(weight=3.0, is_order=False).allowed for _ in range(5)
        ]
        # 10 / 3 = 3 full acquires
        assert sum(results) == 3

    def test_endpoint_weight_used(self):
        limiter = OrderRateLimiter(
            order_capacity=100.0,
            order_rate_per_s=100.0,
            weight_capacity=50.0,
            weight_rate_per_s=1.0,
        )
        # exchangeInfo = 40 weight
        r1 = limiter.acquire("GET /fapi/v1/exchangeInfo")
        assert r1.allowed
        # Next 40-weight request should fail (only 10 left)
        r2 = limiter.acquire("GET /fapi/v1/exchangeInfo")
        assert not r2.allowed

    def test_stats_structure(self):
        limiter = OrderRateLimiter()
        stats = limiter.stats()
        assert "order_bucket" in stats
        assert "weight_bucket" in stats
        assert stats["order_bucket"]["fill_pct"] == 100.0

    def test_reset_restores_full(self):
        limiter = OrderRateLimiter(
            order_capacity=2.0,
            order_rate_per_s=1.0,
            weight_capacity=10.0,
            weight_rate_per_s=1.0,
        )
        limiter.acquire()
        limiter.acquire()
        assert not limiter.acquire().allowed
        limiter.reset()
        assert limiter.acquire().allowed

    def test_endpoint_weights_constants(self):
        assert ENDPOINT_WEIGHTS["POST /fapi/v1/order"] == 1
        assert ENDPOINT_WEIGHTS["GET /fapi/v1/exchangeInfo"] == 40
        assert ENDPOINT_WEIGHTS["GET /fapi/v1/depth"] == 10


# ---------------------------------------------------------------------------
# OrderValidator — Market orders
# ---------------------------------------------------------------------------


class TestOrderValidatorMarket:
    def test_valid_market_order(self, validator, btc_info):
        r = validator.validate(btc_info, qty=0.01, price=0, order_type="market")
        assert r.is_valid
        assert r.adjusted_size == pytest.approx(0.01)

    def test_qty_zero_rejected(self, validator, btc_info):
        r = validator.validate(btc_info, qty=0.0, price=0, order_type="market")
        assert not r.is_valid
        assert "qty_must_be_positive" in r.rejection_reason

    def test_qty_below_min_rejected(self, validator, btc_info):
        r = validator.validate(btc_info, qty=0.0001, price=0, order_type="market")
        assert not r.is_valid
        assert "min" in r.rejection_reason

    def test_qty_above_max_rejected(self, validator, btc_info):
        r = validator.validate(btc_info, qty=9999.0, price=0, order_type="market")
        assert not r.is_valid
        assert "max" in r.rejection_reason

    def test_inactive_symbol_rejected(self, validator):
        info = SymbolInfo(
            "X", "X", "USDT", 0.01, 0.01, 1000.0, 0.01, 5.0, is_active=False
        )
        r = validator.validate(info, qty=1.0, price=0, order_type="market")
        assert not r.is_valid
        assert r.rejection_reason == "symbol_not_active"

    def test_notional_adjusted_with_ref_price(self, validator, btc_info):
        # 0.001 BTC @ 1 USDT = 0.001 < 5 -> qty doit augmenter
        r = validator.validate(btc_info, qty=0.001, price=1.0, order_type="market")
        assert r.is_valid
        assert r.adjusted_size * 1.0 >= btc_info.min_notional

    def test_result_has_order_type(self, validator, btc_info):
        r = validator.validate(btc_info, qty=0.01, price=0, order_type="market")
        assert r.order_type == "market"


# ---------------------------------------------------------------------------
# OrderValidator — Limit orders
# ---------------------------------------------------------------------------


class TestOrderValidatorLimit:
    def test_valid_limit_order(self, validator, btc_info):
        r = validator.validate(
            btc_info, qty=0.01, price=65000.0, order_type="limit", mark_price=65000.0
        )
        assert r.is_valid

    def test_zero_price_rejected(self, validator, btc_info):
        r = validator.validate(btc_info, qty=0.01, price=0, order_type="limit")
        assert not r.is_valid
        assert "requires_positive_price" in r.rejection_reason

    def test_percent_price_below_rejected(self, validator, btc_info):
        # 61000 < 65000 * 0.95 = 61750
        r = validator.validate(
            btc_info, qty=0.01, price=61000.0, order_type="limit", mark_price=65000.0
        )
        assert not r.is_valid
        assert "below" in r.rejection_reason

    def test_percent_price_above_rejected(self, validator, btc_info):
        # 70000 > 65000 * 1.05 = 68250
        r = validator.validate(
            btc_info, qty=0.01, price=70000.0, order_type="limit", mark_price=65000.0
        )
        assert not r.is_valid
        assert "above" in r.rejection_reason

    def test_no_mark_price_skips_percent_check(self, validator, btc_info):
        r = validator.validate(
            btc_info, qty=0.01, price=55000.0, order_type="limit", mark_price=None
        )
        assert r.is_valid

    def test_price_rounded_to_tick(self, validator, btc_info):
        r = validator.validate(btc_info, qty=0.01, price=65000.15, order_type="limit")
        assert r.is_valid
        assert r.adjusted_price == pytest.approx(
            65000.1
        ) or r.adjusted_price == pytest.approx(65000.2)

    def test_size_was_adjusted_property(self, validator, btc_info):
        r = validator.validate(btc_info, qty=0.0059, price=65000.0, order_type="limit")
        if r.is_valid:
            # 0.0059 -> arrondi a 0.005
            assert r.size_was_adjusted or r.adjusted_size == pytest.approx(0.005)

    def test_size_adjustment_pct(self, validator, btc_info):
        r = validator.validate(btc_info, qty=0.01, price=65000.0, order_type="limit")
        assert r.is_valid
        assert abs(r.size_adjustment_pct) < 0.1  # pas d'ajustement pour 0.01

    def test_unknown_order_type_rejected(self, validator, btc_info):
        r = validator.validate(btc_info, qty=0.01, price=65000.0, order_type="stop")
        assert not r.is_valid
        assert "unknown_order_type" in r.rejection_reason


# ---------------------------------------------------------------------------
# ValidationResult properties
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_accept_factory(self):
        r = ValidationResult.accept("X", 1.0, 100.0, 0.99, 99.9)
        assert r.is_valid
        assert r.size_was_adjusted
        assert r.price_was_adjusted

    def test_reject_factory(self):
        r = ValidationResult.reject("X", "test_reason", 1.0, 100.0)
        assert not r.is_valid
        assert r.rejection_reason == "test_reason"
        assert r.adjusted_size is None

    def test_no_adjustment(self):
        r = ValidationResult.accept("X", 1.0, 100.0, 1.0, 100.0)
        assert not r.size_was_adjusted
        assert not r.price_was_adjusted
        assert r.size_adjustment_pct == 0.0


# ---------------------------------------------------------------------------
# SymbolInfo validation
# ---------------------------------------------------------------------------


class TestSymbolInfo:
    def test_invalid_step_size(self):
        with pytest.raises(ValueError):
            SymbolInfo(
                "X",
                "X",
                "USDT",
                step_size=0,
                min_qty=0.001,
                max_qty=10.0,
                tick_size=0.01,
                min_notional=5.0,
            )

    def test_min_qty_greater_than_max(self):
        with pytest.raises(ValueError):
            SymbolInfo(
                "X",
                "X",
                "USDT",
                step_size=0.001,
                min_qty=10.0,
                max_qty=1.0,
                tick_size=0.01,
                min_notional=5.0,
            )

    def test_invalid_tick_size(self):
        with pytest.raises(ValueError):
            SymbolInfo(
                "X",
                "X",
                "USDT",
                step_size=0.001,
                min_qty=0.001,
                max_qty=1000.0,
                tick_size=0,
                min_notional=5.0,
            )

    def test_invalid_percent_price_down(self):
        with pytest.raises(ValueError):
            SymbolInfo(
                "X",
                "X",
                "USDT",
                step_size=0.001,
                min_qty=0.001,
                max_qty=1000.0,
                tick_size=0.01,
                min_notional=5.0,
                percent_price_down=0.0,
            )


# ---------------------------------------------------------------------------
# Binance rules
# ---------------------------------------------------------------------------


class TestBinanceRules:
    def test_get_known_symbol(self):
        info = get_symbol_info("BTCUSDT")
        assert info.symbol == "BTCUSDT"
        assert info.base_asset == "BTC"

    def test_case_insensitive(self):
        assert get_symbol_info("btcusdt").symbol == "BTCUSDT"

    def test_unknown_symbol_raises(self):
        with pytest.raises(KeyError):
            get_symbol_info("XYZUSDT")

    def test_all_symbols_have_valid_rules(self, validator):
        for sym, info in BINANCE_FUTURES_SYMBOLS.items():
            r = validator.validate(
                info, qty=info.min_qty * 2, price=0.0, order_type="market"
            )
            # Ne doit pas lever d'exception
            assert r is not None

    @pytest.mark.parametrize("symbol", list(BINANCE_FUTURES_SYMBOLS.keys()))
    def test_symbol_leverage(self, symbol):
        info = get_symbol_info(symbol)
        assert info.leverage_max >= 10
        assert info.settlement_asset == "USDT"
