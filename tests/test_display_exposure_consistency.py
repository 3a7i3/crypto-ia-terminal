"""tests/test_display_exposure_consistency.py — OBS-001

Tests de régression pour le bug « exposition d'affichage nulle malgré des
positions réelles » + garde INV-2 et INV-5.

Séquence d'écriture exigée par OBS-001 :
  1. TEST 2 (garde INV-2) écrit EN PREMIER — vert sur main inchangé.
  2. TEST 1 (rouge) — rouge pour la bonne raison (exposition == 0).
  3. TEST 3 (INV-5 / mode non-paper).
  4. TEST 4 (INV-1 / aucun effet de bord).

TEST 1 est marqué xfail(strict=True) : il DOIT échouer tant que OBS-002 n'a
pas corrigé le builder CYCLE. Dès que OBS-002 sera livré et que l'assertion
passera, pytest lèvera un XPASS → rappel automatique de retirer le marqueur.

Règles de fixture (risque de non-déterminisme évité) :
  - Aucun appel réseau.
  - Aucun appel à time.time() avec variance entre exécutions.
  - Aucun fichier créé ou modifié en dehors de /tmp.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub des modules absents en environnement CI (dotenv, advisor_runtime_adapters)
# avant tout import du module de production.  Le stub ne remplace jamais un
# module déjà présent dans sys.modules.
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for _missing in ("dotenv", "advisor_runtime_adapters"):
    if _missing not in sys.modules:
        sys.modules[_missing] = MagicMock()

# ---------------------------------------------------------------------------
# Imports testés
# ---------------------------------------------------------------------------

# _display_position_summary est une fonction module-level dans core/advisor_loop.py.
from core.advisor_loop import _display_position_summary  # noqa: E402
from quant_hedge_ai.agents.risk.portfolio_brain import PortfolioBrain  # noqa: E402

# ---------------------------------------------------------------------------
# Doubles de test (aucun réseau, aucune dépendance externe)
# ---------------------------------------------------------------------------


@dataclass
class _FakeOpenPositionSummary:
    """Copie minimale de OpenPositionSummary de mexc_simulator."""

    symbol: str
    side: str
    entry_price: float
    live_pnl_pct: float
    opened_ts: float
    current_price: float = 0.0
    live_pnl_usd: float = 0.0
    qty_usd: float = 0.0
    tp_price: float = 0.0
    sl_price: float = 0.0


@dataclass
class _FakeOpenPositionsSummary:
    """Copie minimale de OpenPositionsSummary de mexc_simulator."""

    n_open: int
    unrealized_pnl_usd: float
    positions: list = field(default_factory=list)


class _FakeVirtualPortfolio:
    """Double de MexcSimulator peuplé de K positions connues.

    Pas de réseau, pas de lock, pas de thread. Suffisant pour tester
    _display_position_summary sans démarrer la boucle complète.
    """

    def __init__(self, positions: list[_FakeOpenPositionSummary]) -> None:
        self._positions_list = positions

    def get_open_positions_summary(self) -> _FakeOpenPositionsSummary:
        return _FakeOpenPositionsSummary(
            n_open=len(self._positions_list),
            unrealized_pnl_usd=sum(p.live_pnl_usd for p in self._positions_list),
            positions=list(self._positions_list),
        )


def _make_three_positions() -> list[_FakeOpenPositionSummary]:
    """Trois positions ouvertes avec notional connu (100 + 100 + 50 USD)."""
    ts = 1_700_000_000.0  # timestamp fixe — pas de time.time()
    return [
        _FakeOpenPositionSummary(
            symbol="BTCUSDT",
            side="BUY",
            entry_price=30_000.0,
            live_pnl_pct=0.5,
            opened_ts=ts,
            qty_usd=100.0,
            live_pnl_usd=0.50,
        ),
        _FakeOpenPositionSummary(
            symbol="BNBUSDT",
            side="BUY",
            entry_price=300.0,
            live_pnl_pct=-0.2,
            opened_ts=ts,
            qty_usd=100.0,
            live_pnl_usd=-0.20,
        ),
        _FakeOpenPositionSummary(
            symbol="ETHUSDT",
            side="SELL",
            entry_price=1_800.0,
            live_pnl_pct=1.0,
            opened_ts=ts,
            qty_usd=50.0,
            live_pnl_usd=0.50,
        ),
    ]


def _empty_pb_health(capital: float = 674.47) -> dict:
    """pb_health produit par PortfolioBrain.portfolio_health([]) — pos_manager vide."""
    brain = PortfolioBrain(total_capital=capital)
    return brain.portfolio_health([])


# ---------------------------------------------------------------------------
# TEST 2 — VERT DE GARDE  « INV-2 : la décision ne bouge pas »
#
# Écrit EN PREMIER (ordre OBS-001 §Plan d'action, étape 4).
# Ce test DOIT être vert sur main inchangé et rester vert après chaque ticket
# de PHASE_01. Si ce test casse, le ticket est refusé (ADR-0007, CLAUDE.md).
# ---------------------------------------------------------------------------


# Référence figée : cas d'entrée et verdict attendu pour check_new_trade.
# Enregistrés une fois pour toutes ; aucun aléatoire, aucune horloge.
_CHECK_NEW_TRADE_REFERENCE: list[dict] = [
    # Cas A — trade autorisé (exposition basse, capital suffisant)
    {
        "symbol": "BTCUSDT",
        "action": "BUY",
        "size_usd": 50.0,
        "regime": "TRENDING",
        "open_positions": [],
        "leverage": 1,
        "conviction_score": 75.0,
        "expected_allowed": True,
        "expected_reason_contains": None,  # pas de raison de refus attendue
    },
    # Cas B — exposition totale dépassée (size_usd dépasse 40 % du capital)
    {
        "symbol": "ETHUSDT",
        "action": "BUY",
        "size_usd": 2_000.0,
        "regime": "VOLATILE",
        "open_positions": [],
        "leverage": 1,
        "conviction_score": 60.0,
        "expected_allowed": False,
        "expected_reason_contains": "Exposition totale trop élevée",
    },
    # Cas C — max positions atteint (5 positions fictives déjà présentes)
    {
        "symbol": "SOLUSDT",
        "action": "BUY",
        "size_usd": 30.0,
        "regime": "MEAN_REVERSION",
        "open_positions": [
            # 5 positions ouvertes simulées avec des SimpleNamespace (aucun réseau)
            *[
                type("FakePos", (), {
                    "size_usd": 50.0,
                    "symbol": f"FAKE{i}",
                    "regime": "MEAN_REVERSION",
                    "pnl_usd": 0.0,
                    "closed": False,
                    "leverage": 1,
                    "side": "BUY",
                })()
                for i in range(5)
            ]
        ],
        "leverage": 1,
        "conviction_score": 80.0,
        "expected_allowed": False,
        "expected_reason_contains": "Max positions atteint",
    },
]


class TestGardeINV2:
    """TEST 2 — garde INV-2 : le verdict de check_new_trade est stable."""

    def test_check_new_trade_verdict_stable(self) -> None:
        """Le verdict ET le motif de refus sont identiques à la référence figée.

        Ce test est la seule preuve exécutable que N n'est pas remis à zéro :
        si check_new_trade change de comportement, le verdict change, le test
        casse, le ticket est refusé.
        """
        brain = PortfolioBrain(total_capital=1_000.0)

        for case in _CHECK_NEW_TRADE_REFERENCE:
            verdict = brain.check_new_trade(
                symbol=case["symbol"],
                action=case["action"],
                size_usd=case["size_usd"],
                regime=case["regime"],
                open_positions=case["open_positions"],
                leverage=case["leverage"],
                conviction_score=case["conviction_score"],
            )

            assert verdict.allowed == case["expected_allowed"], (
                f"[INV-2] Verdict inattendu pour {case['symbol']} "
                f"(size={case['size_usd']}): "
                f"attendu allowed={case['expected_allowed']}, "
                f"obtenu allowed={verdict.allowed}, raison={verdict.reason!r}"
            )

            if case["expected_reason_contains"] is not None:
                assert case["expected_reason_contains"] in (verdict.reason or ""), (
                    f"[INV-2] Motif de refus inattendu pour {case['symbol']}: "
                    f"attendu contenant {case['expected_reason_contains']!r}, "
                    f"obtenu {verdict.reason!r}"
                )


# ---------------------------------------------------------------------------
# TEST 1 — ROUGE ATTENDU  « exposition d'affichage incohérente »
#
# Marqué xfail(strict=True) : DOIT échouer jusqu'à OBS-002.
# Dès qu'OBS-002 corrigera le builder CYCLE (source → _virtual_portfolio),
# ce test deviendra XPASS et rappellera de retirer le marqueur.
#
# L'échec doit citer l'exposition nulle — pas une erreur d'import ni de fixture.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "OBS-001 — BUG CONNU non corrigé : _display_position_summary retourne "
        "n_open depuis _virtual_portfolio MAIS l'exposition affichée provient de "
        "pb_health calculé sur pos_manager VIDE. "
        "Ce test sera vert après OBS-002 (correction du builder CYCLE). "
        "Si ce test passe sans modification du builder, retirer le marqueur xfail."
    ),
)
class TestBugExpositionAffichageNulle:
    """TEST 1 — ROUGE : K positions dans _virtual_portfolio ⇒ exposition == 0."""

    def test_n_open_et_exposition_coherents(self) -> None:
        """Avec 3 positions dans _virtual_portfolio et pos_manager vide,
        l'exposition affichée DOIT être > 0.

        Aujourd'hui elle vaut 0 car pb_health est produit par portfolio_health([])
        (pos_manager vide). Le panneau affiche simultanément « Positions: 3 »
        et « Portfolio Exposure: 0.0 % » — incohérence documentée dans
        PHASE_01.md et RECOVERY.md.
        """
        capital = 674.47
        vp = _FakeVirtualPortfolio(_make_three_positions())
        pb_health = _empty_pb_health(capital=capital)

        n_open, unrealized_pnl = _display_position_summary(vp, pb_health)

        assert n_open == 3, (
            f"[OBS-001] n_open attendu=3, obtenu={n_open}"
        )

        # La ligne ci-dessous ÉCHOUE aujourd'hui (exposition == 0).
        # Preuve numérique du bug : free_capital = 674.47 * 0.40 - 0 = 269.79
        # ce qui confirme total_exposure_usd = 0 (pos_manager vide).
        #
        # Après OBS-002, _display_position_summary devra dériver l'exposition
        # de _virtual_portfolio ; l'assertion deviendra vraie.
        total_notional = sum(p.qty_usd for p in _make_three_positions())  # 250 USD
        expected_exposure_pct = total_notional / capital  # ≈ 0.371 = 37.1 %

        # L'exposition dans pb_health est en % déjà (×100) — voir portfolio_brain:648
        actual_exposure_pct = pb_health.get("total_exposure_pct", 0.0) / 100.0

        assert actual_exposure_pct > 0, (
            f"[OBS-001] BUG CONFIRMÉ — exposition d'affichage nulle malgré "
            f"{n_open} positions ouvertes dans _virtual_portfolio. "
            f"Exposition obtenue={actual_exposure_pct:.1%}, "
            f"exposition attendue≈{expected_exposure_pct:.1%}. "
            f"Cause : pb_health produit par portfolio_health([]) (pos_manager vide). "
            f"Correction : OBS-002 — builder CYCLE doit lire _virtual_portfolio."
        )


# ---------------------------------------------------------------------------
# TEST 3 — VERT  « INV-5 : mode non-paper inchangé »
# ---------------------------------------------------------------------------


class TestModeNonPaper:
    """TEST 3 — mode non-paper : _virtual_portfolio absent ⇒ fallback pb_health."""

    def test_fallback_vers_pb_health_quand_pas_de_virtual_portfolio(self) -> None:
        """Sans _virtual_portfolio, _display_position_summary retourne les
        valeurs de pb_health — comportement identique à l'existant (INV-5).
        """
        # pb_health simulant 2 positions ouvertes et un PnL connu
        pb_health = {
            "n_positions": 2,
            "open_pnl_usd": 12.50,
            "total_exposure_pct": 25.0,
            "capital": 500.0,
            "free_capital": 75.0,
        }

        n_open, pnl = _display_position_summary(None, pb_health)

        assert n_open == 2, (
            f"[INV-5] Fallback pb_health attendu n_open=2, obtenu={n_open}"
        )
        assert pnl == pytest.approx(12.50, abs=0.01), (
            f"[INV-5] Fallback pb_health attendu pnl=12.50, obtenu={pnl}"
        )

    def test_fallback_avec_pb_health_vide(self) -> None:
        """pb_health vide ({}) → 0 positions, 0 PnL — pas d'exception."""
        n_open, pnl = _display_position_summary(None, {})

        assert n_open == 0, f"[INV-5] pb_health vide attendu n_open=0, obtenu={n_open}"
        assert pnl == 0.0, f"[INV-5] pb_health vide attendu pnl=0.0, obtenu={pnl}"

    def test_virtual_portfolio_en_erreur_tombe_en_fallback(self) -> None:
        """Si get_open_positions_summary() lève une exception, fallback pb_health."""

        class _BrokenVP:
            def get_open_positions_summary(self) -> Any:
                raise RuntimeError("réseau indisponible")

        pb_health = {"n_positions": 1, "open_pnl_usd": 5.0}
        n_open, pnl = _display_position_summary(_BrokenVP(), pb_health)

        assert n_open == 1, (
            f"[INV-5] Fallback après exception attendu n_open=1, obtenu={n_open}"
        )


