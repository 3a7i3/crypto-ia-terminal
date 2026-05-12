"""
SupervisionBridge — pont entre l'EventBus et les systèmes de notification existants.

Rôle: écoute les événements critiques du bus et les route vers:
  - OpsNotifier (Telegram / Slack / Email) déjà configuré
  - OpsWatchdog (crash guard, session halt)
  - Logger structuré (toujours actif)

Usage:
    bridge = SupervisionBridge.from_env()
    bridge.activate()
    # À partir de là, tout CrashEvent → Telegram, tout ApiKeyErrorEvent → alerte, etc.

Usage sans Telegram (dev):
    bridge = SupervisionBridge()
    bridge.activate()
"""

from __future__ import annotations

import logging

from event_bus.bus import EventBus
from event_bus.events import (
    ApiKeyErrorEvent,
    ApiKeyValidatedEvent,
    CrashEvent,
    DrawdownAlertEvent,
    EvolutionCycleEvent,
    IncidentResolvedEvent,
    IncidentStartedEvent,
    OrderFilledEvent,
    OrderRejectedEvent,
    PieuvreRegrowthEvent,
    SecurityAlertEvent,
    SessionHaltEvent,
    SystemHealthEvent,
    SystemShutdownEvent,
    SystemStartupEvent,
    TrendChangeEvent,
    WsStaleEvent,
)

logger = logging.getLogger(__name__)


