"""
tools/score_calibration_audit.py — le score classe-t-il quelque chose ?

**Question scientifique.** Le score 0-100 est utilisé comme *fonction de
classement* : le moteur trie les candidats et n'exécute qu'au-dessus d'un seuil.
Un tel score n'a pas besoin d'être linéairement corrélé au PnL ; il doit
seulement **ordonner**. Un coefficient de Pearson nul ne le condamne donc pas.

Ce module teste l'ordonnancement, pas la linéarité :
  - Spearman ρ (rangs, robuste aux valeurs aberrantes) et Kendall τ-b
  - Information Coefficient par horizon (structure temporelle du signal)
  - AUC de Mann-Whitney (P(score d'un gagnant > score d'un perdant))
  - espérance conditionnelle par tranche + monotonicité des tranches
  - écart haut-vs-bas de distribution, avec test de permutation

**Ce qu'il refuse de faire.** Conclure sans puissance. Trois verdicts distincts,
jamais confondus :

| Verdict                        | Signification                                    |
|--------------------------------|--------------------------------------------------|
| `SIGNAL_DETECTE`               | ordonnancement mesurable, significatif           |
| `ABSENCE_DE_SIGNAL_DETECTABLE` | testé avec puissance suffisante, rien trouvé     |
| `INSTRUMENT_INSUFFISANT`       | le dataset ne peut pas répondre — ni oui, ni non |

Le troisième verdict est le plus important. « Pearson ≈ 0 sur N=121 avec 45 %
des trades au même score » n'est pas une absence de signal : c'est une absence
de mesure. Confondre les deux ferait condamner le score sur un artefact
d'échantillonnage.

**Deux populations, deux questions.**

1. `--trades` : les trades **exécutés** (loader unique, INV-DATASET-001).
   Résultat = PnL réalisé, donc *score ⊗ politique de sortie ⊗ frais*. Un score
   parfait peut y paraître nul si les sorties détruisent l'edge.
2. `--regret` : les candidats **observés** (`databases/regret/regret_horizons_*`,
   source canonique ADR-0018), exécutés ou bloqués. Résultat = rendement
   forward signé à horizon fixe, **sans politique de sortie ni frais**. C'est le
   test du score seul.

Angle mort structurel, énoncé quel que soit le résultat : aucune des deux
populations ne contient d'observation à bas score (bornes mesurées et
rapportées). Le pouvoir discriminant du score n'est donc **testable que dans la
bande haute** — celle où le moteur opère réellement. Toute extrapolation sous
cette borne est hors dataset.

Usage :
    python tools/score_calibration_audit.py
    python tools/score_calibration_audit.py --horizon 1h --json
    python tools/score_calibration_audit.py --trades /chemin/paper_trades.jsonl \\
        --regret /chemin/databases/regret --outcome pnl_pct
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.data_quality import CLEAN_DATA_SINCE_ACTIVE  # noqa: E402
from system.performance_metrics import friction_floor  # noqa: E402
from tools.cri_calculator import load_clean_trades, trades_provenance  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Paramètres de décision de l'instrument ────────────────────────────────────

#: Échelle nominale du score. Sert à mesurer la restriction de domaine : un
#: score qui n'est jamais observé hors de [65, 85] est testé sur 20 % de son
#: échelle nominale, et rien ne permet d'extrapoler au reste.
SCORE_SCALE = 100.0

#: Fraction de l'échelle en dessous de laquelle le domaine est déclaré restreint.
MIN_SUPPORT_RATIO = 0.25

#: Masse maximale admissible sur une seule valeur de score. Au-delà, les rangs
#: sont saturés d'ex æquo et toute corrélation est atténuée par construction.
MAX_TIE_MASS = 0.30

#: |ρ| minimal détectable au-delà duquel on considère que l'instrument ne voit
#: que les très gros effets — donc qu'une absence de détection n'informe pas.
MAX_ACCEPTABLE_RHO_FLOOR = 0.20

ALPHA = 0.05
POWER = 0.80
_Z_ALPHA_2 = 1.959963985
_Z_POWER = 0.841621234

DEFAULT_REGRET_DIR = Path("databases/regret")
DEFAULT_HORIZON = "1h"
HORIZON_ORDER = ["5m", "15m", "30m", "1h", "4h", "12h", "24h"]

VERDICT_SIGNAL = "SIGNAL_DETECTE"
VERDICT_ABSENCE = "ABSENCE_DE_SIGNAL_DETECTABLE"
VERDICT_INSTRUMENT = "INSTRUMENT_INSUFFISANT"


# ── Statistique, sans dépendance externe ──────────────────────────────────────


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _pstdev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    var = sum((v - m) ** 2 for v in values) / len(values)
    return math.sqrt(var) if var > 0 else 0.0


def _sem(values: Sequence[float]) -> float:
    """Erreur-type de la moyenne (estimateur non biaisé, ddof=1)."""
    n = len(values)
    if n < 2:
        return 0.0
    m = _mean(values)
    var = sum((v - m) ** 2 for v in values) / (n - 1)
    return math.sqrt(var / n) if var > 0 else 0.0


def ranks(values: Sequence[float]) -> list[float]:
    """Rangs avec **moyenne des ex æquo** — indispensable ici.

    Le score est discret et fortement concentré : 45 % des trades exécutés
    partagent la valeur 72. Des rangs sans correction d'ex æquo fabriqueraient
    un ordre arbitraire à l'intérieur du mode, et donc une corrélation
    fantôme ou atténuée selon l'ordre de lecture du fichier.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def pearson(x: Sequence[float], y: Sequence[float]) -> float:
    n = len(x)
    if n < 2 or len(y) != n:
        return 0.0
    mx, my = _mean(x), _mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = math.sqrt(sum((a - mx) ** 2 for a in x))
    dy = math.sqrt(sum((b - my) ** 2 for b in y))
    return num / (dx * dy) if dx > 0 and dy > 0 else 0.0


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """ρ de Spearman = Pearson sur les rangs (ex æquo moyennés)."""
    return pearson(ranks(x), ranks(y))


