"""Canal ④ QuantCrypto — ce qui appartient a un autre proprietaire n'y est plus.

Contrat : docs/TELEGRAM_CHANNEL_CONTRACTS.md § 1 (matrice de routage) et § 5
(evenements interdits sur ④).

Trois fuites mesurees en service reel le 2026-08-06 :

1. `Seuil 66` dans l'entete du panneau — le seuil effectif appartient a ⑤
   Behavior, qui l'emet avec sa dispersion (thr=66-72 std=2.0). Le donner nu
   laissait croire a une barre fixe alors qu'elle oscille.
2. `Exchange: OK (181ms | uptime 100.0%)` — metrique de sante infra, a ①.
3. `[ALIVE]` toutes les 3 boucles — 23 messages en 6 h, ~92/jour, melangeant
   TROIS proprietaires : equity et positions (②), RAM (①), regime (④).
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace as NS

from core.advisor_loop import _build_summary


def _code_seul(chemin: str) -> str:
    """Source sans les lignes de commentaire.

    Les commentaires qui documentent un retrait CITENT forcement ce qui a ete
    retire — « la ligne nominale "Exchange: OK …" est retiree ». Scanner le
    source brut ferait echouer le test sur sa propre explication.
    """
    lignes = pathlib.Path(chemin).read_text(encoding="utf-8").splitlines()
    return "\n".join(x for x in lignes if not x.strip().startswith("#"))


CODE = _code_seul("core/advisor_loop.py")


def _resultat(symbol="BTC/USDT", score=72, regime="bull_trend", signal="BUY"):
    return {
        "symbol": symbol,
        "signal": NS(signal=signal, score=score, regime=regime),
        "gate": NS(allowed=True),
        "advice": NS(risk_level="medium"),
    }


class TestLeSeuilEffectifAppartientAuCanalComportement:
    def test_l_entete_n_annonce_plus_le_seuil(self):
        entete = _build_summary([_resultat()], cycle=12, min_score=66).splitlines()[1]

        assert "Seuil" not in entete
        assert "66" not in entete

    def test_l_entete_garde_l_univers_et_la_tendance(self):
        """Ne pas sur-corriger : ces deux-la sont bien la propriete de ④."""
        entete = _build_summary([_resultat()], cycle=12, min_score=66).splitlines()[1]

        assert "1 paires" in entete
        assert "Tendance" in entete

    def test_le_filtre_de_la_liste_reste_nomme(self):
        """« +N autres >= 66 » decrit le filtre de CE message, pas l'etat du
        systeme. Sans lui, « +10 autres » ne veut plus rien dire. La frontiere
        est la : annoncer un seuil comme propriete du systeme appartient a ⑤,
        expliquer comment ce message a ete construit appartient au message.
        """
        out = _build_summary(
            [_resultat(symbol=f"X{i}/USDT") for i in range(15)], cycle=1, min_score=66
        )

        assert ">= 66" in out


class TestLaSanteInfraAppartientAuCanalRapport:
    def test_plus_de_ligne_exchange_nominale(self):
        assert "Exchange: OK" not in CODE

    def test_l_alerte_hors_ligne_reste(self):
        """Elle n'est pas deplacee tant que ① n'a pas de chemin urgent :
        ① n'emet que toutes les 6 h. On ne troque pas une impurete de contrat
        contre une panne d'exchange annoncee six heures trop tard.
        """
        assert "EXCHANGE HORS LIGNE" in CODE


class TestLeHeartbeatNEstPlusEmisVersTelegram:
    def test_aucun_envoi_telegram_du_heartbeat(self):
        assert "_telegram(_hb_msg)" not in CODE

    def test_le_heartbeat_reste_journalise(self):
        """Rien n'est perdu : le snapshot reste publie et journalise pour les
        consommateurs internes. Seule la diffusion Telegram disparait.
        """
        assert "render_heartbeat(" in CODE
        assert "[Heartbeat] %s" in CODE
