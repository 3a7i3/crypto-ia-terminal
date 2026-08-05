"""
capital_deployment/capital_throttle.py — F-01 Capital Throttle

Enforce capital limits per deployment phase.
Blocks position sizing above phase capital ceiling.

F-01: max 1% du capital total, plafonné à 100 EUR absolument.
F-02: 5%, F-03: 25%, F-04: 50%, F-05: 100%.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from observability.json_logger import get_logger

_log = get_logger("capital_deployment.capital_throttle")

# ── Horloge de phase persistante ──────────────────────────────────────────────
# `started_at` valait `time.time()` a chaque construction, sans persistance :
# le compteur repartait donc a zero a CHAQUE demarrage du processus. Le critere
# `min_duration_days` (7 j pour F-01) n'etait alors satisfiable que si le moteur
# tournait 7 jours consecutifs sans un seul redemarrage — deploiement, migration
# ou crash inclus. Mesure du 2026-08-05 : le bot affichait « Jour 3.2 / 7 »
# alors que le PROCESSUS avait exactement 3 jours d'uptime. Le compteur mesurait
# l'age du processus, pas celui de la phase.
_PHASE_CLOCK_PATH = Path(os.getenv("PHASE_CLOCK_PATH", "databases/phase_clock.json"))


def _load_phase_start(phase: str) -> Optional[float]:
    """Debut persiste de `phase`, ou None.

    Retourne None si le fichier decrit une AUTRE phase : un changement de phase
    doit legitimement repartir de zero. Toute anomalie de lecture retourne None
    plutot que de lever — une horloge d'observation ne doit jamais empecher le
    moteur de demarrer.
    """
    try:
        data = json.loads(_PHASE_CLOCK_PATH.read_text(encoding="utf-8"))
        if data.get("phase") != phase:
            return None
        started = float(data["started_at"])
        if started <= 0 or started > time.time() + 3600:
            # Horodatage absurde ou dans le futur (derive d'horloge) : on refuse
            # plutot que de produire un `days_elapsed` negatif.
            _log.warning(
                "[PhaseClock] started_at invalide (%s) — reinitialisation", started
            )
            return None
        return started
    except FileNotFoundError:
        return None
    except Exception as exc:
        _log.warning("[PhaseClock] lecture impossible (%s) — reinitialisation", exc)
        return None


def _save_phase_start(phase: str, started_at: float) -> None:
    """Persiste le debut de phase. N'echoue jamais bruyamment."""
    try:
        _PHASE_CLOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PHASE_CLOCK_PATH.write_text(
            json.dumps(
                {
                    "phase": phase,
                    "started_at": started_at,
                    "started_at_iso": datetime.fromtimestamp(
                        started_at, timezone.utc
                    ).isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        _log.warning("[PhaseClock] ecriture impossible: %s", exc)


PHASE_CONFIGS: dict[str, dict] = {
    "F-01": {"capital_pct": 0.01, "max_capital_eur": 100.0, "min_duration_days": 7},
    "F-02": {"capital_pct": 0.05, "max_capital_eur": None, "min_duration_days": 14},
    "F-03": {"capital_pct": 0.25, "max_capital_eur": None, "min_duration_days": 21},
    "F-04": {"capital_pct": 0.50, "max_capital_eur": None, "min_duration_days": 30},
    "F-05": {"capital_pct": 1.00, "max_capital_eur": None, "min_duration_days": 0},
}

PHASE_ORDER = ["F-01", "F-02", "F-03", "F-04", "F-05"]


@dataclass
class PhaseAllocation:
    phase: str
    total_capital: float
    allocated_capital: float
    capital_pct: float
    min_duration_days: int
    started_at: float = field(default_factory=time.time)

    def days_elapsed(self) -> float:
        return (time.time() - self.started_at) / 86400.0

    def time_requirement_met(self) -> bool:
        return self.days_elapsed() >= self.min_duration_days

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "total_capital": round(self.total_capital, 2),
            "allocated_capital": round(self.allocated_capital, 2),
            "capital_pct": self.capital_pct,
            "min_duration_days": self.min_duration_days,
            "days_elapsed": round(self.days_elapsed(), 3),
            "time_requirement_met": self.time_requirement_met(),
        }


class CapitalThrottle:
    """
    Enforce capital limits per deployment phase.

    Usage:
        throttle = CapitalThrottle(total_capital=10_000.0, phase="F-01")
        safe_size = throttle.throttled_size(500.0)   # → 100.0 (F-01 cap)
    """

    def __init__(
        self,
        total_capital: float,
        phase: str = "F-01",
        started_at: Optional[float] = None,
    ) -> None:
        if phase not in PHASE_CONFIGS:
            raise ValueError(f"Phase inconnue: {phase}. Valides: {list(PHASE_CONFIGS)}")
        if total_capital <= 0:
            raise ValueError(f"total_capital doit être > 0, reçu: {total_capital}")

        self._total_capital = total_capital
        self._phase = phase
        cfg = PHASE_CONFIGS[phase]

        raw = total_capital * cfg["capital_pct"]
        cap = cfg.get("max_capital_eur")
        if cap is not None:
            raw = min(raw, cap)

        # Horloge de phase. Priorite :
        #   1. `started_at` explicite — l'appelant fait autorite (tests, rejeu) ;
        #   2. valeur persistee pour CETTE phase — survit au redemarrage ;
        #   3. maintenant — premier demarrage, ou changement de phase.
        # `allocated_capital` ne depend PAS de `started_at` : cette persistance
        # ne peut modifier aucun sizing, seulement la mesure du temps ecoule.
        if started_at is None:
            started_at = _load_phase_start(phase)
            if started_at is None:
                started_at = time.time()
                _log.info(
                    "[PhaseClock] %s — nouvelle horloge demarree a %s",
                    phase,
                    datetime.fromtimestamp(started_at, timezone.utc).isoformat(),
                )
            else:
                _log.info(
                    "[PhaseClock] %s — horloge restauree, %.2f j ecoules",
                    phase,
                    (time.time() - started_at) / 86400.0,
                )
        _save_phase_start(phase, started_at)

        self._allocation = PhaseAllocation(
            phase=phase,
            total_capital=total_capital,
            allocated_capital=raw,
            capital_pct=cfg["capital_pct"],
            min_duration_days=cfg["min_duration_days"],
            started_at=started_at,
        )

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def allocated_capital(self) -> float:
        return self._allocation.allocated_capital

    def max_single_position(self, max_pct_of_phase: float = 0.20) -> float:
        """Max single position = 20% of phase capital by default."""
        return self._allocation.allocated_capital * max_pct_of_phase

    def is_within_limit(self, order_size: float) -> bool:
        return 0 < order_size <= self._allocation.allocated_capital

    def throttled_size(self, requested: float) -> float:
        """Clamp requested order size to phase capital ceiling."""
        if requested <= 0:
            return 0.0
        return min(requested, self._allocation.allocated_capital)

    def allocation(self) -> PhaseAllocation:
        return self._allocation

    def advance_to(self, next_phase: str, certified: bool = False) -> "CapitalThrottle":
        """Return a new throttle for the next phase. Requires certified=True."""
        if not certified:
            raise PermissionError(
                f"Avancement vers {next_phase} refusé — phase {self._phase} non certifiée."
            )
        if next_phase not in PHASE_CONFIGS:
            raise ValueError(f"Phase cible inconnue: {next_phase}")
        return CapitalThrottle(self._total_capital, next_phase)

    def next_phase(self) -> Optional[str]:
        idx = PHASE_ORDER.index(self._phase)
        if idx + 1 < len(PHASE_ORDER):
            return PHASE_ORDER[idx + 1]
        return None
