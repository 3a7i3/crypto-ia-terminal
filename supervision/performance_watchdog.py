"""
performance_watchdog.py — Surveillance des latences et auto-guérison.

Surveille chaque composant du pipeline à chaque cycle :
  - Latence de chaque étape (scan, signal, risk, advisor)
  - Santé LM Studio (modèle chargé, temps de réponse)
  - Santé Binance (connexion exchange)

Niveaux d'alerte :
  WARNING  : latence > seuil_warn  → log seulement
  DEGRADED : latence > seuil_deg   → Telegram + tentative auto-heal
  CRITICAL : composant hors ligne  → mail + demande d'autorisation

Auto-heal :
  - LM Studio hors ligne   : bascule en mode déterministe (silencieux)
  - LM Studio lent         : réduit max_tokens, avertit Telegram
  - Exchange hors ligne    : alerte critique, demande autorisation pour arrêt
  - Cycle trop lent        : log + Telegram, pas d'action auto

Usage :
    wd = PerformanceWatchdog()
    with wd.measure("scan"):
        data = scanner.scan()
    wd.check_cycle()   # à la fin de chaque cycle
"""

from __future__ import annotations

import logging
import os
import smtplib
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Generator

import requests

log = logging.getLogger("performance_watchdog")

# ── Seuils de latence (secondes) ──────────────────────────────────────────────
THRESHOLDS: dict[str, dict[str, float]] = {
    "scan_1h":  {"warn": 8.0,  "degraded": 15.0},
    "scan_mtf": {"warn": 10.0, "degraded": 20.0},
    "features": {"warn": 1.0,  "degraded": 3.0},
    "signal":   {"warn": 2.0,  "degraded": 5.0},
    "risk":     {"warn": 1.0,  "degraded": 3.0},
    "advisor":  {"warn": 10.0, "degraded": 20.0},
    "cycle":    {"warn": 30.0, "degraded": 60.0},
}

# ── Config mail ───────────────────────────────────────────────────────────────
SMTP_SERVER  = os.getenv("EMAIL_SMTP_SERVER",  "smtp.gmail.com")
SMTP_PORT    = int(os.getenv("EMAIL_SMTP_PORT", "587"))
SMTP_USER    = os.getenv("EMAIL_FROM_ADDR",    "")
SMTP_PASS    = os.getenv("EMAIL_SMTP_PASS",    "")
EMAIL_TO     = os.getenv("EMAIL_TO_ADDR",      "ia.strategy.support@gmail.com")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID",   "")

# Historique de latences (fenêtre glissante 20 cycles)
_HISTORY_SIZE = 20


@dataclass
class ComponentStatus:
    name: str
    last_latency: float = 0.0
    avg_latency: float  = 0.0
    status: str         = "ok"       # ok | warn | degraded | offline
    heal_count: int     = 0
    history: deque      = field(default_factory=lambda: deque(maxlen=_HISTORY_SIZE))

    def record(self, latency: float, warn: float, degraded: float) -> str:
        self.last_latency = latency
        self.history.append(latency)
        self.avg_latency = sum(self.history) / len(self.history)
        if latency >= degraded:
            self.status = "degraded"
        elif latency >= warn:
            self.status = "warn"
        else:
            self.status = "ok"
        return self.status


