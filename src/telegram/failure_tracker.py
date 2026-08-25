"""
src/telegram/failure_tracker.py — Détection d'échecs de canal Telegram.

Outil d'observabilité PUR (ADR-0007) : compte les échecs CONSÉCUTIFS d'un
canal de notification et signale quand escalader vers une voie de secours
indépendante du canal défaillant.

Motivation (incident 2026-08-12→20) : le token @QuantCrpto_bot avait été
écrasé ; chaque envoi renvoyait 404 mais le code loguait « envoyé » et
n'escaladait jamais → 8 jours de silence invisible. Ce tracker rend un
canal mort VISIBLE en quelques minutes.

Dépendance ZÉRO (stdlib seule) et horloge injectable → testable en isolation,
contrairement au reste de advisor_loop qui charge tout le stack.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class FailureVerdict:
    """Résultat d'un enregistrement d'échec."""

    streak: int  # nombre d'échecs consécutifs (0 après un succès)
    should_escalate: bool  # True exactement une fois par franchissement + cooldown


class ChannelFailureTracker:
    """Suit les échecs consécutifs d'un canal et décide quand escalader.

    - `escalate_after` échecs consécutifs déclenchent une escalade.
    - `cooldown_s` empêche le spam : au plus une escalade par fenêtre.
    - Un seul succès remet le compteur à zéro (le canal est revenu).
    """

    def __init__(
        self,
        escalate_after: int = 5,
        cooldown_s: float = 1800.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if escalate_after < 1:
            raise ValueError("escalate_after doit être >= 1")
        self._escalate_after = escalate_after
        self._cooldown_s = cooldown_s
        self._clock = clock
        self._streak = 0
        self._last_escalation = float("-inf")

    @property
    def streak(self) -> int:
        return self._streak

    def record_success(self) -> None:
        """Le canal a répondu — on efface l'ardoise."""
        self._streak = 0

    def record_failure(self) -> FailureVerdict:
        """Le canal a échoué — incrémente et décide de l'escalade."""
        self._streak += 1
        should = False
        if self._streak >= self._escalate_after:
            now = self._clock()
            if now - self._last_escalation >= self._cooldown_s:
                self._last_escalation = now
                should = True
        return FailureVerdict(streak=self._streak, should_escalate=should)
