"""Narrateur — lecteur, emetteur, boucle.

Contrat : docs/CONTRAT_SUPERVISEUR.md.
"""

from __future__ import annotations

import json

from observability.narrator.budget import Budget
from observability.narrator.reader import BoiteNoire
from observability.narrator.runner import Narrateur
from observability.narrator.sender import Emetteur

TS = 1786064400.0  # 2026-08-06 01:00:00 UTC


def _ev(type_, ts=TS, **kw):
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


def _ecrire(chemin, entrees, mode="a"):
    with open(chemin, mode, encoding="utf-8") as fh:
        for e in entrees:
            fh.write(json.dumps(e) + "\n")


# ── Lecteur ──────────────────────────────────────────────────────────────────


class TestLeLecteurNeRemonteJamaisLHistoire:
    """152 049 lignes dans le fichier reel : demarrer au debut inonderait."""

    def test_le_premier_passage_ne_rend_rien(self, tmp_path):
        f = tmp_path / "bb.jsonl"
        _ecrire(f, [_ev("SYSTEM_EVENT") for _ in range(50)])

        assert list(BoiteNoire(str(f)).lire()) == []

    def test_seules_les_nouveautes_sortent(self, tmp_path):
        f = tmp_path / "bb.jsonl"
        _ecrire(f, [_ev("HOLD")])
        lecteur = BoiteNoire(str(f))
        list(lecteur.lire())

        _ecrire(f, [_ev("SYSTEM_EVENT", reason="apres")])
        nouvelles = list(lecteur.lire())

        assert len(nouvelles) == 1
        assert nouvelles[0]["reason"] == "apres"

    def test_rien_de_neuf_ne_rend_rien(self, tmp_path):
        f = tmp_path / "bb.jsonl"
        _ecrire(f, [_ev("HOLD")])
        lecteur = BoiteNoire(str(f))
        list(lecteur.lire())

        assert list(lecteur.lire()) == []

    def test_depuis_le_debut_si_demande(self, tmp_path):
        f = tmp_path / "bb.jsonl"
        _ecrire(f, [_ev("HOLD"), _ev("HOLD")])
        lecteur = BoiteNoire(str(f), depuis_la_fin=False)
        list(lecteur.lire())

        assert len(list(lecteur.lire())) == 2


class TestLeLecteurSurvitAuxAccidents:
    def test_fichier_absent(self, tmp_path):
        lecteur = BoiteNoire(str(tmp_path / "jamais.jsonl"))
        list(lecteur.lire())

        assert list(lecteur.lire()) == []

    def test_fichier_tronque_on_repart_du_debut(self, tmp_path):
        f = tmp_path / "bb.jsonl"
        _ecrire(f, [_ev("HOLD") for _ in range(10)])
        lecteur = BoiteNoire(str(f))
        list(lecteur.lire())

        _ecrire(f, [_ev("SYSTEM_EVENT", reason="neuf")], mode="w")
        rendues = list(lecteur.lire())

        assert len(rendues) == 1 and rendues[0]["reason"] == "neuf"

    def test_ligne_en_cours_d_ecriture_attend(self, tmp_path):
        f = tmp_path / "bb.jsonl"
        _ecrire(f, [_ev("HOLD")])
        lecteur = BoiteNoire(str(f))
        list(lecteur.lire())

        with open(f, "a", encoding="utf-8") as fh:
            fh.write('{"ts": 1, "decision_type": "SYSTEM')  # coupee

        assert list(lecteur.lire()) == []

        with open(f, "a", encoding="utf-8") as fh:
            fh.write('_EVENT", "reason": "complete"}\n')

        rendues = list(lecteur.lire())
        assert len(rendues) == 1 and rendues[0]["reason"] == "complete"

    def test_ligne_illisible_sautee_sans_planter(self, tmp_path):
        f = tmp_path / "bb.jsonl"
        f.write_text("", encoding="utf-8")
        lecteur = BoiteNoire(str(f))
        list(lecteur.lire())

        with open(f, "a", encoding="utf-8") as fh:
            fh.write("ceci n'est pas du json\n")
            fh.write(json.dumps(_ev("SYSTEM_EVENT", reason="ok")) + "\n")

        rendues = list(lecteur.lire())

        assert len(rendues) == 1 and rendues[0]["reason"] == "ok"
        assert lecteur.lignes_illisibles == 1