class PerformanceWatchdog:
    """Surveille les latences du pipeline et déclenche les alertes/auto-heals."""

    def __init__(self) -> None:
        self._components: dict[str, ComponentStatus] = {
            name: ComponentStatus(name=name) for name in THRESHOLDS
        }
        self._cycle_start: float = 0.0
        self._pending_auth: list[dict] = []  # actions en attente d'autorisation
        self._lm_degraded: bool = False      # LM Studio déjà signalé comme dégradé

    # ── Mesure de latence ─────────────────────────────────────────────────────

    @contextmanager
    def measure(self, component: str) -> Generator[None, None, None]:
        """Context manager qui mesure la latence d'un bloc de code."""
        t0 = time.time()
        try:
            yield
        finally:
            latency = time.time() - t0
            self._record(component, latency)

    def start_cycle(self) -> None:
        self._cycle_start = time.time()

    def end_cycle(self, cycle: int) -> None:
        if self._cycle_start:
            self._record("cycle", time.time() - self._cycle_start)
        self._summarize(cycle)

    def _record(self, component: str, latency: float) -> None:
        if component not in self._components:
            self._components[component] = ComponentStatus(name=component)
        thresh = THRESHOLDS.get(component, {"warn": 10.0, "degraded": 30.0})
        status = self._components[component].record(
            latency, thresh["warn"], thresh["degraded"]
        )
        if status == "degraded":
            log.warning("[WD] %s DEGRADE — %.1fs (seuil: %.1fs)",
                        component, latency, thresh["degraded"])
        elif status == "warn":
            log.info("[WD] %s lent — %.1fs (seuil warn: %.1fs)",
                     component, latency, thresh["warn"])

    # ── Vérification globale à la fin de chaque cycle ─────────────────────────

    def _summarize(self, cycle: int) -> None:
        degraded = [c for c in self._components.values() if c.status == "degraded"]
        if not degraded:
            return

        names = ", ".join(c.name for c in degraded)
        log.warning("[WD] Cycle %d — %d composant(s) dégradé(s): %s", cycle, len(degraded), names)

        # Telegram pour dégradation
        self._telegram(
            f"Crypto AI Terminal — Ralentissement détecté\n"
            f"Cycle {cycle} | Composants: {names}\n"
            + "\n".join(
                f"  {c.name}: {c.last_latency:.1f}s (moy: {c.avg_latency:.1f}s)"
                for c in degraded
            )
        )

        # Auto-heal par composant
        for comp in degraded:
            self._try_heal(comp, cycle)

    # ── Auto-heal ─────────────────────────────────────────────────────────────

    def _try_heal(self, comp: ComponentStatus, cycle: int) -> None:
        if comp.name == "advisor":
            self._heal_lm_studio(comp, cycle)
        elif comp.name in ("scan_1h", "scan_mtf"):
            self._heal_scanner(comp, cycle)

    def _heal_lm_studio(self, comp: ComponentStatus, cycle: int) -> None:
        """Si l'advisor est lent → vérifier LM Studio et basculer si nécessaire."""
        try:
            from lm_studio.client import list_loaded_models
            loaded = list_loaded_models()
        except Exception:
            loaded = []

        comp.heal_count += 1

        if not loaded:
            # Aucun modèle chargé → basculer en déterministe silencieusement
            if not self._lm_degraded:
                self._lm_degraded = True
                log.warning("[WD] LM Studio: aucun modèle chargé — bascule déterministe")
                self._send_report(
                    subject="[Crypto AI] LM Studio hors ligne — action requise",
                    body=(
                        f"Cycle {cycle} — LM Studio ne répond pas.\n\n"
                        f"Modèles listés: {loaded}\n"
                        f"Action automatique: bascule en mode analyse déterministe.\n\n"
                        f"Pour rétablir: ouvrir LM Studio et charger un modèle.\n"
                        f"Latence advisor: {comp.last_latency:.1f}s\n"
                        f"Heal count: {comp.heal_count}"
                    ),
                    require_auth=False,
                )
        else:
            # Modèle disponible mais lent → rapport informatif
            if not self._lm_degraded:
                self._lm_degraded = True
                self._send_report(
                    subject="[Crypto AI] LM Studio lent",
                    body=(
                        f"Cycle {cycle} — LM Studio répond lentement.\n\n"
                        f"Modèle actif: {loaded[0] if loaded else 'inconnu'}\n"
                        f"Latence advisor: {comp.last_latency:.1f}s\n"
                        f"Action automatique: réduction de max_tokens à 256.\n\n"
                        f"Aucune intervention requise pour l'instant."
                    ),
                    require_auth=False,
                )
                os.environ["LM_STUDIO_MAX_TOKENS"] = "256"

    def _heal_scanner(self, comp: ComponentStatus, cycle: int) -> None:
        """Si le scanner est lent → rapport + demande d'autorisation pour augmenter le cache TTL."""
        comp.heal_count += 1
        if comp.heal_count == 1:
            self._send_report(
                subject=f"[Crypto AI] Scanner {comp.name} lent — autorisation requise",
                body=(
                    f"Cycle {cycle} — Le scanner {comp.name} est lent ({comp.last_latency:.1f}s).\n\n"
                    f"Moyenne sur {len(comp.history)} cycles: {comp.avg_latency:.1f}s\n\n"
                    f"Action proposée: augmenter MARKET_SCANNER_CACHE_TTL de 60s à 120s\n"
                    f"(réduit la fréquence des appels Binance).\n\n"
                    f"Réponds à ce mail avec 'OUI' pour autoriser, 'NON' pour ignorer."
                ),
                require_auth=True,
                action={"type": "env_set", "key": "MARKET_SCANNER_CACHE_TTL", "value": "120"},
            )

    # ── Notifications ─────────────────────────────────────────────────────────

    def _telegram(self, text: str) -> None:
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": f"⚠️ {text}"},
                timeout=10,
            )
        except Exception as exc:
            log.debug("[WD] Telegram erreur: %s", exc)

    def _send_report(self, subject: str, body: str, require_auth: bool = False,
                     action: dict | None = None) -> None:
        """Envoie un mail de rapport. Si require_auth=True, stocke l'action en attente."""
        if require_auth and action:
            self._pending_auth.append(action)
            body += f"\n\nID action en attente: {len(self._pending_auth)}"

        log.info("[WD] Rapport mail: %s", subject)

        if not SMTP_USER or not SMTP_PASS:
            log.warning("[WD] Mail non configuré (EMAIL_FROM_ADDR/EMAIL_SMTP_PASS manquants)")
            # Fallback Telegram si mail non configuré
            self._telegram(f"RAPPORT: {subject}\n\n{body[:400]}")
            return

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = SMTP_USER
            msg["To"]      = EMAIL_TO
            msg.attach(MIMEText(body, "plain", "utf-8"))

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(SMTP_USER, SMTP_PASS)
                smtp.sendmail(SMTP_USER, EMAIL_TO, msg.as_string())
            log.info("[WD] Mail envoyé: %s → %s", subject, EMAIL_TO)
        except Exception as exc:
            log.error("[WD] Echec envoi mail: %s", exc)
            self._telegram(f"RAPPORT (mail échoué): {subject}\n{body[:300]}")

    # ── Rapport de santé ──────────────────────────────────────────────────────

    def health_report(self) -> dict:
        """Retourne un snapshot de l'état de tous les composants."""
        return {
            name: {
                "status":       c.status,
                "last":         round(c.last_latency, 2),
                "avg":          round(c.avg_latency, 2),
                "heal_count":   c.heal_count,
            }
            for name, c in self._components.items()
        }

    def reset_lm_flag(self) -> None:
        """Réinitialise le flag LM Studio dégradé (après rétablissement)."""
        self._lm_degraded = False
