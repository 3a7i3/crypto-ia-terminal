"""
Tests de contrat C1 — IS/OOS Splitter.

Invariants Z3 vérifiés comme propriétés exécutables :
  C1-I1 : complétude        — IS ∪ OOS = input
  C1-I2 : disjonction       — IS ∩ OOS = ∅
  C1-I3 : monotonie         — max(IS.closed_at) ≤ min(OOS.closed_at)
  C1-I4 : anti-leakage      — aucun trade OOS n'apparaît dans IS
  C1-I5 : déterminisme      — f(x) = f(x) toujours, même input shufflé
  C1-I6 : ratio proximity   — |n_is/n − 0.6| ≤ 1/n
"""

import random
from datetime import datetime, timedelta, timezone

import pytest

from src.analytics.is_oos_splitter import split_is_oos
from src.domain.trade_event import MarketRegime, TradeEvent

# ── Factory ──────────────────────────────────────────────────────────────────

_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _make_trade(i: int, gross_pnl: float = 10.5) -> TradeEvent:
    opened = _EPOCH + timedelta(hours=i)
    closed = opened + timedelta(minutes=30)
    return TradeEvent(
        trade_id=f"T{i:04d}",
        run_id="run-c1",
        strategy_id="sma",
        symbol="BTC/USDT",
        side="buy",
        entry_price=100.0,
        exit_price=110.0,
        quantity=1.0,
        execution_mode="backtest",
        gross_pnl_usd=gross_pnl,
        fees_usd=0.5,
        slippage_usd=0.0,
        opened_at=opened,
        closed_at=closed,
    )


def _make_n(n: int) -> list[TradeEvent]:
    return [_make_trade(i) for i in range(n)]


# ── C1-I1 : Complétude ──────────────────────────────────────────────────────


class TestCompleteness:
    @pytest.mark.parametrize("n", [2, 5, 10, 18, 100])
    def test_union_equals_input(self, n):
        trades = _make_n(n)
        r = split_is_oos(trades)
        assert set(r.is_trades) | set(r.oos_trades) == set(trades)

    @pytest.mark.parametrize("n", [2, 5, 10, 18, 100])
    def test_total_count_preserved(self, n):
        trades = _make_n(n)
        r = split_is_oos(trades)
        assert len(r.is_trades) + len(r.oos_trades) == n
        assert r.metadata.n_is + r.metadata.n_oos == n

    @pytest.mark.parametrize("n", [2, 5, 10, 18, 100])
    def test_metadata_counts_match_lists(self, n):
        r = split_is_oos(_make_n(n))
        assert r.metadata.n_is == len(r.is_trades)
        assert r.metadata.n_oos == len(r.oos_trades)


# ── C1-I2 : Disjonction ─────────────────────────────────────────────────────


class TestDisjointness:
    @pytest.mark.parametrize("n", [2, 5, 10, 18, 100])
    def test_is_and_oos_are_disjoint(self, n):
        r = split_is_oos(_make_n(n))
        assert set(r.is_trades) & set(r.oos_trades) == set()

    @pytest.mark.parametrize("n", [2, 5, 10, 18, 100])
    def test_trade_ids_are_disjoint(self, n):
        r = split_is_oos(_make_n(n))
        is_ids = {t.trade_id for t in r.is_trades}
        oos_ids = {t.trade_id for t in r.oos_trades}
        assert is_ids & oos_ids == set()


# ── C1-I3 : Monotonie temporelle ────────────────────────────────────────────


class TestTemporalMonotonicity:
    @pytest.mark.parametrize("n", [2, 5, 10, 18, 100])
    def test_max_is_lte_min_oos(self, n):
        r = split_is_oos(_make_n(n))
        if r.is_trades and r.oos_trades:
            max_is = max(t.closed_at for t in r.is_trades)
            min_oos = min(t.closed_at for t in r.oos_trades)
            assert max_is <= min_oos

    def test_cut_timestamp_equals_max_is(self):
        r = split_is_oos(_make_n(18))
        assert r.metadata.cut_timestamp == max(t.closed_at for t in r.is_trades)

    @pytest.mark.parametrize("n", [2, 5, 10, 18])
    def test_oos_trades_closed_at_gte_cut(self, n):
        r = split_is_oos(_make_n(n))
        if r.oos_trades and r.metadata.cut_timestamp:
            for t in r.oos_trades:
                assert t.closed_at >= r.metadata.cut_timestamp


# ── C1-I4 : Anti-leakage identitaire ────────────────────────────────────────


