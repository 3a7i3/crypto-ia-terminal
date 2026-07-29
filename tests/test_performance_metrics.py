"""
Bibliothèque canonique des KPI — INV-METRIC-001.

Contexte (audit empirique n°1, 2026-07-28) : quatre formules coexistaient sous
le nom « Sharpe », et deux conventions de win-rate sous le nom « win rate ».
Un rapport pouvait donc citer « Sharpe = -0.11 » et un autre « Sharpe = -1.61 »
en décrivant la même population, sans qu'aucun test ne le signale.

Invariants verrouillés ici :
  METRIC-01  chaque variante de Sharpe reste distincte et nommée
  METRIC-02  le refactor reproduit BIT À BIT les formules historiques des
             deux scripts de gate (aucun seuil déplacé sans ADR)
  METRIC-03  le drawdown est additif en USD et dépend de la base de capital
  METRIC-04  la convention de win-rate est explicite, jamais implicite
  METRIC-05  la friction est mesurée par différence, sans lire de config
  METRIC-06  INV-FRICTION-001 : marge = edge brut - friction, verdict binaire
"""

from __future__ import annotations

import math

import pytest

from system.performance_metrics import (
    SHARPE_VARIANTS,
    compute_snapshot,
    expectancy,
    friction_floor,
    friction_rate,
    gross_edge_rate,
    max_drawdown_additive,
    net_edge_rate,
    profit_factor,
    sharpe_annualized,
    sharpe_per_trade,
    stdev,
    t_statistic,
    win_rate,
)

# Série volontairement asymétrique : moyenne négative, un gros gagnant, des
# perdants nombreux — la forme réelle du dataset canonique V4.
_PCTS = [0.02, -0.01, -0.03, 0.10, -0.02, -0.015, 0.005, -0.04]
_USDS = [0.19, -0.12, -0.32, 0.98, -0.22, -0.17, 0.03, -0.42]


def _legacy_burnin_sharpe(pnl_pcts: list[float]) -> float:
    """Formule EXACTE de burnin_calibration_v3 avant le refactor."""
    if len(pnl_pcts) < 2:
        return 0.0
    mean_r = sum(pnl_pcts) / len(pnl_pcts)
    variance = sum((r - mean_r) ** 2 for r in pnl_pcts) / len(pnl_pcts)
    std_r = math.sqrt(variance) if variance > 0 else 0
    return round(mean_r / std_r * math.sqrt(252), 2) if std_r > 0 else 0.0


def _legacy_prelive_sharpe(pcts: list[float]) -> float:
    """Formule EXACTE de la gate B de prelive_gate avant le refactor."""
    n = len(pcts)
    mean_p = sum(pcts) / n if n else 0
    var_p = sum((p - mean_p) ** 2 for p in pcts) / n if n > 1 else 0
    std_p = math.sqrt(var_p) if var_p > 0 else 0
    return mean_p / std_p if std_p > 0 else 0.0


def _legacy_max_dd(pnls: list[float], base: float) -> float:
    equity = [base]
    for p in pnls:
        equity.append(equity[-1] + p)
    peak, max_dd = equity[0], 0.0
    for e in equity:
        if e > peak:
            peak = e
        if peak > 0:
            dd = (peak - e) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


# ── METRIC-01 ─────────────────────────────────────────────────────────────────


def test_metric01_les_quatre_variantes_sont_distinctes():
    """Quatre noms, quatre valeurs : aucune n'est un alias d'une autre."""
    values = {name: fn(_PCTS) for name, fn in SHARPE_VARIANTS.items()}
    assert len(set(round(v, 6) for v in values.values())) == len(values)


def test_metric01_annualisation_est_un_facteur_pur():
    """Le Sharpe annualisé est exactement le Sharpe par trade × √252."""
    assert sharpe_annualized(_PCTS, ddof=0) == pytest.approx(
        sharpe_per_trade(_PCTS, ddof=0) * math.sqrt(252)
    )


