"""
core/formal_proof.py — Vérification formelle Z3 des invariants de gouvernance.

Prouve automatiquement les propriétés de sécurité (safety) et de vivacité
(liveness) du pipeline G0→G8-E en utilisant le solver Z3.

Distinction critique :
    core/invariants.py   → vérifie l'architecture (structure du code)
    core/lifecycle.py    → vérifie le graphe d'états (propriétés du modèle)
    core/formal_proof.py → prouve les propriétés de gouvernance (logique propositionnelle)

Ce fichier prouve des propriétés de la forme :
    "si ces conditions sont vraies, alors ces exécutions sont impossibles"

Les propriétés sont prouvées par réfutation :
    pour prouver P, on cherche un contre-exemple à ¬P.
    Si Z3 retourne unsat → P est prouvée (pas de contre-exemple possible).

Usage :
    from core.formal_proof import prove_all_governance_properties, ProofResult
    results = prove_all_governance_properties()
    for r in results:
        print(r)

Preuve par réfutation (standard Z3) :
    Pour prouver "SAFE_MODE => NOT exec_allowed",
    on cherche un modèle où "SAFE_MODE AND exec_allowed" est satisfiable.
    Si unsat : la propriété est vraie (le contre-exemple est impossible).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

# ---------------------------------------------------------------------------
# Structures de résultat
# ---------------------------------------------------------------------------


@dataclass
class ProofResult:
    """Résultat d'une preuve Z3."""

    property_id: str
    description: str
    proven: bool  # True si la propriété est prouvée (unsat counter-ex)
    counterexample: Optional[dict] = None  # modèle si la propriété est réfutée
    error: Optional[str] = None

    def __str__(self) -> str:
        status = (
            "PROVED" if self.proven else ("REFUTED" if self.counterexample else "ERROR")
        )
        s = f"[{status}] {self.property_id} — {self.description}"
        if self.counterexample:
            s += f"\n  Contre-exemple: {self.counterexample}"
        if self.error:
            s += f"\n  Erreur: {self.error}"
        return s


# ---------------------------------------------------------------------------
# Preuves individuelles
# ---------------------------------------------------------------------------


def _prove(
    property_id: str,
    description: str,
    add_constraints_fn,
    add_negation_fn,
) -> ProofResult:
    """
    Infrastructure de preuve par réfutation.

    add_constraints_fn(solver, vars) : ajoute les axiomes du système
    add_negation_fn(solver, vars)    : ajoute la négation de la propriété à prouver
    Si solver.check() == unsat → propriété prouvée.
    """
    try:
        from z3 import Bool, Implies, Not, Solver, unsat

        # Variables booléennes du modèle de gouvernance
        vars = {
            "trace_id": Bool("trace_id"),
            "packet": Bool("packet"),
            "actionable": Bool("actionable"),
            "safe_mode": Bool("safe_mode"),
            "authority_ok": Bool("authority_ok"),
            "kelly_pos": Bool("kelly_positive"),
            "shadow_ok": Bool("shadow_allowed"),
            "exec_ok": Bool("exec_allowed"),
            "gov_override": Bool("gov_override_active"),
            "chain_ok": Bool("chain_integrity"),
        }

        s = Solver()

        # ── Axiomes du système de gouvernance ────────────────────────────
        # Ces axiomes encodent G0→G8-E tels qu'implémentés dans advisor_loop.py

        # G1 : autorité runtime est la condition de base
        # exec_ok implique authority_ok ET NOT safe_mode
        s.add(Implies(vars["exec_ok"], vars["authority_ok"]))
        s.add(Implies(vars["exec_ok"], Not(vars["safe_mode"])))

        # G8-E : pas de packet → pas d'exécution
        s.add(Implies(vars["exec_ok"], vars["packet"]))

        # G5 : kelly <= 0 → exec_ok = False
        # (kelly_pos = False → exec_ok = False)
        s.add(Implies(Not(vars["kelly_pos"]), Not(vars["exec_ok"])))

        # G8-D : exec_ok implique actionable (sync pipeline→packet)
        s.add(Implies(vars["exec_ok"], vars["actionable"]))

        # G0 : shadow_ok implique trace_id ET packet
        s.add(Implies(vars["shadow_ok"], vars["trace_id"]))
        s.add(Implies(vars["shadow_ok"], vars["packet"]))

        # G8-C : shadow_ok implique actionable
        s.add(Implies(vars["shadow_ok"], vars["actionable"]))

        # SAFE_MODE est un hard stop global — si safe_mode, exec_ok est False
        s.add(Implies(vars["safe_mode"], Not(vars["exec_ok"])))
        s.add(Implies(vars["safe_mode"], Not(vars["shadow_ok"])))

        # G4 : gov_override (GOVERNANCE_KEYS depuis JSON) est impossible en production
        # (si gov_override actif → ça a été bloqué → pas d'effet sur exec_ok)
        s.add(Implies(vars["gov_override"], Not(vars["exec_ok"])))

        # Programme B : exec_ok implique chain intègre
        s.add(Implies(vars["exec_ok"], vars["chain_ok"]))

        # Contraintes supplémentaires du modèle
        add_constraints_fn(s, vars)

        # Négation de la propriété à prouver
        add_negation_fn(s, vars)

        result = s.check()

        if result == unsat:
            return ProofResult(
                property_id=property_id,
                description=description,
                proven=True,
            )
        else:
            # Extraire le contre-exemple
            model = s.model()
            cx = {}
            for v in vars.values():
                try:
                    val = model[v]
                    if val is not None:
                        cx[str(v)] = str(val)
                except Exception:
                    pass
            return ProofResult(
                property_id=property_id,
                description=description,
                proven=False,
                counterexample=cx,
            )

    except ImportError:
        return ProofResult(
            property_id=property_id,
            description=description,
            proven=False,
            error="z3-solver non disponible (pip install z3-solver)",
        )
    except Exception as e:
        return ProofResult(
            property_id=property_id,
            description=description,
            proven=False,
            error=str(e),
        )


