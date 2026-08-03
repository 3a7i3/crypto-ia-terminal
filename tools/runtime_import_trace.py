#!/usr/bin/env python3
"""Trace d'exécution — quels modules du projet sont RÉELLEMENT chargés.

Complète `tools/runtime_cartographer.py` (statique) par une preuve d'exécution :
importe le point d'entrée dans un interpréteur neuf et relève `sys.modules`.
Un module présent dans `sys.modules` a vu son corps EXÉCUTÉ — ce n'est plus
« atteignable par import », c'est « chargé ».

PASSIF : n'appelle jamais `main()`. Le garde `if __name__ == "__main__"` de
`core/advisor_loop.py` empêche le démarrage de la boucle. Aucun ordre, aucun
lock, aucun redémarrage.

Limite : couvre le chargement au BOOT. Les imports paresseux situés dans des
branches non prises au boot (ex. `_get_regret_engine()`) n'apparaissent pas.
Le résultat est donc une borne INFÉRIEURE des modules exécutés.

Usage :
    python tools/runtime_import_trace.py --entry core.advisor_loop \
        --out artifacts/import_trace.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CHILD = r"""
import json, sys, os, traceback
sys.path.insert(0, ROOT_PLACEHOLDER)
sys.path.insert(0, os.path.join(ROOT_PLACEHOLDER, "core"))
before = set(sys.modules)
status, err = "OK", None
try:
    __import__(ENTRY_PLACEHOLDER)
except BaseException as exc:
    status, err = type(exc).__name__, str(exc)[:400]
after = {n: getattr(m, "__file__", None) for n, m in list(sys.modules.items())}
print("@@@JSON@@@" + json.dumps({
    "status": status, "error": err,
    "before": sorted(before),
    "loaded": {k: v for k, v in after.items() if v},
}))
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", default="core.advisor_loop")
    ap.add_argument("--out", default="artifacts/import_trace.json")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    code = CHILD.replace("ROOT_PLACEHOLDER", repr(str(ROOT))).replace(
        "ENTRY_PLACEHOLDER", repr(args.entry)
    )

    env = dict(os.environ)
    # Neutralise toute tentative d'action : le module ne doit qu'être chargé.
    env["CRYPTO_IMPORT_TRACE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    try:
        r = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT après {args.timeout}s — l'import ne termine pas.")
        return 2

    payload = None
    for line in r.stdout.splitlines():
        if line.startswith("@@@JSON@@@"):
            payload = json.loads(line[len("@@@JSON@@@") :])
    if payload is None:
        print("Aucune sortie exploitable.")
        print("STDOUT:", r.stdout[-1500:])
        print("STDERR:", r.stderr[-1500:])
        return 3

    # Ne conserve que les modules du projet (fichier sous ROOT, hors .venv)
    project = {}
    for name, f in payload["loaded"].items():
        try:
            p = Path(f).resolve()
        except Exception:
            continue
        try:
            rel = p.relative_to(ROOT)
        except ValueError:
            continue
        if any(part in {".venv", "site-packages"} for part in rel.parts):
            continue
        project[name] = str(rel).replace("\\", "/")

    out = {
        "entry": args.entry,
        "status": payload["status"],
        "error": payload["error"],
        "measurement": "modules du projet présents dans sys.modules après import "
        "du point d'entrée — corps de module EXÉCUTÉ",
        "limit": "borne INFÉRIEURE : n'inclut pas les imports paresseux des "
        "branches non prises au boot",
        "project_modules_loaded": len(project),
        "modules": dict(sorted(project.items())),
    }
    dest = ROOT / args.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"status={out['status']} error={out['error']}")
    print(f"modules projet chargés = {out['project_modules_loaded']}")
    print(f"-> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
