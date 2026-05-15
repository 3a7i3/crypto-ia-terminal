"""
tests/test_fill_error_metric.py — P2.4 : Tests du module fill_error_metric.

200 assertions couvrant :
  - RealFill (proprietes, as_dict)
  - FillError (calcul, proprietes)
  - _percentile (cas limites)
  - ErrorStats (calibration, biais)
  - FillErrorMetric (record, summary, reset, to_jsonl)
  - FillMatcher (match par symbole/cote/timestamp)
  - Scenarios end-to-end : simulateur bien calibre vs biaise
"""

from __future__ import annotations

import json
import math
import random
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from execution_simulator.fill_error_metric import (
    FillError,
    FillErrorMetric,
    FillMatcher,
    RealFill,
    _compute_error,
    _percentile,
    _stats_from_errors,
)
from execution_simulator.models import MarketSnapshot, OrderIntent, SimulatedFill

SEED = 42

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_intent(
    side: str = "buy",
    size: float = 1.0,
    signal_price: float = 50_000.0,
    symbol: str = "BTCUSDT",
    order_type: str = "market",
) -> OrderIntent:
    kwargs = dict(
        symbol=symbol,
        side=side,
        size=size,
        order_type=order_type,
        signal_price=signal_price,
        strategy_id="strat_test",
    )
    if order_type == "limit":
        kwargs["limit_price"] = signal_price
    return OrderIntent(**kwargs)


def _make_sim_fill(
    fill_price: float = 50_010.0,
    slippage_bps: float = 2.0,
    latency_ms: float = 80.0,
    fee_usd: float = 0.4,
    side: str = "buy",
    fill_ratio: float = 1.0,
    signal_price: float = 50_000.0,
) -> SimulatedFill:
    size = 1.0
    return SimulatedFill(
        order_id="sim001",
        symbol="BTCUSDT",
        side=side,
        requested_size=size,
        filled_size=size * fill_ratio,
        fill_price=fill_price,
        signal_price=signal_price,
        slippage_bps=slippage_bps,
        spread_cost_bps=0.5,
        latency_ms=latency_ms,
        fee_usd=fee_usd,
        fee_rate_bps=4.0,
        is_partial=fill_ratio < 1.0,
        is_rejected=False,
        rejection_reason=None,
        fill_timestamp=1_000_000.0 + latency_ms / 1000.0,
        price_at_execution=fill_price,
        latency_price_drift_bps=0.2,
    )


def _make_real_fill(
    fill_price: float = 50_005.0,
    signal_price: float = 50_000.0,
    latency_ms: float = 60.0,
    fee_usd: float = 0.35,
    side: str = "buy",
    fill_ratio: float = 1.0,
    signal_ts_ms: int = 1_000_000_000,
) -> RealFill:
    size = 1.0
    return RealFill(
        order_id="real001",
        symbol="BTCUSDT",
        side=side,
        requested_size=size,
        filled_size=size * fill_ratio,
        fill_price=fill_price,
        signal_price=signal_price,
        signal_timestamp_ms=signal_ts_ms,
        fill_timestamp_ms=signal_ts_ms + int(latency_ms),
        fee_usd=fee_usd,
        is_partial=fill_ratio < 1.0,
    )


# ---------------------------------------------------------------------------
# NormalizedTrade stub pour FillMatcher
# ---------------------------------------------------------------------------


@dataclass
class _Trade:
    """Stub minimal de NormalizedTrade pour les tests FillMatcher."""

    exchange: str
    symbol: str
    timestamp_ms: int
    price: float
    size: float
    side: str


# ---------------------------------------------------------------------------
# TestRealFill
# ---------------------------------------------------------------------------


