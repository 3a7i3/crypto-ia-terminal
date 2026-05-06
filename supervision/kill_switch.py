"""
kill_switch.py — Kill Switch manuel via Telegram (Idée #3).

Écoute les commandes Telegram et déclenche des actions immédiates :
  /STOP_ALL   → halte complète (plus d'ordres)
  /CLOSE_ALL  → fermeture immédiate de toutes les positions
  /SAFE_MODE  → passage en advisor_only (plus d'exécution)
  /RESUME     → reprendre l'exécution normale
  /STATUS     → réponse avec état courant

Usage:
    ks = TelegramKillSwitch(
        bot_token="...", chat_id="...",
        paper_engine=engine
    )
    ks.start()   # démarre la boucle de polling en thread daemon
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from enum import Enum
from typing import Callable

logger = logging.getLogger(__name__)

_COMMANDS = {"/STOP_ALL", "/CLOSE_ALL", "/SAFE_MODE", "/RESUME", "/STATUS"}


class BotMode(str, Enum):
    LIVE = "live"
    SAFE_MODE = "safe_mode"    # advisor only, pas d'exécution
    STOPPED = "stopped"        # halte complète
    CLOSING = "closing"        # fermeture en cours


class TelegramKillSwitch:
    """
    Polling Telegram → actions immédiates sur le bot de trading.

    Le polling tourne dans un thread daemon (ne bloque pas le main loop).
    Les callbacks peuvent être enregistrés pour chaque commande.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        paper_engine=None,
        poll_interval_s: float = 2.0,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._paper_engine = paper_engine
        self._poll_interval = poll_interval_s

        self.mode: BotMode = BotMode.LIVE
        self._last_update_id: int = 0
        self._running: bool = False
        self._thread: threading.Thread | None = None

        # Callbacks optionnels : {cmd: callable}
        self._callbacks: dict[str, Callable] = {}

    # ── API publique ───────────────────────────────────────────────────────────

    def start(self) -> None:
        """Démarre le polling en arrière-plan."""
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="TelegramKillSwitch"
        )
        self._thread.start()
        logger.info("[KillSwitch] Polling Telegram démarré (interval=%.1fs)", self._poll_interval)

    def stop(self) -> None:
        self._running = False
        logger.info("[KillSwitch] Polling arrêté")

    def register(self, command: str, callback: Callable) -> None:
        """Enregistre un callback pour une commande (ex. '/STOP_ALL')."""
        self._callbacks[command.upper()] = callback

    def is_trading_allowed(self) -> bool:
        return self.mode == BotMode.LIVE

    def is_execution_allowed(self) -> bool:
        return self.mode not in (BotMode.STOPPED, BotMode.SAFE_MODE)

    # ── Boucle de polling ──────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        while self._running:
            try:
                updates = self._get_updates()
                for upd in updates:
                    self._handle_update(upd)
            except Exception as exc:
                logger.warning("[KillSwitch] Erreur polling: %s", exc)
            time.sleep(self._poll_interval)

    def _get_updates(self) -> list[dict]:
        params = {"timeout": 1, "offset": self._last_update_id + 1}
        url = (
            f"https://api.telegram.org/bot{self.bot_token}/getUpdates?"
            + urllib.parse.urlencode(params)
        )
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        if not data.get("ok"):
            return []
        return data.get("result", [])

    def _handle_update(self, update: dict) -> None:
        self._last_update_id = update.get("update_id", self._last_update_id)
        message = update.get("message") or update.get("edited_message") or {}
        text = (message.get("text") or "").strip().upper()
        from_chat = str(message.get("chat", {}).get("id", ""))

        if from_chat != str(self.chat_id):
            return  # ignore les messages d'autres chats

        if text not in _COMMANDS:
            return

        logger.warning("[KillSwitch] Commande reçue: %s", text)
        self._dispatch(text)

    def _dispatch(self, command: str) -> None:
        handlers = {
            "/STOP_ALL":  self._cmd_stop_all,
            "/CLOSE_ALL": self._cmd_close_all,
            "/SAFE_MODE": self._cmd_safe_mode,
            "/RESUME":    self._cmd_resume,
            "/STATUS":    self._cmd_status,
        }
        handler = handlers.get(command)
        if handler:
            handler()
        if command in self._callbacks:
            try:
                self._callbacks[command]()
            except Exception as exc:
                logger.error("[KillSwitch] Callback error pour %s: %s", command, exc)

    # ── Commandes ──────────────────────────────────────────────────────────────

    def _cmd_stop_all(self) -> None:
        self.mode = BotMode.STOPPED
        msg = "🛑 STOP_ALL — Exécution complète stoppée. Plus aucun ordre ne sera envoyé."
        logger.critical("[KillSwitch] %s", msg)
        self._send(msg)
        self._emit_halt("STOP_ALL")

    def _cmd_close_all(self) -> None:
        self.mode = BotMode.CLOSING
        closed = self._close_all_positions()
        msg = f"⚠️ CLOSE_ALL — {closed} position(s) fermée(s). Mode: CLOSING."
        logger.critical("[KillSwitch] %s", msg)
        self._send(msg)
        self.mode = BotMode.STOPPED

    def _cmd_safe_mode(self) -> None:
        self.mode = BotMode.SAFE_MODE
        msg = "🟡 SAFE_MODE — Advisor only. Signaux calculés mais aucun ordre exécuté."
        logger.warning("[KillSwitch] %s", msg)
        self._send(msg)

    def _cmd_resume(self) -> None:
        self.mode = BotMode.LIVE
        msg = "🟢 RESUME — Exécution normale reprise."
        logger.info("[KillSwitch] %s", msg)
        self._send(msg)

    def _cmd_status(self) -> None:
        n_pos = 0
        balance = 0.0
        if self._paper_engine:
            n_pos = sum(1 for v in self._paper_engine.positions.values() if v > 0)
            balance = self._paper_engine.balance
        msg = (
            f"📊 STATUS\n"
            f"Mode: {self.mode.value}\n"
            f"Positions ouvertes: {n_pos}\n"
            f"Balance: {balance:,.2f} USD"
        )
        self._send(msg)

    # ── Utilitaires ────────────────────────────────────────────────────────────

    def _close_all_positions(self) -> int:
        if self._paper_engine is None:
            return 0
        closed = 0
        for symbol, qty in list(self._paper_engine.positions.items()):
            if qty > 0:
                try:
                    self._paper_engine.execute(
                        {"symbol": symbol, "action": "SELL", "size": qty},
                        mark_price=1.0,  # prix symbolique — à overrider en live
                    )
                    closed += 1
                except Exception as exc:
                    logger.error("[KillSwitch] Erreur fermeture %s: %s", symbol, exc)
        return closed

    def _send(self, text: str) -> None:
        try:
            from supervision.notifications.telegram_notifier import TelegramNotifier
            notifier = TelegramNotifier(self.bot_token, self.chat_id)
            notifier.notify(text)
        except Exception as exc:
            logger.warning("[KillSwitch] Send error: %s", exc)

    def _emit_halt(self, reason: str) -> None:
        try:
            from event_bus.bus import EventBus
            from event_bus.events import SessionHaltEvent
            EventBus.get().emit(
                SessionHaltEvent(
                    reason=reason,
                    halt_duration_seconds=0.0,
                    source="telegram_kill_switch",
                )
            )
        except Exception:
            pass
