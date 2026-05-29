"""
lifecycle_manager.py — Gestion du cycle de vie des agents (B-02)

Chaque agent est un service gérable individuellement : start, stop, restart, status, health.
Journal append-only signé de tous les événements de lifecycle.
Alerte si > 3 agents en FAILED simultanément.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from cold_start.warmup_signer import sign
from observability.json_logger import get_logger

_log = get_logger("runtime.lifecycle_manager")

_JOURNAL_PATH = Path(
    os.getenv("P10_LIFECYCLE_JOURNAL_PATH", "cache/startup/lifecycle_journal.jsonl")
)
_MAX_SIMULTANEOUS_FAILED = int(os.getenv("P10_MAX_FAILED_AGENTS", "3"))


class AgentStatus(str, Enum):
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass
class AgentRecord:
    agent_id: str
    status: AgentStatus = AgentStatus.STOPPED
    started_at: float = 0.0
    stopped_at: float = 0.0
    restart_count: int = 0
    last_health: dict = field(default_factory=dict)
    _start_fn: Optional[Callable] = field(default=None, repr=False, compare=False)
    _stop_fn: Optional[Callable] = field(default=None, repr=False, compare=False)
    _health_fn: Optional[Callable] = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "started_at": round(self.started_at, 3),
            "stopped_at": round(self.stopped_at, 3),
            "restart_count": self.restart_count,
            "last_health": self.last_health,
        }


class LifecycleManager:
    """
    Orchestre le démarrage, l'arrêt, le redémarrage et le health check des agents.

    Journal signé HMAC append-only : chaque événement (START, STOP, RESTART, FAILED…)
    est enregistré avec signature et timestamp.
    """

    def __init__(self, journal_path: Optional[Path] = None) -> None:
        self._agents: dict[str, AgentRecord] = {}
        self._journal_path = journal_path or _JOURNAL_PATH
        self._journal_path.parent.mkdir(parents=True, exist_ok=True)

    # ── API publique ──────────────────────────────────────────────────────────

    def register(
        self,
        agent_id: str,
        start_fn: Optional[Callable] = None,
        stop_fn: Optional[Callable] = None,
        health_fn: Optional[Callable] = None,
    ) -> None:
        """Enregistre un agent avec ses fonctions de cycle de vie."""
        self._agents[agent_id] = AgentRecord(
            agent_id=agent_id,
            _start_fn=start_fn,
            _stop_fn=stop_fn,
            _health_fn=health_fn,
        )
        self._journal("REGISTERED", agent_id)

    def start(self, agent_id: str) -> bool:
        """Démarre l'agent. Retourne False si déjà RUNNING."""
        rec = self._require(agent_id)
        if rec.status == AgentStatus.RUNNING:
            _log.warning("[Lifecycle] start ignoré — %s est déjà RUNNING", agent_id)
            return False
        try:
            if rec._start_fn:
                rec._start_fn()
            rec.status = AgentStatus.RUNNING
            rec.started_at = time.time()
            self._journal("STARTED", agent_id)
            return True
        except Exception as exc:
            rec.status = AgentStatus.FAILED
            self._journal("START_FAILED", agent_id, error=str(exc))
            _log.error("[Lifecycle] start %s échoué: %s", agent_id, exc)
            self._check_failed_threshold()
            return False

    def stop(self, agent_id: str) -> bool:
        """Arrête l'agent proprement. Retourne False si déjà STOPPED."""
        rec = self._require(agent_id)
        if rec.status == AgentStatus.STOPPED:
            _log.warning("[Lifecycle] stop ignoré — %s est déjà STOPPED", agent_id)
            return False
        try:
            if rec._stop_fn:
                rec._stop_fn()
            rec.status = AgentStatus.STOPPED
            rec.stopped_at = time.time()
            self._journal("STOPPED", agent_id)
            return True
        except Exception as exc:
            rec.status = AgentStatus.DEGRADED
            self._journal("STOP_FAILED", agent_id, error=str(exc))
            _log.error("[Lifecycle] stop %s échoué: %s", agent_id, exc)
            return False

    def restart(self, agent_id: str) -> bool:
        """Arrêt puis démarrage atomique. Incrémente restart_count si réussi."""
        rec = self._require(agent_id)
        self.stop(agent_id)
        ok = self.start(agent_id)
        if ok:
            rec.restart_count += 1
            self._journal("RESTARTED", agent_id, restart_count=rec.restart_count)
        return ok

    def status(self, agent_id: str) -> AgentStatus:
        """Retourne le statut courant d'un agent (UNKNOWN si non enregistré)."""
        return self._agents.get(agent_id, AgentRecord(agent_id=agent_id)).status

    def health(self, agent_id: str) -> dict:
        """
        Lance le health check de l'agent.
        Met à jour last_health et passe à DEGRADED si la fn lève une exception.
        """
        rec = self._require(agent_id)
        if rec._health_fn:
            try:
                result = rec._health_fn()
                rec.last_health = (
                    result if isinstance(result, dict) else {"ok": bool(result)}
                )
            except Exception as exc:
                rec.status = AgentStatus.DEGRADED
                rec.last_health = {"ok": False, "error": str(exc)}
                self._journal("HEALTH_FAILED", agent_id, error=str(exc))
        else:
            rec.last_health = {"ok": rec.status == AgentStatus.RUNNING}
        return rec.last_health

    def all_statuses(self) -> dict[str, str]:
        return {aid: rec.status.value for aid, rec in self._agents.items()}

    def failed_agents(self) -> list[str]:
        return [
            aid for aid, rec in self._agents.items() if rec.status == AgentStatus.FAILED
        ]

    def agent_count(self) -> int:
        return len(self._agents)

    def get_record(self, agent_id: str) -> Optional[AgentRecord]:
        return self._agents.get(agent_id)

    # ── Journal signé ─────────────────────────────────────────────────────────

    def _journal(self, event: str, agent_id: str, **extra: object) -> None:
        entry: dict = {
            "event": event,
            "agent_id": agent_id,
            "ts": round(time.time(), 3),
            **extra,
        }
        entry["signature"] = sign(entry)
        try:
            with open(self._journal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            _log.warning("[Lifecycle] écriture journal échouée: %s", exc)

    # ── Contrôles internes ────────────────────────────────────────────────────

    def _require(self, agent_id: str) -> AgentRecord:
        if agent_id not in self._agents:
            raise KeyError(f"Agent inconnu: '{agent_id}'. Appeler register() d'abord.")
        return self._agents[agent_id]

    def _check_failed_threshold(self) -> None:
        failed = self.failed_agents()
        if len(failed) >= _MAX_SIMULTANEOUS_FAILED:
            _log.critical(
                "[Lifecycle] ALERTE — %d agents en FAILED simultanément: %s",
                len(failed),
                failed,
            )
