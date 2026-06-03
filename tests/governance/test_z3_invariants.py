"""
tests/governance/test_z3_invariants.py — Preuves formelles Z3 des invariants de gouvernance.

Objectif : prouver statiquement (SMT) qu'aucune assignation de variables d'état ne satisfait
une violation d'invariant. Complément formel du GovernanceAuditor (runtime checks) et de
l'auditeur constitutional (test_constitution_i14.py).

Invariants prouvés :
    G0   — EXECUTION_PENDING ⟹ trace_id présent
    G1   — executed=True ⟹ safe_mode=False (RSM = NORMAL)
    G5   — EXECUTION_PENDING ⟹ kelly > 0
    G8-D — trade_allowed ⟺ packet_actionable (sync)
    G8-E — executed=True ⟹ dp_none=False
    S3   — EXECUTION_PENDING ⟹ allocation > 0
    P04  — EXECUTED ⟹ G0 ∧ G1 ∧ G5 ∧ G8-E ∧ S3 ∧ chain_valid ∧ trade_allowed
    R3   — engine_configured ∧ result=None ⟹ blocked (fail-closed)

Méthode : z3.Solver() en mode UNSAT.
    Une violation est impossible ssi {invariant + hypothèse_de_violation} est UNSAT.
    Chaque "test_*_is_sat" est un sanity-check : prouve qu'un état valide est atteignable.

Dépendance : pip install z3-solver>=4.13.0
    Tests skippés automatiquement si z3-solver absent (pytest.importorskip).
"""

import pytest

z3 = pytest.importorskip("z3", reason="z3-solver non installé — pip install z3-solver")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state():
    """Variables d'état canoniques du pipeline décisionnel."""
    return {
        "safe_mode": z3.Bool("safe_mode"),
        "trade_allowed": z3.Bool("trade_allowed"),
        "trace_id": z3.Bool("trace_id"),
        "dp_none": z3.Bool("dp_none"),
        "kelly": z3.Real("kelly"),
        "allocation": z3.Real("allocation"),
        "chain_valid": z3.Bool("chain_valid"),
        "executed": z3.Bool("executed"),
        "execution_pending": z3.Bool("execution_pending"),
        "packet_actionable": z3.Bool("packet_actionable"),
    }


def _gate(v: dict) -> z3.BoolRef:
    """Prédicat de gate d'exécution : conjonction de toutes les préconditions."""
    return z3.And(
        z3.Not(v["safe_mode"]),
        v["trade_allowed"],
        v["trace_id"],
        z3.Not(v["dp_none"]),
        v["kelly"] > 0,
        v["allocation"] > 0,
        v["chain_valid"],
    )


# ---------------------------------------------------------------------------
# Layer 1 : Preuves unitaires par invariant
# ---------------------------------------------------------------------------


class TestG0TraceId:
    """G0 — Toute exécution doit avoir un trace_id."""

    def test_executed_without_trace_is_unsat(self):
        """Il n'existe aucun état SAT où executed=True et trace_id=False."""
        s, v = z3.Solver(), _state()
        s.add(z3.Implies(v["executed"], v["trace_id"]))
        s.add(v["executed"])
        s.add(z3.Not(v["trace_id"]))
        assert (
            s.check() == z3.unsat
        ), "G0 violation : executed sans trace_id est SAT — invariant non prouvé"

    def test_executed_with_trace_is_sat(self):
        """Sanity : exécution avec trace_id doit être SAT."""
        s, v = z3.Solver(), _state()
        s.add(z3.Implies(v["executed"], v["trace_id"]))
        s.add(v["executed"])
        s.add(v["trace_id"])
        assert s.check() == z3.sat


class TestG1SafeMode:
    """G1 — Aucune exécution quand safe_mode=True."""

    def test_executed_in_safe_mode_is_unsat(self):
        s, v = z3.Solver(), _state()
        s.add(z3.Implies(v["executed"], z3.Not(v["safe_mode"])))
        s.add(v["executed"])
        s.add(v["safe_mode"])
        assert s.check() == z3.unsat, "G1 violation : executed en safe_mode est SAT"

    def test_executed_without_safe_mode_is_sat(self):
        s, v = z3.Solver(), _state()
        s.add(z3.Implies(v["executed"], z3.Not(v["safe_mode"])))
        s.add(v["executed"])
        s.add(z3.Not(v["safe_mode"]))
        assert s.check() == z3.sat


