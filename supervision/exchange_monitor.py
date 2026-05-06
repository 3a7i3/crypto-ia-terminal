"""
exchange_monitor.py — Surveillance continue de la connexion Binance.

Thread background qui ping l'exchange toutes les 60s et :
  - Détecte les coupures réseau / API indisponible
  - Mesure la latence de connexion
  - Alerte Telegram si l'exchange est hors ligne > 2 checks consécutifs
  - Alerte mail si hors ligne > 5 checks consécutifs (urgence)
  - S'intègre avec PerformanceWatchdog via callbacks

Usage :
    mon = ExchangeMonitor()
    mon.start()               # démarre le thread background
    mon.is_healthy()          # True si exchange accessible
    mon.last_latency_ms()     # latence du dernier ping (ms)
    mon.stop()                # arrête le thread
"""

from __future__ import annotations

import logging
import os
import smtplib
import threading
import time
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Callable

import requests

log = logging.getLogger("exchange_monitor")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
SMTP_USER = os.getenv("EMAIL_FROM_ADDR", "")
SMTP_PASS = os.getenv("EMAIL_SMTP_PASS", "")
EMAIL_TO = os.getenv("EMAIL_TO_ADDR", "ia.strategy.support@gmail.com")

CHECK_INTERVAL = int(os.getenv("EXCHANGE_HEARTBEAT_S", "15"))
WARN_AFTER = 2  # checks échoués avant alerte Telegram
CRITICAL_AFTER = 5  # checks échoués avant alerte mail


@dataclass
class ExchangeHealth:
    healthy: bool = True
    last_check_ts: float = 0.0
    last_latency_ms: float = 0.0
    consecutive_failures: int = 0
    total_checks: int = 0
    total_failures: int = 0
    last_error: str = ""
    latency_history: list = field(default_factory=list)  # dernières 20 latences

    def record_success(self, latency_ms: float) -> None:
        self.healthy = True
        self.consecutive_failures = 0
        self.last_latency_ms = latency_ms
        self.last_check_ts = time.time()
        self.total_checks += 1
        self.latency_history.append(latency_ms)
        if len(self.latency_history) > 20:
            self.latency_history = self.latency_history[-20:]

    def record_failure(self, error: str) -> None:
        self.healthy = False
        self.consecutive_failures += 1
        self.total_checks += 1
        self.total_failures += 1
        self.last_check_ts = time.time()
        self.last_error = error

    @property
    def avg_latency_ms(self) -> float:
        if not self.latency_history:
            return 0.0
        return sum(self.latency_history) / len(self.latency_history)

    @property
    def uptime_pct(self) -> float:
        if not self.total_checks:
            return 100.0
        return 100.0 * (self.total_checks - self.total_failures) / self.total_checks


