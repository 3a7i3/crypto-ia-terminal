"""
anomaly_governance.py — Anomaly Governance (P9)

Détecte et gère les anomalies comportementales du système.

4 types d'anomalies surveillées :
  TRADE_SPIKE       : nb trades soudainement > 10× la moyenne
  SCORE_DROP        : score moyen chute de 20+ points
  THRESHOLD_DRIFT   : threshold dérive > 5 points en 10 cycles
  RG_BURST          : RiskGovernor change d'état > 3 fois en 10 cycles

Réaction à chaque anomalie :
  1. Log snapshot de l'état système
  2. Suspension temporaire du composant concerné (cooldown_cycles)
  3. Recalcul paramètres par défaut suggéré
  4. Reprise progressive

Propriétés :
  - Governance cooldown : min N cycles entre deux interventions du même type
  - Historical crisis memory : N dernières crises
  - Governance entropy : mesure la rigidité du système (trop d'interventions = rigide)
"""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, List, Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.risk.anomaly_governance")


class AnomalyType(str, Enum):
    TRADE_SPIKE = "TRADE_SPIKE"
    SCORE_DROP = "SCORE_DROP"
    THRESHOLD_DRIFT = "THRESHOLD_DRIFT"
    RG_BURST = "RG_BURST"


@dataclass
class AnomalyRecord:
    anomaly_id: str
    anomaly_type: AnomalyType
    cycle: int
    description: str
    snapshot: Dict
    suspended_until_cycle: int
    resolved: bool = False
    ts: float = field(default_factory=time.time)


