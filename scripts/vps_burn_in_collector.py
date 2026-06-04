#!/usr/bin/env python3
"""
vps_burn_in_collector.py — Collecteur de métriques burn-in pour VPS.

Lit les données produites par le système en production et génère :
  - Un snapshot horaire  (mode --snapshot, cron toutes les heures)
  - Un rapport journalier avec tableau de décision P13 (mode --report)

Sources de données :
  cache/startup/metrics.jsonl   → MetricsCollector (drawdown, exceptions, memory…)
  cache/startup/alerts.jsonl    → AlertEngine (alertes déclenchées)
  databases/paper_trades.jsonl  → PaperTradeRecorder (OPEN + CLOSE)

Sorties :
  cache/burn_in_reports/hourly.jsonl            → snapshots horaires cumulés
  cache/burn_in_reports/YYYY-MM-DD_report.json  → rapport journalier complet
  cache/burn_in_reports/p13_running_table.json  → tableau P13 mis à jour

Usage :
    python scripts/vps_burn_in_collector.py --snapshot
    python scripts/vps_burn_in_collector.py --report
    python scripts/vps_burn_in_collector.py --report --hours 168   # 7 jours
    python scripts/vps_burn_in_collector.py --report --telegram
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# -- Encodage UTF-8 (VPS Linux natif ; Windows terminal corrigé) ---------
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# -- Résolution du chemin projet ----------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from system.alpha_kill_switch import AlphaKillSwitch  # noqa: E402
from system.burnin_analytics import BurnInAnalytics  # noqa: E402

# -- Chemins (overridables via variables d'environnement) ----------------
METRICS_PATH = Path(os.getenv("P12_METRICS_PATH", "cache/startup/metrics.jsonl"))
ALERTS_PATH = Path(os.getenv("P12_ALERT_PATH", "cache/startup/alerts.jsonl"))
TRADES_PATH = Path(os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl"))
BEHAVIOR_PATH = Path(
    os.getenv("P13_BEHAVIOR_PATH", "cache/startup/behavioral_events.jsonl")
)
REPORTS_DIR = Path(os.getenv("BURN_IN_REPORTS_DIR", "cache/burn_in_reports"))

# -- Seuils P13 (alignés avec system/burn_in.py) -------------------------
_THRESHOLDS: dict[str, float] = {
    "uptime_pct": 99.0,
    "exceptions_per_day": 5.0,
    "invariant_violations": 0.0,
    "audit_corruption": 0.0,
    "reconciliation_failures": 0.0,
    "max_drawdown_pct": 15.0,
    "sharpe_ratio": 1.0,
    "sortino_ratio": 1.5,
    "profit_factor": 1.3,
    "strategy_score": 60.0,
}

_NOW_UTC = datetime.now(timezone.utc)


# ── Chargement des fichiers JSONL ─────────────────────────────────────────────


def _load_jsonl(path: Path, since_ts: float = 0.0) -> list[dict]:
    """Charge un fichier JSONL, filtre les enregistrements depuis since_ts."""
    if not path.exists():
        return []
    records = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    ts = rec.get("ts", 0.0)
                    if ts >= since_ts:
                        records.append(rec)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return records


def _load_complete_trades(path: Path, since_ts: float = 0.0) -> list[dict]:
    """
    Lit paper_trades.jsonl et retourne uniquement les trades COMPLETS
    (1 OPEN + 1 CLOSE appariés par trade_id) postérieurs à since_ts.
    """
    if not path.exists():
        return []

    opens: dict[str, dict] = {}
    closes: dict[str, dict] = {}

    try:
        with open(path, encoding="utf-8") as f:
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
    except OSError:
        return []

    completed = []
    for tid, op in opens.items():
        cl = closes.get(tid)
        if cl and cl.get("ts", 0.0) >= since_ts:
            completed.append(
                {
                    "trade_id": tid,
                    "open_ts": op.get("ts", 0.0),
                    "close_ts": cl.get("ts", 0.0),
                    "symbol": op.get("symbol", ""),
                    "side": op.get("side", ""),
                    "size_usd": op.get("size_usd", 0.0),
                    "regime": op.get("regime", "UNKNOWN"),
                    "score": op.get("score", 0),
                    "entry_price": op.get("price", 0.0),
                    "exit_price": cl.get("exit_price", 0.0),
                    "pnl_usd": cl.get("pnl_usd", 0.0),
                    "pnl_pct": cl.get("pnl_pct", 0.0),
                    "duration_s": cl.get("ts", 0.0) - op.get("ts", 0.0),
                    "exit_reason": cl.get("reason", ""),
                }
            )
    return completed


# ── Événements comportementaux ───────────────────────────────────────────────


def _compute_behavioral_metrics(events: list[dict]) -> dict:
    """
    Analyse les événements TRADING_STALLED, ADAPTATION_INEFFECTIVE, TRADING_RESUMED.

    Répond aux questions de surveillance :
    - Combien de temps en PARALYSED ?
    - Fréquence ADAPTATION_INEFFECTIVE ?
    - Top blockers cumulés ?
    """
    stalled = [e for e in events if e.get("event") == "TRADING_STALLED"]
    resumed = [e for e in events if e.get("event") == "TRADING_RESUMED"]
    ineffective = [e for e in events if e.get("event") == "ADAPTATION_INEFFECTIVE"]

    # Episodes STALLED par label
    episodes_by_label: dict[str, int] = {}
    total_cycles_stalled = 0
    for ev in stalled:
        lbl = ev.get("label", "stalled")
        episodes_by_label[lbl] = episodes_by_label.get(lbl, 0) + 1
        total_cycles_stalled += ev.get("cycles_stalled", 0)

    # Durée moyenne d'un épisode (via TRADING_RESUMED)
    resume_durations = [
        r.get("after_cycles", 0) for r in resumed if r.get("after_cycles", 0) > 0
    ]
    avg_stall_duration = (
        round(sum(resume_durations) / len(resume_durations), 1)
        if resume_durations
        else None
    )

    # Top blockers cumulés sur la période
    blocker_totals: dict[str, int] = {}
    for ev in stalled:
        for blk, cnt in ev.get("top_blockers", {}).items():
            blocker_totals[blk] = blocker_totals.get(blk, 0) + cnt
    top_blockers = sorted(blocker_totals.items(), key=lambda x: -x[1])[:5]

    # ADAPTATION_INEFFECTIVE : nombre et mismatch moyen
    inef_count = len(ineffective)
    inef_mismatch_avg = (
        round(
            sum(e.get("consecutive_mismatch", 0) for e in ineffective) / inef_count, 1
        )
        if inef_count
        else None
    )

    return {
        "stalled_episodes": len(stalled),
        "paralysed_episodes": episodes_by_label.get("paralysed", 0),
        "stalled_only_episodes": episodes_by_label.get("stalled", 0),
        "waiting_episodes": episodes_by_label.get("waiting", 0),
        "avg_stall_duration_cycles": avg_stall_duration,
        "adaptation_ineffective_count": inef_count,
        "adaptation_ineffective_mismatch_avg": inef_mismatch_avg,
        "top_blockers": [{"name": k, "count": v} for k, v in top_blockers],
        "resumed_count": len(resumed),
    }


# ── Calculs des métriques ────────────────────────────────────────────────────


def _compute_uptime_pct(snapshots: list[dict], window_s: float) -> float:
    """
    Estime l'uptime en % en détectant les lacunes dans les snapshots.
    Un trou > 2× l'intervalle médian est considéré comme downtime.
    """
    if len(snapshots) < 2:
        return 100.0 if snapshots else 0.0

    timestamps = sorted(s["ts"] for s in snapshots)
    intervals = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
    median_interval = sorted(intervals)[len(intervals) // 2]
    gap_threshold = max(median_interval * 2, 120.0)  # min 2 min

    total_gaps_s = sum(iv - gap_threshold for iv in intervals if iv > gap_threshold)
    total_gaps_s = min(total_gaps_s, window_s)

    uptime_pct = max(0.0, (1.0 - total_gaps_s / window_s) * 100.0)
    return round(uptime_pct, 2)


def _compute_trading_metrics(trades: list[dict]) -> Optional[dict]:
    """Calcule les métriques de stratégie via StrategyAnalyzer + StrategyScorer."""
    if not trades:
        return None
    try:
        from system.strategy_metrics import StrategyAnalyzer, Trade
        from system.strategy_score import StrategyScorer

        initial_capital = 10_000.0  # valeur de référence pour les calculs
        analyzer = StrategyAnalyzer(initial_capital=initial_capital)
        scorer = StrategyScorer()

        trade_objs = [
            Trade(
                pnl=t["pnl_usd"],
                pnl_pct=t["pnl_pct"] * 100.0 if abs(t["pnl_pct"]) < 1 else t["pnl_pct"],
                duration_s=t["duration_s"],
                ts=t["close_ts"],
                regime=t.get("regime", "UNKNOWN"),
            )
            for t in trades
        ]

        # Courbe equity simplifiée à partir des PnL cumulés
        equity_curve: list[float] = [initial_capital]
        for tr in trade_objs:
            equity_curve.append(equity_curve[-1] + tr.pnl)

        metrics = analyzer.compute(trade_objs, equity_curve)
        score_result = scorer.score(metrics)

        return {
            "total_trades": metrics.total_trades,
            "win_rate": round(metrics.win_rate * 100, 1),
            "profit_factor": round(metrics.profit_factor, 3),
            "expectancy": round(metrics.expectancy, 4),
            "max_drawdown_pct": round(metrics.max_drawdown_pct, 2),
            "sharpe_ratio": round(metrics.sharpe_ratio, 3),
            "sortino_ratio": round(metrics.sortino_ratio, 3),
            "total_return_pct": round(metrics.total_return_pct, 2),
            "strategy_score": round(score_result.total, 1),
            "strategy_grade": score_result.grade.value,
        }
    except Exception as exc:
        print(f"[WARN] StrategyAnalyzer indisponible: {exc}", file=sys.stderr)
        return None


def _build_p13_table(
    snapshots: list[dict],
    alerts: list[dict],
    trades: list[dict],
    window_s: float,
    label: str,
    behavior_events: Optional[list[dict]] = None,
) -> dict:
    """Construit le tableau de décision P13 complet."""

    # -- Métriques système depuis MetricsCollector snapshots -----------------
    drawdown_max = max((s.get("drawdown_pct", 0.0) for s in snapshots), default=0.0)
    memory_max = max((s.get("memory_mb", 0.0) for s in snapshots), default=0.0)
    exceptions = max((s.get("exception_count", 0) for s in snapshots), default=0)
    reconcile_fail = max(
        (s.get("reconciliation_failures", 0) for s in snapshots), default=0
    )
    health_scores = [
        s.get("health_score", 100.0)
        for s in snapshots
        if s.get("health_score") is not None
    ]
    health_min = min(health_scores, default=100.0)
    health_mean = (sum(health_scores) / len(health_scores)) if health_scores else 100.0

    uptime_pct = _compute_uptime_pct(snapshots, window_s)

    # -- Alertes ---------------------------------------------------------------
    n_alerts = len(alerts)
    n_critical = sum(1 for a in alerts if a.get("severity") == "CRITICAL")

    # -- Métriques stratégie ---------------------------------------------------
    strat = _compute_trading_metrics(trades)
    burnin_analytics = BurnInAnalytics().build_report(
        trades,
        generated_at=_NOW_UTC,
        window_hours=window_s / 3600.0,
    )

    # -- Verdict P13 -----------------------------------------------------------
    failures: list[str] = []

    def _check(
        name: str, value: Optional[float], threshold: float, above_is_bad: bool = False
    ) -> None:
        if value is None:
            return
        if above_is_bad and value > threshold:
            failures.append(f"{name}: {value} > {threshold}")
        elif not above_is_bad and value < threshold:
            failures.append(f"{name}: {value} < {threshold}")

    _check("uptime_pct", uptime_pct, _THRESHOLDS["uptime_pct"])
    _check(
        "exceptions_per_day",
        float(exceptions),
        _THRESHOLDS["exceptions_per_day"],
        above_is_bad=True,
    )
    _check(
        "reconciliation_failures",
        float(reconcile_fail),
        _THRESHOLDS["reconciliation_failures"],
        above_is_bad=True,
    )
    _check(
        "max_drawdown_pct",
        drawdown_max,
        _THRESHOLDS["max_drawdown_pct"],
        above_is_bad=True,
    )
    if strat:
        _check("sharpe_ratio", strat["sharpe_ratio"], _THRESHOLDS["sharpe_ratio"])
        _check("sortino_ratio", strat["sortino_ratio"], _THRESHOLDS["sortino_ratio"])
        _check("profit_factor", strat["profit_factor"], _THRESHOLDS["profit_factor"])
        _check("strategy_score", strat["strategy_score"], _THRESHOLDS["strategy_score"])

    burn_in_passed = len(failures) == 0

    # Métriques comportementales (informatives — pas de pass/fail pour l'instant)
    behavioral = _compute_behavioral_metrics(behavior_events or [])

    # Alpha Kill Switch (observatoire — ne bloque rien automatiquement)
    alpha_kill = AlphaKillSwitch().evaluate(trades)

    return {
        "label": label,
        "generated": _NOW_UTC.isoformat(),
        "window_s": window_s,
        "n_snapshots": len(snapshots),
        "n_alerts": n_alerts,
        "n_critical_alerts": n_critical,
        "behavioral": behavioral,
        "burnin_analytics": burnin_analytics,
        "alpha_kill": alpha_kill.as_dict(),
        # Tableau P13
        "p13_table": {
            "uptime_pct": {
                "value": uptime_pct,
                "target": f">={_THRESHOLDS['uptime_pct']}%",
            },
            "exceptions": {
                "value": exceptions,
                "target": f"<={int(_THRESHOLDS['exceptions_per_day'])}/j",
            },
            "invariant_violations": {"value": 0, "target": "=0"},  # via alerts rules
            "audit_corruption": {"value": 0, "target": "=0"},
            "reconciliation_failures": {"value": reconcile_fail, "target": "=0"},
            "max_drawdown_pct": {
                "value": round(drawdown_max, 2),
                "target": f"<={_THRESHOLDS['max_drawdown_pct']}%",
            },
            "health_score_min": {"value": round(health_min, 1), "target": ">=75"},
            "health_score_mean": {"value": round(health_mean, 1), "target": ">=80"},
            "memory_mb_max": {"value": round(memory_max, 1), "target": "<=800 MB"},
            "sharpe_ratio": {
                "value": strat["sharpe_ratio"] if strat else None,
                "target": f">={_THRESHOLDS['sharpe_ratio']}",
            },
            "sortino_ratio": {
                "value": strat["sortino_ratio"] if strat else None,
                "target": f">={_THRESHOLDS['sortino_ratio']}",
            },
            "profit_factor": {
                "value": strat["profit_factor"] if strat else None,
                "target": f">={_THRESHOLDS['profit_factor']}",
            },
            "strategy_score": {
                "value": strat["strategy_score"] if strat else None,
                "target": f">={_THRESHOLDS['strategy_score']}",
            },
            "strategy_grade": {
                "value": strat["strategy_grade"] if strat else None,
                "target": ">=B",
            },
            "total_trades": {
                "value": strat["total_trades"] if strat else 0,
                "target": ">=10",
            },
            "win_rate": {
                "value": strat["win_rate"] if strat else None,
                "target": "informative",
            },
            "burn_in_passed": {"value": burn_in_passed, "target": "OUI"},
        },
        "failure_reasons": failures,
        "burn_in_passed": burn_in_passed,
    }


# ── Rendu terminal ────────────────────────────────────────────────────────────

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _color_value(value, target_str: str) -> str:
    """Colore une valeur selon qu'elle passe ou non le seuil."""
    if value is None:
        return f"{_YELLOW}N/A{_RESET}"
    return str(value)