class TestAntiLeakage:
    @pytest.mark.parametrize("n", [2, 5, 10, 18, 100])
    def test_no_oos_id_in_is(self, n):
        r = split_is_oos(_make_n(n))
        is_ids = {t.trade_id for t in r.is_trades}
        for t in r.oos_trades:
            assert t.trade_id not in is_ids

    @pytest.mark.parametrize("n", [2, 5, 10, 18, 100])
    def test_no_is_id_in_oos(self, n):
        r = split_is_oos(_make_n(n))
        oos_ids = {t.trade_id for t in r.oos_trades}
        for t in r.is_trades:
            assert t.trade_id not in oos_ids

    def test_no_future_data_in_is(self):
        # Aucun trade IS ne peut avoir closed_at > cut_timestamp
        r = split_is_oos(_make_n(18))
        cut = r.metadata.cut_timestamp
        for t in r.is_trades:
            assert t.closed_at <= cut


# ── C1-I5 : Déterminisme ────────────────────────────────────────────────────


class TestDeterminism:
    def test_same_input_same_output(self):
        trades = _make_n(18)
        r1 = split_is_oos(trades)
        r2 = split_is_oos(trades)
        assert r1.is_trades == r2.is_trades
        assert r1.oos_trades == r2.oos_trades
        assert r1.metadata == r2.metadata

    def test_shuffled_input_same_split(self):
        trades = _make_n(18)
        shuffled = trades[:]
        random.shuffle(shuffled)
        r1 = split_is_oos(trades)
        r2 = split_is_oos(shuffled)
        assert set(r1.is_trades) == set(r2.is_trades)
        assert set(r1.oos_trades) == set(r2.oos_trades)
        assert r1.metadata.cut_timestamp == r2.metadata.cut_timestamp

    def test_repeated_call_idempotent(self):
        trades = _make_n(10)
        results = [split_is_oos(trades) for _ in range(5)]
        for r in results[1:]:
            assert r.is_trades == results[0].is_trades
            assert r.metadata == results[0].metadata


# ── C1-I6 : Ratio proximity ─────────────────────────────────────────────────


class TestRatioProximity:
    @pytest.mark.parametrize("n", [2, 5, 10, 18, 100])
    def test_is_ratio_within_one_trade_error(self, n):
        r = split_is_oos(_make_n(n))
        actual = r.metadata.n_is / n
        tolerance = 1.0 / n
        assert abs(actual - 0.6) <= tolerance

    @pytest.mark.parametrize("is_ratio", [0.5, 0.6, 0.7, 0.8])
    def test_custom_ratio_respected(self, is_ratio):
        n = 20
        r = split_is_oos(_make_n(n), is_ratio=is_ratio)
        actual = r.metadata.n_is / n
        assert abs(actual - is_ratio) <= 1.0 / n


# ── Edge cases ──────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_list(self):
        r = split_is_oos([])
        assert r.is_trades == []
        assert r.oos_trades == []
        assert r.metadata.n_is == 0
        assert r.metadata.n_oos == 0
        assert r.metadata.cut_timestamp is None

    def test_single_trade_all_in_is(self):
        r = split_is_oos(_make_n(1))
        assert len(r.is_trades) == 1
        assert r.oos_trades == []
        assert r.metadata.n_is == 1

    def test_two_trades_splits_one_one(self):
        r = split_is_oos(_make_n(2))
        assert len(r.is_trades) == 1
        assert len(r.oos_trades) == 1

    def test_is_ratio_one_all_in_is(self):
        r = split_is_oos(_make_n(5), is_ratio=1.0)
        assert len(r.is_trades) == 5
        assert r.oos_trades == []

    def test_invalid_ratio_zero_raises(self):
        with pytest.raises(ValueError, match="is_ratio"):
            split_is_oos(_make_n(5), is_ratio=0.0)

    def test_invalid_ratio_negative_raises(self):
        with pytest.raises(ValueError, match="is_ratio"):
            split_is_oos(_make_n(5), is_ratio=-0.1)

    def test_invalid_ratio_gt_one_raises(self):
        with pytest.raises(ValueError, match="is_ratio"):
            split_is_oos(_make_n(5), is_ratio=1.5)

    def test_is_sorted_ascending(self):
        trades = _make_n(10)
        r = split_is_oos(trades)
        closed_ats = [t.closed_at for t in r.is_trades]
        assert closed_ats == sorted(closed_ats)

    def test_oos_sorted_ascending(self):
        trades = _make_n(10)
        r = split_is_oos(trades)
        closed_ats = [t.closed_at for t in r.oos_trades]
        assert closed_ats == sorted(closed_ats)
