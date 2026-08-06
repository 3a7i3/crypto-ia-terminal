"""Narrateur — coeur pur : classification, plafond, agregat.

Contrat : docs/CONTRAT_SUPERVISEUR.md. Les quatre proprietes du § 6 sont
verrouillees ici.
"""

from __future__ import annotations

import pathlib

import pytest

from observability.narrator.budget import Budget
from observability.narrator.digest import Agregat
from observability.narrator.events import (
    DIRECT,
    IGNORE,
    ROUTINE,
    TOUS_LES_TYPES,
    classify,
)

# 2026-08-06 01:00:00 UTC
TS = 1786064400.0


def _ev(type_, **kw):
    base = {
        "ts": TS,
        "decision_type": type_,
        "symbol": "ETH/USDT",
        "signal": "BUY",
        "score": 62,
        "reason": "seuil de regime non franchi",
    }
    base.update(kw)
    return base


# ── Propriete 1 : aucun import du moteur de decision ─────────────────────────


class TestLeNarrateurEstDecouple:
    """Contrat § 6-1. Verifiable statiquement, donc verifie statiquement."""

    INTERDITS = ("core.advisor_loop", "from core", "import core", "advisor_loop")

    def test_aucun_import_du_moteur(self):
        paquet = pathlib.Path("observability/narrator")
        fautes = []
        for fichier in paquet.glob("*.py"):
            source = fichier.read_text(encoding="utf-8")
            for ligne in source.splitlines():
                nue = ligne.strip()
                if not (nue.startswith("import ") or nue.startswith("from ")):
                    continue
                if any(mot in nue for mot in self.INTERDITS):
                    fautes.append(f"{fichier.name}: {nue}")
        assert not fautes, f"le narrateur doit rester passif : {fautes}"

    def test_les_types_suivent_la_boite_noire(self):
        """Un type ajoute au moteur ne doit pas passer inapercu ici."""
        from quant_hedge_ai.agents.intelligence.black_box import DecisionType

        assert {d.value for d in DecisionType} == set(TOUS_LES_TYPES)


# ── Classification ───────────────────────────────────────────────────────────


class TestCeQuiAppartientAUnAutreCanal:
    """Une donnee n'a qu'un seul canal proprietaire."""

    @pytest.mark.parametrize(
        "type_,proprietaire",
        [
            ("TRADE_EXECUTED", "PaperArena"),
            ("POSITION_CLOSED", "PaperArena"),
            ("REGIME_CHANGE", "QuantCrypto"),
        ],
    )
    def test_jamais_relaye(self, type_, proprietaire):
        n = classify(_ev(type_))

        assert n.registre == IGNORE
        assert proprietaire in n.motif_ignore
        assert n.texte == ""


class TestCeQuiChangeUnEtatPartTOutDeSuite:
    def test_arret_est_direct_et_urgent(self):
        n = classify(_ev("HALT_TRIGGERED", reason="drawdown session"))

        assert n.registre == DIRECT
        assert n.urgent is True
        assert "ARRET" in n.texte

    def test_safe_mode_est_urgent(self):
        assert classify(_ev("SAFE_MODE")).urgent is True

    def test_vigilance_grave_est_urgente(self):
        n = classify(_ev("AWARENESS_ALERT", awareness_level="CRITICAL"))

        assert n.registre == DIRECT and n.urgent is True

    def test_vigilance_ordinaire_ne_reveille_pas(self):
        n = classify(_ev("AWARENESS_ALERT", awareness_level="OK"))

        assert n.registre == DIRECT and n.urgent is False

    @pytest.mark.parametrize("type_", ["SYSTEM_EVENT", "RULE_TRIGGERED"])
    def test_evenements_de_machine_sont_directs(self, type_):
        assert classify(_ev(type_)).registre == DIRECT


class TestLaRoutineNeSortJamaisALUnite:
    def test_hold_est_routine(self):
        n = classify(_ev("HOLD"))

        assert n.registre == ROUTINE
        assert n.texte == ""

    def test_un_type_inconnu_ne_devient_pas_une_alerte(self):
        n = classify(_ev("UN_TYPE_QUI_NEXISTE_PAS"))

        assert n.registre == ROUTINE
        assert n.urgent is False

    def test_premier_blocage_du_jour_est_raconte(self):
        n = classify(_ev("TRADE_REFUSED", refused_by=["risk_gate"]))

        assert n.registre == DIRECT
        assert "PREMIER BLOCAGE DU JOUR" in n.texte
        assert "risk_gate" in n.texte

    def test_les_suivants_partent_dans_l_agregat(self):
        premier = classify(_ev("TRADE_REFUSED", refused_by=["risk_gate"]))
        second = classify(
            _ev("TRADE_REFUSED", refused_by=["risk_gate"]), deja_vu=premier.cles
        )

        assert second.registre == ROUTINE
        assert second.cles == premier.cles

    def test_une_autre_couche_est_un_autre_premier_blocage(self):
        a = classify(_ev("TRADE_REFUSED", refused_by=["risk_gate"]))
        b = classify(_ev("TRADE_REFUSED", refused_by=["portfolio_brain"]))

        assert a.cles != b.cles
        assert (
            classify(
                _ev("TRADE_REFUSED", refused_by=["portfolio_brain"]), deja_vu=a.cles
            ).registre
            == DIRECT
        )


