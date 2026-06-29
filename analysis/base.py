"""
analysis/base.py — Types et utilitaires partagés par tous les plugins d'audit.

Chaque plugin hérite de `RegimePlugin` et implémente `analyze(trades)`.
Le runner `regime_audit.py` charge les plugins et produit le rapport consolidé.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Trade:
    """Représentation unifiée d'un trade fermé."""

    trade_id: str
    symbol: str
    side: str  # BUY | SELL
    regime: str
    score: int
    entry_price: float
    pnl_usd: float
    pnl_pct: float
    mae_pct: float | None
    mfe_pct: float | None
    duration_s: float
    exit_reason: str
    opened_at: float | None = None  # timestamp UNIX
    atr_pct: float | None = None
    volume_usd: float | None = None


@dataclass
class HypothesisResult:
    """Résultat d'un test d'hypothèse statistique."""

    name: str
    description: str
    n: int
    accepted: bool | None  # None = non concluant (N insuffisant)
    pf: float | None = None  # Profit Factor
    win_rate: float | None = None
    expectancy_usd: float | None = None
    p_value: float | None = None
    effect_size: float | None = None
    confidence_interval: tuple[float, float] | None = None
    min_n_required: int = 50
    notes: str = ""


@dataclass
class AuditResult:
    """Résultat complet d'un plugin d'audit."""

    plugin_name: str
    regime: str
    n_trades: int
    hypotheses: list[HypothesisResult] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    verdict: str = ""
    notes: str = ""


@runtime_checkable
class RegimePlugin(Protocol):
    """Interface que chaque plugin d'audit doit implémenter."""

    name: str
    regime_filter: str | None  # None = tous les régimes

    def analyze(self, trades: list[Trade]) -> AuditResult: ...


# ── Helpers statistiques ──────────────────────────────────────────────────────


def profit_factor(pnls: list[float]) -> float | None:
    wins = sum(p for p in pnls if p > 0)
    losses = abs(sum(p for p in pnls if p < 0))
    if losses == 0:
        return float("inf") if wins > 0 else None
    return round(wins / losses, 3)


def win_rate(pnls: list[float]) -> float | None:
    if not pnls:
        return None
    return round(sum(1 for p in pnls if p > 0) / len(pnls), 3)


def expectancy(pnls: list[float]) -> float | None:
    if not pnls:
        return None
    return round(sum(pnls) / len(pnls), 4)


def sharpe(pnls: list[float], risk_free: float = 0.0) -> float | None:
    if len(pnls) < 2:
        return None
    mean = sum(pnls) / len(pnls)
    variance = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return None
    return round((mean - risk_free) / std, 3)


def sortino(pnls: list[float], risk_free: float = 0.0) -> float | None:
    if len(pnls) < 2:
        return None
    mean = sum(pnls) / len(pnls)
    downside = [p for p in pnls if p < risk_free]
    if not downside:
        return float("inf")
    downside_var = sum((p - risk_free) ** 2 for p in downside) / len(downside)
    downside_std = math.sqrt(downside_var)
    if downside_std == 0:
        return None
    return round((mean - risk_free) / downside_std, 3)


def max_drawdown(pnls: list[float]) -> float:
    """Max drawdown en % du capital cumulatif (basé sur PnL USD)."""
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        cumulative += p
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 4)


def ulcer_index(pnls: list[float]) -> float | None:
    """Ulcer Index — mesure la douleur des drawdowns."""
    if len(pnls) < 2:
        return None
    cumulative = []
    cum = 0.0
    for p in pnls:
        cum += p
        cumulative.append(cum)
    peak = cumulative[0]
    dd_sq_sum = 0.0
    for c in cumulative:
        if c > peak:
            peak = c
        dd_pct = ((peak - c) / peak * 100) if peak > 0 else 0.0
        dd_sq_sum += dd_pct**2
    return round(math.sqrt(dd_sq_sum / len(cumulative)), 3)


