"""
supervision/killswitch_hardened.py — E-04 Telegram KillSwitch Redundancy

Kill Switch durci : local + Telegram, acknowledgement, état persistant.

Garanties :
  - Thread daemon indépendant (fonctionne même si advisor_loop est bloqué)
  - Acknowledgement Telegram : chaque commande reçoit un accusé de réception
  - État persistant sur disque (survit aux crashs et redémarrages)
  - Double confirmation pour les commandes destructives (STOP_ALL, CLOSE_ALL)
  - Mesure du temps de réponse (objectif : < 3s de la commande à l'ack)
  - Redondance locale : force_halt() programmable depuis le code

Commandes Telegram supportées :
  /STOP_ALL      → halt immédiat (confirmation requise dans les 30s)
  /CLOSE_ALL     → fermeture positions + halt (confirmation requise)
  /SAFE_MODE     → mode observation seule
  /RESUME        → reprise normale
  /STATUS        → état complet + temps de réponse watchdog
  /CONFIRM       → confirme la commande destructive en attente
  /CANCEL        → annule la commande en attente
  /HELP          → aide

Usage :
    ks = KillSwitchHardened(state_path=Path("cache/startup/killswitch_state.json"))
    ks.start()               # démarre le polling daemon
    ks.is_halted()           # True si STOP_ALL actif
    ks.force_halt("reason")  # halt programmique (sans Telegram)
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

import requests

from observability.json_logger import get_logger

_log = get_logger("supervision.killswitch_hardened")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
POLL_INTERVAL = 3
_CONFIRM_TIMEOUT_S = 30.0  # délai pour confirmer une commande destructive


@dataclass
class HardenedKSState:
    halted: bool = False
    safe_mode: bool = False
    halt_reason: str = ""
    halt_time: float = 0.0
    safe_mode_time: float = 0.0
    commands_log: list = field(default_factory=list)
    pending_command: str = ""  # commande en attente de confirmation
    pending_command_ts: float = 0.0  # timestamp de la commande en attente
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
        state.pending_command = str(d.get("pending_command", ""))
        state.pending_command_ts = float(d.get("pending_command_ts", 0.0))
        return state


class KillSwitchHardened:
    """
    Kill Switch durci avec acknowledgement, état persistant et thread daemon indépendant.
    """

    DESTRUCTIVE_COMMANDS = {"/STOP_ALL", "/CLOSE_ALL"}
    ALL_COMMANDS = {
        "/STOP_ALL",
        "/CLOSE_ALL",
        "/SAFE_MODE",
        "/RESUME",
        "/STATUS",
        "/CONFIRM",
        "/CANCEL",
        "/HELP",
    }

    def __init__(
        self,
        state_path: Optional[Path] = None,
        on_stop_all: Optional[Callable] = None,
        on_close_all: Optional[Callable] = None,
        on_safe_mode: Optional[Callable] = None,
        on_resume: Optional[Callable] = None,
        require_confirm: bool = True,  # confirmation pour commandes destructives
    ) -> None:
        self._state_path = state_path or Path("cache/startup/killswitch_state.json")
        self._on_stop_all = on_stop_all
        self._on_close_all = on_close_all
        self._on_safe_mode = on_safe_mode
        self._on_resume = on_resume
        self._require_confirm = require_confirm

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_update_id: int = 0
        self._response_times: list[float] = []  # mesures de temps de réponse

        # Charger l'état persistant ou initialiser
        self._state = self._load_state()

    # ── API publique ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Démarre le polling Telegram en daemon thread."""
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
            _log.warning("[KSHardened] Token/ChatID manquants — kill switch désactivé")
            return
        with self._lock:
            if self._running:
                return
            self._running = True

        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="KillSwitchHardened",
        )
        self._thread.start()
        _log.info("[KSHardened] Polling Telegram démarré (daemon=True)")
        self._send_async(
            "Kill Switch Hardened actif.\n"
            "Commandes: /STOP_ALL /CLOSE_ALL /SAFE_MODE /RESUME /STATUS /HELP\n"
            f"Confirmation requise: {'OUI' if self._require_confirm else 'NON'}"
        )

    def stop(self) -> None:
        with self._lock:
            self._running = False
        _log.info("[KSHardened] Arrêté")

    def is_halted(self) -> bool:
        with self._lock:
            return self._state.halted

    def is_safe_mode(self) -> bool:
        with self._lock:
            return self._state.safe_mode

    def is_execution_allowed(self) -> bool:
        """Compatibilité API legacy — False si halted ou safe_mode."""
        return not self.is_halted() and not self.is_safe_mode()

    def halt_reason(self) -> str:
        with self._lock:
            return self._state.halt_reason

    def force_halt(self, reason: str = "halt programmique") -> None:
        """Halt immédiat sans Telegram (depuis le code)."""
        with self._lock:
            self._state.halted = True
            self._state.halt_reason = reason
            self._state.halt_time = time.time()
            self._state.record("FORCE_HALT")
        self._persist_state()
        _log.critical("[KSHardened] FORCE_HALT — %s", reason)
        self._send_async(f"[FORCE HALT] {reason}")

    def state_snapshot(self) -> dict:
        with self._lock:
            return {
                "halted": self._state.halted,
                "safe_mode": self._state.safe_mode,
                "halt_reason": self._state.halt_reason,
                "halt_time": self._state.halt_time,
                "commands_count": len(self._state.commands_log),
                "pending_command": self._state.pending_command,
                "avg_response_time_ms": self._avg_response_time_ms(),
            }

    def is_thread_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def avg_response_time_ms(self) -> float:
        with self._lock:
            return self._avg_response_time_ms()

    # ── Polling Telegram ──────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        _log.info("[KSHardened] Boucle polling démarrée")
        while self._running:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._handle_update(update)
                # Expirer les confirmations en attente
                self._expire_pending_confirm()
            except Exception as exc:
                _log.debug("[KSHardened] Erreur polling: %s", exc)
            time.sleep(POLL_INTERVAL)

    def _get_updates(self) -> list:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        params = {"offset": self._last_update_id + 1, "timeout": 2}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        updates = data.get("result", [])
        if updates:
            self._last_update_id = updates[-1]["update_id"]
        return updates

    def _handle_update(self, update: dict) -> None:
        msg = update.get("message", {})
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = msg.get("text", "").strip()
        received_at = time.time()

        if chat_id != str(TELEGRAM_CHAT):
            return

        cmd = text.upper().split()[0] if text else ""
        if cmd not in {c.upper() for c in self.ALL_COMMANDS}:
            return

        _log.info("[KSHardened] Commande reçue: %s", cmd)
        self._dispatch(cmd, received_at)

    def _dispatch(self, cmd: str, received_at: float) -> None:
        # Commandes destructives avec confirmation
        if self._require_confirm and cmd in {
            c.upper() for c in self.DESTRUCTIVE_COMMANDS
        }:
            with self._lock:
                self._state.pending_command = cmd
                self._state.pending_command_ts = received_at
                self._state.record(f"{cmd}_PENDING")
            self._persist_state()
            self._send(
                f"⚠️ {cmd} reçu.\n"
                f"Répondez /CONFIRM dans les {_CONFIRM_TIMEOUT_S:.0f}s pour confirmer.\n"
                "Ou /CANCEL pour annuler."
            )
            self._record_response_time(received_at)
            return

        if cmd == "/CONFIRM":
            self._cmd_confirm(received_at)
        elif cmd == "/CANCEL":
            self._cmd_cancel()
        elif cmd == "/STOP_ALL":
            self._cmd_stop_all(received_at)
        elif cmd == "/CLOSE_ALL":
            self._cmd_close_all(received_at)
        elif cmd == "/SAFE_MODE":
            self._cmd_safe_mode(received_at)
        elif cmd == "/RESUME":
            self._cmd_resume(received_at)
        elif cmd == "/STATUS":
            self._cmd_status()
        elif cmd == "/HELP":
            self._cmd_help()

    # ── Commandes ─────────────────────────────────────────────────────────────

    def _cmd_confirm(self, received_at: float) -> None:
        with self._lock:
            pending = self._state.pending_command
            pending_ts = self._state.pending_command_ts
            self._state.pending_command = ""
            self._state.pending_command_ts = 0.0

        if not pending:
            self._send("Aucune commande en attente de confirmation.")
            return

        if time.time() - pending_ts > _CONFIRM_TIMEOUT_S:
            self._send(f"Délai de confirmation expiré pour {pending}. Annulé.")
            return

        _log.info("[KSHardened] Confirmation reçue pour %s", pending)
        if pending == "/STOP_ALL":
            self._cmd_stop_all(received_at)
        elif pending == "/CLOSE_ALL":
            self._cmd_close_all(received_at)

    def _cmd_cancel(self) -> None:
        with self._lock:
            pending = self._state.pending_command
            self._state.pending_command = ""
            self._state.pending_command_ts = 0.0
            self._state.record("/CANCEL")
        self._persist_state()
        self._send(f"Commande {pending or 'en attente'} annulée.")

    def _cmd_stop_all(self, received_at: float) -> None:
        t0 = received_at
        with self._lock:
            self._state.halted = True
            self._state.halt_reason = "STOP_ALL via Telegram"
            self._state.halt_time = time.time()
            self._state.record("/STOP_ALL")
        self._persist_state()
        _log.critical("[KSHardened] STOP_ALL — halt immédiat")
        self._record_response_time(t0)
        ack_msg = (
            f"✅ STOP_ALL CONFIRMÉ\n"
            f"Halt immédiat activé à {self._fmt_time(self._state.halt_time)}\n"
            f"Temps de réponse: {self._last_response_time_ms():.0f}ms\n"
            "Pour reprendre: /RESUME"
        )
        self._send(ack_msg)
        if self._on_stop_all:
            try:
                self._on_stop_all()
            except Exception as exc:
                _log.error("[KSHardened] on_stop_all error: %s", exc)

    def _cmd_close_all(self, received_at: float) -> None:
        t0 = received_at
        with self._lock:
            self._state.halted = True
            self._state.halt_reason = "CLOSE_ALL via Telegram"
            self._state.halt_time = time.time()
            self._state.record("/CLOSE_ALL")
        self._persist_state()
        _log.critical("[KSHardened] CLOSE_ALL — fermeture positions + halt")
        self._record_response_time(t0)
        self._send(
            f"✅ CLOSE_ALL CONFIRMÉ\n"
            f"Fermeture positions + halt activé\n"
            f"Temps de réponse: {self._last_response_time_ms():.0f}ms\n"
            "Pour reprendre: /RESUME"
        )
        if self._on_close_all:
            try:
                self._on_close_all()
            except Exception as exc:
                _log.error("[KSHardened] on_close_all error: %s", exc)

    def _cmd_safe_mode(self, received_at: float) -> None:
        with self._lock:
            self._state.safe_mode = True
            self._state.safe_mode_time = time.time()
            self._state.record("/SAFE_MODE")
        self._persist_state()
        self._record_response_time(received_at)
        self._send(
            f"✅ SAFE MODE ACTIVÉ\n"
            f"Observation seule — plus d'ordres\n"
            f"Temps de réponse: {self._last_response_time_ms():.0f}ms\n"
            "Pour reprendre: /RESUME"
        )
        if self._on_safe_mode:
            try:
                self._on_safe_mode()
            except Exception as exc:
                _log.error("[KSHardened] on_safe_mode error: %s", exc)

    def _cmd_resume(self, received_at: float) -> None:
        with self._lock:
            was_halted = self._state.halted
            was_safe = self._state.safe_mode
            self._state.halted = False
            self._state.safe_mode = False
            self._state.halt_reason = ""
            self._state.record("/RESUME")
        self._persist_state()
        self._record_response_time(received_at)
        status = []
        if was_halted:
            status.append("halt levé")
        if was_safe:
            status.append("safe mode désactivé")
        self._send(
            f"✅ RESUME CONFIRMÉ\n"
            f"{', '.join(status) or 'aucun changement'}\n"
            f"Temps de réponse: {self._last_response_time_ms():.0f}ms"
        )
        if self._on_resume:
            try:
                self._on_resume()
            except Exception as exc:
                _log.error("[KSHardened] on_resume error: %s", exc)

    def _cmd_status(self) -> None:
        with self._lock:
            s = self._state
        lines = [
            "📊 STATUS SYSTÈME",
            f"Halted:    {'OUI — ' + s.halt_reason if s.halted else 'NON'}",
            f"Safe mode: {'OUI' if s.safe_mode else 'NON'}",
            f"Commandes: {len(s.commands_log)}",
            f"Thread actif: {'OUI' if self.is_thread_alive() else 'NON'}",
            f"Temps réponse moyen: {self.avg_response_time_ms():.0f}ms",
        ]
        if s.halt_time:
            lines.append(f"Dernier halt: {self._fmt_time(s.halt_time)}")
        if s.pending_command:
            elapsed = time.time() - s.pending_command_ts
            lines.append(
                f"En attente: {s.pending_command} ({elapsed:.0f}s / {_CONFIRM_TIMEOUT_S:.0f}s)"
            )
        self._send("\n".join(lines))

    def _cmd_help(self) -> None:
        self._send(
            "COMMANDES KILL SWITCH HARDENED\n\n"
            "/STOP_ALL   — Halt immédiat (confirmation requise)\n"
            "/CLOSE_ALL  — Ferme positions + halt (confirmation)\n"
            "/SAFE_MODE  — Observation seule\n"
            "/RESUME     — Reprend le trading normal\n"
            "/CONFIRM    — Confirme la commande en attente\n"
            "/CANCEL     — Annule la commande en attente\n"
            "/STATUS     — État complet\n"
            "/HELP       — Cette aide"
        )

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

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _expire_pending_confirm(self) -> None:
        with self._lock:
            if not self._state.pending_command:
                return
            elapsed = time.time() - self._state.pending_command_ts
            if elapsed > _CONFIRM_TIMEOUT_S:
                pending = self._state.pending_command
                self._state.pending_command = ""
                self._state.pending_command_ts = 0.0
        if elapsed > _CONFIRM_TIMEOUT_S:
            _log.info("[KSHardened] Confirmation expirée pour %s", pending)
            self._persist_state()
            self._send_async(
                f"Confirmation expirée pour {pending} — annulé automatiquement."
            )

    def _record_response_time(self, received_at: float) -> None:
        rt = (time.time() - received_at) * 1000
        with self._lock:
            self._response_times.append(rt)
            if len(self._response_times) > 100:
                self._response_times = self._response_times[-100:]

    def _avg_response_time_ms(self) -> float:
        if not self._response_times:
            return 0.0
        return sum(self._response_times) / len(self._response_times)

    def _last_response_time_ms(self) -> float:
        return self._response_times[-1] if self._response_times else 0.0

    def _send(self, text: str) -> None:
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text},
                timeout=10,
            )
        except Exception as exc:
            _log.debug("[KSHardened] Send error: %s", exc)

    def _send_async(self, text: str) -> None:
        threading.Thread(
            target=self._send, args=(text,), daemon=True, name="KSHardenedNotify"
        ).start()

    @staticmethod
    def _fmt_time(ts: float) -> str:
        import datetime

        return datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