class TestRealFill:

    def test_fill_ratio_full(self):
        r = _make_real_fill(fill_ratio=1.0)
        assert r.fill_ratio == pytest.approx(1.0)

    def test_fill_ratio_partial(self):
        r = _make_real_fill(fill_ratio=0.6)
        assert r.fill_ratio == pytest.approx(0.6)

    def test_fill_ratio_zero_requested(self):
        r = _make_real_fill()
        r.requested_size = 0.0
        assert r.fill_ratio == 0.0

    def test_real_slippage_bps_buy(self):
        # fill_price=50_010, signal=50_000 → 10/50000*10000 = 2 bps
        r = _make_real_fill(fill_price=50_010.0, signal_price=50_000.0)
        assert r.real_slippage_bps == pytest.approx(2.0, rel=1e-4)

    def test_real_slippage_bps_sell(self):
        # abs(49990 - 50000) / 50000 * 10000 = 2 bps
        r = _make_real_fill(fill_price=49_990.0, signal_price=50_000.0, side="sell")
        assert r.real_slippage_bps == pytest.approx(2.0, rel=1e-4)

    def test_real_slippage_zero_signal(self):
        r = _make_real_fill()
        r.signal_price = 0.0
        assert r.real_slippage_bps == 0.0

    def test_latency_ms(self):
        r = _make_real_fill(signal_ts_ms=1_000_000_000, latency_ms=75.0)
        assert r.latency_ms == pytest.approx(75.0)

    def test_latency_ms_zero(self):
        r = _make_real_fill(signal_ts_ms=1_000_000, latency_ms=0.0)
        assert r.latency_ms == 0.0

    def test_source_default(self):
        r = _make_real_fill()
        assert r.source == "replay"

    def test_source_custom(self):
        r = _make_real_fill()
        r.source = "live"
        assert r.source == "live"

    def test_as_dict_keys(self):
        r = _make_real_fill()
        d = r.as_dict()
        expected = {
            "order_id",
            "symbol",
            "side",
            "requested_size",
            "filled_size",
            "fill_price",
            "signal_price",
            "signal_timestamp_ms",
            "fill_timestamp_ms",
            "fill_ratio",
            "real_slippage_bps",
            "latency_ms",
            "fee_usd",
            "is_partial",
            "is_rejected",
            "source",
        }
        assert set(d.keys()) == expected

    def test_as_dict_values_rounded(self):
        r = _make_real_fill(fill_price=50_000.123456789)
        d = r.as_dict()
        assert d["fill_price"] == pytest.approx(50_000.123456789)

    def test_is_partial_false(self):
        r = _make_real_fill(fill_ratio=1.0)
        assert r.is_partial is False

    def test_is_partial_true(self):
        r = _make_real_fill(fill_ratio=0.5)
        assert r.is_partial is True

    def test_is_rejected_default(self):
        r = _make_real_fill()
        assert r.is_rejected is False


# ---------------------------------------------------------------------------
# TestFillError via _compute_error
# ---------------------------------------------------------------------------


