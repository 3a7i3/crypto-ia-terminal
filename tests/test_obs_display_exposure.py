"""OBS-001 — Tests de regression de l'exposition d'affichage.

CONTEXTE (auto-portant)
-----------------------
Le panneau Telegram affiche simultanement "Positions: 3" et
"Portfolio Exposure: 0.0%", parce que les deux valeurs viennent de deux
stores differents :

  - le COMPTE de positions vient de _virtual_portfolio (MexcSimulator),
    via _display_position_summary (core/advisor_loop.py:434-459) ;
  - l'EXPOSITION vient de pos_manager.get_open() passe a portfolio_health()
    (core/advisor_loop.py:6785-6787). En mode paper, pos_manager est VIDE.

portfolio_brain.py:668-687 itere la liste recue (total_exposure_usd +=
p.size_usd) puis calcule total_exposure_pct = total_exposure_usd / capital.
Liste vide => exposition 0.

PREUVE NUMERIQUE du diagnostic : portfolio_health derive
free_capital = max(0, capital * MAX_TOTAL_EXPOSURE_PCT - total_exposure_usd)
avec MAX_TOTAL_EXPOSURE_PCT = 0.40 (portfolio_brain.py:88). Le panneau
affichait 674.47 * 0.40 - 0 = 269.79 $, exactement la valeur observee, ce qui
confirme total_exposure_usd = 0 alors que trois positions etaient ouvertes.

CE QUE CE FICHIER FAIT
----------------------
1. Un test ROUGE qui fige le bug : avec des positions ouvertes, les metriques
   d'affichage doivent deriver du MEME store que le compte de positions.
   Il ECHOUE aujourd'hui et devient vert avec OBS-002.
2. Une garde VERTE (INV-2) : le verdict de check_new_trade doit rester
   strictement inchange. Si elle rougit, le comportement de DECISION a change
   => reset d'epoque non autorise => incident.

NOTE D'ARCHITECTURE
-------------------
core.advisor_loop n'est PAS importable (advisor_loop.py:33 fait un import plat
`from advisor_runtime_adapters import ...` d'un module situe dans core/).
Le moteur n'est donc pas testable unitairement — c'est pourquoi ce bug a
survecu. La logique d'affichage est donc placee dans
observability/system_snapshot.py, importable et deja couvert, et advisor_loop
se contente de l'appeler (OBS-002).
"""

import pytest

# Valeurs reellement observees dans le panneau du 2026-07-24.
OBSERVED_CAPITAL = 674.47
OBSERVED_FREE_CASH_BLIND = 269.79  # = 674.47 * 0.40 - 0  (gate aveugle)
MAX_EXPOSURE_PCT = 0.40

# Trois positions ouvertes dans _virtual_portfolio (US, XMR, ZBT).
THREE_POSITIONS_QTY_USD = [135.0, 135.0, 135.0]  # 405.0 au total


def _import_display_metrics():
    """Import differe : garde l'echec au niveau du TEST, jamais de la COLLECTE.

    Une ImportError au niveau module ferait grimper collection_errors et
    violerait INV-HEALTH-001 (expected_collection_errors = 1).
    """
    from observability.system_snapshot import compute_display_portfolio_metrics

    return compute_display_portfolio_metrics


# ---------------------------------------------------------------- ROUGE (OBS-001)


def test_display_exposure_is_nonzero_with_open_positions():
    """ROUGE ATTENDU — devient vert avec OBS-002.

    Avec trois positions ouvertes totalisant 405 $ sur un capital de 674.47 $,
    l'exposition d'affichage ne peut pas valoir 0.
    """
    compute = _import_display_metrics()
    m = compute(
        capital=OBSERVED_CAPITAL,
        positions_qty_usd=THREE_POSITIONS_QTY_USD,
        max_exposure_pct=MAX_EXPOSURE_PCT,
    )
    assert m.portfolio_exposure_pct > 0.0, (
        "exposition d'affichage nulle alors que 3 positions sont ouvertes — "
        "c'est le bug OBS/advisor_loop.py:6786"
    )
    expected = sum(THREE_POSITIONS_QTY_USD) / OBSERVED_CAPITAL * 100.0
    assert m.portfolio_exposure_pct == pytest.approx(expected, abs=0.1)


