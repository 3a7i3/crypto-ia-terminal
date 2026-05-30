"""
proactive_alerts.py — Alertes Telegram proactives (Phase 8).

3 types d'alertes déclenchées automatiquement :
  1. SIGNAL_OPPORTUNITY  : score ≥ seuil + signal actionable → "Opportunité détectée"
  2. REGIME_CHANGE       : changement de régime de marché → "Régime passé de X à Y"
  3. RISK_GATE_BLOCKED   : GlobalRiskGate a bloqué un ordre → "Ordre bloqué — raisons"

Toutes les alertes sont rate-limitées (même type/symbole = 1 msg / cooldown).
Fonctionne sans Telegram configuré : no-op silencieux.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.proactive_alerts")
_COOLDOWN_SIGNAL = float(os.getenv("ALERT_COOLDOWN_SIGNAL", "300"))  # 5 min
_COOLDOWN_REGIME = float(os.getenv("ALERT_COOLDOWN_REGIME", "600"))  # 10 min
_COOLDOWN_RISK = float(os.getenv("ALERT_COOLDOWN_RISK", "120"))  # 2 min

_ICONS = {
    "opportunity": "🟢",
    "regime": "🔄",
    "risk_block": "🔴",
    "weekly": "📊",
    "advice": "💡",
}


@dataclass
class AlertRecord:
    """Historique d'une alerte envoyée."""

    alert_type: str
    key: str
    message: str
    sent_at: float = field(default_factory=time.time)
    success: bool = True


