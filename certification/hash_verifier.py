#!/usr/bin/env python3
"""
Cybertechnique Hash Verifier
Usage:
  python hash_verifier.py compute   # calcule et enregistre les hashes
  python hash_verifier.py verify    # vérifie l'intégrité des modules certifiés
  python hash_verifier.py status    # affiche le niveau de chaque module
"""

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent
REGISTRY = WORKSPACE / ".vscode" / "cybertechnique" / "registry" / "module_levels.json"
CERTIFIED = (
    WORKSPACE / ".vscode" / "cybertechnique" / "registry" / "certified_modules.json"
)

COLORS = {
    "NUCLEAR": "\033[91m",
    "IMMUTABLE": "\033[33m",
    "LIVE_CORE": "\033[96m",
    "CRITICAL": "\033[31m",
    "SEALED": "\033[35m",
    "CERTIFIED": "\033[92m",
    "NORMAL": "\033[37m",
    "RESET": "\033[0m",
    "OK": "\033[92m",
    "FAIL": "\033[91m",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_registry():
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)


def cmd_compute():
    registry = load_registry()
    result = {}
    ts = datetime.now().isoformat()

    for mod_path, level in registry.get("modules", {}).items():
        full = WORKSPACE / mod_path.replace("/", "\\")
        c = COLORS.get(level, COLORS["NORMAL"])
        r = COLORS["RESET"]
        if full.exists():
            digest = sha256(full)
            result[mod_path] = {
                "sha256": digest,
                "level": level,
                "certified_at": ts,
                "mutation_policy": registry["levels"][level]["mutation_policy"],
            }
            print(f"{c}[{level:<10}]{r} {mod_path}")
            print(f"           {digest}")
        else:
            print(f"\033[90m[MISSING   ] {mod_path}{r}")

    with open(CERTIFIED, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(
        f"\n{COLORS['OK']}[OK] {len(result)} modules certifies -> {CERTIFIED}{COLORS['RESET']}\n"
    )


def cmd_verify():
    if not CERTIFIED.exists() or CERTIFIED.stat().st_size < 5:
        print("Aucun certified_modules.json. Lance: python hash_verifier.py compute")
        return 1

    with open(CERTIFIED, encoding="utf-8") as f:
        certified = json.load(f)

    ok = drift = missing = 0

    for mod_path, record in certified.items():
        full = WORKSPACE / mod_path.replace("/", "\\")
        level = record["level"]
        c = COLORS.get(level, COLORS["NORMAL"])
        r = COLORS["RESET"]

        if not full.exists():
            print(f"\033[90m[MISSING ] [{level:<10}] {mod_path}{r}")
            missing += 1
            continue

        current = sha256(full)
        if current == record["sha256"]:
            print(f"{COLORS['OK']}[OK    ]{r} {c}[{level:<10}]{r} {mod_path}")
            ok += 1
        else:
            print(f"{COLORS['FAIL']}[DRIFT  ] [{level:<10}] {mod_path}{r}")
            print(f"           attendu : {record['sha256'][:32]}...")
            print(f"           actuel  : {current[:32]}...")
            drift += 1

    print(f"\nOK: {ok}  |  DRIFT: {drift}  |  MISSING: {missing}")
    return 1 if (drift > 0 or missing > 0) else 0


def cmd_status():
    registry = load_registry()
    print("\n=== CYBERTECHNIQUE MODULE STATUS ===\n")
    for level in [
        "NUCLEAR",
        "IMMUTABLE",
        "LIVE_CORE",
        "CRITICAL",
        "SEALED",
        "CERTIFIED",
    ]:
        mods = [m for m, l in registry.get("modules", {}).items() if l == level]
        if not mods:
            continue
        c = COLORS.get(level, "")
        r = COLORS["RESET"]
        print(f"{c}---- {level} {'-'*(30 - len(level))}{r}")
        for m in mods:
            exists = "[OK]" if (WORKSPACE / m.replace("/", "\\")).exists() else "[--]"
            print(f"  {exists}  {m}")
        print()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "compute":
        cmd_compute()
    elif cmd == "verify":
        sys.exit(cmd_verify())
    else:
        cmd_status()