def recovery_factor(pnls: list[float]) -> float | None:
    """Net profit / Max drawdown."""
    net = sum(pnls)
    dd = max_drawdown(pnls)
    if dd == 0:
        return float("inf") if net > 0 else None
    return round(net / dd, 3)


def kelly_fraction(pnls: list[float]) -> float | None:
    """Kelly criterion simplifié : WR - (1-WR)/ratio moyen gain/perte."""
    wr = win_rate(pnls)
    if wr is None or len(pnls) < 10:
        return None
    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]
    if not losses:
        return 1.0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses)
    if avg_loss == 0:
        return None
    ratio = avg_win / avg_loss
    k = wr - (1 - wr) / ratio
    return round(max(0.0, k), 3)


def mar_ratio(pnls: list[float], period_years: float = 1.0) -> float | None:
    """MAR = CAGR / Max Drawdown."""
    net = sum(pnls)
    dd = max_drawdown(pnls)
    if dd == 0 or net <= 0:
        return None
    cagr = net / period_years  # simplifié (pas de compounding)
    return round(cagr / dd, 3)


def full_metrics(pnls: list[float]) -> dict:
    """Calcule toutes les métriques sur une liste de PnL USD."""
    return {
        "n": len(pnls),
        "total_pnl_usd": round(sum(pnls), 2),
        "profit_factor": profit_factor(pnls),
        "win_rate": win_rate(pnls),
        "expectancy_usd": expectancy(pnls),
        "sharpe": sharpe(pnls),
        "sortino": sortino(pnls),
        "max_drawdown_usd": max_drawdown(pnls),
        "ulcer_index": ulcer_index(pnls),
        "recovery_factor": recovery_factor(pnls),
        "kelly_fraction": kelly_fraction(pnls),
        "mar_ratio": mar_ratio(pnls),
    }


# ── Analyses avancées ────────────────────────────────────────────────────────


def bootstrap_confidence_interval(
    pnls: list[float],
    metric_fn=None,
    n_bootstrap: int = 1000,
    ci: float = 0.95,
) -> tuple[float, float] | None:
    """Bootstrap CI sur une métrique (défaut: expectancy).

    Tire n_bootstrap échantillons avec remise, calcule la métrique sur chacun,
    retourne l'intervalle [alpha/2, 1-alpha/2] des percentiles.
    """
    import random

    if len(pnls) < 10:
        return None
    if metric_fn is None:
        metric_fn = expectancy

    n = len(pnls)
    stats: list[float] = []
    for _ in range(n_bootstrap):
        sample = [pnls[random.randrange(n)] for _ in range(n)]
        val = metric_fn(sample)
        if val is not None and not math.isinf(val):
            stats.append(val)

    if len(stats) < 10:
        return None
    stats.sort()
    alpha = 1 - ci
    lo_idx = int(len(stats) * alpha / 2)
    hi_idx = int(len(stats) * (1 - alpha / 2))
    return (round(stats[lo_idx], 4), round(stats[min(hi_idx, len(stats) - 1)], 4))


def monte_carlo_max_drawdown(
    pnls: list[float],
    n_sim: int = 1000,
    ci: float = 0.95,
) -> dict | None:
    """Monte-Carlo sur séquences de trades : distribution du drawdown maximal.

    Permute l'ordre des trades n_sim fois et calcule le MaxDD à chaque fois.
    Retourne mean, p95, p99 — donne la robustesse du DD au-delà de l'ordre observé.
    """
    import random

    if len(pnls) < 10:
        return None

    dds: list[float] = []
    for _ in range(n_sim):
        shuffled = list(pnls)
        random.shuffle(shuffled)
        dds.append(max_drawdown(shuffled))

    dds.sort()
    n = len(dds)
    return {
        "mean_dd": round(sum(dds) / n, 4),
        "p95_dd": round(dds[int(n * 0.95)], 4),
        "p99_dd": round(dds[int(n * 0.99)], 4),
        "observed_dd": max_drawdown(pnls),
        "n_sim": n_sim,
    }


