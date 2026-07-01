"""
dip/bootstrap.py — Point d'entrée unique du DIP.

Lance l'observateur central et câble tous les modules D01-D14.
Appelé une seule fois au démarrage du système (ex: depuis advisor_loop.py).

Conforme ADR-0007: ne modifie, intercepte ni retarde aucun DecisionPacket.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_started = False
_start_lock = threading.Lock()


def start_dip() -> None:
    """
    Initialise et démarre le DIP.
    Idempotent: les appels successifs sont ignorés.
    """
    global _started
    with _start_lock:
        if _started:
            return

        from dip.core.observer import DIPObserver
        from dip.modules.audit_trail import get_audit_trail
        from dip.modules.causal_tree import get_causal_tree_engine
        from dip.modules.decision_alert import get_alert_engine
        from dip.modules.decision_graph import get_graph_engine
        from dip.modules.decision_timeline import get_timeline_engine
        from dip.modules.explainability import get_explainability_engine
        from dip.modules.knowledge_base import get_knowledge_base

        observer = DIPObserver.instance()

        # Ordre d'enregistrement = ordre d'exécution dans le pipeline d'observation
        # D01 doit être premier car D02-D08 dépendent du graph
        observer.register(get_graph_engine().on_observation)
        observer.register(get_timeline_engine().on_observation)
        observer.register(get_causal_tree_engine().on_observation)
        observer.register(get_explainability_engine().on_observation)
        observer.register(get_knowledge_base().on_observation)
        observer.register(get_alert_engine().on_observation)

        # Audit trail: log de chaque observation DIP
        audit = get_audit_trail()

        def _audit_obs(obs):
            from dip.modules.audit_trail import ACTION_GRAPH_BUILT

            audit.log(
                module="bootstrap",
                action_type=ACTION_GRAPH_BUILT,
                entity_id=obs.packet_id,
                details={"symbol": obs.symbol, "trade_allowed": obs.trade_allowed},
            )

        observer.register(_audit_obs)

        observer.start()
        _started = True
        logger.info("DIP démarré — %d handlers enregistrés", observer.handler_count)


def stop_dip() -> None:
    global _started
    with _start_lock:
        if not _started:
            return
        from dip.core.observer import DIPObserver

        DIPObserver.instance().stop()
        _started = False
        logger.info("DIP arrêté")


def is_running() -> bool:
    return _started
