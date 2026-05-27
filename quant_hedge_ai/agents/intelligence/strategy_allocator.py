"""
strategy_allocator.py — Strategy Allocator (P8)

Orchestrateur principal de l'allocation dynamique du capital entre stratégies.

Pipeline par cycle :
  1. Matrice contextuelle régime → poids cibles
  2. Rampe de transition (asymétrique : +0.03/cycle hausse, -0.08/cycle baisse)
  2b. DynamicWeightingEngine — ajustement par performance relative tri-temporelle
  3. Facteurs probation (TRACKING=0, PROBATION=25%, ACTIVE=rampe 30→100%)
  3b. Energy budget — shadow mode si budget trades épuisé
  4. Pénalités de corrélation (CorrelationMonitor)
  5. Floor 0.05 / ceiling 0.60 par stratégie active
  6. Normalisation
  7. Contrainte d'entropie (min 0.60) — anti-monoculture
  8. Shock absorber global (max 25% de l'allocation totale par cycle)
  8b. Anticipation de transition de régime (pré-positionnement à 30%)
  9. Calcul capital_usd = capital_total × exposure_factor × poids
 10. Capital efficiency check (réduction si utilisé < 30% sur 20 cycles)
 11. Audit trail complet

Env vars clés :
  P8_RAMP_UP_MAX, P8_RAMP_DOWN_MAX, P8_FLOOR_WEIGHT, P8_CEILING_WEIGHT,
  P8_MIN_ENTROPY, P8_SHOCK_MAX_DELTA, ALLOCATOR_DB,
  P8_ENERGY_BUDGETS (JSON), P8_TRANSITION_PREPOS_PROB, P8_EFFICIENCY_MIN,
  P8_EFFICIENCY_WINDOW
"""

from __future__ import annotations

import json
import math
import os
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque, Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.strategy_allocator")
_DB_PATH = Path(os.getenv("ALLOCATOR_DB", "databases/strategy_allocator.json"))

# ── Paramètres dynamiques ──────────────────────────────────────────────────────

_RAMP_UP_MAX = float(os.getenv("P8_RAMP_UP_MAX", "0.03"))  # hausse max/cycle (lente)
_RAMP_DOWN_MAX = float(
    os.getenv("P8_RAMP_DOWN_MAX", "0.08")
)  # baisse max/cycle (rapide)
_FLOOR_WEIGHT = float(
    os.getenv("P8_FLOOR_WEIGHT", "0.05")
)  # plancher par stratégie active
_CEILING_WEIGHT = float(
    os.getenv("P8_CEILING_WEIGHT", "0.60")
)  # plafond anti-domination
_MIN_ENTROPY = float(os.getenv("P8_MIN_ENTROPY", "0.60"))  # diversité minimale
_SHOCK_MAX_DELTA = float(
    os.getenv("P8_SHOCK_MAX_DELTA", "0.25")
)  # delta total max/cycle
_PERF_W_SHORT = float(os.getenv("P8_PERF_W_SHORT", "0.50"))  # fenêtre 20 cycles
_PERF_W_MED = float(os.getenv("P8_PERF_W_MED", "0.30"))  # fenêtre 50 cycles
_PERF_W_FULL = float(os.getenv("P8_PERF_W_FULL", "0.20"))  # historique complet

# Anticipation de transition : pré-positionner si prob > seuil
_TRANSITION_PREPOS_PROB = float(os.getenv("P8_TRANSITION_PREPOS_PROB", "0.60"))
_TRANSITION_PREPOS_FACTOR = 0.30  # pré-positionner 30% du delta vers régime cible

# Capital efficiency : réduction si utilisation < seuil sur N cycles
_EFFICIENCY_MIN = float(os.getenv("P8_EFFICIENCY_MIN", "0.30"))
_EFFICIENCY_WINDOW = int(os.getenv("P8_EFFICIENCY_WINDOW", "20"))
_EFFICIENCY_REDUCTION = 0.20  # réduire le poids de 20% si sous-utilisé

