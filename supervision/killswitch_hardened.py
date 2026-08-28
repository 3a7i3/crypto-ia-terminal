"""
supervision/killswitch_hardened.py — Kill Switch interne durci (SANS interface Telegram).

Constitution 2026-08-28 : aucune commande de contrôle n'est accessible via Telegram.
Toute modification du comportement de la machine doit passer par le VPS (SSH).
Voir docs/architecture/TELEGRAM_BOT_REGISTRY.md.

Ce module conserve uniquement :
  - is_halted() / is_safe_mode() / is_execution_allowed()
  - force_halt(reason)   : halt programmique depuis le code
  - state_snapshot()     : état pour l'observabilité
  - La persistance d'état sur disque (survit aux redémarrages)

Le polling Telegram et toutes les commandes /STOP_ALL /CLOSE_ALL /SAFE_MODE
/RESUME /CONFIRM /CANCEL /STATUS /HELP ont été retirés.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from observability.json_logger import get_logger

_log = get_logger("supervision.killswitch_hardened")


@dataclass
class HardenedKSState:
    halted: bool = False
    safe_mode: bool = False
    halt_reason: str = ""
    halt_time: float = 0.0
    safe_mode_time: float = 0.0
    commands_log: list = field(default_factory=list)
    version: int = 1

    def record(self, cmd: str) -> None:
        self.commands_log.append({"cmd": cmd, "time": time.time()})
        if len(self.commands_log) > 200:
            self.commands_log = self.commands_log[-200:]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "HardenedKSState":
        state = cls()
        state.halted = bool(d.get("halted", False))
        state.safe_mode = bool(d.get("safe_mode", False))
        state.halt_reason = str(d.get("halt_reason", ""))
        state.halt_time = float(d.get("halt_time", 0.0))
        state.safe_mode_time = float(d.get("safe_mode_time", 0.0))
        state.commands_log = list(d.get("commands_log", []))
        return state


class KillSwitchHardened:
    """
    Kill Switch durci avec état persistant — aucune interface Telegram.

    Constitution 2026-08-28 : le contrôle du système n'est jamais exposé via
    Telegram. Ce composant gère uniquement l'état interne et les callbacks
    programmiques. Le halt/resume ne peut être déclenché que depuis le code
    (force_halt/force_resume) ou via SSH sur le VPS.
    """

    def __init__(
        self,
        state_path: Optional[Path] = None,
        on_stop_all: Optional[Callable] = None,
        on_close_all: Optional[Callable] = None,
        on_safe_mode: Optional[Callable] = None,
        on_resume: Optional[Callable] = None,
        require_confirm: bool = True,  # conservé pour compatibilité de signature
    ) -> None:
        self._state_path = state_path or Path("cache/startup/killswitch_state.json")
        self._on_stop_all = on_stop_all
        self._on_close_all = on_close_all
        self._on_safe_mode = on_safe_mode
        self._on_resume = on_resume

        self._lock = threading.Lock()
        self._running = False

        # Charger l'état persistant ou initialiser
        self._state = self._load_state()

    # ── API publique (conservée pour compatibilité advisor_loop) ─────────────

    def start(self) -> None:
        """No-op — le polling Telegram a été retiré (constitution 2026-08-28)."""
        self._running = True
        _log.info("[KSHardened] Démarré en mode interne (aucun polling Telegram)")

    def stop(self) -> None:
        """No-op — conservé pour compatibilité d'interface."""
        self._running = False

    def is_halted(self) -> bool:
        with self._lock:
            return self._state.halted

    def is_safe_mode(self) -> bool:
        with self._lock:
            return self._state.safe_mode

    def is_execution_allowed(self) -> bool:
        """False si halted ou safe_mode."""
        return not self.is_halted() and not self.is_safe_mode()

    def halt_reason(self) -> str:
        with self._lock:
            return self._state.halt_reason

    def is_thread_alive(self) -> bool:
        """Toujours False — aucun thread de polling."""
        return False

    def avg_response_time_ms(self) -> float:
        """Toujours 0 — aucun polling Telegram."""
        return 0.0

    def state_snapshot(self) -> dict:
        with self._lock:
            return {
                "halted": self._state.halted,
                "safe_mode": self._state.safe_mode,
                "halt_reason": self._state.halt_reason,
                "halt_time": self._state.halt_time,
                "commands_count": len(self._state.commands_log),
                "pending_command": "",
                "avg_response_time_ms": 0.0,
            }

    def force_halt(self, reason: str = "halt programmique") -> None:
        """Halt immédiat depuis le code (sans Telegram)."""
        with self._lock:
            self._state.halted = True
            self._state.halt_reason = reason
            self._state.halt_time = time.time()
            self._state.record("FORCE_HALT")
        self._persist_state()
        _log.critical("[KSHardened] FORCE_HALT — %s", reason)
        if self._on_stop_all:
            try:
                self._on_stop_all()
            except Exception as exc:
                _log.error("[KSHardened] on_stop_all error: %s", exc)

    def force_safe_mode(self, reason: str = "safe mode programmique") -> None:
        """Safe mode depuis le code (sans Telegram)."""
        with self._lock:
            self._state.safe_mode = True
            self._state.safe_mode_time = time.time()
            self._state.record("FORCE_SAFE_MODE")
        self._persist_state()
        _log.warning("[KSHardened] FORCE_SAFE_MODE — %s", reason)
        if self._on_safe_mode:
            try:
                self._on_safe_mode()
            except Exception as exc:
                _log.error("[KSHardened] on_safe_mode error: %s", exc)

    def force_resume(self) -> None:
        """Reprise depuis le code (sans Telegram)."""
        with self._lock:
            self._state.halted = False
            self._state.safe_mode = False
            self._state.halt_reason = ""
            self._state.record("FORCE_RESUME")
        self._persist_state()
        _log.info("[KSHardened] FORCE_RESUME")
        if self._on_resume:
            try:
                self._on_resume()
            except Exception as exc:
                _log.error("[KSHardened] on_resume error: %s", exc)

    # ── Persistance d'état ────────────────────────────────────────────────────

    def _persist_state(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                data = self._state.to_dict()
            self._state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            _log.debug("[KSHardened] Erreur persistance: %s", exc)

    def _load_state(self) -> HardenedKSState:
        try:
            if self._state_path.exists():
                data = json.loads(self._state_path.read_text(encoding="utf-8"))
                state = HardenedKSState.from_dict(data)
                _log.info(
                    "[KSHardened] État restauré — halted=%s safe=%s",
                    state.halted,
                    state.safe_mode,
                )
                return state
        except Exception as exc:
            _log.debug("[KSHardened] Chargement état: %s", exc)
        return HardenedKSState()

    @staticmethod
    def _fmt_time(ts: float) -> str:
        import datetime

        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

