"""Narrateur — recapitulatif quotidien et comparaison a la veille.

Contrat : docs/CONTRAT_SUPERVISEUR.md § 2.

La propriete centrale : comparer une journee PARTIELLE a une journee complete
fabriquerait une chute imaginaire, produite par l'instrument et non par la
machine. C'est la meme faute que rendre une donnee absente comme un zero.
"""

from __future__ import annotations

from observability.narrator.daily import Quotidien
from observability.narrator.runner import Narrateur

# 2026-08-05 00:00:00 UTC
J1 = 1785888000.0
J2 = J1 + 86400
HEURE = 3600.0


def _ev(type_, ts, **kw):
    base = {
        "ts": ts,
        "decision_type": type_,
        "symbol": "ETH/USDT",
        "signal": "BUY",
        "score": 62,
        "reason": "motif",
    }
    base.update(kw)
    return base


def _journee(q, depart, n_hold, blocages, duree_h=23.0):
    """Repartit des evenements sur une fenetre d'amplitude exactement duree_h.

    Le pas vaut duree/(N-1) et non duree/N : la couverture mesuree est l'ecart
    entre le PREMIER et le DERNIER evenement, pas la somme des intervalles.
    """
    total = n_hold + sum(blocages.values())
    pas = duree_h * HEURE / max(1, total - 1)
    t = depart
    for _ in range(n_hold):
        q.observer(_ev("HOLD", t))
        t += pas
    for couche, n in blocages.items():
        for _ in range(n):
            q.observer(_ev("TRADE_REFUSED", t, refused_by=[couche]))
            t += pas


class TestPremierJour:
    def test_rien_observe_ne_produit_rien(self):
        assert Quotidien().rendre() == ""

    def test_sans_veille_on_le_dit_au_lieu_de_comparer(self):
        q = Quotidien()
        _journee(q, J1, 100, {"gate": 200})

        out = q.rendre()

        assert "Premier recapitulatif" in out
        assert "aucune veille" in out
        assert "(+" not in out and "(-" not in out


class TestComparaisonALaVeille:
    def _deux_jours(self):
        q = Quotidien()
        _journee(q, J1, 100, {"gate": 200, "meta": 50}, duree_h=23.0)
        _journee(q, J2, 80, {"gate": 260, "conviction": 10}, duree_h=23.0)
        return q

    def test_les_ecarts_sont_affiches(self):
        out = self._deux_jours().rendre()

        assert "Decisions" in out
        assert "(+60)" in out, "gate 200 -> 260"
        assert "(-20)" in out, "holds 100 -> 80"

    def test_une_couche_apparue_est_signalee(self):
        out = self._deux_jours().rendre()

        assert "Couches apparues : conviction" in out

    def test_une_couche_disparue_est_signalee(self):
        out = self._deux_jours().rendre()

        assert "Couches disparues : meta" in out

    def test_une_couche_nouvelle_affiche_son_ecart_complet(self):
        """(+10) et non un blanc qui se lirait « pas de donnee »."""
        out = self._deux_jours().rendre()

        ligne = [x for x in out.splitlines() if "conviction" in x and "(" in x]
        assert ligne and "(+10)" in ligne[0]

    def test_la_journee_visee_est_celle_demandee(self):
        q = self._deux_jours()

        assert "2026-08-05" in q.rendre("2026-08-05")
        assert "2026-08-06" in q.rendre("2026-08-06")

    def test_une_journee_inconnue_ne_rend_rien(self):
        assert self._deux_jours().rendre("1999-01-01") == ""


class TestUneFenetrePartielleNeSeComparePas:
    """Le garde-fou central de ce module."""

    def test_pas_d_ecart_affiche_si_les_fenetres_different(self):
        q = Quotidien()
        _journee(q, J1, 100, {"gate": 200}, duree_h=23.0)
        _journee(q, J2, 20, {"gate": 40}, duree_h=4.0)

        out = q.rendre()

        assert "Fenetres inegales" in out
        assert "ne sont pas comparables" in out
        assert (
            "(-" not in out
        ), "une chute produite par l'instrument, pas par la machine"

    def test_la_fenetre_reelle_est_toujours_affichee(self):
        q = Quotidien()
        _journee(q, J1, 10, {"gate": 10}, duree_h=6.0)

        assert "Observe sur 6.0 h" in q.rendre()

    def test_des_fenetres_proches_restent_comparables(self):
        q = Quotidien()
        _journee(q, J1, 100, {"gate": 200}, duree_h=23.0)
        _journee(q, J2, 100, {"gate": 210}, duree_h=22.0)

        out = q.rendre()

        assert "Fenetres inegales" not in out
        assert "(+10)" in out


class TestAucunVerdict:
    """Decrire est autorise. Conclure appartient au Superviseur, gate."""

    def test_ni_taux_ni_recommandation(self):
        q = Quotidien()
        _journee(q, J1, 100, {"gate": 200})
        _journee(q, J2, 80, {"gate": 260})

        out = q.rendre().lower()

        for interdit in ("%", "recommand", "il faut", "devrait", "trop", "anormal"):
            assert interdit not in out


class TestEmissionAuPassageDeMinuit:
    def test_le_recap_part_au_changement_de_jour(self):
        n = Narrateur(periode_agregat_s=1e9)
        n.absorber([_ev("HOLD", J1 + HEURE)], J1 + HEURE)

        assert n.absorber([], J1 + 2 * HEURE) == []

        sorties = n.absorber([], J2 + 60)

        assert len(sorties) == 1
        assert "RECAPITULATIF — 2026-08-05" in sorties[0].texte

    def test_le_recap_resume_le_jour_FINI_pas_le_jour_commence(self):
        n = Narrateur(periode_agregat_s=1e9)
        n.absorber([_ev("HOLD", J1 + HEURE) for _ in range(5)], J1 + HEURE)

        sorties = n.absorber([_ev("HOLD", J2 + 60)], J2 + 60)

        assert "2026-08-05" in sorties[0].texte
        assert "5" in sorties[0].texte

    def test_une_journee_vide_ne_produit_pas_de_recap(self):
        n = Narrateur(periode_agregat_s=1e9)
        n.absorber([], J1)

        assert n.absorber([], J2 + 60) == []

    def test_le_quotidien_compte_aussi_les_evenements_directs(self):
        n = Narrateur(periode_agregat_s=1e9)
        n.absorber([_ev("SYSTEM_EVENT", J1 + HEURE)], J1 + HEURE)

        sorties = n.absorber([], J2 + 60)

        assert sorties and "Decisions      1" in sorties[0].texte
