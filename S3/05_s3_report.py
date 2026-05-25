"""
05_s3_report.py — Bilan de fin S3 : PRÊT ou PAS PRÊT pour le live (S4).

Évalue 6 dimensions :
  1. Stabilité système  — crashes, redémarrages, uptimestabilité
  2. Performance trading — win rate paper sur la période S3
  3. Gate efficacité     — ratio refus justifiés / trades permis
  4. SelfAwareness      — nb de DANGER/FREEZE inappropriés
  5. Shadow execution    — trades refusés auraient-ils gagné ?
  6. Infrastructure     — latence, reconnexions, mémoire

Verdict binaire: PRÊT → S4 live / PAS PRÊT → continuer S3

Usage :
    python3 S3/05_s3_report.py
    python3 S3/05_s3_report.py --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections import Counter
from pathlib import Path

PAPER_TRACKER_PATH = "databases/paper_tracking.jsonl"
GATE_CSV_PATH = "databases/gate_rejections.csv"
SHADOW_PATH = "databases/shadow_s3_refused.jsonl"
MM_PATH = "databases/mistake_memory.jsonl"


def _load_jsonl(path: str, days: int = 14) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    cutoff = time.time() - days * 86400
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    d = json.loads(line)
                    if d.get("ts", 0) >= cutoff:
                        rows.append(d)
                except json.JSONDecodeError:
                    pass
    return rows


def _load_gate_csv(days: int = 14) -> list[dict]:
    import csv

    p = Path(GATE_CSV_PATH)
    if not p.exists():
        return []
    cutoff = time.time() - days * 86400
    rows = []
    with open(p, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                if float(row.get("ts", 0)) >= cutoff:
                    rows.append(row)
            except ValueError:
                pass
    return rows


def _uptime_days() -> float:
    try:
        result = subprocess.run(
            ["systemctl", "show", "crypto-advisor", "--property=ActiveEnterTimestamp"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        line = result.stdout.strip()
        if "=" in line:
            ts_str = line.split("=", 1)[1].strip()
            from datetime import datetime

            ts = datetime.strptime(ts_str[:19], "%a %Y-%m-%d %H:%M:%S")
            return (time.time() - ts.timestamp()) / 86400
    except Exception:
        pass
    return 0.0


def evaluate() -> dict:
    scores: dict[str, dict] = {}

    # ── 1. Stabilité système ────────────────────────────────────────────────────
    uptime = _uptime_days()
    try:
        result = subprocess.run(
            [
                "journalctl",
                "-u",
                "crypto-advisor",
                "-n2000",
                "--no-pager",
                "--output=cat",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        logs = result.stdout.splitlines()
    except Exception:
        logs = []

    crashes = sum(1 for l in logs if "CRITICAL" in l or "Traceback" in l)
    restarts = sum(1 for l in logs if "restart" in l.lower())

    scores["stability"] = {
        "label": "Stabilité système",
        "uptime_days": round(uptime, 1),
        "crashes": crashes,
        "restarts": restarts,
        "pass": crashes == 0 and restarts <= 2,
        "note": f"Uptime={uptime:.1f}j, {crashes} crash(es), {restarts} restart(s)",
    }

    # ── 2. Performance trading (paper tracker) ──────────────────────────────────
    paper_rows = _load_jsonl(PAPER_TRACKER_PATH, days=14)
    total_trades = sum(r.get("trades", 0) for r in paper_rows)
    total_wins = sum(r.get("wins", 0) for r in paper_rows)
    days_active = len([r for r in paper_rows if r.get("trades", 0) > 0])
    wr = total_wins / total_trades if total_trades else 0

    scores["trading"] = {
        "label": "Performance paper trading",
        "days_active": days_active,
        "total_trades": total_trades,
        "win_rate": round(wr, 3),
        "pass": wr >= 0.50 and days_active >= 7,
        "note": f"WR={wr:.0%} sur {total_trades} trades ({days_active} jours actifs)",
    }

    # ── 3. Gate efficacité ──────────────────────────────────────────────────────
    gate_rows = _load_gate_csv(days=14)
    gate_total = len(gate_rows)
    gate_blocked = sum(1 for r in gate_rows if r.get("allowed", "True") == "False")
    gate_block_rate = gate_blocked / gate_total if gate_total else 0

    scores["gate"] = {
        "label": "Gate efficacité",
        "total_checks": gate_total,
        "blocked": gate_blocked,
        "block_rate": round(gate_block_rate, 3),
        "pass": 0.20 <= gate_block_rate <= 0.80,
        "note": f"Taux de blocage={gate_block_rate:.0%} ({gate_blocked}/{gate_total})",
    }

    # ── 4. SelfAwareness ────────────────────────────────────────────────────────
    danger_events = sum(1 for l in logs if "DANGER" in l or "FREEZE" in l)

    scores["self_awareness"] = {
        "label": "SelfAwareness",
        "danger_events": danger_events,
        "pass": danger_events <= 3,
        "note": f"{danger_events} événements DANGER/FREEZE",
    }

    # ── 5. Shadow execution ──────────────────────────────────────────────────────
    shadow_rows = _load_jsonl(SHADOW_PATH, days=14)
    shadow_count = len(shadow_rows)
    shadow_pnls = [
        r.get("pnl_simulated")
        for r in shadow_rows
        if r.get("pnl_simulated") is not None
    ]
    shadow_wr = (
        sum(1 for p in shadow_pnls if p > 0) / len(shadow_pnls) if shadow_pnls else None
    )

    scores["shadow"] = {
        "label": "Shadow execution",
        "refused_trades": shadow_count,
        "shadow_win_rate": round(shadow_wr, 3) if shadow_wr is not None else None,
        "pass": shadow_wr is None or shadow_wr <= 0.50,
        "note": (
            f"{shadow_count} refus, WR simulé={shadow_wr:.0%}"
            if shadow_wr is not None
            else f"{shadow_count} refus (PnL simulé insuffisant)"
        ),
    }

    # ── 6. Infrastructure ────────────────────────────────────────────────────────
    mem_issues = sum(1 for l in logs if "MemoryError" in l or "OOM" in l)
    reconnects = sum(
        1 for l in logs if "reconnect" in l.lower() or "Exchange initialisé" in l
    )

    scores["infra"] = {
        "label": "Infrastructure",
        "memory_errors": mem_issues,
        "reconnections": reconnects,
        "pass": mem_issues == 0 and reconnects <= 5,
        "note": f"{mem_issues} erreurs mémoire, {reconnects} reconnexions",
    }

    # ── Verdict final ────────────────────────────────────────────────────────────
    passed_count = sum(1 for s in scores.values() if s.get("pass", False))
    total_count = len(scores)
    ready = passed_count >= 5 and scores["trading"]["pass"]

    return {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "verdict": "PRÊT" if ready else "PAS PRÊT",
        "passed": passed_count,
        "total": total_count,
        "dimensions": scores,
        "ready_for_s4": ready,
    }


def print_report(report: dict) -> None:
    icon = "✅" if report["ready_for_s4"] else "❌"
    print(f"\n{'='*60}")
    print(f"  RAPPORT BILAN S3 — {report['ts']}")
    print(f"  Verdict: {icon} {report['verdict']} pour S4 Live")
    print(f"  Score: {report['passed']}/{report['total']} dimensions")
    print(f"{'='*60}")

    for key, dim in report["dimensions"].items():
        status = "✓" if dim.get("pass") else "✗"
        print(f"\n  [{status}] {dim['label']}")
        print(f"      {dim['note']}")

    print(f"\n{'='*60}")
    if report["ready_for_s4"]:
        print("  ACTION: Déployer S4 — passage en live avec capital réduit")
    else:
        failed = [
            d["label"] for d in report["dimensions"].values() if not d.get("pass")
        ]
        print(f"  ACTION: Continuer S3 — corriger: {', '.join(failed)}")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bilan S3 — décision PRÊT/PAS PRÊT pour S4"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = evaluate()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