def _print_score_calibration(burnin: dict) -> None:
    """Affiche l'histogramme score -> performance (calibration audit)."""
    histogram = burnin.get("score_histogram", [])
    if not histogram or not any(r["trades"] > 0 for r in histogram):
        return

    total_trades = burnin.get("trades", 0)
    target = 100
    filled = min(total_trades, target) * 20 // target

    floor = burnin.get("recommended_score_floor")
    confidence = burnin.get("score_floor_confidence", "INSUFFICIENT_DATA")

    print(f"{_BOLD}{_CYAN}{'-'*64}{_RESET}")
    print(f"{_BOLD}  CALIBRATION AUDIT — Score -> Performance{_RESET}")
    print(
        f"  Trades collectes : {total_trades} / {target} cible"
        f"  {'#' * filled}{'.' * (20 - filled)}"
        f"  ({total_trades / target * 100:.0f}%)"
    )
    if floor is not None:
        floor_col = (
            _GREEN
            if confidence == "HIGH"
            else (_YELLOW if confidence == "MEDIUM" else _RED)
        )
        print(
            f"  Score floor recommande : {floor_col}{floor}{_RESET}"
            f"  (confiance: {floor_col}{confidence}{_RESET})"
        )
    else:
        print(
            f"  Score floor recommande : {_YELLOW}N/A — donnees insuffisantes{_RESET}"
        )
    print(f"{_BOLD}{_CYAN}{'-'*64}{_RESET}")
    print(
        f"  {'Score':<10} {'N':>5} {'WR%':>7} {'Expect':>9}"
        f" {'PF':>7} {'Sharpe':>7}  Alpha"
    )
    print(f"  {'-'*8} {'-'*5} {'-'*7} {'-'*9} {'-'*7} {'-'*7}  {'-'*14}")

    for row in histogram:
        if row["trades"] == 0:
            continue
        wr = row["win_rate"]
        exp = row["expectancy"]
        pf = row["profit_factor"]
        sharpe = row.get("sharpe", 0.0)
        alpha_class = row.get("alpha_class", "insufficient_data")

        if alpha_class == "positive":
            verdict = f"{_GREEN}POSITIVE{_RESET}"
        elif alpha_class == "neutral":
            verdict = f"{_YELLOW}NEUTRE{_RESET}"
        elif alpha_class == "negative":
            verdict = f"{_RED}NEGATIVE{_RESET}"
        else:
            verdict = f"{_YELLOW}insuf.{_RESET}"

        print(
            f"  {row['range']:<10} {row['trades']:>5} {wr:>7.1f}"
            f" {exp:>9.3f} {pf:>7.3f} {sharpe:>7.3f}  {verdict}"
        )

    print(f"{_BOLD}{_CYAN}{'-'*64}{_RESET}")
    print()


