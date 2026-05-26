"""
self_monitoring_loop.py — Self-Monitoring Loop (P9)

Le système surveille sa propre surveillance.

meta_health_score [0.0, 1.0] agrège :
  0.4 × component_health_score  (SystemHealthMonitor)
  0.4 × drift_absence_score     (BehavioralDriftDetector)
  0.2 × transition_stability    (régularité des états RiskGovernor)

Si meta_health_score < P9_META_HEALTH_ALERT → alerte niveau 2.

Surveillance du détecteur lui-même :
  Si BehavioralDriftDetector émet > 1 alerte / 10 cycles pendant 3 cycles
  consécutifs → le détecteur lui-même est considéré instable.
"""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, List, Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.self_monitoring_loop")

_META_SCORE_ALERT_DEFAULT = 0.60
_BDD_FREQ_THRESHOLD = 1.0  # alertes / 10 cycles
_BDD_UNSTABLE_CONSECUTIVE = 3  # cycles consecutifs détecteur instable


@dataclass
class MetaHealthSnapshot:
    cycle: int
    meta_health_score: float
    component_health_score: float
    drift_absence_score: float
    transition_stability: float
    bdd_stable: bool
    level2_alert: bool
    ts: float = field(default_factory=time.time)


class SelfMonitoringLoop:
    """
    Agrège SystemHealthMonitor + BehavioralDriftDetector en un score global.

    Usage :
        sml = SelfMonitoringLoop()
        snap = sml.tick(cycle=42, health_monitor=hm, drift_detector=bdd,
                        rg_state="DEFENSIVE")
        if snap.level2_alert:
            log.critical(
                "[P9/Meta] Alerte niveau 2 — score=%.2f", snap.meta_health_score
            )
    """

    def __init__(self) -> None:
        self._alert_threshold = float(
            os.getenv("P9_META_HEALTH_ALERT", str(_META_SCORE_ALERT_DEFAULT))
        )
        self._bdd_freq_threshold = float(
            os.getenv("P9_BDD_FREQ_THRESHOLD", str(_BDD_FREQ_THRESHOLD))
        )
        self._bdd_unstable_cycles = int(
            os.getenv("P9_BDD_UNSTABLE_CYCLES", str(_BDD_UNSTABLE_CONSECUTIVE))
        )

        self._rg_states: Deque[str] = deque(maxlen=10)
        self._bdd_overactive_count: int = 0
        self._history: List[MetaHealthSnapshot] = []
        self._level2_alert_count: int = 0

    # ── Tick cycle ────────────────────────────────────────────────────────────

    def tick(
        self,
        cycle: int,
        health_monitor: Any,
        drift_detector: Any,
        rg_state: str = "NORMAL",
    ) -> MetaHealthSnapshot:
        """
        Appelé 1 fois par cycle.

        health_monitor : SystemHealthMonitor
        drift_detector : BehavioralDriftDetector
        rg_state       : état RiskGovernor actuel (string)
        """
        self._rg_states.append(rg_state)

        # ── Composant 1 : santé composants ───────────────────────────────────
        ch_score = self._compute_health_score(health_monitor)

        # ── Composant 2 : absence de dérive ──────────────────────────────────
        da_score = self._compute_drift_absence(drift_detector)

        # ── Composant 3 : stabilité des transitions RG ───────────────────────
        ts_score = self._compute_transition_stability()

        # ── Score global ─────────────────────────────────────────────────────
        meta = 0.4 * ch_score + 0.4 * da_score + 0.2 * ts_score

        # ── Surveillance du détecteur (méta-dérive) ───────────────────────────
        bdd_stable = self._check_bdd_stability(drift_detector)

        # ── Alerte niveau 2 ───────────────────────────────────────────────────
        level2 = meta < self._alert_threshold or not bdd_stable
        if level2:
            self._level2_alert_count += 1
            _log.critical(
                "[P9/Meta] ALERTE NIVEAU 2 cycle=%d score=%.3f "
                "health=%.2f drift=%.2f trans=%.2f bdd_stable=%s",
                cycle,
                meta,
                ch_score,
                da_score,
                ts_score,
                bdd_stable,
            )

        snap = MetaHealthSnapshot(
            cycle=cycle,
            meta_health_score=round(meta, 4),
            component_health_score=round(ch_score, 4),
            drift_absence_score=round(da_score, 4),
            transition_stability=round(ts_score, 4),
            bdd_stable=bdd_stable,
            level2_alert=level2,
        )
        self._history.append(snap)
        if len(self._history) > 200:
            self._history = self._history[-200:]
        return snap

    # ── Consultation ─────────────────────────────────────────────────────────

    @property
    def level2_alert_count(self) -> int:
        return self._level2_alert_count

    def last_snapshot(self) -> Optional[MetaHealthSnapshot]:
        return self._history[-1] if self._history else None

    def summary(self) -> dict:
        snap = self.last_snapshot()
        return {
            "meta_health_score": snap.meta_health_score if snap else 1.0,
            "level2_alerts_total": self._level2_alert_count,
            "last_level2_alert": snap.level2_alert if snap else False,
        }

    # ── Helpers privés ────────────────────────────────────────────────────────

    def _compute_health_score(self, hm: Any) -> float:
        if hm is None:
            return 1.0
        try:
            from quant_hedge_ai.agents.risk.system_health_monitor import ComponentStatus

            dashboard = hm.get_dashboard()
            if not dashboard:
                return 1.0
            scores = []
            for c in dashboard.values():
                if c.status == ComponentStatus.GREEN:
                    scores.append(1.0)
                elif c.status == ComponentStatus.YELLOW:
                    scores.append(0.5)
                else:
                    scores.append(0.0)
            return sum(scores) / len(scores)
        except Exception:
            return 1.0

    def _compute_drift_absence(self, bdd: Any) -> float:
        if bdd is None:
            return 1.0
        try:
            freq = bdd.alert_frequency  # alertes / 10 cycles
            # 0 alertes → 1.0, 1 alerte/cycle → 0.0
            return max(0.0, 1.0 - freq)
        except Exception:
            return 1.0

    def _compute_transition_stability(self) -> float:
        states = list(self._rg_states)
        if len(states) < 3:
            return 1.0
        transitions = sum(
            1 for i in range(1, len(states)) if states[i] != states[i - 1]
        )
        # 0 transitions → 1.0, ≥ 3 transitions / 10 cycles → 0.0
        return max(0.0, 1.0 - transitions / 3.0)

    def _check_bdd_stability(self, bdd: Any) -> bool:
        """
        Détecteur instable si alert_frequency > seuil depuis N cycles consécutifs.
        """
        if bdd is None:
            return True
        try:
            if bdd.alert_frequency > self._bdd_freq_threshold:
                self._bdd_overactive_count += 1
            else:
                self._bdd_overactive_count = 0
            if self._bdd_overactive_count >= self._bdd_unstable_cycles:
                _log.warning(
                    "[P9/Meta] BehavioralDriftDetector instable "
                    "freq=%.2f/10c depuis %d cycles",
                    bdd.alert_frequency,
                    self._bdd_overactive_count,
                )
                return False
            return True
        except Exception:
            return True
