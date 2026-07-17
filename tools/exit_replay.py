"""
tools/exit_replay.py — exit_audit v2 : rejeu du CHEMIN exact depuis le pouls.

v1 (tools/exit_audit.py) a réfuté le remède naïf « baisser le TP » mais ne
pouvait pas tester la DÉFENSE (SL/timeout/break-even) : MAE/MFE ne donnent
pas l'ordre des excursions. v2 le peut : pour chaque trade de l'époque V4,
le pouls (market_pulse, 15 min, ADR-0016) contient le chemin de prix réel —
on rejoue donc chaque trade sous une grille de géométries de sortie
complètes et on mesure l'espérance nette de chacune.

Grille (72 politiques) :
  TP       : 0.8 / 1.5 / 3.0 % / aucun
  SL       : 0.8 / 1.5 / 2.5 %
  Break-even : off / armé à +0.5% (stop remonté à l'entrée)
  Timeout  : 4 / 12 / 48 h

Limites assumées (honnêteté du modèle) :
  - Résolution 15 min : les excursions intra-tick sont invisibles — les
    touches TP ET SL entre deux ticks sont manquées des deux côtés ;
    si un même tick franchit TP et SL à la fois, on prend le SL (pessimiste).
  - Sorties supposées exécutées au niveau exact (pas de gap) — optimiste
    d'un cran sur les SL, symétrique pour toutes les politiques comparées.
  - Trades trop récents pour couvrir le timeout : sortis au dernier tick
    connu (comptés `n_fin_donnees`).
  - Cet outil DÉCRIT ; tout changement réel de TP/SL/timeout = ADR + règle
    du statisticien.

Usage :
  python tools/exit_replay.py [--top 10] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = (
    Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd()
)
sys.path.insert(0, str(_REPO_ROOT))

TP_GRID = [0.8, 1.5, 3.0, None]
SL_GRID = [0.8, 1.5, 2.5]
BE_GRID = [None, 0.5]
TIMEOUT_H_GRID = [4.0, 12.0, 48.0]


def _f(value, default: float = 0.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if v == v else default


@dataclass(frozen=True)
class ExitPolicy:
    tp_pct: float | None
    sl_pct: float
    be_arm_pct: float | None
    timeout_h: float

    def label(self) -> str:
        tp = f"TP{self.tp_pct:.1f}" if self.tp_pct else "TPnone"
        be = f"BE{self.be_arm_pct:.1f}" if self.be_arm_pct else "BEoff"
        return f"{tp}/SL{self.sl_pct:.1f}/{be}/T{self.timeout_h:.0f}h"


def policy_grid() -> list[ExitPolicy]:
    return [
        ExitPolicy(tp, sl, be, to)
        for tp in TP_GRID
        for sl in SL_GRID
        for be in BE_GRID
        for to in TIMEOUT_H_GRID
    ]


def signed_return_pct(side: str, entry_price: float, price: float) -> float:
    """Rendement signé du point de vue du trade (SELL inversé)."""
    if entry_price <= 0:
        return 0.0
    raw = (price - entry_price) / entry_price * 100.0
    return raw if str(side).lower() in ("buy", "long") else -raw


def replay_trade(
    path: list[tuple[float, float]],
    side: str,
    entry_ts: float,
    entry_price: float,
    policy: ExitPolicy,
    cost_pct: float,
) -> tuple[str, float]:
    """Rejoue un trade sur son chemin de prix. Retourne (raison, net_pct).

    Ordre par tick : SL d'abord (pessimiste si TP et SL franchis au même
    tick 15 min), puis TP, puis timeout.
    """
    stop = -policy.sl_pct
    deadline = entry_ts + policy.timeout_h * 3600.0
    last_ret = 0.0
    for ts, price in path:
        if ts < entry_ts:
            continue
        ret = signed_return_pct(side, entry_price, price)
        if ret <= stop:
            return "SL", stop - cost_pct
        if policy.tp_pct is not None and ret >= policy.tp_pct:
            return "TP", policy.tp_pct - cost_pct
        if policy.be_arm_pct is not None and ret >= policy.be_arm_pct:
            stop = max(stop, 0.0)  # stop remonté à l'entrée
        if ts >= deadline:
            return "TIMEOUT", ret - cost_pct
        last_ret = ret
    return "FIN_DONNEES", last_ret - cost_pct


# ── Chargement des trades V4 + chemins depuis le pouls ─────────────────────────


def load_v4_trades(trades_path: Path) -> list[dict]:
    """CLOSE de l'époque active joints à leur OPEN (entry ts + prix)."""
    from tools.cri_calculator import _read_jsonl, load_clean_trades

    opens = {
        d.get("trade_id"): d
        for d in _read_jsonl(trades_path)
        if d.get("event") == "OPEN"
    }
    out = []
    for c in load_clean_trades(trades_path):
        o = opens.get(c.get("trade_id"))
        if not o:
            continue
        out.append(
            {
                "trade_id": c.get("trade_id"),
                "symbol": c.get("symbol"),
                "side": o.get("side", c.get("side", "buy")),
                "entry_ts": _f(o.get("ts")),
                "entry_price": _f(o.get("price")),
                "actual_net_pct": (
                    100.0 * _f(c.get("pnl_usd")) / _f(c.get("size_usd"))
                    if _f(c.get("size_usd")) > 0
                    else 0.0
                ),
            }
        )
    return out


