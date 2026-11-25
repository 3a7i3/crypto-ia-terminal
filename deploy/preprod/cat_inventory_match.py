"""CAT-PREPROD-01 / S4-B-RV1 — rapproche un inventaire de production des objets git du dépôt local.

Usage (poste de travail, dépôt à jour avec toutes les branches et refs de PR) :
    git fetch origin '+refs/heads/*:refs/remotes/origin/*' '+refs/pull/*/head:refs/remotes/pr/*'
    python3 -I deploy/preprod/cat_inventory_match.py cat-prod-inventory.json [--ref origin/main] > match.json

Pour chaque fichier servi (API, web, sources de build), classe son blob :
  SAME_AS_REF     : identique au fichier de même chemin dans --ref ;
  IN_GITHUB_OTHER : l'objet existe dans le dépôt (autre version, autre branche) mais diffère de --ref ;
  ABSENT          : l'objet n'existe dans aucune ref récupérée : source non publiée sur GitHub.
Lecture seule : n'écrit rien dans le dépôt, n'accède à aucun réseau.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter


def git(*args: str, data: str | None = None) -> str:
    return subprocess.run(["git", *args], input=data, capture_output=True, text=True, check=False).stdout


def existing(blobs: set[str]) -> set[str]:
    out = git("cat-file", "--batch-check=%(objectname) %(objecttype)", data="".join(b + "\n" for b in sorted(blobs)))
    return {line.split()[0] for line in out.splitlines() if line.endswith(" blob")}


def ref_blob(ref: str, path: str) -> str | None:
    sha = git("rev-parse", "-q", "--verify", f"{ref}:{path}").strip()
    return sha or None


def groups(inv: dict) -> dict[str, tuple[str, dict]]:
    g = {}
    api = inv.get("api_tree", {}).get("files")
    if isinstance(api, dict):
        g["api"] = ("", api)
    dist = inv.get("web_dist", {}).get("files")
    if isinstance(dist, dict):
        g["web_dist"] = (None, dist)  # built bundle: compared by existence only
    srv = inv.get("web_server", {}).get("host_dir_files")
    if isinstance(srv, dict):
        g["web_server"] = ("frontend/scripts/", srv)
    for name, files in (inv.get("build_sources") or {}).items():
        if isinstance(files, dict):
            g["build:" + name] = ("frontend/" if "frontend" in name else "", files)
    return g


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inventory")
    ap.add_argument("--ref", default="origin/main")
    a = ap.parse_args()
    with open(a.inventory, encoding="utf-8") as fh:
        inv = json.load(fh)
    g = groups(inv)
    all_blobs = {v[0] for _, files in g.values() for v in files.values() if isinstance(v, list) and len(v[0]) == 40}
    known = existing(all_blobs)
    report: dict = {"ref": a.ref, "ref_commit": git("rev-parse", a.ref).strip(), "groups": {}}
    for name, (prefix, files) in g.items():
        rows, counts = {}, Counter()
        for rel, v in sorted(files.items()):
            if not (isinstance(v, list) and len(v[0]) == 40):
                rows[rel] = "UNREADABLE"
                counts["UNREADABLE"] += 1
                continue
            if prefix is not None and ref_blob(a.ref, prefix + rel) == v[0]:
                cls = "SAME_AS_REF"
            elif v[0] in known:
                cls = "IN_GITHUB_OTHER"
            else:
                cls = "ABSENT"
            counts[cls] += 1
            if cls != "SAME_AS_REF":
                rows[rel] = {"class": cls, "blob": v[0]}
        report["groups"][name] = {"counts": dict(counts), "not_same_as_ref": rows}
    json.dump(report, sys.stdout, indent=1, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
