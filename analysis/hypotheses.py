"""
analysis/hypotheses.py — Hypothèses de trading formalisées comme tests falsifiables.

Chaque hypothèse est un test statistique avec :
  - Description claire et falsifiable
  - Seuil N minimum pour être concluant
  - p-value (test de signe ou binomial)
  - Effect size (Cohen's d simplifié)
  - Intervalle de confiance sur le win rate (Wilson)
  - Verdict : ACCEPTÉE / REJETÉE / NON CONCLUANT

Usage :
    from analysis.hypotheses import run_all_hypotheses
    from analysis.base import load_trades

    trades = load_trades("databases/paper_trades.jsonl")
    results = run_all_hypotheses(trades)
"""

from __future__ import annotations

import math

from analysis.base import HypothesisResult, Trade, expectancy, profit_factor, win_rate

# ── Helpers statistiques ──────────────────────────────────────────────────────


def _wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalle de confiance Wilson sur le win rate (z=1.96 → 95%)."""
    if n == 0:
        return (0.0, 0.0)
    p_hat = successes / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denom
    return (round(max(0, center - margin), 3), round(min(1, center + margin), 3))


def _binomial_p_value(successes: int, n: int, p0: float = 0.5) -> float:
    """p-value test binomial exact (H0: win_rate = p0)."""
    if n == 0:
        return 1.0
    # Approximation normale pour N >= 20
    if n >= 20:
        std = math.sqrt(n * p0 * (1 - p0))
        if std == 0:
            return 1.0
        z = abs(successes - n * p0) / std
        # p-value bilatéral — approximation
        p = 2 * (1 - _norm_cdf(z))
        return round(p, 4)
    # Exact pour N < 20 (somme de la queue)
    from math import comb, factorial  # noqa: F401

    if successes <= n * p0:
        # queue basse
        p = sum(
            comb(n, k) * (p0**k) * ((1 - p0) ** (n - k)) for k in range(successes + 1)
        )
    else:
        # queue haute
        p = sum(
            comb(n, k) * (p0**k) * ((1 - p0) ** (n - k))
            for k in range(successes, n + 1)
        )
    return round(min(1.0, 2 * p), 4)


def _norm_cdf(z: float) -> float:
    """CDF normale standard (approximation Abramowitz & Stegun)."""
    t = 1 / (1 + 0.2316419 * abs(z))
    poly = t * (
        0.319381530
        + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429)))
    )
    p = 1 - (1 / math.sqrt(2 * math.pi)) * math.exp(-(z**2) / 2) * poly
    return p if z >= 0 else 1 - p


def _cohen_d(group_a: list[float], group_b: list[float]) -> float | None:
    """Cohen's d — effect size entre deux groupes."""
    if len(group_a) < 2 or len(group_b) < 2:
        return None
    mean_a = sum(group_a) / len(group_a)
    mean_b = sum(group_b) / len(group_b)
    var_a = sum((x - mean_a) ** 2 for x in group_a) / (len(group_a) - 1)
    var_b = sum((x - mean_b) ** 2 for x in group_b) / (len(group_b) - 1)
    pooled_std = math.sqrt((var_a + var_b) / 2)
    if pooled_std == 0:
        return None
    return round((mean_a - mean_b) / pooled_std, 3)


def _make_result(
    name: str,
    description: str,
    pnls: list[float],
    min_n: int = 50,
    notes: str = "",
) -> HypothesisResult:
    """Construit un HypothesisResult complet depuis une liste de PnL."""
    n = len(pnls)
    if n < min_n:
        return HypothesisResult(
            name=name,
            description=description,
            n=n,
            accepted=None,
            min_n_required=min_n,
            notes=f"Non concluant — N={n} < {min_n} requis",
        )
    wins = sum(1 for p in pnls if p > 0)
    pf = profit_factor(pnls)
    wr = win_rate(pnls)
    exp = expectancy(pnls)
    p_val = _binomial_p_value(wins, n, p0=0.5)
    ci = _wilson_ci(wins, n)
    # Acceptée si expectancy < 0 ET p-value < 0.05 (rejet H0 de neutralité)
    # Convention : l'hypothèse est "cette stratégie est perdante"
    accepted = exp is not None and exp < 0 and p_val < 0.05
    return HypothesisResult(
        name=name,
        description=description,
        n=n,
        accepted=accepted,
        pf=pf,
        win_rate=wr,
        expectancy_usd=exp,
        p_value=p_val,
        confidence_interval=ci,
        min_n_required=min_n,
        notes=notes,
    )


# ── Hypothèses ────────────────────────────────────────────────────────────────


def h1_buy_sideways(trades: list[Trade]) -> HypothesisResult:
    """
    H1 : BUY en régime sideways a une expectancy négative.
    Si acceptée → désactiver BUY en sideways ou augmenter le seuil de score.
    """
    subset = [t.pnl_usd for t in trades if t.regime == "sideways" and t.side == "BUY"]
    return _make_result(
        name="H1",
        description="BUY en sideways → expectancy négative",
        pnls=subset,
        min_n=30,
        notes="Confirme ou infirme la thèse de contre-tendance en range",
    )