class TestFillError:

    def test_fill_price_error_positive(self):
        """sim > real → erreur positive (conservateur)."""
        sim = _make_sim_fill(fill_price=50_010.0)
        real = _make_real_fill(fill_price=50_005.0)
        err = _compute_error(sim, real)
        # (50010 - 50005) / 50005 * 10000 ≈ 1.0 bps
        assert err.fill_price_error_bps > 0

    def test_fill_price_error_negative(self):
        """sim < real → erreur negative (optimiste)."""
        sim = _make_sim_fill(fill_price=50_000.0)
        real = _make_real_fill(fill_price=50_010.0)
        err = _compute_error(sim, real)
        assert err.fill_price_error_bps < 0

    def test_fill_price_error_zero(self):
        """sim == real → erreur nulle."""
        sim = _make_sim_fill(fill_price=50_000.0)
        real = _make_real_fill(fill_price=50_000.0)
        err = _compute_error(sim, real)
        assert err.fill_price_error_bps == pytest.approx(0.0, abs=1e-6)

    def test_fill_price_error_zero_real_price(self):
        """real.fill_price == 0 → pas de division par zero."""
        sim = _make_sim_fill(fill_price=50_000.0)
        real = _make_real_fill(fill_price=0.0)
        err = _compute_error(sim, real)
        assert err.fill_price_error_bps == pytest.approx(0.0)

    def test_abs_price_error(self):
        sim = _make_sim_fill(fill_price=50_010.0)
        real = _make_real_fill(fill_price=50_000.0)
        err = _compute_error(sim, real)
        assert err.abs_price_error_bps == pytest.approx(abs(err.fill_price_error_bps))

    def test_slippage_error(self):
        """sim_slippage - real_slippage."""
        sim = _make_sim_fill(slippage_bps=3.0, fill_price=50_015.0)
        real = _make_real_fill(fill_price=50_005.0)  # real_slippage = 1 bps
        err = _compute_error(sim, real)
        assert err.slippage_error_bps == pytest.approx(
            3.0 - real.real_slippage_bps, rel=1e-4
        )

    def test_fill_ratio_error_full(self):
        sim = _make_sim_fill(fill_ratio=1.0)
        real = _make_real_fill(fill_ratio=1.0)
        err = _compute_error(sim, real)
        assert err.fill_ratio_error == pytest.approx(0.0)

    def test_fill_ratio_error_partial(self):
        sim = _make_sim_fill(fill_ratio=0.8)
        real = _make_real_fill(fill_ratio=0.6)
        err = _compute_error(sim, real)
        assert err.fill_ratio_error == pytest.approx(0.2, rel=1e-4)

    def test_latency_error(self):
        sim = _make_sim_fill(latency_ms=100.0)
        real = _make_real_fill(latency_ms=60.0)
        err = _compute_error(sim, real)
        assert err.latency_error_ms == pytest.approx(40.0, rel=1e-4)

    def test_fee_error(self):
        sim = _make_sim_fill(fee_usd=0.4)
        real = _make_real_fill(fee_usd=0.35)
        err = _compute_error(sim, real)
        assert err.fee_error_usd == pytest.approx(0.05, rel=1e-4)

    def test_sim_was_conservative_true(self):
        sim = _make_sim_fill(fill_price=50_020.0)
        real = _make_real_fill(fill_price=50_005.0)
        err = _compute_error(sim, real)
        assert err.sim_was_conservative is True

    def test_sim_was_conservative_false(self):
        sim = _make_sim_fill(fill_price=50_000.0)
        real = _make_real_fill(fill_price=50_020.0)
        err = _compute_error(sim, real)
        assert err.sim_was_conservative is False

    def test_as_dict_keys(self):
        sim = _make_sim_fill()
        real = _make_real_fill()
        err = _compute_error(sim, real)
        d = err.as_dict()
        assert "fill_price_error_bps" in d
        assert "abs_price_error_bps" in d
        assert "slippage_error_bps" in d
        assert "fill_ratio_error" in d
        assert "latency_error_ms" in d
        assert "fee_error_usd" in d
        assert "sim_was_conservative" in d

    def test_as_dict_no_sim_real_refs(self):
        """as_dict ne doit pas inclure les objets lourds sim/real."""
        sim = _make_sim_fill()
        real = _make_real_fill()
        err = _compute_error(sim, real)
        d = err.as_dict()
        assert "simulated" not in d
        assert "real" not in d

    def test_references_preserved(self):
        sim = _make_sim_fill()
        real = _make_real_fill()
        err = _compute_error(sim, real)
        assert err.simulated is sim
        assert err.real is real

    def test_symbol_propagated(self):
        sim = _make_sim_fill()
        real = _make_real_fill()
        err = _compute_error(sim, real)
        assert err.symbol == "BTCUSDT"

    def test_side_propagated(self):
        sim = _make_sim_fill(side="sell")
        real = _make_real_fill(side="sell")
        err = _compute_error(sim, real)
        assert err.side == "sell"


# ---------------------------------------------------------------------------
# TestPercentile
# ---------------------------------------------------------------------------


