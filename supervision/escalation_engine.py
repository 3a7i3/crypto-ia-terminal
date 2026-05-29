"""
supervision/escalation_engine.py — E-03 BotDoctor Escalation

5 niveaux d'escalade avec auto-escalade après timeout par niveau.

Niveaux :
  L1 AUTO_HEAL        : SelfHealingBot tente la guérison automatique
  L2 ISOLATE          : Isolation du composant défaillant
  L3 DEGRADE_MODE     : AGGRESSIVE → DEFENSIVE → RISK_OFF
  L4 PARTIAL_HALT     : Arrêt des composants non-critiques
  L5 TOTAL_HALT       : Arrêt total + Telegram + email

Fonctionnement :
  1. trigger(anomaly_reason) → démarre l'escalade au niveau L1
  2. L'action L1 est exécutée. Si elle échoue ou timeout → L2
  3. tick() vérifie les timeouts et auto-escalade si nécessaire
  4. Chaque niveau franchi déclenche une alerte (Telegram/log)
  5. reset() après guérison complète

Usage :
    engine = EscalationEngine(steps=[
        EscalationStep(level=EscalationLevel.L1_AUTO_HEAL,
                       action=my_heal_fn, timeout_s=60, alert_fn=notify),
        ...
    ])
    engine.trigger("LM Studio hors ligne depuis 5 min")
    # Dans la boucle périodique :
    engine.tick()
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional

from observability.json_logger import get_logger

_log = get_logger("supervision.escalation_engine")


class EscalationLevel(Enum):
    L1_AUTO_HEAL = 1
    L2_ISOLATE_COMPONENT = 2
    L3_DEGRADE_MODE = 3
    L4_PARTIAL_HALT = 4
    L5_TOTAL_HALT = 5

    @property
    def label(self) -> str:
        labels = {
            1: "L1_AUTO_HEAL",
            2: "L2_ISOLATE",
            3: "L3_DEGRADE",
            4: "L4_PARTIAL_HALT",
            5: "L5_TOTAL_HALT",
        }
        return labels[self.value]


@dataclass
class EscalationStep:
    level: EscalationLevel
    action: Callable[[], bool]  # True si réussi
    timeout_s: float  # auto-escalade après timeout_s si action échoue
    alert_fn: Optional[Callable[[str, EscalationLevel], None]] = None
    description: str = ""


@dataclass
class EscalationEvent:
    level: EscalationLevel
    ts: float
    reason: str
    action_result: Optional[bool] = None
    escalated_to_next: bool = False

    def to_dict(self) -> dict:
        return {
            "level": self.level.label,
            "ts": round(self.ts, 3),
            "reason": self.reason,
            "action_result": self.action_result,
            "escalated_to_next": self.escalated_to_next,
        }


class EscalationEngine:
    """
    Moteur d'escalade à 5 niveaux.

    L'escalade progresse automatiquement si :
      - L'action du niveau courant échoue (action retourne False)
      - Le timeout du niveau courant est dépassé sans résolution
    """

    def __init__(
        self,
        steps: Optional[list[EscalationStep]] = None,
        auto_tick_interval_s: float = 0.0,  # 0 = tick() manuel
    ) -> None:
        self._steps: dict[EscalationLevel, EscalationStep] = {}
        if steps:
            for step in steps:
                self._steps[step.level] = step

        self._current_level: Optional[EscalationLevel] = None
        self._level_started_at: float = 0.0
        self._trigger_reason: str = ""
        self._history: list[EscalationEvent] = []
        self._lock = threading.Lock()
        self._resolved = False

        # Thread auto-tick (optionnel)
        if auto_tick_interval_s > 0:
            self._start_auto_tick(auto_tick_interval_s)

    # ── API publique ──────────────────────────────────────────────────────────

    def add_step(self, step: EscalationStep) -> None:
        self._steps[step.level] = step

    def trigger(self, reason: str) -> None:
        """Démarre l'escalade au niveau L1 avec la raison donnée."""
        with self._lock:
            if self._current_level is not None:
                _log.warning(
                    "[Escalation] Déjà en escalade niveau %s — trigger ignoré",
                    self._current_level.label,
                )
                return
            self._trigger_reason = reason
            self._resolved = False
            self._current_level = EscalationLevel.L1_AUTO_HEAL
            self._level_started_at = time.time()

        _log.warning("[Escalation] DÉCLENCHÉ niveau L1 — raison: %s", reason)
        self._execute_current_level(reason)

    def tick(self) -> None:
        """
        Vérifie les timeouts et auto-escalade si nécessaire.
        À appeler périodiquement (ex. toutes les 10s).
        """
        with self._lock:
            current = self._current_level
            started_at = self._level_started_at
            resolved = self._resolved

        if current is None or resolved:
            return

        step = self._steps.get(current)
        if step is None:
            return

        elapsed = time.time() - started_at
        if elapsed >= step.timeout_s:
            _log.warning(
                "[Escalation] Timeout niveau %s (%.0fs / %.0fs) — escalade",
                current.label,
                elapsed,
                step.timeout_s,
            )
            self._escalate_to_next(f"timeout {elapsed:.0f}s à {current.label}")

    def reset(self, reason: str = "résolu") -> None:
        """Réinitialise l'escalade après récupération complète."""
        with self._lock:
            prev = self._current_level
            self._current_level = None
            self._resolved = True
            self._level_started_at = 0.0

        _log.info(
            "[Escalation] RÉINITIALISÉ (était %s) — %s", prev and prev.label, reason
        )

    def current_level(self) -> Optional[EscalationLevel]:
        with self._lock:
            return self._current_level

    def is_escalating(self) -> bool:
        with self._lock:
            return self._current_level is not None and not self._resolved

    def can_escalate(self) -> bool:
        """True s'il reste un niveau supérieur."""
        with self._lock:
            current = self._current_level
        if current is None:
            return False
        return current.value < EscalationLevel.L5_TOTAL_HALT.value

    def escalation_history(self, n: int = 20) -> list[dict]:
        with self._lock:
            return [e.to_dict() for e in self._history[-n:]]

    def time_at_current_level_s(self) -> float:
        """Secondes depuis le début du niveau courant."""
        with self._lock:
            if self._current_level is None:
                return 0.0
            return time.time() - self._level_started_at

    # ── Interne ───────────────────────────────────────────────────────────────

    def _execute_current_level(self, reason: str) -> None:
        with self._lock:
            current = self._current_level

        if current is None:
            return

        step = self._steps.get(current)
        event = EscalationEvent(
            level=current,
            ts=time.time(),
            reason=reason,
        )

        # Alerte obligatoire à chaque niveau
        self._fire_alert(current, reason, step)

        if step is None:
            _log.warning("[Escalation] Aucune action définie pour %s", current.label)
            event.action_result = None
        else:
            try:
                result = step.action()
                event.action_result = bool(result)
                if result:
                    _log.info(
                        "[Escalation] Action %s réussie — surveillance continue",
                        current.label,
                    )
                else:
                    _log.warning(
                        "[Escalation] Action %s échouée — auto-escalade sous %.0fs",
                        current.label,
                        step.timeout_s,
                    )
            except Exception as exc:
                _log.error(
                    "[Escalation] Exception dans action %s: %s", current.label, exc
                )
                event.action_result = False

        with self._lock:
            self._history.append(event)
            if len(self._history) > 200:
                self._history = self._history[-200:]

        # Auto-escalade immédiate si action échouée
        if event.action_result is False:
            self._escalate_to_next(f"action {current.label} échouée")

    def _escalate_to_next(self, reason: str) -> None:
        with self._lock:
            current = self._current_level
            if current is None or self._resolved:
                return

            next_value = current.value + 1
            if next_value > EscalationLevel.L5_TOTAL_HALT.value:
                _log.critical("[Escalation] NIVEAU MAXIMUM L5 atteint — %s", reason)
                # Marquer le dernier event comme escaladé
                if self._history:
                    self._history[-1].escalated_to_next = False
                return

            next_level = EscalationLevel(next_value)
            if self._history:
                self._history[-1].escalated_to_next = True
            self._current_level = next_level
            self._level_started_at = time.time()

        _log.error(
            "[Escalation] ESCALADE %s → %s — raison: %s",
            current.label,
            next_level.label,
            reason,
        )
        self._execute_current_level(reason)

    def _fire_alert(
        self,
        level: EscalationLevel,
        reason: str,
        step: Optional[EscalationStep],
    ) -> None:
        msg = f"[ESCALADE] {level.label} — {reason}"
        _log.warning(msg)
        if step and step.alert_fn:
            try:
                step.alert_fn(msg, level)
            except Exception as exc:
                _log.debug("[Escalation] alert_fn erreur: %s", exc)

    def _start_auto_tick(self, interval_s: float) -> None:
        def _loop():
            while True:
                time.sleep(interval_s)
                try:
                    self.tick()
                except Exception as exc:
                    _log.debug("[Escalation] auto-tick erreur: %s", exc)

        t = threading.Thread(target=_loop, daemon=True, name="EscalationAutoTick")
        t.start()


