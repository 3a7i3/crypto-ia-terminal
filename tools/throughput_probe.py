"""
tools/throughput_probe.py — Sonde de débit de trading (audit passif, lecture seule).

Répond à la question opérateur (2026-07-14, famine de trading post-restart) :
« combien de trades/jour le système produirait-il à seuil X, avec quelle
qualité attendue, et en combien de temps atteindrait-il N=100 / N=500 ? »

Sources (déjà produites par les observateurs passifs — AUCUN impact moteur) :
  - databases/rejections/rejections_YYYY-MM-DD.jsonl  (RejectionStore)
  - databases/regret/regret_horizons_YYYY-MM-DD.jsonl (RegretScheduler)
  - databases/regret_analysis.jsonl                   (RegretEngine, legacy)
  - databases/paper_trades.jsonl                      (MexcSimulator, ledger)

Garde-fous scientifiques (règle du statisticien, CLAUDE.md) :
  - Le débit simulé est une BORNE HAUTE : seule la condition signal_score
    est simulée. Les autres conditions du gate (confirmation, régime,
    portfolio, score packet ~4-6 pts sous le score brut, cf. constat ETH
    70→66<72 du 2026-07-14) réduisent le débit réel.
  - La qualité est mesurée à horizon court (5m-1h après refus) : lecture
    directionnelle, PAS un backtest TP/SL.
  - Cet outil ne recommande AUCUN seuil et ne modifie RIEN : toute
    calibration reste une décision opérateur (N>=500, CRI>=90).

Usage :
    python tools/throughput_probe.py [--days 7] [--db databases] [--json]
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

# Racine du repo sur sys.path — même convention que tools/cri_calculator.py.
# Fallback cwd : permet l'exécution via stdin (audit ad hoc en SSH,
# `python - --days 7 < tools/throughput_probe.py`) où __file__ n'existe pas.
_REPO_ROOT = (
    Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd()
)
sys.path.insert(0, str(_REPO_ROOT))

THRESHOLD_GRID = [55, 58, 60, 62, 64, 66, 68, 72]
N_TARGETS = (100, 500)

# Horizon préféré pour la lecture qualité (le plus long disponible gagne)
_HORIZON_PREFERENCE = ["1h", "30m", "15m", "5m"]


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _f(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ── Chargement fenêtré ─────────────────────────────────────────────────────────


def load_rejections(db_dir: Path, since_ts: float) -> list[dict]:
    out: list[dict] = []
    for fp in sorted(glob.glob(str(db_dir / "rejections" / "rejections_*.jsonl"))):
        for r in _read_jsonl(Path(fp)):
            if _f(r.get("ts")) >= since_ts:
                out.append(r)
    return out


def _normalize_regret_horizons(record: dict) -> dict | None:
    """regret_horizons_*.jsonl → record commun. Prend l'horizon le plus long évalué."""
    horizons = record.get("horizons") or {}
    chosen = None
    for h in _HORIZON_PREFERENCE:
        if h in horizons and horizons[h]:
            chosen = horizons[h]
            break
    if chosen is None and horizons:
        chosen = next(iter(horizons.values()))
    if chosen is None:
        return None
    side = str(record.get("side", "")).upper()
    ret = _f(chosen.get("return_pct"))
    return {
        "ts": _f(record.get("ts_signal")),
        "symbol": record.get("symbol", "?"),
        "side": side,
        "score": _f(record.get("score")),
        "regime": record.get("regime", "unknown"),
        "ret_if_followed": ret if side == "BUY" else -ret,
        "direction_ok": bool(chosen.get("direction_ok", False)),
        "regret_type": str(chosen.get("regret_type", "NEUTRAL")),
        "horizon": str(chosen.get("horizon", "?")),
    }


def _normalize_regret_legacy(record: dict) -> dict | None:
    """regret_analysis.jsonl (schéma plat) → record commun."""
    if "potential_pnl_pct" not in record:
        return None
    side = str(record.get("signal", record.get("side", ""))).upper()
    return {
        "ts": _f(record.get("ts_signal")),
        "symbol": record.get("symbol", "?"),
        "side": side,
        "score": _f(record.get("score")),
        "regime": record.get("regime", "unknown"),
        "ret_if_followed": _f(record.get("potential_pnl_pct")),
        "direction_ok": bool(record.get("direction_correct", False)),
        "regret_type": str(record.get("regret_type", "NEUTRAL")),
        "horizon": "eval",
    }


