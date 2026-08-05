"""Agrégation des transitions de régime — le compte est le signal.

Le canal comportemental émettait un message Telegram par transition confirmée.
Le 30/07, six bascules `bear_trend` ⇄ `sideways` entre 20:23 et 23:22 ont
produit six messages. Pris un par un, aucun ne disait ce qu'ils signifiaient
ensemble : un détecteur de régime qui bat de l'aile toutes les quarante minutes.

Ces tests verrouillent la propriété qui compte : **agréger ne doit jamais
effacer le nombre de transitions ni la durée**. Un digest qui dirait seulement
« le régime a changé » serait pire que six messages — il perdrait le signal
tout en gardant le bruit.
"""

from __future__ import annotations

from core.advisor_loop import _format_regime_digest

REGIMES_LONGS = [
    "high_volatility_regime",
    "bear_trend",
    "sideways",
    "bull_trend",
    "flash_crash",
]


class TestEvenementIsole:
    """Une transition seule reste un événement lisible, pas un digest."""

    def test_une_transition_garde_le_format_simple(self):
        msg = _format_regime_digest([(1000.0, "bear_trend", "sideways")])
        assert "bear_trend" in msg and "sideways" in msg
        assert "transitions" not in msg, "pas de pluriel pour un événement unique"

    def test_liste_vide_ne_produit_rien(self):
        assert _format_regime_digest([]) == ""


class TestLeCompteEstPreserve:
    """La propriété centrale : agréger sans perdre l'information."""

    def test_la_rafale_du_30_07_est_resumee_sans_perdre_le_compte(self):
        base = 1000.0
        paires = [
            ("bear_trend", "sideways"),
            ("sideways", "bear_trend"),
            ("bear_trend", "sideways"),
            ("sideways", "bear_trend"),
            ("bear_trend", "sideways"),
            ("sideways", "bear_trend"),
        ]
        ev = [(base + i * 2150, a, b) for i, (a, b) in enumerate(paires)]
        msg = _format_regime_digest(ev)
        assert "6 transitions" in msg, "le nombre de bascules EST le signal"
        assert "h" in msg or "min" in msg, "la durée doit apparaître"
        assert "bear_trend" in msg and "sideways" in msg

    def test_l_aller_retour_est_nomme(self):
        ev = [
            (0.0, "sideways", "bear_trend"),
            (2280.0, "bear_trend", "sideways"),
        ]
        msg = _format_regime_digest(ev)
        assert "2 transitions" in msg
        assert "⇄" in msg, "une oscillation entre deux régimes doit être signalée"

    def test_l_etat_final_est_toujours_donne(self):
        ev = [
            (0.0, "a", "b"),
            (600.0, "b", "c"),
            (1200.0, "c", "d"),
        ]
        assert "état final : d" in _format_regime_digest(ev)


class TestLisibilite:
    """Tronquer la chaîne ne doit jamais tronquer le compte."""

    def test_chaine_longue_tronquee_mais_compte_intact(self):
        ev = [
            (i * 600.0, REGIMES_LONGS[i % 5], REGIMES_LONGS[(i + 1) % 5])
            for i in range(10)
        ]
        msg = _format_regime_digest(ev)
        assert "…" in msg, "la chaîne doit être abrégée au-delà de 120 caractères"
        assert "10 transitions" in msg, "le compte survit à la troncature"
        assert "état final" in msg

    def test_duree_en_minutes_sous_90_min(self):
        msg = _format_regime_digest([(0.0, "a", "b"), (1800.0, "b", "a")])
        assert "min" in msg and " h" not in msg

    def test_duree_en_heures_au_dela(self):
        msg = _format_regime_digest([(0.0, "a", "b"), (10800.0, "b", "a")])
        assert " h" in msg