# ── Fabrique d'une escalade standard ─────────────────────────────────────────


def make_standard_escalation(
    alert_fn: Optional[Callable[[str, EscalationLevel], None]] = None,
    heal_fn: Optional[Callable[[], bool]] = None,
    isolate_fn: Optional[Callable[[], bool]] = None,
    degrade_fn: Optional[Callable[[], bool]] = None,
    partial_halt_fn: Optional[Callable[[], bool]] = None,
    total_halt_fn: Optional[Callable[[], bool]] = None,
) -> EscalationEngine:
    """
    Crée une EscalationEngine avec les 5 niveaux standard et des timeouts par défaut.
    Les fonctions non fournies utilisent des no-ops qui retournent False (force escalade).
    """
    _noop_fail = lambda: False
    _noop_ok = lambda: True

    steps = [
        EscalationStep(
            level=EscalationLevel.L1_AUTO_HEAL,
            action=heal_fn or _noop_fail,
            timeout_s=60.0,
            alert_fn=alert_fn,
            description="Auto-guérison SelfHealingBot",
        ),
        EscalationStep(
            level=EscalationLevel.L2_ISOLATE_COMPONENT,
            action=isolate_fn or _noop_fail,
            timeout_s=120.0,
            alert_fn=alert_fn,
            description="Isolation du composant défaillant",
        ),
        EscalationStep(
            level=EscalationLevel.L3_DEGRADE_MODE,
            action=degrade_fn or _noop_fail,
            timeout_s=180.0,
            alert_fn=alert_fn,
            description="Dégradation mode risque (DEFENSIVE → RISK_OFF)",
        ),
        EscalationStep(
            level=EscalationLevel.L4_PARTIAL_HALT,
            action=partial_halt_fn or _noop_fail,
            timeout_s=300.0,
            alert_fn=alert_fn,
            description="Arrêt partiel (composants non-critiques)",
        ),
        EscalationStep(
            level=EscalationLevel.L5_TOTAL_HALT,
            action=total_halt_fn or _noop_ok,
            timeout_s=600.0,
            alert_fn=alert_fn,
            description="Arrêt total + Telegram + email",
        ),
    ]
    return EscalationEngine(steps=steps)
