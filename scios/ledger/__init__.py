"""Couche L1 — le ledger d'événements.

Seul plan du système dont le contenu n'est pas reconstructible. Aucun agent
n'y écrit : les événements viennent du runtime, de l'exchange ou d'une
ingestion, jamais d'une inférence.
"""

from scios.ledger.event import Event, EventSource
from scios.ledger.store import EventLedger, LedgerError

__all__ = ["Event", "EventLedger", "EventSource", "LedgerError"]
