"""
telegram_kill_switch.py — Kill Switch interne (SANS interface Telegram).

Constitution 2026-08-28 : aucune commande de contrôle n'est accessible via Telegram.
Toute modification du comportement de la machine doit passer par le VPS (SSH).
Voir docs/architecture/TELEGRAM_BOT_REGISTRY.md.

Ce module conserve uniquement :
  - is_halted()     : True si un halt a été demandé depuis le code
  - is_safe_mode()  : True si le mode observation est actif
  - force_halt()    : halt programmique depuis le code (pas via Telegram)
  - start() / stop(): no-op conservés pour compatibilité d'interface

Le polling Telegram a été retiré. L'interface Telegram du KillSwitch est supprimée.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from observability.json_logger import get_logger

_log = get_logger("kill_switch")


@dataclass
class KillSwitchState:
    halted: bool = False
    safe_mode: bool = False
    halt_reason: str = ""
    halt_time: float = 0.0
    commands_log: list = field(default_factory=list)

    def record(self, cmd: str) -> None:
        self.commands_log.append({"cmd": cmd, "time": time.time()})
        if len(self.commands_log) > 100:
            self.commands_log = self.commands_log[-100:]


class TelegramKillSwitch:
    """
    Kill Switch interne — aucune interface Telegram.

    Constitution 2026-08-28 : le contrôle du système (halt, safe mode, resume)
    n'est jamais exposé via Telegram. Ce composant gère uniquement l'état
    interne et les callbacks programmiques.
    """

    def __init__(
        self,
        on_stop_all: Optional[Callable] = None,
        on_close_all: Optional[Callable] = None,
        on_safe_mode: Optional[Callable] = None,
        on_resume: Optional[Callable] = None,
    ) -> None:
        self._state = KillSwitchState()
        self._lock = threading.Lock()
        self._on_stop_all = on_stop_all
        self._on_close_all = on_close_all
        self._on_safe_mode = on_safe_mode
        self._on_resume = on_resume

    # ── API publique (conservée pour compatibilité advisor_loop) ─────────────

    def start(self) -> None:
        """No-op — le polling Telegram a été retiré (constitution 2026-08-28)."""
        _log.info("[KillSwitch] Démarré en mode interne (aucun polling Telegram)")

    def stop(self) -> None:
        """No-op — conservé pour compatibilité d'interface."""
        pass

    def is_halted(self) -> bool:
        with self._lock:
            return self._state.halted

    def is_safe_mode(self) -> bool:
        with self._lock:
            return self._state.safe_mode

    def state_snapshot(self) -> dict:
        with self._lock:
            return {
                "halted": self._state.halted,
                "safe_mode": self._state.safe_mode,
                "halt_reason": self._state.halt_reason,
                "halt_time": self._state.halt_time,
            }

    def force_halt(self, reason: str = "halt programmique") -> None:
        """Halt immédiat depuis le code (sans Telegram)."""
        with self._lock:
            self._state.halted = True
            self._state.halt_reason = reason
            self._state.halt_time = time.time()
            self._state.record("FORCE_HALT")
        _log.critical("[KillSwitch] FORCE_HALT — %s", reason)
        if self._on_stop_all:
            try:
                self._on_stop_all()
            except Exception as exc:
                _log.error("[KillSwitch] Callback stop_all error: %s", exc)

    def force_resume(self) -> None:
        """Reprise depuis le code (sans Telegram)."""
        with self._lock:
            self._state.halted = False
            self._state.safe_mode = False
            self._state.halt_reason = ""
            self._state.record("FORCE_RESUME")
        _log.info("[KillSwitch] FORCE_RESUME")
        if self._on_resume:
            try:
                self._on_resume()
            except Exception as exc:
                _log.error("[KillSwitch] Callback resume error: %s", exc)