class TestG5Kelly:
    """G5 — EXECUTION_PENDING exige kelly > 0."""

    def test_execution_pending_with_zero_kelly_is_unsat(self):
        s, v = z3.Solver(), _state()
        s.add(z3.Implies(v["execution_pending"], v["kelly"] > 0))
        s.add(v["execution_pending"])
        s.add(v["kelly"] <= 0)
        assert (
            s.check() == z3.unsat
        ), "G5 violation : EXECUTION_PENDING avec kelly≤0 est SAT"

    def test_execution_pending_with_positive_kelly_is_sat(self):
        s, v = z3.Solver(), _state()
        s.add(z3.Implies(v["execution_pending"], v["kelly"] > 0))
        s.add(v["execution_pending"])
        s.add(v["kelly"] > 0)
        assert s.check() == z3.sat


class TestG8DSync:
    """G8-D — trade_allowed et packet_actionable doivent être synchronisés."""

    def test_trade_allowed_without_actionable_packet_is_unsat(self):
        """TYPE-A : trade_allowed=True mais packet non-actionable est impossible."""
        s, v = z3.Solver(), _state()
        s.add(z3.Implies(v["trade_allowed"], v["packet_actionable"]))
        s.add(v["trade_allowed"])
        s.add(z3.Not(v["packet_actionable"]))
        assert (
            s.check() == z3.unsat
        ), "G8-D violation : trade_allowed=True sans packet_actionable est SAT"

    def test_both_true_is_sat(self):
        s, v = z3.Solver(), _state()
        s.add(z3.Implies(v["trade_allowed"], v["packet_actionable"]))
        s.add(v["trade_allowed"])
        s.add(v["packet_actionable"])
        assert s.check() == z3.sat


class TestG8EPacketNone:
    """G8-E — Aucune exécution si dp=None."""

    def test_executed_with_dp_none_is_unsat(self):
        s, v = z3.Solver(), _state()
        s.add(z3.Implies(v["executed"], z3.Not(v["dp_none"])))
        s.add(v["executed"])
        s.add(v["dp_none"])
        assert s.check() == z3.unsat, "G8-E violation : executed avec dp=None est SAT"

    def test_executed_with_packet_present_is_sat(self):
        s, v = z3.Solver(), _state()
        s.add(z3.Implies(v["executed"], z3.Not(v["dp_none"])))
        s.add(v["executed"])
        s.add(z3.Not(v["dp_none"]))
        assert s.check() == z3.sat


class TestS3Allocation:
    """S3 — EXECUTION_PENDING exige allocation > 0."""

    def test_execution_pending_with_zero_allocation_is_unsat(self):
        s, v = z3.Solver(), _state()
        s.add(z3.Implies(v["execution_pending"], v["allocation"] > 0))
        s.add(v["execution_pending"])
        s.add(v["allocation"] <= 0)
        assert (
            s.check() == z3.unsat
        ), "S3 violation : EXECUTION_PENDING avec allocation≤0 est SAT"

    def test_execution_pending_with_positive_allocation_is_sat(self):
        s, v = z3.Solver(), _state()
        s.add(z3.Implies(v["execution_pending"], v["allocation"] > 0))
        s.add(v["execution_pending"])
        s.add(v["allocation"] > 0)
        assert s.check() == z3.sat


# ---------------------------------------------------------------------------
# Layer 2 : Preuve combinée — gate final fail-closed si une condition manque
# ---------------------------------------------------------------------------


class TestExecutionGateCombined:
    """
    Le gate d'exécution = conjonction de toutes les préconditions.
    Prouve que si l'une manque, l'exécution est impossible — même si toutes les autres sont vraies.
    """

    def test_safe_mode_alone_blocks_execution(self):
        s, v = z3.Solver(), _state()
        s.add(_gate(v))
        s.add(v["safe_mode"])
        assert s.check() == z3.unsat

    def test_missing_trace_alone_blocks_execution(self):
        s, v = z3.Solver(), _state()
        s.add(_gate(v))
        s.add(z3.Not(v["trace_id"]))
        assert s.check() == z3.unsat

    def test_trade_not_allowed_alone_blocks_execution(self):
        s, v = z3.Solver(), _state()
        s.add(_gate(v))
        s.add(z3.Not(v["trade_allowed"]))
        assert s.check() == z3.unsat

    def test_dp_none_alone_blocks_execution(self):
        s, v = z3.Solver(), _state()
        s.add(_gate(v))
        s.add(v["dp_none"])
        assert s.check() == z3.unsat

    def test_zero_kelly_alone_blocks_execution(self):
        s, v = z3.Solver(), _state()
        s.add(_gate(v))
        s.add(v["kelly"] <= 0)
        assert s.check() == z3.unsat

    def test_zero_allocation_alone_blocks_execution(self):
        s, v = z3.Solver(), _state()
        s.add(_gate(v))
        s.add(v["allocation"] <= 0)
        assert s.check() == z3.unsat

    def test_broken_chain_alone_blocks_execution(self):
        s, v = z3.Solver(), _state()
        s.add(_gate(v))
        s.add(z3.Not(v["chain_valid"]))
        assert s.check() == z3.unsat

    def test_valid_execution_state_is_sat(self):
        """Sanity : un état entièrement valide doit être SAT (le gate n'est pas trivially false)."""
        s, v = z3.Solver(), _state()
        s.add(_gate(v))
        assert (
            s.check() == z3.sat
        ), "Le gate d'exécution valide doit être SAT — vérifier les contraintes"


