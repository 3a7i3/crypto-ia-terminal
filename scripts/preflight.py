#!/usr/bin/env python3
"""
scripts/preflight.py — Validation pré-démarrage du service crypto-advisor.

Vérifie TOUT avant de laisser systemd lancer le service :
  1. Version Python (≥3.9)
  2. Variables d'environnement critiques
  3. Espace disque (≥500 MB)
  4. Permissions répertoires (logs/, databases/)
  5. Santé du process existant (double-check lock périmé)
  6. Qualité données (si paper_trades.jsonl existe)

Usage :
    python3 scripts/preflight.py
    # Dans systemd : ExecStartPre=python3 /path/to/scripts/preflight.py

Exit 0 = GO | Exit 1 = ABORT (problème critique détecté)
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

REQUIRED_ENV = [
    "MEXC_API_KEY",
    "MEXC_API_SECRET",
]
OPTIONAL_ENV_DEFAULTS = {
    "PB_MIN_POSITION_USD": "3",
    "PAPER_TRADING": "true",
}
MIN_DISK_MB = 500
MIN_PYTHON = (3, 9)

W = 64

_ok = True
_warnings: list[str] = []
_errors: list[str] = []


def _fail(msg: str) -> None:
    global _ok
    _ok = False
    _errors.append(msg)


def _warn(msg: str) -> None:
    _warnings.append(msg)


# ── 1. Version Python ─────────────────────────────────────────────────────────
def check_python() -> None:
    v = sys.version_info[:2]
    if v < MIN_PYTHON:
        _fail(f"Python {v[0]}.{v[1]} < {MIN_PYTHON[0]}.{MIN_PYTHON[1]} requis")
    else:
        print(f"  ✅ Python {v[0]}.{v[1]}")


# ── 2. Variables d'environnement ──────────────────────────────────────────────
def check_env() -> None:
    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    if missing:
        _fail(f"Variables manquantes: {', '.join(missing)}")
    else:
        print(f"  ✅ Env vars obligatoires présentes ({len(REQUIRED_ENV)})")

    # Rappel des defaults
    for k, default in OPTIONAL_ENV_DEFAULTS.items():
        val = os.getenv(k, default)
        print(f"  ℹ  {k}={val}")


# ── 3. Espace disque ──────────────────────────────────────────────────────────
def check_disk() -> None:
    usage = shutil.disk_usage(ROOT)
    free_mb = usage.free / 1024 / 1024
    if free_mb < MIN_DISK_MB:
        _fail(f"Espace disque insuffisant: {free_mb:.0f} MB < {MIN_DISK_MB} MB requis")
    else:
        print(f"  ✅ Disque: {free_mb:.0f} MB disponible")


# ── 4. Permissions répertoires ────────────────────────────────────────────────
def check_permissions() -> None:
    dirs = [ROOT / "logs", ROOT / "databases"]
    for d in dirs:
        if not d.exists():
            try:
                d.mkdir(parents=True, exist_ok=True)
                print(f"  ✅ Créé: {d.name}/")
            except PermissionError:
                _fail(f"Impossible de créer {d} — permission refusée")
        elif not os.access(d, os.W_OK):
            _fail(f"Répertoire {d.name}/ non accessible en écriture")
        else:
            print(f"  ✅ Permissions {d.name}/: OK")


# ── 5. Lock périmé ────────────────────────────────────────────────────────────
def check_stale_lock() -> None:
    lock = ROOT / "logs" / "advisor.lock"
    if not lock.exists():
        print("  ✅ Lock: absent (premier démarrage)")
        return
    try:
        pid_str = lock.read_text().strip()
        if not pid_str.isdigit():
            _warn(
                f"Lock file illisible (contenu: {pid_str!r}) — sera écrasé au démarrage"
            )
            return
        pid = int(pid_str)
        try:
            os.kill(pid, 0)
            _fail(
                f"Process PID {pid} déjà actif — double démarrage interdit. "
                "Arrêter l'instance existante avant de relancer."
            )
        except PermissionError:
            # PID vivant mais accès restreint (Linux) → bloquer
            _fail(
                f"Process PID {pid} actif (accès restreint) — "
                "vérifier manuellement avant de continuer"
            )
        except OSError:
            # ProcessLookupError (Linux) ou WinError 87 (Windows) → PID mort
            _warn(f"Lock périmé (PID {pid} mort) — auto-nettoyage au démarrage")
            print(f"  ⚠️  Lock périmé PID {pid} — auto-nettoyage prévu")
    except OSError as e:
        _warn(f"Lecture lock: {e}")


# ── 6. Qualité données ────────────────────────────────────────────────────────
def check_data_quality() -> None:
    jsonl = ROOT / "databases" / "paper_trades.jsonl"
    if not jsonl.exists():
        print("  ✅ paper_trades.jsonl: absent (démarrage propre)")
        return
    import json

    parse_errors = 0
    n_events = 0
    with jsonl.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            n_events += 1
            try:
                json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1

    if parse_errors > 0:
        _fail(f"paper_trades.jsonl: {parse_errors}/{n_events} lignes JSON corrompues")
    else:
        print(f"  ✅ paper_trades.jsonl: {n_events} événements propres")


# ── Runner ────────────────────────────────────────────────────────────────────
def main() -> int:
    global _ok
    _ok = True
    _warnings.clear()
    _errors.clear()

    print(f"\n{'='*W}")
    print("  PREFLIGHT CHECK — crypto-advisor")
    print(f"{'='*W}")

    check_python()
    check_env()
    check_disk()
    check_permissions()
    check_stale_lock()
    check_data_quality()

    print(f"\n{'─'*W}")
    if _warnings:
        for w in _warnings:
            print(f"  ⚠️  {w}")

    if _errors:
        for e in _errors:
            print(f"  ❌ {e}")
        print(f"\n  🔴 ABORT — {len(_errors)} erreur(s) critique(s)")
        print(f"{'='*W}\n")
        return 1

    print(f"  🟢 GO — service autorisé à démarrer")
    print(f"{'='*W}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
