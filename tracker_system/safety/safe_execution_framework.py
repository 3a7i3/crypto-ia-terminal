"""
ULTRA SAFE FUND MODE — Sécurité niveau hedge fund
Decision Throttling + Confidence + Rollback + Shadow Simulation
"""

from dataclasses import dataclass
from typing import Dict, Any, Tuple, Optional, List
from datetime import datetime, timedelta
import json


@dataclass
class SafetyConstraints:
    """Limites de sécurité strictes"""
    # Fréquence
    min_trades_before_decision: int = 20
    min_time_between_decisions: int = 6 * 3600  # 6 heures

    # Confidence
    min_confidence_for_action: float = 0.60

    # Changements
    max_tp_change: float = 0.30      # Max 30%
    max_sl_change: float = 0.30      # Max 30%
    max_risk_reduction: float = 0.50  # Min 50% de la position

    # Rollback
    max_performance_drop: float = 0.20  # 20% drop = rollback

    # Shadow simulation
    min_historical_trades: int = 20


class ConfidenceCalculator:
    """Calcule confidence score pour les décisions"""

    @staticmethod
    def calculate(metrics: Dict[str, Any]) -> float:
        """
        Confidence = moyenne pondérée de plusieurs facteurs

        Returns:
            score 0-1 (0=aucune confiance, 1=maximum)
        """
        score = 0.0
        weight_total = 0.0

        # Factor 1: Nombre de trades (data suffisante)
        num_trades = metrics.get("num_trades", 0)
        if num_trades > 30:
            score += 0.33  # Full weight
            weight_total += 0.33
        elif num_trades > 20:
            score += 0.20  # Partial weight
            weight_total += 0.33
        else:
            weight_total += 0.33  # Penality appliquée

        # Factor 2: Consistency (variance faible = consistant)
        consistency = metrics.get("consistency", 0)
        if consistency > 0.65:
            score += 0.33
        elif consistency > 0.50:
            score += 0.20
        weight_total += 0.33

        # Factor 3: Expectancy significatif
        expectancy = abs(metrics.get("expectancy", 0))
        if expectancy > 0.25:
            score += 0.34
        elif expectancy > 0.15:
            score += 0.20
        weight_total += 0.34

        # Normaliser
        confidence = score / weight_total if weight_total > 0 else 0.0
        return min(1.0, max(0.0, confidence))


class DecisionThrottler:
    """Limite la fréquence des décisions"""

    def __init__(self, constraints: SafetyConstraints):
        self.constraints = constraints
        self.last_decision_time = None
        self.trades_since_decision = 0
        self.active_change = False
        self.change_applied_time = None

    def can_make_decision(self) -> Tuple[bool, str]:
        """Vérifie si une décision est permise"""

        # Check 1: Lock sur changement actif
        if self.active_change:
            time_since = (datetime.utcnow() - self.change_applied_time).total_seconds()
            if time_since < 3600:  # 1 heure de stabilisation
                return False, "Active change lock - stabilizing"

        # Check 2: Minimum trades
        if self.trades_since_decision < self.constraints.min_trades_before_decision:
            return False, f"Need {self.constraints.min_trades_before_decision} trades before decision"

        # Check 3: Minimum time
        if self.last_decision_time:
            time_since = (datetime.utcnow() - self.last_decision_time).total_seconds()
            if time_since < self.constraints.min_time_between_decisions:
                return False, f"Wait {self.constraints.min_time_between_decisions}s before next decision"

        return True, "OK"

    def on_decision_made(self):
        """Appelé après une décision"""
        self.last_decision_time = datetime.utcnow()
        self.trades_since_decision = 0
        self.active_change = True
        self.change_applied_time = datetime.utcnow()

    def on_trade_executed(self):
        """Appelé après chaque trade"""
        self.trades_since_decision += 1

    def on_change_stable(self):
        """Appelé quand changement s'est montré stable"""
        self.active_change = False