def kendall_tau_b(x: Sequence[float], y: Sequence[float], *, cap: int = 4000) -> float:
    """τ-b de Kendall, O(n²) — échantillonné au-delà de `cap` paires utiles.

    τ-b corrige explicitement les ex æquo dans les deux dimensions, ce qui en
    fait la mesure d'ordonnancement la plus honnête sur un score discret. Le
    coût quadratique est borné par un sous-échantillon déterministe (graine
    fixe) pour rester exécutable sur 18 000 observations.
    """
    n = len(x)
    if n < 2:
        return 0.0
    idx = list(range(n))
    if n > cap:
        rng = random.Random(20260729)
        idx = sorted(rng.sample(idx, cap))
    conc = disc = tx = ty = 0
    for a in range(len(idx)):
        ia = idx[a]
        for b in range(a + 1, len(idx)):
            ib = idx[b]
            dx = x[ia] - x[ib]
            dy = y[ia] - y[ib]
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                tx += 1
            elif dy == 0:
                ty += 1
            elif (dx > 0) == (dy > 0):
                conc += 1
            else:
                disc += 1
    denom = math.sqrt((conc + disc + tx) * (conc + disc + ty))
    return (conc - disc) / denom if denom > 0 else 0.0


def auc_mann_whitney(scores: Sequence[float], labels: Sequence[bool]) -> float:
    """P(score d'un gagnant > score d'un perdant), ex æquo comptés 0.5.

    0.5 = aucun pouvoir discriminant. Insensible aux valeurs extrêmes de PnL,
    contrairement à toute corrélation calculée sur les montants.
    """
    n1 = sum(1 for f in labels if f)
    n0 = len(labels) - n1
    if n1 == 0 or n0 == 0:
        return 0.5
    r = ranks(scores)
    rank_sum_pos = sum(rk for rk, f in zip(r, labels) if f)
    u = rank_sum_pos - n1 * (n1 + 1) / 2.0
    return u / (n1 * n0)


def auc_se_hanley(auc: float, n_pos: int, n_neg: int) -> float:
    """Erreur-type de l'AUC — Hanley & McNeil (1982), forme fermée."""
    if n_pos == 0 or n_neg == 0:
        return 0.0
    q1 = auc / (2.0 - auc)
    q2 = 2.0 * auc * auc / (1.0 + auc)
    var = (
        auc * (1 - auc)
        + (n_pos - 1) * (q1 - auc * auc)
        + (n_neg - 1) * (q2 - auc * auc)
    ) / (n_pos * n_neg)
    return math.sqrt(var) if var > 0 else 0.0


def _normal_sf(z: float) -> float:
    """P(Z > z) pour Z ~ N(0,1)."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def p_value_spearman_asymptotic(rho: float, n: int) -> float:
    """p bilatéral asymptotique. Fiable au-delà de quelques centaines d'obs."""
    if n < 4 or abs(rho) >= 1.0:
        return float("nan")
    t = rho * math.sqrt((n - 2) / (1 - rho * rho))
    return 2.0 * _normal_sf(abs(t))


def p_value_permutation(
    x: Sequence[float], y: Sequence[float], *, iterations: int, seed: int
) -> float:
    """p bilatéral par permutation des rangs — exact en loi, sans hypothèse.

    Préféré à l'asymptotique aux petits N : à N=121 avec 45 % d'ex æquo, la
    distribution nulle de ρ n'est pas celle du cas continu.
    """
    rx, ry = ranks(x), ranks(y)
    observed = abs(pearson(rx, ry))
    rng = random.Random(seed)
    shuffled = list(ry)
    hits = 0
    for _ in range(iterations):
        rng.shuffle(shuffled)
        if abs(pearson(rx, shuffled)) >= observed - 1e-15:
            hits += 1
    # +1/+1 : un p de 0 exact n'existe pas avec un nombre fini de tirages.
    return (hits + 1) / (iterations + 1)


def min_detectable_rho(n: int) -> float:
    """|ρ| minimal détectable à α=0.05 et puissance 0.80 (transformation de Fisher).

    C'est la **résolution de l'instrument**. À N=121 elle vaut ~0.26 : tout
    effet plus petit est invisible, et son absence de détection n'est donc pas
    une information sur le système.
    """
    if n <= 4:
        return 1.0
    z = (_Z_ALPHA_2 + _Z_POWER) / math.sqrt(n - 3)
    return math.tanh(z)


def bootstrap_mean_ci(
    values: Sequence[float], *, iterations: int, seed: int, alpha: float = ALPHA
) -> tuple[float, float]:
    """IC percentile de la moyenne. Aucune hypothèse de normalité."""
    if len(values) < 2:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(iterations):
        means.append(_mean([values[rng.randrange(n)] for _ in range(n)]))
    means.sort()
    lo = means[int((alpha / 2) * iterations)]
    hi = means[min(iterations - 1, int((1 - alpha / 2) * iterations))]
    return (lo, hi)