def load_regrets(db_dir: Path, since_ts: float) -> list[dict]:
    out: list[dict] = []
    for fp in sorted(glob.glob(str(db_dir / "regret" / "regret_horizons_*.jsonl"))):
        for r in _read_jsonl(Path(fp)):
            norm = _normalize_regret_horizons(r)
            if norm and norm["ts"] >= since_ts:
                out.append(norm)
    if not out:  # fallback legacy (fichier unique, peut être volumineux)
        for r in _read_jsonl(db_dir / "regret_analysis.jsonl"):
            norm = _normalize_regret_legacy(r)
            if norm and norm["ts"] >= since_ts:
                out.append(norm)
    return out


def load_trades_window(db_dir: Path, since_ts: float) -> dict:
    opens, closes = 0, 0
    for r in _read_jsonl(db_dir / "paper_trades.jsonl"):
        if _f(r.get("ts")) < since_ts:
            continue
        if r.get("event") == "OPEN":
            opens += 1
        elif r.get("event") == "CLOSE":
            closes += 1
    return {"opens": opens, "closes": closes}


def canonical_n(db_dir: Path) -> int:
    """N canonique (borne CLEAN_DATA_SINCE_ACTIVE) — même source que le CRI."""
    try:
        from tools.cri_calculator import load_clean_trades

        return len(load_clean_trades(db_dir / "paper_trades.jsonl"))
    except Exception:
        return -1  # indisponible (l'outil reste utilisable pour le débit)


# ── Analyses pures (testables) ─────────────────────────────────────────────────


def distinct_opportunities_per_day(records: list[dict]) -> dict[str, set]:
    """{jour: {(symbol, side)}} — le même setup re-signalé chaque cycle de
    5 min ne compte qu'une fois par jour (constat 2026-07-14 : 21 signaux
    'ETH 70' en 26h = une seule opportunité, pas 21 trades potentiels)."""
    days: dict[str, set] = defaultdict(set)
    for r in records:
        ts = _f(r.get("ts"))
        if ts <= 0:
            continue
        day = time.strftime("%Y-%m-%d", time.gmtime(ts))
        days[day].add((r.get("symbol", "?"), str(r.get("side", "?")).upper()))
    return days


def simulated_throughput(
    rejections: list[dict], n_days: float, thresholds: list[int]
) -> dict[int, dict]:
    """Par seuil X : signaux bruts/jour et opportunités distinctes/jour
    dont score >= X. BORNE HAUTE (seule la condition signal_score simulée)."""
    out: dict[int, dict] = {}
    for thr in thresholds:
        eligible = [r for r in rejections if _f(r.get("score")) >= thr]
        days = distinct_opportunities_per_day(eligible)
        distinct_total = sum(len(v) for v in days.values())
        out[thr] = {
            "signals_per_day": len(eligible) / n_days if n_days > 0 else 0.0,
            "distinct_per_day": distinct_total / n_days if n_days > 0 else 0.0,
        }
    return out


def quality_at_threshold(regrets: list[dict], threshold: float) -> dict:
    """Parmi les refus évalués (regret) avec score >= seuil : direction,
    espérance brute à l'horizon d'évaluation, répartition regret_type."""
    sel = [r for r in regrets if _f(r.get("score")) >= threshold]
    n = len(sel)
    if n == 0:
        return {"n": 0}
    direction_ok = sum(1 for r in sel if r.get("direction_ok"))
    rets = [_f(r.get("ret_if_followed")) for r in sel]
    types: dict[str, int] = defaultdict(int)
    for r in sel:
        types[str(r.get("regret_type", "NEUTRAL"))] += 1
    return {
        "n": n,
        "direction_ok_pct": 100.0 * direction_ok / n,
        "mean_ret_pct": 100.0 * sum(rets) / n,
        "types": dict(types),
    }


def days_to_target(distinct_per_day: float, current_n: int, target: int) -> float:
    remaining = max(0, target - max(0, current_n))
    if remaining == 0:
        return 0.0
    if distinct_per_day <= 0:
        return float("inf")
    return remaining / distinct_per_day


# ── Rendu ──────────────────────────────────────────────────────────────────────


