"""Les montants nomment le registre dont ils viennent (2026-08-06).

En mode paper, `get_balances()` renvoie WALLET_PAPER_CAPITAL + PnL cumule du
ledger (execution_engine.py:233) — pas un solde d'exchange. Ce montant
s'affichait sous la cle "spot" et sous le titre « Capital total » : deux
etiquettes qui designent de l'argent reel. Le chiffre etait juste, le nom
mentait.

Regle : un registre inconnu ne se devine pas. Sans `get_capital_ledger`, les
libelles restent neutres au lieu d'affirmer « papier » ou « reel ».
"""

from capital_deployment.command_center_bot import (
    CommandDataProvider,
    _fmt_balance,
    _fmt_pnl,
)


def _provider(ledger=None, **kw):
    return CommandDataProvider(
        get_balances=lambda: {"spot": 672.93, "futures": 0.0},
        get_capital_ledger=ledger,
        **kw,
    )


class TestSoldes:
    def test_le_titre_nomme_le_registre(self):
        out = _fmt_balance(_provider(ledger=lambda: "papier"))

        assert "SOLDES — compte papier" in out
        assert "Total papier" in out

    def test_registre_inconnu_reste_neutre(self):
        out = _fmt_balance(_provider())

        assert "*SOLDES*" in out
        assert "papier" not in out and "réel" not in out

    def test_un_fournisseur_qui_casse_ne_fait_pas_mentir(self):
        def _boom():
            raise RuntimeError("mode indisponible")

        out = _fmt_balance(_provider(ledger=_boom))

        assert "*SOLDES*" in out
        assert "papier" not in out

    def test_registre_vide_traite_comme_inconnu(self):
        out = _fmt_balance(_provider(ledger=lambda: "   "))

        assert "*SOLDES*" in out


class TestAucunSoldeFabrique:
    """Un solde non mesure n'est pas un solde nul (2026-08-06).

    advisor_loop passait {"spot": capital, "futures": 0.0} : le 0.0 etait un
    litteral en dur, jamais lu d'un exchange, alors que le journal PaperArena
    etiquette ses trades "futures_demo". Le panneau annoncait un solde futures
    nul pendant que le canal annoncait des trades futures.
    """

    def test_le_wallet_simule_ne_s_appelle_plus_spot(self):
        p = CommandDataProvider(
            get_balances=lambda: {"wallet simulé": 672.82},
            get_capital_ledger=lambda: "papier",
        )

        out = _fmt_balance(p)

        assert "Wallet simulé" in out
        assert "Spot" not in out

    def test_pas_de_ligne_futures_fabriquee(self):
        p = CommandDataProvider(
            get_balances=lambda: {"wallet simulé": 672.82},
            get_capital_ledger=lambda: "papier",
        )

        out = _fmt_balance(p)

        assert "Futures" not in out
        assert "0.00" not in out


class TestPnL:
    def test_capital_total_ne_ment_plus(self):
        out = _fmt_pnl(_provider(ledger=lambda: "papier"))

        assert "Capital papier: *672.93 USD*" in out
        # « total » etait faux : le PnL latent n'est pas dans cette somme.
        assert "Capital total" not in out

    def test_registre_inconnu_reste_neutre(self):
        out = _fmt_pnl(_provider())

        assert "Capital: *672.93 USD*" in out
        assert "Capital total" not in out

    def test_mode_reel_le_dit(self):
        out = _fmt_pnl(_provider(ledger=lambda: "réel"))

        assert "Capital réel: *672.93 USD*" in out