# Multiplicateur du ramp cap par état RiskGovernor
_MOMENTUM_MULT: dict[str, float] = {
    "AGGRESSIVE": 1.6,
    "NORMAL": 1.0,
    "DEFENSIVE": 0.4,
    "RECOVERY": 0.5,
    "RISK_OFF": 0.0,
}

# ── Stratégies P8 ─────────────────────────────────────────────────────────────

STRATEGY_IDS: list[str] = ["mean_reversion", "breakout", "scalp", "momentum", "grid"]

# Mapping personnalité MetaStrategyEngine → strategy_id P8
PERSONALITY_TO_STRATEGY: dict[str, str] = {
    "momentum_following": "momentum",
    "defensive_short": "momentum",
    "mean_reversion": "mean_reversion",
    "scalping_mode": "scalp",
    "capital_protection": "scalp",  # mode défensif → scalp (petites tailles)
    "neutral": "mean_reversion",
}

# ── Matrice d'allocation de base ───────────────────────────────────────────────

BASE_ALLOCATION_MATRIX: dict[str, dict[str, float]] = {
    "SIDEWAYS": {
        "mean_reversion": 0.45,
        "breakout": 0.10,
        "scalp": 0.30,
        "momentum": 0.05,
        "grid": 0.10,
    },
    "TREND_BULL": {
        "mean_reversion": 0.10,
        "breakout": 0.40,
        "scalp": 0.05,
        "momentum": 0.35,
        "grid": 0.10,
    },
    "TREND_BEAR": {
        "mean_reversion": 0.15,
        "breakout": 0.20,
        "scalp": 0.10,
        "momentum": 0.40,
        "grid": 0.15,
    },
    "HIGH_VOL": {
        "mean_reversion": 0.10,
        "breakout": 0.10,
        "scalp": 0.40,
        "momentum": 0.10,
        "grid": 0.30,
    },
    "CHOPPY": {
        "mean_reversion": 0.30,
        "breakout": 0.10,
        "scalp": 0.25,
        "momentum": 0.10,
        "grid": 0.25,
    },
    "UNKNOWN": {
        "mean_reversion": 0.20,
        "breakout": 0.20,
        "scalp": 0.20,
        "momentum": 0.20,
        "grid": 0.20,
    },
}

_REGIME_NORM: dict[str, str] = {
    "bull_trend": "TREND_BULL",
    "TREND_BULL": "TREND_BULL",
    "bear_trend": "TREND_BEAR",
    "TREND_BEAR": "TREND_BEAR",
    "sideways": "SIDEWAYS",
    "SIDEWAYS": "SIDEWAYS",
    "high_volatility_regime": "HIGH_VOL",
    "high_volatility": "HIGH_VOL",
    "HIGH_VOL": "HIGH_VOL",
    "flash_crash": "UNKNOWN",
    "choppy": "CHOPPY",
    "CHOPPY": "CHOPPY",
    "unknown": "UNKNOWN",
    "UNKNOWN": "UNKNOWN",
}