def test_metric01_ddof_change_la_valeur_et_doit_etre_explicite():
    assert stdev(_PCTS, ddof=0) != stdev(_PCTS, ddof=1)
    with pytest.raises(TypeError):
        stdev(_PCTS)  # type: ignore[call-arg]


def test_metric01_t_student_repond_a_une_question_de_signe():
    """t = mean / (stdev_{ddof=1}/√n) — jamais égal au Sharpe par trade."""
    n = len(_USDS)
    attendu = (sum(_USDS) / n) / (stdev(_USDS, ddof=1) / math.sqrt(n))
    assert t_statistic(_USDS) == pytest.approx(attendu)
    assert t_statistic(_USDS) != pytest.approx(sharpe_per_trade(_USDS, ddof=1))


# ── METRIC-02 : verrou de non-régression sur les formules historiques ──────────


def test_metric02_sharpe_burnin_identique_a_la_formule_historique():
    assert round(sharpe_annualized(_PCTS, ddof=0), 2) == _legacy_burnin_sharpe(_PCTS)


def test_metric02_sharpe_gate_b_identique_a_la_formule_historique():
    assert sharpe_per_trade(_PCTS, ddof=0) == pytest.approx(
        _legacy_prelive_sharpe(_PCTS)
    )


def test_metric02_drawdown_identique_a_la_formule_historique():
    for base in (100.0, 677.07, 1000.0):
        assert max_drawdown_additive(_USDS, base) == pytest.approx(
            _legacy_max_dd(_USDS, base)
        )


def test_metric02_win_rate_et_pf_identiques_aux_formules_historiques():
    wins = [p for p in _USDS if p > 0]
    assert win_rate(_USDS, zero_is_win=False) * 100 == pytest.approx(
        len(wins) / len(_USDS) * 100
    )
    gross_win = sum(wins)
    gross_loss = abs(sum(p for p in _USDS if p < 0))
    assert profit_factor(_USDS) == pytest.approx(gross_win / gross_loss)


# ── METRIC-03 ─────────────────────────────────────────────────────────────────


def test_metric03_drawdown_depend_de_la_base_de_capital():
    """Même série, deux bases : deux drawdowns. La base est donc un paramètre.

    Piège réel : `_PAPER_CAPITAL` est figé à l'import de `infra.wallet_sync`
    avec un défaut de 100 alors que `.env` porte 1000 — un ordre d'import
    défavorable divise le drawdown par dix face à un seuil de gate à 10 %.
    Raison pour laquelle ce module n'a AUCUN défaut de capital.
    """
    assert max_drawdown_additive(_USDS, 100.0) > max_drawdown_additive(_USDS, 1000.0)


def test_metric03_drawdown_est_nul_sur_serie_monotone_croissante():
    assert max_drawdown_additive([0.1, 0.2, 0.3], 1000.0) == 0.0


def test_metric03_drawdown_ignore_la_composition():
    """Additif : deux pertes de 1 USD font -2 USD, pas (1-x)² de capital."""
    assert max_drawdown_additive([-1.0, -1.0], 1000.0) == pytest.approx(2.0 / 1000.0)


# ── METRIC-04 ─────────────────────────────────────────────────────────────────


def test_metric04_convention_win_rate_est_obligatoire():
    with pytest.raises(TypeError):
        win_rate(_USDS)  # type: ignore[call-arg]


def test_metric04_le_zero_bascule_le_taux():
    pnls = [1.0, 0.0, -1.0, -1.0]
    assert win_rate(pnls, zero_is_win=True) == 0.5
    assert win_rate(pnls, zero_is_win=False) == 0.25


def test_metric04_serie_vide_ne_leve_pas():
    """Un outil de mesure ne meurt pas sur une population vide."""
    assert win_rate([], zero_is_win=True) == 0.0
    assert profit_factor([]) == 0.0
    assert expectancy([]) == 0.0
    assert max_drawdown_additive([], 1000.0) == 0.0
    assert sharpe_per_trade([], ddof=0) == 0.0
    assert t_statistic([]) == 0.0