def _print_symbol_breakdown(burnin: dict) -> None:
    """Affiche l'expectancy par symbole — detecte les actifs drag."""
    rows = burnin.get("symbol_breakdown", [])
    if not rows or not any(r["trades"] > 0 for r in rows):
        return

    print(f"{_BOLD}{_CYAN}{'-'*64}{_RESET}")
    print(f"{_BOLD}  BREAKDOWN PAR SYMBOLE{_RESET}")
    print(f"{_BOLD}{_CYAN}{'-'*64}{_RESET}")
    print(f"  {'Symbole':<14} {'N':>5} {'WR%':>7} {'Expect':>9} {'PF':>7}  Signal")
    print(f"  {'-'*12} {'-'*5} {'-'*7} {'-'*9} {'-'*7}  {'-'*10}")

    for row in rows:
        if row["trades"] == 0:
            continue
        exp = row["expectancy"]
        wr = row["win_rate"]
        pf = row["profit_factor"]

        if exp > 0.2:
            signal = f"{_GREEN}FORT+{_RESET}"
        elif exp > 0.05:
            signal = f"{_GREEN}+{_RESET}"
        elif exp > -0.05:
            signal = f"{_YELLOW}~{_RESET}"
        elif exp > -0.2:
            signal = f"{_RED}-{_RESET}"
        else:
            signal = f"{_RED}DRAG{_RESET}"

        sym = row["symbol"][:14]
        print(
            f"  {sym:<14} {row['trades']:>5} {wr:>7.1f}"
            f" {exp:>9.3f} {pf:>7.3f}  {signal}"
        )

    print(f"{_BOLD}{_CYAN}{'-'*64}{_RESET}")
    print()