# ── Structures de résultat ────────────────────────────────────────────────────


@dataclass
class Tranche:
    label: str
    n: int
    score_min: float
    score_max: float
    mean_outcome: float
    ci_low: float
    ci_high: float
    win_rate: float


@dataclass
class DomainSupport:
    """Ce que le dataset permet de voir du score — avant tout résultat."""

    n: int
    score_min: float
    score_max: float
    score_mean: float
    score_stdev: float
    distinct_values: int
    modal_value: float
    tie_mass: float
    support_ratio: float
    restricted: bool
    unobserved_below: float

    @property
    def note(self) -> str:
        return (
            f"aucune observation sous score {self.unobserved_below:g} : "
            f"toute conclusion ne porte que sur la bande "
            f"[{self.score_min:g}, {self.score_max:g}]"
        )


@dataclass
class PopulationResult:
    population: str
    outcome: str
    support: DomainSupport
    pearson_r: float
    spearman_rho: float
    kendall_tau: float
    p_value: float
    p_method: str
    auc: float
    auc_ci_low: float
    auc_ci_high: float
    n_winners: int
    n_losers: int
    min_detectable_rho: float
    tranches: list[Tranche]
    tranche_monotonicity: float
    top_minus_bottom: float
    top_minus_bottom_p: float
    verdict: str
    verdict_reasons: list[str] = field(default_factory=list)


@dataclass
class AuditReport:
    generated_at: str
    clean_data_since: str
    seed: int
    horizon: Optional[str]
    provenance: dict
    populations: list[PopulationResult]
    friction: dict
    ic_term_structure: dict = field(default_factory=dict)
    robustness: Optional[dict] = None
    blind_spots: list[str] = field(default_factory=list)


# ── Analyse ───────────────────────────────────────────────────────────────────


def describe_support(scores: Sequence[float]) -> DomainSupport:
    counts: dict[float, int] = {}
    for s in scores:
        counts[s] = counts.get(s, 0) + 1
    modal = max(counts, key=lambda k: counts[k]) if counts else 0.0
    lo, hi = (min(scores), max(scores)) if scores else (0.0, 0.0)
    support_ratio = (hi - lo) / SCORE_SCALE if scores else 0.0
    tie_mass = counts.get(modal, 0) / len(scores) if scores else 0.0
    return DomainSupport(
        n=len(scores),
        score_min=lo,
        score_max=hi,
        score_mean=_mean(scores),
        score_stdev=_pstdev(scores),
        distinct_values=len(counts),
        modal_value=modal,
        tie_mass=tie_mass,
        support_ratio=support_ratio,
        restricted=support_ratio < MIN_SUPPORT_RATIO or tie_mass > MAX_TIE_MASS,
        unobserved_below=lo,
    )


