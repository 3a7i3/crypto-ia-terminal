"""
counterfactual_replay.py — Replay contrefactuel avec contrainte max_positions.

Répond à : si MetaStrategyEngine.max_positions avait été appliqué au MexcSimulator,
quel PF aurait été obtenu ?

Contexte du bug :
  - advisor_loop.py:4789 passe open_positions=pos_manager.get_open() (positions live)
  - En paper trading, pos_manager est toujours vide → MetaStrategyEngine voit 0 pos
  - MexcSimulator reçoit TOUS les signaux gate_allowed, sans limite globale de positions
  - Seule contrainte effective : 1 position par symbole (MexcSim._fill_market ligne 547)

Contraintes max_positions réelles (meta_strategy_engine.py) :
  mean_reversion  (sideways / bear_trend) → max 2 positions simultanées
  momentum        (bull_trend)            → max 3 positions simultanées
  scalping_mode   (high_volatility)       → max 1 position simultanée
  neutral         (unknown)               → max 2 positions simultanées

Usage:
    python scripts/counterfactual_replay.py
    python scripts/counterfactual_replay.py --jsonl databases/paper_trades.jsonl
    python scripts/counterfactual_replay.py --window 360 --since-ts 0
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Début burn-in v2 (post-6ce7fc2)
BURNIN_V2_START_TS: float = 1_782_025_920.0

# Contraintes max_positions par régime — miroir de meta_strategy_engine.py
_REGIME_MAX: dict[str, int] = {
    "sideways": 2,
    "RANGE": 2,
    "bear_trend": 2,
    "TREND_BEAR": 2,
    "bull_trend": 3,
    "TREND_BULL": 3,
    "high_volatility_regime": 1,
    "VOLATILE": 1,
    "flash_crash": 0,
    "unknown": 2,
    "UNKNOWN": 2,
}
_DEFAULT_MAX = 2


def regime_max(regime: str) -> int:
    return _REGIME_MAX.get(regime, _DEFAULT_MAX)


# ── Chargement ──────────────────────────────────────────────────────────────────


def load_trades(path: Path, since_ts: float) -> list[dict]:
    """
    Charge les trades CLOSE complets post-since_ts.
    Enrichit chaque trade avec les données de l'OPEN correspondant (score, regime).
    """
    opens: dict[str, dict] = {}
    closes: dict[str, dict] = {}

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = ev.get("ts", 0.0)
            tid = ev.get("trade_id", "") or ev.get("pos_id", "")
            event = ev.get("event", "")
            if event == "OPEN" and ts >= since_ts:
                opens[tid] = ev
            elif event == "CLOSE":
                closes[tid] = ev

    trades = []
    for tid, cl in closes.items():
        op = opens.get(tid)
        if op is None:
            continue
        opened_at = op.get("ts", 0.0) or cl.get("opened_at", 0.0)
        closed_at = cl.get("ts", 0.0)
        trades.append(
            {
                "trade_id": tid,
                "symbol": op.get("symbol", cl.get("symbol", "")),
                "side": (op.get("side") or cl.get("side") or "?").upper(),
                "opened_at": opened_at,
                "closed_at": closed_at,
                "pnl_usd": cl.get("pnl_usd") or 0.0,
                "pnl_pct": cl.get("pnl_pct") or 0.0,
                "score": int(op.get("score") or cl.get("score") or 0),
                "regime": op.get("regime") or cl.get("regime") or "unknown",
                "reason": cl.get("reason") or "?",
                "mfe_pct": cl.get("mfe_pct"),
                "mae_pct": cl.get("mae_pct"),
            }
        )
    return sorted(trades, key=lambda t: t["opened_at"])


# ── Simulation contrefactuelle ──────────────────────────────────────────────────


def assign_buckets(trades: list[dict], window_s: float) -> list[dict]:
    """
    Groupe les trades par fenêtre temporelle (≈ durée d'un cycle).
    Les trades d'un même bucket ont ouvert dans la même fenêtre.
    """
    if not trades:
        return trades
    bucket_id = 0
    bucket_start = trades[0]["opened_at"]
    for t in trades:
        if t["opened_at"] > bucket_start + window_s:
            bucket_start = t["opened_at"]
            bucket_id += 1
        t["_bucket"] = bucket_id
    return trades


def run_counterfactual(
    trades: list[dict], window_s: float
) -> tuple[list[dict], list[dict]]:
    """
    Simule la politique max_positions sur les trades exécutés.

    Algorithme :
      Pour chaque fenêtre (≈ cycle) par ordre chronologique :
        1. Ferme les positions ouvertes dont closed_at <= fenêtre actuelle
        2. Calcule les slots disponibles = max_positions - n_open
        3. Trie les trades de la fenêtre par score décroissant
        4. Sélectionne les top-N (N = slots) ; rejette les autres

    Retourne (sélectionnés, éjectés).
    """
    trades = assign_buckets(trades, window_s)
    buckets: dict[int, list[dict]] = defaultdict(list)
    for t in trades:
        buckets[t["_bucket"]].append(t)

    open_pos: list[dict] = []  # positions actuellement ouvertes (dans le CF)
    selected: list[dict] = []
    dropped: list[dict] = []

    for bid in sorted(buckets.keys()):
        batch = sorted(buckets[bid], key=lambda t: t["score"], reverse=True)
        bucket_ts = batch[0]["opened_at"]

        # Fermer les positions expirées avant ce bucket
        open_pos = [p for p in open_pos if p["closed_at"] > bucket_ts]

        # Régime majoritaire dans ce batch
        regimes = [t["regime"] for t in batch]
        majority_regime = max(set(regimes), key=regimes.count)
        max_pos = regime_max(majority_regime)

        n_slots = max(0, max_pos - len(open_pos))

        for i, trade in enumerate(batch):
            if i < n_slots:
                selected.append(trade)
                open_pos.append(trade)
            else:
                trade["_drop_reason"] = (
                    f"slot_limit ({len(open_pos)}/{max_pos} {majority_regime})"
                )
                dropped.append(trade)

    return selected, dropped


# ── Métriques ───────────────────────────────────────────────────────────────────


def profit_factor(pnls: list[float]) -> float:
    wins = sum(p for p in pnls if p > 0)
    losses = abs(sum(p for p in pnls if p < 0))
    return wins / losses if losses > 0 else float("inf")


def pf_str(pf: float) -> str:
    return f"{pf:.3f}" if pf != float("inf") else "∞"


def metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "wr": 0, "pf": 0, "exp": 0, "total": 0}
    pnls = [t["pnl_usd"] for t in trades]
    n = len(pnls)
    wins = [p for p in pnls if p > 0]
    return {
        "n": n,
        "wr": len(wins) / n * 100,
        "pf": profit_factor(pnls),
        "exp": sum(pnls) / n,
        "total": sum(pnls),
    }


# ── Rapport ──────────────────────────────────────────────────────────────────────


def report(
    all_trades: list[dict],
    selected: list[dict],
    dropped: list[dict],
    window_s: float,
) -> None:
    m_all = metrics(all_trades)
    m_sel = metrics(selected)
    m_drp = metrics(dropped)

    print(f"\n{'='*62}")
    print(f"  REPLAY CONTREFACTUEL — max_positions MetaStrategyEngine")
    print(f"{'='*62}")
    print(f"  Fenêtre bucket : {window_s:.0f}s (~{window_s/60:.1f} min / cycle)")

    # Tableau comparatif principal
    print(f"\n{'─'*62}")
    print(f"  {'Métrique':<22} {'Réel (bug)':>13} {'CF (max_pos)':>13} {'Éjectés':>10}")
    print(f"{'─'*62}")
    print(f"  {'N trades':<22} {m_all['n']:>13d} {m_sel['n']:>13d} {m_drp['n']:>10d}")
    wr_line = (
        f"  {'Win Rate':<22}"
        f" {m_all['wr']:>12.1f}%"
        f" {m_sel['wr']:>12.1f}%"
        f" {m_drp['wr']:>9.1f}%"
    )
    pf_line = (
        f"  {'Profit Factor':<22}"
        f" {pf_str(m_all['pf']):>13}"
        f" {pf_str(m_sel['pf']):>13}"
        f" {pf_str(m_drp['pf']):>10}"
    )
    exp_line = (
        f"  {'Expectancy USD':<22}"
        f" {m_all['exp']:>+12.4f}$"
        f" {m_sel['exp']:>+12.4f}$"
        f" {m_drp['exp']:>+9.4f}$"
    )
    pnl_line = (
        f"  {'PnL total':<22}"
        f" {m_all['total']:>+12.2f}$"
        f" {m_sel['total']:>+12.2f}$"
        f" {m_drp['total']:>+9.2f}$"
    )
    print(wr_line)
    print(pf_line)
    print(exp_line)
    print(pnl_line)

    # Par régime
    print(f"\n{'─'*62}")
    print(f"  IMPACT PAR RÉGIME")
    print(f"{'─'*62}")
    by_reg_all: dict[str, list[float]] = defaultdict(list)
    by_reg_sel: dict[str, list[float]] = defaultdict(list)
    for t in all_trades:
        by_reg_all[t["regime"]].append(t["pnl_usd"])
    for t in selected:
        by_reg_sel[t["regime"]].append(t["pnl_usd"])

    all_regs = sorted(by_reg_all, key=lambda r: -len(by_reg_all[r]))
    print(
        f"  {'Régime':<26} {'N réel':>7} {'PF réel':>8} "
        f"{'N CF':>6} {'PF CF':>8} {'max_pos':>7}"
    )
    print(f"  {'-'*62}")
    for reg in all_regs:
        ra = by_reg_all.get(reg, [])
        rc = by_reg_sel.get(reg, [])
        mp = regime_max(reg)
        print(
            f"  {reg:<26} {len(ra):>7d} {pf_str(profit_factor(ra)):>8} "
            f"{len(rc):>6d} {pf_str(profit_factor(rc)):>8} {mp:>7d}"
        )

    # Par score bucket
    print(f"\n{'─'*62}")
    print(f"  RÉPARTITION PAR SCORE (réel vs contrefactuel)")
    print(f"{'─'*62}")
    score_all: dict[int, list[float]] = defaultdict(list)
    score_sel: dict[int, list[float]] = defaultdict(list)
    for t in all_trades:
        b = (t["score"] // 5) * 5
        score_all[b].append(t["pnl_usd"])
    for t in selected:
        b = (t["score"] // 5) * 5
        score_sel[b].append(t["pnl_usd"])

    print(f"  {'Score':>7} {'N réel':>8} {'PF réel':>9} {'N CF':>7} {'PF CF':>9}")
    for b in sorted(set(score_all) | set(score_sel)):
        ra = score_all.get(b, [])
        rc = score_sel.get(b, [])
        print(
            f"  {b:3d}-{b+4:3d} {len(ra):>8d} {pf_str(profit_factor(ra)):>9} "
            f"{len(rc):>7d} {pf_str(profit_factor(rc)):>9}"
        )

    # MFE / MAE (qualité du signal — indépendant du max_positions)
    mfe_vals = [t["mfe_pct"] for t in all_trades if t.get("mfe_pct") is not None]
    mae_vals = [t["mae_pct"] for t in all_trades if t.get("mae_pct") is not None]
    tout_t = [t for t in all_trades if t["reason"] == "TIMEOUT"]
    sl_t = [t for t in all_trades if t["reason"] == "SL"]
    tp_t = [t for t in all_trades if t["reason"] == "TP"]

    if mfe_vals:
        print(f"\n{'─'*62}")
        print(f"  MFE / MAE — QUALITÉ DU SIGNAL (tous trades)")
        print(f"{'─'*62}")
        avg_mfe = sum(mfe_vals) / len(mfe_vals)
        avg_mae = sum(mae_vals) / len(mae_vals) if mae_vals else 0
        print(
            f"  Global N={len(mfe_vals)}"
            f"  avg MFE: {avg_mfe:+.2f}%"
            f"  avg MAE: {avg_mae:+.2f}%"
        )

        for label, subset in [("SL", sl_t), ("TP", tp_t), ("TIMEOUT", tout_t)]:
            if not subset:
                continue
            s_mfe = [t["mfe_pct"] for t in subset if t.get("mfe_pct") is not None]
            s_mae = [t["mae_pct"] for t in subset if t.get("mae_pct") is not None]
            s_pnl = [t["pnl_usd"] for t in subset]
            avg_pnl = sum(s_pnl) / len(s_pnl) if s_pnl else 0
            avg_s_mfe = sum(s_mfe) / len(s_mfe) if s_mfe else 0
            avg_s_mae = sum(s_mae) / len(s_mae) if s_mae else 0

            # Diagnostic sortie défaillante : MFE >> |PnL| → le signal était bon
            mfe_gt_loss = (
                sum(
                    1
                    for t in subset
                    if (t.get("mfe_pct") or 0) > abs(t.get("pnl_pct") or 0) * 1.5
                )
                if subset
                else 0
            )
            leak_pct = mfe_gt_loss / len(subset) * 100 if subset else 0

            print(
                f"  {label:<8} N={len(subset):>3}  "
                f"avg MFE:{avg_s_mfe:>+7.2f}%  avg MAE:{avg_s_mae:>+7.2f}%  "
                f"avg PnL:{avg_pnl:>+7.4f}$  "
                f"MFE>|PnL|×1.5: {leak_pct:.0f}%"
            )

    # Top trades éjectés (les plus impactants)
    if dropped:
        print(f"\n{'─'*62}")
        print(f"  TOP TRADES ÉJECTÉS (par |PnL|)")
        print(f"{'─'*62}")
        top_drop = sorted(dropped, key=lambda t: abs(t["pnl_usd"]), reverse=True)[:10]
        print(
            f"  {'Symbol':<22} {'Side':>4} {'Score':>6} {'PnL':>9} "
            f"{'Reason':>8} {'Drop raison'}"
        )
        for t in top_drop:
            print(
                f"  {t['symbol']:<22} {t['side']:>4} {t['score']:>6d} "
                f"{t['pnl_usd']:>+8.4f}$ {t['reason']:>8}  "
                f"{t.get('_drop_reason', '')}"
            )

    # Verdict
    print(f"\n{'='*62}")
    go_real = m_all["pf"] > 1.20 and m_all["exp"] > 0
    go_cf = m_sel["pf"] > 1.20 and m_sel["exp"] > 0

    if not go_real and not go_cf:
        pf_r, pf_c = pf_str(m_all["pf"]), pf_str(m_sel["pf"])
        print(f"  [STABLE NO-GO] PF réel={pf_r}  PF CF={pf_c}")
        print(f"  → Alpha insuffisant indépendamment du bug max_positions.")
    elif not go_real and go_cf:
        pf_r, pf_c = pf_str(m_all["pf"]), pf_str(m_sel["pf"])
        print(f"  [SHIFT] PF réel={pf_r} NO-GO → PF CF={pf_c} GO")
        print(f"  → Bypass max_positions a faussé le verdict :")
        print(f"    les meilleurs signaux sont rentables ; dilution détruit l'edge.")
    elif go_real and not go_cf:
        pf_r, pf_c = pf_str(m_all["pf"]), pf_str(m_sel["pf"])
        print(f"  [INVERSE] PF réel={pf_r} GO → PF CF={pf_c} NO-GO")
        print(f"  → Les meilleurs signaux sont MOINS bons que la moyenne.")
    else:
        pf_r, pf_c = pf_str(m_all["pf"]), pf_str(m_sel["pf"])
        print(f"  [STABLE GO] PF réel={pf_r}  PF CF={pf_c}")
    print()


# ── Main ─────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay contrefactuel max_positions MexcSimulator"
    )
    parser.add_argument(
        "--jsonl",
        default="databases/paper_trades.jsonl",
        help="Chemin vers paper_trades.jsonl",
    )
    parser.add_argument(
        "--since-ts",
        type=float,
        default=BURNIN_V2_START_TS,
        help="Timestamp Unix de début (défaut: BURNIN_V2_START_TS)",
    )
    parser.add_argument(
        "--window",
        type=float,
        default=360.0,
        help="Durée d'un bucket/cycle en secondes (défaut: 360s = 6 min)",
    )
    args = parser.parse_args()

    path = Path(args.jsonl)
    if not path.exists():
        print(f"[Erreur] Fichier introuvable : {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Chargement trades depuis {path}...", end=" ", flush=True)
    trades = load_trades(path, args.since_ts)
    print(f"{len(trades)} trades fermés.")

    if not trades:
        print("[Erreur] Aucun trade fermé trouvé après since_ts.", file=sys.stderr)
        sys.exit(1)

    selected, dropped = run_counterfactual(trades, args.window)

    report(trades, selected, dropped, args.window)


if __name__ == "__main__":
    main()