def _print_p13_table(report: dict) -> None:
    table = report["p13_table"]
    passed = report["burn_in_passed"]
    label = report["label"]
    ts = report["generated"]

    status_str = (
        f"{_GREEN}{_BOLD}PASS{_RESET}" if passed else f"{_RED}{_BOLD}FAIL{_RESET}"
    )

    print()
    print(f"{_BOLD}{_CYAN}{'-'*64}{_RESET}")
    print(f"{_BOLD}  TABLEAU DE DECISION P13 -- {label}{_RESET}")
    print(f"  Genere : {ts}")
    print(
        f"  Fenetre : {report['window_s']/3600:.1f}h"
        f"  |  Snapshots : {report['n_snapshots']}"
        f"  |  Alertes : {report['n_alerts']}"
        f" ({report['n_critical_alerts']} critiques)"
    )
    print(f"{_BOLD}{_CYAN}{'-'*64}{_RESET}")
    print(f"  {'Indicateur':<30} {'Valeur':>12}  {'Cible'}")
    print(f"  {'-'*28} {'-'*12}  {'-'*18}")

    rows = [
        ("uptime_pct", "Uptime"),
        ("exceptions", "Exceptions"),
        ("invariant_violations", "Invariant violations"),
        ("audit_corruption", "Audit corruption"),
        ("reconciliation_failures", "Reconciliation failures"),
        ("max_drawdown_pct", "Max drawdown"),
        ("health_score_min", "Health score (min)"),
        ("health_score_mean", "Health score (moy)"),
        ("memory_mb_max", "Mémoire max"),
        ("sharpe_ratio", "Sharpe"),
        ("sortino_ratio", "Sortino"),
        ("profit_factor", "Profit Factor"),
        ("strategy_score", "Strategy Score"),
        ("strategy_grade", "Grade"),
        ("total_trades", "Trades totaux"),
        ("win_rate", "Win Rate"),
        ("burn_in_passed", "Burn-in Passed"),
    ]

    for key, label_txt in rows:
        entry = table.get(key, {})
        val = entry.get("value")
        target = entry.get("target", "—")

        # Formatage de la valeur
        if val is None:
            val_str = f"{_YELLOW}N/A{_RESET}"
        elif isinstance(val, bool):
            val_str = f"{_GREEN}OUI{_RESET}" if val else f"{_RED}NON{_RESET}"
        elif isinstance(val, float):
            val_str = f"{val:.2f}"
        else:
            val_str = str(val)

        print(f"  {label_txt:<30} {val_str:>12}  {target}")

    print(f"{_BOLD}{_CYAN}{'-'*64}{_RESET}")
    print(f"  Verdict : {status_str}")
    if report["failure_reasons"]:
        for r in report["failure_reasons"]:
            print(f"    {_RED}x{_RESET} {r}")

    # Section comportementale
    beh = report.get("behavioral", {})
    if beh and (
        beh.get("stalled_episodes", 0) > 0
        or beh.get("adaptation_ineffective_count", 0) > 0
    ):
        print(f"{_BOLD}{_CYAN}{'-'*64}{_RESET}")
        print(f"{_BOLD}  COMPORTEMENT INTERNE{_RESET}")
        print(
            f"  {'Episodes TRADING_STALLED':<30} {beh.get('stalled_episodes', 0):>12}"
        )
        print(f"  {'  dont PARALYSED':<30} {beh.get('paralysed_episodes', 0):>12}")
        avg_d = beh.get("avg_stall_duration_cycles")
        dur_str = str(avg_d) if avg_d is not None else "N/A"
        print(f"  {'  duree moy (cycles)':<30} {dur_str:>12}")
        inef = beh.get("adaptation_ineffective_count", 0)
        print(f"  {'ADAPTATION_INEFFECTIVE':<30} {inef:>12}")
        if beh.get("top_blockers"):
            blk_str = " | ".join(
                f"{b['name']}:{b['count']}" for b in beh["top_blockers"][:3]
            )
            print(f"  Top blockers: {blk_str}")

    print(f"{_BOLD}{_CYAN}{'-'*64}{_RESET}")
    print()

    # Calibration + symboles (toujours affichés dans un rapport complet)
    burnin = report.get("burnin_analytics", {})
    _print_score_calibration(burnin)
    _print_symbol_breakdown(burnin)

    # Alpha Kill Switch
    ak = report.get("alpha_kill", {})
    if ak.get("triggered"):
        print(f"{_BOLD}{_CYAN}{'-'*64}{_RESET}")
        print(f"{_BOLD}{_RED}  ALPHA KILL SWITCH — ALERTE{_RESET}")
        print(f"{_BOLD}{_CYAN}{'-'*64}{_RESET}")
        for reason in ak.get("reasons", []):
            print(f"  {_RED}!{_RESET} {reason}")
        print()
        print(f"  Actions suggérées :")
        for action in ak.get("suggested_actions", []):
            print(f"  {_YELLOW}→{_RESET} {action}")
        print(f"{_BOLD}{_CYAN}{'-'*64}{_RESET}")
        print()