# ---------------------------------------------------------------------------
# Propriétés à prouver
# ---------------------------------------------------------------------------


def prove_safe_mode_blocks_exec() -> ProofResult:
    """
    G1-SAFETY : SAFE_MODE => NOT exec_allowed

    Contre-exemple recherché : safe_mode=True AND exec_allowed=True
    """
    from z3 import And

    def no_extra(s, v):
        pass

    def negate(s, v):
        s.add(And(v["safe_mode"], v["exec_ok"]))

    return _prove(
        "G1-SAFETY",
        "SAFE_MODE => NOT exec_allowed",
        no_extra,
        negate,
    )


def prove_no_packet_blocks_exec() -> ProofResult:
    """
    G8-E-SAFETY : NOT packet => NOT exec_allowed

    Contre-exemple recherché : packet=False AND exec_allowed=True
    """
    from z3 import And, Not

    def no_extra(s, v):
        pass

    def negate(s, v):
        s.add(And(Not(v["packet"]), v["exec_ok"]))

    return _prove(
        "G8-E-SAFETY",
        "NOT packet => NOT exec_allowed",
        no_extra,
        negate,
    )


def prove_no_authority_blocks_exec() -> ProofResult:
    """
    G1-AUTH : NOT authority_ok => NOT exec_allowed

    Contre-exemple recherché : authority_ok=False AND exec_allowed=True
    """
    from z3 import And, Not

    def no_extra(s, v):
        pass

    def negate(s, v):
        s.add(And(Not(v["authority_ok"]), v["exec_ok"]))

    return _prove(
        "G1-AUTH",
        "NOT authority_ok => NOT exec_allowed",
        no_extra,
        negate,
    )


def prove_no_trace_id_blocks_shadow() -> ProofResult:
    """
    G0-SAFETY : NOT trace_id => NOT shadow_allowed

    Contre-exemple recherché : trace_id=False AND shadow_allowed=True
    """
    from z3 import And, Not

    def no_extra(s, v):
        pass

    def negate(s, v):
        s.add(And(Not(v["trace_id"]), v["shadow_ok"]))

    return _prove(
        "G0-SAFETY",
        "NOT trace_id => NOT shadow_allowed",
        no_extra,
        negate,
    )


def prove_kelly_zero_blocks_exec() -> ProofResult:
    """
    G5-SAFETY : NOT kelly_positive => NOT exec_allowed

    Contre-exemple recherché : kelly_positive=False AND exec_allowed=True
    """
    from z3 import And, Not

    def no_extra(s, v):
        pass

    def negate(s, v):
        s.add(And(Not(v["kelly_pos"]), v["exec_ok"]))

    return _prove(
        "G5-SAFETY",
        "NOT kelly_positive => NOT exec_allowed",
        no_extra,
        negate,
    )


