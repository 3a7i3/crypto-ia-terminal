"""Base class pour toutes les règles d'exit."""
from __future__ import annotations
from typing import Optional


class ExitRule:
    def check(self, position: dict, price: float, context: dict | None = None) -> Optional[str]:
        """
        Retourne :
          - None        → continuer à tenir la position
          - str (raison)→ fermer la position
        """
        raise NotImplementedError