class EnergyBudgetManager:
    """
    Budget de trades par session par stratégie.
    Une stratégie en shadow mode quand son budget est épuisé.

    Usage :
        ebm = EnergyBudgetManager({"scalp": 200, "grid": 30})
        if ebm.can_trade("scalp"):
            ebm.record_trade("scalp")
        ebm.reset_session()   # début de chaque session
    """

    _DEFAULT_BUDGETS: dict[str, int] = {
        "scalp": 200,
        "mean_reversion": 50,
        "breakout": 40,
        "momentum": 60,
        "grid": 30,
    }

    def __init__(self, budgets: Optional[dict[str, int]] = None) -> None:
        raw = os.getenv("P8_ENERGY_BUDGETS")
        if raw:
            try:
                env_budgets: dict[str, int] = json.loads(raw)
                self._budgets = {k: int(v) for k, v in env_budgets.items()}
            except Exception:
                self._budgets = dict(budgets or self._DEFAULT_BUDGETS)
        else:
            self._budgets = dict(budgets or self._DEFAULT_BUDGETS)
        self._used: dict[str, int] = {sid: 0 for sid in self._budgets}
        self._session: int = 0

    def can_trade(self, strategy_id: str) -> bool:
        """True si la stratégie peut encore trader cette session."""
        budget = self._budgets.get(strategy_id)
        if budget is None:
            return True
        return self._used.get(strategy_id, 0) < budget

    def record_trade(self, strategy_id: str) -> None:
        if strategy_id in self._used:
            self._used[strategy_id] += 1

    def capital_factor(self, strategy_id: str) -> float:
        """0.0 quand budget épuisé (shadow mode), 1.0 sinon."""
        return 1.0 if self.can_trade(strategy_id) else 0.0

    def reset_session(self) -> None:
        """Réinitialise les compteurs au début d'une nouvelle session."""
        self._used = {sid: 0 for sid in self._budgets}
        self._session += 1
        _log.info("[EnergyBudget] Session %d réinitialisée", self._session)

    def utilization(self) -> dict[str, float]:
        """Fraction du budget utilisée par stratégie [0.0, 1.0]."""
        result = {}
        for sid, budget in self._budgets.items():
            result[sid] = self._used.get(sid, 0) / budget if budget > 0 else 0.0
        return result

    def snapshot(self) -> dict:
        return {
            "session": self._session,
            "used": dict(self._used),
            "budgets": dict(self._budgets),
            "utilization": {k: round(v, 3) for k, v in self.utilization().items()},
        }


class CapitalEfficiencyTracker:
    """
    Suit le ratio capital utilisé / capital alloué par stratégie.
    Signale les stratégies sous-utilisées (efficiency < 30% sur 20 cycles).

    Usage :
        cet = CapitalEfficiencyTracker()
        cet.record("scalp", allocated_usd=5000, used_usd=1200)
        inefficient = cet.get_underutilized()  # → ["scalp"]
    """

    def __init__(self) -> None:
        self._window: dict[str, Deque[float]] = {}

    def record(self, strategy_id: str, allocated_usd: float, used_usd: float) -> None:
        """Enregistre le ratio d'utilisation pour ce cycle."""
        if allocated_usd < 1e-6:
            return
        ratio = min(1.0, used_usd / allocated_usd)
        if strategy_id not in self._window:
            self._window[strategy_id] = deque(maxlen=_EFFICIENCY_WINDOW)
        self._window[strategy_id].append(ratio)

    def efficiency(self, strategy_id: str) -> float:
        """Ratio moyen d'utilisation sur la fenêtre. 1.0 si pas de données."""
        buf = self._window.get(strategy_id)
        if not buf:
            return 1.0
        return sum(buf) / len(buf)

    def get_underutilized(self, threshold: float = _EFFICIENCY_MIN) -> list[str]:
        """Stratégies avec efficiency < threshold sur toute la fenêtre."""
        result = []
        for sid, buf in self._window.items():
            if len(buf) >= _EFFICIENCY_WINDOW and self.efficiency(sid) < threshold:
                result.append(sid)
        return result

    def weight_reduction_factor(self, strategy_id: str) -> float:
        """
        Facteur de réduction à appliquer au poids.
        1.0 = pas de réduction, (1 - _EFFICIENCY_REDUCTION) si sous-utilisé.
        """
        if strategy_id in self.get_underutilized():
            return 1.0 - _EFFICIENCY_REDUCTION
        return 1.0

    def snapshot(self) -> dict:
        return {
            sid: {
                "efficiency": round(self.efficiency(sid), 3),
                "underutilized": sid in self.get_underutilized(),
                "samples": len(buf),
            }
            for sid, buf in self._window.items()
        }


@dataclass
class AllocationResult:
    cycle: int
    regime: str
    risk_state: str
    weights: dict[str, float]
    capital_usd: dict[str, float]
    exposure_factor: float
    entropy: float
    audit_events: list[dict] = field(default_factory=list)

    def capital_for(self, strategy_id: str) -> float:
        return self.capital_usd.get(strategy_id, 0.0)

    def summary(self) -> str:
        top = sorted(self.weights.items(), key=lambda x: x[1], reverse=True)[:3]
        parts = " | ".join(f"{k}={v:.0%}" for k, v in top)
        return (
            f"[Allocator] {self.regime}/{self.risk_state} H={self.entropy:.2f} {parts}"
        )


