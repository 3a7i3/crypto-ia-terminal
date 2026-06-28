#!/usr/bin/env python3
"""
scripts/performance_check.py — Audit performance du service crypto-advisor.

Mesure :
  - Latence moyenne d'une boucle (depuis les logs)
  - Temps d'inférence IA (si loggué)
  - Latence API MEXC (si loggué)
  - Mémoire RSS du process (live)
  - CPU usage moyen (sur 3s)
  - Tendance mémoire (dernier 1h de logs si disponible)

Usage :
    python3 scripts/performance_check.py [--json] [--tail N]
Exit 0 = OK | Exit 1 = WARNING | Exit 2 = CRITICAL
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
LOCK_FILE = ROOT / "logs" / "advisor.lock"
LOG_FILE = ROOT / "logs" / "advisor_loop.log"

W = 64

# Patterns dans les logs (adapter selon format réel)
_RE_CYCLE_MS = re.compile(r"cycle.*?(\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)
_RE_INFER_MS = re.compile(r"infer(?:ence)?.*?(\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)
_RE_API_MS = re.compile(r"api.*?(\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)
_RE_LATENCY = re.compile(r"latency[:\s]+(\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)


def _read_pid() -> int | None:
    if not LOCK_FILE.exists():
        return None
    try:
        return int(LOCK_FILE.read_text().strip())
    except (ValueError, OSError):
        return None


def _sample_process(pid: int, duration_s: float = 3.0) -> dict:
    try:
        import psutil

        proc = psutil.Process(pid)
        proc.cpu_percent(interval=None)  # premier appel = init
        time.sleep(duration_s)
        cpu = proc.cpu_percent(interval=None)
        mem = proc.memory_info()
        threads = proc.num_threads()
        return {
            "cpu_pct": round(cpu, 1),
            "mem_rss_mb": round(mem.rss / 1024 / 1024, 1),
            "threads": threads,
            "ok": True,
        }
    except ImportError:
        return {"ok": False, "error": "psutil absent"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _parse_log_metrics(tail_lines: int = 500) -> dict:
    if not LOG_FILE.exists():
        return {"ok": False, "error": "Log absent"}

    # Lire les N dernières lignes
    lines: list[str] = []
    try:
        with open(LOG_FILE, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(tail_lines * 200, size)
            f.seek(-chunk, 2)
            raw = f.read(chunk).decode("utf-8", errors="replace")
        lines = raw.splitlines()[-tail_lines:]
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    cycle_ms: list[float] = []
    infer_ms: list[float] = []
    api_ms: list[float] = []

    for line in lines:
        for val in _RE_CYCLE_MS.findall(line):
            cycle_ms.append(float(val))
        for val in _RE_INFER_MS.findall(line):
            infer_ms.append(float(val))
        for val in _RE_API_MS.findall(line):
            api_ms.append(float(val))
        for val in _RE_LATENCY.findall(line):
            api_ms.append(float(val))

    def _stats(vals: list[float]) -> dict | None:
        if not vals:
            return None
        return {
            "n": len(vals),
            "mean_ms": round(sum(vals) / len(vals), 1),
            "min_ms": round(min(vals), 1),
            "max_ms": round(max(vals), 1),
            "p95_ms": round(sorted(vals)[int(len(vals) * 0.95)], 1),
        }

    return {
        "ok": True,
        "lines_scanned": len(lines),
        "cycle": _stats(cycle_ms),
        "inference": _stats(infer_ms),
        "api": _stats(api_ms),
    }


def main(as_json: bool = False, tail_lines: int = 500) -> int:
    pid = _read_pid()
    exit_code = 0

    results: dict = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pid": pid,
    }

    # Métriques live du process
    if pid is not None:
        try:
            os.kill(pid, 0)
            print("  ⏱  Sampling CPU/mémoire (3s)…", end="\r")
            proc = _sample_process(pid)
            results["process"] = proc
            if proc.get("ok"):
                if proc.get("cpu_pct", 0) > 80:
                    exit_code = max(exit_code, 1)
                if proc.get("mem_rss_mb", 0) > 1500:
                    exit_code = max(exit_code, 1)
        except (ProcessLookupError, PermissionError):
            results["process"] = {"ok": False, "error": f"PID {pid} inaccessible"}
            exit_code = 2
    else:
        results["process"] = {"ok": False, "error": "Service non actif"}
        exit_code = 2

    # Métriques depuis les logs
    log_metrics = _parse_log_metrics(tail_lines)
    results["log_metrics"] = log_metrics

    # Seuils de performance
    alerts: list[str] = []
    if log_metrics.get("cycle") and log_metrics["cycle"]["mean_ms"] > 5000:
        alerts.append(f"Boucle lente: {log_metrics['cycle']['mean_ms']} ms moyenne")
        exit_code = max(exit_code, 1)
    if log_metrics.get("api") and log_metrics["api"]["p95_ms"] > 2000:
        alerts.append(f"API lente p95: {log_metrics['api']['p95_ms']} ms")
        exit_code = max(exit_code, 1)
    results["alerts"] = alerts

    if as_json:
        print(json.dumps(results, indent=2))
        return exit_code

    # ── Affichage ─────────────────────────────────────────────────────────────
    icon = {0: "✅ OK", 1: "⚠️  WARNING", 2: "❌ CRITICAL"}[exit_code]
    print(f"\n{'='*W}")
    print(f"  PERFORMANCE CHECK — {results['timestamp']}  {icon}")
    print(f"{'='*W}")

    proc = results.get("process", {})
    if proc.get("ok"):
        print(f"  PID    : {pid}")
        print(f"  CPU    : {proc['cpu_pct']} %  (moy. 3s)")
        print(f"  Mémoire: {proc['mem_rss_mb']} MB RSS")
        print(f"  Threads: {proc['threads']}")
    else:
        print(f"  ❌ Process: {proc.get('error', '?')}")

    lm = log_metrics
    if lm.get("ok"):
        print(f"\n  Logs scannés: {lm['lines_scanned']} lignes")
        for key, label in [
            ("cycle", "Boucle"),
            ("inference", "Inférence IA"),
            ("api", "API"),
        ]:
            s = lm.get(key)
            if s:
                print(
                    f"  {label:<16}: n={s['n']} "
                    f"moy={s['mean_ms']}ms min={s['min_ms']}ms "
                    f"max={s['max_ms']}ms p95={s['p95_ms']}ms"
                )
            else:
                print(f"  {label:<16}: aucune mesure trouvée dans les logs")
    else:
        print(f"  ❌ Logs: {lm.get('error', '?')}")

    if alerts:
        print(f"\n  🚨 Alertes performance:")
        for a in alerts:
            print(f"    - {a}")

    print(f"\n{'='*W}\n")
    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Performance check crypto-advisor")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    parser.add_argument("--tail", type=int, default=500, help="Lignes de log à scanner")
    args = parser.parse_args()
    sys.exit(main(as_json=args.json, tail_lines=args.tail))