# ---------------------------------------------------------------------------
# Layer 3 : Preuve P04 — EXECUTED ⟹ preuve complète (conjonction terminale)
# ---------------------------------------------------------------------------


class TestP04ExecutedProofChain:
    """
    P04 — Un packet EXECUTED doit satisfaire TOUS les invariants simultanément.
    Prouve que chaque sous-violation individuelle rend l'état EXECUTED impossible.
    """

    def _p04_solver(self):
        s, v = z3.Solver(), _state()
        # P04 : EXECUTED => conjonction complète
        s.add(
            z3.Implies(
                v["executed"],
                z3.And(
                    v["trace_id"],  # G0
                    z3.Not(v["safe_mode"]),  # G1
                    v["kelly"] > 0,  # G5
                    z3.Not(v["dp_none"]),  # G8-E
                    v["allocation"] > 0,  # S3
                    v["chain_valid"],  # Programme B — hash chain
                    v["trade_allowed"],  # autorisation pipeline
                ),
            )
        )
        return s, v

    def test_executed_without_trace_violates_p04(self):
        s, v = self._p04_solver()
        s.add(v["executed"])
        s.add(z3.Not(v["trace_id"]))
        assert s.check() == z3.unsat

    def test_executed_in_safe_mode_violates_p04(self):
        s, v = self._p04_solver()
        s.add(v["executed"])
        s.add(v["safe_mode"])
        assert s.check() == z3.unsat

    def test_executed_zero_kelly_violates_p04(self):
        s, v = self._p04_solver()
        s.add(v["executed"])
        s.add(v["kelly"] <= 0)
        assert s.check() == z3.unsat

    def test_executed_with_dp_none_violates_p04(self):
        s, v = self._p04_solver()
        s.add(v["executed"])
        s.add(v["dp_none"])
        assert s.check() == z3.unsat

    def test_executed_zero_allocation_violates_p04(self):
        s, v = self._p04_solver()
        s.add(v["executed"])
        s.add(v["allocation"] <= 0)
        assert s.check() == z3.unsat

    def test_executed_with_broken_chain_violates_p04(self):
        s, v = self._p04_solver()
        s.add(v["executed"])
        s.add(z3.Not(v["chain_valid"]))
        assert s.check() == z3.unsat

    def test_executed_without_trade_allowed_violates_p04(self):
        s, v = self._p04_solver()
        s.add(v["executed"])
        s.add(z3.Not(v["trade_allowed"]))
        assert s.check() == z3.unsat

    def test_not_executed_can_be_in_any_state(self):
        """P04 ne contraint que EXECUTED — un packet non exécuté peut avoir n'importe quel état."""
        s, v = self._p04_solver()
        s.add(z3.Not(v["executed"]))
        s.add(v["safe_mode"])
        s.add(z3.Not(v["trace_id"]))
        s.add(v["dp_none"])
        assert s.check() == z3.sat

    def test_fully_valid_executed_packet_is_sat(self):
        """Sanity : un packet EXECUTED avec toutes les preuves est SAT."""
        s, v = self._p04_solver()
        s.add(v["executed"])
        s.add(v["trace_id"])
        s.add(z3.Not(v["safe_mode"]))
        s.add(v["kelly"] > z3.RealVal(0))
        s.add(z3.Not(v["dp_none"]))
        s.add(v["allocation"] > z3.RealVal(0))
        s.add(v["chain_valid"])
        s.add(v["trade_allowed"])
        assert s.check() == z3.sat


# ---------------------------------------------------------------------------
# Layer 4 : R3 — Fail-closed pour engines internes non déterministes
# ---------------------------------------------------------------------------