def render_report(
    *,
    n_days: float,
    trades: dict,
    rejections: list[dict],
    regrets: list[dict],
    n_canonical: int,
    thresholds: list[int],
) -> str:
    sim = simulated_throughput(rejections, n_days, thresholds)
    lines = [
        "SONDE DE DÉBIT — audit passif (lecture seule, aucune action moteur)",
        "━" * 66,
        f"Fenêtre analysée : {n_days:.1f} jour(s)"
        f" | Refus loggés : {len(rejections)}"
        f" | Refus évalués (regret) : {len(regrets)}",
        "",
        "DÉBIT OBSERVÉ",
        (
            f"  Trades exécutés : {trades['opens']} ouverts, {trades['closes']} fermés"
            f" ({trades['closes'] / n_days:.1f} clôture(s)/jour)"
            if n_days > 0
            else "  (fenêtre vide)"
        ),
        f"  N canonique actuel : {n_canonical if n_canonical >= 0 else 'indisponible'}",
        "",
        "DÉBIT SIMULÉ PAR SEUIL — BORNE HAUTE (seule la condition signal_score",
        "simulée ; confirmation/portfolio/score packet réduiraient le réel)",
        f"  {'Seuil':>5} | {'signaux/j':>9} | {'opportunités distinctes/j':>25}"
        + (" | jours→N=100 | jours→N=500" if n_canonical >= 0 else ""),
    ]
    for thr in thresholds:
        s = sim[thr]
        row = (
            f"  {thr:>5} | {s['signals_per_day']:>9.1f}"
            f" | {s['distinct_per_day']:>25.1f}"
        )
        if n_canonical >= 0:
            d100 = days_to_target(s["distinct_per_day"], n_canonical, 100)
            d500 = days_to_target(s["distinct_per_day"], n_canonical, 500)
            row += (
                f" | {d100:>11.0f} | {d500:>11.0f}"
                if d100 != float("inf")
                else f" | {'jamais':>11} | {'jamais':>11}"
            )
        lines.append(row)
    lines += [
        "",
        "QUALITÉ ATTENDUE PAR SEUIL — refus évalués a posteriori (RegretEngine)",
        "Lecture directionnelle à horizon court (5m-1h), PAS un backtest TP/SL :",
    ]
    for thr in thresholds:
        q = quality_at_threshold(regrets, thr)
        if q["n"] == 0:
            lines.append(f"  >= {thr:>3} : aucun refus évalué dans la fenêtre")
            continue
        types = q["types"]
        lines.append(
            f"  >= {thr:>3} : n={q['n']:>4}"
            f" | direction correcte {q['direction_ok_pct']:.0f}%"
            f" | espérance brute {q['mean_ret_pct']:+.2f}%"
            f" | MISSED_WIN={types.get('MISSED_WIN', 0)}"
            f" GOOD_REFUSAL={types.get('GOOD_REFUSAL', 0)}"
            f" NEUTRAL={types.get('NEUTRAL', 0)}"
        )
    lines += [
        "",
        "GARDE-FOUS (règle du statisticien, CLAUDE.md)",
        "  - Ces chiffres DÉCRIVENT, ils ne recommandent aucun seuil.",
        "  - Toute calibration reste une décision opérateur : N>=500, CRI>=90.",
        "  - Une 'opportunité distincte' = (symbole, sens) par jour — le même",
        "    setup re-signalé chaque cycle ne compte qu'une fois.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sonde de débit (audit passif)")
    parser.add_argument("--days", type=float, default=7.0, help="fenêtre en jours")
    parser.add_argument("--db", default="databases", help="répertoire databases/")
    parser.add_argument("--json", action="store_true", help="sortie JSON brute")
    args = parser.parse_args(argv)

    db_dir = Path(args.db)
    since_ts = time.time() - args.days * 86400.0

    rejections = load_rejections(db_dir, since_ts)
    regrets = load_regrets(db_dir, since_ts)
    trades = load_trades_window(db_dir, since_ts)
    n_can = canonical_n(db_dir)

    if args.json:
        payload = {
            "window_days": args.days,
            "trades": trades,
            "n_canonical": n_can,
            "simulated": simulated_throughput(rejections, args.days, THRESHOLD_GRID),
            "quality": {
                thr: quality_at_threshold(regrets, thr) for thr in THRESHOLD_GRID
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(
        render_report(
            n_days=args.days,
            trades=trades,
            rejections=rejections,
            regrets=regrets,
            n_canonical=n_can,
            thresholds=THRESHOLD_GRID,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