def load_paths(
    symbols: set[str], t_min: float, t_max: float
) -> dict[str, list[tuple[float, float]]]:
    """Séries (ts, last) spot par symbole depuis les fichiers du pouls."""
    from observation.market_observer import day_file, obs_dir, read_day

    directory = obs_dir()
    series: dict[str, dict[float, float]] = {s: {} for s in symbols}
    day = t_min - 86400.0
    while day <= t_max + 86400.0:
        for r in read_day(day_file(directory, day)):
            sym = r.get("sym")
            if sym in series and r.get("mkt") == "spot":
                ts, last = _f(r.get("ts")), _f(r.get("last"))
                if t_min - 900 <= ts <= t_max and last > 0:
                    series[sym][ts] = last
        day += 86400.0
    return {s: sorted(pts.items()) for s, pts in series.items()}


def run_replay(trades_path: Path | None = None) -> dict:
    from tools.exit_audit import roundtrip_cost_pct

    trades_path = trades_path or Path("databases/paper_trades.jsonl")
    trades = load_v4_trades(trades_path)
    if not trades:
        return {"error": "aucun trade V4 joignable (OPEN+CLOSE)"}

    cost = roundtrip_cost_pct()
    max_to = max(TIMEOUT_H_GRID) * 3600.0
    t_min = min(t["entry_ts"] for t in trades)
    t_max = min(time.time(), max(t["entry_ts"] for t in trades) + max_to)
    paths = load_paths({t["symbol"] for t in trades}, t_min, t_max)

    usable = [t for t in trades if len(paths.get(t["symbol"], [])) >= 4]
    results = []
    for pol in policy_grid():
        total = 0.0
        wins = reasons_eod = 0
        for t in usable:
            reason, net = replay_trade(
                paths[t["symbol"]],
                t["side"],
                t["entry_ts"],
                t["entry_price"],
                pol,
                cost,
            )
            total += net
            wins += 1 if net > 0 else 0
            reasons_eod += 1 if reason == "FIN_DONNEES" else 0
        n = max(1, len(usable))
        results.append(
            {
                "policy": pol.label(),
                "esperance_nette_pct": round(total / n, 4),
                "wr_pct": round(100.0 * wins / n, 1),
                "n_fin_donnees": reasons_eod,
            }
        )
    results.sort(key=lambda r: -r["esperance_nette_pct"])
    actual = sum(t["actual_net_pct"] for t in usable) / max(1, len(usable))
    return {
        "n_trades_v4": len(trades),
        "n_rejouables": len(usable),
        "cout_aller_retour_pct": round(cost, 3),
        "esperance_reelle_pct": round(actual, 4),
        "resolution": "ticks 15 min (pouls ADR-0016)",
        "politiques": results,
    }


def render_report(r: dict, top: int = 10) -> str:
    if r.get("error"):
        return f"exit_replay — {r['error']}"
    lines = [
        "REJEU DES SORTIES (v2, chemin exact 15 min) — époque V4",
        f"  {r['n_rejouables']} trades rejouables / {r['n_trades_v4']}"
        f" | coût: {r['cout_aller_retour_pct']:.2f}%"
        f" | espérance RÉELLE: {r['esperance_reelle_pct']:+.3f}%/trade",
        "",
        f"  {'Politique':<28} {'esp. nette':>10} {'WR':>6} {'fin_données':>11}",
    ]
    for p in r["politiques"][:top]:
        lines.append(
            f"  {p['policy']:<28} {p['esperance_nette_pct']:>+9.3f}%"
            f" {p['wr_pct']:>5.0f}% {p['n_fin_donnees']:>11}"
        )
    lines.append("  …")
    for p in r["politiques"][-3:]:
        lines.append(
            f"  {p['policy']:<28} {p['esperance_nette_pct']:>+9.3f}%"
            f" {p['wr_pct']:>5.0f}% {p['n_fin_donnees']:>11}"
        )
    lines += [
        "",
        "  Rappel : description, pas réglage — changement réel = ADR + règle",
        "  du statisticien. Relancer chaque jour : N(V4) grossit de ~17/j.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="exit_audit v2 — rejeu du chemin")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = run_replay()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(render_report(result, top=args.top))
    return 0 if not result.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
