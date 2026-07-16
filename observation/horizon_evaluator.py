"""
observation/horizon_evaluator.py — R2 : évaluation à horizons de la shortlist radar.

Phase R2 de l'ADR-0016 : mesure, pour chaque paire de la shortlist R1, ce que
le marché a réellement offert aux horizons de trading de la machine
(15m / 1h / 4h) — volatilité réalisée, amplitude des mouvements, persistance
directionnelle — puis agrège par PALIER (top 50 / 100 / 200) pour nourrir la
décision d'élargissement de l'univers tradé (ADR-0017, époque V4).

STRICTEMENT PASSIF, et ZÉRO appel API : tout est recalculé depuis le store
d'observation (le pouls enregistre déjà les prix de tout le marché toutes
les 15 min). Écrit dans le même store — jamais lu par le chemin de décision.

Métriques par paire (fenêtre 24h) :
  - vol_pct   : écart-type des rendements à l'horizon (volatilité réalisée)
  - p50_abs / p90_abs : amplitude médiane / P90 des mouvements absolus
  - persistance_1h : fraction de rendements 1h consécutifs de même signe
    (>0.5 = régime momentum, <0.5 = retour à la moyenne)

Métriques par palier (top K du composite radar) :
  - opportunités/jour : mouvements |4h| >= RADAR_EVAL_MIN_MOVE_PCT (défaut 1%)
  - volatilité médiane par horizon

Usage :
  python observation/horizon_evaluator.py --run             # calcule + stocke
  python observation/horizon_evaluator.py --report [DATE]   # relit un rapport
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from observation.market_observer import day_file, obs_dir, read_day  # noqa: E402
from observation.market_radar import shortlist_path  # noqa: E402

HORIZONS_S: dict[str, float] = {"15m": 900.0, "1h": 3600.0, "4h": 14400.0}
PALIERS = (50, 100, 200)
_TOL_FRAC = 0.35  # tolérance d'appariement autour de l'horizon (ticks 15 min)


def _f(value, default: float = 0.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if v == v else default


def _min_move_pct() -> float:
    return float(os.getenv("RADAR_EVAL_MIN_MOVE_PCT", "1.0"))


# ── Séries de prix depuis le pouls ─────────────────────────────────────────────


def series_by_symbol(
    records: list[dict], wanted: set[str]
) -> dict[str, list[tuple[float, float]]]:
    """Records du pouls → {sym: [(ts, last)] trié, dédupliqué par ts}."""
    raw: dict[str, dict[float, float]] = {}
    for r in records:
        sym = str(r.get("sym", ""))
        if sym not in wanted:
            continue
        ts, last = _f(r.get("ts")), _f(r.get("last"))
        if ts > 0 and last > 0:
            raw.setdefault(sym, {})[ts] = last
    return {sym: sorted(points.items()) for sym, points in raw.items()}


def forward_returns(series: list[tuple[float, float]], horizon_s: float) -> list[float]:
    """Rendements (%) entre chaque tick et le tick le plus proche de t+horizon."""
    if len(series) < 2:
        return []
    tol = horizon_s * _TOL_FRAC
    out: list[float] = []
    j = 0
    for i, (ts, price) in enumerate(series):
        target = ts + horizon_s
        j = max(j, i + 1)
        while j < len(series) and series[j][0] < target - tol:
            j += 1
        if j >= len(series):
            break
        ts_j, price_j = series[j]
        if abs(ts_j - target) <= tol and price > 0:
            out.append((price_j - price) / price * 100.0)
    return out


def persistence_1h(series: list[tuple[float, float]]) -> float | None:
    """Fraction de rendements 1h consécutifs (non chevauchants) de même signe."""
    rets = forward_returns(series[::4], HORIZONS_S["1h"])  # 1 tick sur 4 ≈ pas 1h
    signs = [1 if r > 0 else -1 for r in rets if r != 0]
    if len(signs) < 2:
        return None
    agree = sum(1 for a, b in zip(signs, signs[1:]) if a == b)
    return round(agree / (len(signs) - 1), 3)


def evaluate_symbol(series: list[tuple[float, float]]) -> dict:
    metrics: dict = {"n_ticks": len(series)}
    for name, horizon in HORIZONS_S.items():
        rets = forward_returns(series, horizon)
        if not rets:
            metrics[name] = {"n": 0}
            continue
        abs_rets = sorted(abs(r) for r in rets)
        metrics[name] = {
            "n": len(rets),
            "vol_pct": round(statistics.pstdev(rets), 4) if len(rets) > 1 else 0.0,
            "p50_abs": round(abs_rets[len(abs_rets) // 2], 4),
            "p90_abs": round(
                abs_rets[min(len(abs_rets) - 1, int(len(abs_rets) * 0.9))], 4
            ),
        }
    metrics["persistance_1h"] = persistence_1h(series)
    return metrics


# ── Agrégats par palier ────────────────────────────────────────────────────────


def palier_aggregates(
    shortlist: list[dict],
    evaluations: dict[str, dict],
    window_days: float,
    min_move_pct: float,
) -> dict[str, dict]:
    """Pour chaque palier top-K : opportunités/jour >= seuil et vol médiane."""
    out: dict[str, dict] = {}
    for k in PALIERS:
        syms = [e["sym"] for e in shortlist[:k]]
        moves = 0
        vols_1h: list[float] = []
        n_eval = 0
        for sym in syms:
            ev = evaluations.get(sym)
            if not ev:
                continue
            h4 = ev.get("4h", {})
            if h4.get("n", 0) > 0:
                n_eval += 1
                # approximation : P90 * n donne l'ordre de grandeur, mais on
                # compte directement les mouvements au-dessus du seuil
                moves += ev.get("_4h_ge_thr", 0)
            h1 = ev.get("1h", {})
            if h1.get("n", 0) > 1:
                vols_1h.append(h1["vol_pct"])
        out[f"top{k}"] = {
            "n_paires_evaluees": n_eval,
            "opportunites_par_jour": (
                round(moves / window_days, 1) if window_days > 0 else 0.0
            ),
            "vol_1h_mediane_pct": (
                round(statistics.median(vols_1h), 4) if vols_1h else None
            ),
        }
    return out


def _count_moves_ge(series: list[tuple[float, float]], thr_pct: float) -> int:
    """Mouvements 4h non chevauchants dont l'amplitude dépasse le seuil."""
    rets = forward_returns(series[::16], HORIZONS_S["4h"])  # pas ≈ 4h
    return sum(1 for r in rets if abs(r) >= thr_pct)