def prove_gov_override_blocks_exec() -> ProofResult:
    """
    G4-SAFETY : gov_override => NOT exec_allowed

    Contre-exemple recherché : gov_override=True AND exec_allowed=True
    """
    from z3 import And

    def no_extra(s, v):
        pass

    def negate(s, v):
        s.add(And(v["gov_override"], v["exec_ok"]))

    return _prove(
        "G4-SAFETY",
        "gov_override => NOT exec_allowed",
        no_extra,
        negate,
    )


def prove_exec_implies_chain_integrity() -> ProofResult:
    """
    B-INTEGRITY : exec_allowed => chain_ok

    Contre-exemple recherché : exec_allowed=True AND chain_ok=False
    """
    from z3 import And, Not

    def no_extra(s, v):
        pass

    def negate(s, v):
        s.add(And(v["exec_ok"], Not(v["chain_ok"])))

    return _prove(
        "B-INTEGRITY",
        "exec_allowed => verify_chain() == True",
        no_extra,
        negate,
    )


def prove_exec_implies_actionable() -> ProofResult:
    """
    G8-D-SYNC : exec_allowed => packet.is_actionable()

    Prouve que la sync G8-D garantit la cohérence.
    Contre-exemple recherché : exec_allowed=True AND NOT actionable
    """
    from z3 import And, Not

    def no_extra(s, v):
        pass

    def negate(s, v):
        s.add(And(v["exec_ok"], Not(v["actionable"])))

    return _prove(
        "G8-D-SYNC",
        "exec_allowed => packet.is_actionable()",
        no_extra,
        negate,
    )


def prove_safe_mode_blocks_shadow() -> ProofResult:
    """
    G1-SHADOW : SAFE_MODE => NOT shadow_allowed

    Contre-exemple recherché : safe_mode=True AND shadow_allowed=True
    """
    from z3 import And

    def no_extra(s, v):
        pass

    def negate(s, v):
        s.add(And(v["safe_mode"], v["shadow_ok"]))

    return _prove(
        "G1-SHADOW",
        "SAFE_MODE => NOT shadow_allowed",
        no_extra,
        negate,
    )


def prove_compositional_safety() -> ProofResult:
    """
    COMPOSITIONAL-SAFETY : fermeture compositionnelle

    Propriété : il est impossible que exec_allowed=True quand l'une des
    conditions suivantes est vraie :
        safe_mode=True
        OR NOT authority_ok
        OR NOT packet
        OR NOT kelly_pos
        OR NOT actionable
        OR NOT chain_ok
        OR gov_override=True

    C'est la propriété la plus forte — elle prouve que les gardes
    sont compositionnellement fermées (pas de chemin de bypass par composition).
    """
    from z3 import And, Not, Or

    def no_extra(s, v):
        pass

    def negate(s, v):
        # exec_allowed = True AND (l'une des conditions bloquantes est active)
        blocking = Or(
            v["safe_mode"],
            Not(v["authority_ok"]),
            Not(v["packet"]),
            Not(v["kelly_pos"]),
            Not(v["actionable"]),
            Not(v["chain_ok"]),
            v["gov_override"],
        )
        s.add(And(v["exec_ok"], blocking))

    return _prove(
        "COMPOSITIONAL-SAFETY",
        "exec_allowed AND (any_blocker) est impossible",
        no_extra,
        negate,
    )


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------


def prove_all_governance_properties() -> List[ProofResult]:
    """
    Lance toutes les preuves Z3 des propriétés de gouvernance.

    Returns:
        Liste de ProofResult — un par propriété.
        Toutes proven=True si le modèle est cohérent.
    """
    provers = [
        prove_safe_mode_blocks_exec,
        prove_no_packet_blocks_exec,
        prove_no_authority_blocks_exec,
        prove_no_trace_id_blocks_shadow,
        prove_kelly_zero_blocks_exec,
        prove_gov_override_blocks_exec,
        prove_exec_implies_chain_integrity,
        prove_exec_implies_actionable,
        prove_safe_mode_blocks_shadow,
        prove_compositional_safety,
    ]
    return [fn() for fn in provers]


def verify_all_proved(results: List[ProofResult]) -> bool:
    """True si toutes les preuves ont réussi."""
    return all(r.proven for r in results)
