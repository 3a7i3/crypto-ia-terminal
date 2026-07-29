"""
system/performance_metrics.py — bibliothèque canonique des KPI de performance.

**INV-METRIC-001 : un KPI porte le nom de sa formule.**

`sharpe` n'est pas un nom. Le dépôt a porté *quatre* définitions différentes
sous ce seul mot (audit AUDIT-EMP-001, 2026-07-28) :

| Appelant                  | Formule                           | Valeur (N=121) |
|---------------------------|-----------------------------------|----------------|
| `burnin_calibration_v3`   | mean/pstdev × √252 sur `pnl_pct`  | -1.61          |
| `prelive_gate` gate B     | mean/pstdev sur `pnl_pct`         | -0.1015        |
| audit du 2026-07-28       | mean/stdev × √n sur `pnl_usd`     | -1.574 (t)     |
| `src/backtest/metrics.py` | mean/stdev (ddof=1) sur `returns` | non appelé     |

Ce module **ne tranche aucune** de ces définitions : trancher changerait ce que
le seuil `1.0` de la gate B *mesure*, donc déplacerait le seuil en pratique —
interdit sous gel scientifique sans ADR signé (CLAUDE.md). La décision est
enregistrée et ouverte : `DEC-SHARPE-001`.

Ce que ce module fait, et qui n'exige aucune décision : nommer chaque formule,
les exposer côte à côte, et devenir **l'unique endroit du dépôt où elles sont
écrites**. Un appelant choisit une variante explicitement ; il ne peut plus en
réinventer une par inadvertance.

Contrat d'usage
---------------
1. La population vient du loader unique (`tools.cri_calculator.load_clean_trades`,
   INV-DATASET-001). Ce module ne lit aucun fichier.
2. Aucune fonction n'arrondit. L'arrondi est une décision d'affichage, prise
   par l'appelant, jamais propagée dans un calcul.
3. Les taux sont rendus en **fraction** (0.347), jamais en pourcentage.
   `pnl_pct` du journal est déjà une fraction (0.0251 = +2.51 %).

Usage :
    from system.performance_metrics import compute_snapshot, sharpe_annualized

    snap = compute_snapshot(trades, base_capital=1000.0)
    print(snap.win_rate, snap.profit_factor, snap.sharpe["annualized_252_ddof0"])
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Sequence

__all__ = [
    "mean",
    "stdev",
    "win_rate",
    "profit_factor",
    "expectancy",
    "max_drawdown_additive",
    "sharpe_per_trade",
    "sharpe_annualized",
    "t_statistic",
    "friction_rate",
    "gross_edge_rate",
    "net_edge_rate",
    "friction_floor",
    "SHARPE_VARIANTS",
    "PerformanceSnapshot",
    "FrictionFloor",
    "compute_snapshot",
    "TRADING_PERIODS_PER_YEAR",
]

# Convention héritée : 252 jours de bourse. Notée ici pour que son caractère
# arbitraire soit visible — les paper trades ne sont ni journaliers ni bornés
# aux jours ouvrés (crypto 24/7), et leur durée moyenne varie. Annualiser une
# série *par trade* avec √252 suppose « un trade par jour ouvré », hypothèse
# fausse sur ce dataset. Conservée telle quelle car changer la constante
# déplacerait le Sharpe de burn-in : c'est une décision, pas un nettoyage.
TRADING_PERIODS_PER_YEAR = 252.0


# ── Primitives ────────────────────────────────────────────────────────────────


def mean(values: Sequence[float]) -> float:
    """Moyenne arithmétique. 0.0 sur série vide (jamais d'exception en mesure)."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def stdev(values: Sequence[float], *, ddof: int) -> float:
    """Écart-type. `ddof=0` = population (biaisé), `ddof=1` = échantillon.

    Le choix n'est pas cosmétique : les deux scripts de gate divisaient par `n`
    (ddof=0) alors qu'ils estiment la volatilité d'un processus à partir d'un
    échantillon — `ddof=1` est l'estimateur non biaisé. À N=121 l'écart est de
    0.4 %, négligeable ; à N=20 il ne l'est plus. Le paramètre est obligatoire
    pour qu'aucun appelant ne l'hérite sans le savoir.
    """
    n = len(values)
    if n - ddof <= 0:
        return 0.0
    m = mean(values)
    variance = sum((v - m) ** 2 for v in values) / (n - ddof)
    return math.sqrt(variance) if variance > 0 else 0.0


# ── KPI de résultat ───────────────────────────────────────────────────────────


def win_rate(pnls: Sequence[float], *, zero_is_win: bool) -> float:
    """Fraction de trades gagnants.

    `zero_is_win` est explicite parce que le dépôt portait les deux conventions :
    `burnin_calibration_v3` comptait `pnl >= 0` (aligné sur
    `MexcSimulator._close_position`), `prelive_gate` comptait `pnl > 0`.
    Mesure d'impact sur le dataset canonique du 2026-07-29 (N=121) : **aucun
    trade à `pnl_usd == 0`**, la divergence est donc un NO-OP aujourd'hui.
    Elle est conservée nommée plutôt qu'unifiée d'autorité : le taux nourrit le
    seuil `WR > 45 %` de la gate B, et un seuil ne se déplace pas sans ADR.
    """
    if not pnls:
        return 0.0
    if zero_is_win:
        wins = sum(1 for p in pnls if p >= 0)
    else:
        wins = sum(1 for p in pnls if p > 0)
    return wins / len(pnls)


def profit_factor(pnls: Sequence[float]) -> float:
    """Σ gains / |Σ pertes|. `inf` si aucune perte, 0.0 si aucun gain."""
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    if gross_loss == 0:
        return math.inf if gross_win > 0 else 0.0
    return gross_win / gross_loss


def expectancy(values: Sequence[float]) -> float:
    """Espérance empirique par trade — moyenne, dans l'unité fournie."""
    return mean(values)


def max_drawdown_additive(pnls: Sequence[float], base_capital: float) -> float:
    """Drawdown maximal d'une courbe d'equity **additive** en USD, en fraction.

    Additive et non composée : `pnl_pct` du journal contient des valeurs
    aberrantes (> 100 %) qui font exploser une composition. La base de capital
    est un paramètre — jamais lue ici — parce qu'elle est épinglée à
    `WALLET_PAPER_CAPITAL` par ADR-0007 et que son changement est une décision
    de calibration.

    Piège de composition (AUDIT-EMP-001) : ce KPI n'a de sens que si `pnls`
    provient d'**une seule époque**. Sur les 664 CLOSE toutes époques le
    drawdown était de 33.55 % ; sur les 121 canoniques il tombe sous 1 %. La
    même formule, deux populations, un verdict de gate inversé.
    """
    equity = base_capital
    peak = base_capital
    max_dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        if peak > 0:
            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


# ── Famille Sharpe — quatre noms, aucune décision ─────────────────────────────


def sharpe_per_trade(returns: Sequence[float], *, ddof: int = 0) -> float:
    """Ratio moyenne/écart-type **par trade**, non annualisé.

    C'est la formule de la gate B. Conséquence mesurée : franchir un seuil de
    1.0 exigerait, à volatilité constante sur le dataset actuel, un rendement
    moyen d'environ 4.8 % PAR TRADE. Le seuil `1.0` a manifestement été pensé
    pour un Sharpe annualisé ; la gate est donc structurellement infranchissable
    sur ce critère. Constat mesuré, non tranché (DEC-SHARPE-001).
    """
    s = stdev(returns, ddof=ddof)
    return mean(returns) / s if s > 0 else 0.0


def sharpe_annualized(
    returns: Sequence[float],
    *,
    periods_per_year: float = TRADING_PERIODS_PER_YEAR,
    ddof: int = 0,
) -> float:
    """Sharpe par trade × √periods_per_year — formule de `burnin_calibration_v3`.

    L'annualisation suppose des périodes de longueur homogène. Ce n'est pas le
    cas ici (durées de trade de quelques minutes à 8 h) : la valeur est
    comparable *à elle-même dans le temps*, pas à un Sharpe de marché.
    """
    return sharpe_per_trade(returns, ddof=ddof) * math.sqrt(periods_per_year)


def t_statistic(values: Sequence[float]) -> float:
    """t de Student de H0 : « espérance = 0 » — mean / (stdev_{ddof=1} / √n).

    Seule variante de la famille qui répond à une question falsifiable : « le
    signe de l'espérance est-il distinguable du bruit ? ». Les trois autres
    répondent « quel ratio rendement/risque ? », qui n'est pas un test.
    """
    n = len(values)
    if n < 2:
        return 0.0
    s = stdev(values, ddof=1)
    return mean(values) / (s / math.sqrt(n)) if s > 0 else 0.0


#: Les quatre variantes, nommées, pour affichage côte à côte. Un rapport qui
#: cite « le Sharpe » sans nommer sa clé est un rapport non reproductible.
SHARPE_VARIANTS: Mapping[str, Callable[[Sequence[float]], float]] = {
    "per_trade_ddof0": lambda r: sharpe_per_trade(r, ddof=0),
    "per_trade_ddof1": lambda r: sharpe_per_trade(r, ddof=1),
    "annualized_252_ddof0": lambda r: sharpe_annualized(r, ddof=0),
    "t_student": t_statistic,
}


# ── Friction — INV-FRICTION-001 ───────────────────────────────────────────────


def _trade_friction_rate(trade: Mapping[str, object]) -> float | None:
    """Coût de friction d'un trade, en fraction de la taille engagée.

    Reconstruit par différence, sans lire aucune configuration de frais :
    `MexcSimulator._close_position` écrit `pnl_usd = size × pnl_pct − fees`,
    donc `fees / size = pnl_pct − pnl_usd / size`. Mesurer la friction plutôt
    que la déclarer évite qu'une constante de config divergente la masque.
    """
    try:
        size = float(trade.get("size_usd") or 0.0)  # type: ignore[arg-type]
        gross_pct = float(trade.get("pnl_pct") or 0.0)  # type: ignore[arg-type]
        net_usd = float(trade.get("pnl_usd") or 0.0)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if size <= 0:
        return None
    return gross_pct - net_usd / size


def friction_rate(trades: Iterable[Mapping[str, object]]) -> float:
    """Friction moyenne par trade, en fraction de la taille (0.00194 = 0.194 %)."""
    rates = [r for r in (_trade_friction_rate(t) for t in trades) if r is not None]
    return mean(rates)


def gross_edge_rate(trades: Iterable[Mapping[str, object]]) -> float:
    """Edge BRUT moyen par trade — mouvement de prix seul, hors frais."""
    values = []
    for t in trades:
        try:
            values.append(float(t.get("pnl_pct") or 0.0))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
    return mean(values)


def net_edge_rate(trades: Iterable[Mapping[str, object]]) -> float:
    """Edge NET moyen par trade, en fraction de la taille engagée."""
    values = []
    for t in trades:
        try:
            size = float(t.get("size_usd") or 0.0)  # type: ignore[arg-type]
            net = float(t.get("pnl_usd") or 0.0)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if size > 0:
            values.append(net / size)
    return mean(values)


@dataclass(frozen=True)
class FrictionFloor:
    """Verdict d'INV-FRICTION-001 : l'edge brut couvre-t-il son propre coût ?"""

    n: int
    friction_rate: float
    gross_edge_rate: float
    net_edge_rate: float

    @property
    def margin(self) -> float:
        """Edge brut moins friction. Négatif = condamné par arithmétique."""
        return self.gross_edge_rate - self.friction_rate

    @property
    def covers_friction(self) -> bool:
        return self.margin > 0

    @property
    def verdict(self) -> str:
        return (
            "EDGE_COUVRE_FRICTION" if self.covers_friction else "PLANCHER_NON_FRANCHI"
        )


def friction_floor(trades: Sequence[Mapping[str, object]]) -> FrictionFloor:
    """Plancher d'edge — INV-FRICTION-001.

    Énoncé de l'invariant : *tout modèle dont l'edge brut moyen est inférieur à
    son coût de friction total est condamné à espérance négative, quel que soit
    le money management*. La taille de position, le sizing Kelly, le nombre de
    positions simultanées et la courbe d'equity n'entrent pas dans cette
    comparaison : elle est **indépendante de l'architecture**.

    Corollaire opérationnel : aucune optimisation de sizing, de portefeuille ou
    de sortie ne peut être justifiée tant que `margin <= 0`. Le seul levier
    admissible est l'entrée (edge brut) ou la friction (coûts d'exécution).
    """
    return FrictionFloor(
        n=len(trades),
        friction_rate=friction_rate(trades),
        gross_edge_rate=gross_edge_rate(trades),
        net_edge_rate=net_edge_rate(trades),
    )


# ── Instantané complet ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PerformanceSnapshot:
    """Tous les KPI d'une population, avec les quatre Sharpe côte à côte."""

    n: int
    base_capital: float
    total_pnl_usd: float
    win_rate: float  # convention `pnl_usd > 0`
    win_rate_zero_is_win: float  # convention `pnl_usd >= 0`
    profit_factor: float
    expectancy_usd: float
    expectancy_pct: float
    max_drawdown: float
    sharpe: Mapping[str, float] = field(default_factory=dict)
    friction: FrictionFloor | None = None


def compute_snapshot(
    trades: Sequence[Mapping[str, object]], *, base_capital: float
) -> PerformanceSnapshot:
    """Instantané complet d'une population canonique.

    `trades` doit provenir de `load_clean_trades` (INV-DATASET-001). Aucun
    filtre n'est appliqué ici : ce module mesure ce qu'on lui donne, et c'est
    précisément pour ça qu'il ne doit jamais choisir sa population lui-même.
    """
    pnl_usd: list[float] = []
    pnl_pct: list[float] = []
    for t in trades:
        try:
            pnl_usd.append(float(t.get("pnl_usd") or 0.0))  # type: ignore[arg-type]
            pnl_pct.append(float(t.get("pnl_pct") or 0.0))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue

    return PerformanceSnapshot(
        n=len(pnl_usd),
        base_capital=base_capital,
        total_pnl_usd=sum(pnl_usd),
        win_rate=win_rate(pnl_usd, zero_is_win=False),
        win_rate_zero_is_win=win_rate(pnl_usd, zero_is_win=True),
        profit_factor=profit_factor(pnl_usd),
        expectancy_usd=expectancy(pnl_usd),
        expectancy_pct=expectancy(pnl_pct),
        max_drawdown=max_drawdown_additive(pnl_usd, base_capital),
        sharpe={
            "per_trade_ddof0": sharpe_per_trade(pnl_pct, ddof=0),
            "per_trade_ddof1": sharpe_per_trade(pnl_pct, ddof=1),
            "annualized_252_ddof0": sharpe_annualized(pnl_pct, ddof=0),
            "t_student_pnl_pct": t_statistic(pnl_pct),
            "t_student_pnl_usd": t_statistic(pnl_usd),
        },
        friction=friction_floor(trades),
    )