# ── Orchestration ──────────────────────────────────────────────────────────────


def run_evaluation(directory: Path | None = None, now: float | None = None) -> dict:
    directory = directory or obs_dir()
    now = now or time.time()
    today = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")
    min_move = _min_move_pct()

    # Shortlist du jour, sinon la plus récente disponible
    sl_path = shortlist_path(directory, today)
    if not sl_path.exists():
        candidates = sorted(directory.glob("radar_shortlist_*.json"))
        if not candidates:
            return {"error": "aucune shortlist radar disponible", "file": None}
        sl_path = candidates[-1]
    shortlist = json.loads(sl_path.read_text(encoding="utf-8")).get("shortlist", [])
    wanted = {e["sym"] for e in shortlist}

    since = now - 24 * 3600.0
    records: list[dict] = []
    for offset in (86400.0, 0.0):
        for r in read_day(day_file(directory, now - offset)):
            if _f(r.get("ts")) >= since:
                records.append(r)

    series = series_by_symbol(records, wanted)
    ticks = sorted({_f(r.get("ts")) for r in records if _f(r.get("ts")) > 0})
    window_days = (
        max(0.02, (ticks[-1] - ticks[0]) / 86400.0) if len(ticks) > 1 else 0.02
    )

    evaluations: dict[str, dict] = {}
    for sym, s in series.items():
        ev = evaluate_symbol(s)
        ev["_4h_ge_thr"] = _count_moves_ge(s, min_move)
        evaluations[sym] = ev

    payload = {
        "generated_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        "shortlist_file": str(sl_path),
        "window_days": round(window_days, 3),
        "min_move_pct": min_move,
        "n_symbols_evaluated": len(evaluations),
        "paliers": palier_aggregates(shortlist, evaluations, window_days, min_move),
        "symbols": {
            sym: {k: v for k, v in ev.items() if not k.startswith("_")}
            for sym, ev in evaluations.items()
        },
    }
    out_path = directory / f"horizon_eval_{today}.json"
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    payload["file"] = str(out_path)
    return payload


def render_report(payload: dict) -> str:
    if payload.get("error"):
        return f"R2 — {payload['error']}"
    lines = [
        "RADAR R2 — horizons sur la shortlist (fenêtre "
        f"{payload['window_days']:.1f} j, {payload['n_symbols_evaluated']} paires)",
        f"Seuil d'opportunité : mouvement |4h| >= {payload['min_move_pct']:.1f}%",
    ]
    for name, agg in payload.get("paliers", {}).items():
        opp = agg.get("opportunites_par_jour", 0.0)
        vol = agg.get("vol_1h_mediane_pct")
        lines.append(
            f"  {name:>6} : {agg.get('n_paires_evaluees', 0):>3} paires évaluées"
            f" | {opp:>7.1f} opportunités/jour"
            f" | vol 1h médiane {vol if vol is not None else '?'}%"
        )
    lines.append(
        "(mesure passive — l'élargissement de l'univers tradé reste une "
        "décision ADR-0017, seuils de régime inchangés)"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="R2 — évaluation à horizons de la shortlist radar (passif)"
    )
    parser.add_argument("--run", action="store_true", help="calcule et stocke")
    parser.add_argument(
        "--report", nargs="?", const="today", default=None, help="relit un rapport"
    )
    args = parser.parse_args(argv)

    directory = obs_dir()

    if args.run:
        payload = run_evaluation(directory)
        print(render_report(payload))
        if payload.get("file"):
            print(f"[r2] rapport -> {payload['file']}")
        return 0 if not payload.get("error") else 1

    day = (
        datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if args.report in (None, "today")
        else args.report
    )
    path = directory / f"horizon_eval_{day}.json"
    if not path.exists():
        print(f"Aucune évaluation R2 pour {day} ({path})")
        return 1
    print(render_report(json.loads(path.read_text(encoding="utf-8"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
