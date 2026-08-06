"""Chronique du burn-in — temps OBSERVE contre temps calendaire.

Le temps calendaire depuis l'epoque suppose que le moteur tourne sans
interruption. Il s'arrete : quatre redemarrages le 2026-08-06, des migrations,
des incidents. Un debit calcule sur le calendaire sous-estime la machine, une
date d'arrivee a N=500 calculee dessus est optimiste.
"""

from __future__ import annotations

from tools.burnin_chronicle import detecter_segments, projeter, resumer

H = 3600.0
J = 86400.0
T0 = 1785888000.0  # 2026-08-05 00:00 UTC
SEUIL = 600.0  # 10 min


def _flux(depart, duree_s, pas=300.0):
    """Un rejet toutes les 5 minutes — le pouls nominal du moteur."""
    n = int(duree_s / pas) + 1
    return [depart + i * pas for i in range(n)]


class TestDetectionDesInterruptions:
    def test_un_flux_continu_donne_un_seul_segment(self):
        segments = detecter_segments(_flux(T0, 6 * H), SEUIL)

        assert len(segments) == 1
        assert segments[0][0] == T0

    def test_un_trou_coupe_le_segment(self):
        flux = _flux(T0, 2 * H) + _flux(T0 + 5 * H, 2 * H)

        assert len(detecter_segments(flux, SEUIL)) == 2

    def test_un_micro_ecart_ne_coupe_rien(self):
        """Un cycle dure ~5 min : 8 minutes de silence n'est pas un arret."""
        flux = _flux(T0, H) + _flux(T0 + H + 480, H)

        assert len(detecter_segments(flux, SEUIL)) == 1

    def test_l_ordre_d_arrivee_n_a_pas_d_importance(self):
        flux = _flux(T0, 2 * H)

        assert detecter_segments(list(reversed(flux)), SEUIL) == detecter_segments(
            flux, SEUIL
        )

    def test_aucune_donnee_ne_produit_aucun_segment(self):
        assert detecter_segments([], SEUIL) == []


class TestLeTempsObserveNestPasLeCalendaire:
    def test_une_interruption_creuse_l_ecart(self):
        flux = _flux(T0, 2 * H) + _flux(T0 + 5 * H, 2 * H)
        fin = T0 + 7 * H

        r = resumer(detecter_segments(flux, SEUIL), fin)

        assert r["calendaire_s"] == 7 * H
        assert abs(r["observe_s"] - 4 * H) < 1
        assert abs(r["arret_s"] - 3 * H) < 1
        assert r["interruptions"] == 1
        assert abs(r["plus_longue_interruption_s"] - 3 * H) < 1

    def test_le_silence_en_cours_compte_comme_un_arret(self):
        """Sinon la couverture reste flatteuse juste apres une panne."""
        flux = _flux(T0, 2 * H)

        r = resumer(detecter_segments(flux, SEUIL), T0 + 6 * H)

        assert r["interruptions"] == 1
        assert abs(r["arret_s"] - 4 * H) < 1

    def test_un_flux_parfait_ne_signale_aucun_arret(self):
        flux = _flux(T0, 6 * H)

        r = resumer(detecter_segments(flux, SEUIL), flux[-1])

        assert r["interruptions"] == 0
        assert abs(r["observe_s"] - r["calendaire_s"]) < 1

    def test_sans_donnees_tout_est_a_zero(self):
        r = resumer([], T0)

        assert r["observe_s"] == 0 and r["interruptions"] == 0


class TestProjection:
    def test_le_rythme_observe_donne_une_date_plus_lointaine(self):
        """C'est tout l'interet : 200 trades en 10 j observes sur 20 j
        calendaires, ce n'est pas le meme horizon.
        """
        sur_calendaire = projeter(200, 20.0)
        sur_observe = projeter(200, 10.0)

        assert sur_calendaire == 30.0
        assert sur_observe == 15.0
        assert sur_observe < sur_calendaire

    def test_cible_atteinte_rend_zero(self):
        assert projeter(500, 10.0) == 0.0
        assert projeter(620, 10.0) == 0.0

    def test_un_rythme_nul_ne_promet_pas_une_date(self):
        """Zero trade rendu comme « 0 jour » serait une promesse, pas une
        mesure — meme faute qu'un PnL inconnu affiche a zero.
        """
        assert projeter(0, 10.0) is None
        assert projeter(200, 0.0) is None
