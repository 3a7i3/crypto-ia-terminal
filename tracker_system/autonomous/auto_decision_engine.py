"""
AUTO DECISION ENGINE — Système autonome contrôlé
Observe → Décide → Agit → Contrôle → Apprend
"""

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Cooldown minimal après STOP_TRADING avant de pouvoir reprendre (secondes)
_RESUME_COOLDOWN_S = 3600  # 1h minimum après un arrêt

# Seuils de recovery pour RESUME_TRADING
_RESUME_DRAWDOWN_MAX = 0.03  # drawdown doit être < 3% pour reprendre
_RESUME_LOSS_STREAK_MAX = 1  # loss_streak doit être <= 1


@dataclass
class Decision:
    """Représente une décision du système"""

    action: str  # see AutoDecisionEngine.ACTIONS
    params: Dict[str, Any]
    reason: str
    confidence: float = 0.5
    timestamp: str = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()


class AutoDecisionEngine:
    """Moteur de décision automatique"""

    ACTIONS = [
        "ADJUST_TP",  # Augmenter TP si exits trop tôt
        "ADJUST_SL",  # Réduire SL si MAE trop élevé
        "REDUCE_RISK",  # Réduire taille position si streak de pertes
        "STOP_TRADING",  # Arrêt si DD trop élevé
        "RESUME_TRADING",  # Reprise après recovery des conditions
        "APPLY_META",  # Appliquer config meta-learning
        "NO_ACTION",  # Rien faire
    ]

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        # Récupérer le timestamp d'arrêt depuis la config persistée si disponible
        self._halted_at: Optional[float] = config.get("_halted_at")

    @property
    def is_halted(self) -> bool:
        return not self.config.get("trading_enabled", True)

    def decide(
        self,
        metrics: Dict[str, Any],
        meta_suggestion: Optional[Dict] = None,
        risk_state: Optional[Dict] = None,
    ) -> Decision:
        """
        Priorité :
        0. Recovery — si halted ET conditions améliorées → RESUME_TRADING
        1. Risk first — STOP_TRADING si DD > 5%
        2. Réduction risque — REDUCE_RISK si loss_streak >= 4
        3. Exit optimization — ADJUST_TP / ADJUST_SL
        4. Meta-learning — APPLY_META
        5. NO_ACTION
        """

        # PRIORITY 0: RECOVERY CHECK (si le système est actuellement arrêté)
        if self.is_halted and risk_state:
            drawdown = risk_state.get("drawdown", 1.0)
            loss_streak = risk_state.get("loss_streak", 99)
            elapsed = time.time() - (self._halted_at or 0)

            if (
                elapsed >= _RESUME_COOLDOWN_S
                and drawdown < _RESUME_DRAWDOWN_MAX
                and loss_streak <= _RESUME_LOSS_STREAK_MAX
            ):
                return Decision(
                    action="RESUME_TRADING",
                    params={},
                    reason=(
                        f"Recovery confirmed: drawdown={drawdown:.1%}"
                        f" < {_RESUME_DRAWDOWN_MAX:.0%},"
                        f" loss_streak={loss_streak}"
                        f" <= {_RESUME_LOSS_STREAK_MAX},"
                        f" cooldown elapsed {elapsed/3600:.1f}h"
                    ),
                    confidence=0.90,
                )

            # Si halted et recovery pas atteinte — éviter de répéter STOP_TRADING
            if self.is_halted:
                return Decision(
                    action="NO_ACTION",
                    params={},
                    reason=(
                        f"Trading halted — waiting for recovery"
                        f" (dd={drawdown:.1%}, streak={loss_streak},"
                        f" elapsed={elapsed/60:.0f}min)"
                    ),
                    confidence=0.99,
                )

        # PRIORITY 1: RISK CONTROL
        if risk_state:
            drawdown = risk_state.get("drawdown", 0)
            if drawdown > 0.05:
                return Decision(
                    action="STOP_TRADING",
                    params={},
                    reason=(
                        f"Drawdown {drawdown:.1%} > 5%"
                        " — stopping to prevent catastrophic loss"
                    ),
                    confidence=0.95,
                )

            loss_streak = risk_state.get("loss_streak", 0)
            if loss_streak >= 4:
                return Decision(
                    action="REDUCE_RISK",
                    params={"position_size_factor": 0.5},
                    reason=(
                        f"Loss streak of {loss_streak} detected"
                        " — reducing position size"
                    ),
                    confidence=0.85,
                )

        # PRIORITY 2: EXIT OPTIMIZATION
        if metrics:
            efficiency = metrics.get("efficiency", 0)
            if efficiency < 0.45:
                return Decision(
                    action="ADJUST_TP",
                    params={"tp_factor": 1.15},
                    reason=(
                        f"Exit efficiency too low ({efficiency:.1%})"
                        " — increasing TP target"
                    ),
                    confidence=0.72,
                )

            mae = metrics.get("mae_pct", 0)
            if mae < -0.025:
                return Decision(
                    action="ADJUST_SL",
                    params={"sl_factor": 0.85},
                    reason=f"MAE too high ({mae:.2%}) — tightening stop loss",
                    confidence=0.68,
                )

        # PRIORITY 3: META-LEARNING
        if meta_suggestion:
            return Decision(
                action="APPLY_META",
                params=meta_suggestion,
                reason="Applying meta-learned configuration",
                confidence=meta_suggestion.get("confidence", 0.6),
            )

        return Decision(
            action="NO_ACTION",
            params={},
            reason="System stable — no adjustments needed",
            confidence=0.5,
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
            **limits,
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
            msg = (
                f"Position size reduced: {old_size:.3f}"
                f" -> {self.config['position_size']:.3f}"
            )

        elif decision.action == "STOP_TRADING":
            self.config["trading_enabled"] = False
            self.config["_halted_at"] = time.time()
            msg = "Trading stopped (RISK LIMIT)"
            try:
                from system.state_machine import get_state_machine as _gsm

                _gsm().transition(
                    "HALTED", reason=decision.reason, halt_source="AutoDecisionEngine"
                )
            except Exception:
                pass

        elif decision.action == "RESUME_TRADING":
            self.config["trading_enabled"] = True
            self.config.pop("_halted_at", None)
            msg = "Trading resumed — risk conditions normalized"
            try:
                from system.state_machine import get_state_machine as _gsm

                _gsm().transition("RECOVERY", reason=decision.reason)
            except Exception:
                pass

        elif decision.action == "APPLY_META":
            # Appliquer config meta-learning
            for key, value in decision.params.items():
                if key not in ["confidence"]:
                    self.config[key] = value
            msg = "Meta-learned configuration applied"

        else:
            return self.config, False, f"Unknown action: {decision.action}"

        self.execution_history.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "action": decision.action,
                "success": True,
                "message": msg,
            }
        )

        return self.config, True, msg


class DecisionLogger:
    """Enregistre toutes les décisions pour audit"""

    def __init__(self, log_file: str = "logs/decisions.jsonl"):
        self.log_file = log_file

    def log(
        self, decision: Decision, validated: bool, executed: bool, reason: str = ""
    ):
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
            "validation_reason": reason,
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

    def __init__(
        self,
        initial_config: Dict[str, Any],
        limits: Dict[str, float] = None,
        log_file: str = "logs/decisions.jsonl",
    ):
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

    def run_decision_cycle(
        self,
        metrics: Dict[str, Any],
        risk_state: Dict[str, Any],
        meta_suggestion: Optional[Dict] = None,
    ) -> Tuple[Dict, Decision, bool]:
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
            self.current_config, executed, execution_reason = self.executor.execute(
                decision
            )

        # STEP 4: Logger
        self.logger.log(
            decision, is_valid, executed, validation_reason if not is_valid else ""
        )

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
