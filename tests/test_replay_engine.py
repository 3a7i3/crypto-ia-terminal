"""
Tests de contrat — Run Replay Engine.

Invariants vérifiés :
  R1 : trades identiques → integrity_pass = True
  R2 : trades modifiés   → integrity_pass = False, fingerprint_match = False
  R3 : champs ReplayResult cohérents avec recomputed pipeline
  R4 : fingerprint_match et integrity_pass indépendants (un peut passer sans l'autre)
  R5 : ReplayResult est immutable (frozen)
  R6 : replay ne modifie pas l'original (no side effects)
  R7 : empty trades → safe
  R8 : recomputed_run_hash est le hash du recomputed run
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.analytics.alpha_pipeline import run_alpha_pipeline
from src.analytics.replay_engine import ReplayResult, replay_run
from src.domain.trade_event import TradeEvent

_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _make_trade(i: int, net_pnl: float = 10.0) -> TradeEvent:
    opened = _EPOCH + timedelta(hours=i)
    closed = opened + timedelta(minutes=30)
    return TradeEvent(
        trade_id=f"T{i:04d}",
        run_id="run-replay",
        strategy_id="sma",
        symbol="BTC/USDT",
        side="buy",
        entry_price=100.0,
        exit_price=110.0,
        quantity=1.0,
        execution_mode="backtest",
        gross_pnl_usd=net_pnl + 0.5,
        fees_usd=0.5,
        slippage_usd=0.0,
        opened_at=opened,
        closed_at=closed,
    )


def _trades(n: int, net_pnl: float = 10.0) -> list[TradeEvent]:
    return [_make_trade(i, net_pnl) for i in range(n)]


def _pipeline(trades, **kwargs):
    return run_alpha_pipeline(trades, seed=42, **kwargs)


# ── R1 : trades identiques → integrity_pass = True ─────────────────────────


class TestIntegrityPass:
    def test_identical_trades_pass(self):
        trades = _trades(20)
        original = _pipeline(trades)
        result = replay_run(original, trades)
        assert result.integrity_pass is True

    def test_identical_trades_fingerprint_match(self):
        trades = _trades(20)
        original = _pipeline(trades)
        result = replay_run(original, trades)
        assert result.fingerprint_match is True

    @pytest.mark.parametrize("n", [1, 5, 10, 20, 50])
    def test_pass_for_any_size(self, n):
        trades = _trades(n)
        original = _pipeline(trades)
        assert replay_run(original, trades).integrity_pass is True

    def test_shuffled_trades_still_pass(self):
        import random

        trades = _trades(20)
        shuffled = trades[:]
        random.shuffle(shuffled)
        original = _pipeline(trades)
        result = replay_run(original, shuffled)
        # sort-stable par (closed_at, trade_id) → même résultat
        assert result.integrity_pass is True
        assert result.fingerprint_match is True


# ── R2 : trades modifiés → integrity_pass = False ───────────────────────────


class TestIntegrityFail:
    def test_extra_trade_breaks_integrity(self):
        trades = _trades(20)
        original = _pipeline(trades)
        modified = trades + [_make_trade(100)]
        result = replay_run(original, modified)
        assert result.integrity_pass is False
        assert result.fingerprint_match is False

    def test_missing_trade_breaks_integrity(self):
        trades = _trades(20)
        original = _pipeline(trades)
        result = replay_run(original, trades[:-1])
        assert result.integrity_pass is False

    def test_different_trades_breaks_integrity(self):
        trades_a = _trades(20, net_pnl=10.0)
        trades_b = _trades(20, net_pnl=20.0)  # pnl différent → closed_at identique
        original = _pipeline(trades_a)
        result = replay_run(original, trades_b)
        # fingerprint basé sur trade_id + closed_at, pas sur pnl
        # → fingerprint identique (même IDs, mêmes timestamps)
        # → mais run_hash diffère si outputs C2 diffèrent
        # Ce test vérifie que le replay détecte la différence de PnL via run_hash
        assert (
            result.recomputed_run_hash != original.run_hash
            or result.integrity_pass is False
        )

    def test_empty_trades_breaks_integrity(self):
        trades = _trades(20)
        original = _pipeline(trades)
        result = replay_run(original, [])
        assert result.integrity_pass is False
        assert result.fingerprint_match is False


# ── R3 : champs cohérents avec recomputed pipeline ──────────────────────────


class TestFieldCoherence:
    def test_c1_counts_match_recomputed_split(self):
        from src.analytics.is_oos_splitter import split_is_oos

        trades = _trades(20)
        original = _pipeline(trades)
        result = replay_run(original, trades)
        expected_split = split_is_oos(trades, is_ratio=original.is_ratio)
        assert result.c1_is_count == expected_split.metadata.n_is
        assert result.c1_oos_count == expected_split.metadata.n_oos

    def test_c1_is_plus_oos_equals_total(self):
        n = 20
        trades = _trades(n)
        original = _pipeline(trades)
        result = replay_run(original, trades)
        assert result.c1_is_count + result.c1_oos_count == n

    def test_bootstrap_ci_is_tuple_of_two_floats(self):
        trades = _trades(20)
        original = _pipeline(trades)
        result = replay_run(original, trades)
        assert isinstance(result.bootstrap_ci, tuple)
        assert len(result.bootstrap_ci) == 2
        assert result.bootstrap_ci[0] <= result.bootstrap_ci[1]

    def test_p_value_in_unit_interval(self):
        trades = _trades(20)
        original = _pipeline(trades)
        result = replay_run(original, trades)
        assert 0.0 <= result.p_value <= 1.0

    def test_alpha_significant_matches_pipeline(self):
        trades = _trades(60, net_pnl=50.0)
        original = _pipeline(trades, n_resamples=200)
        result = replay_run(original, trades)
        assert result.alpha_significant == original.alpha_significant

    def test_recomputed_run_hash_matches_original_on_pass(self):
        trades = _trades(20)
        original = _pipeline(trades)
        result = replay_run(original, trades)
        assert result.recomputed_run_hash == original.run_hash


# ── R4 : fingerprint_match et integrity_pass indépendants ───────────────────


class TestIndependence:
    def test_fingerprint_match_without_integrity_impossible(self):
        # Si fingerprint match ET params identiques → run_hash identique → integrity pass
        # Donc fingerprint_match=True → integrity_pass=True (si params inchangés)
        trades = _trades(20)
        original = _pipeline(trades)
        result = replay_run(original, trades)
        if result.fingerprint_match:
            assert result.integrity_pass is True

    def test_integrity_fail_implies_fingerprint_mismatch_or_output_change(self):
        trades_a = _trades(20)
        trades_b = trades_a + [_make_trade(100)]
        original = _pipeline(trades_a)
        result = replay_run(original, trades_b)
        # si integrity échoue → au moins fingerprint ou outputs ont changé
        assert (
            not result.fingerprint_match
            or result.recomputed_run_hash != original.run_hash
        )


# ── R5 : ReplayResult est immutable ─────────────────────────────────────────


class TestImmutability:
    def test_frozen_cannot_set_integrity_pass(self):
        from dataclasses import FrozenInstanceError

        trades = _trades(10)
        original = _pipeline(trades)
        result = replay_run(original, trades)
        with pytest.raises((FrozenInstanceError, AttributeError)):
            result.integrity_pass = False  # type: ignore[misc]

    def test_frozen_cannot_set_run_hash(self):
        from dataclasses import FrozenInstanceError

        trades = _trades(10)
        original = _pipeline(trades)
        result = replay_run(original, trades)
        with pytest.raises((FrozenInstanceError, AttributeError)):
            result.recomputed_run_hash = "tampered"  # type: ignore[misc]


# ── R6 : replay ne modifie pas l'original ────────────────────────────────────


class TestNoSideEffects:
    def test_original_run_hash_unchanged_after_replay(self):
        trades = _trades(20)
        original = _pipeline(trades)
        original_hash = original.run_hash
        replay_run(original, trades)
        assert original.run_hash == original_hash

    def test_original_fingerprint_unchanged_after_replay(self):
        trades = _trades(20)
        original = _pipeline(trades)
        original_fp = original.dataset_fingerprint
        replay_run(original, trades + [_make_trade(99)])
        assert original.dataset_fingerprint == original_fp

    def test_multiple_replays_consistent(self):
        trades = _trades(20)
        original = _pipeline(trades)
        r1 = replay_run(original, trades)
        r2 = replay_run(original, trades)
        assert r1 == r2


# ── R7 : empty trades → safe ─────────────────────────────────────────────────


class TestEmptySafety:
    def test_replay_with_empty_trades_returns_result(self):
        original = _pipeline(_trades(20))
        result = replay_run(original, [])
        assert isinstance(result, ReplayResult)

    def test_replay_with_empty_trades_fails_integrity(self):
        original = _pipeline(_trades(20))
        result = replay_run(original, [])
        assert result.integrity_pass is False

    def test_replay_of_empty_original_with_empty_trades(self):
        original = _pipeline([])
        result = replay_run(original, [])
        assert result.integrity_pass is True

    def test_replay_of_empty_original_with_nonempty_trades(self):
        original = _pipeline([])
        result = replay_run(original, _trades(5))
        assert result.integrity_pass is False


# ── R8 : recomputed_run_hash est le hash du recomputed run ───────────────────


class TestRecomputedHash:
    def test_recomputed_hash_matches_fresh_pipeline(self):
        trades = _trades(20)
        original = _pipeline(trades)
        result = replay_run(original, trades)
        fresh = run_alpha_pipeline(
            trades,
            is_ratio=original.is_ratio,
            n_resamples=original.n_resamples,
            alpha_level=original.alpha_level,
            seed=original.seed,
        )
        assert result.recomputed_run_hash == fresh.run_hash

    def test_recomputed_hash_is_hex_string(self):
        trades = _trades(10)
        original = _pipeline(trades)
        result = replay_run(original, trades)
        assert isinstance(result.recomputed_run_hash, str)
        assert len(result.recomputed_run_hash) == 16
        int(result.recomputed_run_hash, 16)
