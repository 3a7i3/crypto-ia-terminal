"""
core/decision_packet.py — Constitution runtime du système de décision.

Définition canonique :
    Une décision est une intention de marché mutable, progressivement enrichie,
    évaluée et contrainte par les différentes couches du système,
    jusqu'à résolution finale : EXECUTED, REJECTED ou EXPIRED.

Règles invariantes :
    - Aucune logique métier ici. Le packet transporte. Il ne pense pas.
    - features  = données quantitatives ML-ready (float uniquement)
    - metadata  = debug/runtime/humain, jamais parsé par les agents
    - La mutation d'état passe UNIQUEMENT par transition_to()
    - Jamais de pandas / numpy / torch / objets exchange dans ce packet
    - version   = 1 : incrémenter à chaque rupture de schéma
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from observability.json_logger import get_logger

_log = get_logger("decision_packet")

# ---------------------------------------------------------------------------
# Enums — seules valeurs légales dans le système
# ---------------------------------------------------------------------------


class DecisionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class MarketRegime(str, Enum):
    TREND_BULL = "TREND_BULL"
    TREND_BEAR = "TREND_BEAR"
    RANGE = "RANGE"
    VOLATILE = "VOLATILE"
    UNKNOWN = "UNKNOWN"


class ConvictionLevel(str, Enum):
    """Niveau de conviction — détermine le sizing relatif."""

    VERY_HIGH = "VERY_HIGH"  # 100% de l'allocation cible
    HIGH = "HIGH"  # 75%
    MEDIUM = "MEDIUM"  # 50%
    LOW = "LOW"  # 25%
    SKIP = "SKIP"  # Ne pas trader


class ReasoningSeverity(str, Enum):
    """
    Nature opérationnelle d'un raisonnement — orthogonal à confidence_impact.

    INFO     : observation normale dans le flux attendu
    WARNING  : dégradation, divergence ou condition dégradée
    CRITICAL : menace pour la gouvernance ou la qualité d'exécution
    FATAL    : arrêt immédiat requis — veto, kill switch, anomalie systémique
    """

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"


class ReasoningCategory(str, Enum):
    """
    Famille causale d'un raisonnement — domaine cognitif de l'agent émetteur.

    Chaque valeur correspond à une couche institutionnelle précise.
    Utilisée pour le meta-learning futur : mesurer l'impact moyen par domaine
    sur le PnL réel, détecter les agents toxiques, ranker les catégories causales.

    Taxinomie fermée — toute nouvelle catégorie requiert une justification
    institutionnelle explicite pour éviter la pollution sémantique.
    """

    SIGNAL_QUALITY = "signal_quality"  # score, âge, direction détectée
    TREND_ALIGNMENT = "trend_alignment"  # MTF, régime, momentum
    RISK_GOVERNANCE = "risk_governance"  # session, drawdown, seuils gate
    PORTFOLIO_EXPOSURE = "portfolio_exposure"  # exposition totale, régime, levier
    PORTFOLIO_CONCENTRATION = "portfolio_concentration"  # concentration par symbole
    PORTFOLIO_CORRELATION = (
        "portfolio_correlation"  # risque corrélation inter-positions
    )
    PORTFOLIO_RISK_BUDGET = (
        "portfolio_risk_budget"  # nombre positions, direction, fragmentation
    )
    SIZING = "sizing"  # Kelly, volatilité, drawdown, facteurs
    GOVERNANCE = "governance"  # veto, kill switch, règles absolues
    UNCATEGORIZED = "uncategorized"  # fallback — à éviter


class DecisionState(str, Enum):
    """
    Machine d'état du cycle de vie d'une décision.

    Flux nominal :
        CREATED → SIGNAL_GENERATED → CONTEXT_ENRICHED → [REGIME_VALIDATED]
        → RISK_EVALUATED → APPROVED → EXECUTION_PENDING → EXECUTED
        → MONITORED → CLOSED → POSTMORTEM_ANALYZED

    Séparation institutionnelle :
        RISK_EVALUATED   = analyse terminée, verdict rendu
        APPROVED         = autorisation d'engagement capital accordée
        EXECUTION_PENDING= en file d'attente (async, throttling, routing)
        EXECUTED         = capital engagé sur le marché

    Branches terminales (résolution finale) :
        REJECTED | EXPIRED | CANCELLED | FAILED | VETOED
    Les états terminaux sont accessibles depuis n'importe quel état non-terminal
    (veto, expiry, panne système — voir VALID_TRANSITIONS).
    """

    # --- Flux nominal ---
    CREATED = "CREATED"
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    CONTEXT_ENRICHED = "CONTEXT_ENRICHED"
    REGIME_VALIDATED = "REGIME_VALIDATED"
    RISK_EVALUATED = "RISK_EVALUATED"
    APPROVED = "APPROVED"
    EXECUTION_PENDING = "EXECUTION_PENDING"
    EXECUTED = "EXECUTED"
    MONITORED = "MONITORED"
    CLOSED = "CLOSED"
    POSTMORTEM_ANALYZED = "POSTMORTEM_ANALYZED"

    # --- Branches terminales ---
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    VETOED = "VETOED"


class PacketEventCategory(str, Enum):
    """
    Catégorie sémantique d'un DecisionPacket (DPSS).

    Sépare trois espaces décisionnels pour éviter la contamination des métriques :

        TRADE      = décision de trading (signal → pipeline → exécution ou rejet)
        GOVERNANCE = rejet pur d'autorité sans signal de trading (G1-blocked, ATC)
        SYSTEM     = événement non-décisionnel (exception ENL, erreur système)

    Par défaut : TRADE (backward-compatible).
    Les métriques et dashboards DOIVENT filtrer sur event_category == TRADE
    pour ne pas diluer les KPIs décisionnels.
    """

    TRADE = "TRADE"
    GOVERNANCE = "GOVERNANCE"
    SYSTEM = "SYSTEM"


# États terminaux exceptionnels — mort prématurée du packet.
# Accessibles depuis n'importe quel état non-terminal : veto, expiry, panne,
# annulation peuvent survenir à tout moment dans le lifecycle.
EXCEPTIONAL_TERMINAL_STATES: Set[DecisionState] = {
    DecisionState.REJECTED,
    DecisionState.EXPIRED,
    DecisionState.CANCELLED,
    DecisionState.FAILED,
    DecisionState.VETOED,
}

# Tous les états terminaux — un packet dans ces états ne peut plus progresser.
# POSTMORTEM_ANALYZED est terminal nominal (fin de flux complet) mais N'EST PAS
# exceptionnel : il ne peut être atteint que depuis CLOSED via le graphe.
# Distinction critique : empêche CREATED → POSTMORTEM_ANALYZED ou tout autre
# court-circuit qui casserait la causalité, les analytics et les replay engines.
TERMINAL_STATES: Set[DecisionState] = EXCEPTIONAL_TERMINAL_STATES | {
    DecisionState.POSTMORTEM_ANALYZED,
}

# Graphe des transitions valides — non-terminales uniquement.
# Règle : seuls EXCEPTIONAL_TERMINAL_STATES sont accessibles depuis n'importe
# quel état non-terminal (veto système, expiry, panne).
# REGIME_VALIDATED est optionnel : CONTEXT_ENRICHED peut le court-circuiter
# si aucune couche de validation de régime n'est présente dans le pipeline.
_DS = DecisionState
VALID_TRANSITIONS: Dict[DecisionState, List[DecisionState]] = {
    _DS.CREATED: [_DS.SIGNAL_GENERATED],
    _DS.SIGNAL_GENERATED: [_DS.CONTEXT_ENRICHED],
    _DS.CONTEXT_ENRICHED: [_DS.REGIME_VALIDATED, _DS.RISK_EVALUATED],
    _DS.REGIME_VALIDATED: [_DS.RISK_EVALUATED],
    _DS.RISK_EVALUATED: [_DS.APPROVED],
    _DS.APPROVED: [_DS.EXECUTION_PENDING],
    _DS.EXECUTION_PENDING: [_DS.EXECUTED],
    _DS.EXECUTED: [_DS.MONITORED],
    _DS.MONITORED: [_DS.CLOSED],
    _DS.CLOSED: [_DS.POSTMORTEM_ANALYZED],
}
del _DS

# STI — contraintes croisées : catégorie sémantique × état du cycle de vie.
# Un état listé ici est STRUCTURELLEMENT INTERDIT pour la catégorie donnée,
# quelle que soit la validité graphique. Appliqué dans transition_to() (Garde 3).
#
# TRADE   : aucune restriction supplémentaire (cycle de vie complet autorisé).
# SYSTEM  : événements d'infrastructure (exceptions, ENL) — ne peuvent jamais
#           atteindre les états d'exécution ou d'approbation du capital.
# GOVERNANCE : décisions d'autorité pure — ne peuvent pas recevoir d'approbation
#              de trading ni accéder au pipeline d'exécution.
CATEGORY_BLOCKED_STATES: dict["PacketEventCategory", frozenset["DecisionState"]] = {
    PacketEventCategory.SYSTEM: frozenset(
        {
            DecisionState.APPROVED,
            DecisionState.EXECUTION_PENDING,
            DecisionState.EXECUTED,
            DecisionState.MONITORED,
            DecisionState.CLOSED,
            DecisionState.POSTMORTEM_ANALYZED,
        }
    ),
    PacketEventCategory.GOVERNANCE: frozenset(
        {
            DecisionState.APPROVED,
            DecisionState.EXECUTION_PENDING,
            DecisionState.EXECUTED,
            DecisionState.MONITORED,
            DecisionState.CLOSED,
            DecisionState.POSTMORTEM_ANALYZED,
        }
    ),
    # PacketEventCategory.TRADE : aucune entrée → pas de restriction
}


# ---------------------------------------------------------------------------
# Structures immuables (slots=True pour performance et sécurité)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class StateTransition:
    """
    Enregistrement d'une transition d'état.
    Devient : audit trail, replay engine, dataset RL, debugger causal.

    duration_ms       : temps passé dans from_state avant cette transition
    confidence_before : confiance du packet au moment de quitter from_state
    confidence_after  : confiance après la transition (post add_reasoning)
    previous_hash     : SHA-256 de la transition précédente (chaîne de hachage)
    current_hash      : SHA-256 de cette transition (inclut previous_hash)
    """

    from_state: str
    to_state: str
    timestamp: datetime
    actor: str
    reason: str
    duration_ms: int = 0
    confidence_before: float = 0.0
    confidence_after: float = 0.0
    previous_hash: str = ""
    current_hash: str = ""

    @staticmethod
    def compute_hash(
        from_state: str,
        to_state: str,
        timestamp_iso: str,
        actor: str,
        reason: str,
        previous_hash: str,
    ) -> str:
        """
        SHA-256 déterministe de cette transition.
        Tout changement de contenu ou de chaîne produit un hash différent.
        """
        canonical = json.dumps(
            {
                "from_state": from_state,
                "to_state": to_state,
                "timestamp": timestamp_iso,
                "actor": actor,
                "reason": reason,
                "previous_hash": previous_hash,
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_state": self.from_state,
            "to_state": self.to_state,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "reason": self.reason,
            "duration_ms": self.duration_ms,
            "confidence_before": self.confidence_before,
            "confidence_after": self.confidence_after,
            "previous_hash": self.previous_hash,
            "current_hash": self.current_hash,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> StateTransition:
        return cls(
            from_state=d["from_state"],
            to_state=d["to_state"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            actor=d["actor"],
            reason=d["reason"],
            duration_ms=int(d.get("duration_ms", 0)),
            confidence_before=float(d.get("confidence_before", 0.0)),
            confidence_after=float(d.get("confidence_after", 0.0)),
            previous_hash=d.get("previous_hash", ""),
            current_hash=d.get("current_hash", ""),
        )


@dataclass(slots=True)
class ReasoningEntry:
    """
    Entrée de raisonnement structurée.
    Remplace List[str] — exploitable par l'explainability layer et le ML.

    confidence_impact : delta appliqué à la confiance par cet agent
                        (positif = renforce, négatif = affaiblit, 0 = neutre)
    category          : famille sémantique du raisonnement — permet de mesurer
                        l'impact moyen par type sur l'EV réel (meta-learning futur)
                        Exemples : "trend_alignment", "regime_confirmation",
                                   "volatility_penalty", "liquidity_warning",
                                   "risk_governance", "signal_quality"
    """

    actor: str
    message: str
    confidence_impact: float
    timestamp: datetime
    category: ReasoningCategory = ReasoningCategory.UNCATEGORIZED
    severity: ReasoningSeverity = ReasoningSeverity.INFO

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actor": self.actor,
            "message": self.message,
            "confidence_impact": self.confidence_impact,
            "timestamp": self.timestamp.isoformat(),
            "category": self.category.value,
            "severity": self.severity.value,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ReasoningEntry:
        try:
            category = ReasoningCategory(d.get("category", "uncategorized"))
        except ValueError:
            category = ReasoningCategory.UNCATEGORIZED
        return cls(
            actor=d["actor"],
            message=d["message"],
            confidence_impact=float(d.get("confidence_impact", 0.0)),
            timestamp=datetime.fromisoformat(d["timestamp"]),
            category=category,
            severity=ReasoningSeverity(d.get("severity", "INFO")),
        )


# ---------------------------------------------------------------------------
# Contrat principal
# ---------------------------------------------------------------------------


@dataclass
class DecisionPacket:
    """
    Vecteur d'intention qui traverse toutes les couches du système.

    Chaque couche lit le packet, l'enrichit via les méthodes officielles,
    et le passe à la suivante. Aucune couche ne remonte vers le haut.

    La mutation d'état passe UNIQUEMENT par transition_to().
    L'écriture directe de lifecycle_state est interdite par convention.

    Cycle nominal :
        signal_engine → intelligence layers → risk_gate → portfolio_brain
        → order_sizer → execution_engine → trade_logger → postmortem
    """

    # --- Version du schéma (incrémenter à chaque rupture) -----------------
    version: int = 1

    # --- Identité ---------------------------------------------------------
    packet_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_cycle_id: Optional[str] = None  # ID du scan/batch ayant généré ce packet
    context_id: Optional[str] = None  # Clé vers DecisionContext (données lourdes)

    # --- Instrument -------------------------------------------------------
    symbol: str = ""
    timeframe: str = "1h"

    # --- Catégorie sémantique (DPSS) ----------------------------------------
    # Défaut TRADE pour backward-compat. Mettre SYSTEM pour les records ENL-2,
    # GOVERNANCE pour les rejects d'autorité hors signal.
    event_category: PacketEventCategory = PacketEventCategory.TRADE

    # --- Signal de base ---------------------------------------------------
    side: DecisionSide = DecisionSide.FLAT
    confidence: float = 0.0  # 0–100, compat: reflète adjusted_confidence
    confidence_raw: Optional[float] = None  # score brut LSE, immuable
    adjusted_confidence: Optional[float] = None  # score pipeline après reasoning
    expected_value: float = 0.0  # ratio risque/rendement attendu

    # --- Contexte de marché -----------------------------------------------
    regime: MarketRegime = MarketRegime.UNKNOWN

    # --- Prix et niveaux --------------------------------------------------
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    r_multiple: Optional[float] = None  # (TP - entry) / (entry - SL)

    # --- Risk & sizing ----------------------------------------------------
    risk_score: float = 0.0  # 0–100, produit par risk_gate
    allocation_pct: float = 0.0  # % du capital alloué
    conviction: ConvictionLevel = ConvictionLevel.SKIP

    # --- Veto (raccourci rapide — reflété dans lifecycle_state) -----------
    veto: bool = False
    veto_reason: Optional[str] = None

    # --- Machine d'état ---------------------------------------------------
    lifecycle_state: DecisionState = DecisionState.CREATED
    state_history: List[StateTransition] = field(default_factory=list)

    # --- Traçabilité agents -----------------------------------------------
    source_agents: List[str] = field(default_factory=list)
    reasoning: List[ReasoningEntry] = field(default_factory=list)

    # --- Données quantitatives ML-ready -----------------------------------
    # Règle : uniquement des float, exploitables directement par un modèle.
    # Exemple : {"rsi": 71.2, "atr": 182.1, "ema_spread": 0.028}
    features: Dict[str, float] = field(default_factory=dict)

    # --- Données runtime / debug (humain-ready) ---------------------------
    # Règle : jamais parsé dans la logique métier.
    # Exemple : {"exchange": "binance", "latency_ms": 182}
    metadata: Dict[str, Any] = field(default_factory=dict)

    # --- Signature Ed25519 (C-02) — posée par seal() après état final -----
    ed25519_signature: str = field(default="")
    signed_at: float = field(default=0.0)

    # ---------------------------------------------------------------------------
    # Machine d'état — seul point de mutation d'état autorisé
    # ---------------------------------------------------------------------------

    def __post_init__(self) -> None:
        base = max(0.0, min(100.0, float(self.confidence)))
        if self.confidence_raw is None:
            self.confidence_raw = base
        if self.adjusted_confidence is None:
            self.adjusted_confidence = base
        self.confidence = max(0.0, min(100.0, float(self.adjusted_confidence)))

    def transition_to(
        self,
        new_state: DecisionState,
        actor: str,
        reason: str,
    ) -> None:
        """
        Transition officielle vers un nouvel état.

        Valide la transition contre VALID_TRANSITIONS (graphe formel).
        Les états terminaux sont toujours accessibles depuis tout état non-terminal.
        Un packet déjà terminal ne peut plus transitionner.

        Raises RuntimeError si la transition est hors graphe.
        """
        current = self.lifecycle_state

        # Garde 1 : état terminal → impossible de progresser
        if current in TERMINAL_STATES:
            raise RuntimeError(
                f"Transition interdite : packet {self.packet_id} est déjà "
                f"dans l'état terminal {current.value}. "
                f"Demandé par {actor} vers {new_state.value}."
            )

        # Garde 2 : transition hors graphe canonique.
        # S4 — consulte lifecycle.ALLOWED_TRANSITIONS comme source unique de vérité.
        # Le graphe complet encode explicitement nominal + terminaux exceptionnels.
        try:
            from core.lifecycle import is_transition_allowed as _ita
            from core.lifecycle import successors as _succs

            _use_lifecycle = True
        except ImportError:
            _use_lifecycle = False

        if _use_lifecycle:
            if not _ita(current, new_state):
                _allowed_set = _succs(current)
                raise RuntimeError(
                    f"Transition invalide : {current.value} → {new_state.value} "
                    f"hors du graphe (lifecycle.ALLOWED_TRANSITIONS). "
                    f"Autorisées depuis {current.value} : "
                    f"{sorted(s.value for s in _allowed_set)}. "
                    f"Demandé par {actor}."
                )
        else:
            # Fallback : logique locale si lifecycle.py non importable (bootstrap)
            if new_state not in EXCEPTIONAL_TERMINAL_STATES:
                allowed = VALID_TRANSITIONS.get(current, [])
                if new_state not in allowed:
                    raise RuntimeError(
                        f"Transition invalide : {current.value} → {new_state.value} "
                        f"hors du graphe. Autorisées depuis {current.value} : "
                        f"{[s.value for s in allowed]}. "
                        f"Demandé par {actor}."
                    )

        # Garde 3 — STI : contraintes croisées catégorie × état (DPSS × lifecycle).
        # Un packet SYSTEM ou GOVERNANCE est structurellement incompatible
        # avec les états d'exécution — même si le graphe le permettrait.
        _sti_blocked = CATEGORY_BLOCKED_STATES.get(self.event_category, frozenset())
        if new_state in _sti_blocked:
            raise RuntimeError(
                f"STI violation : packet {self.packet_id!r} "
                f"({self.event_category.value}) ne peut pas transitionner "
                f"vers {new_state.value}. "
                f"Catégorie {self.event_category.value} est structurellement "
                f"incompatible avec les états d'exécution/approbation. "
                f"Demandé par {actor!r}."
            )

        now = datetime.utcnow()
        duration_ms = (
            int((now - self.state_history[-1].timestamp).total_seconds() * 1000)
            if self.state_history
            else 0
        )
        # confidence_before = confiance à l'entrée de from_state
        # (= confidence_after de la transition précédente, ou 0.0 au départ)
        confidence_before = (
            self.state_history[-1].confidence_after if self.state_history else 0.0
        )
        # Programme B — Hash chain : chaque transition est liée à la précédente.
        # previous_hash = hash de la transition n-1, ou "" pour la première.
        _prev_hash = self.state_history[-1].current_hash if self.state_history else ""
        _now_iso = now.isoformat()
        _cur_hash = StateTransition.compute_hash(
            from_state=current.value,
            to_state=new_state.value,
            timestamp_iso=_now_iso,
            actor=actor,
            reason=reason,
            previous_hash=_prev_hash,
        )
        transition = StateTransition(
            from_state=current.value,
            to_state=new_state.value,
            timestamp=now,
            actor=actor,
            reason=reason,
            duration_ms=duration_ms,
            confidence_before=confidence_before,
            confidence_after=self.confidence,
            previous_hash=_prev_hash,
            current_hash=_cur_hash,
        )
        self.state_history.append(transition)
        self.lifecycle_state = new_state
        _log.decision(
            "PACKET_TRANSITION",
            packet_id=self.packet_id,
            symbol=self.symbol,
            from_state=current.value,
            to_state=new_state.value,
            actor=actor,
            reason=reason,
            confidence=self.confidence,
            duration_ms=duration_ms,
        )
        # S1 — Métriques constitutionnelles : chaque transition est comptabilisée.
        # Pas de dépendance dure — metrics_bus optionnel (pas disponible en test minimal).
        try:
            from observability.metrics_bus import (
                metrics_bus as _mb,  # type: ignore[attr-defined]
            )

            _mb.increment("decision_packet", f"transition.{new_state.value.lower()}")
            _mb.increment("decision_packet", "transitions_total")
            if new_state.value in (
                "REJECTED",
                "VETOED",
                "FAILED",
                "CANCELLED",
                "EXPIRED",
            ):
                _mb.increment("decision_packet", f"terminal.{new_state.value.lower()}")
                _mb.increment("decision_packet", f"rejected_by.{actor.lower()[:32]}")
            if duration_ms > 0:
                _mb.record(
                    "decision_packet", "transition_duration_ms", float(duration_ms)
                )
        except Exception:
            pass

    # ---------------------------------------------------------------------------
    # Méthodes d'enrichissement — appelées par chaque couche
    # ---------------------------------------------------------------------------

    def add_agent(self, agent_name: str) -> None:
        """Enregistre qu'un agent a traité ce packet."""
        if agent_name not in self.source_agents:
            self.source_agents.append(agent_name)

    def add_reasoning(
        self,
        actor: str,
        message: str,
        confidence_impact: float = 0.0,
        category: ReasoningCategory = ReasoningCategory.UNCATEGORIZED,
        severity: ReasoningSeverity = ReasoningSeverity.INFO,
    ) -> None:
        """
        Ajoute une entrée de raisonnement structurée.
        confidence_impact applique automatiquement le delta à self.confidence.
        category permet le meta-learning : mesurer l'impact moyen par famille.
        severity exprime la nature opérationnelle de l'événement — orthogonal
        à confidence_impact (un WARNING peut avoir un impact positif et vice versa).
        """
        self.reasoning.append(
            ReasoningEntry(
                actor=actor,
                message=message,
                confidence_impact=confidence_impact,
                timestamp=datetime.utcnow(),
                category=category,
                severity=severity,
            )
        )
        if self.adjusted_confidence is None:
            self.adjusted_confidence = max(0.0, min(100.0, float(self.confidence)))
        if self.confidence_raw is None:
            self.confidence_raw = max(0.0, min(100.0, float(self.confidence)))
        if confidence_impact != 0.0:
            self.adjusted_confidence = max(
                0.0,
                min(100.0, float(self.adjusted_confidence) + confidence_impact),
            )
        self.confidence = float(self.adjusted_confidence)

    def veto_by(self, actor: str, reason: str) -> None:
        """Pose un veto. Transition vers VETOED immédiate."""
        self.veto = True
        self.veto_reason = reason
        self.add_agent(actor)
        self.add_reasoning(
            actor,
            f"[VETO] {reason}",
            confidence_impact=-100.0,
            category=ReasoningCategory.GOVERNANCE,
            severity=ReasoningSeverity.FATAL,
        )
        self.transition_to(DecisionState.VETOED, actor, reason)

    def reject(self, actor: str, reason: str) -> None:
        """Rejet par risk_gate ou portfolio_brain. no_trade_layer opère en amont via AgentVote."""
        self.add_agent(actor)
        self.add_reasoning(actor, f"[REJECTED] {reason}")
        self.transition_to(DecisionState.REJECTED, actor, reason)

    # ---------------------------------------------------------------------------
    # Signature Ed25519 (C-02)
    # ---------------------------------------------------------------------------

    def seal(self, signer) -> None:
        """
        Signe le packet avec Ed25519 via le signer fourni.
        Appelé après la transition vers l'état final (EXECUTED, REJECTED, VETOED…).
        Le signer doit implémenter sign(dict) -> dict (duck typing, pas d'import).
        """
        canonical = self.to_dict()
        canonical.pop("ed25519_signature", None)
        canonical.pop("signed_at", None)
        signed = signer.sign(canonical)
        self.ed25519_signature = signed["ed25519_signature"]
        self.signed_at = signed["signed_at"]

    def is_sealed(self) -> bool:
        """Vrai si le packet a été signé."""
        return bool(self.ed25519_signature)

    def verify_signature(self, signer) -> bool:
        """
        Vérifie la signature Ed25519.
        Retourne False si absent, invalide, ou contenu modifié.
        """
        if not self.is_sealed():
            return False
        return signer.verify(self.to_dict())

    # ---------------------------------------------------------------------------
    # Guards
    # ---------------------------------------------------------------------------

    def is_actionable(self) -> bool:
        """Vrai si le packet peut encore progresser vers l'exécution."""
        return (
            not self.veto
            and self.lifecycle_state not in TERMINAL_STATES
            and self.side != DecisionSide.FLAT
        )

    def is_terminal(self) -> bool:
        return self.lifecycle_state in TERMINAL_STATES

    def verify_chain(self) -> bool:
        """
        Programme B — Vérifie l'intégrité de la chaîne de hachage des transitions.

        Chaque transition doit :
          1. avoir un current_hash non vide
          2. référencer le current_hash de la transition précédente via previous_hash
          3. avoir un current_hash recalculable à partir de son contenu

        Retourne True si la chaîne est intègre, False si toute altération est détectée.
        """
        if not self.state_history:
            return True  # Pas de transitions : chaîne triviale

        expected_prev = ""
        for t in self.state_history:
            if not t.current_hash:
                return False  # Transition sans hash → non signée
            if t.previous_hash != expected_prev:
                return False  # Rupture de chaîne
            recomputed = StateTransition.compute_hash(
                from_state=t.from_state,
                to_state=t.to_state,
                timestamp_iso=t.timestamp.isoformat(),
                actor=t.actor,
                reason=t.reason,
                previous_hash=t.previous_hash,
            )
            if recomputed != t.current_hash:
                return False  # Contenu modifié post-hachage
            expected_prev = t.current_hash
        return True

    # ---------------------------------------------------------------------------
    # Sérialisation — logs, SQLite, replay, dashboard, event_bus, websocket
    # ---------------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Sérialisation plate JSON-safe. Zéro dépendance externe."""
        return {
            "version": self.version,
            "packet_id": self.packet_id,
            "created_at": self.created_at.isoformat(),
            "created_cycle_id": self.created_cycle_id,
            "context_id": self.context_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "event_category": self.event_category.value,
            "side": self.side.value,
            "confidence": self.confidence,
            "confidence_raw": self.confidence_raw,
            "adjusted_confidence": self.adjusted_confidence,
            "expected_value": self.expected_value,
            "regime": self.regime.value,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "r_multiple": self.r_multiple,
            "risk_score": self.risk_score,
            "allocation_pct": self.allocation_pct,
            "conviction": self.conviction.value,
            "veto": self.veto,
            "veto_reason": self.veto_reason,
            "lifecycle_state": self.lifecycle_state.value,
            "state_history": [t.to_dict() for t in self.state_history],
            "source_agents": self.source_agents,
            "reasoning": [r.to_dict() for r in self.reasoning],
            "features": self.features,
            "metadata": self.metadata,
            "ed25519_signature": self.ed25519_signature,
            "signed_at": self.signed_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> DecisionPacket:
        """Reconstruction depuis un dict sérialisé (replay, tests, migration)."""
        p = cls(
            version=int(d.get("version", 1)),
            packet_id=d.get("packet_id", str(uuid.uuid4())),
            created_at=(
                datetime.fromisoformat(d["created_at"])
                if "created_at" in d
                else datetime.utcnow()
            ),
            created_cycle_id=d.get("created_cycle_id"),
            context_id=d.get("context_id"),
            symbol=d.get("symbol", ""),
            timeframe=d.get("timeframe", "1h"),
            event_category=PacketEventCategory(d.get("event_category", "TRADE")),
            side=DecisionSide(d.get("side", "FLAT")),
            confidence=float(d.get("confidence", 0.0)),
            confidence_raw=(
                float(d["confidence_raw"])
                if d.get("confidence_raw") is not None
                else None
            ),
            adjusted_confidence=(
                float(d["adjusted_confidence"])
                if d.get("adjusted_confidence") is not None
                else None
            ),
            expected_value=float(d.get("expected_value", 0.0)),
            regime=MarketRegime(d.get("regime", "UNKNOWN")),
            entry_price=d.get("entry_price"),
            stop_loss=d.get("stop_loss"),
            take_profit=d.get("take_profit"),
            r_multiple=d.get("r_multiple"),
            risk_score=float(d.get("risk_score", 0.0)),
            allocation_pct=float(d.get("allocation_pct", 0.0)),
            conviction=ConvictionLevel(d.get("conviction", "SKIP")),
            veto=bool(d.get("veto", False)),
            veto_reason=d.get("veto_reason"),
            lifecycle_state=DecisionState(d.get("lifecycle_state", "CREATED")),
            state_history=[
                StateTransition.from_dict(t) for t in d.get("state_history", [])
            ],
            source_agents=list(d.get("source_agents", [])),
            reasoning=[ReasoningEntry.from_dict(r) for r in d.get("reasoning", [])],
            features=dict(d.get("features", {})),
            metadata=dict(d.get("metadata", {})),
            ed25519_signature=d.get("ed25519_signature", ""),
            signed_at=float(d.get("signed_at", 0.0)),
        )
        return p

    def __repr__(self) -> str:
        return (
            f"DecisionPacket("
            f"{self.symbol} {self.side.value} "
            f"conf={self.confidence:.0f} "
            f"state={self.lifecycle_state.value} "
            f"veto={self.veto}"
            f")"
        )
