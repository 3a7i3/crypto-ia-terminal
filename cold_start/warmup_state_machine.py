"""
warmup_state_machine.py — Machine d'état du démarrage à froid (P10)

8 états séquentiels. Chaque transition a :
  - condition d'entrée (check_entry)
  - timeout (secondes)
  - score de confiance minimum
  - action de rollback
  - fallback state si échec

États :
    BOOTING → FETCHING_MARKET_DATA → BUILDING_FEATURES
    → STABILIZING_REGIMES → VALIDATING_RISK → SHADOW_MODE
    → LIVE_READY
    (any) → FAILED
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from cold_start.warmup_signer import sign_state, verify_state
from observability.json_logger import get_logger

_log = get_logger("cold_start.warmup_state_machine")

_STATE_PERSIST_PATH = Path(
    os.getenv("P10_STATE_PERSIST_PATH", "cache/startup/warmup_state.json")
)
# Nombre max de cycles consécutifs dans le même état sans progression → boucle
_MAX_STUCK_CYCLES = int(os.getenv("P10_MAX_STUCK_CYCLES", "3"))
# Durée (s) sans transition → alerte stuck
_STUCK_ALERT_S = float(os.getenv("P10_STUCK_ALERT_S", "300.0"))  # 5 min


class WarmupState(Enum):
    BOOTING = auto()
    FETCHING_MARKET_DATA = auto()
    BUILDING_FEATURES = auto()
    STABILIZING_REGIMES = auto()
    VALIDATING_RISK = auto()
    SHADOW_MODE = auto()
    LIVE_READY = auto()
    FAILED = auto()


# Ordre de progression (FAILED et LIVE_READY sont des états terminaux)
_STATE_SEQUENCE = [
    WarmupState.BOOTING,
    WarmupState.FETCHING_MARKET_DATA,
    WarmupState.BUILDING_FEATURES,
    WarmupState.STABILIZING_REGIMES,
    WarmupState.VALIDATING_RISK,
    WarmupState.SHADOW_MODE,
    WarmupState.LIVE_READY,
]

# Timeouts par état (secondes)
_STATE_TIMEOUTS: dict[WarmupState, float] = {
    WarmupState.BOOTING: 30.0,
    WarmupState.FETCHING_MARKET_DATA: 120.0,
    WarmupState.BUILDING_FEATURES: 180.0,
    WarmupState.STABILIZING_REGIMES: 600.0,
    WarmupState.VALIDATING_RISK: 120.0,
    WarmupState.SHADOW_MODE: 300.0,  # minimum 5 min en shadow
    WarmupState.LIVE_READY: 0.0,
    WarmupState.FAILED: 0.0,
}

# Score de confiance minimum par état pour progresser
_MIN_CONFIDENCE: dict[WarmupState, float] = {
    WarmupState.BOOTING: 0.80,
    WarmupState.FETCHING_MARKET_DATA: 0.60,
    WarmupState.BUILDING_FEATURES: 0.70,
    WarmupState.STABILIZING_REGIMES: 0.75,
    WarmupState.VALIDATING_RISK: 0.85,
    WarmupState.SHADOW_MODE: 0.85,
    WarmupState.LIVE_READY: 1.0,
    WarmupState.FAILED: 0.0,
}


@dataclass
class StateRecord:
    state: WarmupState
    entered_at: float = field(default_factory=time.time)
    exited_at: Optional[float] = None
    confidence_at_exit: float = 0.0
    failure_reason: str = ""

    @property
    def duration_s(self) -> float:
        end = self.exited_at or time.time()
        return end - self.entered_at

    def to_dict(self) -> dict:
        return {
            "state": self.state.name,
            "entered_at": round(self.entered_at, 3),
            "exited_at": round(self.exited_at, 3) if self.exited_at else None,
            "duration_s": round(self.duration_s, 1),
            "confidence_at_exit": round(self.confidence_at_exit, 3),
            "failure_reason": self.failure_reason,
        }


class WarmupStateMachine:
    """
    Machine d'état linéaire BOOTING → LIVE_READY.

    Appelée chaque cycle par ColdStartManager.tick().
    Ne connaît pas les modules internes — reçoit un score de confiance
    calculé par l'extérieur (ColdStartManager).
    """

    def __init__(self) -> None:
        self._state = WarmupState.BOOTING
        self._history: list[StateRecord] = [StateRecord(state=WarmupState.BOOTING)]
        self._consecutive_failures: int = 0
        self._stuck_cycles: int = 0  # cycles sans transition dans l'état courant
        self._stuck_alerted: bool = False  # alerte 5 min déjà émise
        self._persist()
        _log.info("[WarmupSM] initialisé — état=%s", self._state.name)

    # ── Propriétés ────────────────────────────────────────────────────────────

    @property
    def state(self) -> WarmupState:
        return self._state

    @property
    def current_timeout(self) -> float:
        return _STATE_TIMEOUTS.get(self._state, 60.0)

    @property
    def min_confidence(self) -> float:
        return _MIN_CONFIDENCE.get(self._state, 0.70)

    def time_in_state(self) -> float:
        if not self._history:
            return 0.0
        return self._history[-1].duration_s

    def is_timed_out(self) -> bool:
        timeout = self.current_timeout
        if timeout <= 0:
            return False
        return self.time_in_state() > timeout

    # ── Transitions ──────────────────────────────────────────────────────────

    def try_advance(self, confidence: float) -> WarmupState:
        """
        Tente de progresser à l'état suivant si confidence >= min requis.
        Si timeout dépassé, marque FAILED.
        Détecte les boucles (> _MAX_STUCK_CYCLES sans progression).
        Retourne le nouvel état.
        """
        if self._state in (WarmupState.LIVE_READY, WarmupState.FAILED):
            return self._state

        if self.is_timed_out():
            return self._fail(
                f"timeout ({self.time_in_state():.0f}s > {self.current_timeout:.0f}s)"
            )

        # Détection boucle : trop de cycles sans progression
        if confidence < self.min_confidence:
            self._stuck_cycles += 1
            self._check_stuck_alert()
            if self._stuck_cycles > _MAX_STUCK_CYCLES * 10:
                # Protection maximale : 30+ cycles bloqués = boucle infinie
                return self._fail(
                    f"boucle détectée: {self._stuck_cycles} cycles en {self._state.name}"
                )
            return self._state

        return self._advance(confidence)

    def force_fail(self, reason: str) -> WarmupState:
        """Force la transition vers FAILED depuis n'importe quel état."""
        return self._fail(reason)

    def reset(self) -> None:
        """Réinitialise la machine (utilisé après FAILED pour retry)."""
        _log.warning("[WarmupSM] reset — retour à BOOTING")
        self._state = WarmupState.BOOTING
        self._history.append(StateRecord(state=WarmupState.BOOTING))
        self._consecutive_failures = 0
        self._stuck_cycles = 0
        self._stuck_alerted = False
        self._persist()

    # ── Internals ────────────────────────────────────────────────────────────

    def _advance(self, confidence: float) -> WarmupState:
        idx = _STATE_SEQUENCE.index(self._state)
        if idx + 1 >= len(_STATE_SEQUENCE):
            return self._state

        next_state = _STATE_SEQUENCE[idx + 1]
        self._exit_current(confidence)
        self._state = next_state
        self._stuck_cycles = 0
        self._stuck_alerted = False
        self._history.append(StateRecord(state=next_state))
        self._consecutive_failures = 0
        self._persist()
        _log.info(
            "[WarmupSM] %s → %s (conf=%.2f)",
            _STATE_SEQUENCE[idx].name,
            next_state.name,
            confidence,
        )
        return self._state

    def _fail(self, reason: str) -> WarmupState:
        self._consecutive_failures += 1
        self._exit_current(0.0, failure_reason=reason)
        self._state = WarmupState.FAILED
        self._history.append(
            StateRecord(state=WarmupState.FAILED, failure_reason=reason)
        )
        self._persist()
        _log.error(
            "[WarmupSM] FAILED — %s (consec=%d)", reason, self._consecutive_failures
        )
        return self._state

    def _exit_current(self, confidence: float, failure_reason: str = "") -> None:
        if self._history:
            rec = self._history[-1]
            rec.exited_at = time.time()
            rec.confidence_at_exit = confidence
            rec.failure_reason = failure_reason

    def _persist(self) -> None:
        """Persiste l'état courant dans un fichier signé HMAC."""
        try:
            _STATE_PERSIST_PATH.parent.mkdir(parents=True, exist_ok=True)
            record = sign_state(
                self._state.name,
                extra={"consecutive_failures": self._consecutive_failures},
            )
            _STATE_PERSIST_PATH.write_text(
                json.dumps(record, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as exc:
            _log.debug("[WarmupSM] persistance état échouée: %s", exc)

    def _check_stuck_alert(self) -> None:
        """Émet une alerte si l'état courant dure plus de _STUCK_ALERT_S secondes."""
        if self._stuck_alerted:
            return
        elapsed = self.time_in_state()
        if elapsed >= _STUCK_ALERT_S:
            _log.warning(
                "[WarmupSM] ALERTE BLOCAGE — état=%s depuis %.0fs (seuil %.0fs)",
                self._state.name,
                elapsed,
                _STUCK_ALERT_S,
            )
            self._stuck_alerted = True

    # ── Snapshot ─────────────────────────────────────────────────────────────

    @property
    def is_stuck(self) -> bool:
        """True si l'état courant dure plus de _STUCK_ALERT_S secondes."""
        return (
            self._state not in (WarmupState.LIVE_READY, WarmupState.FAILED)
            and self.time_in_state() >= _STUCK_ALERT_S
        )

    def load_persisted_state(self) -> Optional[str]:
        """
        Charge l'état persisté depuis le fichier signé.
        Retourne le nom de l'état si la signature est valide, None sinon.
        """
        try:
            if not _STATE_PERSIST_PATH.exists():
                return None
            record = json.loads(_STATE_PERSIST_PATH.read_text(encoding="utf-8"))
            if not verify_state(record):
                _log.warning("[WarmupSM] état persisté invalide (signature corrompue)")
                return None
            return record.get("state")
        except Exception as exc:
            _log.debug("[WarmupSM] chargement état persisté: %s", exc)
            return None

    def snapshot(self) -> dict:
        return {
            "state": self._state.name,
            "time_in_state_s": round(self.time_in_state(), 1),
            "timeout_s": self.current_timeout,
            "min_confidence": self.min_confidence,
            "consecutive_failures": self._consecutive_failures,
            "stuck_cycles": self._stuck_cycles,
            "is_stuck": self.is_stuck,
            "history": [r.to_dict() for r in self._history[-5:]],
        }
