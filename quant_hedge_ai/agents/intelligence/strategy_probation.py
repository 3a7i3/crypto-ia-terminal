"""
strategy_probation.py — Strategy Probation System (P8)

Lifecycle progressif des stratégies :
  TRACKING → PROBATION → ACTIVE
  ACTIVE → PROBATION_EXTENDED → SUSPENDED → RETIRED

Remplace le blacklist binaire par une maturation statistique.
Chaque stratégie démarre en TRACKING (observation pure, zéro capital réel).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.strategy_probation")
_DB_PATH = Path(os.getenv("PROBATION_DB", "databases/strategy_probation.json"))


class StrategyStatus(str, Enum):
    TRACKING = "TRACKING"  # shadow mode, zéro capital
    PROBATION = "PROBATION"  # 25% capital, évaluation en cours
    ACTIVE = "ACTIVE"  # capital plein via allocateur
    PROBATION_EXTENDED = "PROBATION_EXTENDED"  # 10% capital, 10 trades supplémentaires
    SUSPENDED = "SUSPENDED"  # zéro capital, rééval périodique
    RETIRED = "RETIRED"  # arrêt permanent (≥ 5 suspensions)


_STATUS_CAPITAL: dict[StrategyStatus, float] = {
    StrategyStatus.TRACKING: 0.0,
    StrategyStatus.PROBATION: 0.25,
    StrategyStatus.ACTIVE: 1.0,
    StrategyStatus.PROBATION_EXTENDED: 0.10,
    StrategyStatus.SUSPENDED: 0.0,
    StrategyStatus.RETIRED: 0.0,
}

# Rampe de capital PROBATION → ACTIVE : (cycles_minimum, facteur_capital)
_GRADUATION_PHASES: list[tuple[int, float]] = [
    (5, 0.30),
    (10, 0.50),
    (20, 0.75),
    (999, 1.00),
]

# Valeurs par défaut — relues depuis os.getenv à chaque instanciation
_P8_TRACKING_MAX_CYCLES_DEFAULT = 50
_P8_TRACKING_MIN_TRADES_DEFAULT = 5
_P8_PROBATION_EVAL_TRADES_DEFAULT = 20
_P8_ACTIVE_WINRATE_MIN_DEFAULT = 0.35
_P8_ACTIVE_SHARPE_MIN_DEFAULT = 0.30
_P8_EXTENDED_WINRATE_MIN_DEFAULT = 0.20
_P8_SUSPEND_WINRATE_MAX_DEFAULT = 0.10
_P8_EXTENDED_EXTRA_TRADES_DEFAULT = 10
_P8_SUSPEND_REEVAL_CYCLES_DEFAULT = 100
_P8_RETIRE_SUSPENSIONS_DEFAULT = 5


@dataclass
class StrategyProbationRecord:
    strategy_id: str
    status: StrategyStatus = StrategyStatus.TRACKING

    trades: int = 0
    wins: int = 0
    total_pnl: float = 0.0
    total_sharpe: float = 0.0

    cycles_in_status: int = 0
    graduation_phase: int = 0  # 0-3 pour la rampe ACTIVE
    cycles_in_graduation: int = 0
    extended_trades_at_start: int = 0

    suspension_count: int = 0
    suspension_history: list = field(default_factory=list)
    last_suspension_regime: Optional[str] = None

    shadow_trades: int = 0
    shadow_wins: int = 0
    shadow_pnl: float = 0.0

    created_at: float = field(default_factory=time.time)
    status_changed_at: float = field(default_factory=time.time)
    last_reeval_cycle: int = 0

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades > 0 else 0.0

    @property
    def avg_sharpe(self) -> float:
        return self.total_sharpe / self.trades if self.trades > 0 else 0.0

    def capital_factor(self) -> float:
        if self.status == StrategyStatus.ACTIVE:
            phase_cycles, phase_factor = _GRADUATION_PHASES[
                min(self.graduation_phase, len(_GRADUATION_PHASES) - 1)
            ]
            return phase_factor
        return _STATUS_CAPITAL.get(self.status, 0.0)

    def rehab_thresholds(self) -> tuple[float, float]:
        bonus = self.suspension_count * 0.05
        return (
            _P8_ACTIVE_WINRATE_MIN_DEFAULT + bonus,
            _P8_ACTIVE_SHARPE_MIN_DEFAULT + bonus,
        )

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "status": self.status.value,
            "trades": self.trades,
            "wins": self.wins,
            "total_pnl": round(self.total_pnl, 4),
            "total_sharpe": round(self.total_sharpe, 4),
            "cycles_in_status": self.cycles_in_status,
            "graduation_phase": self.graduation_phase,
            "cycles_in_graduation": self.cycles_in_graduation,
            "extended_trades_at_start": self.extended_trades_at_start,
            "suspension_count": self.suspension_count,
            "suspension_history": self.suspension_history[-10:],
            "last_suspension_regime": self.last_suspension_regime,
            "shadow_trades": self.shadow_trades,
            "shadow_wins": self.shadow_wins,
            "shadow_pnl": round(self.shadow_pnl, 4),
            "created_at": self.created_at,
            "status_changed_at": self.status_changed_at,
            "last_reeval_cycle": self.last_reeval_cycle,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyProbationRecord":
        r = cls(strategy_id=d["strategy_id"])
        r.status = StrategyStatus(d.get("status", "TRACKING"))
        r.trades = d.get("trades", 0)
        r.wins = d.get("wins", 0)
        r.total_pnl = d.get("total_pnl", 0.0)
        r.total_sharpe = d.get("total_sharpe", 0.0)
        r.cycles_in_status = d.get("cycles_in_status", 0)
        r.graduation_phase = d.get("graduation_phase", 0)
        r.cycles_in_graduation = d.get("cycles_in_graduation", 0)
        r.extended_trades_at_start = d.get("extended_trades_at_start", 0)
        r.suspension_count = d.get("suspension_count", 0)
        r.suspension_history = d.get("suspension_history", [])
        r.last_suspension_regime = d.get("last_suspension_regime")
        r.shadow_trades = d.get("shadow_trades", 0)
        r.shadow_wins = d.get("shadow_wins", 0)
        r.shadow_pnl = d.get("shadow_pnl", 0.0)
        r.created_at = d.get("created_at", time.time())
        r.status_changed_at = d.get("status_changed_at", time.time())
        r.last_reeval_cycle = d.get("last_reeval_cycle", 0)
        return r


class StrategyProbationSystem:
    """
    Gère le cycle de vie formel des stratégies.
    Appelé chaque cycle via tick_cycle() pour mettre à jour états et transitions.
    """

    def __init__(self) -> None:
        # Lire la config depuis l'environnement à l'instantiation (pas au module-load)
        # pour permettre la surcharge dans les tests.
        self._db_path = Path(
            os.getenv("PROBATION_DB", "databases/strategy_probation.json")
        )
        self._tracking_max_cycles = int(
            os.getenv("P8_TRACKING_MAX_CYCLES", str(_P8_TRACKING_MAX_CYCLES_DEFAULT))
        )
        self._tracking_min_trades = int(
            os.getenv("P8_TRACKING_MIN_TRADES", str(_P8_TRACKING_MIN_TRADES_DEFAULT))
        )
        self._probation_eval_trades = int(
            os.getenv(
                "P8_PROBATION_EVAL_TRADES", str(_P8_PROBATION_EVAL_TRADES_DEFAULT)
            )
        )
        self._active_winrate_min = float(
            os.getenv("P8_ACTIVE_WINRATE_MIN", str(_P8_ACTIVE_WINRATE_MIN_DEFAULT))
        )
        self._active_sharpe_min = float(
            os.getenv("P8_ACTIVE_SHARPE_MIN", str(_P8_ACTIVE_SHARPE_MIN_DEFAULT))
        )
        self._extended_winrate_min = float(
            os.getenv("P8_EXTENDED_WINRATE_MIN", str(_P8_EXTENDED_WINRATE_MIN_DEFAULT))
        )
        self._suspend_winrate_max = float(
            os.getenv("P8_SUSPEND_WINRATE_MAX", str(_P8_SUSPEND_WINRATE_MAX_DEFAULT))
        )
        self._extended_extra_trades = int(
            os.getenv(
                "P8_EXTENDED_EXTRA_TRADES", str(_P8_EXTENDED_EXTRA_TRADES_DEFAULT)
            )
        )
        self._suspend_reeval_cycles = int(
            os.getenv(
                "P8_SUSPEND_REEVAL_CYCLES", str(_P8_SUSPEND_REEVAL_CYCLES_DEFAULT)
            )
        )
        self._retire_suspensions = int(
            os.getenv("P8_RETIRE_SUSPENSIONS", str(_P8_RETIRE_SUSPENSIONS_DEFAULT))
        )
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, StrategyProbationRecord] = {}
        self._load()

    def register(self, strategy_id: str) -> StrategyProbationRecord:
        if strategy_id not in self._records:
            self._records[strategy_id] = StrategyProbationRecord(
                strategy_id=strategy_id
            )
            _log.info("[Probation] Nouvelle stratégie TRACKING: %s", strategy_id)
            self._save()
        return self._records[strategy_id]

    def get(self, strategy_id: str) -> Optional[StrategyProbationRecord]:
        return self._records.get(strategy_id)

    def capital_factor(self, strategy_id: str) -> float:
        r = self._records.get(strategy_id)
        return r.capital_factor() if r is not None else 0.0

    def record_shadow_trade(self, strategy_id: str, pnl_pct: float) -> None:
        r = self._records.get(strategy_id)
        if r is None or r.status != StrategyStatus.TRACKING:
            return
        r.shadow_trades += 1
        r.shadow_pnl += pnl_pct
        if pnl_pct > 0:
            r.shadow_wins += 1

    def record_trade(
        self,
        strategy_id: str,
        pnl_pct: float,
        sharpe: float = 0.0,
        regime: Optional[str] = None,
    ) -> StrategyProbationRecord:
        r = self._records.get(strategy_id)
        if r is None:
            r = self.register(strategy_id)
        if r.status in (StrategyStatus.TRACKING, StrategyStatus.RETIRED):
            return r

        r.trades += 1
        r.total_pnl += pnl_pct
        r.total_sharpe += sharpe
        if pnl_pct > 0:
            r.wins += 1

        if r.status == StrategyStatus.ACTIVE:
            r.cycles_in_graduation += 1
            phase_cycles, _ = _GRADUATION_PHASES[
                min(r.graduation_phase, len(_GRADUATION_PHASES) - 1)
            ]
            if (
                r.cycles_in_graduation >= phase_cycles
                and r.graduation_phase < len(_GRADUATION_PHASES) - 1
            ):
                r.graduation_phase += 1
                r.cycles_in_graduation = 0
                _log.info(
                    "[Probation] %s graduation → phase %d",
                    strategy_id,
                    r.graduation_phase,
                )

        self._check_transitions(r, regime)
        self._save()
        return r

    def tick_cycle(self, cycle: int, regime: Optional[str] = None) -> list[str]:
        """Incrémente les compteurs et déclenche les réévaluations périodiques."""
        events: list[str] = []
        for r in self._records.values():
            r.cycles_in_status += 1

            if r.status == StrategyStatus.TRACKING:
                if (
                    r.cycles_in_status >= self._tracking_max_cycles
                    or r.shadow_trades >= self._tracking_min_trades
                ):
                    self._transition(
                        r,
                        StrategyStatus.PROBATION,
                        "TRACKING→PROBATION (timeout/trades)",
                    )
                    events.append(f"{r.strategy_id}: TRACKING→PROBATION")

            elif r.status == StrategyStatus.SUSPENDED:
                if cycle - r.last_reeval_cycle >= self._suspend_reeval_cycles:
                    r.last_reeval_cycle = cycle
                    rehab_wr, rehab_sh = r.rehab_thresholds()
                    if (
                        regime
                        and r.last_suspension_regime
                        and regime == r.last_suspension_regime
                    ):
                        events.append(f"{r.strategy_id}: SUSPENDED (même régime, skip)")
                    elif r.win_rate >= rehab_wr and r.avg_sharpe >= rehab_sh:
                        self._transition(
                            r,
                            StrategyStatus.PROBATION,
                            "SUSPENDED→PROBATION (rééval OK)",
                        )
                        events.append(f"{r.strategy_id}: SUSPENDED→PROBATION")
                    else:
                        events.append(f"{r.strategy_id}: SUSPENDED (rééval maintenu)")

        # Shadow track permanent : garantit au moins une stratégie en TRACKING
        shadow_evts = self._ensure_shadow_track(cycle)
        events.extend(shadow_evts)

        if events:
            self._save()
        return events

    def _ensure_shadow_track(self, cycle: int) -> list[str]:
        """
        Si aucune stratégie n'est en TRACKING, réactive la SUSPENDED la plus ancienne
        en mode shadow pour l'exploration permanente.
        Budget shadow = max(2%, 50% × (1 - proportion_ACTIVE)).
        """
        tracking = [
            r for r in self._records.values() if r.status == StrategyStatus.TRACKING
        ]
        if tracking:
            return []

        # Cherche la meilleure candidate : SUSPENDED non-RETIRED avec la rééval
        # la plus ancienne (priorité à celles qui n'ont pas été évaluées récemment)
        suspended = sorted(
            [r for r in self._records.values() if r.status == StrategyStatus.SUSPENDED],
            key=lambda r: r.last_reeval_cycle,
        )
        if not suspended:
            return []

        candidate = suspended[0]
        # Réinitialiser les compteurs shadow sans toucher aux compteurs réels
        candidate.shadow_trades = 0
        candidate.shadow_wins = 0
        candidate.cycles_in_status = 0
        self._transition(
            candidate,
            StrategyStatus.TRACKING,
            "shadow_track_permanent: exploration forcée (aucun slot TRACKING)",
        )
        _log.info(
            "[Probation] Shadow track permanent → %s (cycle=%d)",
            candidate.strategy_id,
            cycle,
        )
        return [f"{candidate.strategy_id}: SUSPENDED→TRACKING (shadow permanent)"]

    def override_status(
        self,
        strategy_id: str,
        new_status: StrategyStatus,
        reason: str = "manual override",
    ) -> None:
        r = self._records.get(strategy_id)
        if r is None:
            return
        _log.warning(
            "[Probation] Override manuel %s: %s → %s (%s)",
            strategy_id,
            r.status.value,
            new_status.value,
            reason,
        )
        self._transition(r, new_status, reason)
        self._save()

    def snapshot(self) -> dict:
        return {
            sid: {
                "status": r.status.value,
                "capital_factor": round(r.capital_factor(), 2),
                "trades": r.trades,
                "win_rate": round(r.win_rate, 3),
                "avg_sharpe": round(r.avg_sharpe, 3),
                "suspension_count": r.suspension_count,
            }
            for sid, r in self._records.items()
        }

    # ── Transitions internes ──────────────────────────────────────────────────

    def _check_transitions(
        self, r: StrategyProbationRecord, regime: Optional[str]
    ) -> None:
        rehab_wr, rehab_sh = r.rehab_thresholds()

        if (
            r.status == StrategyStatus.PROBATION
            and r.trades >= self._probation_eval_trades
        ):
            if r.win_rate >= rehab_wr and r.avg_sharpe >= rehab_sh:
                self._transition(
                    r, StrategyStatus.ACTIVE, "PROBATION→ACTIVE (seuils OK)"
                )
            elif r.win_rate >= self._extended_winrate_min:
                r.extended_trades_at_start = r.trades
                self._transition(
                    r,
                    StrategyStatus.PROBATION_EXTENDED,
                    "PROBATION→EXTENDED (winrate faible)",
                )
            else:
                self._suspend(r, regime, "PROBATION→SUSPENDED (winrate trop faible)")

        elif r.status == StrategyStatus.PROBATION_EXTENDED:
            trades_in_ext = r.trades - r.extended_trades_at_start
            if trades_in_ext >= self._extended_extra_trades:
                if r.win_rate > self._suspend_winrate_max:
                    self._transition(
                        r, StrategyStatus.PROBATION, "EXTENDED→PROBATION (reset éval)"
                    )
                else:
                    self._suspend(r, regime, "EXTENDED→SUSPENDED (winrate < 10%)")

        elif r.status == StrategyStatus.ACTIVE:
            if r.trades >= 10 and r.win_rate < self._suspend_winrate_max:
                self._transition(
                    r, StrategyStatus.PROBATION_EXTENDED, "ACTIVE→EXTENDED (rechute)"
                )

    def _suspend(
        self, r: StrategyProbationRecord, regime: Optional[str], reason: str
    ) -> None:
        r.suspension_count += 1
        r.last_suspension_regime = regime
        r.suspension_history.append(
            {
                "regime": regime,
                "winrate": round(r.win_rate, 3),
                "sharpe": round(r.avg_sharpe, 3),
                "trades": r.trades,
                "ts": time.time(),
            }
        )
        if r.suspension_count >= self._retire_suspensions:
            self._transition(
                r, StrategyStatus.RETIRED, f"RETIRED ({r.suspension_count} suspensions)"
            )
        else:
            self._transition(r, StrategyStatus.SUSPENDED, reason)

    def _transition(
        self, r: StrategyProbationRecord, new_status: StrategyStatus, reason: str
    ) -> None:
        _log.info(
            "[Probation] %s: %s → %s (%s)",
            r.strategy_id,
            r.status.value,
            new_status.value,
            reason,
        )
        r.status = new_status
        r.cycles_in_status = 0
        r.status_changed_at = time.time()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._db_path.exists():
            return
        try:
            data = json.loads(self._db_path.read_text(encoding="utf-8"))
            for d in data.get("records", []):
                r = StrategyProbationRecord.from_dict(d)
                self._records[r.strategy_id] = r
            _log.info("[Probation] Chargé: %d stratégies", len(self._records))
        except Exception as exc:
            _log.warning("[Probation] Erreur chargement: %s", exc)

    def _save(self) -> None:
        try:
            data = {"records": [r.to_dict() for r in self._records.values()]}
            self._db_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            _log.warning("[Probation] Erreur sauvegarde: %s", exc)