class ShadowSimulator:
    """Simule une décision avant de l'appliquer"""

    def __init__(self, constraints: SafetyConstraints):
        self.constraints = constraints

    def simulate_decision(self,
                         decision_params: Dict[str, Any],
                         historical_trades: List[Dict]) -> Tuple[float, str]:
        """
        Simule une décision sur les derniers trades

        Args:
            decision_params: {"tp_factor": 1.15, "sl_factor": 0.85}
            historical_trades: Derniers trades

        Returns:
            (simulated_expectancy, reason)
        """

        if len(historical_trades) < self.constraints.min_historical_trades:
            return 0.0, "Not enough historical trades for simulation"

        # Appliquer les changements aux derniers trades
        simulated_pnl = []

        for trade in historical_trades[-20:]:
            original_pnl = trade.get("pnl_pct", 0)

            # Appliquer TP adjustment
            if "tp_factor" in decision_params:
                tp_factor = decision_params["tp_factor"]
                # Si TP augmente, trade dure plus longtemps
                if tp_factor > 1.0:
                    original_pnl *= 0.95  # Diminuer légèrement (moins de TP hits)
                else:
                    original_pnl *= 1.05  # Augmenter (plus de TP hits)

            # Appliquer SL adjustment
            if "sl_factor" in decision_params:
                sl_factor = decision_params["sl_factor"]
                # Si SL se réduit, plus de SL hits
                if sl_factor < 1.0:
                    original_pnl *= 0.98  # Pertes plus fréquentes

            simulated_pnl.append(original_pnl)

        # Calculer expectancy simulée
        simulated_expectancy = sum(simulated_pnl) / len(simulated_pnl) if simulated_pnl else 0

        # Comparer avec expectancy actuelle
        current_expectancy = sum(t.get("pnl_pct", 0) for t in historical_trades[-20:]) / 20

        if simulated_expectancy < current_expectancy * 0.95:
            reason = f"Simulation shows {simulated_expectancy:.2%} expectancy (current: {current_expectancy:.2%})"
            return simulated_expectancy, reason

        return simulated_expectancy, "Simulation approved"

    def should_reject(self, simulated_expectancy: float, current_expectancy: float) -> bool:
        """Décide si rejeter la décision"""
        if simulated_expectancy < current_expectancy * 0.95:
            return True
        return False


class PerformanceMonitor:
    """Monitore l'impact d'une décision"""

    def __init__(self, constraints: SafetyConstraints):
        self.constraints = constraints
        self.baseline_expectancy = 0.0
        self.decision_applied_time = None
        self.trades_since_decision = []

    def record_baseline(self, expectancy: float):
        """Enregistre la baseline avant un changement"""
        self.baseline_expectancy = expectancy
        self.decision_applied_time = datetime.utcnow()
        self.trades_since_decision = []

    def record_trade(self, pnl_pct: float):
        """Enregistre un trade après décision"""
        self.trades_since_decision.append(pnl_pct)

    def should_rollback(self) -> Tuple[bool, str]:
        """Vérifie si rollback est nécessaire"""

        if not self.trades_since_decision:
            return False, "Not enough trades to evaluate"

        if len(self.trades_since_decision) < 3:
            return False, "Wait for more trades before rollback check"

        # Calculer expectancy actuelle
        current_expectancy = sum(self.trades_since_decision) / len(self.trades_since_decision)

        # Vérifier si dégradation > seuil
        drop = (self.baseline_expectancy - current_expectancy) / abs(self.baseline_expectancy) if self.baseline_expectancy != 0 else 0

        if drop > self.constraints.max_performance_drop:
            return True, f"Performance dropped by {drop:.1%} (threshold: {self.constraints.max_performance_drop:.1%})"

        return False, "Performance stable"


