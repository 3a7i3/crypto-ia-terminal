"""
Chaos #1 — Exchange offline.

Simule une panne complète de l'exchange (ConnectionError sur tous les appels).
Invariants vérifiés :
  - Aucun ordre fantôme enregistré dans le deduplicator quand l'exchange échoue
  - PositionManager reste cohérent en paper_mode sans exchange
  - L'exception est capturée — pas de crash silencieux vers l'appelant
"""

from __future__ import annotations

import pytest

from quant_hedge_ai.agents.execution.order_deduplicator import OrderDeduplicator
from quant_hedge_ai.agents.execution.position_manager import (
    Position,
    PositionManager,
    PositionSide,
)


class _OfflineExchange:
    """Simule un exchange complètement hors-ligne."""

    def create_order(self, *a, **kw):
        raise ConnectionError("Exchange offline: connection refused")

    def fetch_ticker(self, *a, **kw):
        raise ConnectionError("Exchange offline: connection refused")

    def fetch_balance(self, *a, **kw):
        raise ConnectionError("Exchange offline: connection refused")


def _attempt_order(
    dedup: OrderDeduplicator,
    exchange: _OfflineExchange,
    symbol: str,
    action: str,
    size: float,
) -> bool:
    """
    Tente d'envoyer un ordre.
    Règle : on ne register() dans le deduplicator QUE si l'exchange confirme.
    Retourne True si l'ordre a été accepté, False sinon.
    """
    if dedup.is_duplicate(symbol, action, size):
        return False
    try:
        exchange.create_order(symbol, action, size)
        dedup.register(symbol, action, size)
        return True
    except ConnectionError:
        return False  # NE PAS enregistrer — l'ordre n'a pas abouti


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestExchangeOffline:
    def test_no_phantom_order_on_connection_error(self, dedup):
        """Un ordre qui échoue sur l'exchange ne doit pas polluer le deduplicator."""
        exchange = _OfflineExchange()
        result = _attempt_order(dedup, exchange, "BTC/USDT", "BUY", 0.1)

        assert result is False
        assert not dedup.is_duplicate(
            "BTC/USDT", "BUY", 0.1
        ), "INVARIANT BRISÉ: ordre fantôme enregistré malgré l'échec exchange"

    def test_exchange_error_not_silent(self, dedup):
        """La ConnectionError doit être absorbée par la couche d'exécution."""
        exchange = _OfflineExchange()
        try:
            _attempt_order(dedup, exchange, "ETH/USDT", "SELL", 1.0)
        except ConnectionError:
            pytest.fail(
                "CRASH SILENCIEUX: ConnectionError non capturée dans l'exécution"
            )

    def test_position_manager_stable_without_exchange(self):
        """PositionManager en paper_mode reste stable même sans exchange live."""
        pm = PositionManager(exchange=None, paper_mode=True)
        pos = Position(
            symbol="BTC/USDT",
            side=PositionSide.LONG,
            entry_price=50_000.0,
            size_usd=5_000.0,
            qty=0.1,
            use_atr=False,
        )
        pm.add_position(pos, silent=True)

        open_pos = pm.get_open()
        assert len(open_pos) == 1, "Position doit exister même sans exchange live"
        assert not open_pos[
            0
        ].closed, "Position ne doit pas être auto-fermée sans exchange"

    def test_repeated_offline_attempts_no_accumulation(self, dedup):
        """5 tentatives sur exchange offline → deduplicator reste vide."""
        exchange = _OfflineExchange()
        for _ in range(5):
            _attempt_order(dedup, exchange, "SOL/USDT", "BUY", 10.0)

        assert not dedup.is_duplicate(
            "SOL/USDT", "BUY", 10.0
        ), "INVARIANT BRISÉ: ordre fantôme accumulé après 5 échecs exchange"

    def test_online_after_offline_registers_correctly(self, dedup):
        """Après panne, le premier ordre qui réussit est bien enregistré."""
        exchange = _OfflineExchange()
        _attempt_order(dedup, exchange, "BTC/USDT", "BUY", 0.1)  # échoue

        # Exchange revient online → on enregistre manuellement (simule succès)
        dedup.register("BTC/USDT", "BUY", 0.1)
        assert dedup.is_duplicate(
            "BTC/USDT", "BUY", 0.1
        ), "Ordre confirmé par l'exchange doit être en mémoire de déduplication"

    def test_different_symbols_independent_on_partial_outage(self, dedup):
        """Une panne sur BTC n'impacte pas l'état de déduplication sur ETH."""
        exchange = _OfflineExchange()
        _attempt_order(dedup, exchange, "BTC/USDT", "BUY", 0.1)  # échoue

        # ETH est sur un autre exchange (simulé par register direct)
        dedup.register("ETH/USDT", "BUY", 1.0)
        assert dedup.is_duplicate("ETH/USDT", "BUY", 1.0)
        assert not dedup.is_duplicate("BTC/USDT", "BUY", 0.1)
