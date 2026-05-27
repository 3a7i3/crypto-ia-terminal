"""
cold_start — Cold Start Protocol (P10 prerequisite)

Garantit que le système refuse d'être dangereux tant qu'il n'est pas prêt.
Objectif : confiance opérationnelle, pas un timer.

Usage :
    from cold_start import ColdStartManager
    mgr = ColdStartManager()
    while not mgr.is_live_ready():
        state = mgr.advance(system_snapshot)
        log.info("[ColdStart] état=%s score=%.2f", state.name, mgr.warmup_score())
"""

from cold_start.cold_start_manager import ColdStartManager
from cold_start.warmup_metrics import WarmupMetrics
from cold_start.warmup_state_machine import WarmupState, WarmupStateMachine

__all__ = [
    "ColdStartManager",
    "WarmupState",
    "WarmupStateMachine",
    "WarmupMetrics",
]