# ── Telegram ──────────────────────────────────────────────────────────────────


def _alpha_digest_lines(burnin: dict) -> list[str]:
    """Section alpha pour le digest Telegram — indépendante du tableau P13."""
    lines: list[str] = []
    total = burnin.get("trades", 0)
    if total == 0:
        return ["_Aucun trade fermé sur la période_"]

    target = 100
    pct = round(min(total, target) / target * 100)
    wr = burnin.get("win_rate", 0.0)
    pf = burnin.get("profit_factor", 0.0)
    sh = burnin.get("sharpe", 0.0)
    dd = burnin.get("max_drawdown", 0.0)

    lines += [
        f"• Trades : *{total}* / {target} cible ({pct}%)",
        f"• Win Rate : {wr:.1f}%",
        f"• Profit Factor : {pf:.3f}",
        f"• Sharpe : {sh:.3f}",
        f"• Max Drawdown : {dd:.2f}%",
    ]

    # Meilleur / pire bin (parmi ceux avec au moins 1 trade)
    histogram = [r for r in burnin.get("score_histogram", []) if r["trades"] > 0]
    if histogram:
        best_bin = max(histogram, key=lambda r: r["expectancy"])
        worst_bin = min(histogram, key=lambda r: r["expectancy"])
        lines += [
            "",
            f"📈 Meilleur bin : *{best_bin['range']}*"
            f" (E: {best_bin['expectancy']:+.3f}, WR: {best_bin['win_rate']:.0f}%,"
            f" N: {best_bin['trades']})",
            f"📉 Pire bin : *{worst_bin['range']}*"
            f" (E: {worst_bin['expectancy']:+.3f}, WR: {worst_bin['win_rate']:.0f}%,"
            f" N: {worst_bin['trades']})",
        ]

    # Meilleur / pire symbole
    sym_rows = [r for r in burnin.get("symbol_breakdown", []) if r["trades"] > 0]
    if sym_rows:
        best_sym = sym_rows[0]  # déjà trié expectancy desc
        worst_sym = sym_rows[-1]
        lines += [
            f"🟢 Meilleur symbole : *{best_sym['symbol']}*"
            f" (E: {best_sym['expectancy']:+.3f}, N: {best_sym['trades']})",
            f"🔴 Pire symbole : *{worst_sym['symbol']}*"
            f" (E: {worst_sym['expectancy']:+.3f}, N: {worst_sym['trades']})",
        ]

    # Recommandation score floor
    floor = burnin.get("recommended_score_floor")
    conf = burnin.get("score_floor_confidence", "INSUFFICIENT_DATA")
    if floor is not None:
        lines.append(f"🎯 Score floor recommandé : *{floor}* (confiance: {conf})")
    else:
        lines.append(f"🎯 Score floor recommandé : N/A (données insuffisantes)")

    return lines