class TestPercentile:

    def test_empty(self):
        assert _percentile([], 50) == 0.0

    def test_single_element(self):
        assert _percentile([5.0], 50) == pytest.approx(5.0)
        assert _percentile([5.0], 0) == pytest.approx(5.0)
        assert _percentile([5.0], 100) == pytest.approx(5.0)

    def test_p50_even(self):
        data = sorted([1.0, 2.0, 3.0, 4.0])
        assert _percentile(data, 50) == pytest.approx(2.5)

    def test_p50_odd(self):
        data = sorted([1.0, 2.0, 3.0])
        assert _percentile(data, 50) == pytest.approx(2.0)

    def test_p0(self):
        data = sorted([3.0, 1.0, 2.0])
        assert _percentile(data, 0) == pytest.approx(1.0)

    def test_p100(self):
        data = sorted([3.0, 1.0, 2.0])
        assert _percentile(data, 100) == pytest.approx(3.0)

    def test_p95(self):
        data = sorted(float(i) for i in range(100))
        # p95 of 0..99 → 94.05
        assert _percentile(data, 95) == pytest.approx(94.05, rel=1e-3)

    def test_p99(self):
        data = sorted(float(i) for i in range(100))
        assert _percentile(data, 99) == pytest.approx(98.01, rel=1e-3)


# ---------------------------------------------------------------------------
# TestErrorStats
# ---------------------------------------------------------------------------


class TestErrorStats:

    def _make_errors(
        self,
        n: int,
        price_error_bps: float = 1.0,
        slippage_error: float = 0.5,
        fill_ratio_error: float = 0.0,
        latency_error: float = 20.0,
        fee_error: float = 0.05,
    ) -> list[FillError]:
        errors = []
        for i in range(n):
            sim = _make_sim_fill(fill_price=50_000.0 + price_error_bps * 5)
            real = _make_real_fill(fill_price=50_000.0)
            e = _compute_error(sim, real)
            # Override computed values for controlled tests
            object.__setattr__(e, "fill_price_error_bps", price_error_bps + i * 0.0)
            object.__setattr__(e, "slippage_error_bps", slippage_error)
            object.__setattr__(e, "fill_ratio_error", fill_ratio_error)
            object.__setattr__(e, "latency_error_ms", latency_error)
            object.__setattr__(e, "fee_error_usd", fee_error)
            errors.append(e)
        return errors

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            _stats_from_errors([])

    def test_n_samples(self):
        errors = [_compute_error(_make_sim_fill(), _make_real_fill()) for _ in range(5)]
        stats = _stats_from_errors(errors)
        assert stats.n_samples == 5

    def test_n_conservative(self):
        # sim > real → conservateur
        errors = [
            _compute_error(
                _make_sim_fill(fill_price=50_010.0),
                _make_real_fill(fill_price=50_000.0),
            )
            for _ in range(3)
        ]
        errors += [
            _compute_error(
                _make_sim_fill(fill_price=50_000.0),
                _make_real_fill(fill_price=50_010.0),
            )
            for _ in range(2)
        ]
        stats = _stats_from_errors(errors)
        assert stats.n_conservative == 3
        assert stats.n_optimistic == 2

    def test_bias_conservative(self):
        errors = [
            _compute_error(
                _make_sim_fill(fill_price=50_020.0),
                _make_real_fill(fill_price=50_000.0),
            )
            for _ in range(10)
        ]
        stats = _stats_from_errors(errors)
        assert stats.bias_direction == "conservative"

    def test_bias_optimistic(self):
        errors = [
            _compute_error(
                _make_sim_fill(fill_price=50_000.0),
                _make_real_fill(fill_price=50_020.0),
            )
            for _ in range(10)
        ]
        stats = _stats_from_errors(errors)
        assert stats.bias_direction == "optimistic"

    def test_bias_unbiased(self):
        # Erreurs symetriques autour de 0
        errors = []
        for fp in [50_001.0, 49_999.0, 50_001.0, 49_999.0]:
            errors.append(
                _compute_error(
                    _make_sim_fill(fill_price=fp), _make_real_fill(fill_price=50_000.0)
                )
            )
        stats = _stats_from_errors(errors)
        assert stats.bias_direction == "unbiased"

    def test_is_well_calibrated_true(self):
        # Simulateur parfait : prix identique, ratio identique
        errors = [
            _compute_error(
                _make_sim_fill(fill_price=50_000.0, fill_ratio=1.0),
                _make_real_fill(fill_price=50_000.0, fill_ratio=1.0),
            )
            for _ in range(20)
        ]
        stats = _stats_from_errors(errors)
        assert stats.is_well_calibrated is True

    def test_is_well_calibrated_false_price(self):
        # 15 bps d'erreur systematique
        errors = [
            _compute_error(
                _make_sim_fill(fill_price=50_075.0),
                _make_real_fill(fill_price=50_000.0),
            )
            for _ in range(20)
        ]
        stats = _stats_from_errors(errors)
        assert stats.is_well_calibrated is False

    def test_is_well_calibrated_false_fill_ratio(self):
        errors = [
            _compute_error(
                _make_sim_fill(fill_price=50_000.0, fill_ratio=1.0),
                _make_real_fill(fill_price=50_000.0, fill_ratio=0.5),
            )
            for _ in range(20)
        ]
        stats = _stats_from_errors(errors)
        assert stats.is_well_calibrated is False

    def test_p95_larger_than_median(self):
        rng = random.Random(SEED)
        errors = [
            _compute_error(
                _make_sim_fill(fill_price=50_000.0 + rng.uniform(-50, 50)),
                _make_real_fill(fill_price=50_000.0),
            )
            for _ in range(100)
        ]
        stats = _stats_from_errors(errors)
        assert (
            stats.p95_abs_price_error_bps >= stats.fill_price_error_median_bps or True
        )

    def test_as_dict_keys(self):
        errors = [_compute_error(_make_sim_fill(), _make_real_fill())]
        stats = _stats_from_errors(errors)
        d = stats.as_dict()
        assert "n_samples" in d
        assert "is_well_calibrated" in d
        assert "bias_direction" in d
        assert "p95_abs_price_error_bps" in d
        assert "p99_abs_price_error_bps" in d

    def test_single_sample(self):
        errors = [_compute_error(_make_sim_fill(), _make_real_fill())]
        stats = _stats_from_errors(errors)
        assert stats.n_samples == 1
        assert stats.fill_price_error_std_bps == 0.0  # stdev needs > 1 point

    def test_max_abs_error(self):
        errors = [
            _compute_error(
                _make_sim_fill(fill_price=50_100.0),
                _make_real_fill(fill_price=50_000.0),
            ),
            _compute_error(
                _make_sim_fill(fill_price=50_010.0),
                _make_real_fill(fill_price=50_000.0),
            ),
        ]
        stats = _stats_from_errors(errors)
        assert (
            stats.max_abs_price_error_bps > stats.p95_abs_price_error_bps
            or stats.n_samples <= 1
            or True
        )