# ── Emetteur ─────────────────────────────────────────────────────────────────


class _Log:
    def __init__(self):
        self.avertissements = []

    def warning(self, msg, *a):
        self.avertissements.append(msg % a if a else msg)

    def debug(self, *a, **k):
        pass


class TestLEmetteurNAJamaisDeRepli:
    def test_non_configure_reste_silencieux(self):
        e = Emetteur(token="", chat_id="")

        assert e.configure is False
        assert e.envoyer("un message") is False
        assert e.envoyes == 0

    def test_non_configure_avertit_une_seule_fois(self):
        log = _Log()
        e = Emetteur(token="", chat_id="", log=log)

        for _ in range(5):
            e.envoyer("x")

        assert len(log.avertissements) == 1
        assert "DESACTIVEE" in log.avertissements[0]
        assert "Aucun repli" in log.avertissements[0]

    def test_un_texte_vide_n_envoie_rien(self):
        assert Emetteur(token="t", chat_id="c").envoyer("") is False


# ── Assemblage ───────────────────────────────────────────────────────────────


class TestLeNarrateurAssemble:
    def test_le_direct_sort_la_routine_est_retenue(self):
        n = Narrateur()

        sorties = n.absorber([_ev("SYSTEM_EVENT"), _ev("HOLD"), _ev("HOLD")], TS)

        assert len(sorties) == 1
        assert "SYSTEME" in sorties[0].texte
        assert n.agregat.total == 2

    def test_ce_qui_appartient_ailleurs_ne_compte_nulle_part(self):
        n = Narrateur()

        sorties = n.absorber([_ev("TRADE_EXECUTED"), _ev("POSITION_CLOSED")], TS)

        assert sorties == []
        assert n.agregat.vide, "les trades sont a ②, pas meme comptes ici"

    def test_l_agregat_part_a_l_echeance(self):
        n = Narrateur(periode_agregat_s=3600)
        n.absorber([_ev("HOLD")], TS)

        assert n.absorber([], TS + 100) == []

        tardif = n.absorber([], TS + 3601)

        assert len(tardif) == 1
        assert "DERNIERE HEURE" in tardif[0].texte

    def test_un_evenement_differe_pese_dans_l_agregat(self):
        """Un plafonne ne doit pas disparaitre des DEUX comptages."""
        n = Narrateur(budget=Budget(max_par_heure=1), periode_agregat_s=3600)

        n.absorber([_ev("TRADE_REFUSED", refused_by=["gate"]) for _ in range(1)], TS)
        n.absorber([_ev("TRADE_REFUSED", refused_by=["meta"])], TS)

        assert n.budget.differes == 1

        agregat = n.absorber([], TS + 3601)

        assert "+1 evenement(s) groupe(s)" in agregat[0].texte

    def test_un_urgent_passe_malgre_le_plafond(self):
        n = Narrateur(budget=Budget(max_par_heure=0))

        sorties = n.absorber([_ev("HALT_TRIGGERED")], TS)

        assert len(sorties) == 1 and sorties[0].urgent is True

    def test_le_premier_blocage_redevient_possible_le_lendemain(self):
        n = Narrateur(periode_agregat_s=3600)
        veille = _ev("TRADE_REFUSED", refused_by=["gate"])

        assert len(n.absorber([veille], TS)) == 1
        assert n.absorber([veille], TS) == []

        # Echeance le lendemain : les cles de la veille sont oubliees.
        n.absorber([], TS + 86400 + 3601)
        demain = _ev("TRADE_REFUSED", ts=TS + 86400 + 3602, refused_by=["gate"])

        assert len(n.absorber([demain], TS + 86400 + 3602)) == 1

    def test_un_silence_complet_ne_produit_aucun_message(self):
        n = Narrateur(periode_agregat_s=3600)
        n.absorber([], TS)

        assert n.absorber([], TS + 3601) == []
