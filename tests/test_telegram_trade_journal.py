"""Journal Telegram des trades — @QuantCrpto_bot ne contient que des trades.

Contexte. Aucun événement de trade n'atteignait Telegram : le message `SORTIE`
existait bien (`advisor_loop._on_position_close`) mais sur le callback
`pos_manager.on_close`, alors que les trades réels sont ouverts et fermés par
`MexcSimulator`. Le chemin instrumenté n'était pas le chemin exécuté — quatrième
occurrence du même motif dans ce dépôt.

Ces tests verrouillent deux propriétés :

1. **Le format est complet et stable.** Un panneau d'application doit pouvoir le
   consommer tel quel : horodatage, paire, sens, prix, PnL, durée, motif, compte.
2. **Le journal ne peut jamais faire échouer un trade.** Un canal d'observation
   qui casse l'exécution serait pire que pas de canal du tout.
"""

from __future__ import annotations

from paper_trading.mexc_simulator import (
    MexcSimulator,
    _fmt_duree,
    format_entree,
    format_sortie,
)

TS = 1785877666.0  # horodatage fixe — aucun test ne dépend de l'heure courante


class TestFormatEntree:
    def test_contient_tout_ce_qu_un_panneau_doit_afficher(self):
        msg = format_entree("MYX/USDT", "buy", 0.07907952, 10.0, "futures_demo", TS)
        assert "ENTRÉE BUY" in msg
        assert "MYX/USDT" in msg
        assert "UTC" in msg, "l'horodatage doit être explicite et daté UTC"
        assert "0.0790795" in msg
        assert "$10.00" in msg
        assert "futures_demo" in msg

    def test_le_sens_est_normalise_en_majuscules(self):
        assert "SELL" in format_entree("X/USDT", "sell", 1.0, 1.0, "m", TS)


class TestFormatSortie:
    def test_trade_gagnant(self):
        msg = format_sortie(
            "MYX/USDT", "buy", 0.079, 0.080, 0.13, 1.31, "TP", 5100.0, "m", TS
        )
        assert "+$0.13" in msg and "+1.31%" in msg
        assert "Motif: TP" in msg
        assert "1h25m" in msg

    def test_trade_perdant_signe_negatif(self):
        msg = format_sortie(
            "ZRO/USDT", "sell", 2.451, 2.502, -0.21, -2.08, "SL", 412.0, "m", TS
        )
        ligne_pnl = msg.split("PnL:")[1].split("\n")[0]
        assert "-$0.21" in ligne_pnl
        assert "-2.08%" in ligne_pnl
        assert "+" not in ligne_pnl, "aucun signe positif sur un trade perdant"

    def test_entree_et_sortie_toutes_deux_presentes(self):
        msg = format_sortie("A/B", "buy", 10.0, 12.0, 2.0, 20.0, "TP", 60.0, "m", TS)
        assert "10" in msg and "12" in msg


class TestDuree:
    def test_sous_une_heure_en_minutes_secondes(self):
        assert _fmt_duree(412) == "06m52s"
        assert _fmt_duree(0) == "00m00s"
        assert _fmt_duree(3599) == "59m59s"

    def test_au_dela_en_heures_minutes(self):
        assert _fmt_duree(3600) == "1h00m"
        assert _fmt_duree(8130) == "2h15m"

    def test_duree_negative_ne_casse_pas(self):
        assert _fmt_duree(-5) == "00m00s"


class TestLeJournalNeCassePasLeTrade:
    """Un canal d'observation ne doit jamais interrompre l'exécution."""

    def test_sans_callback_reste_silencieux(self):
        MexcSimulator()._journal("ignoré")  # ne doit pas lever

    def test_callback_en_echec_est_absorbe(self):
        def boom(_):
            raise RuntimeError("canal HS")

        MexcSimulator(trade_journal_fn=boom)._journal("x")  # ne doit pas lever

    def test_callback_valide_recoit_le_texte(self):
        recu: list[str] = []
        MexcSimulator(trade_journal_fn=recu.append)._journal("ping")
        assert recu == ["ping"]

    def test_journal_distinct_du_canal_operationnel(self):
        """`telegram_fn` porte le bavardage ; `trade_journal_fn` les trades."""
        ops: list[str] = []
        trades: list[str] = []
        sim = MexcSimulator(telegram_fn=ops.append, trade_journal_fn=trades.append)
        sim._notify("[SIM] REJETE — prix indisponible")
        sim._journal("ENTRÉE BUY — X/USDT")
        assert ops == ["[SIM] REJETE — prix indisponible"]
        assert trades == ["ENTRÉE BUY — X/USDT"]
