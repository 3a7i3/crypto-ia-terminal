"""Suivi de main pour le Repository Cartographer (décision Mathieu 2026-11-22 10:28Z).

Avant chaque passage, l'unité de suivi récupère main (lecture GitHub seule) dans un arbre
distinct, puis ce module dérive la mission de la mission modèle : même profil, même zone, même
question, seul `analyzed_ref` change. L'identifiant de mission reste le hash de son identité :
une nouvelle révision de main donne une nouvelle mission, la même révision la même mission.

Sorties (écriture atomique dans `--out`) :
- `mission.json` : la mission dérivée, validée par le contrat ;
- `current.env` : ANALYSED_SHA et MISSION_ID pour l'unité systemd du cartographe ;
- `repository-cartographer.mission` : l'identifiant de mission courant, lu par l'API.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from pathlib import Path

from agent_bench.observation import contract as c

HEX40 = re.compile(r"^[0-9a-f]{40}$")
POINTER = "repository-cartographer.mission"


def derive_mission(template: dict, analysed_sha: str) -> dict:
    if not HEX40.match(analysed_sha or ""):
        raise ValueError("ANALYSED_SHA_INVALID")
    m = copy.deepcopy(template)
    m["analyzed_ref"] = {"kind": "GIT_COMMIT", "sha": analysed_sha}
    m["mission_id"] = c.compute_mission_id(m)
    c.validate_mission(m)
    return m


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o640)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def publish(template: dict, analysed_sha: str, out: Path) -> dict:
    m = derive_mission(template, analysed_sha)
    _atomic_write(out / "mission.json", (json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
    _atomic_write(out / "current.env", f"ANALYSED_SHA={analysed_sha}\nMISSION_ID={m['mission_id']}\n".encode("ascii"))
    _atomic_write(out / POINTER, (m["mission_id"] + "\n").encode("ascii"))
    return m


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m agent_bench.observation.follow_main")
    ap.add_argument("--template", required=True)
    ap.add_argument("--analysed-sha", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        m = publish(json.loads(Path(a.template).read_text(encoding="utf-8")), a.analysed_sha, Path(a.out))
    except (OSError, ValueError, KeyError, c.MissionRejected) as exc:
        print(json.dumps({"outcome": "REFUSED", "detail": type(exc).__name__ + ":" + str(exc)[:80]}))
        return 2
    print(json.dumps({"outcome": "PUBLISHED", "analysed_sha": a.analysed_sha, "mission_id": m["mission_id"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
