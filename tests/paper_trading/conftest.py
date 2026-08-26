"""Fixtures Phase 5 — admission de portefeuille paper (Phase 4.0).

Chaque fixture est nommée et documentée pour être réutilisée par plusieurs
tests. Aucune fixture ne mute d'état runtime hors du simulateur qu'elle
construit.

Portée : contract tests (Phase 4.1), canari historique (Phase 4.6). Les
fixtures d'admission (AdmissionVerdict, causal ledger, shadow) arriveront
avec le commit suivant.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from paper_trading.mexc_simulator import (
    MexcPosition,
    MexcSimulator,
    OrderSide,
)


def _make_position(
    symbol: str,
    side: OrderSide,
    qty_usd: float,
    entry_price: float,
    regime: str,
    personality: str,
    score: int = 70,
    pos_id: str | None = None,
) -> MexcPosition:
    """Construit une MexcPosition minimale pour test.

    Réplique la structure produite par ``_fill_market`` sans passer par le
    thread de monitoring : test-friendly.
    """
    return MexcPosition(
        pos_id=pos_id or f"TEST-{symbol.replace('/', '')}",
        symbol=symbol,
        side=side,
        qty_usd=qty_usd,
        entry_price=entry_price,
        tp_price=entry_price * 1.04,
        sl_price=entry_price * 0.98,
        fee_entry_usd=0.0,
        score=score,
        personality=personality,
        regime=regime,
    )


@pytest.fixture
def mexc_positions_empty() -> MexcSimulator:
    """MexcSimulator neuf avec store paper vide.

    Ne démarre pas le thread background : construit-lift pour tests
    d'adaptateur/contrat uniquement.
    """
    sim = MexcSimulator(mexc_reader=MagicMock(), telegram_fn=lambda _m: None)
    sim._positions.clear()
    return sim


@pytest.fixture
def mexc_positions_historical() -> MexcSimulator:
    """Reconstruit exactement l'état SPX/MET/VIRTUAL de la Phase 1.

    Sources — databases/paper_trades.jsonl (VPS) :
      * SPX/USDT       OPEN 2026-08-26T05:05:59Z  buy  bull_trend  score=73  id=62203B8F-A
      * MET/USDT       OPEN 2026-08-26T06:06:28Z  buy  sideways    score=69  id=39C97484-4
      * VIRTUAL/USDT   OPEN 2026-08-26T06:06:32Z  buy  bull_trend  score=72  id=745C4257-6

    Fenêtre observée avec N=3 : 06:06:32 → 13:06:37 UTC (~7 h).
    Cet état est le canari de régression du bug Phase 1.
    """
    sim = MexcSimulator(mexc_reader=MagicMock(), telegram_fn=lambda _m: None)
    sim._positions.clear()
    for pos in (
        _make_position(
            "SPX/USDT",
            OrderSide.BUY,
            qty_usd=10.0,
            entry_price=0.54217095,
            regime="bull_trend",
            personality="momentum_following",
            score=73,
            pos_id="62203B8F-A",
        ),
        _make_position(
            "MET/USDT",
            OrderSide.BUY,
            qty_usd=10.0,
            entry_price=0.2097048,
            regime="sideways",
            personality="mean_reversion",
            score=69,
            pos_id="39C97484-4",
        ),
        _make_position(
            "VIRTUAL/USDT",
            OrderSide.BUY,
            qty_usd=10.0,
            entry_price=0.76248105,
            regime="bull_trend",
            personality="momentum_following",
            score=72,
            pos_id="745C4257-6",
        ),
    ):
        sim._positions[pos.symbol] = pos
    return sim


# Réexport pour import explicite depuis des tests qui construisent
# des positions ad-hoc (CT-03, CT-10).
__all__ = ["_make_position", "mexc_positions_empty", "mexc_positions_historical"]