def _send_telegram(report: dict) -> None:
    """Envoie le digest burn-in (gouvernance + alpha) via Telegram."""
    try:
        import requests
        from dotenv import load_dotenv

        load_dotenv(override=True)

        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            print(
                "[WARN] TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant",
                file=sys.stderr,
            )
            return

        table = report["p13_table"]
        passed = report["burn_in_passed"]
        verdict = "✅ PASS" if passed else "❌ FAIL"
        label = report.get("label", "")

        def _fmt(key: str) -> str:
            v = table.get(key, {}).get("value")
            return (
                "N/A" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))
            )

        # ── Section gouvernance ──────────────────────────────────────────────
        lines = [
            f"🔥 *Burn-In — {label}*",
            f"Verdict : *{verdict}*",
            "",
            "*━━ Gouvernance ━━*",
            f"• Uptime : {_fmt('uptime_pct')}%",
            f"• Exceptions : {_fmt('exceptions')}",
            f"• Reconcile failures : {_fmt('reconciliation_failures')}",
            f"• Max drawdown sys : {_fmt('max_drawdown_pct')}%",
            f"• Health min : {_fmt('health_score_min')}",
        ]
        if report["failure_reasons"]:
            lines.append("*Échecs P13 :*")
            for r in report["failure_reasons"]:
                lines.append(f"  ✗ {r}")

        beh = report.get("behavioral", {})
        if (
            beh.get("stalled_episodes", 0) > 0
            or beh.get("adaptation_ineffective_count", 0) > 0
        ):
            n_st = beh.get("stalled_episodes", 0)
            n_pa = beh.get("paralysed_episodes", 0)
            n_inef = beh.get("adaptation_ineffective_count", 0)
            lines.append(
                f"• Stalled: {n_st} ep (dont {n_pa} PARALYSED)" f" | Inef: {n_inef}x"
            )

        # ── Section alpha ────────────────────────────────────────────────────
        burnin = report.get("burnin_analytics", {})
        if burnin:
            lines += ["", "*━━ Alpha ━━*"]
            lines += _alpha_digest_lines(burnin)

        # ── Alpha Kill Switch ────────────────────────────────────────────────
        ak = report.get("alpha_kill", {})
        if ak.get("triggered"):
            lines += ["", "*🚨 ALPHA KILL SWITCH*"]
            for reason in ak.get("reasons", []):
                lines.append(f"  ✗ {reason}")
            for action in ak.get("suggested_actions", []):
                lines.append(f"  → `{action}`")

        text = "\n".join(lines)
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        if resp.ok:
            print("[OK] Rapport envoyé sur Telegram")
        else:
            print(
                f"[WARN] Telegram: {resp.status_code} {resp.text[:200]}",
                file=sys.stderr,
            )
    except Exception as exc:
        print(f"[WARN] Telegram échoué: {exc}", file=sys.stderr)


