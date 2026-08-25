"""
orderbook_observer — Observatoire passif du flux de transactions et orderbook.

Observer strictement passif (ADR-0007, ADR-0018).
Ne produit aucun signal BUY/SELL/SCORE — uniquement des mesures descriptives.
Activé par ORDERBOOK_OBSERVER_ENABLED=true (défaut false).
"""

from __future__ import annotations

__version__ = "0.1.0"