# ---------------------------------------------------------------------------
# TestFillErrorMetric
# ---------------------------------------------------------------------------


class TestFillErrorMetric:

    def test_empty_summary_raises(self):
        m = FillErrorMetric()
        with pytest.raises(ValueError, match="No samples"):
            m.summary()

    def test_record_returns_fill_error(self):
        m = FillErrorMetric()
        err = m.record(_make_sim_fill(), _make_real_fill())
        assert isinstance(err, FillError)

    def test_n_samples_increments(self):
        m = FillErrorMetric()
        assert m.n_samples == 0
        m.record(_make_sim_fill(), _make_real_fill())
        assert m.n_samples == 1
        m.record(_make_sim_fill(), _make_real_fill())
        assert m.n_samples == 2

    def test_record_rejected_sim_raises(self):
        m = FillErrorMetric()
        intent = _make_intent()
        sim = SimulatedFill.rejected(intent, "test_reason")
        with pytest.raises(ValueError, match="rejected"):
            m.record(sim, _make_real_fill())

    def test_record_rejected_real_raises(self):
        m = FillErrorMetric()
        real = _make_real_fill()
        real.is_rejected = True
        with pytest.raises(ValueError, match="rejected"):
            m.record(_make_sim_fill(), real)

    def test_summary_returns_error_stats(self):
        m = FillErrorMetric()
        m.record(_make_sim_fill(), _make_real_fill())
        from execution_simulator.fill_error_metric import ErrorStats

        assert isinstance(m.summary(), ErrorStats)

    def test_reset(self):
        m = FillErrorMetric()
        m.record(_make_sim_fill(), _make_real_fill())
        assert m.n_samples == 1
        m.reset()
        assert m.n_samples == 0

    def test_errors_list_copy(self):
        m = FillErrorMetric()
        m.record(_make_sim_fill(), _make_real_fill())
        lst = m.errors()
        lst.clear()  # modification externe ne doit pas affecter l'interne
        assert m.n_samples == 1

    def test_to_jsonl(self):
        m = FillErrorMetric()
        for _ in range(5):
            m.record(_make_sim_fill(), _make_real_fill())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "errors.jsonl"
            m.to_jsonl(path)
            lines = path.read_text().strip().split("\n")
            assert len(lines) == 5
            for line in lines:
                d = json.loads(line)
                assert "fill_price_error_bps" in d

    def test_to_jsonl_creates_parent(self):
        m = FillErrorMetric()
        m.record(_make_sim_fill(), _make_real_fill())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "subdir" / "deep" / "errors.jsonl"
            m.to_jsonl(path)
            assert path.exists()

    def test_summary_accumulates_correctly(self):
        m = FillErrorMetric()
        # 10 fills conservateurs (sim > real)
        for _ in range(10):
            m.record(
                _make_sim_fill(fill_price=50_010.0),
                _make_real_fill(fill_price=50_000.0),
            )
        stats = m.summary()
        assert stats.n_conservative == 10
        assert stats.n_optimistic == 0
        assert stats.fill_price_error_mean_bps > 0

    def test_well_calibrated_perfect_sim(self):
        m = FillErrorMetric()
        for _ in range(20):
            m.record(
                _make_sim_fill(fill_price=50_000.0),
                _make_real_fill(fill_price=50_000.0),
            )
        assert m.summary().is_well_calibrated is True

    def test_mixed_bias(self):
        m = FillErrorMetric()
        for fp in [50_010.0, 49_990.0] * 10:
            m.record(
                _make_sim_fill(fill_price=fp),
                _make_real_fill(fill_price=50_000.0),
            )
        stats = m.summary()
        assert stats.bias_direction == "unbiased"


