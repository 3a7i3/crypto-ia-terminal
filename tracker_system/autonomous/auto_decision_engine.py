"""
AUTO DECISION ENGINE — Système autonome contrôlé
Observe → Décide → Agit → Contrôle → Apprend
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime
import json


@dataclass
class Decision:
    """Représente une décision du système"""
    action: str  # ADJUST_TP, ADJUST_SL, REDUCE_RISK, STOP_TRADING, APPLY_META, NO_ACTION
    params: Dict[str, Any]
    reason: str
    confidence: float = 0.5
    timestamp: str = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()


class AutoDecisionEngine:
    """Moteur de décision automatique"""

    # Actions possibles (SEULEMENT CES 3)
    ACTIONS = [
        "ADJUST_TP",      # Augmenter TP si exits trop tôt
        "ADJUST_SL",      # Réduire SL si MAE trop élevé
        "REDUCE_RISK",    # Réduire taille position si streak de pertes
        "STOP_TRADING",   # Arrêt si DD trop élevé
        "APPLY_META",     # Appliquer config meta-learning
        "NO_ACTION",      # Rien faire
    ]

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: Paramètres de trading actuels
        """
        self.config = config

    def decide(self,
              metrics: Dict[str, Any],
              meta_suggestion: Optional[Dict] = None,
              risk_state: Optional[Dict] = None) -> Decision:
        """
        Prend une décision basée sur:
        1. Métriques de performance
        2. Suggestions meta-learning
        3. État du risque

        Priorité:
        1. Risk first (arrêt si dangereux)
        2. Réduction risque (loss streak)
        3. Optimisation exits (efficiency)
        4. Meta-learning suggestion
        """

        # PRIORITY 1: RISK CONTROL
        if risk_state:
            # Drawdown trop élevé
            if risk_state.get("drawdown", 0) > 0.05:
                return Decision(
                    action="STOP_TRADING",
                    params={},
                    reason="Drawdown > 5% - stopping to prevent catastrophic loss",
                    confidence=0.95
                )

            # Streak de pertes
            loss_streak = risk_state.get("loss_streak", 0)
            if loss_streak >= 4:
                return Decision(
                    action="REDUCE_RISK",
                    params={"position_size_factor": 0.5},
                    reason=f"Loss streak of {loss_streak} detected - reducing position size",
                    confidence=0.85
                )

        # PRIORITY 2: EXIT OPTIMIZATION
        if metrics:
            efficiency = metrics.get("efficiency", 0)

            # Exits trop tôt (efficiency faible)
            if efficiency < 0.45:
                return Decision(
                    action="ADJUST_TP",
                    params={"tp_factor": 1.15},  # Augmenter TP de 15%
                    reason=f"Exit efficiency too low ({efficiency:.1%}) - increasing TP target",
                    confidence=0.72
                )

            # MAE trop élevé (SL trop large)
            mae = metrics.get("mae_pct", 0)
            if mae < -0.025:  # -2.5%
                return Decision(
                    action="ADJUST_SL",
                    params={"sl_factor": 0.85},  # Réduire SL de 15%
                    reason=f"MAE too high ({mae:.2%}) - tightening stop loss",
                    confidence=0.68
                )

        # PRIORITY 3: META-LEARNING
        if meta_suggestion:
            return Decision(
                action="APPLY_META",
                params=meta_suggestion,
                reason="Applying meta-learned configuration",
                confidence=meta_suggestion.get("confidence", 0.6)
            )

        # NO ACTION NEEDED
        return Decision(
            action="NO_ACTION",
            params={},
            reason="System stable - no adjustments needed",
            confidence=0.5
        )


class RiskGuard:
    """Garde-fou de risque — valide les décisions"""

    def __init__(self, limits: Dict[str, float]):
        """
        Args:
            limits: {
                "max_tp_increase": 0.3,   # 30% max increase
                "max_sl_decrease": 0.3,   # 30% max decrease
                "max_position_reduction": 0.7,  # Can reduce to 30% min
            }
        """
        self.limits = {
            "max_tp_increase": 0.3,
            "max_sl_decrease": 0.3,
            "max_position_reduction": 0.7,
            **limits
        }

    def validate(self, decision: Decision) -> Tuple[bool, str]:
        """
        Valide une décision avant exécution

        Returns:
            (valid: bool, reason: str)
        """

        # FORBIDDEN ACTIONS
        forbidden = ["INCREASE_RISK", "INCREASE_POSITION_SIZE"]
        if decision.action in forbidden:
            return False, "Action forbidden for safety"

        # CHECK PARAMETER LIMITS
        if decision.action == "ADJUST_TP":
            factor = decision.params.get("tp_factor", 1.0)
            if factor > 1 + self.limits["max_tp_increase"]:
                return False, f"TP increase too aggressive ({factor:.1%})"

        if decision.action == "ADJUST_SL":
            factor = decision.params.get("sl_factor", 1.0)
            if factor < 1 - self.limits["max_sl_decrease"]:
                return False, f"SL decrease too aggressive ({factor:.1%})"

        if decision.action == "REDUCE_RISK":
            factor = decision.params.get("position_size_factor", 1.0)
            if factor < 1 - self.limits["max_position_reduction"]:
                return False, "Position reduction too aggressive"

        return True, "Validation passed"