def h2_sell_bear(trades: list[Trade]) -> HypothesisResult:
    """
    H2 : SELL en bear_trend a une expectancy positive.
    Si rejetée → le régime bear n'est pas exploitable en SELL.
    """
    subset = [
        t.pnl_usd for t in trades if t.regime == "bear_trend" and t.side == "SELL"
    ]
    # Pour H2, on teste l'hypothèse POSITIVE (stratégie gagnante)
    # Acceptée si expectancy > 0 ET p-value < 0.05
    n = len(subset)
    if n < 30:
        return HypothesisResult(
            name="H2",
            description="SELL en bear_trend → expectancy positive",
            n=n,
            accepted=None,
            min_n_required=30,
            notes="Non concluant — données insuffisantes",
        )
    wins = sum(1 for p in subset if p > 0)
    pf = profit_factor(subset)
    wr = win_rate(subset)
    exp = expectancy(subset)
    p_val = _binomial_p_value(wins, n, p0=0.5)
    ci = _wilson_ci(wins, n)
    accepted = exp is not None and exp > 0 and p_val < 0.05
    return HypothesisResult(
        name="H2",
        description="SELL en bear_trend → expectancy positive",
        n=n,
        accepted=accepted,
        pf=pf,
        win_rate=wr,
        expectancy_usd=exp,
        p_value=p_val,
        confidence_interval=ci,
        min_n_required=30,
        notes="Valide la personnalité defensive_short",
    )


def h3_high_score_better(trades: list[Trade], threshold: int = 75) -> HypothesisResult:
    """
    H3 : Score ≥ 75 a une expectancy significativement meilleure que score < 75.
    Si acceptée → le scoring apporte de la valeur prédictive.
    """
    high = [t.pnl_usd for t in trades if t.score >= threshold]
    low = [t.pnl_usd for t in trades if t.score < threshold]
    n_high = len(high)
    n_low = len(low)
    if n_high < 20 or n_low < 20:
        return HypothesisResult(
            name="H3",
            description=f"Score≥{threshold} → expectancy supérieure",
            n=n_high + n_low,
            accepted=None,
            min_n_required=40,
            notes=f"Non concluant — N_high={n_high}, N_low={n_low}",
        )
    exp_high = expectancy(high)
    exp_low = expectancy(low)
    d = _cohen_d(high, low)
    accepted = (
        exp_high is not None
        and exp_low is not None
        and exp_high > exp_low
        and d is not None
        and abs(d) > 0.2
    )
    return HypothesisResult(
        name="H3",
        description=f"Score≥{threshold} → expectancy supérieure",
        n=n_high + n_low,
        accepted=accepted,
        expectancy_usd=exp_high,
        effect_size=d,
        min_n_required=40,
        notes=(
            f"E[score≥{threshold}]={exp_high:.3f}$ vs "
            f"E[score<{threshold}]={exp_low:.3f}$ | Cohen's d={d}"
        ),
    )


def h4_atr_filter(trades: list[Trade], atr_threshold: float = 1.5) -> HypothesisResult:
    """
    H4 : ATR% élevé (≥ seuil) améliore le PF par rapport à ATR% bas.
    Si acceptée → filtrer les entrées sur ATR minimum.
    """
    with_atr = [t for t in trades if t.atr_pct is not None]
    if len(with_atr) < 40:
        return HypothesisResult(
            name="H4",
            description=f"ATR%≥{atr_threshold} → PF supérieur",
            n=len(with_atr),
            accepted=None,
            min_n_required=40,
            notes="Non concluant — atr_pct absent des données ou N insuffisant",
        )
    high_atr = [t.pnl_usd for t in with_atr if t.atr_pct >= atr_threshold]
    low_atr = [t.pnl_usd for t in with_atr if t.atr_pct < atr_threshold]
    pf_high = profit_factor(high_atr)
    pf_low = profit_factor(low_atr)
    d = _cohen_d(high_atr, low_atr) if high_atr and low_atr else None
    accepted = (
        pf_high is not None
        and pf_low is not None
        and isinstance(pf_high, float)
        and isinstance(pf_low, float)
        and pf_high > pf_low
        and d is not None
        and abs(d) > 0.2
    )
    return HypothesisResult(
        name="H4",
        description=f"ATR%≥{atr_threshold} → PF supérieur",
        n=len(with_atr),
        accepted=accepted,
        pf=pf_high,
        effect_size=d,
        min_n_required=40,
        notes=(
            f"PF[ATR≥{atr_threshold}]={pf_high} vs "
            f"PF[ATR<{atr_threshold}]={pf_low} | Cohen's d={d}"
        ),
    )


# ── Runner ────────────────────────────────────────────────────────────────────


def run_all_hypotheses(trades: list[Trade]) -> list[HypothesisResult]:
    """Lance tous les tests d'hypothèses et retourne les résultats."""
    return [
        h1_buy_sideways(trades),
        h2_sell_bear(trades),
        h3_high_score_better(trades),
        h4_atr_filter(trades),
    ]


def print_hypotheses_report(results: list[HypothesisResult]) -> None:
    W = 68
    print(f"\n{'='*W}")
    print("  RAPPORT HYPOTHÈSES STATISTIQUES")
    print(f"{'='*W}")
    for r in results:
        if r.accepted is None:
            icon = "⏳"
            verdict = f"NON CONCLUANT (N={r.n}/{r.min_n_required})"
        elif r.accepted:
            icon = "✅"
            verdict = "ACCEPTÉE"
        else:
            icon = "❌"
            verdict = "REJETÉE"
        print(f"\n  {icon} {r.name} — {r.description}")
        print(f"     Verdict : {verdict}")
        if r.n >= r.min_n_required:
            print(f"     N={r.n} | PF={r.pf} | WR={r.win_rate} | E={r.expectancy_usd}$")
            if r.p_value is not None:
                print(f"     p-value={r.p_value} | CI_95%={r.confidence_interval}")
            if r.effect_size is not None:
                print(f"     Cohen's d={r.effect_size}")
        if r.notes:
            print(f"     Note: {r.notes}")
    print(f"\n{'='*W}\n")


if __name__ == "__main__":
    import sys

    from analysis.base import load_trades

    path = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        trades = load_trades(path)
        results = run_all_hypotheses(trades)
        print_hypotheses_report(results)
    except FileNotFoundError as e:
        print(f"ERREUR: {e}")
        sys.exit(1)