class ExchangeMonitor:
    """Thread background qui surveille la connexion Binance en continu."""

    def __init__(
        self,
        on_offline: Callable | None = None,
        on_recovered: Callable | None = None,
    ) -> None:
        self._health = ExchangeHealth()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False
        self._alerted_warn = False
        self._alerted_critical = False
        self._was_offline = False

        # Callbacks optionnels
        self._on_offline = on_offline
        self._on_recovered = on_recovered

    # ── API publique ──────────────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        log.info("[ExchangeMonitor] Démarré (interval: %ds)", CHECK_INTERVAL)

    def stop(self) -> None:
        self._running = False

    def is_healthy(self) -> bool:
        with self._lock:
            return self._health.healthy

    def last_latency_ms(self) -> float:
        with self._lock:
            return self._health.last_latency_ms

    def snapshot(self) -> dict:
        with self._lock:
            h = self._health
            return {
                "healthy": h.healthy,
                "consecutive_failures": h.consecutive_failures,
                "last_latency_ms": round(h.last_latency_ms, 1),
                "avg_latency_ms": round(h.avg_latency_ms, 1),
                "uptime_pct": round(h.uptime_pct, 1),
                "total_checks": h.total_checks,
                "last_error": h.last_error,
            }

    # ── Boucle de surveillance ────────────────────────────────────────────────

    def _monitor_loop(self) -> None:
        # Premier check immédiat
        self._check_once()
        while self._running:
            time.sleep(CHECK_INTERVAL)
            if self._running:
                self._check_once()

    def _check_once(self) -> None:
        t0 = time.time()
        try:
            # Ping l'endpoint public Binance (pas besoin de clé)
            testnet = os.getenv("BINANCE_TESTNET", "false").lower() == "true"
            base_url = (
                "https://testnet.binance.vision"
                if testnet
                else "https://api.binance.com"
            )
            r = requests.get(f"{base_url}/api/v3/ping", timeout=8)
            latency_ms = (time.time() - t0) * 1000

            if r.status_code == 200:
                with self._lock:
                    self._health.record_success(latency_ms)
                log.debug("[ExchangeMonitor] OK — %.0fms", latency_ms)

                # Récupération après panne
                if self._was_offline:
                    self._was_offline = False
                    self._alerted_warn = False
                    self._alerted_critical = False
                    log.info("[ExchangeMonitor] Exchange rétabli")
                    self._send_telegram("Exchange Binance RETABLI — connexion OK")
                    if self._on_recovered:
                        try:
                            self._on_recovered()
                        except Exception as exc:
                            log.error("[ExchangeMonitor] Callback recovered: %s", exc)
            else:
                raise RuntimeError(f"HTTP {r.status_code}")

        except Exception as exc:
            err = str(exc)
            with self._lock:
                self._health.record_failure(err)
                failures = self._health.consecutive_failures

            log.warning("[ExchangeMonitor] Echec ping #%d: %s", failures, err)
            self._was_offline = True
            self._handle_failure(failures, err)

    def _handle_failure(self, failures: int, error: str) -> None:
        if failures >= WARN_AFTER and not self._alerted_warn:
            self._alerted_warn = True
            log.error("[ExchangeMonitor] Exchange HORS LIGNE (%d checks)", failures)
            self._send_telegram(
                f"ALERTE — Exchange Binance HORS LIGNE\n"
                f"Echecs consecutifs: {failures}\n"
                f"Erreur: {error}\n"
                f"Les cycles continuent en mode degradé."
            )
            if self._on_offline:
                try:
                    self._on_offline()
                except Exception as exc:
                    log.error("[ExchangeMonitor] Callback offline: %s", exc)

        if failures >= CRITICAL_AFTER and not self._alerted_critical:
            self._alerted_critical = True
            log.critical("[ExchangeMonitor] Exchange CRITIQUE — %d echecs", failures)
            self._send_email(
                subject="[URGENT] Crypto AI — Exchange Binance hors ligne",
                body=(
                    f"ALERTE CRITIQUE\n\n"
                    f"L'exchange Binance ne répond pas depuis {failures} checks "
                    f"({failures * CHECK_INTERVAL // 60} minutes).\n\n"
                    f"Dernière erreur: {error}\n\n"
                    f"Actions possibles:\n"
                    f"  1. Vérifier la connexion internet\n"
                    f"  2. Vérifier https://status.binance.com\n"
                    f"  3. Envoyer /STOP_ALL sur Telegram si le bot doit s'arrêter\n\n"
                    f"Le bot continue à observer sans passer d'ordres."
                ),
            )

    # ── Notifications ─────────────────────────────────────────────────────────

    def _send_telegram(self, text: str) -> None:
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text},
                timeout=10,
            )
        except Exception as exc:
            log.debug("[ExchangeMonitor] Telegram erreur: %s", exc)

    def _send_email(self, subject: str, body: str) -> None:
        log.info("[ExchangeMonitor] Mail: %s", subject)
        if not SMTP_USER or not SMTP_PASS:
            log.warning("[ExchangeMonitor] Mail non configuré — fallback Telegram")
            self._send_telegram(f"RAPPORT (mail non dispo): {subject}\n{body[:400]}")
            return
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = SMTP_USER
            msg["To"] = EMAIL_TO
            msg.attach(MIMEText(body, "plain", "utf-8"))
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(SMTP_USER, SMTP_PASS)
                smtp.sendmail(SMTP_USER, EMAIL_TO, msg.as_string())
            log.info("[ExchangeMonitor] Mail envoyé → %s", EMAIL_TO)
        except Exception as exc:
            log.error("[ExchangeMonitor] Echec mail: %s", exc)
            self._send_telegram(f"URGENT (mail échoué): {subject}\n{body[:300]}")