class ActionExecutor:
    """Exécute les décisions approuvées"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.copy()
        self.execution_history = []

    def execute(self, decision: Decision) -> Tuple[Dict[str, Any], bool, str]:
        """
        Exécute une décision

        Returns:
            (new_config, success, reason)
        """

        if decision.action == "NO_ACTION":
            return self.config, True, "No action"

        elif decision.action == "ADJUST_TP":
            factor = decision.params.get("tp_factor", 1.0)
            old_tp = self.config.get("tp", 0.02)
            self.config["tp"] = old_tp * factor
            msg = f"TP adjusted: {old_tp:.3f} -> {self.config['tp']:.3f}"

        elif decision.action == "ADJUST_SL":
            factor = decision.params.get("sl_factor", 1.0)
            old_sl = self.config.get("sl", 0.01)
            self.config["sl"] = old_sl * factor
            msg = f"SL adjusted: {old_sl:.3f} -> {self.config['sl']:.3f}"

        elif decision.action == "REDUCE_RISK":
            factor = decision.params.get("position_size_factor", 1.0)
            old_size = self.config.get("position_size", 0.1)
            self.config["position_size"] = old_size * factor
            msg = f"Position size reduced: {old_size:.3f} -> {self.config['position_size']:.3f}"

        elif decision.action == "STOP_TRADING":
            self.config["trading_enabled"] = False
            msg = "Trading stopped (RISK LIMIT)"

        elif decision.action == "APPLY_META":
            # Appliquer config meta-learning
            for key, value in decision.params.items():
                if key not in ["confidence"]:
                    self.config[key] = value
            msg = "Meta-learned configuration applied"

        else:
            return self.config, False, f"Unknown action: {decision.action}"

        self.execution_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": decision.action,
            "success": True,
            "message": msg
        })

        return self.config, True, msg


class DecisionLogger:
    """Enregistre toutes les décisions pour audit"""

    def __init__(self, log_file: str = "logs/decisions.jsonl"):
        self.log_file = log_file

    def log(self, decision: Decision, validated: bool, executed: bool, reason: str = ""):
        """
        Enregistre une décision

        Args:
            decision: Decision object
            validated: Si passée le RiskGuard
            executed: Si exécutée
            reason: Raison du rejet si applicable
        """
        entry = {
            "timestamp": decision.timestamp,
            "action": decision.action,
            "params": decision.params,
            "reason": decision.reason,
            "confidence": decision.confidence,
            "validated": validated,
            "executed": executed,
            "validation_reason": reason
        }

        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"Logging error: {e}")

    def get_decision_history(self, limit: int = 50) -> List[Dict]:
        """Récupère l'historique des décisions"""
        history = []
        try:
            with open(self.log_file, "r") as f:
                lines = f.readlines()
                for line in lines[-limit:]:
                    history.append(json.loads(line))
        except FileNotFoundError:
            pass

        return history


class AutoDecisionOrchestrator:
    """Orchestre l'ensemble du pipeline décisionnel"""

    def __init__(self,
                 initial_config: Dict[str, Any],
                 limits: Dict[str, float] = None,
                 log_file: str = "logs/decisions.jsonl"):
        """
        Args:
            initial_config: Configuration initiale de trading
            limits: Limites de risque pour le guard
            log_file: Fichier de log des décisions
        """
        self.engine = AutoDecisionEngine(initial_config)
        self.guard = RiskGuard(limits or {})
        self.executor = ActionExecutor(initial_config)
        self.logger = DecisionLogger(log_file)

        self.current_config = initial_config.copy()
        self.decision_count = 0

    def run_decision_cycle(self,
                          metrics: Dict[str, Any],
                          risk_state: Dict[str, Any],
                          meta_suggestion: Optional[Dict] = None) -> Tuple[Dict, Decision, bool]:
        """
        Exécute un cycle complet de décision

        Returns:
            (new_config, decision, executed)
        """

        # STEP 1: Générer décision
        decision = self.engine.decide(metrics, meta_suggestion, risk_state)

        # STEP 2: Valider
        is_valid, validation_reason = self.guard.validate(decision)

        # STEP 3: Exécuter si valide
        executed = False
        if is_valid:
            self.current_config, executed, execution_reason = self.executor.execute(decision)

        # STEP 4: Logger
        self.logger.log(decision, is_valid, executed, validation_reason if not is_valid else "")

        # STEP 5: Stats
        self.decision_count += 1

        return self.current_config, decision, executed

    def get_status(self) -> Dict[str, Any]:
        """Statut du système autonome"""
        history = self.logger.get_decision_history(10)

        last_decisions = [h["action"] for h in history[-5:]]
        action_counts = {}
        for action in last_decisions:
            action_counts[action] = action_counts.get(action, 0) + 1

        return {
            "total_decisions": self.decision_count,
            "current_config": self.current_config,
            "last_decisions": last_decisions,
            "action_breakdown": action_counts,
            "trading_enabled": self.current_config.get("trading_enabled", True),
        }