def build_tranches(
    scores: Sequence[float],
    outcomes: Sequence[float],
    *,
    target_bins: int,
    seed: int,
    bootstrap_iterations: int,
) -> list[Tranche]:
    """Tranches à masse approximativement égale, **sans jamais couper un ex æquo**.

    Des déciles au sens strict sont impossibles sur un score discret dont une
    seule valeur porte 45 % de la masse : ils placeraient la même valeur de
    score dans deux tranches différentes, ce qui fabriquerait une différence
    inter-tranches à partir de rien. On agrège donc par valeur de score, puis on
    fusionne les groupes jusqu'à atteindre la masse cible.
    """
    if not scores:
        return []
    by_score: dict[float, list[float]] = {}
    for s, o in zip(scores, outcomes):
        by_score.setdefault(s, []).append(o)

    target = max(1, len(scores) // max(1, target_bins))
    tranches: list[Tranche] = []
    bucket_scores: list[float] = []
    bucket_outcomes: list[float] = []

    def flush(idx: int) -> None:
        if not bucket_outcomes:
            return
        lo, hi = min(bucket_scores), max(bucket_scores)
        ci = bootstrap_mean_ci(
            bucket_outcomes, iterations=bootstrap_iterations, seed=seed + idx
        )
        wins = sum(1 for v in bucket_outcomes if v > 0)
        tranches.append(
            Tranche(
                label=f"{lo:g}" if lo == hi else f"{lo:g}-{hi:g}",
                n=len(bucket_outcomes),
                score_min=lo,
                score_max=hi,
                mean_outcome=_mean(bucket_outcomes),
                ci_low=ci[0],
                ci_high=ci[1],
                win_rate=wins / len(bucket_outcomes),
            )
        )

    for score in sorted(by_score):
        bucket_scores.append(score)
        bucket_outcomes.extend(by_score[score])
        if len(bucket_outcomes) >= target:
            flush(len(tranches))
            bucket_scores, bucket_outcomes = [], []
    if bucket_outcomes:
        if tranches and len(bucket_outcomes) < target / 2:
            # Résidu trop mince pour porter une moyenne : fusionné avec la
            # tranche précédente plutôt que rapporté comme une tranche à part.
            last = tranches.pop()
            bucket_scores.append(last.score_min)
            merged = bucket_outcomes + [last.mean_outcome] * last.n
            bucket_outcomes = merged
        flush(len(tranches))
    return tranches


def analyse_population(
    name: str,
    outcome_label: str,
    scores: Sequence[float],
    outcomes: Sequence[float],
    *,
    seed: int,
    permutation_iterations: int,
    bootstrap_iterations: int,
    target_bins: int,
) -> PopulationResult:
    support = describe_support(scores)
    rho = spearman(scores, outcomes)
    r = pearson(scores, outcomes)
    tau = kendall_tau_b(scores, outcomes)

    if support.n <= 2000:
        p = p_value_permutation(
            scores, outcomes, iterations=permutation_iterations, seed=seed
        )
        p_method = f"permutation ({permutation_iterations} tirages, graine {seed})"
    else:
        p = p_value_spearman_asymptotic(rho, support.n)
        p_method = "asymptotique (t sur rangs, approximation normale)"

    labels = [o > 0 for o in outcomes]
    n_pos = sum(1 for f in labels if f)
    n_neg = len(labels) - n_pos
    auc = auc_mann_whitney(scores, labels)
    se = auc_se_hanley(auc, n_pos, n_neg)

    tranches = build_tranches(
        scores,
        outcomes,
        target_bins=target_bins,
        seed=seed,
        bootstrap_iterations=bootstrap_iterations,
    )
    mono = 0.0
    if len(tranches) >= 3:
        mono = spearman(list(range(len(tranches))), [t.mean_outcome for t in tranches])

    top_minus_bottom = 0.0
    tmb_p = float("nan")
    if len(tranches) >= 2:
        top_minus_bottom = tranches[-1].mean_outcome - tranches[0].mean_outcome
        cut_lo, cut_hi = tranches[0].score_max, tranches[-1].score_min
        lo_vals = [o for s, o in zip(scores, outcomes) if s <= cut_lo]
        hi_vals = [o for s, o in zip(scores, outcomes) if s >= cut_hi]
        tmb_p = _permutation_diff_p(
            lo_vals, hi_vals, iterations=permutation_iterations, seed=seed + 1
        )

    rho_floor = min_detectable_rho(support.n)
    verdict, reasons = _verdict(support, rho, p, rho_floor, auc, se)

    return PopulationResult(
        population=name,
        outcome=outcome_label,
        support=support,
        pearson_r=r,
        spearman_rho=rho,
        kendall_tau=tau,
        p_value=p,
        p_method=p_method,
        auc=auc,
        auc_ci_low=auc - _Z_ALPHA_2 * se,
        auc_ci_high=auc + _Z_ALPHA_2 * se,
        n_winners=n_pos,
        n_losers=n_neg,
        min_detectable_rho=rho_floor,
        tranches=tranches,
        tranche_monotonicity=mono,
        top_minus_bottom=top_minus_bottom,
        top_minus_bottom_p=tmb_p,
        verdict=verdict,
        verdict_reasons=reasons,
    )


def _permutation_diff_p(
    low: Sequence[float], high: Sequence[float], *, iterations: int, seed: int
) -> float:
    """p bilatéral pour « la moyenne du haut diffère de celle du bas »."""
    if len(low) < 2 or len(high) < 2:
        return float("nan")
    observed = abs(_mean(high) - _mean(low))
    pool = list(low) + list(high)
    n_low = len(low)
    rng = random.Random(seed)
    hits = 0
    for _ in range(iterations):
        rng.shuffle(pool)
        if abs(_mean(pool[n_low:]) - _mean(pool[:n_low])) >= observed - 1e-15:
            hits += 1
    return (hits + 1) / (iterations + 1)


def _verdict(
    support: DomainSupport,
    rho: float,
    p: float,
    rho_floor: float,
    auc: float,
    se: float,
) -> tuple[str, list[str]]:
    """Trichotomie explicite. L'ordre des tests importe : l'instrument d'abord.

    Tester la significativité avant la puissance produirait la faute classique —
    lire « p > 0.05 » comme « pas d'effet » alors que le test ne pouvait pas en
    voir un.
    """
    reasons: list[str] = []
    significant = (not math.isnan(p)) and p < ALPHA
    auc_separated = se > 0 and abs(auc - 0.5) > _Z_ALPHA_2 * se

    if significant and abs(rho) >= rho_floor:
        reasons.append(
            f"ρ={rho:+.3f} significatif (p={p:.4g}) et au-dessus de la "
            f"résolution de l'instrument ({rho_floor:.3f})"
        )
        if auc_separated:
            reasons.append(f"AUC={auc:.3f} séparée de 0.5 hors intervalle à 95 %")
        return VERDICT_SIGNAL, reasons

    if significant and abs(rho) < rho_floor:
        reasons.append(
            f"ρ={rho:+.3f} significatif (p={p:.4g}) mais sous la résolution "
            f"({rho_floor:.3f}) : effet réel possible, taille non estimable"
        )
        return VERDICT_SIGNAL, reasons

    if rho_floor > MAX_ACCEPTABLE_RHO_FLOOR:
        reasons.append(
            f"résolution {rho_floor:.3f} > {MAX_ACCEPTABLE_RHO_FLOOR} : "
            f"N={support.n} ne permet de voir que de très gros effets"
        )
    if support.tie_mass > MAX_TIE_MASS:
        reasons.append(
            f"{support.tie_mass:.0%} des observations au score "
            f"{support.modal_value:g} : rangs saturés d'ex æquo, "
            f"corrélation atténuée par construction"
        )
    if support.support_ratio < MIN_SUPPORT_RATIO:
        reasons.append(
            f"domaine observé [{support.score_min:g}, {support.score_max:g}] = "
            f"{support.support_ratio:.0%} de l'échelle nominale"
        )
    if reasons:
        return VERDICT_INSTRUMENT, reasons

    reasons.append(
        f"ρ={rho:+.3f} (p={p:.4g}) et AUC={auc:.3f} compatibles avec l'absence "
        f"d'ordonnancement, à une résolution de {rho_floor:.3f}"
    )
    reasons.append(support.note)
    return VERDICT_ABSENCE, reasons


# ── Chargement des populations ────────────────────────────────────────────────


def _safe_float(value: object) -> Optional[float]:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def load_executed(path: Optional[Path], outcome_key: str) -> tuple[list, list, list]:
    """Trades exécutés — délègue au loader unique (INV-DATASET-001)."""
    trades = load_clean_trades(path)
    scores: list[float] = []
    outcomes: list[float] = []
    kept: list[dict] = []
    for t in trades:
        s = _safe_float(t.get("score"))
        o = _safe_float(t.get(outcome_key))
        if s is None or o is None or s <= 0:
            continue
        scores.append(s)
        outcomes.append(o)
        kept.append(t)
    return scores, outcomes, kept


@dataclass
class ObservedRecord:
    """Une observation de candidat, avec ses facteurs de confusion.

    `regime`, `side`, `symbol` et `day` ne servent pas au résultat principal :
    ils servent à tenter de le DÉTRUIRE (stratification, démoyennage). Un
    ordonnancement qui disparaît une fois la dérive propre au symbole retirée
    n'était pas un ordonnancement du score.
    """

    score: float
    outcome: float
    regime: str
    side: str
    symbol: str
    day: str


def load_observed_records(regret_dir: Path, horizon: str) -> tuple[list, dict]:
    """Candidats observés (regret_horizons v2, source canonique ADR-0018).

    Filtre d'époque appliqué sur `ts_signal` avec la MÊME borne que le loader de
    trades (`CLEAN_DATA_SINCE_ACTIVE`) : comparer deux populations bornées
    différemment reproduirait exactement l'incident AUDIT-EMP-001.
    """
    records: list[ObservedRecord] = []
    stats = {
        "files": 0,
        "records_total": 0,
        "excluded_hors_epoque": 0,
        "excluded_horizon_absent": 0,
        "kept": 0,
        "horizon": horizon,
    }
    if not regret_dir.exists():
        return records, stats

    for f in sorted(regret_dir.glob("regret_horizons_*.jsonl")):
        stats["files"] += 1
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            stats["records_total"] += 1
            ts = _safe_float(rec.get("ts_signal"))
            if ts is None:
                stats["excluded_hors_epoque"] += 1
                continue
            when = datetime.fromtimestamp(ts, tz=timezone.utc)
            if when < CLEAN_DATA_SINCE_ACTIVE:
                stats["excluded_hors_epoque"] += 1
                continue
            score = _safe_float(rec.get("score"))
            h = (rec.get("horizons") or {}).get(horizon) or {}
            ret = _safe_float(h.get("return_pct"))
            if score is None or ret is None:
                stats["excluded_horizon_absent"] += 1
                continue
            records.append(
                ObservedRecord(
                    score=score,
                    outcome=ret,
                    regime=str(rec.get("regime") or "unknown"),
                    side=str(rec.get("side") or "unknown"),
                    symbol=str(rec.get("symbol") or "unknown"),
                    day=when.date().isoformat(),
                )
            )
            stats["kept"] += 1
    return records, stats


def load_observed(
    regret_dir: Path, horizon: str
) -> tuple[list[float], list[float], dict]:
    """Vue (scores, résultats) de `load_observed_records` — API historique."""
    records, stats = load_observed_records(regret_dir, horizon)
    return [r.score for r in records], [r.outcome for r in records], stats


# ── Robustesse : tenter de détruire le résultat ───────────────────────────────


@dataclass
class Stratum:
    label: str
    n: int
    spearman_rho: float
    auc: float
    mean_outcome: float


@dataclass
class RobustnessResult:
    """Le résultat survit-il aux facteurs de confusion évidents ?

    Trois attaques, toutes destructives si le signal est un artefact :
      1. **stratification** — un ρ global peut naître d'un mélange de régimes
         (paradoxe de Simpson) sans exister dans aucun régime.
      2. **démoyennage** — retirer la moyenne du symbole, puis du jour, retire
         la dérive commune. Si ρ vient du fait que les scores élevés tombent sur
         les paires ou les jours qui montent, il s'effondre.
      3. **bootstrap par blocs de jours** — les observations se recouvrent
         (mêmes symboles, fenêtres glissantes toutes les 15 min) : le N effectif
         est bien inférieur au N nominal, et les p asymptotiques sont donc
         optimistes. Rééchantillonner des JOURS entiers rend un intervalle
         honnête.
    """

    horizon: str
    n: int
    n_days: int
    rho_global: float
    strata: list[Stratum]
    rho_demeaned_symbol: float
    rho_demeaned_day: float
    rho_demeaned_both: float
    block_ci_low: float
    block_ci_high: float
    block_ci_median: float
    survives: bool
    notes: list[str] = field(default_factory=list)


def _stratify(records: Sequence[ObservedRecord], key, min_n: int) -> list[Stratum]:
    groups: dict[str, list[ObservedRecord]] = {}
    for r in records:
        groups.setdefault(key(r), []).append(r)
    out: list[Stratum] = []
    for label in sorted(groups, key=lambda k: -len(groups[k])):
        g = groups[label]
        if len(g) < min_n:
            continue
        s = [x.score for x in g]
        y = [x.outcome for x in g]
        out.append(
            Stratum(
                label=label,
                n=len(g),
                spearman_rho=spearman(s, y),
                auc=auc_mann_whitney(s, [v > 0 for v in y]),
                mean_outcome=_mean(y),
            )
        )
    return out


def _group_means(records: Sequence[ObservedRecord], key) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for r in records:
        buckets.setdefault(key(r), []).append(r.outcome)
    return {k: _mean(v) for k, v in buckets.items()}


def _demean(records: Sequence[ObservedRecord], key) -> list[float]:
    means = _group_means(records, key)
    return [r.outcome - means[key(r)] for r in records]


def robustness_checks(
    records: Sequence[ObservedRecord],
    *,
    horizon: str,
    seed: int,
    block_iterations: int,
    min_stratum: int = 200,
) -> Optional[RobustnessResult]:
    if len(records) < min_stratum:
        return None

    scores = [r.score for r in records]
    outcomes = [r.outcome for r in records]
    rho_global = spearman(scores, outcomes)

    strata = _stratify(records, lambda r: f"regime:{r.regime}", min_stratum)
    strata += _stratify(records, lambda r: f"side:{r.side}", min_stratum)

    grand = _mean(outcomes)
    sym_means = _group_means(records, lambda r: r.symbol)
    day_means = _group_means(records, lambda r: r.day)
    d_both = [
        r.outcome - sym_means[r.symbol] - day_means[r.day] + grand for r in records
    ]

    rho_sym = spearman(scores, _demean(records, lambda r: r.symbol))
    rho_day = spearman(scores, _demean(records, lambda r: r.day))
    rho_both = spearman(scores, d_both)

    by_day: dict[str, list[ObservedRecord]] = {}
    for r in records:
        by_day.setdefault(r.day, []).append(r)
    days = sorted(by_day)
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(block_iterations):
        sample: list[ObservedRecord] = []
        for _ in range(len(days)):
            sample.extend(by_day[days[rng.randrange(len(days))]])
        estimates.append(
            spearman([x.score for x in sample], [x.outcome for x in sample])
        )
    estimates.sort()
    lo = estimates[int((ALPHA / 2) * block_iterations)]
    hi = estimates[min(block_iterations - 1, int((1 - ALPHA / 2) * block_iterations))]
    med = estimates[block_iterations // 2]

    notes: list[str] = []
    same_sign = [s for s in strata if s.spearman_rho * rho_global > 0]
    if len(same_sign) < len(strata):
        contraires = [s.label for s in strata if s.spearman_rho * rho_global <= 0]
        notes.append(
            "signe inversé ou nul dans : " + ", ".join(contraires) + " — le ρ global "
            "ne vaut pas uniformément dans toutes les strates"
        )
    attenuation = abs(rho_both) / abs(rho_global) if rho_global else 0.0
    notes.append(
        f"après démoyennage jour+symbole, |ρ| conserve {attenuation:.0%} de sa "
        f"valeur : la part restante n'est explicable ni par la paire ni par le jour"
    )
    if lo <= 0 <= hi:
        notes.append(
            "l'intervalle par blocs de jours contient 0 : avec seulement "
            f"{len(days)} jours, le signe lui-même n'est pas établi"
        )
    else:
        notes.append(
            f"intervalle par blocs de jours [{lo:+.3f} ; {hi:+.3f}] hors de 0 sur "
            f"{len(days)} jours — mais {len(days)} jours restent peu"
        )

    survives = (lo > 0 or hi < 0) and abs(rho_both) > 0.02
    return RobustnessResult(
        horizon=horizon,
        n=len(records),
        n_days=len(days),
        rho_global=rho_global,
        strata=strata,
        rho_demeaned_symbol=rho_sym,
        rho_demeaned_day=rho_day,
        rho_demeaned_both=rho_both,
        block_ci_low=lo,
        block_ci_high=hi,
        block_ci_median=med,
        survives=survives,
        notes=notes,
    )


def ic_term_structure(regret_dir: Path, *, seed: int) -> dict:
    """ρ de Spearman du score par horizon — structure temporelle du signal.

    Un score peut ordonner à 15 min et plus rien à 24 h (edge qui se dissipe),
    ou l'inverse (thèse lente). Une mesure à horizon unique ne distingue pas
    « pas de signal » de « pas au bon horizon ».
    """
    out: dict[str, dict] = {}
    for horizon in HORIZON_ORDER:
        scores, outcomes, stats = load_observed(regret_dir, horizon)
        if len(scores) < 30:
            continue
        rho = spearman(scores, outcomes)
        out[horizon] = {
            "n": len(scores),
            "spearman_rho": rho,
            "p_value": p_value_spearman_asymptotic(rho, len(scores)),
            "auc": auc_mann_whitney(scores, [o > 0 for o in outcomes]),
            "mean_return_pct": _mean(outcomes),
            "min_detectable_rho": min_detectable_rho(len(scores)),
        }
    return out


# ── Rapport ───────────────────────────────────────────────────────────────────


def _fmt_pct(value: float) -> str:
    return f"{value * 100:+.4f}%"


def render_text(report: AuditReport) -> str:
    lines: list[str] = []
    add = lines.append
    add("=" * 74)
    add("  SCORE CALIBRATION AUDIT — le score classe-t-il quelque chose ?")
    add("=" * 74)
    add(f"  Généré      : {report.generated_at}")
    add(f"  Borne époque: {report.clean_data_since}")
    add(f"  Graine      : {report.seed}")
    add("")

    fr = report.friction
    add("-" * 74)
    add("  PLANCHER DE FRICTION — INV-FRICTION-001")
    add("-" * 74)
    add(f"  Friction moyenne / trade        {_fmt_pct(fr['friction_rate'])}")
    add(f"  Edge BRUT moyen / trade         {_fmt_pct(fr['gross_edge_rate'])}")
    add(f"  Edge NET moyen / trade          {_fmt_pct(fr['net_edge_rate'])}")
    add(f"  Marge (brut - friction)         {_fmt_pct(fr['margin'])}")
    add(f"  Verdict                         {fr['verdict']}")
    add("")

    for pop in report.populations:
        s = pop.support
        add("-" * 74)
        add(f"  POPULATION : {pop.population}")
        add(f"  Résultat mesuré : {pop.outcome}")
        add("-" * 74)
        add(f"  N                               {s.n}")
        add(
            f"  Domaine du score                [{s.score_min:g}, {s.score_max:g}]"
            f"  ({s.support_ratio:.0%} de l'échelle)"
        )
        add(
            f"  Dispersion                      σ={s.score_stdev:.2f}"
            f"  {s.distinct_values} valeurs distinctes"
        )
        add(
            f"  Mode                            {s.modal_value:g}"
            f"  ({s.tie_mass:.0%} de la masse)"
        )
        add(f"  Résolution (|ρ| min détectable) {pop.min_detectable_rho:.3f}")
        add("")
        add(f"  Pearson r                       {pop.pearson_r:+.4f}")
        add(f"  Spearman ρ                      {pop.spearman_rho:+.4f}")
        add(f"  Kendall τ-b                     {pop.kendall_tau:+.4f}")
        add(f"  p ({pop.p_method})")
        add(f"                                  {pop.p_value:.4g}")
        add(
            f"  AUC gagnants/perdants           {pop.auc:.4f}"
            f"  [IC95 {pop.auc_ci_low:.4f} ; {pop.auc_ci_high:.4f}]"
        )
        add(f"  Gagnants / perdants             {pop.n_winners} / {pop.n_losers}")
        add("")
        if pop.tranches:
            add("  TRANCHES (masse ~égale, ex æquo jamais coupés)")
            add("    score          n     moyenne       IC95                 WR")
            for t in pop.tranches:
                add(
                    f"    {t.label:<12} {t.n:>4}  {_fmt_pct(t.mean_outcome):>11}"
                    f"  [{_fmt_pct(t.ci_low):>10} ; {_fmt_pct(t.ci_high):>10}]"
                    f"  {t.win_rate:.0%}"
                )
            add(f"  Monotonicité des tranches       {pop.tranche_monotonicity:+.3f}")
            add(
                f"  Haut - bas                      {_fmt_pct(pop.top_minus_bottom)}"
                f"  (p={pop.top_minus_bottom_p:.4g})"
            )
            add("")
        add(f"  VERDICT : {pop.verdict}")
        for reason in pop.verdict_reasons:
            add(f"    - {reason}")
        add("")

    if report.ic_term_structure:
        add("-" * 74)
        add("  STRUCTURE TEMPORELLE DE L'IC (population observée)")
        add("-" * 74)
        add("    horizon      n        ρ         p        AUC     rendement moyen")
        for horizon in HORIZON_ORDER:
            d = report.ic_term_structure.get(horizon)
            if not d:
                continue
            add(
                f"    {horizon:<8} {d['n']:>6}  {d['spearman_rho']:+.4f}"
                f"  {d['p_value']:>8.3g}  {d['auc']:.4f}"
                f"  {_fmt_pct(d['mean_return_pct']):>12}"
            )
        add("")

    rb = report.robustness
    if rb:
        add("-" * 74)
        add(
            "  ROBUSTESSE — tentatives de destruction du résultat "
            f"(horizon {rb['horizon']})"
        )
        add("-" * 74)
        add(f"  ρ global                        {rb['rho_global']:+.4f}")
        add("  Stratification :")
        for st in rb["strata"]:
            add(
                f"    {st['label']:<32} n={st['n']:>6}  ρ={st['spearman_rho']:+.4f}"
                f"  AUC={st['auc']:.4f}  moy={_fmt_pct(st['mean_outcome'])}"
            )
        add("  Démoyennage (retrait des dérives communes) :")
        add(f"    par symbole                   ρ={rb['rho_demeaned_symbol']:+.4f}")
        add(f"    par jour                      ρ={rb['rho_demeaned_day']:+.4f}")
        add(f"    par jour + symbole            ρ={rb['rho_demeaned_both']:+.4f}")
        add(
            f"  Bootstrap par blocs de jours    IC95 [{rb['block_ci_low']:+.4f} ; "
            f"{rb['block_ci_high']:+.4f}]  médiane {rb['block_ci_median']:+.4f}"
            f"  ({rb['n_days']} jours)"
        )
        add(f"  SURVIT AUX CONTRÔLES            {'OUI' if rb['survives'] else 'NON'}")
        for note in rb["notes"]:
            add(f"    - {note}")
        add("")

    if report.blind_spots:
        add("-" * 74)
        add("  ANGLES MORTS — ce que ce dataset ne peut pas dire")
        add("-" * 74)
        for b in report.blind_spots:
            add(f"    - {b}")
        add("")
    add("=" * 74)
    return "\n".join(lines)


def build_report(
    *,
    trades_path: Optional[Path],
    regret_dir: Path,
    horizon: str,
    outcome_key: str,
    seed: int,
    permutation_iterations: int,
    bootstrap_iterations: int,
    target_bins: int,
    with_term_structure: bool,
    with_robustness: bool = True,
    block_iterations: int = 400,
) -> AuditReport:
    populations: list[PopulationResult] = []
    blind_spots: list[str] = []

    scores_x, outcomes_x, trades = load_executed(trades_path, outcome_key)
    if scores_x:
        populations.append(
            analyse_population(
                "trades exécutés (score ⊗ sorties ⊗ frais)",
                f"{outcome_key} réalisé",
                scores_x,
                outcomes_x,
                seed=seed,
                permutation_iterations=permutation_iterations,
                bootstrap_iterations=bootstrap_iterations,
                target_bins=target_bins,
            )
        )

    observed, regret_stats = load_observed_records(regret_dir, horizon)
    scores_o = [r.score for r in observed]
    outcomes_o = [r.outcome for r in observed]
    if scores_o:
        populations.append(
            analyse_population(
                f"candidats observés, horizon {horizon} (score seul)",
                f"return_pct signé à {horizon}, hors frais",
                scores_o,
                outcomes_o,
                seed=seed,
                permutation_iterations=permutation_iterations,
                bootstrap_iterations=bootstrap_iterations,
                target_bins=target_bins,
            )
        )
    else:
        blind_spots.append(
            f"population observée vide dans {regret_dir} — le test du score "
            f"seul (hors politique de sortie) n'a PAS été exécuté"
        )

    for pop in populations:
        if pop.support.restricted:
            blind_spots.append(f"{pop.population} : {pop.support.note}")
    blind_spots.append(
        "aucun dataset du dépôt n'observe le résultat d'un candidat à bas score : "
        "le pouvoir discriminant du score hors bande haute est structurellement "
        "non testable en l'état"
    )

    robustness = None
    if with_robustness and observed:
        rb = robustness_checks(
            observed,
            horizon=horizon,
            seed=seed,
            block_iterations=block_iterations,
        )
        if rb is not None:
            robustness = asdict(rb)
            if not rb.survives:
                blind_spots.append(
                    f"horizon {horizon} : le ρ observé ne survit pas aux contrôles "
                    f"de robustesse — ne pas le citer comme un signal"
                )

    fr = friction_floor(trades)
    return AuditReport(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        clean_data_since=CLEAN_DATA_SINCE_ACTIVE.isoformat(),
        seed=seed,
        horizon=horizon,
        provenance={
            "trades": trades_provenance(trades_path),
            "regret": regret_stats,
        },
        populations=populations,
        friction={
            "n": fr.n,
            "friction_rate": fr.friction_rate,
            "gross_edge_rate": fr.gross_edge_rate,
            "net_edge_rate": fr.net_edge_rate,
            "margin": fr.margin,
            "verdict": fr.verdict,
        },
        ic_term_structure=(
            ic_term_structure(regret_dir, seed=seed) if with_term_structure else {}
        ),
        robustness=robustness,
        blind_spots=blind_spots,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Le score ordonne-t-il les résultats ? (outil de mesure passif)"
    )
    parser.add_argument("--trades", type=Path, default=None, help="paper_trades.jsonl")
    parser.add_argument(
        "--regret",
        type=Path,
        default=Path(os.getenv("REGRET_HORIZONS_DIR", str(DEFAULT_REGRET_DIR))),
        help="répertoire databases/regret",
    )
    parser.add_argument("--horizon", default=DEFAULT_HORIZON, choices=HORIZON_ORDER)
    parser.add_argument(
        "--outcome",
        default="pnl_usd",
        choices=["pnl_usd", "pnl_pct"],
        help="résultat mesuré sur les trades exécutés (défaut : net en USD)",
    )
    parser.add_argument("--seed", type=int, default=20260729)
    parser.add_argument("--permutations", type=int, default=20000)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--bins", type=int, default=5)
    parser.add_argument(
        "--no-term-structure",
        action="store_true",
        help="ne pas recalculer l'IC sur les 7 horizons (plus rapide)",
    )
    parser.add_argument(
        "--no-robustness",
        action="store_true",
        help="ne pas exécuter stratification / démoyennage / bootstrap par blocs",
    )
    parser.add_argument("--block-iterations", type=int, default=400)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        trades_path=args.trades,
        regret_dir=args.regret,
        horizon=args.horizon,
        outcome_key=args.outcome,
        seed=args.seed,
        permutation_iterations=args.permutations,
        bootstrap_iterations=args.bootstrap,
        target_bins=args.bins,
        with_term_structure=not args.no_term_structure,
        with_robustness=not args.no_robustness,
        block_iterations=args.block_iterations,
    )

    if args.json:
        print(json.dumps(asdict(report), indent=2, default=str, ensure_ascii=False))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