class SafeExecutionFramework:
    """Framework complet de sécurité ultra-safe"""

    def __init__(self, constraints: SafetyConstraints = None):
        self.constraints = constraints or SafetyConstraints()
        self.confidence_calc = ConfidenceCalculator()
        self.throttler = DecisionThrottler(self.constraints)
        self.shadow_sim = ShadowSimulator(self.constraints)
        self.perf_monitor = PerformanceMonitor(self.constraints)

        self.decision_history = []
        self.rollback_history = []
        self.config_snapshots = []

    def execute_decision(self,
                        decision: Dict[str, Any],
                        metrics: Dict[str, Any],
                        historical_trades: List[Dict],
                        current_config: Dict[str, Any]) -> Tuple[Dict, bool, str]:
        """
        Exécute une décision avec TOUS les garde-fou

        Returns:
            (new_config, executed, reason)
        """

        # STEP 1: Confidence check
        confidence = self.confidence_calc.calculate(metrics)
        if confidence < self.constraints.min_confidence_for_action:
            return current_config, False, f"Low confidence ({confidence:.1%}) < {self.constraints.min_confidence_for_action:.1%}"

        # STEP 2: Throttling check
        can_decide, throttle_reason = self.throttler.can_make_decision()
        if not can_decide:
            return current_config, False, f"Throttled: {throttle_reason}"

        # STEP 3: Shadow simulation
        sim_expectancy, sim_reason = self.shadow_sim.simulate_decision(
            decision.get("params", {}),
            historical_trades
        )

        current_expectancy = metrics.get("expectancy", 0)
        if self.shadow_sim.should_reject(sim_expectancy, current_expectancy):
            return current_config, False, f"Shadow rejected: {sim_reason}"

        # STEP 4: Save snapshot
        self.config_snapshots.append(current_config.copy())
        baseline_expectancy = metrics.get("expectancy", 0)
        self.perf_monitor.record_baseline(baseline_expectancy)

        # STEP 5: Apply decision
        new_config = self._apply_decision(current_config, decision)

        # STEP 6: Log
        self.decision_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "decision": decision,
            "confidence": confidence,
            "simulated_expectancy": sim_expectancy,
            "executed": True
        })

        # STEP 7: Throttler state
        self.throttler.on_decision_made()

        return new_config, True, f"Decision executed (confidence: {confidence:.1%})"

    def _apply_decision(self, config: Dict, decision: Dict) -> Dict:
        """Applique la décision à la config"""
        new_config = config.copy()
        params = decision.get("params", {})

        # Validation stricte de chaque changement
        if "tp_factor" in params:
            factor = params["tp_factor"]
            if abs(factor - 1.0) <= self.constraints.max_tp_change:
                new_config["tp"] = config["tp"] * factor

        if "sl_factor" in params:
            factor = params["sl_factor"]
            if abs(factor - 1.0) <= self.constraints.max_sl_change:
                new_config["sl"] = config["sl"] * factor

        if "position_size_factor" in params:
            factor = params["position_size_factor"]
            if factor >= (1 - self.constraints.max_risk_reduction):
                new_config["position_size"] = config["position_size"] * factor

        return new_config

    def record_trade(self, pnl_pct: float) -> Optional[str]:
        """Enregistre un trade et vérifie si rollback"""
        self.perf_monitor.record_trade(pnl_pct)
        self.throttler.on_trade_executed()

        # Vérifier rollback après ~3 trades
        should_rb, reason = self.perf_monitor.should_rollback()
        if should_rb and self.config_snapshots:
            # Rollback to previous config
            self.rollback_history.append({
                "timestamp": datetime.utcnow().isoformat(),
                "reason": reason
            })
            return reason

        return None

    def get_status(self) -> Dict[str, Any]:
        """Statut du framework de sécurité"""
        return {
            "decisions_executed": len(self.decision_history),
            "rollbacks_triggered": len(self.rollback_history),
            "active_throttle": self.throttler.active_change,
            "trades_since_decision": self.throttler.trades_since_decision,
            "last_decision": self.decision_history[-1] if self.decision_history else None,
            "last_rollback": self.rollback_history[-1] if self.rollback_history else None,
        }
