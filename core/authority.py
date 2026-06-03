"""
core/authority.py — Governance Kernel.

Point d'accès unique à l'autorité de gouvernance pour le pipeline décisionnel.

Le pipeline ne connaît que cette interface.
Il ne connaît jamais RuntimeStateMachine directement.
Toute la gouvernance peut évoluer (SafeModeRegistry, EmergencyController…)
sans toucher au pipeline.

Usage :
    # Au démarrage (une seule fois) :
    from core.authority import init_authority
    init_authority(runtime_state_machine)

    # Dans le pipeline :
    from core.authority import get_authority
    if not get_authority().can_trade():
        ...  # bloquer
"""

from __future__ import annotations

from observability.json_logger import get_logger
from quant_hedge_ai.runtime.runtime_state_machine import (
    RuntimeStateMachine,
    SystemState,
)

_log = get_logger("core.authority")


class GovernanceKernel:
    """
    Façade exposant les permissions de gouvernance au pipeline décisionnel.

    Règle absolue : le pipeline appelle cette interface, jamais RuntimeStateMachine.
    Cela garantit qu'on peut remplacer toute la gouvernance sans toucher au pipeline.
    """

    def __init__(self, rsm: RuntimeStateMachine) -> None:
        self._rsm = rsm

    def can_trade(self) -> bool:
        """Trading autorisé selon l'état RSM courant."""
        return self._rsm.can_trade

    def can_fetch(self) -> bool:
        """Fetch de données de marché autorisé."""
        return self._rsm.can_fetch_data

    def can_place_order(self) -> bool:
        """Condition stricte : trading autorisé ET hors état RECOVERY."""
        return self._rsm.can_trade and self._rsm.state != SystemState.RECOVERY

    def size_factor(self) -> float:
        """Multiplicateur de taille imposé par l'état RSM (0.0 à 1.0)."""
        return self._rsm.size_factor

    def rsm_state(self) -> str:
        """Nom de l'état RSM courant (string)."""
        return self._rsm.state.value

    def snapshot(self) -> dict:
        """Snapshot complet de la RSM pour observabilité."""
        return self._rsm.snapshot()


# ---------------------------------------------------------------------------
# Singleton module-level
# ---------------------------------------------------------------------------

_kernel: GovernanceKernel | None = None


def init_authority(rsm: RuntimeStateMachine) -> GovernanceKernel:
    """
    Initialise le Governance Kernel.

    À appeler une seule fois au démarrage du processus, après la création
    de RuntimeStateMachine. Toute tentative de get_authority() avant cet
    appel lève RuntimeError.
    """
    global _kernel
    _kernel = GovernanceKernel(rsm)
    _log.info("[Authority] GovernanceKernel initialisé — state=%s", rsm.state.value)
    return _kernel


def get_authority() -> GovernanceKernel:
    """
    Retourne le Governance Kernel actif.

    Lève RuntimeError si init_authority() n'a pas été appelé.
    Dans les tests unitaires hors boucle principale, attraper RuntimeError
    et traiter comme can_trade=True (comportement permissif par défaut).
    """
    if _kernel is None:
        raise RuntimeError(
            "GovernanceKernel non initialisé — appeler init_authority(rsm) "
            "au démarrage avant tout appel au pipeline décisionnel."
        )
    return _kernel


def reset_authority() -> None:
    """Remet le singleton à None. Réservé aux tests."""
    global _kernel
    _kernel = None