class StrategyAllocator:
    """
    Alloue le capital entre stratégies de manière dynamique et contextuelle.
    Intègre : matrice régime, probation, corrélation, entropie, audit trail.
    """

    def __init__(
        self,
        probation_system=None,
        confidence_scorers: Optional[dict] = None,
        correlation_monitor=None,
        energy_budget: Optional[EnergyBudgetManager] = None,
    ) -> None:
        self._db_path = Path(
            os.getenv("ALLOCATOR_DB", "databases/strategy_allocator.json")
        )
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._probation = probation_system
        self._scorers: dict[str, object] = confidence_scorers or {}
        self._corr = correlation_monitor
        self._energy = energy_budget or EnergyBudgetManager()
        self._efficiency = CapitalEfficiencyTracker()

        # DynamicWeightingEngine — import lazy pour éviter la circularité
        try:
            from quant_hedge_ai.agents.intelligence.dynamic_weighting_engine import (
                DynamicWeightingEngine,
            )

            self._dwe: Optional[object] = DynamicWeightingEngine(STRATEGY_IDS)
        except Exception:
            self._dwe = None

        eq = 1.0 / len(STRATEGY_IDS)
        self._weights: dict[str, float] = {sid: eq for sid in STRATEGY_IDS}
        self._prev_weights: dict[str, float] = dict(self._weights)

        # Performance history pour le weighting adaptatif (legacy — aussi dans DWE)
        self._perf_short: dict[str, list[float]] = {sid: [] for sid in STRATEGY_IDS}
        self._perf_med: dict[str, list[float]] = {sid: [] for sid in STRATEGY_IDS}
        self._perf_full: dict[str, dict] = {
            sid: {"sum": 0.0, "count": 0} for sid in STRATEGY_IDS
        }

        self._current_regime: str = "UNKNOWN"
        self._overrides: dict[str, dict] = {}
        self._audit_log: list[dict] = []
        self._load()

    # ── Cycle principal ────────────────────────────────────────────────────────

    def allocate(
        self,
        cycle: int,
        regime: str,
        risk_state: str,
        capital_total: float,
        exposure_factor: float,
        transition_forecast: Optional[tuple[str, float]] = None,
    ) -> AllocationResult:
        """
        Retourne les allocations capital_usd par stratégie.

        exposure_factor      : RiskGovernor.size_multiplier [0.0, 1.2]
        transition_forecast  : (next_regime, prob) depuis RegimeTransitionPredictor
                               Si prob > P8_TRANSITION_PREPOS_PROB, pré-positionne 30%.
        """
        norm_regime = _REGIME_NORM.get(regime, "UNKNOWN")
        audit: list[dict] = []
        mult = _MOMENTUM_MULT.get(risk_state, 1.0)
        ramp_up = _RAMP_UP_MAX * mult
        ramp_down = _RAMP_DOWN_MAX * mult

        matrix = BASE_ALLOCATION_MATRIX.get(
            norm_regime, BASE_ALLOCATION_MATRIX["UNKNOWN"]
        )

        # 1. Rampe vers poids cibles (asymétrique)
        w = {}
        for sid in STRATEGY_IDS:
            cur = self._weights.get(sid, 1.0 / len(STRATEGY_IDS))
            ov = self._overrides.get(sid)
            if ov and cycle <= ov.get("until_cycle", 0):
                if ov.get("frozen"):
                    w[sid] = cur
                    continue
                if "fixed_weight" in ov:
                    w[sid] = float(ov["fixed_weight"])
                    continue
            tgt = matrix.get(sid, 1.0 / len(STRATEGY_IDS))
            delta = tgt - cur
            if delta > 0:
                delta = min(delta, ramp_up)
            else:
                delta = max(delta, -ramp_down)
            w[sid] = cur + delta

        # 1b. DynamicWeightingEngine — ajustement par performance relative
        if self._dwe is not None:
            try:
                w = self._dwe.adjust(w, risk_state=risk_state)
                audit.append({"type": "dwe_adjust", "scores": self._dwe.scores()})
            except Exception as _dwe_exc:
                _log.debug("[Allocator] DWE skip: %s", _dwe_exc)

        # 2. Facteurs probation
        if self._probation:
            for sid in STRATEGY_IDS:
                prob_factor = self._probation.capital_factor(sid)
                w[sid] *= prob_factor

        # 2b. Energy budget — shadow mode si budget épuisé
        for sid in STRATEGY_IDS:
            if not self._energy.can_trade(sid):
                old = w[sid]
                w[sid] = 0.0
                audit.append(
                    {
                        "type": "energy_budget_exhausted",
                        "strategy": sid,
                        "from": round(old, 3),
                    }
                )

        # 3. Pénalités corrélation
        if self._corr:
            comp_scores = {
                sid: (self._scorers[sid].confidence if sid in self._scorers else 0.5)
                for sid in STRATEGY_IDS
            }
            penalties = self._corr.get_weight_penalties(norm_regime, comp_scores)
            for sid, pen in penalties.items():
                if sid in w and pen > 0:
                    old = w[sid]
                    w[sid] = max(0.0, w[sid] * (1.0 - pen))
                    audit.append(
                        {
                            "type": "corr_penalty",
                            "strategy": sid,
                            "penalty": round(pen, 3),
                            "from": round(old, 3),
                        }
                    )

        # 4. Floor et ceiling
        for sid in STRATEGY_IDS:
            if w[sid] <= 1e-9:
                continue
            w[sid] = max(_FLOOR_WEIGHT, min(_CEILING_WEIGHT, w[sid]))

        # 5. Normalisation
        total = sum(w.values())
        if total > 1e-9:
            for sid in w:
                w[sid] /= total
        else:
            for sid in w:
                w[sid] = 1.0 / len(STRATEGY_IDS)

        # 6. Contrainte d'entropie
        entropy = _entropy(list(w.values()))
        if entropy < _MIN_ENTROPY:
            w = self._enforce_entropy(w)
            entropy = _entropy(list(w.values()))
            audit.append(
                {"type": "entropy_enforced", "entropy_after": round(entropy, 3)}
            )

        # 7. Shock absorber global
        total_delta = sum(
            abs(w[sid] - self._prev_weights.get(sid, 1.0 / len(STRATEGY_IDS)))
            for sid in STRATEGY_IDS
        )
        if total_delta > _SHOCK_MAX_DELTA:
            scale = _SHOCK_MAX_DELTA / total_delta
            for sid in STRATEGY_IDS:
                prev = self._prev_weights.get(sid, 1.0 / len(STRATEGY_IDS))
                w[sid] = prev + (w[sid] - prev) * scale
            s = sum(w.values())
            if s > 1e-9:
                for sid in w:
                    w[sid] /= s
            audit.append(
                {
                    "type": "shock_absorber",
                    "total_delta": round(total_delta, 3),
                    "scale": round(scale, 3),
                }
            )

        # 7b. Anticipation de transition de régime
        if transition_forecast is not None:
            next_regime, next_prob = transition_forecast
            if next_prob >= _TRANSITION_PREPOS_PROB:
                next_matrix = BASE_ALLOCATION_MATRIX.get(
                    _REGIME_NORM.get(next_regime, "UNKNOWN"),
                    BASE_ALLOCATION_MATRIX["UNKNOWN"],
                )
                for sid in STRATEGY_IDS:
                    tgt_next = next_matrix.get(sid, 1.0 / len(STRATEGY_IDS))
                    pre_delta = (tgt_next - w[sid]) * _TRANSITION_PREPOS_FACTOR
                    w[sid] = max(0.0, w[sid] + pre_delta)
                s = sum(w.values())
                if s > 1e-9:
                    for sid in w:
                        w[sid] /= s
                audit.append(
                    {
                        "type": "transition_anticipation",
                        "next_regime": next_regime,
                        "probability": round(next_prob, 3),
                        "prepos_factor": _TRANSITION_PREPOS_FACTOR,
                    }
                )
                _log.info(
                    "[Allocator] Anticipation transition → %s (prob=%.0f%%)",
                    next_regime,
                    next_prob * 100,
                )

        # 7c. Capital efficiency — réduire les stratégies sous-utilisées
        underutilized = self._efficiency.get_underutilized()
        if underutilized:
            freed = 0.0
            for sid in underutilized:
                reduction = w[sid] * _EFFICIENCY_REDUCTION
                w[sid] -= reduction
                freed += reduction
                audit.append(
                    {
                        "type": "efficiency_reduction",
                        "strategy": sid,
                        "efficiency": round(self._efficiency.efficiency(sid), 3),
                        "reduction": round(reduction, 4),
                    }
                )
            # Redistribuer aux bien-utilisées proportionnellement
            well_used = [
                sid
                for sid in STRATEGY_IDS
                if sid not in underutilized and w.get(sid, 0) > 1e-9
            ]
            if well_used and freed > 0:
                total_wu = sum(w[sid] for sid in well_used)
                for sid in well_used:
                    w[sid] += freed * (w[sid] / total_wu)
            s = sum(w.values())
            if s > 1e-9:
                for sid in w:
                    w[sid] /= s

        # 8. Capital USD par stratégie
        eff_capital = capital_total * max(0.0, exposure_factor)
        capital_usd = {sid: eff_capital * w.get(sid, 0.0) for sid in STRATEGY_IDS}

        # 9. Audit trail
        entry = {
            "cycle": cycle,
            "regime": norm_regime,
            "risk_state": risk_state,
            "exposure_factor": round(exposure_factor, 3),
            "entropy": round(entropy, 3),
            "weights": {k: round(v, 4) for k, v in w.items()},
            "prev_weights": {k: round(v, 4) for k, v in self._prev_weights.items()},
            "capital_usd": {k: round(v, 2) for k, v in capital_usd.items()},
            "events": audit,
            "ts": time.time(),
        }
        self._audit_log.append(entry)
        if len(self._audit_log) > 1000:
            self._audit_log = self._audit_log[-1000:]

        self._prev_weights = dict(w)
        self._weights = dict(w)
        self._current_regime = norm_regime

        result = AllocationResult(
            cycle=cycle,
            regime=norm_regime,
            risk_state=risk_state,
            weights=dict(w),
            capital_usd=capital_usd,
            exposure_factor=exposure_factor,
            entropy=round(entropy, 3),
            audit_events=audit,
        )
        _log.info("[Allocator] %s", result.summary())
        self._save()
        return result

    def record_performance(
        self, strategy_id: str, pnl_pct: float, sharpe: float = 0.0
    ) -> None:
        """Enregistre la performance pour le weighting adaptatif (DWE + legacy)."""
        if strategy_id not in STRATEGY_IDS:
            return
        # DWE
        if self._dwe is not None:
            try:
                self._dwe.record(strategy_id, pnl_pct, sharpe)
            except Exception:
                pass
        # Legacy buffers
        perf = pnl_pct * 0.6 + sharpe * 0.4
        q = self._perf_short[strategy_id]
        q.append(perf)
        if len(q) > 20:
            q.pop(0)
        q2 = self._perf_med[strategy_id]
        q2.append(perf)
        if len(q2) > 50:
            q2.pop(0)
        f = self._perf_full[strategy_id]
        f["sum"] += perf
        f["count"] += 1

    def record_capital_used(
        self, strategy_id: str, allocated_usd: float, used_usd: float
    ) -> None:
        """Enregistre le capital utilisé dans le capital efficiency tracker."""
        self._efficiency.record(strategy_id, allocated_usd, used_usd)

    def record_trade_executed(self, strategy_id: str) -> None:
        """Incrémente le compteur du budget de trades pour cette session."""
        self._energy.record_trade(strategy_id)

    def reset_energy_session(self) -> None:
        """Réinitialise les budgets de trades (début de session)."""
        self._energy.reset_session()

    def performance_score(self, strategy_id: str) -> float:
        """Score composite pondéré court/moyen/long terme."""
        short = self._perf_short.get(strategy_id, [])
        med = self._perf_med.get(strategy_id, [])
        full = self._perf_full.get(strategy_id, {"sum": 0.0, "count": 0})
        s = sum(short) / len(short) if short else 0.0
        m = sum(med) / len(med) if med else 0.0
        f = full["sum"] / full["count"] if full["count"] > 0 else 0.0
        return s * _PERF_W_SHORT + m * _PERF_W_MED + f * _PERF_W_FULL

    def set_override(
        self,
        strategy_id: str,
        until_cycle: int,
        fixed_weight: Optional[float] = None,
        frozen: bool = False,
        reason: str = "",
    ) -> None:
        """Human override API — gèle ou fixe le poids d'une stratégie."""
        self._overrides[strategy_id] = {
            "until_cycle": until_cycle,
            "fixed_weight": fixed_weight,
            "frozen": frozen,
            "reason": reason,
        }
        _log.warning(
            "[Allocator] Override %s until cycle %d (%s)",
            strategy_id,
            until_cycle,
            reason,
        )
        self._save()

    def clear_override(self, strategy_id: str) -> None:
        self._overrides.pop(strategy_id, None)
        self._save()

    def snapshot(self) -> dict:
        return {
            "weights": {k: round(v, 4) for k, v in self._weights.items()},
            "regime": self._current_regime,
            "entropy": round(_entropy(list(self._weights.values())), 3),
            "overrides": {k: v for k, v in self._overrides.items()},
            "energy": self._energy.snapshot(),
            "efficiency": self._efficiency.snapshot(),
            "dwe_scores": self._dwe.scores() if self._dwe else {},
        }

    def audit_recent(self, n: int = 10) -> list[dict]:
        return self._audit_log[-n:]

    # ── Entropy enforcement ────────────────────────────────────────────────────

    def _enforce_entropy(self, weights: dict[str, float]) -> dict[str, float]:
        """Redistribue 15% du capital du dominant vers les stratégies plus petites."""
        dominant = max(weights, key=lambda k: weights[k])
        surplus = weights[dominant] * 0.15
        weights[dominant] -= surplus
        others = [k for k in weights if k != dominant and weights[k] > 1e-9]
        if others:
            share = surplus / len(others)
            for sid in others:
                weights[sid] += share
        total = sum(weights.values())
        if total > 1e-9:
            for sid in weights:
                weights[sid] /= total
        return weights

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._db_path.exists():
            return
        try:
            data = json.loads(self._db_path.read_text(encoding="utf-8"))
            self._weights = data.get("weights", self._weights)
            self._prev_weights = dict(self._weights)
            self._overrides = data.get("overrides", {})
            self._perf_short = data.get("perf_short", self._perf_short)
            self._perf_med = data.get("perf_med", self._perf_med)
            self._perf_full = data.get("perf_full", self._perf_full)
            self._audit_log = data.get("audit_log", [])[-200:]
            _log.info(
                "[Allocator] Chargé: %s",
                {k: round(v, 3) for k, v in self._weights.items()},
            )
        except Exception as exc:
            _log.warning("[Allocator] Erreur chargement: %s", exc)

    def _save(self) -> None:
        try:
            data = {
                "weights": {k: round(v, 6) for k, v in self._weights.items()},
                "overrides": self._overrides,
                "perf_short": self._perf_short,
                "perf_med": self._perf_med,
                "perf_full": self._perf_full,
                "audit_log": self._audit_log[-200:],
            }
            self._db_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            _log.warning("[Allocator] Erreur sauvegarde: %s", exc)


def _entropy(weights: list[float]) -> float:
    """Entropie de Shannon normalisée. 1.0=parfaite diversité, 0.0=monoculture."""
    probs = [w for w in weights if w > 1e-9]
    if len(probs) < 2:
        return 0.0
    raw = -sum(p * math.log(p) for p in probs)
    return raw / math.log(len(probs))