class TestUneCoucheNeSAnnonceQuUneFoisParJour:
    """Regression 2026-08-06, trouvee en service reel.

    Apres « gate » seule puis « meta » seule, un refus cumulant les deux se
    presentait en TROISIEME « premier blocage du jour » — un message qui
    n'apprenait rien. La cle portait sur la COMBINAISON de couches ; elle
    porte desormais sur chaque couche.
    """

    def test_une_combinaison_deja_vue_ne_se_raconte_pas(self):
        vues = set()
        for couches in (["gate"], ["meta"]):
            vues.update(classify(_ev("TRADE_REFUSED", refused_by=couches)).cles)

        cumul = classify(
            _ev("TRADE_REFUSED", refused_by=["gate", "meta"]), deja_vu=vues
        )

        assert cumul.registre == ROUTINE

    def test_seule_la_couche_nouvelle_est_annoncee(self):
        vues = set(classify(_ev("TRADE_REFUSED", refused_by=["gate"])).cles)

        cumul = classify(
            _ev("TRADE_REFUSED", refused_by=["gate", "conviction"]), deja_vu=vues
        )

        assert cumul.registre == DIRECT
        titre = cumul.texte.splitlines()[0]
        assert "conviction" in titre
        assert "gate" not in titre, "gate a deja ete annoncee, elle n'est plus nouvelle"

    def test_le_detail_complet_reste_dans_le_corps(self):
        vues = set(classify(_ev("TRADE_REFUSED", refused_by=["gate"])).cles)

        cumul = classify(
            _ev(
                "TRADE_REFUSED",
                refused_by=["gate", "conviction"],
                reason="Refus: gate + conviction",
            ),
            deja_vu=vues,
        )

        assert "gate" in cumul.texte, "le motif complet ne doit rien perdre"

    def test_un_cumul_entierement_neuf_annonce_les_deux(self):
        n = classify(_ev("TRADE_REFUSED", refused_by=["gate", "meta"]))

        assert n.registre == DIRECT
        titre = n.texte.splitlines()[0]
        assert "gate" in titre and "meta" in titre
        assert len(n.cles) == 2

    @pytest.mark.parametrize(
        "brut,attendu",
        [
            ("gate: signal_score (57<66)", "gate"),
            ("gate: signal_score (62<72)", "gate"),
            ("meta: Signal BUY non autorisé en mode defensive_short", "meta"),
            ("portfolio_brain", "portfolio_brain"),
            ("conviction (low)", "conviction"),
            ("", "couche non precisee"),
        ],
    )
    def test_la_couche_perd_ses_parametres(self, brut, attendu):
        """Mesure 2026-08-06 : refused_by porte les VALEURS de seuil.

        Deduplique tel quel, chaque valeur devenait un « premier blocage du
        jour » distinct — 46 messages en 1 h 30, soit ~700/jour contre 20-50
        vises. Le contrat etait respecte a la lettre, viole en pratique.
        """
        from observability.narrator.events import couche_normalisee

        assert couche_normalisee(brut) == attendu

    def test_un_blocage_sans_couche_identifiee_ne_se_raconte_pas(self):
        """Mesure 2026-08-06 : 68 refus sur 861 arrivent sans `refused_by`,
        motif « HOLD — pas de signal ». Annoncer un premier blocage sans
        savoir quelle couche a bloque n'apprend rien.
        """
        n = classify(_ev("TRADE_REFUSED", refused_by=[], reason="HOLD — pas de signal"))

        assert n.registre == ROUTINE
        assert n.texte == ""

    def test_il_reste_compte_dans_l_agregat(self):
        a = Agregat()
        a.observer(_ev("TRADE_REFUSED", refused_by=[]))

        out = a.rendre()

        assert "Blocages : 1" in out
        assert "couche non precisee" in out

    def test_deux_valeurs_de_seuil_sont_le_meme_blocage(self):
        a = classify(_ev("TRADE_REFUSED", refused_by=["gate: signal_score (57<66)"]))
        b = classify(
            _ev("TRADE_REFUSED", refused_by=["gate: signal_score (64<72)"]),
            deja_vu=a.cles,
        )

        assert a.cles == b.cles
        assert b.registre == ROUTINE

    def test_la_cle_change_de_jour(self):
        veille = classify(_ev("TRADE_REFUSED", ts=TS - 86400, refused_by=["risk_gate"]))
        aujourdhui = classify(_ev("TRADE_REFUSED", refused_by=["risk_gate"]))

        assert veille.cles != aujourdhui.cles


# ── Propriete 4 : une donnee absente n'est jamais un zero ────────────────────