def test_metric04_profit_factor_infini_sans_perte():
    assert profit_factor([1.0, 2.0]) == math.inf
    assert profit_factor([-1.0, -2.0]) == 0.0


# ── METRIC-05 / METRIC-06 : INV-FRICTION-001 ──────────────────────────────────

# size × pnl_pct − pnl_usd = frais. Ici 10 × 0.02 − 0.19 = 0.01 → 0.10 %.
_TRADES = [
    {"size_usd": 10.0, "pnl_pct": 0.02, "pnl_usd": 0.19},
    {"size_usd": 10.0, "pnl_pct": -0.01, "pnl_usd": -0.12},
]


def test_metric05_friction_mesuree_par_difference():
    """Aucune constante de frais lue : la friction est déduite des trades."""
    assert friction_rate(_TRADES) == pytest.approx((0.001 + 0.002) / 2)


def test_metric05_friction_ignore_les_trades_sans_taille():
    assert friction_rate([{"size_usd": 0.0, "pnl_pct": 1.0, "pnl_usd": 1.0}]) == 0.0
    assert friction_rate([{"pnl_pct": "n/a", "pnl_usd": None}]) == 0.0


def test_metric05_edges_brut_et_net_sont_distincts():
    assert gross_edge_rate(_TRADES) == pytest.approx((0.02 - 0.01) / 2)
    assert net_edge_rate(_TRADES) == pytest.approx((0.019 - 0.012) / 2)
    assert gross_edge_rate(_TRADES) > net_edge_rate(_TRADES)


def test_metric06_plancher_non_franchi_quand_edge_brut_sous_friction():
    """Edge brut 0.05 % < friction 0.15 % → condamné, quel que soit le sizing."""
    trades = [{"size_usd": 10.0, "pnl_pct": 0.0005, "pnl_usd": 0.0005 * 10 - 0.015}]
    floor = friction_floor(trades)
    assert floor.friction_rate == pytest.approx(0.0015)
    assert floor.margin < 0
    assert not floor.covers_friction
    assert floor.verdict == "PLANCHER_NON_FRANCHI"


def test_metric06_plancher_franchi_quand_edge_brut_depasse_friction():
    trades = [{"size_usd": 10.0, "pnl_pct": 0.01, "pnl_usd": 0.01 * 10 - 0.015}]
    floor = friction_floor(trades)
    assert floor.margin > 0
    assert floor.covers_friction
    assert floor.verdict == "EDGE_COUVRE_FRICTION"


def test_metric06_le_verdict_est_independant_de_la_taille_de_position():
    """Doubler la taille ne change ni la marge ni le verdict — c'est l'énoncé.

    Si ce test échoue, INV-FRICTION-001 n'est plus « indépendant de
    l'architecture » et l'invariant lui-même est faux.
    """
    petit = [{"size_usd": 10.0, "pnl_pct": 0.001, "pnl_usd": 0.001 * 10 - 0.02}]
    grand = [{"size_usd": 1000.0, "pnl_pct": 0.001, "pnl_usd": 0.001 * 1000 - 2.0}]
    assert friction_floor(petit).margin == pytest.approx(friction_floor(grand).margin)
    assert friction_floor(petit).verdict == friction_floor(grand).verdict


# ── Instantané complet ────────────────────────────────────────────────────────


def test_snapshot_expose_les_deux_conventions_et_les_variantes():
    trades = [
        {"size_usd": 10.0, "pnl_pct": p, "pnl_usd": u} for p, u in zip(_PCTS, _USDS)
    ]
    snap = compute_snapshot(trades, base_capital=1000.0)
    assert snap.n == len(trades)
    assert snap.win_rate <= snap.win_rate_zero_is_win
    assert "per_trade_ddof0" in snap.sharpe
    assert "annualized_252_ddof0" in snap.sharpe
    assert "t_student_pnl_usd" in snap.sharpe
    assert snap.friction is not None
    assert snap.total_pnl_usd == pytest.approx(sum(_USDS))
