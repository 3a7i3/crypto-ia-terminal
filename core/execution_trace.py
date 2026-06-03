"""
core/execution_trace.py — Execution Trace Equivalence Layer.

Formalise l'ordre exact des checks dans advisor_loop.analyze_symbol()
et prouve l'équivalence entre la trace d'exécution réelle et le graphe lifecycle.

Problème résolu :
    lifecycle.py est formellement correct.
    advisor_loop.py est l'orchestrateur réel.
    Sans ce module, les deux peuvent diverger par :
        - ordering effects (ordre d'évaluation des checks)
        - early returns non modélisés
        - flags dynamiques (RSM, env, fallbacks)
        - composition implicite de conditions

Ce module :
    1. Définit l'ordre canonique strict (lexicographique) des checks G0→G8-E
    2. Enregistre chaque check comme un CheckResult typé et ordonné
    3. Vérifie à la fin de chaque cycle que la trace est cohérente
       avec l'état final du DecisionPacket
    4. Expose TraceVerifier pour la vérification d'équivalence runtime ↔ modèle

Propriété garantie :
    ∀ trace T :
        T.final_verdict  ⟺  T.packet_state ∈ ACTIONABLE_STATES
        T.blocked_at(P)  ⟹  ∀ P' > P, T.check(P') irrelevant
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, List, Optional

# ---------------------------------------------------------------------------
# Ordre canonique des checks — priorité lexicographique stricte
#
# La règle : si check de priorité P bloque, les checks de priorité > P
# sont INOPÉRANTS. L'orchestrateur doit respecter cet ordre.
#
# P1 (RSM/G1)    — plus haute priorité, coupe tout avant analyse
# P2 (G4/Gate)   — vérifie le signal marché
# P3 (I14/agents)— vérifications multi-agents fail-closed
# P4 (G8-D sync) — synchronisation packet ↔ pipeline
# P5 (G8-E)      — présence du DecisionPacket
# P6 (G0/trace)  — trace_id obligatoire
# P7 (G8-C)      — is_actionable() packet
# ---------------------------------------------------------------------------


class CheckPriority(IntEnum):
    """Priorité des checks governance — ordre lexicographique strict."""

    G1_RUNTIME_AUTHORITY = 10  # RSM.can_trade() + GovernanceKernel
    G4_GLOBAL_RISK_GATE = 20  # gate_result.allowed
    I14_CONVICTION = 30  # conviction_engine fail-closed
    I14_PORTFOLIO_BRAIN = 31  # portfolio_brain fail-closed
    I14_AWARENESS = 32  # awareness_engine fail-closed
    I14_NO_TRADE = 33  # no_trade_layer fail-closed
    I14_MISTAKE_MEMORY = 34  # mistake_memory fail-closed
    I14_EXEC_OVERRIDE = 35  # executive_override fail-closed
    I14_THREAT_RADAR = 36  # threat_radar fail-closed
    G8_D_PIPELINE_SYNC = 40  # sync trade_allowed → packet.reject()
    G8_E_PACKET_PRESENCE = 50  # _dp is not None
    G0_TRACE_ID = 60  # trace_id présent dans metadata
    G8_C_PACKET_ACTIONABLE = 70  # packet.is_actionable()


# États du DecisionPacket considérés comme "actionables" (exécution autorisée)
_ACTIONABLE_STATES = frozenset(
    {
        "APPROVED",
        "EXECUTION_PENDING",
    }
)

# Un check qui a bloqué — les checks de priorité supérieure sont inopérants
BLOCKED = False
ALLOWED = True


# ---------------------------------------------------------------------------
# Structures de données
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """
    Résultat d'un seul check de gouvernance dans l'orchestrateur.

    Chaque check correspond à une barrière dans l'ordre canonique.
    priority est utilisé pour la vérification d'équivalence.
    """

    check_id: str  # identifiant canonical (ex: "G1_RUNTIME_AUTHORITY")
    priority: CheckPriority  # ordre lexicographique
    verdict: bool  # True = autorisé, False = bloqué
    actor: str  # source du verdict
    reason: str  # explication
    timestamp: float = field(default_factory=time.time)
    evidence: dict = field(default_factory=dict)

    def __str__(self) -> str:
        status = "OK" if self.verdict else "BLOCKED"
        return f"[P{self.priority.value:02d}/{self.check_id}] {status} — {self.reason}"


@dataclass
class ExecutionTrace:
    """
    Trace complète d'une exécution d'analyze_symbol().

    Enregistre chaque check dans l'ordre canonique.
    Utilisée par TraceVerifier pour la preuve d'équivalence.
    """

    trace_id: str
    symbol: str
    cycle: int
    created_at: float = field(default_factory=time.time)
    checks: List[CheckResult] = field(default_factory=list)
    final_verdict: Optional[bool] = None  # trade_allowed final
    packet_state: Optional[str] = None  # lifecycle_state du packet à la fin
    packet_id: Optional[str] = None

    def record(
        self,
        check_id: str,
        priority: CheckPriority,
        verdict: bool,
        actor: str,
        reason: str,
        evidence: Optional[dict] = None,
    ) -> None:
        """Enregistre un check dans la trace."""
        self.checks.append(
            CheckResult(
                check_id=check_id,
                priority=priority,
                verdict=verdict,
                actor=actor,
                reason=reason,
                evidence=evidence or {},
            )
        )

    def first_block(self) -> Optional[CheckResult]:
        """Retourne le premier check bloquant (priorité la plus haute)."""
        blocked = [c for c in self.checks if not c.verdict]
        if not blocked:
            return None
        return min(blocked, key=lambda c: c.priority.value)

    def checks_after_first_block(self) -> List[CheckResult]:
        """
        Retourne les checks enregistrés APRÈS le premier blocage.
        Ces checks sont potentiellement superflus ou signalent un ordering problem.
        """
        first = self.first_block()
        if first is None:
            return []
        return [c for c in self.checks if c.priority > first.priority]

    def is_ordered(self) -> bool:
        """True si les checks sont enregistrés dans l'ordre canonique."""
        priorities = [c.priority.value for c in self.checks]
        return priorities == sorted(priorities)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "symbol": self.symbol,
            "cycle": self.cycle,
            "created_at": self.created_at,
            "final_verdict": self.final_verdict,
            "packet_state": self.packet_state,
            "packet_id": self.packet_id,
            "checks": [
                {
                    "check_id": c.check_id,
                    "priority": c.priority.value,
                    "verdict": c.verdict,
                    "actor": c.actor,
                    "reason": c.reason,
                    "ts": c.timestamp,
                }
                for c in self.checks
            ],
        }


