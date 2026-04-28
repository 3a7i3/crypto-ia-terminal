"""Tests unitaires — OrderDeduplicator."""

from __future__ import annotations

import time

from quant_hedge_ai.agents.execution.order_deduplicator import OrderDeduplicator


class TestOrderDeduplicator:
    def setup_method(self):
        self.d = OrderDeduplicator(window_seconds=30.0)

    # ── is_duplicate ──────────────────────────────────────────────────────────

    def test_new_order_not_duplicate(self):
        assert not self.d.is_duplicate("BTC/USDT", "BUY", 1.0)

    def test_registered_order_is_duplicate(self):
        self.d.register("BTC/USDT", "BUY", 1.0)
        assert self.d.is_duplicate("BTC/USDT", "BUY", 1.0)

    def test_different_symbol_not_duplicate(self):
        self.d.register("BTC/USDT", "BUY", 1.0)
        assert not self.d.is_duplicate("ETH/USDT", "BUY", 1.0)

    def test_different_action_not_duplicate(self):
        self.d.register("BTC/USDT", "BUY", 1.0)
        assert not self.d.is_duplicate("BTC/USDT", "SELL", 1.0)

    def test_very_different_size_not_duplicate(self):
        self.d.register("BTC/USDT", "BUY", 1.0)
        assert not self.d.is_duplicate("BTC/USDT", "BUY", 9.9)

    def test_similar_size_bucketed_as_duplicate(self):
        # 1.03 et 1.04 → round(...,1) = 1.0, bucket identique
        self.d.register("BTC/USDT", "BUY", 1.03)
        assert self.d.is_duplicate("BTC/USDT", "BUY", 1.04)

    def test_action_case_insensitive(self):
        self.d.register("BTC/USDT", "buy", 1.0)
        assert self.d.is_duplicate("BTC/USDT", "BUY", 1.0)

    # ── expiry ────────────────────────────────────────────────────────────────

    def test_expired_order_not_duplicate(self):
        d = OrderDeduplicator(window_seconds=0.05)
        d.register("BTC/USDT", "BUY", 1.0)
        time.sleep(0.1)
        assert not d.is_duplicate("BTC/USDT", "BUY", 1.0)

    def test_within_window_still_duplicate(self):
        d = OrderDeduplicator(window_seconds=10.0)
        d.register("BTC/USDT", "BUY", 1.0)
        time.sleep(0.05)
        assert d.is_duplicate("BTC/USDT", "BUY", 1.0)

    # ── reset ─────────────────────────────────────────────────────────────────

    def test_reset_clears_all(self):
        self.d.register("BTC/USDT", "BUY", 1.0)
        self.d.register("ETH/USDT", "SELL", 2.0)
        self.d.reset()
        assert not self.d.is_duplicate("BTC/USDT", "BUY", 1.0)
        assert not self.d.is_duplicate("ETH/USDT", "SELL", 2.0)

    # ── eviction ──────────────────────────────────────────────────────────────

    def test_evict_stale_removes_old_entries(self):
        d = OrderDeduplicator(window_seconds=0.05)
        d.register("BTC/USDT", "BUY", 1.0)
        time.sleep(0.15)
        # L'éviction se fait à l'appel de is_duplicate
        d.is_duplicate("ETH/USDT", "BUY", 1.0)
        assert "BTC/USDT|BUY|1.0" not in d._recent

    # ── multiple registrations ────────────────────────────────────────────────

    def test_re_register_refreshes_window(self):
        d = OrderDeduplicator(window_seconds=0.5)
        d.register("BTC/USDT", "BUY", 1.0)
        time.sleep(0.15)
        d.register("BTC/USDT", "BUY", 1.0)  # rafraîchit la fenêtre
        time.sleep(0.15)
        # ~0.15s depuis le dernier register < 0.5s → encore dans fenêtre
        assert d.is_duplicate("BTC/USDT", "BUY", 1.0)

    def test_multiple_symbols_independent(self):
        self.d.register("BTC/USDT", "BUY", 1.0)
        assert not self.d.is_duplicate("ETH/USDT", "BUY", 1.0)
        assert not self.d.is_duplicate("SOL/USDT", "BUY", 1.0)
        assert self.d.is_duplicate("BTC/USDT", "BUY", 1.0)

    # ── logging ───────────────────────────────────────────────────────────────

    def test_duplicate_logs_warning(self, caplog):
        import logging

        self.d.register("BTC/USDT", "BUY", 1.0)
        with caplog.at_level(logging.WARNING):
            self.d.is_duplicate("BTC/USDT", "BUY", 1.0)
        assert "Duplicate" in caplog.text or "duplicate" in caplog.text