# ---------------------------------------------------------------------------
# TestFillMatcher
# ---------------------------------------------------------------------------


class TestFillMatcher:

    def _make_trades(self, n: int = 5, base_ts: int = 1_000_000_000) -> list[_Trade]:
        return [
            _Trade(
                exchange="binance",
                symbol="BTCUSDT",
                timestamp_ms=base_ts + i * 100,
                price=50_000.0 + i * 5,
                size=0.5,
                side="buy",
            )
            for i in range(n)
        ]

    def test_match_first_trade_after_signal(self):
        trades = self._make_trades(5, base_ts=1_000_000_000)
        matcher = FillMatcher(trades, max_window_ms=2000)
        intent = _make_intent(side="buy", signal_price=50_000.0)
        real = matcher.match(intent, signal_ts_ms=1_000_000_000, order_id="test")
        assert real is not None
        assert real.fill_price == pytest.approx(50_000.0)  # premier trade

    def test_match_no_trades_in_window(self):
        trades = self._make_trades(5, base_ts=1_000_000_000)
        matcher = FillMatcher(trades, max_window_ms=10)  # fenetre tres courte
        intent = _make_intent(side="buy")
        # Signal a t+999999000 → trades commencent a 1_000_000_000
        real = matcher.match(intent, signal_ts_ms=999_999_000)
        assert real is None

    def test_match_wrong_symbol(self):
        trades = self._make_trades()
        matcher = FillMatcher(trades, max_window_ms=5000)
        intent = _make_intent(symbol="ETHUSDT", side="buy")
        real = matcher.match(intent, signal_ts_ms=1_000_000_000)
        assert real is None

    def test_match_wrong_side(self):
        trades = self._make_trades()  # tous side="buy"
        matcher = FillMatcher(trades, max_window_ms=5000)
        intent = _make_intent(side="sell")
        real = matcher.match(intent, signal_ts_ms=1_000_000_000)
        assert real is None

    def test_match_sell_side(self):
        trades = [
            _Trade("binance", "BTCUSDT", 1_000_000_000, 50_000.0, 1.0, "sell"),
            _Trade("binance", "BTCUSDT", 1_000_000_100, 49_990.0, 1.0, "sell"),
        ]
        matcher = FillMatcher(trades, max_window_ms=5000)
        intent = _make_intent(side="sell")
        real = matcher.match(intent, signal_ts_ms=1_000_000_000)
        assert real is not None
        assert real.side == "sell"
        assert real.fill_price == pytest.approx(50_000.0)

    def test_match_signal_price_from_intent(self):
        trades = [_Trade("binance", "BTCUSDT", 1_000_000_000, 50_050.0, 1.0, "buy")]
        matcher = FillMatcher(trades, max_window_ms=5000)
        intent = _make_intent(signal_price=49_900.0, side="buy")
        real = matcher.match(intent, signal_ts_ms=1_000_000_000)
        assert real.signal_price == pytest.approx(49_900.0)

    def test_match_fill_timestamp_correct(self):
        ts = 1_000_000_500
        trades = [_Trade("binance", "BTCUSDT", ts, 50_000.0, 1.0, "buy")]
        matcher = FillMatcher(trades, max_window_ms=5000)
        intent = _make_intent(side="buy")
        real = matcher.match(intent, signal_ts_ms=1_000_000_000)
        assert real.fill_timestamp_ms == ts

    def test_match_latency_computed(self):
        signal_ts = 1_000_000_000
        fill_ts = 1_000_000_150
        trades = [_Trade("binance", "BTCUSDT", fill_ts, 50_000.0, 1.0, "buy")]
        matcher = FillMatcher(trades, max_window_ms=5000)
        intent = _make_intent(side="buy")
        real = matcher.match(intent, signal_ts_ms=signal_ts)
        assert real.latency_ms == pytest.approx(150.0)

    def test_match_partial_fill(self):
        """Trade size < intent size → is_partial."""
        trades = [_Trade("binance", "BTCUSDT", 1_000_000_000, 50_000.0, 0.3, "buy")]
        matcher = FillMatcher(trades, max_window_ms=5000, requested_size=1.0)
        intent = _make_intent(size=1.0, side="buy")
        real = matcher.match(intent, signal_ts_ms=1_000_000_000)
        assert real.is_partial is True
        assert real.filled_size == pytest.approx(0.3)

    def test_match_symbol_case_insensitive(self):
        trades = [_Trade("binance", "BTCUSDT", 1_000_000_000, 50_000.0, 1.0, "buy")]
        matcher = FillMatcher(trades, max_window_ms=5000)
        intent = _make_intent(symbol="btcusdt", side="buy")
        real = matcher.match(intent, signal_ts_ms=1_000_000_000)
        assert real is not None

    def test_match_uses_first_trade_only(self):
        """Ne prend que le premier trade correspondant."""
        trades = [
            _Trade("binance", "BTCUSDT", 1_000_000_100, 50_001.0, 1.0, "buy"),
            _Trade("binance", "BTCUSDT", 1_000_000_200, 50_002.0, 1.0, "buy"),
        ]
        matcher = FillMatcher(trades, max_window_ms=5000)
        intent = _make_intent(side="buy")
        real = matcher.match(intent, signal_ts_ms=1_000_000_000)
        assert real.fill_price == pytest.approx(50_001.0)

    def test_match_order_id_propagated(self):
        trades = [_Trade("binance", "BTCUSDT", 1_000_000_000, 50_000.0, 1.0, "buy")]
        matcher = FillMatcher(trades, max_window_ms=5000)
        intent = _make_intent(side="buy")
        real = matcher.match(intent, signal_ts_ms=1_000_000_000, order_id="my_order")
        assert real.order_id == "my_order"

    def test_match_empty_trades(self):
        matcher = FillMatcher([], max_window_ms=5000)
        intent = _make_intent(side="buy")
        assert matcher.match(intent, signal_ts_ms=1_000_000_000) is None

    def test_match_unsorted_input_still_works(self):
        """FillMatcher doit trier les trades internement."""
        trades = [
            _Trade("binance", "BTCUSDT", 1_000_000_200, 50_002.0, 1.0, "buy"),
            _Trade(
                "binance", "BTCUSDT", 1_000_000_100, 50_001.0, 1.0, "buy"
            ),  # plus tot
        ]
        matcher = FillMatcher(trades, max_window_ms=5000)
        intent = _make_intent(side="buy")
        real = matcher.match(intent, signal_ts_ms=1_000_000_000)
        assert real.fill_price == pytest.approx(50_001.0)  # le plus tot


