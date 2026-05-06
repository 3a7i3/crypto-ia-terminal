"""
telegram_kill_switch.py — Kill Switch via commandes Telegram.

Commandes disponibles :
  /STOP_ALL    → halt immédiat, plus aucun ordre, alerte Telegram
  /CLOSE_ALL   → ferme toutes les positions ouvertes puis halt
  /SAFE_MODE   → bascule en ADVISOR_ONLY (observation seule)
  /RESUME      → reprend le trading normal (annule SAFE_MODE)
  /STATUS      → rapport d'état complet
  /HELP        → liste des commandes

Usage :
    ks = TelegramKillSwitch()
    ks.start()          # démarre le polling en thread background
    ks.is_halted()      # True si STOP_ALL a été déclenché
    ks.is_safe_mode()   # True si SAFE_MODE actif
    ks.stop()           # arrête le polling
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import requests

log = logging.getLogger("kill_switch")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
POLL_INTERVAL  = 3  # secondes entre chaque check Telegram


@dataclass
class KillSwitchState:
    halted: bool      = False
    safe_mode: bool   = False
    halt_reason: str  = ""
    halt_time: float  = 0.0
    commands_log: list = field(default_factory=list)

    def record(self, cmd: str) -> None:
        self.commands_log.append({"cmd": cmd, "time": time.time()})
        if len(self.commands_log) > 100:
            self.commands_log = self.commands_log[-100:]


class TelegramKillSwitch:
    """
    Polling Telegram en background. Réagit aux commandes de contrôle.
    Thread-safe via un verrou interne.
    """

    COMMANDS = {
        "/STOP_ALL",
        "/CLOSE_ALL",
        "/SAFE_MODE",
        "/RESUME",
        "/STATUS",
        "/HELP",
        # minuscules aussi acceptées
        "/stop_all",
        "/close_all",
        "/safe_mode",
        "/resume",
        "/status",
        "/help",
    }

    def __init__(
        self,
        on_stop_all:  Callable | None = None,
        on_close_all: Callable | None = None,
        on_safe_mode: Callable | None = None,
        on_resume:    Callable | None = None,
    ) -> None:
        self._state  = KillSwitchState()
        self._lock   = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_update_id: int = 0

        # Callbacks optionnels — appelés quand la commande arrive
        self._on_stop_all  = on_stop_all
        self._on_close_all = on_close_all
        self._on_safe_mode = on_safe_mode
        self._on_resume    = on_resume

    # ── API publique ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Démarre le polling Telegram en thread background."""
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
            log.warning("[KillSwitch] Token/ChatID manquants — kill switch désactivé")
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        log.info("[KillSwitch] Polling Telegram démarré (interval: %ds)", POLL_INTERVAL)
        self._send_async(
            "Kill Switch actif. Commandes disponibles: /STOP_ALL /CLOSE_ALL /SAFE_MODE /RESUME /STATUS /HELP"
        )

    def stop(self) -> None:
        self._running = False

    def is_halted(self) -> bool:
        with self._lock:
            return self._state.halted

    def is_safe_mode(self) -> bool:
        with self._lock:
            return self._state.safe_mode

    def state_snapshot(self) -> dict:
        with self._lock:
            return {
                "halted":      self._state.halted,
                "safe_mode":   self._state.safe_mode,
                "halt_reason": self._state.halt_reason,
                "halt_time":   self._state.halt_time,
            }

    # ── Polling ───────────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        while self._running:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._handle_update(update)
            except Exception as exc:
                log.debug("[KillSwitch] Erreur polling: %s", exc)
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

        # Ignorer les messages qui ne viennent pas du bon chat
        if chat_id != str(TELEGRAM_CHAT):
            return

        cmd = text.upper()
        if not any(cmd.startswith(c.upper()) for c in self.COMMANDS):
            return

        log.info("[KillSwitch] Commande recue: %s", text)

        if cmd.startswith("/STOP_ALL"):
            self._cmd_stop_all()
        elif cmd.startswith("/CLOSE_ALL"):
            self._cmd_close_all()
        elif cmd.startswith("/SAFE_MODE"):
            self._cmd_safe_mode()
        elif cmd.startswith("/RESUME"):
            self._cmd_resume()
        elif cmd.startswith("/STATUS"):
            self._cmd_status()
        elif cmd.startswith("/HELP"):
            self._cmd_help()

    # ── Commandes ─────────────────────────────────────────────────────────────

    def _cmd_stop_all(self) -> None:
        with self._lock:
            self._state.halted      = True
            self._state.halt_reason = "STOP_ALL manuel via Telegram"
            self._state.halt_time   = time.time()
            self._state.record("/STOP_ALL")

        log.critical("[KillSwitch] STOP_ALL déclenché — halt immédiat")
        self._send(
            "STOP_ALL EXECUTE\n"
            "Halt immédiat — plus aucun ordre ne sera place.\n"
            "Pour reprendre: /RESUME"
        )
        if self._on_stop_all:
            try:
                self._on_stop_all()
            except Exception as exc:
                log.error("[KillSwitch] Callback stop_all error: %s", exc)

    def _cmd_close_all(self) -> None:
        with self._lock:
            self._state.halted      = True
            self._state.halt_reason = "CLOSE_ALL manuel via Telegram"
            self._state.halt_time   = time.time()
            self._state.record("/CLOSE_ALL")

        log.critical("[KillSwitch] CLOSE_ALL déclenché")
        self._send(
            "CLOSE_ALL EXECUTE\n"
            "Fermeture des positions + halt.\n"
            "Pour reprendre: /RESUME"
        )
        if self._on_close_all:
            try:
                self._on_close_all()
            except Exception as exc:
                log.error("[KillSwitch] Callback close_all error: %s", exc)

    def _cmd_safe_mode(self) -> None:
        with self._lock:
            self._state.safe_mode = True
            self._state.record("/SAFE_MODE")

        log.warning("[KillSwitch] SAFE_MODE activé — bascule observation")
        self._send(
            "SAFE MODE ACTIVE\n"
            "Le bot observe seulement, plus d'ordres.\n"
            "Pour reprendre le trading: /RESUME"
        )
        if self._on_safe_mode:
            try:
                self._on_safe_mode()
            except Exception as exc:
                log.error("[KillSwitch] Callback safe_mode error: %s", exc)

    def _cmd_resume(self) -> None:
        with self._lock:
            was_halted    = self._state.halted
            was_safe_mode = self._state.safe_mode
            self._state.halted    = False
            self._state.safe_mode = False
            self._state.halt_reason = ""
            self._state.record("/RESUME")

        log.info("[KillSwitch] RESUME — reprise normale")
        status = []
        if was_halted:
            status.append("halt leve")
        if was_safe_mode:
            status.append("safe mode desactive")
        self._send(
            f"RESUME EXECUTE ({', '.join(status) if status else 'rien a changer'})\n"
            "Le bot reprend son cycle normal."
        )
        if self._on_resume:
            try:
                self._on_resume()
            except Exception as exc:
                log.error("[KillSwitch] Callback resume error: %s", exc)

    def _cmd_status(self) -> None:
        with self._lock:
            s = self._state

        lines = [
            "STATUS SYSTEME",
            "",
            f"Halted:    {'OUI — ' + s.halt_reason if s.halted else 'non'}",
            f"Safe mode: {'OUI' if s.safe_mode else 'non'}",
            f"Commandes recues: {len(s.commands_log)}",
        ]
        if s.halt_time:
            import datetime
            dt = datetime.datetime.fromtimestamp(s.halt_time).strftime("%H:%M:%S")
            lines.append(f"Dernier halt: {dt}")

        self._send("\n".join(lines))

    def _cmd_help(self) -> None:
        self._send(
            "COMMANDES DISPONIBLES:\n\n"
            "/STOP_ALL   — Halt immediat, plus d'ordres\n"
            "/CLOSE_ALL  — Ferme positions + halt\n"
            "/SAFE_MODE  — Mode observation seule\n"
            "/RESUME     — Reprend le trading normal\n"
            "/STATUS     — Etat du systeme\n"
            "/HELP       — Cette aide"
        )

    # ── Envoi Telegram ────────────────────────────────────────────────────────

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
            log.debug("[KillSwitch] Send error: %s", exc)

    def _send_async(self, text: str) -> None:
        thread = threading.Thread(
            target=self._send,
            args=(text,),
            daemon=True,
            name="KillSwitchNotify",
        )
        thread.start()