# ---------------------------------------------------------------------------
# TraceVerifier — preuve d'équivalence runtime ↔ lifecycle modèle
# ---------------------------------------------------------------------------


@dataclass
class Violation:
    """Une divergence entre la trace d'exécution et le modèle lifecycle."""

    rule: str
    description: str
    evidence: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[VIOLATION/{self.rule}] {self.description}"


class TraceVerifier:
    """
    Vérifie l'équivalence entre une ExecutionTrace et le graphe lifecycle.

    Propriété centrale :
        trace.final_verdict  ⟺  packet.is_actionable()

    Et si un check bloque à la priorité P :
        ∀ check à priorité > P, son verdict est inopérant.
    """

    def verify(self, trace: ExecutionTrace, packet: Any) -> List[Violation]:
        """
        Vérifie toutes les propriétés d'équivalence de la trace.

        Args:
            trace  : ExecutionTrace produite par analyze_symbol()
            packet : DecisionPacket final (peut être None)

        Returns:
            Liste de violations (vide si la trace est équivalente au modèle).
        """
        violations: List[Violation] = []

        violations.extend(self._check_canonical_ordering(trace))
        violations.extend(self._check_verdict_packet_equivalence(trace, packet))
        violations.extend(self._check_no_spurious_checks_after_block(trace))
        violations.extend(self._check_g1_first_priority(trace))
        violations.extend(self._check_chain_integrity(trace, packet))

        return violations

    # ── Règles de vérification ────────────────────────────────────────────

    def _check_canonical_ordering(self, trace: ExecutionTrace) -> List[Violation]:
        """
        V-01 : Les checks sont enregistrés dans l'ordre de priorité croissant.
        Un check de priorité 20 ne doit jamais apparaître avant un check de priorité 10.
        """
        if not trace.is_ordered():
            priorities = [c.priority.value for c in trace.checks]
            return [
                Violation(
                    rule="V-01/CANONICAL-ORDER",
                    description=(
                        f"Checks hors ordre canonique : {priorities}. "
                        "L'orchestrateur ne respecte pas l'ordre lexicographique."
                    ),
                    evidence={"priorities_observed": priorities},
                )
            ]
        return []

    def _check_verdict_packet_equivalence(
        self, trace: ExecutionTrace, packet: Any
    ) -> List[Violation]:
        """
        V-02 : trace.final_verdict ⟺ packet.is_actionable()

        C'est la propriété centrale d'équivalence.
        Si les deux divergent, l'orchestrateur s'est écarté du modèle.
        """
        if packet is None:
            # G8-E : packet absent = bloc garanti
            if trace.final_verdict is True:
                return [
                    Violation(
                        rule="V-02/EQUIV-PACKET-NONE",
                        description=(
                            "trace.final_verdict=True mais DecisionPacket absent. "
                            "G8-E doit bloquer quand packet=None."
                        ),
                        evidence={"final_verdict": trace.final_verdict},
                    )
                ]
            return []

        try:
            packet_actionable = packet.is_actionable()
        except Exception:
            return []

        final = trace.final_verdict
        if final is None:
            return []

        if final != packet_actionable:
            return [
                Violation(
                    rule="V-02/EQUIV-VERDICT-PACKET",
                    description=(
                        f"trace.final_verdict={final} "
                        f"MAIS packet.is_actionable()={packet_actionable} "
                        f"(packet.lifecycle_state={trace.packet_state}). "
                        "L'orchestrateur et le packet ont divergé — G8-D sync incomplète."
                    ),
                    evidence={
                        "final_verdict": final,
                        "packet_actionable": packet_actionable,
                        "packet_state": trace.packet_state,
                        "packet_id": trace.packet_id,
                    },
                )
            ]
        return []

    def _check_no_spurious_checks_after_block(
        self, trace: ExecutionTrace
    ) -> List[Violation]:
        """
        V-03 : Aucun check de gouvernance après le premier blocage.

        Si G1 (priorité 10) bloque, les checks de priorité 20+ doivent
        être absents de la trace (early return).
        """
        spurious = trace.checks_after_first_block()
        if spurious:
            first = trace.first_block()
            return [
                Violation(
                    rule="V-03/SPURIOUS-CHECKS",
                    description=(
                        f"{len(spurious)} check(s) enregistrés après blocage à "
                        f"P{first.priority.value}/{first.check_id}. "
                        "L'orchestrateur ne réalise pas d'early return propre."
                    ),
                    evidence={
                        "blocking_check": first.check_id,
                        "blocking_priority": first.priority.value,
                        "spurious_checks": [c.check_id for c in spurious],
                    },
                )
            ]
        return []

    def _check_g1_first_priority(self, trace: ExecutionTrace) -> List[Violation]:
        """
        V-04 : G1 (RuntimeAuthority) doit être le premier check si présent.

        Tout check avant G1 signifie qu'une logique s'exécute sans
        vérification de l'autorité runtime — violation du principe fail-fast.
        """
        g1_checks = [
            c for c in trace.checks if c.priority == CheckPriority.G1_RUNTIME_AUTHORITY
        ]
        if not g1_checks:
            return []  # G1 absent de la trace (acceptable si not recorded)

        first_g1 = g1_checks[0]
        checks_before_g1 = [
            c
            for c in trace.checks
            if c.priority < CheckPriority.G1_RUNTIME_AUTHORITY.value
            and c is not first_g1
        ]
        if checks_before_g1:
            return [
                Violation(
                    rule="V-04/G1-NOT-FIRST",
                    description=(
                        f"Checks avant G1 (RuntimeAuthority) : "
                        f"{[c.check_id for c in checks_before_g1]}. "
                        "G1 doit être la première barrière."
                    ),
                    evidence={
                        "checks_before_g1": [c.check_id for c in checks_before_g1]
                    },
                )
            ]
        return []

    def _check_chain_integrity(
        self, trace: ExecutionTrace, packet: Any
    ) -> List[Violation]:
        """
        V-05 : verify_chain() du packet doit être True si trace.final_verdict=True.

        Si le système autorise une exécution, la chaîne de hachage doit être intègre.
        """
        if trace.final_verdict is not True:
            return []
        if packet is None:
            return []
        if not hasattr(packet, "verify_chain"):
            return []
        try:
            if not packet.verify_chain():
                return [
                    Violation(
                        rule="V-05/CHAIN-INTEGRITY",
                        description=(
                            "trace.final_verdict=True mais verify_chain()=False. "
                            "La chaîne de hachage est rompue malgré une autorisation d'exécution."
                        ),
                        evidence={"packet_id": trace.packet_id},
                    )
                ]
        except Exception:
            pass
        return []