class TestUneDonneeAbsenteDisparait:
    def test_pas_de_motif_invente(self):
        n = classify(_ev("HALT_TRIGGERED", reason=""))

        assert "Motif" not in n.texte

    def test_pas_de_placeholder_unknown(self):
        n = classify(_ev("SYSTEM_EVENT", reason="unknown"))

        assert "unknown" not in n.texte

    def test_score_absent_n_est_pas_rendu_comme_zero(self):
        ev = _ev("TRADE_REFUSED", refused_by=["risk_gate"])
        del ev["score"]

        assert "score" not in classify(ev).texte


# ── Propriete 2 : plafond avec fusion annoncee ───────────────────────────────


class TestLePlafondNePerdRien:
    def test_six_passent_le_septieme_est_differe(self):
        b = Budget(max_par_heure=6)

        passes = [b.offrir(f"msg {i}", TS) for i in range(6)]
        septieme = b.offrir("msg 7", TS)

        assert all(p is not None for p in passes)
        assert septieme is None
        assert b.differes == 1

    def test_un_urgent_passe_toujours(self):
        b = Budget(max_par_heure=1)
        b.offrir("routine", TS)

        urgent = b.offrir("ARRET", TS, urgent=True)

        assert urgent is not None and urgent.urgent is True
        assert b.differes == 0, "une alerte de securite ne se met jamais en file"

    def test_la_fusion_est_annoncee_avec_son_compte(self):
        b = Budget(max_par_heure=1)
        b.offrir("passe", TS)
        for i in range(3):
            b.offrir(f"differe {i}", TS)

        texte = b.vider()

        assert "+3 evenement(s) groupe(s)" in texte
        assert "differe 0" in texte

    def test_rien_a_annoncer_ne_produit_rien(self):
        assert Budget().vider() == ""

    def test_vider_remet_le_compteur_a_zero(self):
        b = Budget(max_par_heure=0)
        b.offrir("x", TS)
        b.vider()

        assert b.differes == 0
        assert b.vider() == ""

    def test_la_fenetre_glissante_libere_des_places(self):
        b = Budget(max_par_heure=2, fenetre_s=3600)
        b.offrir("a", TS)
        b.offrir("b", TS)

        assert b.offrir("c", TS) is None
        assert b.offrir("d", TS + 3601) is not None


# ── Agregat ──────────────────────────────────────────────────────────────────


class TestAgregat:
    def test_un_silence_reel_ne_produit_pas_de_message(self):
        assert Agregat().rendre() == ""

    def test_compte_les_blocages_par_couche(self):
        a = Agregat()
        for _ in range(3):
            a.observer(_ev("TRADE_REFUSED", refused_by=["risk_gate"]))
        a.observer(_ev("TRADE_REFUSED", refused_by=["portfolio_brain"]))
        a.observer(_ev("HOLD"))

        out = a.rendre()

        assert "5 decision(s) observee(s)" in out
        assert "Blocages : 4" in out
        assert "risk_gate  3" in out
        assert "Sans signal exploitable : 1" in out

    def test_aucune_metrique_appartenant_a_un_autre_canal(self):
        """L'agregat ne PRODUIT aucune metrique dont un autre canal est
        proprietaire : ni equity ou PnL (②), ni score ou univers (④), ni
        seuil effectif ou oscillation (⑤).

        Le test porte sur ce que l'agregat FABRIQUE, pas sur les mots que
        peut contenir un motif de refus recopie tel quel : « seuil de regime
        non franchi » est un motif legitime, et le relayer est precisement le
        territoire du Narrateur.
        """
        a = Agregat()
        a.observer(_ev("TRADE_REFUSED", refused_by=["risk_gate"], reason="volume bas"))
        a.observer(_ev("HOLD"))

        out = a.rendre().lower()

        for interdit in ("equity", "pnl", "usd", "avg_thr", "oscill", "sharpe", "%"):
            assert interdit not in out, f"metrique d'un autre canal : {interdit}"

    def test_le_motif_complet_reste_dans_le_message_direct(self):
        """Le motif EST le territoire du Narrateur — mais a l'unite.

        Le compter sur une periode fabriquerait une statistique de seuil
        effectif, propriete du canal ⑤.
        """
        n = classify(
            _ev(
                "TRADE_REFUSED",
                refused_by=["gate: signal_score (62<66)"],
                reason="Refus: gate: signal_score (62<66)",
            )
        )

        assert "62<66" in n.texte

        a = Agregat()
        a.observer(_ev("TRADE_REFUSED", refused_by=["gate: signal_score (62<66)"]))

        assert "62<66" not in a.rendre()

    def test_les_differes_sont_repris_dans_l_agregat(self):
        a = Agregat()
        a.observer(_ev("HOLD"))

        out = a.rendre(differes="+2 evenement(s) groupe(s) :\n  · x")

        assert "+2 evenement(s) groupe(s)" in out

    def test_les_differes_seuls_suffisent_a_emettre(self):
        assert "+1" in Agregat().rendre(differes="+1 evenement(s) groupe(s) :")

    def test_rendre_remet_les_compteurs_a_zero(self):
        a = Agregat()
        a.observer(_ev("HOLD"))
        a.rendre()

        assert a.vide and a.rendre() == ""