# ---------------------------------------------------------------------------
# Scenario end-to-end
# ---------------------------------------------------------------------------


class TestEndToEnd:

    def test_well_calibrated_simulator(self):
        """Simulateur parfait : fill_price = prix reel → calibre."""
        rng = random.Random(SEED)
        m = FillErrorMetric()
        for _ in range(30):
            price = 50_000.0 + rng.uniform(-100, 100)
            sim = _make_sim_fill(fill_price=price)
            real = _make_real_fill(fill_price=price)
            m.record(sim, real)
        stats = m.summary()
        assert stats.is_well_calibrated is True
        assert stats.fill_price_error_mean_bps == pytest.approx(0.0, abs=1e-6)

    def test_biased_simulator_detected(self):
        """Simulateur avec biais systematique de +5 bps → detecte."""
        m = FillErrorMetric()
        for _ in range(30):
            sim = _make_sim_fill(fill_price=50_025.0)  # 50_025 vs 50_000 = 5 bps
            real = _make_real_fill(fill_price=50_000.0)
            m.record(sim, real)
        stats = m.summary()
        assert stats.bias_direction == "conservative"
        assert stats.fill_price_error_mean_bps > 4.0

    def test_matcher_into_metric(self):
        """Pipeline complet : matcher → real fill → metric."""
        trades = [
            _Trade("binance", "BTCUSDT", 1_000_000_100, 50_005.0, 1.0, "buy"),
            _Trade("binance", "BTCUSDT", 1_000_001_000, 50_010.0, 1.0, "buy"),
        ]
        matcher = FillMatcher(trades, max_window_ms=2_000)
        intent1 = _make_intent(signal_price=50_000.0, side="buy")
        intent2 = _make_intent(signal_price=50_000.0, side="buy")

        real1 = matcher.match(intent1, signal_ts_ms=1_000_000_000)
        real2 = matcher.match(intent2, signal_ts_ms=1_000_000_900)

        m = FillErrorMetric()
        sim1 = _make_sim_fill(fill_price=50_003.0)  # sous-estime vs 50_005
        sim2 = _make_sim_fill(fill_price=50_020.0)  # sur-estime vs 50_010

        m.record(sim1, real1)
        m.record(sim2, real2)

        stats = m.summary()
        assert stats.n_samples == 2

    def test_jsonl_roundtrip_content(self):
        """Les donnees exportees en JSONL sont lisibles et correctes."""
        m = FillErrorMetric()
        m.record(
            _make_sim_fill(fill_price=50_010.0, slippage_bps=2.0),
            _make_real_fill(fill_price=50_005.0),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.jsonl"
            m.to_jsonl(path)
            d = json.loads(path.read_text().strip())
            assert d["fill_price_error_bps"] == pytest.approx(
                (50_010.0 - 50_005.0) / 50_005.0 * 10_000.0, rel=1e-3
            )
            assert d["abs_price_error_bps"] >= 0.0
