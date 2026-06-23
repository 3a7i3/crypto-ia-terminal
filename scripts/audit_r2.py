#!/usr/bin/env python3
"""
AUDIT-R2 — Diagnostic quantitatif complet du burn-in.

Complète burnin_v2_report.py avec les 3 dimensions manquantes :
  1. PF par régime × score (cross-table)
  2. Distribution réelle des régimes depuis 4f77935 (via cycle_data)
  3. Trades filtrés par RECOVERY : analyse gate_reason + delta implicite

Usage :
    python -X utf8 scripts/audit_r2.py
    python -X utf8 scripts/audit_r2.py --jsonl /path/vps/paper_trades.jsonl
    python -X utf8 scripts/audit_r2.py --jsonl /path/vps/paper_trades.jsonl \
                                        --cycle-data /path/vps/cycle_data.jsonl
    python -X utf8 scripts/audit_r2.py --since-ts 0   # tous les trades
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Timestamp du fix 4f77935 (2026-06-12 00:17:10 -0700 = 07:17:10 UTC)
FIX_4F77935_TS: float = 1_749_716_230.0
# Timestamp du deploy VPS b249857 (~2026-06-15)
DEPLOY_VPS_TS: float = 1_749_974_400.0
# Timestamp du fix synthétique 6ce7fc2 (2026-06-21 07:32:00 UTC)
BURNIN_V2_START_TS: float = 1_782_025_920.0

SCORE_BUCKETS = [
    ("55-59", 55, 60),
    ("60-64", 60, 65),
    ("65-69", 65, 70),
    ("70-74", 70, 75),
    ("75-79", 75, 80),
    ("80+", 80, 999),
]

REGIME_MIN_SCORE: dict[str, int] = {
    "sideways": 60,
    "RANGE": 60,
    "bull_trend": 72,
    "TREND_BULL": 72,
    "bear_trend": 68,
    "TREND_BEAR": 68,
    "high_volatility_regime": 68,
    "VOLATILE": 68,
    "flash_crash": 999,
    "unknown": 72,
}


# ── Helpers ────────────────────────────────────────────────────────────────────


def pf(pnls: list[float]) -> str:
    wins = sum(p for p in pnls if p > 0)
    losses = abs(sum(p for p in pnls if p < 0))
    if losses == 0:
        return "inf" if wins > 0 else "n/a"
    return f"{wins / losses:.2f}"


def wr(pnls: list[float]) -> str:
    if not pnls:
        return "n/a"
    return f"{sum(1 for p in pnls if p > 0) / len(pnls) * 100:.0f}%"


def score_bucket(score: int | float | None) -> str:
    if score is None:
        return "?"
    score = int(score)
    for label, lo, hi in SCORE_BUCKETS:
        if lo <= score < hi:
            return label
    return f"{score}"


# ── Chargement données ─────────────────────────────────────────────────────────


def load_paper_trades(path: Path, since_ts: float) -> list[dict]:
    """Reconstruit les trades complets (OPEN+CLOSE) depuis le JSONL."""
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
                if ev.get("ts", 0.0) >= since_ts:
                    closes[tid] = ev

    trades = []
    for tid, cl in closes.items():
        op = opens.get(tid)
        trades.append(
            {
                "trade_id": tid,
                "symbol": cl.get("symbol") or (op or {}).get("symbol", "?"),
                "side": cl.get("side") or (op or {}).get("side", "?"),
                "regime": (op or {}).get("regime") or cl.get("regime") or "unknown",
                "score": (op or {}).get("score") or cl.get("score"),
                "score_bin": (op or {}).get("score_bin") or cl.get("score_bin") or "?",
                "pnl_usd": cl.get("pnl_usd") or 0.0,
                "pnl_pct": cl.get("pnl_pct") or 0.0,
                "reason": cl.get("reason") or "?",
                "duration_s": cl.get("duration_s"),
                "mae_pct": cl.get("mae_pct"),
                "mfe_pct": cl.get("mfe_pct"),
                "opened_ts": (op or {}).get("ts"),
                "closed_ts": cl.get("ts"),
            }
        )
    return sorted(trades, key=lambda x: x.get("closed_ts") or 0.0)


def load_cycle_data(path: Path, since_ts: float) -> list[dict]:
    """Charge les cycles depuis since_ts."""
    cycles = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                c = json.loads(line)
            except json.JSONDecodeError:
                continue
            if c.get("ts", 0.0) >= since_ts:
                cycles.append(c)
    return cycles


# ── Sections rapport ───────────────────────────────────────────────────────────


def section_regime_x_score(trades: list[dict]) -> None:
    print("\n" + "=" * 65)
    print("  SECTION 3 — Régime × Score (cross-table)")
    print("=" * 65)

    if not trades:
        print("  [VIDE] Aucun trade disponible.")
        return

    # Construire la table
    table: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    all_regimes: set[str] = set()
    all_buckets: set[str] = set()

    for t in trades:
        reg = t.get("regime") or "unknown"
        bkt = score_bucket(t.get("score"))
        p = t.get("pnl_usd") or 0.0
        table[reg][bkt].append(p)
        all_regimes.add(reg)
        all_buckets.add(bkt)

    bucket_order = [b for b, _, _ in SCORE_BUCKETS if b in all_buckets] + [
        b for b in sorted(all_buckets) if b not in [x for x, _, _ in SCORE_BUCKETS]
    ]
    regime_order = sorted(
        all_regimes, key=lambda r: -sum(len(v) for v in table[r].values())
    )

    # Header
    col_w = 12
    hdr = f"  {'Regime':<22}" + "".join(f"{b:>{col_w}}" for b in bucket_order)
    print(hdr)
    print("  " + "-" * (22 + col_w * len(bucket_order)))

    for reg in regime_order:
        row_pnls = [p for bkt in table[reg].values() for p in bkt]
        global_pf = pf(row_pnls)
        line = f"  {reg:<22}"
        for bkt in bucket_order:
            ps = table[reg].get(bkt, [])
            if not ps:
                cell = "-"
            else:
                cell = f"N={len(ps)} PF={pf(ps)}"
            line += f"{cell:>{col_w}}"
        line += f"   | Total PF={global_pf} N={len(row_pnls)}"
        print(line)

    # Totaux par bucket
    print("  " + "-" * (22 + col_w * len(bucket_order)))
    tot_line = f"  {'TOTAL':<22}"
    for bkt in bucket_order:
        all_ps = [p for reg in all_regimes for p in table[reg].get(bkt, [])]
        tot_line += f"{'PF='+pf(all_ps):>{col_w}}" if all_ps else f"{'':>{col_w}}"
    print(tot_line)


def section_regime_distribution(cycles: list[dict], since_label: str) -> None:
    print("\n" + "=" * 65)
    print(f"  SECTION 4 — Distribution régimes réels ({since_label})")
    print("=" * 65)

    if not cycles:
        print("  [VIDE] Aucun cycle dans cycle_data depuis ce timestamp.")
        print("  Fournir --cycle-data pour activer cette section.")
        return

    regime_obs: dict[str, int] = defaultdict(int)
    signal_obs: dict[str, int] = defaultdict(int)
    gate_ok: dict[str, int] = defaultdict(int)

    total_obs = 0
    total_signals = 0
    total_gate = 0

    for cycle in cycles:
        for sym in cycle.get("symbols", []):
            if not isinstance(sym, dict):
                continue
            total_obs += 1
            reg = sym.get("regime") or "unknown"
            regime_obs[reg] += 1
            sig = sym.get("signal", "HOLD")
            if sig != "HOLD":
                total_signals += 1
                signal_obs[reg] += 1
            if sym.get("gate_allowed"):
                total_gate += 1
                gate_ok[reg] += 1

    print(
        f"\n  Observations : {total_obs}"
        f"  |  Non-HOLD : {total_signals}"
        f"  |  Gate OK : {total_gate}"
    )
    print(f"  Cycles       : {len(cycles)}")
    print()
    print(f"  {'Regime':<25} {'Obs':>6} {'%Obs':>6} {'Signaux':>8} {'GateOK':>8}")
    print(f"  {'-'*56}")

    for reg in sorted(regime_obs, key=lambda r: -regime_obs[r]):
        n = regime_obs[reg]
        s = signal_obs.get(reg, 0)
        g = gate_ok.get(reg, 0)
        print(f"  {reg:<25} {n:>6} {n/total_obs*100:>5.1f}%  {s:>7}  {g:>7}")

    # Score distribution pour les non-HOLD
    print()
    score_dist: dict[str, int] = defaultdict(int)
    score_gate: dict[str, int] = defaultdict(int)
    for cycle in cycles:
        for sym in cycle.get("symbols", []):
            if not isinstance(sym, dict) or sym.get("signal", "HOLD") == "HOLD":
                continue
            bkt = score_bucket(sym.get("score"))
            score_dist[bkt] += 1
            if sym.get("gate_allowed"):
                score_gate[bkt] += 1

    if score_dist:
        print(f"  Score distribution (signaux non-HOLD) :")
        print(f"  {'Bucket':<10} {'N':>6} {'Gate OK':>8} {'Gate %':>7}")
        print(f"  {'-'*34}")
        for bkt, _, _ in SCORE_BUCKETS:
            n = score_dist.get(bkt, 0)
            g = score_gate.get(bkt, 0)
            if n:
                print(f"  {bkt:<10} {n:>6} {g:>8} {g/n*100:>6.0f}%")


def _parse_gate_failed(sym: dict) -> list[str]:
    """Extrait la liste des conditions échouées depuis gate_reason ou gate_failed."""
    # Format 1 : liste de strings dans gate_failed (nouveau)
    failed = sym.get("gate_failed")
    if isinstance(failed, list):
        return failed
    # Format 2 : string unique dans gate_reason
    reason = sym.get("gate_reason") or ""
    if reason and reason not in ("", "unknown"):
        return [reason]
    return []


def section_recovery_analysis(cycles: list[dict], trades: list[dict]) -> None:
    import re

    print("\n" + "=" * 65)
    print("  SECTION 5 — RECOVERY : trades filtrés par delta")
    print("=" * 65)

    if not cycles:
        print("  [VIDE] cycle_data requis pour cette section.")
        return

    # Pattern gate écrit : "signal_score (62<66)" → score=62, eff_min=66
    _pat = re.compile(r"signal_score\s*\((\d+)<(\d+)\)")

    total_gate_score_fail = 0
    recovery_blocked: list[tuple[str, int, int, int]] = []  # (regime, score, base, eff)
    gate_reason_raw: dict[str, int] = defaultdict(int)
    total_refused = 0

    for cycle in cycles:
        for sym in cycle.get("symbols", []):
            if not isinstance(sym, dict):
                continue
            if sym.get("gate_allowed") or sym.get("signal", "HOLD") == "HOLD":
                continue
            total_refused += 1
            for cond in _parse_gate_failed(sym):
                gate_reason_raw[cond] += 1
                m = _pat.search(cond)
                if m:
                    total_gate_score_fail += 1
                    score_val = int(m.group(1))
                    eff_min = int(m.group(2))
                    regime = sym.get("regime") or "unknown"
                    base_min = REGIME_MIN_SCORE.get(regime, 72)
                    if eff_min > base_min:
                        # effective_min > base_min → RECOVERY delta est actif
                        recovery_blocked.append((regime, score_val, base_min, eff_min))

    print(f"\n  Refus de gate (signaux non-HOLD, N={total_refused}) :")

    if gate_reason_raw:
        print(f"  {'Condition échouée':<40} {'N':>6} {'%':>6}")
        print(f"  {'-'*55}")
        for cond, n in sorted(gate_reason_raw.items(), key=lambda x: -x[1])[:10]:
            print(f"  {cond:<40} {n:>6} {n/max(total_refused,1)*100:>5.1f}%")
    else:
        print("  gate_failed non peuplé dans ce cycle_data.")
        print("  (VPS data requis — local cycle_data pre-juin utilise format ancien)")

    # Analyse RECOVERY
    print()
    print(
        f"  Signaux bloqués par RECOVERY (eff_min > base_min) : {len(recovery_blocked)}"
    )

    if recovery_blocked:
        by_regime: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
        for reg, sc, base, eff in recovery_blocked:
            by_regime[reg].append((sc, base, eff))

        print()
        hdr = (
            f"  {'Regime':<25} {'N':>4}"
            f" {'base':>6} {'eff_min':>8} {'delta':>6} {'score_range'}"
        )
        print(hdr)
        print(f"  {'-'*60}")
        for reg in sorted(by_regime, key=lambda r: -len(by_regime[r])):
            items = by_regime[reg]
            n = len(items)
            base = items[0][1]
            effs = sorted(set(e for _, _, e in items))
            deltas = sorted(set(e - base for _, _, e in items))
            scores = [s for s, _, _ in items]
            print(
                f"  {reg:<25} {n:>4} {base:>6} {effs[0]:>8} {deltas[0]:>+6} "
                f"  [{min(scores)}-{max(scores)}]"
            )

        # Comparaison trades filtrés vs trades exécutés
        n_traded = len(trades)
        print()
        print(f"  Trades exécutés                 : {n_traded}")
        print(f"  Trades bloqués RECOVERY         : {len(recovery_blocked)}")
        if n_traded:
            ratio = len(recovery_blocked) / n_traded
            print(f"  Ratio bloqué/exécuté            : {ratio:.1f}x")
        print()
        print("  Note : ces trades auraient potentiellement été exécutés si delta=0.")
        print("  Leur PF conditionnel est inconnu (pas d'outcome pour les refus).")
    elif total_gate_score_fail == 0 and not gate_reason_raw:
        print("  (Format gate_reason non parseable — relancer avec cycle_data VPS)")
    else:
        print("  Aucun blocage RECOVERY detecté : eff_min == base_min partout.")
        print("  Delta RiskGovernor probablement à 0 sur cette période.")


def section_time_distribution(trades: list[dict]) -> None:
    """Répartition temporelle des trades (identifier concentration ou sécheresse)."""
    if not trades or not any(t.get("closed_ts") for t in trades):
        return

    from datetime import datetime, timezone

    print("\n" + "=" * 65)
    print("  SECTION 6 — Répartition temporelle")
    print("=" * 65)

    by_day: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        ts = t.get("closed_ts")
        if ts:
            day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            by_day[day].append(t.get("pnl_usd") or 0.0)

    print(f"\n  {'Date':<12} {'N':>4} {'WR':>6} {'PF':>7} {'PnL':>9}")
    print(f"  {'-'*42}")
    for day in sorted(by_day):
        ps = by_day[day]
        print(f"  {day:<12} {len(ps):>4} {wr(ps):>6} {pf(ps):>7} {sum(ps):>+8.2f}$")


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AUDIT-R2 — diagnostic quantitatif burn-in"
    )
    parser.add_argument(
        "--jsonl",
        default="databases/paper_trades.jsonl",
        help="Chemin paper_trades.jsonl (local ou VPS)",
    )
    parser.add_argument(
        "--cycle-data",
        default="databases/cycle_data.jsonl",
        help="Chemin cycle_data.jsonl (local ou VPS)",
    )
    parser.add_argument(
        "--since-ts",
        type=float,
        default=BURNIN_V2_START_TS,
        help="Timestamp Unix depuis lequel filtrer les trades (défaut: post-6ce7fc2)",
    )
    parser.add_argument(
        "--cycle-since-ts",
        type=float,
        default=FIX_4F77935_TS,
        help="Timestamp Unix pour filtrer cycle_data (défaut: post-fix 4f77935)",
    )
    parser.add_argument(
        "--min-n",
        type=int,
        default=10,
        help="N minimum pour afficher la section cross-table (défaut: 10)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 65)
    print("  AUDIT-R2 — Rapport diagnostic burn-in")
    print("=" * 65)

    # ── Trades paper ──────────────────────────────────────────────────────────
    jsonl = Path(args.jsonl)
    trades: list[dict] = []
    if jsonl.exists():
        trades = load_paper_trades(jsonl, args.since_ts)
        print(f"\n  paper_trades.jsonl : {jsonl}")
        print(f"  Trades chargés     : {len(trades)} (depuis ts={args.since_ts:.0f})")
    else:
        print(f"\n  [WARNING] {jsonl} introuvable — sections trades désactivées")

    # ── Cycle data ────────────────────────────────────────────────────────────
    cycle_path = Path(args.cycle_data)
    cycles: list[dict] = []
    since_label = "post-4f77935"
    if cycle_path.exists():
        cycles = load_cycle_data(cycle_path, args.cycle_since_ts)
        print(f"  cycle_data.jsonl   : {cycle_path}")
        print(
            f"  Cycles chargés     : {len(cycles)}"
            f" (depuis ts={args.cycle_since_ts:.0f})"
        )
    else:
        print(f"  [WARNING] {cycle_path} introuvable — sections cycle désactivées")

    if not trades and not cycles:
        print(
            "\n  [ERREUR] Aucune donnée disponible. Fournir --jsonl et/ou --cycle-data."
        )
        sys.exit(1)

    # ── Sections ──────────────────────────────────────────────────────────────
    if len(trades) < args.min_n:
        print(f"\n  [ATTENTE] {len(trades)} trades < {args.min_n} minimum.")
        print("  Sections trades affichées quand même (résultats préliminaires).")

    section_regime_x_score(trades)
    section_regime_distribution(cycles, since_label)
    section_recovery_analysis(cycles, trades)
    section_time_distribution(trades)

    print("\n" + "=" * 65)
    print("  Fin AUDIT-R2")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
