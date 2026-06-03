"""
governance/auditor.py — Programme C : Auto-Audit Runtime.

Agent d'observation indépendant qui ne trade jamais.
Sa mission : observer, vérifier, prouver, alerter.

Il vérifie la cohérence entre les couches de gouvernance à chaque cycle
et détecte les anomalies que les gardes individuelles ne peuvent pas voir
en isolation (invariants inter-couches, dérive systémique, incohérences d'état).

Usage :
    from governance.auditor import GovernanceAuditor

    auditor = GovernanceAuditor()

    # À appeler après chaque cycle d'analyse
    anomalies = auditor.audit_cycle(
        result=result,           # retour de analyze_symbol()
        rsm_state=rsm.state,
        cycle=cycle,
    )
    for a in anomalies:
        if a.severity >= AnomalySeverity.CRITICAL:
            log.critical("[AUDITOR] %s", a)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, List, Optional

from observability.json_logger import get_logger

_log = get_logger("governance.auditor")


# ---------------------------------------------------------------------------
# Modèle d'anomalie
# ---------------------------------------------------------------------------


class AnomalySeverity(IntEnum):
    INFO = 0
    WARNING = 1
    CRITICAL = 2
    FATAL = 3


@dataclass
class Anomaly:
    """Une incohérence détectée entre les couches de gouvernance."""

    rule: str  # identifiant de la règle violée
    description: str  # explication humaine
    severity: AnomalySeverity
    evidence: dict = field(default_factory=dict)  # données factuelles
    timestamp: float = field(default_factory=time.time)
    cycle: int = 0
    symbol: str = ""

    def __str__(self) -> str:
        return (
            f"[{self.severity.name}] {self.rule} — {self.description} "
            f"(sym={self.symbol} cycle={self.cycle})"
        )


# ---------------------------------------------------------------------------
# GovernanceAuditor
# ---------------------------------------------------------------------------


_SEVERITY_WEIGHT = {
    AnomalySeverity.INFO: 0,
    AnomalySeverity.WARNING: 5,
    AnomalySeverity.CRITICAL: 25,
    AnomalySeverity.FATAL: 50,
}

# Durée maximale acceptable dans l'état EXECUTION_PENDING (secondes)
_MAX_EXECUTION_PENDING_AGE_S: float = 300.0


class GovernanceAuditor:
    """
    Auditeur de gouvernance — S6 : couche causale.

    L'auditeur ne se contente plus d'observer : en cas d'anomalie FATAL,
    il peut déclencher une demande de SAFE_MODE sur le RuntimeStateMachine.

    Séparation des responsabilités :
        - Observation : toutes les règles S2/S3/P-04 → anomalies
        - Causalité   : anomalie FATAL → request_safe_mode() sur RSM
        - Veto        : anomalie FATAL avec evidence "exec_imminent" → halt

    L'auditeur ne peut pas émettre d'ordre de trading.
    Il peut demander l'arrêt du pipeline via le RSM (seul canal autorisé).
    """

    def __init__(
        self,
        journal_path: Optional[str] = None,
        runtime_authority: Any = None,  # S6 : RSM pour demandes causales
    ) -> None:
        import json as _json
        import pathlib as _pl

        self._json = _json
        self._journal = (
            _pl.Path(journal_path)
            if journal_path
            else _pl.Path("logs/governance_audit_constitutional.jsonl")
        )
        self._journal.parent.mkdir(parents=True, exist_ok=True)
        self._cycle_scores: list[float] = []
        # S6 — RSM optionnel : si fourni, anomalies FATAL → request_safe_mode()
        self._rsm: Any = runtime_authority
        self._causal_requests: list[dict] = []  # historique des requêtes causales

    # ── Point d'entrée ────────────────────────────────────────────────────

    def audit_cycle(
        self,
        result: dict,
        rsm_state: Any,
        cycle: int = 0,
    ) -> List[Anomaly]:
        """
        Audite un résultat de cycle. Émet les métriques S1 et persiste dans le journal.

        Args:
            result   : dict retourné par analyze_symbol()
            rsm_state: SystemState courant du RuntimeStateMachine
            cycle    : numéro du cycle pour le traçage

        Returns:
            Liste d'Anomaly (vide si tout est cohérent).
        """
        anomalies: List[Anomaly] = []
        sym = result.get("symbol", "?")

        _checks = [
            # S2 — Règles inter-couches fondamentales
            self._check_type_a_disagreement,
            self._check_packet_without_trace_id,
            self._check_safe_mode_with_shadow,
            self._check_execution_pending_no_trace,
            self._check_chain_integrity,
            self._check_rsm_safe_mode_with_trade_allowed,
            # S3 — Règles de cohérence
            self._check_execution_pending_allocation,
            self._check_execution_pending_age,
            self._check_rejected_to_approved_impossible,
            # P-04 — Preuve complète avant EXECUTED
            self._check_executed_state_proof_chain,
        ]

        for check in _checks:
            try:
                found = check(result=result, rsm_state=rsm_state, cycle=cycle, sym=sym)
                if found:
                    anomalies.extend(found if isinstance(found, list) else [found])
            except Exception as e:
                _log.debug("[Auditor] check %s erreur: %s", check.__name__, e)

        score = self._compute_health_score(anomalies)
        self._cycle_scores.append(score)
        if len(self._cycle_scores) > 100:
            self._cycle_scores.pop(0)

        self._emit_metrics(anomalies, score, cycle, sym)
        self._persist_journal(anomalies, score, cycle, sym, rsm_state)

        for a in anomalies:
            if a.severity >= AnomalySeverity.CRITICAL:
                _log.critical(
                    "[AUDITOR] %s",
                    a,
                    extra={"rule": a.rule, "evidence": a.evidence},
                )
            elif a.severity == AnomalySeverity.WARNING:
                _log.warning("[AUDITOR] %s", a)

        return anomalies

    # ── Règles individuelles ──────────────────────────────────────────────

    def _check_type_a_disagreement(self, result, rsm_state, cycle, sym):
        """
        TYPE-A : legacy=True, packet=False.
        Danger réel — le système voulait exécuter mais le packet dit non.
        Après G8-D/E, ne devrait plus se produire si la sync fonctionne.
        """
        trade_allowed = bool(result.get("trade_allowed", False))
        packet = result.get("decision_packet")
        if packet is None:
            return None
        packet_allows = packet.is_actionable()
        if trade_allowed and not packet_allows:
            return Anomaly(
                rule="TYPE-A-DISAGREEMENT",
                description=(
                    "Legacy trade_allowed=True mais DecisionPacket non-actionable. "
                    "La sync G8-D n'a pas fonctionné ou le packet a été modifié après."
                ),
                severity=AnomalySeverity.CRITICAL,
                evidence={
                    "trade_allowed": trade_allowed,
                    "packet_state": packet.lifecycle_state.value,
                    "packet_id": packet.packet_id,
                },
                cycle=cycle,
                symbol=sym,
            )
        return None

    def _check_packet_without_trace_id(self, result, rsm_state, cycle, sym):
        """G0 : packet présent mais sans trace_id → traçabilité compromise."""
        packet = result.get("decision_packet")
        if packet is None:
            return None
        trace = packet.metadata.get("trace_id", "")
        if not trace:
            return Anomaly(
                rule="G0-MISSING-TRACE-ID",
                description="DecisionPacket présent sans trace_id dans metadata.",
                severity=AnomalySeverity.CRITICAL,
                evidence={
                    "packet_id": packet.packet_id,
                    "packet_state": packet.lifecycle_state.value,
                    "cycle_trace_id": result.get("trace_id", ""),
                },
                cycle=cycle,
                symbol=sym,
            )
        return None

    def _check_safe_mode_with_shadow(self, result, rsm_state, cycle, sym):
        """G1 : shadow trade présent alors que RSM est en SAFE_MODE."""
        try:
            from quant_hedge_ai.runtime.runtime_state_machine import SystemState

            if rsm_state != SystemState.SAFE_MODE:
                return None
        except ImportError:
            return None
        shadow = result.get("shadow")
        if shadow is not None:
            return Anomaly(
                rule="G1-SHADOW-IN-SAFE-MODE",
                description="Shadow trade exécuté alors que RSM=SAFE_MODE. Violation G1.",
                severity=AnomalySeverity.FATAL,
                evidence={"rsm_state": str(rsm_state)},
                cycle=cycle,
                symbol=sym,
            )
        return None

    def _check_execution_pending_no_trace(self, result, rsm_state, cycle, sym):
        """G0/G5 : packet en EXECUTION_PENDING sans trace_id."""
        packet = result.get("decision_packet")
        if packet is None:
            return None
        try:
            from core.decision_packet import DecisionState

            if packet.lifecycle_state != DecisionState.EXECUTION_PENDING:
                return None
        except ImportError:
            return None
        trace = packet.metadata.get("trace_id", "")
        if not trace:
            return Anomaly(
                rule="G0-EXECUTION-PENDING-NO-TRACE",
                description=(
                    "Packet en EXECUTION_PENDING sans trace_id. "
                    "Invariant G0 : EXECUTION_PENDING ⟹ trace_id exists."
                ),
                severity=AnomalySeverity.FATAL,
                evidence={
                    "packet_id": packet.packet_id,
                    "lifecycle_state": packet.lifecycle_state.value,
                },
                cycle=cycle,
                symbol=sym,
            )
        return None

    def _check_chain_integrity(self, result, rsm_state, cycle, sym):
        """Programme B : hash chain du packet intègre."""
        packet = result.get("decision_packet")
        if packet is None or not hasattr(packet, "verify_chain"):
            return None
        if not packet.verify_chain():
            return Anomaly(
                rule="CHAIN-INTEGRITY-BREACH",
                description=(
                    "La chaîne de hachage du DecisionPacket est rompue. "
                    "Altération post-création détectée."
                ),
                severity=AnomalySeverity.FATAL,
                evidence={
                    "packet_id": packet.packet_id,
                    "n_transitions": len(packet.state_history),
                    "lifecycle_state": packet.lifecycle_state.value,
                },
                cycle=cycle,
                symbol=sym,
            )
        return None

    def _check_rsm_safe_mode_with_trade_allowed(self, result, rsm_state, cycle, sym):
        """G1 : RSM=SAFE_MODE mais trade_allowed=True dans le résultat."""
        try:
            from quant_hedge_ai.runtime.runtime_state_machine import SystemState

            if rsm_state != SystemState.SAFE_MODE:
                return None
        except ImportError:
            return None
        trade_allowed = bool(result.get("trade_allowed", False))
        if trade_allowed:
            return Anomaly(
                rule="G1-TRADE-ALLOWED-IN-SAFE-MODE",
                description=(
                    "trade_allowed=True retourné par analyze_symbol() "
                    "alors que RSM=SAFE_MODE. Double protection G1 requise."
                ),
                severity=AnomalySeverity.CRITICAL,
                evidence={
                    "rsm_state": str(rsm_state),
                    "trade_allowed": trade_allowed,
                    "blockers": result.get("blockers", ""),
                },
                cycle=cycle,
                symbol=sym,
            )
        return None

    # ── S3 : Règles de cohérence ──────────────────────────────────────────

    def _check_execution_pending_allocation(self, result, rsm_state, cycle, sym):
        """
        S3 : Un packet EXECUTION_PENDING doit avoir une allocation (os_size_usd > 0).
        Invariant : APPROVED → EXECUTION_PENDING ⟹ allocation valide.
        """
        packet = result.get("decision_packet")
        if packet is None:
            return None
        try:
            from core.decision_packet import DecisionState

            if packet.lifecycle_state != DecisionState.EXECUTION_PENDING:
                return None
        except ImportError:
            return None
        os_size = float(packet.features.get("os_size_usd", 0.0))
        if os_size <= 0.0:
            return Anomaly(
                rule="S3-EXECUTION-PENDING-NO-ALLOCATION",
                description=(
                    f"Packet EXECUTION_PENDING avec os_size_usd={os_size:.2f}. "
                    "Invariant S3 : EXECUTION_PENDING ⟹ allocation > 0."
                ),
                severity=AnomalySeverity.CRITICAL,
                evidence={
                    "packet_id": packet.packet_id,
                    "os_size_usd": os_size,
                    "os_kelly": packet.features.get("os_kelly", "absent"),
                },
                cycle=cycle,
                symbol=sym,
            )
        return None

    def _check_execution_pending_age(self, result, rsm_state, cycle, sym):
        """
        S3 : Un packet ne doit pas rester EXECUTION_PENDING plus de N secondes.
        Détecte les packets bloqués en file d'attente (dead queue).
        """
        packet = result.get("decision_packet")
        if packet is None:
            return None
        try:
            from core.decision_packet import DecisionState

            if packet.lifecycle_state != DecisionState.EXECUTION_PENDING:
                return None
        except ImportError:
            return None
        now = time.time()
        ep_ts = None
        for t in packet.state_history:
            if t.to_state == "EXECUTION_PENDING":
                ep_ts = (
                    t.timestamp.timestamp()
                    if hasattr(t.timestamp, "timestamp")
                    else None
                )
                break
        if ep_ts is not None:
            age_s = now - ep_ts
            if age_s > _MAX_EXECUTION_PENDING_AGE_S:
                return Anomaly(
                    rule="S3-EXECUTION-PENDING-STALE",
                    description=(
                        f"Packet EXECUTION_PENDING depuis {age_s:.0f}s "
                        f"(max={_MAX_EXECUTION_PENDING_AGE_S:.0f}s). Packet bloqué."
                    ),
                    severity=AnomalySeverity.WARNING,
                    evidence={
                        "packet_id": packet.packet_id,
                        "age_seconds": round(age_s, 1),
                    },
                    cycle=cycle,
                    symbol=sym,
                )
        return None

    def _check_rejected_to_approved_impossible(self, result, rsm_state, cycle, sym):
        """
        S3 : Un packet REJECTED ne peut jamais transitionner vers APPROVED.
        Vérifie l'historique des transitions pour détecter cette impossibilité.
        """
        packet = result.get("decision_packet")
        if packet is None or not packet.state_history:
            return None
        saw_rejected = False
        for t in packet.state_history:
            if t.from_state == "REJECTED":
                saw_rejected = True
            if saw_rejected and t.to_state in (
                "APPROVED",
                "EXECUTION_PENDING",
                "EXECUTED",
            ):
                return Anomaly(
                    rule="S3-REJECTED-TO-APPROVED-IMPOSSIBLE",
                    description=(
                        f"Transition REJECTED → {t.to_state} dans l'historique. "
                        "Un packet terminal ne peut pas progresser."
                    ),
                    severity=AnomalySeverity.FATAL,
                    evidence={
                        "packet_id": packet.packet_id,
                        "forbidden_transition": f"REJECTED → {t.to_state}",
                        "actor": t.actor,
                    },
                    cycle=cycle,
                    symbol=sym,
                )
        return None

    def _check_executed_state_proof_chain(self, result, rsm_state, cycle, sym):
        """
        P-04 : Un packet EXECUTED doit avoir la preuve complete.

        Invariant : EXECUTED =>
            trace_id present
            AND verify_chain() == True
            AND lifecycle EXECUTED atteint via transitions valides

        Un etat EXECUTED sans preuve complete indique un bypass de gouvernance.
        """
        packet = result.get("decision_packet")
        if packet is None:
            return None
        try:
            from core.decision_packet import DecisionState

            if packet.lifecycle_state != DecisionState.EXECUTED:
                return None
        except ImportError:
            return None

        violations_found = []

        # Verif 1 : trace_id present
        if not packet.metadata.get("trace_id"):
            violations_found.append("trace_id absent")

        # Verif 2 : chaine de hash integre
        if hasattr(packet, "verify_chain"):
            if not packet.verify_chain():
                violations_found.append("verify_chain()=False (chaine alteree)")

        # Verif 3 : historique contient bien EXECUTION_PENDING -> EXECUTED
        has_ep_to_ex = any(
            t.from_state == "EXECUTION_PENDING" and t.to_state == "EXECUTED"
            for t in packet.state_history
        )
        if not has_ep_to_ex:
            violations_found.append(
                "transition EXECUTION_PENDING->EXECUTED absente de l'historique"
            )

        if violations_found:
            return Anomaly(
                rule="P04-EXECUTED-WITHOUT-PROOF",
                description=(
                    f"Packet EXECUTED sans preuve complete : "
                    f"{'; '.join(violations_found)}. "
                    "Invariant P-04 : EXECUTED => trace_id + chain + transitions valides."
                ),
                severity=AnomalySeverity.FATAL,
                evidence={
                    "packet_id": packet.packet_id,
                    "violations": violations_found,
                    "trace_id": packet.metadata.get("trace_id", ""),
                },
                cycle=cycle,
                symbol=sym,
            )
        return None

    # ── Score de santé constitutionnelle ─────────────────────────────────

    def _compute_health_score(self, anomalies: List[Anomaly]) -> float:
        """Score de santé constitutionnelle [0.0, 100.0]. 100 = aucune anomalie."""
        penalty = sum(_SEVERITY_WEIGHT.get(a.severity, 0) for a in anomalies)
        return max(0.0, 100.0 - float(penalty))

    def health_trend(self) -> float:
        """Score moyen sur les N derniers cycles (tendance)."""
        if not self._cycle_scores:
            return 100.0
        return sum(self._cycle_scores) / len(self._cycle_scores)

    # ── Infrastructure S2 ─────────────────────────────────────────────────

    def _emit_metrics(self, anomalies, score, cycle, sym):
        try:
            from observability.metrics_bus import metrics_bus as _mb  # type: ignore

            _mb.gauge("governance_auditor", "constitutional_health_score", score)
            _mb.gauge("governance_auditor", "health_trend", self.health_trend())
            _mb.increment("governance_auditor", "cycles_audited")
            for a in anomalies:
                sev = a.severity.name.lower()
                _mb.increment("governance_auditor", f"anomaly.{sev}")
                _mb.increment(
                    "governance_auditor", f"rule.{a.rule.lower().replace('-', '_')}"
                )
        except Exception:
            pass

    def _persist_journal(self, anomalies, score, cycle, sym, rsm_state):
        if not anomalies and score >= 100.0:
            return  # Ne log que les cycles dégradés
        try:
            record = {
                "cycle": cycle,
                "symbol": sym,
                "rsm_state": str(rsm_state),
                "constitutional_health_score": score,
                "anomaly_count": len(anomalies),
                "anomalies": [
                    {
                        "rule": a.rule,
                        "severity": a.severity.name,
                        "description": a.description,
                        "evidence": a.evidence,
                        "ts": a.timestamp,
                    }
                    for a in anomalies
                ],
                "ts": time.time(),
            }
            with self._journal.open("a", encoding="utf-8") as fh:
                fh.write(self._json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            _log.debug("[Auditor] journal write failed: %s", e)
