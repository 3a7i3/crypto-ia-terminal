#!/usr/bin/env python3
"""
scripts/health_check.py — Vérification santé du process crypto-advisor.

Vérifie :
  - Process actif (PID depuis lock file)
  - Threads actifs
  - Child processes
  - File descriptors ouverts (count + types)
  - Mémoire RSS
  - CPU usage
  - Uptime
  - Logs récents (dernière activité)

Usage : python3 scripts/health_check.py [--json]
Exit 0 = OK | Exit 1 = WARNING | Exit 2 = CRITICAL
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
LOCK_FILE = ROOT / "logs" / "advisor.lock"
LOG_FILE = ROOT / "logs" / "advisor_loop.log"

W = 60


def _read_pid() -> int | None:
    if not LOCK_FILE.exists():
        return None
    try:
        return int(LOCK_FILE.read_text().strip())
    except (ValueError, OSError):
        return None


def _check_process(pid: int) -> dict:
    try:
        import psutil

        proc = psutil.Process(pid)
        with proc.oneshot():
            mem = proc.memory_info()
            cpu = proc.cpu_percent(interval=0.5)
            create_time = proc.create_time()
            status = proc.status()
            threads = proc.num_threads()
            children = proc.children(recursive=True)
            try:
                fds = proc.num_fds()
                open_files = proc.open_files()
                connections = proc.connections()
            except (psutil.AccessDenied, AttributeError):
                fds, open_files, connections = -1, [], []

        uptime_s = time.time() - create_time
        uptime_h = uptime_s / 3600

        fd_types: dict[str, int] = {}
        for of in open_files:
            ext = Path(of.path).suffix or "no_ext"
            fd_types[ext] = fd_types.get(ext, 0) + 1

        return {
            "pid": pid,
            "status": status,
            "uptime_h": round(uptime_h, 2),
            "threads": threads,
            "children": len(children),
            "children_pids": [c.pid for c in children],
            "mem_rss_mb": round(mem.rss / 1024 / 1024, 1),
            "cpu_pct": cpu,
            "fd_count": fds,
            "fd_by_type": fd_types,
            "open_sockets": len(connections),
            "ok": True,
        }
    except ImportError:
        # psutil absent — fallback /proc
        try:
            stat = Path(f"/proc/{pid}/status").read_text()
            vm_rss = next(
                (ln for ln in stat.splitlines() if ln.startswith("VmRSS")), ""
            )
            threads_line = next(
                (ln for ln in stat.splitlines() if ln.startswith("Threads")), ""
            )
            fd_count = len(list(Path(f"/proc/{pid}/fd").iterdir()))
            return {
                "pid": pid,
                "status": "running",
                "uptime_h": "?",
                "threads": int(threads_line.split()[1]) if threads_line else -1,
                "children": -1,
                "mem_rss_mb": (int(vm_rss.split()[1]) / 1024 if vm_rss else -1),
                "cpu_pct": -1,
                "fd_count": fd_count,
                "fd_by_type": {},
                "open_sockets": -1,
                "ok": True,
            }
        except Exception as e:
            return {"pid": pid, "ok": False, "error": str(e)}
    except Exception as e:
        return {"pid": pid, "ok": False, "error": str(e)}


def _check_log_activity() -> dict:
    if not LOG_FILE.exists():
        return {"exists": False, "lag_s": None, "last_line": None}
    try:
        stat = LOG_FILE.stat()
        lag_s = time.time() - stat.st_mtime
        # Lire dernière ligne non vide
        last_line = ""
        with open(LOG_FILE, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(4096, size)
            f.seek(-chunk, 2)
            tail = f.read(chunk).decode("utf-8", errors="replace")
        for line in reversed(tail.splitlines()):
            if line.strip():
                last_line = line.strip()[-120:]
                break
        return {"exists": True, "lag_s": round(lag_s, 1), "last_line": last_line}
    except Exception as e:
        return {"exists": True, "lag_s": None, "error": str(e), "last_line": None}


def _fd_inheritance_risk(proc_info: dict) -> list[str]:
    """Identifie les fd potentiellement hérités par des child processes."""
    warnings = []
    if proc_info.get("children", 0) > 0:
        warnings.append(
            f"{proc_info['children']} child process(es) actif(s) "
            f"(PIDs: {proc_info.get('children_pids', [])})"
        )
    fd_count = proc_info.get("fd_count", 0)
    if fd_count > 100:
        warnings.append(f"FD count élevé: {fd_count} (risque d'épuisement)")
    return warnings


def main(as_json: bool = False) -> int:
    pid = _read_pid()

    results: dict = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lock_file": str(LOCK_FILE),
        "pid": pid,
    }

    exit_code = 0

    # ── Process check ─────────────────────────────────────────────────────────
    if pid is None:
        results["process"] = {"ok": False, "error": "Lock file absent ou illisible"}
        exit_code = 2
    else:
        try:
            os.kill(pid, 0)
            proc_info = _check_process(pid)
            results["process"] = proc_info

            inheritance_warnings = _fd_inheritance_risk(proc_info)
            if inheritance_warnings:
                results["fd_warnings"] = inheritance_warnings
                exit_code = max(exit_code, 1)

            # Seuils d'alerte
            if proc_info.get("mem_rss_mb", 0) > 1500:
                results.setdefault("alerts", []).append(
                    f"Mémoire élevée: {proc_info['mem_rss_mb']} MB"
                )
                exit_code = max(exit_code, 1)

            if proc_info.get("cpu_pct", 0) > 80:
                results.setdefault("alerts", []).append(
                    f"CPU élevé: {proc_info['cpu_pct']}%"
                )
                exit_code = max(exit_code, 1)

        except ProcessLookupError:
            results["process"] = {
                "ok": False,
                "error": f"PID {pid} mort (lock périmé)",
            }
            exit_code = 2
        except PermissionError:
            results["process"] = {
                "ok": True,
                "note": f"PID {pid} vivant (accès restreint)",
            }

    # ── Log activity check ────────────────────────────────────────────────────
    log_info = _check_log_activity()
    results["log"] = log_info
    if log_info.get("lag_s") is not None and log_info["lag_s"] > 600:
        results.setdefault("alerts", []).append(
            f"Log inactif depuis {log_info['lag_s']:.0f}s (>10min — possible blocage)"
        )
        exit_code = max(exit_code, 1)

    # ── Output ────────────────────────────────────────────────────────────────
    if as_json:
        print(json.dumps(results, indent=2))
        return exit_code

    status_icon = {0: "✅ OK", 1: "⚠️  WARNING", 2: "❌ CRITICAL"}[exit_code]
    print(f"\n{'='*W}")
    print(f"  HEALTH CHECK — {results['timestamp']}  {status_icon}")
    print(f"{'='*W}")

    proc = results.get("process", {})
    if proc.get("ok"):
        print(f"  PID       : {pid}")
        print(f"  Status    : {proc.get('status', '?')}")
        print(f"  Uptime    : {proc.get('uptime_h', '?')} h")
        print(f"  Threads   : {proc.get('threads', '?')}")
        print(f"  Children  : {proc.get('children', '?')}")
        print(f"  Mémoire   : {proc.get('mem_rss_mb', '?')} MB")
        print(f"  CPU       : {proc.get('cpu_pct', '?')} %")
        print(f"  FDs ouverts: {proc.get('fd_count', '?')}")
        if proc.get("fd_by_type"):
            fd_str = "  ".join(f"{k}:{v}" for k, v in proc["fd_by_type"].items())
            print(f"  FD types  : {fd_str}")
        print(f"  Sockets   : {proc.get('open_sockets', '?')}")
    else:
        print(f"  ❌ Process: {proc.get('error', 'inconnu')}")

    log = results.get("log", {})
    if log.get("lag_s") is not None:
        lag_ok = "✅" if log["lag_s"] < 600 else "⚠️ "
        print(f"\n  Log lag   : {lag_ok} {log['lag_s']}s")
    if log.get("last_line"):
        print(f"  Dernière ligne: {log['last_line']}")

    if results.get("fd_warnings"):
        print(f"\n  ⚠️  FD warnings:")
        for w in results["fd_warnings"]:
            print(f"    - {w}")

    if results.get("alerts"):
        print(f"\n  🚨 Alertes:")
        for a in results["alerts"]:
            print(f"    - {a}")

    print(f"\n{'='*W}\n")
    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Health check crypto-advisor")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()
    sys.exit(main(as_json=args.json))
