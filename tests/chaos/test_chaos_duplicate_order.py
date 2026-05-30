"""
Chaos #4 — Duplicate order.

Simule un doublon d'ordre (retry réseau, double-signal, bot loop).
Invariants vérifiés :
  - Le même ordre dans la fenêtre est bloqué
  - Des ordres sur symbole/action/taille différents ne se bloquent pas mutuellement
  - Après expiration de la fenêtre, l'ordre passe à nouveau
  - reset() vide complètement la mémoire de déduplication
"""

from __future__ import annotations

import time

from quant_hedge_ai.agents.execution.order_deduplicator import OrderDeduplicator

# ── Tests ─────────────────────────────────────────────────────────────────────


class TestDuplicateOrder:
    def test_same_order_blocked_within_window(self, dedup):
        """Ordre identique dans la fenêtre → bloqué."""
        dedup.register("BTC/USDT", "BUY", 0.1)
        assert (
            dedup.is_duplicate("BTC/USDT", "BUY", 0.1) is True
        ), "INVARIANT BRISÉ: doublon non détecté"

    def test_different_symbol_not_blocked(self, dedup):
        """Symbole différent → pas de blocage inter-symbole."""
        dedup.register("BTC/USDT", "BUY", 0.1)
        assert dedup.is_duplicate("ETH/USDT", "BUY", 0.1) is False

    def test_different_action_not_blocked(self, dedup):
        """BUY et SELL pour le même symbole sont des ordres distincts."""
        dedup.register("BTC/USDT", "BUY", 0.1)
        assert dedup.is_duplicate("BTC/USDT", "SELL", 0.1) is False

    def test_different_size_bucket_not_blocked(self, dedup):
        """Tailles dans des buckets distincts (arrondi 1 décimale) → indépendants."""
        dedup.register("BTC/USDT", "BUY", 0.1)
        # 0.5 → bucket 0.5 ≠ bucket 0.1
        assert dedup.is_duplicate("BTC/USDT", "BUY", 0.5) is False

    def test_similar_size_same_bucket_blocked(self, dedup):
        """Tailles proches (même bucket 10%) → bloquées ensemble."""
        dedup.register("BTC/USDT", "BUY", 0.10)
        # 0.14 arrondi → 0.1 → même bucket
        assert dedup.is_duplicate("BTC/USDT", "BUY", 0.14) is True

    def test_expired_window_allows_repeat(self):
        """Après expiration de la fenêtre, le même ordre est à nouveau accepté."""
        dedup = OrderDeduplicator(window_seconds=0.1)
        dedup.register("BTC/USDT", "BUY", 0.1)
        assert dedup.is_duplicate("BTC/USDT", "BUY", 0.1) is True

        time.sleep(0.15)
        assert (
            dedup.is_duplicate("BTC/USDT", "BUY", 0.1) is False
        ), "INVARIANT BRISÉ: ordre toujours bloqué après expiration de fenêtre"

    def test_rapid_fire_nine_duplicates_all_blocked(self, dedup):
        """10 ordres identiques rapides → les 9 suivants sont bloqués."""
        dedup.register("SOL/USDT", "BUY", 5.0)
        blocked = sum(1 for _ in range(9) if dedup.is_duplicate("SOL/USDT", "BUY", 5.0))
        assert blocked == 9, f"INVARIANT BRISÉ: {blocked}/9 doublons bloqués"

    def test_reset_clears_all_history(self, dedup):
        """reset() efface la totalité de l'historique de déduplication."""
        dedup.register("BTC/USDT", "BUY", 0.1)
        dedup.register("ETH/USDT", "SELL", 1.0)
        dedup.reset()

        assert dedup.is_duplicate("BTC/USDT", "BUY", 0.1) is False
        assert dedup.is_duplicate("ETH/USDT", "SELL", 1.0) is False

    def test_multi_symbol_independent_windows(self, dedup):
        """La fenêtre de chaque symbole est indépendante."""
        dedup.register("BTC/USDT", "BUY", 0.1)
        dedup.register("ETH/USDT", "BUY", 1.0)
        dedup.register("SOL/USDT", "BUY", 10.0)

        assert dedup.is_duplicate("BTC/USDT", "BUY", 0.1) is True
        assert dedup.is_duplicate("ETH/USDT", "BUY", 1.0) is True
        assert dedup.is_duplicate("SOL/USDT", "BUY", 10.0) is True
        assert dedup.is_duplicate("DOGE/USDT", "BUY", 100.0) is False
