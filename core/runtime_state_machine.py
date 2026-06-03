"""
core/runtime_state_machine.py — Point d'entrée canonique de la machine d'état runtime.

Re-export de l'implémentation canonique dans quant_hedge_ai/runtime/.
Les nouveaux modules importent depuis core.runtime_state_machine.
Les anciens imports depuis quant_hedge_ai.runtime.runtime_state_machine restent valides.

Usage:
    from core.runtime_state_machine import RuntimeStateMachine, SystemState
"""

from quant_hedge_ai.runtime.runtime_state_machine import (  # noqa: F401
    _POLICIES,
    RuntimeStateMachine,
    SystemState,
)

__all__ = ["RuntimeStateMachine", "SystemState", "_POLICIES"]
