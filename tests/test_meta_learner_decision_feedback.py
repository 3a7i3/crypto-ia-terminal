"""
tests/test_meta_learner_decision_feedback.py — S-02B.1 : passivité de MetaLearner.

ADR S-02B.1 : LEARNING != AUTHORITY. MetaLearner peut apprendre et proposer un
exit (tp/sl/trailing) en permanence via `find_best()` ; cette recommandation ne
peut modifier les paramètres réels du trade live (`Position.tp_pct/sl_pct/
trailing_pct`) que si FEATURE_ADAPTIVE_DECISION_FEEDBACK est explicitement
activé. La frontière est implémentée par
`core.advisor_loop.resolve_meta_learner_exit_params()`, appelée depuis
`_build_position_from_execution()` (le seul point de consommation décisionnelle
démontré de MetaLearner dans advisor_loop.py).
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

import core.advisor_loop as advisor_loop
from tracker_system.meta_learner import MetaLearner
from tracker_system.meta_memory import MetaMemory


ML_DECISION = {"exit_type": "hybrid", "tp": 0.05, "sl": 0.025, "trail_pct": 0.01}
PERSONALITY = SimpleNamespace(tp_pct=0.04, sl_pct=0.02, trailing_pct=0.0)


class TestResolveMetaLearnerExitParams:
    """Unité pure — la frontière S-02B.1 elle-même."""

    def test_feedback_false_ignores_recommendation_uses_personality(self):
        tp, sl, trailing, applied = advisor_loop.resolve_meta_learner_exit_params(
            ML_DECISION, PERSONALITY, adaptive_decision_feedback=False
        )
        assert (tp, sl, trailing) == (0.04, 0.02, 0.0)
        assert applied is False

    def test_feedback_true_applies_recommendation_legacy_behavior(self):
        tp, sl, trailing, applied = advisor_loop.resolve_meta_learner_exit_params(
            ML_DECISION, PERSONALITY, adaptive_decision_feedback=True
        )
        assert (tp, sl, trailing) == (0.05, 0.025, 0.01)
        assert applied is True

    def test_default_is_false_when_flag_omitted_by_import(self):
        """Le module importe le flag fail-closed — la frontière n'active rien
        d'elle-même si l'appelant oublie de préciser le flag explicitement."""
        assert advisor_loop.FEATURE_ADAPTIVE_DECISION_FEEDBACK is False

    def test_no_recommendation_uses_personality_regardless_of_flag(self):
        for flag in (False, True):
            tp, sl, trailing, applied = advisor_loop.resolve_meta_learner_exit_params(
                None, PERSONALITY, adaptive_decision_feedback=flag
            )
            assert (tp, sl, trailing) == (0.04, 0.02, 0.0)
            assert applied is False

    def test_no_personality_falls_back_to_hardcoded_defaults(self):
        tp, sl, trailing, applied = advisor_loop.resolve_meta_learner_exit_params(
            None, None, adaptive_decision_feedback=False
        )
        assert (tp, sl, trailing) == (0.04, 0.02, 0.0)
        assert applied is False

    def test_partial_recommendation_only_applied_fields_override(self):
        """tp_pct=0 dans la recommandation → falsy → fallback personnalité
        (comportement legacy `or` inchangé, uniquement pour les champs fournis)."""
        partial = {"exit_type": "tp_sl", "tp": 0.0, "sl": 0.03}
        tp, sl, trailing, applied = advisor_loop.resolve_meta_learner_exit_params(
            partial, PERSONALITY, adaptive_decision_feedback=True
        )
        assert tp == 0.04  # tp=0.0 falsy → fallback personnalité (legacy)
        assert sl == 0.03
        assert trailing == 0.0  # absent de la recommandation → fallback
        assert applied is True


class TestMetaLearnerLearningAlwaysActive:
    """Apprentissage/écriture — jamais gaté par le flag S-02 (§8)."""

    def test_learn_persists_regardless_of_flag(self, tmp_path):
        learner = MetaLearner(memory_path=tmp_path / "meta_memory.json")
        learner.learn(
            {"regime": "bull_trend", "volatility_bucket": "medium"},
            ML_DECISION,
            {"sharpe": 2.0, "win_rate": 0.6, "avg_pnl": 0.01, "n_trades": 20},
        )
        assert len(learner.memory) == 1

    def test_find_best_still_returns_recommendation_in_passive_mode(self, tmp_path):
        """find_best() reste une pure lecture/proposition — jamais gatée elle-même."""
        learner = MetaLearner(memory_path=tmp_path / "meta_memory.json")
        learner.learn(
            {"regime": "bull_trend", "volatility_bucket": "medium"},
            ML_DECISION,
            {"sharpe": 2.0, "win_rate": 0.6, "avg_pnl": 0.01, "n_trades": 20},
        )
        dec = learner.find_best({"regime": "bull_trend", "volatility": 0.015})
        assert dec is not None
        assert dec["tp"] == 0.05


class TestStateProvenance:
    def test_meta_memory_provenance_minimal_fields(self, tmp_path):
        mem = MetaMemory(path=tmp_path / "meta_memory.json")
        mem.add(
            {"regime": "bull_trend", "volatility_bucket": "medium"},
            ML_DECISION,
            {"sharpe": 2.0, "win_rate": 0.6, "avg_pnl": 0.01, "n_trades": 20},
        )
        prov = mem.state_provenance()
        assert prov["subsystem"] == "MetaLearner"
        assert prov["n_entries"] == 1
        assert prov["state_mtime"] is not None
        assert prov["source_path"].endswith("meta_memory.json")

    def test_meta_learner_passthrough_provenance(self, tmp_path):
        learner = MetaLearner(memory_path=tmp_path / "meta_memory.json")
        assert learner.state_provenance()["subsystem"] == "MetaLearner"

    def test_provenance_distinguishes_empty_vs_populated_state(self, tmp_path):
        path = tmp_path / "meta_memory.json"
        empty = MetaMemory(path=path).state_provenance()
        mem = MetaMemory(path=path)
        mem.add(
            {"regime": "range", "volatility_bucket": "low"},
            ML_DECISION,
            {"sharpe": 1.0, "win_rate": 0.5, "avg_pnl": 0.01, "n_trades": 5},
        )
        populated = mem.state_provenance()
        assert empty["n_entries"] != populated["n_entries"]


class TestBuildPositionWiring:
    """Preuve statique que `_build_position_from_execution` consomme bien la
    frontière S-02B.1 (et non plus directement `ml_decision`) — cf. mission
    §20 (diff integrity) : ce test casse si le câblage est modifié sans
    passer par `resolve_meta_learner_exit_params`."""

    def test_build_position_uses_resolve_helper(self):
        source = Path(advisor_loop.__file__).read_text(encoding="utf-8")
        start = source.index("def _build_position_from_execution(")
        end = source.index("def _register_position_from_execution(")
        body = source[start:end]
        assert "resolve_meta_learner_exit_params(" in body
        assert 'tp_pct=_tp_pct' in body
        assert 'sl_pct=_sl_pct' in body
        assert 'trailing=_trailing_pct' in body

    def test_provenance_lookup_is_defensive(self):
        """Régression : un `meta_learner` sans state_provenance() (double de
        test, implémentation partielle) ne doit jamais empêcher la
        construction de la position réelle — cf. correction appliquée après
        échec de test_advisor_loop_smoke.py::test_main_opens_real_position_
        path_and_updates_tracker pendant le développement S-02B.1."""
        source = Path(advisor_loop.__file__).read_text(encoding="utf-8")
        start = source.index("def _build_position_from_execution(")
        end = source.index("def _register_position_from_execution(")
        body = source[start:end]
        prov_idx = body.index("meta_learner.state_provenance()")
        guard = body[max(0, prov_idx - 200) : prov_idx]
        assert "try:" in guard, (
            "meta_learner.state_provenance() doit être appelée sous try/except "
            "— une provenance indisponible ne doit jamais casser la position."
        )
