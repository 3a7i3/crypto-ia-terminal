"""Rapport automatique de @mon_portfolio_bot — contrat § 4, « Human Dashboard ».

Le rapport poussé toutes les heures contenait PERFORMANCE (WR/Sharpe/DD), le
détail des positions, la liste des SIGNAUX et les DERNIERS TRADES — soit ~25
lignes, dont la majorité appartient contractuellement à d'autres canaux et y
était déjà émise. Sept duplications avaient été mesurées entre les six canaux.

Ce que ces tests verrouillent :

1. **Le rapport poussé ne contient que les cinq informations du § 4** — phase,
   capital, PnL ouvert, nombre de positions, niveau de risque.
2. **Une donnée absente n'est pas remplacée par un zéro.** C'est le défaut qui
   rendait `/regime` et le panneau `[BEHAVIOR]` trompeurs plutôt que muets :
   afficher `0` à la place d'une absence fait croire, là où le silence ferait
   douter.
3. **Les commandes ne sont pas touchées.** Le contrat régit ce qui est POUSSÉ,
   pas ce qui est demandé : `/kpis` et `/positions` restent détaillés.
"""

from __future__ import annotations

from capital_deployment.command_center_bot import (
    CommandDataProvider,
    _fmt_positions,
    _fmt_rapport,
)


class _Throttle:
    class _Alloc:
        min_duration_days = 7

        def days_elapsed(self):
            return 0.1

    allocated_capital = 10.0

    def allocation(self):
        return _Throttle._Alloc()


def _kpis():
    return type(
        "K",
        (),
        {
            "win_rate": 0.379,
            "sharpe": -5.717,
            "max_drawdown": 0.015,
            "current_drawdown": 0.007,
            "total_trades": 190,
        },
    )()


def _provider_complet(**over):
    base = dict(
        get_paper_equity=lambda: 673.48,
        get_open_pnl=lambda: {
            "pnl_usd": -0.42,
            "pnl_pct": -1.40,
            "engaged_usd": 30.0,
        },
        get_positions=lambda: [{"symbol": "MYX/USDT"}, {"symbol": "ZRO/USDT"}],
        get_phase=lambda: "F-01",
        get_throttle=lambda: _Throttle(),
        get_risk=lambda: {"level": "CLEAR", "open_pnl_pct": -0.42},
        get_signals=lambda: {"X/USDT": {"score": 72, "action": "SELL"}},
        get_trades=lambda: [{"symbol": "A/USDT", "pnl": 1.2, "ts": 1785900000}],
        get_kpis=_kpis,
    )
    base.update(over)
    return CommandDataProvider(**base)


class TestLeRapportContientLesCinqInformations:
    def test_phase_capital_pnl_positions_risque(self):
        out = _fmt_rapport(_provider_complet())
        assert "F-01" in out
        assert "673.48" in out
        assert "-0.42" in out
        assert "Positions" in out and "2" in out
        assert "CLEAR" in out

    def test_le_rapport_tient_sur_un_ecran(self):
        out = _fmt_rapport(_provider_complet())
        assert len(out.splitlines()) <= 8, "un digest ne doit pas etre un flux"


class TestCeQuiAppartientAuxAutresCanaux:
    """Chaque bloc retire est emis ailleurs — il ne disparait pas, il demenage."""

    def test_performance_absente(self):
        out = _fmt_rapport(_provider_complet())
        assert "Win Rate" not in out and "Sharpe" not in out
        assert "Max DD" not in out

    def test_detail_des_positions_absent(self):
        out = _fmt_rapport(_provider_complet())
        assert "MYX" not in out, "le detail va a @PaperArena, seul le compte reste"

    def test_signaux_absents(self):
        assert "SIGNAUX" not in _fmt_rapport(_provider_complet())

    def test_derniers_trades_absents(self):
        assert "DERNIERS TRADES" not in _fmt_rapport(_provider_complet())


class TestUneDonneeAbsenteNestPasUnZero:
    def test_pnl_inconnu_n_est_pas_affiche(self):
        out = _fmt_rapport(_provider_complet(get_open_pnl=lambda: None))
        assert "PnL ouvert" not in out

    def test_pnl_reellement_nul_est_affiche(self):
        out = _fmt_rapport(
            _provider_complet(
                get_open_pnl=lambda: {
                    "pnl_usd": 0.0,
                    "pnl_pct": 0.0,
                    "engaged_usd": 30.0,
                }
            )
        )
        assert "PnL ouvert" in out and "0.00" in out

    def test_niveau_de_risque_absent_n_invente_rien(self):
        out = _fmt_rapport(_provider_complet(get_risk=lambda: {}))
        assert "Risque" not in out


class TestLePnLVientDuLedgerQuiPorteLesPositions:
    """Regression 2026-08-05 : "PnL ouvert +0.00 %" sous 3 positions vivantes.

    Le rapport lisait ExecutiveOverride.open_pnl_pct, alimenté par pos_manager,
    jamais rempli en paper trading. La ligne Positions venait deja de MexcSim :
    deux registres differents sur deux lignes voisines, sans etiquette.
    """

    def test_le_rapport_n_utilise_plus_executive_override(self):
        out = _fmt_rapport(
            _provider_complet(
                get_open_pnl=lambda: None,
                get_risk=lambda: {"level": "CLEAR", "open_pnl_pct": 99.99},
            )
        )
        assert "99.99" not in out, "le PnL du rapport ne vient plus de get_risk"
        assert "PnL ouvert" not in out

    def test_le_montant_en_usd_leve_l_ambiguite_du_denominateur(self):
        out = _fmt_rapport(_provider_complet())
        assert "-0.42 USD" in out
        assert "-1.40 %" in out


class TestLesCommandesRestentDetaillees:
    """Le contrat regit le POUSSE, pas le DEMANDE."""

    def test_positions_reste_detaille_a_la_demande(self):
        out = _fmt_positions(
            _provider_complet(
                get_positions=lambda: [
                    {
                        "symbol": "MYX/USDT",
                        "side": "buy",
                        "size_usd": 10.0,
                        "pnl": -0.05,
                        "pnl_pct": -0.5,
                    }
                ]
            )
        )
        assert "MYX/USDT" in out, "/positions doit rester complet"


class TestRobustesse:
    def test_provider_vide_ne_leve_pas(self):
        out = _fmt_rapport(CommandDataProvider())
        assert "PORTEFEUILLE" in out
