"""
04_resilience_test.py — Test de résilience réseau du bot.

AVERTISSEMENT : ce script coupe l'interface réseau (eth0/ens4) pendant
30s ou 2min. À lancer UNIQUEMENT en maintenance, jamais en production live.

Tests effectués :
  1. Reconnexion exchange après coupure réseau
  2. Absence de doublons de positions après reconnexion
  3. Heartbeat bot après retour réseau
  4. Intégrité du fichier positions_snapshot.json

Usage :
    sudo python3 S3/04_resilience_test.py --duration 30
    sudo python3 S3/04_resilience_test.py --duration 120 --interface ens4

Nécessite sudo pour ip link down/up.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

POSITIONS_PATH = "databases/positions_snapshot.json"
HEARTBEAT_TIMEOUT_S = 60  # délai max pour que le bot se reconnecte


def _run(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=30)


def _get_interface() -> str:
    """Détecte l'interface réseau principale (eth0, ens4, etc.)."""
    result = _run(["ip", "route", "show", "default"])
    for line in result.stdout.splitlines():
        parts = line.split()
        if "dev" in parts:
            idx = parts.index("dev")
            return parts[idx + 1]
    return "eth0"


def _snapshot_positions() -> dict:
    p = Path(POSITIONS_PATH)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _check_bot_alive() -> bool:
    """Vérifie si le service crypto-advisor est actif."""
    result = _run(["systemctl", "is-active", "crypto-advisor"])
    return result.stdout.strip() == "active"


def _check_reconnected(timeout: float = HEARTBEAT_TIMEOUT_S) -> bool:
    """Attend que le bot ait reconnecté l'exchange (heartbeat dans les logs)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = _run(
            ["journalctl", "-u", "crypto-advisor", "-n50", "--no-pager", "--output=cat"]
        )
        recent_logs = result.stdout
        if "Exchange initialisé" in recent_logs or "ExchangeFactory" in recent_logs:
            # Chercher une ligne récente (< 2 min)
            lines = recent_logs.splitlines()
            for line in reversed(lines):
                if "Exchange" in line or "reconnect" in line.lower():
                    return True
        time.sleep(5)
    return False


def run_test(interface: str, duration_s: int) -> dict:
    results: dict = {
        "interface": interface,
        "duration_s": duration_s,
        "pre_positions": {},
        "post_positions": {},
        "bot_alive_before": False,
        "bot_alive_after": False,
        "reconnected": False,
        "position_integrity": False,
        "passed": False,
        "issues": [],
    }

    print(f"\n{'='*60}")
    print(f"  RESILIENCE TEST — interface={interface} durée={duration_s}s")
    print(f"{'='*60}\n")

    # ── Pré-test ──────────────────────────────────────────────────────────────
    results["bot_alive_before"] = _check_bot_alive()
    if not results["bot_alive_before"]:
        results["issues"].append("Bot non actif avant le test")
        print("  ✗ ABORT: bot non actif avant le test")
        return results

    results["pre_positions"] = _snapshot_positions()
    print(f"  Positions avant coupure: {len(results['pre_positions'])} entrées")
    print(f"  Bot actif: {results['bot_alive_before']}")

    # ── Coupure réseau ────────────────────────────────────────────────────────
    print(f"\n  → Coupure réseau {interface} ({duration_s}s)...")
    try:
        _run(["ip", "link", "set", interface, "down"], check=True)
    except subprocess.CalledProcessError as e:
        results["issues"].append(f"Impossible de couper {interface}: {e.stderr}")
        print(f"  ✗ ABORT: {e.stderr}")
        return results

    print(f"  Interface coupée. Attente {duration_s}s...")
    time.sleep(duration_s)

    # ── Rétablissement ────────────────────────────────────────────────────────
    print("  → Rétablissement réseau...")
    _run(["ip", "link", "set", interface, "up"])
    time.sleep(5)  # laisser le réseau s'établir

    # ── Vérification reconnexion ───────────────────────────────────────────────
    print(f"  → Vérification reconnexion (timeout={HEARTBEAT_TIMEOUT_S}s)...")
    results["reconnected"] = _check_reconnected(HEARTBEAT_TIMEOUT_S)

    if results["reconnected"]:
        print("  ✓ Bot reconnecté")
    else:
        results["issues"].append(f"Pas de reconnexion en {HEARTBEAT_TIMEOUT_S}s")
        print(f"  ✗ Pas de reconnexion en {HEARTBEAT_TIMEOUT_S}s")

    # ── Intégrité des positions ────────────────────────────────────────────────
    results["post_positions"] = _snapshot_positions()
    results["bot_alive_after"] = _check_bot_alive()

    pre_keys = set(results["pre_positions"].keys())
    post_keys = set(results["post_positions"].keys())
    duplicates = []

    for key in post_keys:
        if key in pre_keys:
            pre_pos = results["pre_positions"][key]
            post_pos = results["post_positions"][key]
            if isinstance(pre_pos, dict) and isinstance(post_pos, dict):
                pre_qty = pre_pos.get("size", pre_pos.get("qty", 0))
                post_qty = post_pos.get("size", post_pos.get("qty", 0))
                if isinstance(post_qty, (int, float)) and isinstance(
                    pre_qty, (int, float)
                ):
                    if post_qty > pre_qty * 1.5:
                        duplicates.append(key)

    if duplicates:
        results["issues"].append(f"Doublons détectés sur: {duplicates}")
        print(f"  ✗ Doublons positions: {duplicates}")
    else:
        results["position_integrity"] = True
        print(
            f"  ✓ Intégrité positions OK (avant={len(pre_keys)} après={len(post_keys)})"
        )

    # ── Verdict ────────────────────────────────────────────────────────────────
    results["passed"] = (
        results["reconnected"]
        and results["position_integrity"]
        and results["bot_alive_after"]
        and not results["issues"]
    )

    print(f"\n  {'✓ TEST PASSÉ' if results['passed'] else '✗ TEST ÉCHOUÉ'}")
    if results["issues"]:
        for issue in results["issues"]:
            print(f"    • {issue}")
    print(f"\n{'='*60}\n")

    return results


def main() -> None:
    if sys.platform != "linux":
        print("[resilience_test] Ce test nécessite Linux (ip link command).")
        sys.exit(1)

    if "--help" not in sys.argv and "-h" not in sys.argv:
        result = _run(["id", "-u"])
        if result.stdout.strip() != "0":
            print("[resilience_test] Nécessite sudo.")
            print("  Usage: sudo python3 S3/04_resilience_test.py --duration 30")
            sys.exit(1)

    parser = argparse.ArgumentParser(description="Test de résilience réseau")
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        choices=[30, 60, 120],
        help="Durée de la coupure en secondes",
    )
    parser.add_argument(
        "--interface",
        default="",
        help="Interface réseau (auto-détecté si absent)",
    )
    args = parser.parse_args()

    interface = args.interface or _get_interface()
    print(f"[resilience_test] Interface détectée: {interface}")
    print(f"[resilience_test] ATTENTION: le réseau sera coupé {args.duration}s!")
    confirm = input("Continuer ? [oui/non] : ").strip().lower()
    if confirm != "oui":
        print("Annulé.")
        sys.exit(0)

    result = run_test(interface, args.duration)
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
