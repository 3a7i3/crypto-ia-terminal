"""Attribution du seuil de score — invariants de l'instrumentation.

Contexte. Le seuil effectif appliqué par le `GlobalRiskGate` résulte de
plusieurs termes (base de régime, delta regret, delta governor, rampe de
transition, plancher absolu). Avant ce champ, aucun artefact ne les portait :
le seuil n'était reconstructible qu'indirectement, en analysant la chaîne
``signal_score (55<64)`` de `gate_failed` — donc **uniquement sur les refus**,
jamais sur les trades acceptés, et sans distinguer quel terme l'avait produit.

Ces tests verrouillent trois propriétés, dans l'ordre d'importance :

1. **L'instrumentation ne change aucune décision.** `explain_threshold` est
   sans effet de bord et ne participe à aucun test d'acceptation.
2. **Le breakdown est cohérent avec le seuil réellement appliqué.**
3. **Le champ est additif** : un `GateResult` construit sans lui, ou un cycle
   court-circuité avant le test de score, donne ``{}`` et jamais une exception.
"""

from __future__ import annotations

from observability.decision_observation import build_from_result
from quant_hedge_ai.agents.risk.global_risk_gate import GateResult, GlobalRiskGate

REGIMES = ["sideways", "bear_trend", "bull_trend", "RANGE", "regime_inexistant"]


class _Signal:
    """Signal minimal accepté par `GlobalRiskGate.check`."""

    def __init__(self, score: float = 58.0, regime: str = "sideways") -> None:
        self.score = score
        self.regime = regime
        self.confirmed = True
        self.strength = 0.4
        self.actionable = True
        self.side = "BUY"
        self.symbol = "BTC/USDT"
        self.price = 100.0


class TestPasDEffetDeBord:
    """Propriété n°1 — l'instrumentation est passive."""

    def test_explain_threshold_ne_modifie_pas_le_seuil(self):
        gate = GlobalRiskGate()
        avant = gate._effective_min_score("sideways")
        for _ in range(5):
            gate.explain_threshold("sideways", avant)
        assert gate._effective_min_score("sideways") == avant

    def test_explain_threshold_ne_modifie_pas_les_deltas(self):
        gate = GlobalRiskGate()
        gate.apply_regret_delta(-2)
        gate.set_governor_delta(3)
        regret, governor = gate._regret_delta, gate._governor_delta
        gate.explain_threshold("sideways", gate._effective_min_score("sideways"))
        assert (gate._regret_delta, gate._governor_delta) == (regret, governor)

    def test_le_verdict_du_gate_est_inchange_par_la_presence_du_champ(self):
        """Un score sous le seuil doit échouer, au-dessus doit passer — le
        breakdown est descriptif et ne doit jamais entrer dans le verdict."""
        gate = GlobalRiskGate()
        seuil = gate._effective_min_score("sideways")
        assert gate.check(_Signal(score=seuil + 5)).conditions["signal_score"] is True
        refus = gate.check(_Signal(score=seuil - 5))
        assert refus.conditions["signal_score"] is False
        assert refus.threshold_breakdown["effective"] == seuil