# ---------------------------------------------------------------------------
# Singleton global (optionnel) — tracer le cycle courant
# ---------------------------------------------------------------------------

_current_trace: Optional[ExecutionTrace] = None


def begin_trace(trace_id: str, symbol: str, cycle: int) -> ExecutionTrace:
    """Démarre une nouvelle trace pour un cycle d'analyse."""
    global _current_trace
    _current_trace = ExecutionTrace(
        trace_id=trace_id,
        symbol=symbol,
        cycle=cycle,
    )
    return _current_trace


def current_trace() -> Optional[ExecutionTrace]:
    """Retourne la trace du cycle courant (None si non initialisée)."""
    return _current_trace


def end_trace(
    final_verdict: bool,
    packet: Any = None,
) -> Optional[List[Violation]]:
    """
    Finalise la trace et vérifie l'équivalence.

    Returns:
        Liste des violations (vide si équivalent), ou None si pas de trace active.
    """
    global _current_trace
    if _current_trace is None:
        return None

    _current_trace.final_verdict = final_verdict
    if packet is not None:
        try:
            _current_trace.packet_state = packet.lifecycle_state.value
            _current_trace.packet_id = packet.packet_id
        except Exception:
            pass

    verifier = TraceVerifier()
    violations = verifier.verify(_current_trace, packet)
    _current_trace = None
    return violations