def rolling_profit_factor(pnls: list[float], window: int = 20) -> list[float | None]:
    """PF glissant sur une fenêtre de `window` trades.

    Utile pour détecter une dérive progressive de la performance.
    Retourne une liste de longueur len(pnls), None pour les fenêtres incomplètes.
    """
    result: list[float | None] = [None] * len(pnls)
    for i in range(window - 1, len(pnls)):
        window_pnls = pnls[i - window + 1 : i + 1]
        result[i] = profit_factor(window_pnls)
    return result


def concept_drift_detected(
    pnls: list[float],
    window: int = 20,
    min_n: int = 40,
    threshold_ratio: float = 0.7,
) -> dict:
    """Détection de dérive (concept drift) : compare PF récent vs historique.

    Si PF_recent / PF_historique < threshold_ratio → drift probable.
    Retourne un dict avec verdict et métriques.
    """
    if len(pnls) < min_n:
        return {
            "drift": None,
            "reason": f"N={len(pnls)} < {min_n} requis",
            "pf_historical": None,
            "pf_recent": None,
        }

    historical = pnls[:-window]
    recent = pnls[-window:]
    pf_h = profit_factor(historical)
    pf_r = profit_factor(recent)

    if not isinstance(pf_h, float) or not isinstance(pf_r, float):
        return {
            "drift": None,
            "reason": "PF non calculable (toutes pertes ou tous gains)",
            "pf_historical": pf_h,
            "pf_recent": pf_r,
        }

    ratio = pf_r / pf_h if pf_h > 0 else 0.0
    drift = ratio < threshold_ratio

    return {
        "drift": drift,
        "ratio": round(ratio, 3),
        "pf_historical": pf_h,
        "pf_recent": pf_r,
        "threshold": threshold_ratio,
        "reason": (
            f"PF récent ({pf_r}) / PF historique ({pf_h}) = {ratio:.2f} "
            f"{'< ' if drift else '>= '}{threshold_ratio}"
        ),
    }


# ── Chargement trades depuis JSONL ────────────────────────────────────────────


def load_trades(jsonl_path: str | None = None) -> list[Trade]:
    """Charge les trades fermés depuis paper_trades.jsonl."""
    import json
    from pathlib import Path

    path = Path(jsonl_path or "databases/paper_trades.jsonl")
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable: {path}")

    opens: dict[str, dict] = {}
    closes: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            tid = ev.get("trade_id", "")
            if ev.get("event") == "OPEN":
                opens[tid] = ev
            elif ev.get("event") == "CLOSE":
                closes[tid] = ev

    trades: list[Trade] = []
    for tid, cl in closes.items():
        op = opens.get(tid, {})
        try:
            pnl_usd = float(cl.get("pnl_usd") or 0)
            pnl_pct = float(cl.get("pnl_pct") or 0)
        except (TypeError, ValueError):
            continue
        mae = cl.get("mae_pct")
        mfe = cl.get("mfe_pct")
        trades.append(
            Trade(
                trade_id=tid,
                symbol=cl.get("symbol") or op.get("symbol", "?"),
                side=(op.get("side") or cl.get("side") or "?").upper(),
                regime=op.get("regime") or cl.get("regime") or "unknown",
                score=int(op.get("score") or cl.get("score") or 0),
                entry_price=float(op.get("entry_price") or op.get("price") or 0),
                pnl_usd=pnl_usd,
                pnl_pct=pnl_pct,
                mae_pct=float(mae) if mae is not None else None,
                mfe_pct=float(mfe) if mfe is not None else None,
                duration_s=float(cl.get("duration_s") or 0),
                exit_reason=cl.get("reason") or "?",
                opened_at=float(op.get("timestamp") or 0) or None,
                atr_pct=float(op.get("atr_pct") or 0) or None,
                volume_usd=float(op.get("volume_usd") or 0) or None,
            )
        )
    return trades
