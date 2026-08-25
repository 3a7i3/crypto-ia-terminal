"""
trade_analysis.integrations — Adaptateurs de lecture du sidecar LMI.

Ces adaptateurs sont STRICTEMENT en lecture seule : ils lisent
lmi_live_state.json (produit par l'observatoire) et le formatent pour
le dashboard ou le bot Telegram. Aucune boucle WebSocket, aucune
influence sur une decision (ADR-0007).
"""

from trade_analysis.integrations.dashboard_adapter import (
    lmi_events,
    lmi_status,
    lmi_symbol,
    lmi_table,
)
from trade_analysis.integrations.radar_adapter import format_lmi_message

__all__ = [
    "lmi_status",
    "lmi_table",
    "lmi_symbol",
    "lmi_events",
    "format_lmi_message",
]
