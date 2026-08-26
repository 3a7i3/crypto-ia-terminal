"""Tests P5-03 — Level A pur : ``evaluate_hard_portfolio_ceiling``.

INV-001 seul. Fonction pure, indépendante de PortfolioBrain.

Portée : ``canonical_n_positions < hard_max``. Rien d'autre. Ni
exposition, ni corrélation, ni hedge, ni levier, ni personality. Les
tests vérifient également l'ISOLATION architecturale : le module Level
A ne doit importer ni ``portfolio_brain`` ni ``meta_strategy_engine``.
"""

from __future__ import annotations

import inspect

import pytest

from paper_trading.admission_policy import evaluate_hard_portfolio_ceiling
from paper_trading.admission_types import (
    AdmissionBlocker,
    AdmissionDecision,
    AdmissionLevel,
    AdmissionVerdict,
)


class TestInv001Boundary:
    """Boundary tests — n < hard_max ⇔ APPROVED."""

    def test_zero_and_one_allowed(self):
        v = evaluate_hard_portfolio_ceiling(0, 1)
        assert v.decision == AdmissionDecision.APPROVED

    def test_at_ceiling_rejected(self):
        v = evaluate_hard_portfolio_ceiling(1, 1)
        assert v.decision == AdmissionDecision.REJECTED

    def test_below_ceiling_allowed(self):
        v = evaluate_hard_portfolio_ceiling(2, 5)
        assert v.decision == AdmissionDecision.APPROVED

    def test_at_ceiling_five_rejected(self):
        v = evaluate_hard_portfolio_ceiling(5, 5)
        assert v.decision == AdmissionDecision.REJECTED

    def test_over_ceiling_rejected(self):
        """Cas OVER_LIMIT_RESTORED : Level A doit refuser sans crasher.

        Note : le blocker retourné reste PORTFOLIO_HARD_CEILING —
        l'événement OVER_LIMIT_RESTORED est produit ailleurs (P5-04),
        Level A ne le devine pas.
        """
        v = evaluate_hard_portfolio_ceiling(3, 2)
        assert v.decision == AdmissionDecision.REJECTED
        assert v.blocker == AdmissionBlocker.PORTFOLIO_HARD_CEILING

    def test_hard_max_zero_always_rejects(self):
        """capital_protection global : personne n'entre."""
        assert (
            evaluate_hard_portfolio_ceiling(0, 0).decision
            == AdmissionDecision.REJECTED
        )
        assert (
            evaluate_hard_portfolio_ceiling(5, 0).decision
            == AdmissionDecision.REJECTED
        )


class TestVerdictShape:
    """Le verdict retourné doit être bien formé — capture propre du TOCTOU."""

    def test_approved_verdict_shape(self):
        v = evaluate_hard_portfolio_ceiling(2, 5)
        assert isinstance(v, AdmissionVerdict)
        assert v.level == AdmissionLevel.A
        assert v.n_at_check == 2
        assert v.hard_max_at_check == 5
        assert v.blocker == AdmissionBlocker.NONE
        assert v.reason == ""
        assert v.checked_by == "evaluate_hard_portfolio_ceiling"

    def test_rejected_verdict_shape(self):
        v = evaluate_hard_portfolio_ceiling(5, 5)
        assert v.level == AdmissionLevel.A
        assert v.n_at_check == 5
        assert v.hard_max_at_check == 5
        assert v.blocker == AdmissionBlocker.PORTFOLIO_HARD_CEILING
        assert "5/5" in v.reason
        assert v.checked_by == "evaluate_hard_portfolio_ceiling"

    def test_verdict_is_immutable(self):
        v = evaluate_hard_portfolio_ceiling(0, 5)
        with pytest.raises(Exception):  # FrozenInstanceError
            v.decision = AdmissionDecision.REJECTED  # type: ignore[misc]


class TestPurity:
    """La fonction doit être PURE — même entrée → même sortie."""

    def test_idempotent(self):
        v1 = evaluate_hard_portfolio_ceiling(2, 5)
        v2 = evaluate_hard_portfolio_ceiling(2, 5)
        # Mêmes valeurs mais instances distinctes (frozen dataclass equality)
        assert v1 == v2

    def test_no_side_effects_on_repeat_call(self):
        for _ in range(100):
            v = evaluate_hard_portfolio_ceiling(3, 5)
            assert v.decision == AdmissionDecision.APPROVED
            assert v.n_at_check == 3

    def test_takes_only_two_positional_args(self):
        """Signature stricte : rien d'autre ne doit se glisser."""
        sig = inspect.signature(evaluate_hard_portfolio_ceiling)
        params = list(sig.parameters.values())
        assert len(params) == 2
        names = [p.name for p in params]
        assert names == ["canonical_n_positions", "hard_max"]


class TestNegativeInputs:
    """Robustesse : entrées négatives doivent échouer bruyamment."""

    def test_negative_n_raises(self):
        with pytest.raises(ValueError, match="canonical_n_positions"):
            evaluate_hard_portfolio_ceiling(-1, 5)

    def test_negative_max_raises(self):
        with pytest.raises(ValueError, match="hard_max"):
            evaluate_hard_portfolio_ceiling(0, -1)


class TestArchitecturalIsolation:
    """Level A ne doit importer ni PortfolioBrain ni MetaStrategyEngine.

    Correction opérateur Phase 5.2 §4 : Level A doit être un invariant
    mécanique, PAS une version partielle cachée de PortfolioBrain. Toute
    dépendance transitive trahirait ce principe.

    On inspecte les IMPORTS AST — pas le texte brut du module. Le
    docstring peut mentionner ``PortfolioBrain`` pour expliquer ce que
    Level A n'est pas, sans casser l'invariant.
    """

    @staticmethod
    def _module_imports() -> set[str]:
        import ast

        import paper_trading.admission_policy as mod

        src = inspect.getsource(mod)
        tree = ast.parse(src)
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    names.add(node.module)
        return names

    def test_no_import_of_portfolio_brain(self):
        imports = self._module_imports()
        forbidden = {i for i in imports if "portfolio_brain" in i}
        assert not forbidden, f"Level A doit ignorer PortfolioBrain: {forbidden}"

    def test_no_import_of_meta_strategy_engine(self):
        imports = self._module_imports()
        forbidden = {i for i in imports if "meta_strategy" in i}
        assert not forbidden, f"Level A doit ignorer MetaStrategy: {forbidden}"

    def test_no_import_of_simulator_or_view(self):
        imports = self._module_imports()
        forbidden = {
            i
            for i in imports
            if any(
                k in i
                for k in ("mexc_simulator", "paper_portfolio_view", "advisor_loop")
            )
        }
        assert not forbidden, (
            f"Level A doit rester amont de la frontière d'écriture: {forbidden}"
        )

    def test_only_admission_types_from_project(self):
        """Seul ``paper_trading.admission_types`` autorisé côté projet."""
        imports = self._module_imports()
        project_imports = {
            i
            for i in imports
            if i.startswith(("paper_trading", "quant_hedge_ai", "core", "observability"))
        }
        assert project_imports == {"paper_trading.admission_types"}, (
            f"imports projet autorisés = {{'paper_trading.admission_types'}}, "
            f"trouvés = {project_imports}"
        )
