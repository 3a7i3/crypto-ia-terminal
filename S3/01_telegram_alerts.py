"""
telegram_alerts.py — Alertes Telegram non-bloquantes avec dédoublonnage.

Wraps TelegramNotifier (déjà existant) en ajoutant :
  - Queue async (thread daemon) — ne bloque jamais la boucle advisor
  - Dédoublonnage sur 5 min — évite le spam en cas de boucle d'erreurs
  - Types d'alertes : trade, danger, error, heartbeat, daily_summary
  - Désactivé silencieusement si token/chat_id absent

Config (par ordre de priorité) :
  1. config/telegram_config.json
  2. TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (env vars)

Usage dans advisor_loop.py :
    from S3.telegram_alerts import TelegramAlert
    alert = TelegramAlert()
    alert.trade("BUY", "BTC/USDT", 50.0, 67000.0)
    alert.danger("GATE_BLOCK", "signal_score 58<60")
    alert.heartbeat()
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
import time
from pathlib import Path
from typing import Optional

from observability.json_logger import get_logger

_log = get_logger("S3.01_telegram_alerts")
_CONFIG_PATH = "config/telegram_config.json"
_DEDUP_WINDOW_S = 300  # 5 minutes


def _load_config() -> tuple[str, str]:
    """Retourne (bot_token, chat_id) depuis config JSON ou env vars."""
    p = Path(_CONFIG_PATH)
    if p.exists():
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
            return cfg.get("bot_token", ""), cfg.get("chat_id", "")
        except Exception:
            pass
    return (
        os.getenv("TELEGRAM_BOT_TOKEN", ""),
        os.getenv("TELEGRAM_CHAT_ID", ""),
    )


class TelegramAlert:
    """
    Alertes Telegram async avec dédoublonnage.

    Instancier une fois au démarrage — le thread daemon tourne en continu.
    Si token absent : opération silencieuse (aucune exception levée).
    """

    def __init__(self, config_path: str = _CONFIG_PATH) -> None:
        token, chat_id = _load_config()
        self._enabled = bool(token and chat_id)
        self._token = token
        self._chat_id = chat_id
        self._queue: queue.Queue[Optional[str]] = queue.Queue(maxsize=50)
        self._dedup: dict[str, float] = {}  # hash → timestamp dernière envoi
        self._lock = threading.Lock()

        if self._enabled:
            t = threading.Thread(target=self._worker, daemon=True, name="TelegramAlert")
            t.start()
            _log.info("[TelegramAlert] Démarré — token configuré")
        else:
            _log.info("[TelegramAlert] Token absent — alertes désactivées")

    # ── API publique ───────────────────────────────────────────────────────────

    def trade(
        self,
        side: str,
        symbol: str,
        size_usd: float,
        price: float,
        pnl_pct: Optional[float] = None,
    ) -> None:
        sign = "+" if (pnl_pct or 0) >= 0 else ""
        pnl_str = f" | PnL: {sign}{pnl_pct:.2%}" if pnl_pct is not None else ""
        icon = "🟢" if side == "BUY" else "🔴"
        self._send(
            f"{icon} TRADE {side}\n"
            f"  {symbol} @ {price:.4g} USD\n"
            f"  Taille: ${size_usd:.0f}{pnl_str}"
        )

    def danger(self, level: str, reason: str) -> None:
        icon = "🚨" if level in ("DANGER", "CRITICAL") else "⚠️"
        self._send(
            f"{icon} {level}\n  {reason}", dedup_key=f"danger:{level}:{reason[:40]}"
        )

    def error(self, component: str, message: str) -> None:
        self._send(
            f"❌ ERREUR [{component}]\n  {message[:200]}",
            dedup_key=f"error:{component}:{message[:40]}",
        )

    def heartbeat(self, status: str = "OK") -> None:
        self._send(f"💓 Heartbeat — {status}", dedup_key="heartbeat", force=False)

    def daily_summary(
        self,
        trades: int,
        wins: int,
        pnl_pct: float,
        active_positions: int = 0,
    ) -> None:
        wr = wins / trades * 100 if trades else 0
        sign = "+" if pnl_pct >= 0 else ""
        self._send(
            f"📊 RÉSUMÉ JOURNALIER\n"
            f"  Trades: {trades} | Wins: {wins} | WR: {wr:.0f}%\n"
            f"  PnL: {sign}{pnl_pct:.2%} | Positions: {active_positions}",
            force=True,
        )

    def info(self, message: str) -> None:
        self._send(f"ℹ️ {message}")

    # ── Envoi async avec dédoublonnage ────────────────────────────────────────

    def _send(
        self,
        text: str,
        dedup_key: Optional[str] = None,
        force: bool = False,
    ) -> None:
        if not self._enabled:
            return

        key = dedup_key or hashlib.md5(text.encode()).hexdigest()[:16]

        with self._lock:
            now = time.time()
            # Nettoyer les vieilles entrées dedup
            self._dedup = {
                k: v for k, v in self._dedup.items() if now - v < _DEDUP_WINDOW_S
            }

            if not force and key in self._dedup:
                _log.debug("[TelegramAlert] Dédoublonné: %s", key)
                return
            self._dedup[key] = now

        try:
            self._queue.put_nowait(text)
        except queue.Full:
            _log.warning("[TelegramAlert] Queue pleine — message ignoré")

    def _worker(self) -> None:
        import urllib.request

        while True:
            try:
                text = self._queue.get(timeout=60)
                if text is None:
                    break
                url = f"https://api.telegram.org/bot{self._token}/sendMessage"
                payload = json.dumps({"chat_id": self._chat_id, "text": text}).encode(
                    "utf-8"
                )
                req = urllib.request.Request(
                    url, data=payload, headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if resp.status != 200:
                        _log.warning("[TelegramAlert] HTTP %d", resp.status)
            except queue.Empty:
                pass
            except Exception as exc:
                _log.warning("[TelegramAlert] Envoi échoué: %s", exc)
                time.sleep(5)

    def stop(self) -> None:
        if self._enabled:
            self._queue.put(None)


# ── Standalone : test de connectivité ─────────────────────────────────────────

if __name__ == "__main__":
    import sys

    alert = TelegramAlert()
    if not alert._enabled:
        print("[telegram_alerts] Aucun token configuré.")
        print(
            f"  → Remplir {_CONFIG_PATH} ou définir TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID"
        )
        sys.exit(1)

    print("[telegram_alerts] Envoi du message de test...")
    alert.info("S3 — Test de connectivité Telegram ✓")
    time.sleep(3)
    print("[telegram_alerts] Message envoyé. Vérifier votre canal Telegram.")
