"""Aucun canal Telegram ne doit se déverser dans un autre en silence.

Deux replis muets existaient :

- `advisor_loop._telegram_behavior` : `TELEGRAM_BEHAVIOR_CHAT or TELEGRAM_CHAT`.
  Un `chat_id` vide envoyait le canal comportement dans @QuantCrpto_bot.
- `CommandCenterBot.from_env` : `os.getenv("P10_PORTFOLIO_CHAT_ID",
  os.getenv("TELEGRAM_CHAT_ID", ""))`. Même défaut pour le tableau de bord.

Dans les deux cas, une variable d'environnement oubliée suffisait à fusionner
deux responsabilités **sans aucun signal**. Un contrat de canal ne tient pas
sous un repli muet : il devient contournable par accident.

La règle retenue : **non configuré = silencieux ET signalé**. Mélanger deux
canaux est pire que n'en avoir qu'un, parce qu'un canal manquant se remarque
alors qu'un canal pollué se confond avec du bruit.
"""

from __future__ import annotations


class TestCanalComportement:
    def test_aucun_envoi_quand_le_canal_n_est_pas_configure(self, monkeypatch):
        """Propriete COMPORTEMENTALE : aucune requete, pas meme vers le principal.

        Un test qui grepperait le code source matcherait aussi la docstring qui
        cite l'ancien motif — il testerait la documentation, pas le programme.
        On verifie donc ce qui compte : qu'aucun POST ne part.
        """
        import core.advisor_loop as al

        monkeypatch.setattr(al, "TELEGRAM_BEHAVIOR_CHAT", "")
        monkeypatch.setattr(al, "TELEGRAM_TOKEN", "jeton-factice")
        monkeypatch.setattr(al, "TELEGRAM_CHAT", "-100999999")
        monkeypatch.setattr(al, "_BEHAVIOR_CHAT_WARNED", False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        appels: list = []
        monkeypatch.setattr(al.requests, "post", lambda *a, **k: appels.append((a, k)))
        monkeypatch.setattr(al.log, "warning", lambda *a, **k: None)

        al._telegram_behavior("message comportement")
        assert appels == [], "un chat_id vide ne doit produire AUCUN envoi"

    def test_envoie_bien_quand_le_canal_est_configure(self, monkeypatch):
        import core.advisor_loop as al

        monkeypatch.setattr(al, "TELEGRAM_BEHAVIOR_CHAT", "-100111111")
        monkeypatch.setattr(al, "TELEGRAM_TOKEN", "jeton-factice")
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        envois: list = []

        class _Rep:
            status_code = 200

        def _post(url, **k):
            envois.append(k.get("json", {}))
            return _Rep()

        monkeypatch.setattr(al.requests, "post", _post)
        al._telegram_behavior("message comportement")
        assert len(envois) == 1
        assert envois[0]["chat_id"] == "-100111111"

    def test_avertit_une_seule_fois(self, monkeypatch):
        import core.advisor_loop as al

        monkeypatch.setattr(al, "TELEGRAM_BEHAVIOR_CHAT", "")
        monkeypatch.setattr(al, "TELEGRAM_TOKEN", "jeton-factice")
        monkeypatch.setattr(al, "_BEHAVIOR_CHAT_WARNED", False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        avertissements: list[str] = []
        monkeypatch.setattr(
            al.log, "warning", lambda msg, *a, **k: avertissements.append(str(msg))
        )
        # Un envoi reel serait un appel reseau : sans chat_id la fonction sort
        # avant, c'est precisement ce qu'on verifie.
        al._telegram_behavior("x")
        al._telegram_behavior("y")
        al._telegram_behavior("z")
        assert len(avertissements) == 1, "un log par cycle noierait le signal"
        assert "DESACTIVE" in avertissements[0]


class TestTableauDeBordPortefeuille:
    def test_pas_de_repli_vers_telegram_chat_id(self, monkeypatch):
        from capital_deployment.command_center_bot import CommandCenterBot
        from capital_deployment.command_center_bot import (
            CommandDataProvider as Provider,
        )

        monkeypatch.setenv("P10_PORTFOLIO_BOT_TOKEN", "jeton-factice")
        monkeypatch.delenv("P10_PORTFOLIO_CHAT_ID", raising=False)
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100999999")

        bot = CommandCenterBot.from_env(Provider())
        assert (
            bot._chat_id != "-100999999"
        ), "le bot ne doit JAMAIS retomber sur le chat principal"
        assert not bot._chat_id

    def test_chat_id_propre_est_respecte(self, monkeypatch):
        from capital_deployment.command_center_bot import CommandCenterBot
        from capital_deployment.command_center_bot import (
            CommandDataProvider as Provider,
        )

        monkeypatch.setenv("P10_PORTFOLIO_BOT_TOKEN", "jeton-factice")
        monkeypatch.setenv("P10_PORTFOLIO_CHAT_ID", "-100123456")
        bot = CommandCenterBot.from_env(Provider())
        assert bot._chat_id == "-100123456"
