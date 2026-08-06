"""Narrateur — relais de la chronique du burn-in dans le recap quotidien.

Le Narrateur ne CALCULE pas la chronique : `tools/burnin_chronicle.py` la
produit, un timer la rafraichit, le Narrateur relaie le dernier releve.

Deux proprietes verrouillees ici :

1. Seule la FENETRE d'observation est relayee. N canonique et la projection
   vers 500 appartiennent a ① rapport_automatique (« gouvernance
   scientifique ») et n'ont rien a faire dans ce canal.
2. Un releve perime est DATE, jamais presente comme l'etat courant — meme
   regle que le PnL inconnu qui ne s'affiche pas a zero.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from observability.narrator.chronicle import PEREMPTION_H, dernier_releve, lignes

MAINTENANT = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def _releve(age_h=1.0, **kw):
    base = {
        "genere_le": (MAINTENANT - timedelta(hours=age_h)).isoformat(),
        "observe_s": 1732309.5,
        "calendaire_s": 1733656.6,
        "couverture_pct": 99.92,
        "interruptions": 3,
        "plus_longue_interruption_s": 712.7,
        "jours_sans_fichier": [],
        "n": 202,
        "reste_observe_j": 29.58,
    }
    base.update(kw)
    return base


def _fichier(tmp_path, *releves):
    chemin = tmp_path / "burnin_chronicle.jsonl"
    chemin.write_text("".join(json.dumps(r) + "\n" for r in releves), encoding="utf-8")
    return chemin


def _rendu(tmp_path, *releves):
    return "\n".join(
        lignes(_fichier(tmp_path, *releves), maintenant=MAINTENANT.timestamp())
    )


class TestLecture:
    def test_fichier_absent(self, tmp_path):
        assert dernier_releve(tmp_path / "rien.jsonl") is None
        assert lignes(tmp_path / "rien.jsonl") == []

    def test_fichier_vide(self, tmp_path):
        chemin = tmp_path / "vide.jsonl"
        chemin.write_text("", encoding="utf-8")

        assert dernier_releve(chemin) is None

    def test_ligne_illisible_ne_fait_pas_planter(self, tmp_path):
        chemin = tmp_path / "casse.jsonl"
        chemin.write_text("ceci n'est pas du json\n", encoding="utf-8")

        assert dernier_releve(chemin) is None
        assert lignes(chemin) == []

    def test_c_est_le_DERNIER_releve_qui_compte(self, tmp_path):
        chemin = _fichier(tmp_path, _releve(interruptions=1), _releve(interruptions=7))

        assert dernier_releve(chemin)["interruptions"] == 7


class TestCeQuiEstRelaye:
    def test_la_fenetre_observee_est_rendue(self, tmp_path):
        out = _rendu(tmp_path, _releve())

        assert "FENETRE D'OBSERVATION" in out
        assert "20.0 j" in out and "20.1 j" in out
        assert "99.9 %" in out

    def test_les_interruptions_avec_la_plus_longue(self, tmp_path):
        out = _rendu(tmp_path, _releve())

        assert "Arrets    3" in out
        assert "12 min" in out

    def test_aucune_interruption_n_affiche_pas_de_detail(self, tmp_path):
        out = _rendu(tmp_path, _releve(interruptions=0))

        assert "Arrets    0" in out
        assert "plus longue" not in out

    def test_les_jours_sans_donnees_sont_signales(self, tmp_path):
        out = _rendu(tmp_path, _releve(jours_sans_fichier=["2026-07-20"]))

        assert "Jours sans donnees : 1" in out
        assert "couverture non garantie" in out


class TestCeQuiAppartientAuCanalGouvernance:
    def test_ni_n_canonique_ni_projection(self, tmp_path):
        """« Gouvernance scientifique (N canonique, gates) » est a ①."""
        out = _rendu(tmp_path, _releve())

        assert "202" not in out
        assert "500" not in out
        assert "29.5" not in out and "2026-09" not in out


class TestUnReleveEstDate:
    def test_un_releve_perime_est_annonce_comme_tel(self, tmp_path):
        out = _rendu(tmp_path, _releve(age_h=PEREMPTION_H + 25))

        assert "non rafraichi" in out
        assert "FENETRE D'OBSERVATION" not in out
        assert "99.9" not in out, "un chiffre perime ne se donne pas pour actuel"

    def test_un_releve_frais_passe(self, tmp_path):
        out = _rendu(tmp_path, _releve(age_h=PEREMPTION_H - 1))

        assert "FENETRE D'OBSERVATION" in out
        assert "non rafraichi" not in out

    def test_une_date_illisible_ne_bloque_pas_le_relais(self, tmp_path):
        out = _rendu(tmp_path, _releve(genere_le="pas une date"))

        assert "FENETRE D'OBSERVATION" in out


class TestDonneesIncompletes:
    def test_sans_duree_rien_n_est_rendu(self, tmp_path):
        releve = _releve()
        del releve["observe_s"]

        assert _rendu(tmp_path, releve) == ""

    def test_calendaire_nul_ne_produit_pas_de_division(self, tmp_path):
        assert _rendu(tmp_path, _releve(calendaire_s=0)) == ""