class SupervisionBridge:
    """
    Abonne automatiquement les handlers de notification sur l'EventBus.

    Chaque handler:
      - Logue toujours (même sans notifier)
      - Route vers notifier si disponible
      - Ne crash jamais (toutes les exceptions sont absorbées et loguées)
    """

    def __init__(self, notifier=None) -> None:
        self._notifier = notifier
        self._bus = EventBus.get()
        self._active = False
        # Stocke les références bound pour que subscribe/unsubscribe utilisent le même objet
        self._handlers = {
            CrashEvent: self._on_crash,
            SecurityAlertEvent: self._on_security_alert,
            IncidentStartedEvent: self._on_incident_started,
            IncidentResolvedEvent: self._on_incident_resolved,
            PieuvreRegrowthEvent: self._on_regrowth,
            ApiKeyErrorEvent: self._on_api_key_error,
            ApiKeyValidatedEvent: self._on_api_validated,
            DrawdownAlertEvent: self._on_drawdown,
            SessionHaltEvent: self._on_session_halt,
            OrderRejectedEvent: self._on_order_rejected,
            OrderFilledEvent: self._on_order_filled,
            TrendChangeEvent: self._on_trend_change,
            SystemStartupEvent: self._on_startup,
            SystemShutdownEvent: self._on_shutdown,
            WsStaleEvent: self._on_ws_stale,
            EvolutionCycleEvent: self._on_evolution_cycle,
            SystemHealthEvent: self._on_health,
        }

    @classmethod
    def from_env(cls) -> SupervisionBridge:
        """Construit avec OpsNotifier chargé depuis les variables d'environnement."""
        try:
            from supervision.notifications.ops_notifier import OpsNotifier

            notifier = OpsNotifier.from_env()
            return cls(notifier=notifier)
        except Exception as exc:
            logger.warning(
                "SupervisionBridge: OpsNotifier non dispo (%s) — mode log seul", exc
            )
            return cls(notifier=None)

    def activate(self) -> None:
        """Enregistre tous les handlers sur le bus."""
        if self._active:
            return

        for event_type, handler in self._handlers.items():
            self._bus.subscribe(event_type, handler)

        self._active = True
        logger.info(
            "SupervisionBridge activé — %d types d'événements routés",
            len(self._handlers),
        )

    def deactivate(self) -> None:
        """Supprime tous les handlers du bus."""
        for event_type, handler in self._handlers.items():
            self._bus.unsubscribe(event_type, handler)
        self._active = False

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _on_crash(self, event: CrashEvent) -> None:
        logger.error("[CRASH] contexte=%s erreur=%s", event.context, event.error)
        self._notify(
            f"💥 CRASH DÉTECTÉ\n"
            f"Contexte: {event.context}\n"
            f"Erreur: {event.error[:200]}\n"
            f"Type: {event.error_type}",
            key="crash",
        )

    def _on_security_alert(self, event: SecurityAlertEvent) -> None:
        sev = event.severity.upper()
        logger.warning(
            "[SECURITE/%s] %s:%d — %s", sev, event.file, event.line, event.message
        )
        if event.severity in ("high", "critical"):
            self._notify(
                f"🛡️ Alerte Sécurité [{sev}]\n"
                f"Règle: {event.rule}\n"
                f"Fichier: {event.file}:{event.line}\n"
                f"{event.message}",
                key=f"security_{event.rule}",
            )

    def _on_incident_started(self, event: IncidentStartedEvent) -> None:
        logger.warning(
            "[PIEUVRE/INCIDENT] id=%s sév=%s module=%s",
            event.incident_id,
            event.severity,
            event.module,
        )
        self._notify(
            f"🐙 Incident Pieuvre [{event.severity.upper()}]\n"
            f"ID: {event.incident_id}\n"
            f"Module: {event.module}\n"
            f"{event.message[:150]}",
            key=f"incident_{event.incident_id}",
        )

    def _on_incident_resolved(self, event: IncidentResolvedEvent) -> None:
        logger.info(
            "[PIEUVRE/RÉSOLU] id=%s +%.3f force → %.3f",
            event.incident_id,
            event.strength_gained,
            event.new_force,
        )
        self._notify(
            f"✅ Incident Résolu\n"
            f"ID: {event.incident_id}\n"
            f"Force: +{event.strength_gained:.3f} → {event.new_force:.3f}\n"
            f"Immunités: {', '.join(event.immunity_patterns[:5])}",
            key=f"resolved_{event.incident_id}",
        )

    def _on_regrowth(self, event: PieuvreRegrowthEvent) -> None:
        logger.info(
            "[PIEUVRE/REGROWTH] gén=%d force=%.3f immunités=%d",
            event.generation,
            event.total_force,
            event.total_immunities,
        )

    def _on_api_key_error(self, event: ApiKeyErrorEvent) -> None:
        logger.error("[API_KEY] exchange=%s erreur=%s", event.exchange, event.error)
        self._notify(
            f"🔑 Erreur Clé API\n"
            f"Exchange: {event.exchange}\n"
            f"Erreur: {event.error[:200]}",
            key=f"api_error_{event.exchange}",
        )

    def _on_api_validated(self, event: ApiKeyValidatedEvent) -> None:
        status = "✅ OK" if event.ok else f"❌ Échec: {event.error[:80]}"
        logger.info(
            "[API] %s %s latence=%.0fms", event.exchange, status, event.latency_ms
        )

    def _on_drawdown(self, event: DrawdownAlertEvent) -> None:
        logger.warning(
            "[DRAWDOWN] %.1f%% > max %.1f%% — action: %s",
            event.current_drawdown_pct,
            event.max_allowed_pct,
            event.action_taken,
        )
        self._notify(
            f"📉 Alerte Drawdown\n"
            f"Actuel: {event.current_drawdown_pct:.1f}%\n"
            f"Max autorisé: {event.max_allowed_pct:.1f}%\n"
            f"Action: {event.action_taken}",
            key="drawdown_alert",
        )

    def _on_session_halt(self, event: SessionHaltEvent) -> None:
        logger.warning(
            "[SESSION/HALT] raison=%s durée=%.0fs",
            event.reason,
            event.halt_duration_seconds,
        )
        self._notify(
            f"⏸️ Session Suspendue\n"
            f"Raison: {event.reason}\n"
            f"Durée: {event.halt_duration_seconds:.0f}s",
            key="session_halt",
        )

    def _on_order_rejected(self, event: OrderRejectedEvent) -> None:
        if "duplicate" not in event.reason.lower():
            logger.warning(
                "[ORDER/REJET] %s %s: %s", event.symbol, event.side, event.reason
            )
            self._notify(
                f"🚫 Ordre Rejeté\n"
                f"{event.symbol} {event.side}\n"
                f"Raison: {event.reason}",
                key="order_rejected",
            )

    def _on_order_filled(self, event: OrderFilledEvent) -> None:
        logger.info(
            "[ORDER/FILL] %s %s %.4f @ %.2f [%s]",
            event.symbol,
            event.side,
            event.size,
            event.price,
            event.mode,
        )

    def _on_trend_change(self, event: TrendChangeEvent) -> None:
        logger.info(
            "[REGIME] %s: %s → %s (conf=%.0f%%)",
            event.symbol,
            event.old_regime,
            event.new_regime,
            event.confidence * 100,
        )

    def _on_startup(self, event: SystemStartupEvent) -> None:
        logger.info("[STARTUP] mode=%s exchanges=%s", event.mode, event.exchanges)
        self._notify(
            f"🚀 Système Démarré\n"
            f"Mode: {event.mode}\n"
            f"Exchanges: {', '.join(event.exchanges) or 'aucun'}\n"
            f"Symbols: {len(event.symbols)}",
            key="startup",
        )

    def _on_shutdown(self, event: SystemShutdownEvent) -> None:
        uptime_h = event.uptime_seconds / 3600
        logger.info("[SHUTDOWN] raison=%s uptime=%.1fh", event.reason, uptime_h)
        self._notify(
            f"🛑 Système Arrêté\n"
            f"Raison: {event.reason}\n"
            f"Uptime: {uptime_h:.1f}h\n"
            f"Cycles: {event.total_cycles}",
            key="shutdown",
        )

    def _on_ws_stale(self, event: WsStaleEvent) -> None:
        logger.warning("[WS/STALE] %s depuis %.0fs", event.symbol, event.stale_seconds)

    def _on_evolution_cycle(self, event: EvolutionCycleEvent) -> None:
        logger.info(
            "[EVOLUTION] cycle=%d régime=%s best_sharpe=%.4f sauvés=%d",
            event.cycle,
            event.regime,
            event.best_sharpe,
            event.saved_to_memory,
        )

    def _on_health(self, event: SystemHealthEvent) -> None:
        if event.status != "ok":
            logger.warning(
                "[HEALTH/%s] cpu=%.0f%% ram=%.0f%%",
                event.status.upper(),
                event.cpu_pct,
                event.ram_pct,
            )

    # ── Helper notif ──────────────────────────────────────────────────────────

    def _notify(self, message: str, key: str = "") -> None:
        """Envoie via OpsNotifier si disponible — ne crash jamais."""
        if self._notifier is None:
            return
        try:
            self._notifier.info(message, key=key)
        except Exception as exc:
            logger.debug("SupervisionBridge notifier error: %s", exc)