# ---------------------------------------------------------------------------
# TEST 4 — VERT  « INV-1 : aucun effet de bord »
# ---------------------------------------------------------------------------


class TestAucunEffetDeBord:
    """TEST 4 — INV-1 : _display_position_summary est une fonction pure d'affichage.

    Elle ne doit créer, modifier ni ouvrir aucun fichier de données.
    """

    def test_aucun_fichier_cree_ou_modifie(self, tmp_path: Any) -> None:
        """Appel de _display_position_summary : aucun fichier créé dans tmp_path."""
        vp = _FakeVirtualPortfolio(_make_three_positions())
        pb_health = _empty_pb_health()

        before = set(tmp_path.iterdir())
        _display_position_summary(vp, pb_health)
        after = set(tmp_path.iterdir())

        assert before == after, (
            f"[INV-1] Des fichiers ont été créés ou modifiés : {after - before}"
        )

    def test_appels_successifs_idempotents(self) -> None:
        """Deux appels identiques retournent le même résultat (pas d'état interne)."""
        vp = _FakeVirtualPortfolio(_make_three_positions())
        pb_health = _empty_pb_health()

        result_1 = _display_position_summary(vp, pb_health)
        result_2 = _display_position_summary(vp, pb_health)

        assert result_1 == result_2, (
            f"[INV-1] Résultats non idempotents : {result_1!r} ≠ {result_2!r}"
        )