class ProactiveAlerts:
    """
    Gestionnaire d'alertes Telegram proactives.

    Usage:
        alerts = ProactiveAlerts.from_env()

        # Depuis LiveSignalEngine
        alerts.on_signal_opportunity(signal_result, advice)

        # Depuis AdvancedRegimeDetector
        alerts.on_regime_change("BTCUSDT", old="sideways", new="bull_trend")

        # Depuis GlobalRiskGate
        alerts.on_risk_gate_blocked(gate_result, signal_result)
    """

    def __init__(self, notifier=None) -> None:
        self._notifier = notifier
        self._last_sent: dict[str, float] = {}
        self._history: list[AlertRecord] = []

    @classmethod
    def from_env(cls) -> "ProactiveAlerts":
        """Construit depuis les variables d'environnement TELEGRAM_*."""
        try:
            from supervision.notifications.ops_notifier import OpsNotifier

            notifier = OpsNotifier.from_env()
            if not notifier.enabled:
                _log.info(
                    "[ProactiveAlerts] Telegram non configuré — alertes désactivées"
                )
                return cls(notifier=None)
            return cls(notifier=notifier)
        except Exception as exc:
            _log.debug("[ProactiveAlerts] Erreur init notifier: %s", exc)
            return cls(notifier=None)

    @property
    def enabled(self) -> bool:
        return self._notifier is not None

    # ── 3 types d'alertes proactives ──────────────────────────────────────────

    def on_signal_opportunity(self, signal_result, advice=None) -> bool:
        """
        Alerte de type 1 : opportunité de trading détectée.

        Déclenche si signal_result.actionable is True.
        """
        if not getattr(signal_result, "actionable", False):
            return False

        symbol = getattr(signal_result, "symbol", "?")
        signal = getattr(signal_result, "signal", "?")
        score = getattr(signal_result, "score", 0)
        regime = getattr(signal_result, "regime", "unknown")
        strength = getattr(signal_result, "strength", 0.0)

        key = f"opportunity_{symbol}_{signal}"
        if not self._can_send(key, _COOLDOWN_SIGNAL):
            return False

        icon = _ICONS["opportunity"]
        lines = [
            f"{icon} OPPORTUNITÉ DÉTECTÉE",
            f"Symbole : {symbol}",
            f"Signal  : {signal} (score {score}/100)",
            f"Régime  : {regime}",
            f"Force MTF : {strength:.0%}",
        ]
        if advice is not None:
            advice_text = getattr(advice, "text", str(advice))
            lines.append(f"\n{_ICONS['advice']} {advice_text[:300]}")

        return self._send(key, "opportunity", "\n".join(lines))

    def on_regime_change(self, symbol: str, old_regime: str, new_regime: str) -> bool:
        """
        Alerte de type 2 : changement de régime de marché.
        """
        if old_regime == new_regime:
            return False

        key = f"regime_{symbol}_{new_regime}"
        if not self._can_send(key, _COOLDOWN_REGIME):
            return False

        risk_regimes = {"flash_crash", "high_volatility_regime"}
        extra = " ⚠️  RÉGIME À RISQUE" if new_regime in risk_regimes else ""

        icon = _ICONS["regime"]
        msg = (
            f"{icon} CHANGEMENT DE RÉGIME{extra}\n"
            f"Symbole : {symbol}\n"
            f"Ancien  : {old_regime}\n"
            f"Nouveau : {new_regime}"
        )
        return self._send(key, "regime", msg)

    def on_risk_gate_blocked(self, gate_result, signal_result=None) -> bool:
        """
        Alerte de type 3 : GlobalRiskGate a bloqué un ordre.
        """
        if getattr(gate_result, "allowed", True):
            return False

        symbol = getattr(signal_result, "symbol", "?") if signal_result else "?"
        failed = getattr(gate_result, "failed", [])
        key = f"risk_block_{symbol}"
        if not self._can_send(key, _COOLDOWN_RISK):
            return False

        icon = _ICONS["risk_block"]
        lines = [
            f"{icon} ORDRE BLOQUÉ PAR RISK GATE",
            f"Symbole    : {symbol}",
            f"Conditions : {len(failed)}/5 échouée(s)",
        ]
        for f in failed:
            lines.append(f"  • {f}")
        warnings = getattr(gate_result, "warnings", [])
        for w in warnings:
            lines.append(f"  ⚠️  {w}")

        return self._send(key, "risk_block", "\n".join(lines))

    def on_weekly_report(self, report) -> bool:
        """Envoie le rapport hebdomadaire via Telegram."""
        key = "weekly_report"
        if not self._can_send(key, 3600 * 24):  # max 1 fois par 24h
            return False

        text = getattr(report, "text_summary", str(report))
        # Telegram limite à 4096 caractères
        if len(text) > 4000:
            text = text[:4000] + "\n[...]"
        return self._send(key, "weekly", text)

    # ── Utilitaires ───────────────────────────────────────────────────────────

    def history(self, limit: int = 20) -> list[AlertRecord]:
        return self._history[-limit:]

    def stats(self) -> dict:
        total = len(self._history)
        by_type: dict[str, int] = {}
        for r in self._history:
            by_type[r.alert_type] = by_type.get(r.alert_type, 0) + 1
        return {"total_sent": total, "by_type": by_type, "enabled": self.enabled}

    def reset_cooldowns(self) -> None:
        """Utilitaire de test : efface tous les cooldowns."""
        self._last_sent.clear()

    # ── Interne ───────────────────────────────────────────────────────────────

    def _can_send(self, key: str, cooldown: float) -> bool:
        now = time.time()
        last = self._last_sent.get(key, 0.0)
        if (now - last) < cooldown:
            _log.debug(
                "[ProactiveAlerts] Rate-limit %s (%.0fs restants)",
                key,
                cooldown - (now - last),
            )
            return False
        return True

    def _send(self, key: str, alert_type: str, message: str) -> bool:
        self._last_sent[key] = time.time()
        success = False

        if self._notifier is not None:
            try:
                self._notifier.info(message, key=alert_type)
                success = True
            except Exception as exc:
                _log.warning("[ProactiveAlerts] Erreur envoi %s: %s", alert_type, exc)
        else:
            _log.info(
                "[ProactiveAlerts] (no Telegram) %s: %s", alert_type, message[:80]
            )
            success = True  # considéré OK si pas de notifier configuré

        self._history.append(
            AlertRecord(
                alert_type=alert_type, key=key, message=message, success=success
            )
        )
        self._emit_event(alert_type, message)
        return success

    def _emit_event(self, alert_type: str, message: str) -> None:
        try:
            from event_bus.bus import EventBus
            from event_bus.events import SecurityAlertEvent

            if alert_type == "risk_block":
                EventBus.get().emit(
                    SecurityAlertEvent(
                        severity="medium",
                        message=message[:200],
                        source="proactive_alerts",
                    )
                )
        except Exception as exc:
            _log.warning("[ProactiveAlerts] Erreur emission alerte securite: %s", exc)