class AnomalyGovernance:
    """
    Détecte et répond aux anomalies comportementales système.

    Usage :
        gov = AnomalyGovernance()
        # Chaque cycle :
        anomalies = gov.detect(
            cycle=42,
            trades_this_cycle=5,
            avg_score=65.0,
            threshold_used=70,
            rg_state="DEFENSIVE",
        )
        for a in anomalies:
            log.warning("[P9/Gov] Anomalie: %s", a.description)
        # Vérifier si un composant est en suspension :
        if gov.is_suspended("execution", cycle=42): skip_execution()
    """

    def __init__(self) -> None:
        self._trade_window: Deque[int] = deque(maxlen=20)
        self._score_window: Deque[float] = deque(maxlen=10)
        self._threshold_window: Deque[float] = deque(maxlen=10)
        self._rg_states: Deque[str] = deque(maxlen=10)

        self._cooldown_cycles = int(os.getenv("P9_GOV_COOLDOWN", "15"))
        self._crisis_memory_size = int(os.getenv("P9_GOV_CRISIS_MEMORY", "50"))
        self._trade_spike_mult = float(os.getenv("P9_TRADE_SPIKE_MULT", "10.0"))
        self._score_drop_pts = float(os.getenv("P9_SCORE_DROP_PTS", "20.0"))
        self._threshold_drift_pts = float(os.getenv("P9_THRESHOLD_DRIFT_PTS", "5.0"))
        self._rg_burst_count = int(os.getenv("P9_RG_BURST_COUNT", "3"))
        self._suspension_cycles = int(os.getenv("P9_SUSPENSION_CYCLES", "10"))

        # Cooldowns par type (cycle de dernière intervention)
        self._last_intervention: Dict[str, int] = {}
        # Suspensions actives : composant → cycle_fin
        self._suspensions: Dict[str, int] = {}
        # Historique des crises
        self._crisis_memory: List[AnomalyRecord] = []
        self._anomaly_counter: int = 0
        self._total_interventions: int = 0

    # ── Détection ────────────────────────────────────────────────────────────

    def detect(
        self,
        cycle: int,
        trades_this_cycle: int = 0,
        avg_score: float = 0.0,
        threshold_used: float = 70.0,
        rg_state: str = "NORMAL",
        snapshot: Optional[Dict] = None,
    ) -> List[AnomalyRecord]:
        """
        Appelé 1 fois par cycle. Retourne liste des anomalies détectées.
        """
        self._trade_window.append(trades_this_cycle)
        self._score_window.append(avg_score)
        self._threshold_window.append(threshold_used)
        self._rg_states.append(rg_state)

        if snapshot is None:
            snapshot = {
                "cycle": cycle,
                "trades": trades_this_cycle,
                "avg_score": avg_score,
                "threshold": threshold_used,
                "rg_state": rg_state,
                "ts": time.time(),
            }

        anomalies: List[AnomalyRecord] = []

        checks = [
            (AnomalyType.TRADE_SPIKE, self._check_trade_spike),
            (AnomalyType.SCORE_DROP, self._check_score_drop),
            (AnomalyType.THRESHOLD_DRIFT, self._check_threshold_drift),
            (AnomalyType.RG_BURST, self._check_rg_burst),
        ]
        for atype, check_fn in checks:
            if self._in_cooldown(atype.value, cycle):
                continue
            desc = check_fn()
            if desc:
                rec = self._create_anomaly(atype, cycle, desc, snapshot)
                anomalies.append(rec)

        return anomalies

    # ── Consultation ─────────────────────────────────────────────────────────

    def is_suspended(self, component: str, cycle: int) -> bool:
        """True si le composant est en suspension ce cycle."""
        return self._suspensions.get(component, -1) >= cycle

    def governance_entropy(self) -> float:
        """
        Entropie de gouvernance [0, 1].
        0 = toujours le même type d'anomalie (rigide),
        1 = tous les types équitablement (diversité saine).
        """
        if not self._crisis_memory:
            return 1.0
        import math
        from collections import Counter

        counts = Counter(a.anomaly_type for a in self._crisis_memory)
        n = sum(counts.values())
        k = len(counts)
        if k <= 1:
            return 0.0
        entropy = -sum((c / n) * math.log(c / n) for c in counts.values())
        return entropy / math.log(k)

    def crisis_memory(self) -> List[AnomalyRecord]:
        return list(self._crisis_memory)

    def summary(self) -> dict:
        return {
            "total_interventions": self._total_interventions,
            "active_suspensions": len([c for c in self._suspensions.values() if c > 0]),
            "crisis_count": len(self._crisis_memory),
            "governance_entropy": round(self.governance_entropy(), 3),
        }

    # ── Checks internes ───────────────────────────────────────────────────────

    def _check_trade_spike(self) -> Optional[str]:
        trades = list(self._trade_window)
        if len(trades) < 5:
            return None
        baseline = trades[:-1]
        avg = sum(baseline) / len(baseline) if baseline else 0
        if avg <= 0:
            return None
        if trades[-1] > avg * self._trade_spike_mult:
            return (
                f"trades={trades[-1]} > {self._trade_spike_mult:.0f}× "
                f"moyenne={avg:.1f}"
            )
        return None

    def _check_score_drop(self) -> Optional[str]:
        scores = list(self._score_window)
        if len(scores) < 4:
            return None
        baseline_mean = sum(scores[:-2]) / max(len(scores) - 2, 1)
        recent_mean = sum(scores[-2:]) / 2
        drop = baseline_mean - recent_mean
        if drop >= self._score_drop_pts:
            return (
                f"score chute de {drop:.1f} pts "
                f"(baseline={baseline_mean:.1f} → récent={recent_mean:.1f})"
            )
        return None

    def _check_threshold_drift(self) -> Optional[str]:
        thrs = list(self._threshold_window)
        if len(thrs) < 5:
            return None
        drift = abs(thrs[-1] - thrs[0])
        if drift >= self._threshold_drift_pts:
            return (
                f"threshold dérive {drift:.1f} pts "
                f"({thrs[0]:.0f} → {thrs[-1]:.0f} en {len(thrs)} cycles)"
            )
        return None

    def _check_rg_burst(self) -> Optional[str]:
        states = list(self._rg_states)
        if len(states) < 4:
            return None
        transitions = sum(
            1 for i in range(1, len(states)) if states[i] != states[i - 1]
        )
        if transitions > self._rg_burst_count:
            return (
                f"RiskGovernor: {transitions} transitions "
                f"en {len(states)} cycles (max={self._rg_burst_count})"
            )
        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _in_cooldown(self, key: str, cycle: int) -> bool:
        last = self._last_intervention.get(key, -9999)
        return (cycle - last) < self._cooldown_cycles

    def _create_anomaly(
        self,
        atype: AnomalyType,
        cycle: int,
        desc: str,
        snapshot: Dict,
    ) -> AnomalyRecord:
        self._anomaly_counter += 1
        self._total_interventions += 1
        self._last_intervention[atype.value] = cycle

        # Suspension du composant concerné
        component_map = {
            AnomalyType.TRADE_SPIKE: "execution",
            AnomalyType.SCORE_DROP: "scoring",
            AnomalyType.THRESHOLD_DRIFT: "adaptive_threshold",
            AnomalyType.RG_BURST: "risk_governor",
        }
        comp = component_map.get(atype, "unknown")
        self._suspensions[comp] = cycle + self._suspension_cycles

        rec = AnomalyRecord(
            anomaly_id=f"{atype.value}_{cycle}_{self._anomaly_counter}",
            anomaly_type=atype,
            cycle=cycle,
            description=desc,
            snapshot=snapshot,
            suspended_until_cycle=cycle + self._suspension_cycles,
        )

        self._crisis_memory.append(rec)
        if len(self._crisis_memory) > self._crisis_memory_size:
            self._crisis_memory = self._crisis_memory[-self._crisis_memory_size :]

        _log.warning(
            "[P9/Gov] %s détectée cycle=%d composant=%s suspendu %d cycles : %s",
            atype.value,
            cycle,
            comp,
            self._suspension_cycles,
            desc,
        )
        return rec