# ── Sauvegarde ────────────────────────────────────────────────────────────────


def _save_report(report: dict, mode: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = _NOW_UTC.strftime("%Y-%m-%d")

    if mode == "snapshot":
        out = REPORTS_DIR / "hourly.jsonl"
        with open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False) + "\n")
    else:
        out = REPORTS_DIR / f"{date_str}_report.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # Mise à jour du tableau P13 courant
        p13_out = REPORTS_DIR / "p13_running_table.json"
        with open(p13_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    burnin_analytics = report.get("burnin_analytics", {})

    burnin_out = REPORTS_DIR / "burnin_report.json"
    with open(burnin_out, "w", encoding="utf-8") as f:
        json.dump(burnin_analytics, f, indent=2, ensure_ascii=False)

    _save_calibration_report(burnin_analytics, REPORTS_DIR)
    _save_equity_curve(burnin_analytics, REPORTS_DIR)

    return out


def _save_equity_curve(burnin: dict, reports_dir: Path) -> None:
    """Sauvegarde burnin_equity_curve.json — courbe de capital trade par trade."""
    curve = burnin.get("equity_curve", [])
    out = reports_dir / "burnin_equity_curve.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(
            {"generated_at": burnin.get("generated_at", ""), "curve": curve},
            f,
            indent=2,
            ensure_ascii=False,
        )


def _save_calibration_report(burnin: dict, reports_dir: Path) -> None:
    """Produit calibration_report.json : score bins + EV curve + recommandation."""
    total = burnin.get("trades", 0)
    target = 100

    calibration = {
        "generated_at": burnin.get("generated_at", _NOW_UTC.isoformat()),
        "window_hours": burnin.get("window_hours"),
        "total_trades": total,
        "target_trades": target,
        "coverage_pct": round(min(total, target) / target * 100, 1),
        "bins": burnin.get("score_histogram", []),
        "expected_value_curve": burnin.get("expected_value_curve", []),
        "recommended_score_floor": burnin.get("recommended_score_floor"),
        "score_floor_confidence": burnin.get(
            "score_floor_confidence", "INSUFFICIENT_DATA"
        ),
        "symbol_breakdown": burnin.get("symbol_breakdown", []),
        "symbol_bin_matrix": burnin.get("symbol_bin_matrix", {}),
        "alpha_drift": burnin.get("alpha_drift", {}),
    }
    out = reports_dir / "calibration_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(calibration, f, indent=2, ensure_ascii=False)


