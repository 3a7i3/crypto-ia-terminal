"""
Decision Engine — Connecte Meta Learning a Exit Engine
Flow: context → meta_learner → decision → exit_engine
"""

from typing import Any
from meta_learning.learner import MetaLearner
from tracker_system.config.exit_config import get_exit_config
from tracker_system.engine.exit_factory import build_exit_engine
from tracker_system.engine.exit_engine import ExitEngine


class DecisionEngine:
    def __init__(self, meta_learner: MetaLearner | None = None):
        self.meta_learner = meta_learner
        self.fallback_config = get_exit_config(None)

    def get_exit_decision(
        self,
        context: dict[str, Any],
        fallback_regime: str | None = None,
    ) -> dict[str, Any]:
        """
        Retourne decision d'exit basee sur:
        1. Meta learner (si contexte similaire trouve)
        2. Sinon fallback config par regime
        """
        decision = {
            "source": "default",
            "tp": self.fallback_config["tp"],
            "sl": self.fallback_config["sl"],
            "trailing": self.fallback_config["trailing"],
        }

        if self.meta_learner:
            best = self.meta_learner.find_best_decision(context)
            if best:
                decision["source"] = f"meta_learned (score={best['similarity_score']:.2f})"
                decision.update(best["decision"])
                return decision

        regime = context.get("regime", fallback_regime)
        if regime:
            config = get_exit_config(regime)
            decision["source"] = f"config[{regime}]"
            decision["tp"] = config["tp"]
            decision["sl"] = config["sl"]
            decision["trailing"] = config["trailing"]

        return decision

    def build_exit_engine(
        self,
        context: dict[str, Any],
        fallback_regime: str | None = None,
    ) -> ExitEngine:
        """
        Construit ExitEngine basee sur decision intelligente.
        """
        decision = self.get_exit_decision(context, fallback_regime)
        confidence = context.get("confidence")

        config = {
            "tp": decision["tp"],
            "sl": decision["sl"],
            "trailing": decision["trailing"],
        }

        if confidence:
            tp_scaled = config["tp"] * (1.0 + float(confidence) / 100.0)
            config["tp"] = min(tp_scaled, config["tp"] * 2.0)

        return build_exit_engine(context.get("regime"), confidence)

    def log_decision(
        self,
        context: dict[str, Any],
        decision: dict[str, Any],
        execution_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Log decision pour audit trail.
        """
        record = {
            "context": context,
            "decision": decision,
            "execution": execution_result or {},
        }
        return record