def test_display_cash_is_consistent_with_exposure():
    """ROUGE ATTENDU — paper_cash et free_cash doivent refleter le deploye.

    Le panneau affichait paper_cash = 674.47 (soit 100 % liquide) ET
    free_cash = 269.79 simultanement : deux definitions du cash qui se
    contredisent, parce que free_cash venait du gate aveugle.
    """
    compute = _import_display_metrics()
    deployed = sum(THREE_POSITIONS_QTY_USD)
    m = compute(
        capital=OBSERVED_CAPITAL,
        positions_qty_usd=THREE_POSITIONS_QTY_USD,
        max_exposure_pct=MAX_EXPOSURE_PCT,
    )
    assert m.paper_cash == pytest.approx(OBSERVED_CAPITAL - deployed, abs=0.01)
    assert m.free_cash != pytest.approx(
        OBSERVED_FREE_CASH_BLIND, abs=0.01
    ), "free_cash vaut encore la valeur du gate aveugle (capital x 0.40 - 0)"
    assert m.free_cash == pytest.approx(
        max(0.0, OBSERVED_CAPITAL * MAX_EXPOSURE_PCT - deployed), abs=0.01
    )


def test_display_metrics_fall_back_to_zero_without_positions():
    """ROUGE ATTENDU — sans position, les metriques restent coherentes.

    Garantit que le correctif OBS-002 ne casse pas le mode non-paper, ou
    aucune position n'est ouverte.
    """
    compute = _import_display_metrics()
    m = compute(
        capital=OBSERVED_CAPITAL,
        positions_qty_usd=[],
        max_exposure_pct=MAX_EXPOSURE_PCT,
    )
    assert m.portfolio_exposure_pct == 0.0
    assert m.paper_cash == pytest.approx(OBSERVED_CAPITAL, abs=0.01)
    assert m.free_cash == pytest.approx(OBSERVED_FREE_CASH_BLIND, abs=0.01)


# ------------------------------------------------------- GARDE VERTE (INV-2)


def test_decision_verdict_unchanged_guard():
    """GARDE INV-2 — DOIT RESTER VERTE.

    Fige le verdict de check_new_trade pour des entrees fixees. Si ce test
    rougit apres un ticket NON GATED, c'est que le comportement de DECISION a
    change : reset d'epoque non autorise, incident a remonter immediatement.

    Ce test n'appelle PAS le chemin d'affichage : il verrouille le moteur.
    """
    from quant_hedge_ai.agents.risk.portfolio_brain import PortfolioBrain

    brain = PortfolioBrain(total_capital=OBSERVED_CAPITAL)

    # Portefeuille vide : reproduit exactement ce que voit le gate aujourd'hui.
    verdict = brain.check_new_trade(
        symbol="BTC/USDT",
        action="BUY",
        size_usd=50.0,
        regime="sideways",
        open_positions=[],
        leverage=1,
        conviction_score=70.0,
    )

    assert (
        verdict.allowed is True
    ), "le verdict de reference a change — INV-2 potentiellement viole"
    assert verdict.size_factor == pytest.approx(1.0, abs=1e-9)

    health = brain.portfolio_health([])
    assert health["total_exposure_pct"] == pytest.approx(0.0, abs=1e-9)
    assert health["n_positions"] == 0
    # La preuve numerique du diagnostic, figee comme reference.
    assert health["free_capital"] == pytest.approx(OBSERVED_FREE_CASH_BLIND, abs=0.01)
    assert health["capital"] == pytest.approx(OBSERVED_CAPITAL, abs=0.01)
