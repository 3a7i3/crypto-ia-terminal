"""Préparation d'une mission ``CHANGE_IMPACT`` (repo-architect) depuis un dépôt git.

Calcule, avec la même commande git que l'exécuteur, les chemins modifiés base → tête et
l'empreinte du diff, puis écrit la mission sur la sortie standard. Lecture seule du dépôt.

    python3 -m agent_bench.observation.change_mission --repo <checkout> --base <sha> --head <sha> \\
        --change-id <slug> --text "…" [--upstream-map carte.json]

`--upstream-map` : {"agent_id": "repository-cartographer", "content_sha256", "analysed_sha" (= base),
"mapped_paths": [...]}, tiré d'un rapport du cartographe déjà publié sur le VPS.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_bench.observation import agents as ag
from agent_bench.observation import contract as c
from agent_bench.observation import executor as ex
from agent_bench.observation import invocation as inv


def build(repo: Path, *, base, head, change_id, text, upstream_map=None, profile_blob=None,
          max_bytes=4_000_000, max_wall_ms=60_000) -> dict:
    spec = ag.spec("repo-architect")
    paths = ex.changed_paths(repo, base, head)
    if not paths:
        raise ValueError("DIFF_EMPTY")
    if len(paths) > spec.max_files:
        raise ValueError(f"FILE_BUDGET_EXCEEDED: {len(paths)} > {spec.max_files}")
    diff = ex.git_diff(repo, base, head, paths)
    if profile_blob is None:
        profile_blob = c.git_blob_sha1((repo / spec.profile_path).read_bytes())
    m = {
        "contract": c.MISSION_CONTRACT_V2, "agent_id": "repo-architect",
        "profile": {"source_path": spec.profile_path, "blob_sha1": profile_blob},
        "mission_id": None, "analyzed_ref": {"kind": "GIT_COMMIT", "sha": head},
        "scope": {"read_paths": paths},
        "question": {"kind": "CHANGE_IMPACT", "change_id": change_id, "text": text, "base_sha": base,
                     "changed_paths": paths, "diff_sha256": inv.hashlib_sha256(diff),
                     "upstream_map": upstream_map},
        "budget": {"max_files": len(paths), "max_bytes": max_bytes, "max_wall_ms": max_wall_ms},
        "capture": None,
    }
    m["mission_id"] = c.compute_mission_id(m)
    c.validate_mission(m)
    return m


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m agent_bench.observation.change_mission")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--change-id", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--upstream-map", default=None)
    a = ap.parse_args(argv)
    try:
        um = json.loads(Path(a.upstream_map).read_text(encoding="utf-8")) if a.upstream_map else None
        m = build(Path(a.repo), base=a.base, head=a.head, change_id=a.change_id, text=a.text, upstream_map=um)
    except (OSError, ValueError, ex.Refused, c.MissionRejected) as exc:
        print(json.dumps({"outcome": "REFUSED", "detail": f"{type(exc).__name__}:{str(exc)[:120]}"}))
        return 2
    sys.stdout.write(json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