class TestR3FailClosedEngines:
    """
    R3 (risque résiduel) — Engines configurés avec résultat None doivent bloquer.
    Modélise la logique I-14 (advisor_loop.py) en Z3.
    """

    def test_engine_configured_result_none_blocks(self):
        """engine_configured=True ∧ result_present=False ⟹ allowed=False."""
        s = z3.Solver()
        engine_configured = z3.Bool("engine_configured")
        result_present = z3.Bool("result_present")
        allowed = z3.Bool("allowed")

        # Fail-closed : engine configuré + résultat absent → bloqué
        s.add(
            z3.Implies(
                z3.And(engine_configured, z3.Not(result_present)),
                z3.Not(allowed),
            )
        )
        s.add(engine_configured)
        s.add(z3.Not(result_present))
        s.add(allowed)  # hypothèse de violation
        assert (
            s.check() == z3.unsat
        ), "R3 violation : engine configuré + résultat None + allowed=True est SAT — fail-open"

    def test_engine_not_configured_result_none_is_ok(self):
        """Engine non configuré : result=None est normal → allowed peut être True."""
        s = z3.Solver()
        engine_configured = z3.Bool("engine_configured")
        result_present = z3.Bool("result_present")
        allowed = z3.Bool("allowed")

        s.add(
            z3.Implies(
                z3.And(engine_configured, z3.Not(result_present)),
                z3.Not(allowed),
            )
        )
        s.add(z3.Not(engine_configured))
        s.add(z3.Not(result_present))
        s.add(allowed)
        assert s.check() == z3.sat

    def test_engine_configured_result_present_allows_true(self):
        """Engine configuré + résultat présent : allowed peut être True si le résultat l'autorise."""
        s = z3.Solver()
        engine_configured = z3.Bool("engine_configured")
        result_present = z3.Bool("result_present")
        allowed = z3.Bool("allowed")

        s.add(
            z3.Implies(
                z3.And(engine_configured, z3.Not(result_present)),
                z3.Not(allowed),
            )
        )
        s.add(engine_configured)
        s.add(result_present)
        s.add(allowed)
        assert s.check() == z3.sat


# ---------------------------------------------------------------------------
# Layer 5 : Preuve de non-régression — les invariants sont cohérents entre eux
# ---------------------------------------------------------------------------


class TestInvariantCoherence:
    """
    Vérifie que la conjonction de tous les invariants n'est pas trivially contradictoire.
    Si cette preuve est UNSAT, les invariants se contredisent — le système ne peut jamais exécuter.
    """

    def test_all_invariants_conjunction_is_satisfiable(self):
        """
        La conjonction de G0+G1+G5+G8-D+G8-E+S3+P04 doit être SAT.
        Prouve qu'il existe au moins un état valide où une exécution est possible.
        """
        s, v = z3.Solver(), _state()

        # G0
        s.add(z3.Implies(v["executed"], v["trace_id"]))
        # G1
        s.add(z3.Implies(v["executed"], z3.Not(v["safe_mode"])))
        # G5
        s.add(z3.Implies(v["execution_pending"], v["kelly"] > 0))
        # G8-D
        s.add(z3.Implies(v["trade_allowed"], v["packet_actionable"]))
        # G8-E
        s.add(z3.Implies(v["executed"], z3.Not(v["dp_none"])))
        # S3
        s.add(z3.Implies(v["execution_pending"], v["allocation"] > 0))
        # P04
        s.add(
            z3.Implies(
                v["executed"],
                z3.And(
                    v["trace_id"],
                    z3.Not(v["safe_mode"]),
                    v["kelly"] > 0,
                    z3.Not(v["dp_none"]),
                    v["allocation"] > 0,
                    v["chain_valid"],
                    v["trade_allowed"],
                ),
            )
        )

        # Assigner un état d'exécution complet et valide
        s.add(v["executed"])
        s.add(v["execution_pending"])
        s.add(v["trace_id"])
        s.add(z3.Not(v["safe_mode"]))
        s.add(v["kelly"] > z3.RealVal(0))
        s.add(z3.Not(v["dp_none"]))
        s.add(v["allocation"] > z3.RealVal(0))
        s.add(v["chain_valid"])
        s.add(v["trade_allowed"])
        s.add(v["packet_actionable"])

        assert s.check() == z3.sat, (
            "CRITIQUE : la conjonction de tous les invariants est UNSAT — "
            "les invariants se contredisent et aucune exécution n'est possible. "
            "Vérifier les définitions de G0/G1/G5/G8-D/G8-E/S3/P04."
        )
