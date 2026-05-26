"""
decision_arbitrator.py — Multi-Agent Decision Arbitration Layer

Remplace le système de vetos dispersés par un cerveau de décision centralisé.
Au lieu de N systèmes qui bloquent indépendamment, calcule un score de consensus
pondéré et prend UNE décision finale avec justification.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.v2.decision_arbitrator")


class ArbitrationDecision(str, Enum):
    EXECUTE = "execute"  # consensus fort → exécuter
    EXECUTE_REDUCED = "execute_reduced"  # consensus modéré → taille réduite
    WAIT = "wait"  # signal trop faible → attendre
    REJECT = "reject"  # consensus négatif → rejeter
    EMERGENCY_EXIT = "emergency_exit"  # danger détecté → sortir immédiatement


@dataclass
class AgentVote:
    agent_name: str
    score: float  # [-1, +1] : -1=fort rejet, +1=fort accord
    weight: float = 1.0  # importance de cet agent
    reasoning: str = ""
    veto: bool = False  # veto absolu (override tout consensus)


@dataclass
class ArbitrationResult:
    decision: ArbitrationDecision
    consensus_score: float  # [-1, +1] score final pondéré
    confidence: float  # [0, 1] confiance dans la décision
    size_multiplier: float  # [0, 1] multiplicateur de taille
    votes: list[AgentVote] = field(default_factory=list)
    veto_agents: list[str] = field(default_factory=list)
    reasoning: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "consensus_score": self.consensus_score,
            "confidence": self.confidence,
            "size_multiplier": self.size_multiplier,
            "veto_agents": self.veto_agents,
            "reasoning": self.reasoning,
            "n_votes": len(self.votes),
        }


class DecisionArbitrator:
    """
    Arbitre central qui agrège les votes de tous les agents de décision
    et produit une décision finale cohérente.

    Logique :
    - Chaque agent soumet un score [-1, +1] et un poids
    - Un agent peut soumettre un veto absolu
    - Le score final est la moyenne pondérée
    - La décision est mappée depuis le score selon des seuils configurables
    """

    # Seuils de décision
    EXECUTE_THRESHOLD = 0.35
    EXECUTE_REDUCED_THRESHOLD = 0.15
    REJECT_THRESHOLD = -0.20
    EMERGENCY_THRESHOLD = -0.70

    # Poids par défaut des agents
    DEFAULT_WEIGHTS = {
        "global_risk_gate": 2.0,  # critique — veto possible
        "conviction_engine": 1.8,
        "portfolio_brain": 1.8,
        "meta_strategy": 1.5,
        "microstructure": 1.5,  # nouveau V2
        "hmm_regime": 1.4,  # nouveau V2
        "onchain_sentiment": 1.2,  # nouveau V2
        "no_trade_layer": 1.3,
        "self_awareness": 1.0,
        "mistake_memory": 1.0,
        "executive_override": 2.5,  # poids maximal
        "threat_radar": 1.3,
    }

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._weights = {**self.DEFAULT_WEIGHTS, **(weights or {})}
        self._history: list[ArbitrationResult] = []
        self._agent_credibility: dict[str, float] = (
            {}
        )  # ajusté par les résultats passés

    def arbitrate(
        self, votes: list[AgentVote], context: dict[str, Any] | None = None
    ) -> ArbitrationResult:
        """
        Arbitre entre tous les votes et retourne une décision finale.
        """
        if not votes:
            return ArbitrationResult(
                decision=ArbitrationDecision.REJECT,
                consensus_score=0.0,
                confidence=0.0,
                size_multiplier=0.0,
                reasoning="Aucun vote reçu",
            )

        # Vérification vetos absolus
        veto_agents = [v.agent_name for v in votes if v.veto]
        if veto_agents:
            result = ArbitrationResult(
                decision=ArbitrationDecision.REJECT,
                consensus_score=-1.0,
                confidence=1.0,
                size_multiplier=0.0,
                votes=votes,
                veto_agents=veto_agents,
                reasoning=f"VETO par: {', '.join(veto_agents)}",
            )
            self._history.append(result)
            _log.warning("[Arbitrator] VETO: %s", veto_agents)
            return result

        # Emergency (score < seuil d'urgence)
        emergency_votes = [v for v in votes if v.score <= self.EMERGENCY_THRESHOLD]
        if len(emergency_votes) >= 2:
            result = ArbitrationResult(
                decision=ArbitrationDecision.EMERGENCY_EXIT,
                consensus_score=-0.9,
                confidence=0.9,
                size_multiplier=0.0,
                votes=votes,
                reasoning=f"URGENCE: {len(emergency_votes)} agents signalent danger critique",
            )
            self._history.append(result)
            return result

        # Calcul du score pondéré
        total_weight = 0.0
        weighted_sum = 0.0
        for vote in votes:
            w = self._weights.get(vote.agent_name, vote.weight)
            # Ajuster par crédibilité historique
            cred = self._agent_credibility.get(vote.agent_name, 1.0)
            effective_weight = w * cred
            weighted_sum += vote.score * effective_weight
            total_weight += effective_weight

        consensus = weighted_sum / total_weight if total_weight > 0 else 0.0
        consensus = max(-1.0, min(1.0, consensus))

        # Confiance = cohérence entre les votes (variance faible = confiance élevée)
        scores = [v.score for v in votes]
        variance = sum((s - consensus) ** 2 for s in scores) / len(scores)
        confidence = max(0.1, 1.0 - variance**0.5)

        # Décision
        decision, size_mult = self._map_decision(consensus, confidence, context)

        # Reasoning
        reasoning = self._build_reasoning(votes, consensus, decision, size_mult)

        result = ArbitrationResult(
            decision=decision,
            consensus_score=consensus,
            confidence=confidence,
            size_multiplier=size_mult,
            votes=votes,
            reasoning=reasoning,
        )
        self._history.append(result)
        return result

    def update_credibility(self, agent_name: str, was_correct: bool) -> None:
        """
        Ajuste la crédibilité d'un agent en fonction de ses résultats passés.
        Appelé après clôture d'un trade.
        """
        current = self._agent_credibility.get(agent_name, 1.0)
        if was_correct:
            new = min(current * 1.05, 2.0)
        else:
            new = max(current * 0.95, 0.3)
        self._agent_credibility[agent_name] = new

    def credibility_report(self) -> dict[str, float]:
        return {
            agent: self._agent_credibility.get(agent, 1.0) for agent in self._weights
        }

    def recent_decisions(self, n: int = 10) -> list[dict]:
        return [r.to_dict() for r in self._history[-n:]]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _map_decision(
        self,
        score: float,
        confidence: float,
        context: dict | None,
    ) -> tuple[ArbitrationDecision, float]:
        if score >= self.EXECUTE_THRESHOLD and confidence >= 0.5:
            size_mult = min(1.0, score * confidence * 1.5)
            return ArbitrationDecision.EXECUTE, size_mult

        if score >= self.EXECUTE_REDUCED_THRESHOLD:
            size_mult = max(0.25, score * 0.7)
            return ArbitrationDecision.EXECUTE_REDUCED, size_mult

        if score <= self.REJECT_THRESHOLD:
            return ArbitrationDecision.REJECT, 0.0

        return ArbitrationDecision.WAIT, 0.0

    def _build_reasoning(
        self,
        votes: list[AgentVote],
        consensus: float,
        decision: ArbitrationDecision,
        size_mult: float,
    ) -> str:
        n_positive = sum(1 for v in votes if v.score > 0.1)
        n_negative = sum(1 for v in votes if v.score < -0.1)
        n_neutral = len(votes) - n_positive - n_negative
        return (
            f"Score={consensus:+.2f} | "
            f"{n_positive}✓ {n_negative}✗ {n_neutral}~ sur {len(votes)} agents | "
            f"Décision: {decision.value} (taille×{size_mult:.0%})"
        )