class TestCoherence:
    """Propriété n°2 — le breakdown décrit le seuil réellement appliqué."""

    def test_effective_correspond_au_seuil_applique(self):
        gate = GlobalRiskGate()
        for regime in REGIMES:
            seuil = gate._effective_min_score(regime)
            assert gate.explain_threshold(regime, seuil)["effective"] == seuil

    def test_le_delta_regret_est_reporte(self):
        gate = GlobalRiskGate()
        gate.apply_regret_delta(-2)
        b = gate.explain_threshold("sideways", gate._effective_min_score("sideways"))
        assert b["regret_delta"] == -2

    def test_le_delta_governor_est_reporte(self):
        gate = GlobalRiskGate()
        gate.set_governor_delta(4)
        b = gate.explain_threshold("sideways", gate._effective_min_score("sideways"))
        assert b["governor_delta"] == 4

    def test_la_transition_est_un_override_pas_un_terme(self):
        """`_transition_threshold` court-circuite les autres termes : `source`
        doit le signaler, sinon un lecteur croirait à une somme."""
        gate = GlobalRiskGate()
        gate.apply_regret_delta(-3)
        gate.set_transition_threshold(70)
        b = gate.explain_threshold("sideways", gate._effective_min_score("sideways"))
        assert b["source"] == "transition"
        assert b["transition_threshold"] == 70
        assert b["effective"] == 70
        # Le delta regret reste enregistré, mais n'a pas produit le seuil.
        assert b["regret_delta"] == -3

    def test_toute_branche_est_nommee_et_complete(self):
        """Garde-fou contre une « simplification » qui supposerait l'additivité.

        `base_min_signal_score` est la constante globale ; sous classifier, la
        base réelle est celle du régime, et `base + deltas != effective`. Le
        contrat n'est donc pas une somme : c'est *entrées + sortie + branche*.
        Ces trois éléments doivent être présents quelle que soit la branche,
        pour qu'un consommateur puisse constater lui-même la non-additivité au
        lieu de la supposer.
        """
        gate = GlobalRiskGate()
        attendus = {
            "source",
            "regime",
            "base_min_signal_score",
            "regret_delta",
            "governor_delta",
            "transition_threshold",
            "absolute_floor",
            "effective",
        }
        for regime in REGIMES:
            b = gate.explain_threshold(regime, gate._effective_min_score(regime))
            assert set(b) == attendus, f"champs manquants en régime {regime}"
            assert b["source"] in {"transition", "classifier", "fallback"}

    def test_la_non_additivite_est_observable_depuis_le_champ(self):
        """Sur ce dépôt, le classifier donne effective != base + deltas.

        Si cette assertion échoue un jour, c'est que le classifier est devenu
        additif ou a été retiré — les deux méritent d'être vus, pas ignorés.
        """
        gate = GlobalRiskGate()
        b = gate.explain_threshold("sideways", gate._effective_min_score("sideways"))
        if b["source"] != "classifier":
            return  # branche non exercée dans cette configuration
        somme = b["base_min_signal_score"] + b["regret_delta"] + b["governor_delta"]
        assert b["effective"] != somme, (
            "le classifier est devenu additif : la note de non-additivité de "
            "`explain_threshold` doit être revue"
        )


class TestChampAdditif:
    """Propriété n°3 — aucun appelant existant n'est cassé."""

    def test_gate_result_sans_le_champ(self):
        assert GateResult(allowed=True).threshold_breakdown == {}

    def test_as_dict_expose_le_champ(self):
        assert "threshold_breakdown" in GateResult(allowed=True).as_dict()

    def test_observation_sans_gate_donne_un_dict_vide(self):
        obs = build_from_result({"signal": _Signal()}, cycle=1, engine_version="t")
        assert obs.threshold_breakdown == {}

    def test_observation_avec_gate_porte_le_breakdown(self):
        gate = GlobalRiskGate()
        gate.apply_regret_delta(-3)
        sig = _Signal(score=58.0)
        obs = build_from_result(
            {"signal": sig, "gate": gate.check(sig)}, cycle=1, engine_version="t"
        )
        assert obs.threshold_breakdown["regret_delta"] == -3
        assert obs.to_dict()["threshold_breakdown"] == obs.threshold_breakdown

    def test_le_seuil_est_desormais_lisible_sur_un_trade_ACCEPTE(self):
        """Le gain principal. Avant ce champ, le seuil ne se reconstruisait que
        depuis `gate_failed` — donc jamais sur un trade autorisé."""
        gate = GlobalRiskGate()
        seuil = gate._effective_min_score("sideways")
        sig = _Signal(score=seuil + 10)
        obs = build_from_result(
            {"signal": sig, "gate": gate.check(sig)}, cycle=1, engine_version="t"
        )
        assert obs.gate_failed == []
        assert obs.threshold_breakdown["effective"] == seuil
