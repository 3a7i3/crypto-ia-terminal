"""
02_log_surveillance.py — Surveillance des logs système toutes les 6h.

Scanne les logs du bot (systemd + fichiers) pour détecter :
  - Exceptions Python non gérées
  - Pics mémoire (OOM, MemoryError)
  - Watchdog restarts (crash loop)
  - DANGER / FREEZE / CRITICAL dans les logs
  - Inactivité anormale (pas de cycle depuis >15 min)
  - Taille des logs (rotation nécessaire ?)

Rapport : HEALTHY / WARNING / CRITICAL
Peut envoyer une alerte Telegram si configuré.

Usage :
    python3 S3/02_log_surveillance.py              # rapport one-shot
    python3 S3/02_log_surveillance.py --telegram   # + alerte si WARNING+
    python3 S3/02_log_surveillance.py --json       # sortie JSON (pour cron)

Cron (toutes les 6h) :
    0 */6 * * * cd /home/.../crypto_ai_terminal && python3 S3/02_log_surveillance.py --telegram
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LOG_LINES = 2000  # nb de lignes systemd à analyser
INACTIVITY_THRESHOLD_MIN = 15  # inactif si pas de cycle depuis N min
MAX_LOG_SIZE_MB = 100  # alerte si log > N MB


def _systemd_logs(lines: int = LOG_LINES) -> list[str]:
    """Lit les dernières N lignes du service systemd."""
    try:
        result = subprocess.run(
            [
                "journalctl",
                "-u",
                "crypto-advisor",
                f"-n{lines}",
                "--no-pager",
                "--output=cat",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout.splitlines()
    except Exception:
        return []


def _file_logs() -> list[str]:
    """Lit les fichiers de logs locaux."""
    lines = []
    log_dirs = ["logs/", "databases/"]
    for d in log_dirs:
        p = Path(d)
        if not p.exists():
            continue
        for f in p.glob("*.log"):
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    lines.extend(fh.readlines()[-500:])
            except Exception:
                pass
    return lines


def analyze(log_lines: list[str]) -> dict:
    """Analyse les lignes de log et retourne un rapport structuré."""
    issues: list[dict] = []
    text = "\n".join(log_lines)

    # ── Exceptions Python ─────────────────────────────────────────────────────
    exceptions = re.findall(
        r"(Traceback \(most recent call last\).*?)(?=\n\n|\Z)", text, re.DOTALL
    )
    # Compter aussi les ERROR logs simples
    error_lines = [l for l in log_lines if " ERROR " in l or " CRITICAL " in l]
    if exceptions:
        issues.append(
            {
                "severity": "WARNING",
                "category": "exceptions",
                "count": len(exceptions),
                "message": f"{len(exceptions)} traceback(s) Python détecté(s)",
            }
        )
    elif error_lines:
        issues.append(
            {
                "severity": "WARNING",
                "category": "errors",
                "count": len(error_lines),
                "message": f"{len(error_lines)} lignes ERROR/CRITICAL",
                "sample": error_lines[-1][:120] if error_lines else "",
            }
        )

    # ── Watchdog restarts ─────────────────────────────────────────────────────
    restarts = [
        l for l in log_lines if "restart" in l.lower() or "restarting" in l.lower()
    ]
    if len(restarts) >= 3:
        issues.append(
            {
                "severity": "WARNING",
                "category": "watchdog_restarts",
                "count": len(restarts),
                "message": f"{len(restarts)} redémarrages watchdog détectés — possible crash loop",
            }
        )

    # ── DANGER / FREEZE ───────────────────────────────────────────────────────
    danger_lines = [
        l for l in log_lines if "DANGER" in l or "FREEZE" in l or "CRITICAL" in l
    ]
    if danger_lines:
        issues.append(
            {
                "severity": (
                    "CRITICAL"
                    if any("CRITICAL" in l for l in danger_lines)
                    else "WARNING"
                ),
                "category": "danger_freeze",
                "count": len(danger_lines),
                "message": f"{len(danger_lines)} DANGER/FREEZE/CRITICAL events",
                "sample": danger_lines[-1][:120],
            }
        )

    # ── Mémoire ───────────────────────────────────────────────────────────────
    mem_issues = [
        l
        for l in log_lines
        if "MemoryError" in l or "OOM" in l or "out of memory" in l.lower()
    ]
    if mem_issues:
        issues.append(
            {
                "severity": "CRITICAL",
                "category": "memory",
                "count": len(mem_issues),
                "message": f"Problème mémoire détecté: {mem_issues[-1][:100]}",
            }
        )

    # ── Inactivité ────────────────────────────────────────────────────────────
    cycle_lines = [
        l for l in log_lines if "cycle" in l.lower() or "advisor_loop" in l.lower()
    ]
    if cycle_lines:
        # Chercher le timestamp de la dernière ligne de cycle
        last_cycle_line = cycle_lines[-1]
        ts_match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", last_cycle_line)
        if ts_match:
            try:
                last_ts = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S")
                last_ts = last_ts.replace(tzinfo=timezone.utc)
                elapsed_min = (
                    datetime.now(timezone.utc) - last_ts
                ).total_seconds() / 60
                if elapsed_min > INACTIVITY_THRESHOLD_MIN:
                    issues.append(
                        {
                            "severity": "WARNING",
                            "category": "inactivity",
                            "message": f"Dernier cycle il y a {elapsed_min:.0f} min (seuil: {INACTIVITY_THRESHOLD_MIN} min)",
                        }
                    )
            except ValueError:
                pass
    elif log_lines:
        issues.append(
            {
                "severity": "WARNING",
                "category": "inactivity",
                "message": "Aucun cycle détecté dans les logs récents",
            }
        )

    # ── Taille des logs ───────────────────────────────────────────────────────
    for log_path in (
        Path("databases/").glob("*.jsonl") if Path("databases/").exists() else []
    ):
        try:
            size_mb = log_path.stat().st_size / 1024 / 1024
            if size_mb > MAX_LOG_SIZE_MB:
                issues.append(
                    {
                        "severity": "WARNING",
                        "category": "log_size",
                        "message": f"{log_path.name} = {size_mb:.1f} MB (seuil: {MAX_LOG_SIZE_MB} MB)",
                    }
                )
        except Exception:
            pass

    # ── Verdict global ────────────────────────────────────────────────────────
    if any(i["severity"] == "CRITICAL" for i in issues):
        status = "CRITICAL"
    elif issues:
        status = "WARNING"
    else:
        status = "HEALTHY"

    return {
        "status": status,
        "ts": datetime.now(timezone.utc).isoformat(),
        "log_lines_analyzed": len(log_lines),
        "issues": issues,
        "issue_count": len(issues),
    }


def format_report(report: dict) -> str:
    status = report["status"]
    icon = {"HEALTHY": "✅", "WARNING": "⚠️", "CRITICAL": "🚨"}.get(status, "?")
    lines = [
        f"{icon} LOG SURVEILLANCE — {status}",
        f"  {report['ts'][:19]} | {report['log_lines_analyzed']} lignes analysées",
    ]
    if report["issues"]:
        lines.append(f"  {report['issue_count']} problème(s):")
        for issue in report["issues"]:
            sev = issue["severity"]
            lines.append(f"    [{sev}] {issue['category']}: {issue['message']}")
    else:
        lines.append("  Aucun problème détecté.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Surveillance des logs système")
    parser.add_argument(
        "--telegram", action="store_true", help="Alerte Telegram si WARNING+"
    )
    parser.add_argument("--json", action="store_true", help="Sortie JSON brute")
    parser.add_argument(
        "--min-severity", default="WARNING", choices=["WARNING", "CRITICAL"]
    )
    args = parser.parse_args()

    log_lines = _systemd_logs() + _file_logs()
    report = analyze(log_lines)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    print(format_report(report))

    if args.telegram and report["status"] != "HEALTHY":
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from S3.telegram_alerts import TelegramAlert

            alert = TelegramAlert()
            alert.danger(report["status"], format_report(report)[:400])
            time.sleep(3)
        except Exception as exc:
            print(f"[log_surveillance] Telegram échoué: {exc}")

    sys.exit(0 if report["status"] == "HEALTHY" else 1)


if __name__ == "__main__":
    main()
