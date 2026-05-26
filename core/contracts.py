"""
core/contracts.py — Vocabulaire canonique du système.

Rôle unique : être le SEUL fichier à importer pour les types partagés
entre les stacks (quant_hedge_ai, tracker_system, meta_learning,
supervision, strategy_lab, governance).

Règles :
    - Aucune logique métier ici. Juste des types, enums et conversions.
    - Tout nouveau type partagé vient ici d'abord.
    - Les stacks importent depuis core.contracts, pas depuis l'autre stack.
    - Non-breaking : les modules existants continuent de fonctionner.
      La migration vers core.contracts se fait progressivement.

Conflits résolus (audit Phase 1 — 2026-05-25) :
    - ConvictionLevel : deux enums différentes → alias + conversion
    - GateResult      : deux homonymes non compatibles → noms distincts
    - Decision        : trois concepts → noms distincts
    - Regime          : string / enum / packet → fonctions de conversion
    - Signal          : pas de contrat unifié → TradeSignal introduit
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Re-exports depuis decision_packet — point d'import unique pour les types core
# ---------------------------------------------------------------------------
from core.decision_packet import (  # noqa: F401  (ré-exporté intentionnellement)
    EXCEPTIONAL_TERMINAL_STATES,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    ConvictionLevel,
    DecisionPacket,
    DecisionSide,
    DecisionState,
    MarketRegime,
    ReasoningCategory,
    ReasoningEntry,
    ReasoningSeverity,
    StateTransition,
)

# ---------------------------------------------------------------------------
# ConvictionLevel — résolution du conflit entre core et conviction_engine
#
# Contexte :
#   core/decision_packet.py  → ConvictionLevel(VERY_HIGH, HIGH, MEDIUM, LOW, SKIP)
#   conviction_engine.py     → ConvictionLevel(MINIMAL, LOW, MEDIUM, HIGH, EXCEPTIONAL)
#
# Résolution :
#   - Le core ConvictionLevel est canonique (utilisé par DecisionPacket).
#   - L'enum conviction_engine est rebaptisé EngineConvictionScale ici.
#   - to_core_conviction() fait le pont entre les deux.
# ---------------------------------------------------------------------------


class EngineConvictionScale(str, Enum):
    """
    Échelle interne du ConvictionEngine.
    Distinct de ConvictionLevel (core) — ne pas confondre.
    Utilisé uniquement dans quant_hedge_ai/agents/intelligence/conviction_engine.py.
    """

    MINIMAL = "MINIMAL"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    EXCEPTIONAL = "EXCEPTIONAL"


_ENGINE_TO_CORE: Dict[EngineConvictionScale, ConvictionLevel] = {
    EngineConvictionScale.EXCEPTIONAL: ConvictionLevel.VERY_HIGH,
    EngineConvictionScale.HIGH: ConvictionLevel.HIGH,
    EngineConvictionScale.MEDIUM: ConvictionLevel.MEDIUM,
    EngineConvictionScale.LOW: ConvictionLevel.LOW,
    EngineConvictionScale.MINIMAL: ConvictionLevel.SKIP,
}


def to_core_conviction(engine_level: EngineConvictionScale) -> ConvictionLevel:
    """Convertit une EngineConvictionScale en ConvictionLevel canonique."""
    return _ENGINE_TO_CORE[engine_level]


def from_core_conviction(core_level: ConvictionLevel) -> EngineConvictionScale:
    """Convertit un ConvictionLevel canonique en EngineConvictionScale."""
    _reverse = {v: k for k, v in _ENGINE_TO_CORE.items()}
    return _reverse[core_level]


# ---------------------------------------------------------------------------
# MarketRegime — résolution du conflit string / enum
#
# Contexte :
#   core/decision_packet.py          → MarketRegime enum (TREND_BULL, …)
#   market_regime_classifier.py      → strings ("bull_trend", "bear_trend", …)
#   tracker_system/auto_regime.py    → strings identiques
#
# Résolution :
#   - MarketRegime enum est canonique.
#   - regime_from_string() convertit les strings legacy en enum.
# ---------------------------------------------------------------------------

_REGIME_STRING_MAP: Dict[str, MarketRegime] = {
    "bull_trend": MarketRegime.TREND_BULL,
    "trend_bull": MarketRegime.TREND_BULL,
    "bear_trend": MarketRegime.TREND_BEAR,
    "trend_bear": MarketRegime.TREND_BEAR,
    "range": MarketRegime.RANGE,
    "sideways": MarketRegime.RANGE,
    "choppy": MarketRegime.RANGE,
    "volatile": MarketRegime.VOLATILE,
    "high_vol": MarketRegime.VOLATILE,
    "scalp": MarketRegime.VOLATILE,
    "protection": MarketRegime.UNKNOWN,
    "unknown": MarketRegime.UNKNOWN,
}


def regime_from_string(s: str) -> MarketRegime:
    """
    Convertit une string régime (legacy) en MarketRegime canonique.
    Insensible à la casse. Retourne UNKNOWN si non reconnu.
    """
    return _REGIME_STRING_MAP.get(s.lower(), MarketRegime.UNKNOWN)


def regime_to_string(regime: MarketRegime) -> str:
    """
    Convertit un MarketRegime canonique en string legacy.
    Utilisé pour les modules qui attendent encore des strings.
    """
    _reverse: Dict[MarketRegime, str] = {
        MarketRegime.TREND_BULL: "bull_trend",
        MarketRegime.TREND_BEAR: "bear_trend",
        MarketRegime.RANGE: "range",
        MarketRegime.VOLATILE: "volatile",
        MarketRegime.UNKNOWN: "unknown",
    }
    return _reverse.get(regime, "unknown")


# ---------------------------------------------------------------------------
# TradeSignal — contrat unifié pour tous les signaux de trading
#
# Contexte :
#   Avant : SignalResult (quant), MVPSignal (mvp), WhaleSignal (onchain),
#           IncomingSignal (governance) — aucun contrat commun.
#
# Résolution :
#   TradeSignal est le type d'entrée canonique de la couche décision.
#   Les sources spécialisées (whale, social) se convertissent vers TradeSignal.
# ---------------------------------------------------------------------------


@dataclass
class TradeSignal:
    """
    Signal de trading unifié — entrée canonique du pipeline décisionnel.

    Produit par : LiveSignalEngine, MVPSignalEngine, WhaleRadar, SocialScanner.
    Consommé par : governance/decision_router.py, advisor_loop.py, DecisionPacket.

    score       : 0–100, force du signal (100 = conviction maximale)
    confidence  : 0.0–1.0, fiabilité estimée de la source
    regime      : contexte de marché au moment du signal
    source      : nom du module émetteur (pour audit et meta-learning)
    """

    symbol: str
    side: DecisionSide
    score: float  # 0–100
    confidence: float  # 0.0–1.0
    regime: MarketRegime = MarketRegime.UNKNOWN
    timeframe: str = "1h"
    source: str = "unknown"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    features: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "score": self.score,
            "confidence": self.confidence,
            "regime": self.regime.value,
            "timeframe": self.timeframe,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "features": self.features,
            "metadata": self.metadata,
        }

    def to_packet(self) -> DecisionPacket:
        """
        Crée un DecisionPacket depuis ce signal.
        Point d'entrée officiel dans le pipeline décisionnel.
        """
        packet = DecisionPacket(
            symbol=self.symbol,
            timeframe=self.timeframe,
            side=self.side,
            confidence=self.score,
            regime=self.regime,
        )
        packet.add_agent(self.source)
        packet.features.update(self.features)
        packet.metadata.update(self.metadata)
        return packet


# ---------------------------------------------------------------------------
# Gate results — résolution du doublon GateResult
#
# Contexte :
#   global_risk_gate.py      → GateResult(allowed, conditions, failed, warnings)
#   governance/confidence_gate.py → GateResult(passed, score, level, threshold, reason)
#   Même nom, champs incompatibles.
#
# Résolution :
#   Noms distincts ici. Les modules existants gardent leur GateResult local
#   pour ne pas casser les tests. Migration progressive possible.
# ---------------------------------------------------------------------------


@dataclass
class GlobalRiskGateResult:
    """
    Résultat du GlobalRiskGate (risk management layer).
    Remplace l'usage direct de GateResult dans global_risk_gate.py.
    """

    allowed: bool
    conditions: Dict[str, bool] = field(default_factory=dict)
    failed: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    score: float = 0.0

    @property
    def is_clean(self) -> bool:
        """Vrai si autorisé et aucun warning."""
        return self.allowed and len(self.warnings) == 0


@dataclass
class ConfidenceGateResult:
    """
    Résultat du ConfidenceGate (governance layer).
    Remplace l'usage direct de GateResult dans governance/confidence_gate.py.
    """

    passed: bool
    score: float
    level: str
    threshold: float
    reason: str


# ---------------------------------------------------------------------------
# AutonomousAction — résolution du conflit Decision
#
# Contexte :
#   tracker_system/autonomous/auto_decision_engine.py → Decision @dataclass
#   (actions: ADJUST_TP, REDUCE_RISK, STOP_TRADING, HOLD)
#   Conflit avec DecisionPacket (vecteur principal) et les deux DecisionEngine.
#
# Résolution :
#   Renommé AutonomousAction ici pour clarté sémantique.
#   tracker_system peut l'importer depuis core.contracts.
# ---------------------------------------------------------------------------


class AutonomousActionType(str, Enum):
    """Type d'action autonome produit par l'auto_decision_engine."""

    ADJUST_TP = "ADJUST_TP"
    ADJUST_SL = "ADJUST_SL"
    REDUCE_RISK = "REDUCE_RISK"
    INCREASE_RISK = "INCREASE_RISK"
    STOP_TRADING = "STOP_TRADING"
    RESUME_TRADING = "RESUME_TRADING"
    HOLD = "HOLD"
    CLOSE_POSITION = "CLOSE_POSITION"


@dataclass
class AutonomousAction:
    """
    Action autonome produite par l'auto_decision_engine du tracker_system.
    Distinct de DecisionPacket (vecteur pipeline) et de DecisionEngine (orchestrateur).
    """

    action: AutonomousActionType
    reason: str
    confidence: float  # 0.0–1.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "params": self.params,
        }


# ---------------------------------------------------------------------------
# RegimeContext — représentation riche du régime (ex-RegimePacket)
#
# Contexte :
#   market_regime_classifier.py → RegimePacket (riche: confidence, duration, entropy)
#   Renommé ici pour éviter la confusion avec DecisionPacket.
# ---------------------------------------------------------------------------


@dataclass
class RegimeContext:
    """
    Contexte de marché enrichi — sortie du classifieur de régime.
    Ex-RegimePacket. Contient le régime + méta-données de confiance.

    Utilisé par : AdaptiveThresholdEngine, RegimeTransitionSmoother,
                  advisor_loop, DecisionPacket.regime (via .regime).
    """

    regime: MarketRegime
    confidence: float  # 0.0–1.0
    duration_cycles: int = 0
    entropy: float = (
        0.0  # incertitude du classifieur (0 = certain, 1 = max incertitude)
    )
    in_transition: bool = False
    transition_from: Optional[MarketRegime] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    raw_string: str = ""  # valeur originale avant conversion (debug)

    @classmethod
    def from_string(cls, regime_str: str, confidence: float = 0.5) -> "RegimeContext":
        """Crée un RegimeContext depuis une string legacy."""
        regime = regime_from_string(regime_str)
        return cls(regime=regime, confidence=confidence, raw_string=regime_str)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime": self.regime.value,
            "confidence": self.confidence,
            "duration_cycles": self.duration_cycles,
            "entropy": self.entropy,
            "in_transition": self.in_transition,
            "transition_from": (
                self.transition_from.value if self.transition_from else None
            ),
            "timestamp": self.timestamp.isoformat(),
            "raw_string": self.raw_string,
        }


# ---------------------------------------------------------------------------
# Exports publics — ce que les stacks doivent importer
# ---------------------------------------------------------------------------

__all__ = [
    # --- Depuis decision_packet (re-exportés) ---
    "DecisionPacket",
    "DecisionSide",
    "DecisionState",
    "DecisionState",
    "MarketRegime",
    "ConvictionLevel",
    "ReasoningCategory",
    "ReasoningEntry",
    "ReasoningSeverity",
    "StateTransition",
    "TERMINAL_STATES",
    "EXCEPTIONAL_TERMINAL_STATES",
    "VALID_TRANSITIONS",
    # --- Nouveaux types unifiés ---
    "TradeSignal",
    "RegimeContext",
    "GlobalRiskGateResult",
    "ConfidenceGateResult",
    "AutonomousAction",
    "AutonomousActionType",
    "EngineConvictionScale",
    # --- Fonctions de conversion ---
    "regime_from_string",
    "regime_to_string",
    "to_core_conviction",
    "from_core_conviction",
]