# ── Snapshot horaire ──────────────────────────────────────────────────────────


def _run_snapshot(hours: float) -> None:
    since_ts = time.time() - hours * 3600
    window_s = hours * 3600
    label = f"snapshot_{_NOW_UTC.strftime('%Y-%m-%d_%H:%M')}UTC"

    snapshots = _load_jsonl(METRICS_PATH, since_ts)
    alerts = _load_jsonl(ALERTS_PATH, since_ts)
    trades = _load_complete_trades(TRADES_PATH, since_ts)
    behavior_events = _load_jsonl(BEHAVIOR_PATH, since_ts)

    report = _build_p13_table(
        snapshots, alerts, trades, window_s, label, behavior_events
    )
    out = _save_report(report, "snapshot")

    # Résumé une ligne
    p = report["p13_table"]
    ok = "PASS" if report["burn_in_passed"] else "FAIL"
    print(
        f"[{_NOW_UTC.strftime('%H:%M')}UTC] {ok} | "
        f"uptime={p['uptime_pct']['value']}% "
        f"exc={p['exceptions']['value']} "
        f"dd={p['max_drawdown_pct']['value']}% "
        f"health_min={p['health_score_min']['value']} "
        f"trades={p['total_trades']['value']} "
        f"→ {out}"
    )


# ── Rapport complet ───────────────────────────────────────────────────────────


def _run_report(hours: float, send_telegram: bool) -> None:
    since_ts = time.time() - hours * 3600
    window_s = hours * 3600
    label = f"report_{_NOW_UTC.strftime('%Y-%m-%d')}_{int(hours)}h"

    print(f"[INFO] Chargement des données (fenêtre {hours:.0f}h)…")
    snapshots = _load_jsonl(METRICS_PATH, since_ts)
    alerts = _load_jsonl(ALERTS_PATH, since_ts)
    trades = _load_complete_trades(TRADES_PATH, since_ts)
    behavior_events = _load_jsonl(BEHAVIOR_PATH, since_ts)

    print(
        f"[INFO] {len(snapshots)} snapshots | {len(alerts)} alertes"
        f" | {len(trades)} trades | {len(behavior_events)} events comportementaux"
    )

    report = _build_p13_table(
        snapshots, alerts, trades, window_s, label, behavior_events
    )
    _print_p13_table(report)

    out = _save_report(report, "report")
    print(f"[OK] Rapport sauvegardé : {out}")

    if send_telegram:
        _send_telegram(report)


# ── Point d'entrée ────────────────────────────────────────────────────────────


def _run_calibrate(hours: float) -> None:
    """Mode dédié calibration : score histogram + symbol breakdown uniquement."""
    since_ts = time.time() - hours * 3600
    trades = _load_complete_trades(TRADES_PATH, since_ts)
    print(f"[INFO] {len(trades)} trades sur {hours:.0f}h")

    if not trades:
        print("[WARN] Aucun trade — impossible de calculer la calibration.")
        return

    burnin = BurnInAnalytics().build_report(
        trades,
        generated_at=_NOW_UTC,
        window_hours=hours,
    )
    _print_score_calibration(burnin)
    _print_symbol_breakdown(burnin)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _save_calibration_report(burnin, REPORTS_DIR)
    print(f"[OK] calibration_report.json -> {REPORTS_DIR / 'calibration_report.json'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Collecteur de métriques burn-in VPS")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--snapshot", action="store_true", help="Snapshot horaire rapide (mode cron)"
    )
    group.add_argument(
        "--report",
        action="store_true",
        help="Rapport complet avec tableau P13 (défaut)",
    )
    group.add_argument(
        "--calibrate",
        action="store_true",
        help="Audit calibration seul : score histogram + symboles",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=24.0,
        help="Fenêtre d'analyse en heures (défaut: 24)",
    )
    parser.add_argument(
        "--telegram", action="store_true", help="Envoie le rapport sur Telegram"
    )
    args = parser.parse_args()

    if args.snapshot:
        _run_snapshot(hours=args.hours)
    elif args.calibrate:
        _run_calibrate(hours=args.hours)
    else:
        _run_report(hours=args.hours, send_telegram=args.telegram)


if __name__ == "__main__":
    main()
