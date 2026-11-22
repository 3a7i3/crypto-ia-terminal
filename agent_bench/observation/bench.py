"""Banc d'essai isolé du pilote ``data-provenance-auditor``.

Chaque cas est copié dans un répertoire temporaire (le dépôt n'est jamais lu par
l'auditeur pendant un cas), son état de fichiers (mtime) est fixé par
``setup.json``, puis la mission est exécutée deux fois. Le banc compare le
rapport au résultat attendu ``expected.json`` défini à l'avance.

Usage :
    python3 -m agent_bench.observation.bench freeze   # recalcule tree/mission_id des fixtures
    python3 -m agent_bench.observation.bench matrix --out DIR
    python3 -m agent_bench.observation.bench pilot --repo-sha SHA --out FILE
Aucun réseau, aucun VPS, aucune API de marché. Les sorties vont dans --out uniquement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from agent_bench.observation import contract as c
from agent_bench.observation.provenance_auditor import audit

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "agent_bench" / "fixtures" / "observation"
PILOT_MISSION = REPO / "docs" / "agents" / "observation" / "examples" / "pilot_mission.json"


def tree_sha256(root):
    root = Path(root)
    rows = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts:
            rows.append([p.relative_to(root).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest()])
    return c.sha256_json(rows)


def finalize(mission):
    mission = dict(mission)
    mission["mission_id"] = c.compute_mission_id(mission)
    return mission


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def cases():
    return sorted(p for p in FIXTURES.iterdir() if (p / "mission.json").is_file())


def freeze(case):
    """Recalcule l'empreinte de l'arbre, de la capture et l'identité de mission."""
    m = json.loads((case / "mission.json").read_text(encoding="utf-8"))
    ws = case / "workspace"
    m["analyzed_ref"] = {"kind": "FIXTURE_TREE", "sha": tree_sha256(ws)}
    cap = ws / m["capture"]["path"]
    if cap.is_file():
        m["capture"]["sha256"] = hashlib.sha256(cap.read_bytes()).hexdigest()
    if not (case / "setup.json").is_file() or not json.loads((case / "setup.json").read_text()).get("keep_mission_id"):
        m = finalize(m)
    (case / "mission.json").write_text(_dump(m), encoding="utf-8")
    return m


def prepare_case(case, tmp):
    """Copie le cas dans ``tmp``, vérifie son empreinte d'arbre, applique setup.json."""
    setup = json.loads((case / "setup.json").read_text(encoding="utf-8")) if (case / "setup.json").is_file() else {}
    mission = json.loads((case / "mission.json").read_text(encoding="utf-8"))
    ws = Path(tmp) / "workspace"
    shutil.copytree(case / "workspace", ws, symlinks=True)
    if mission["analyzed_ref"] != {"kind": "FIXTURE_TREE", "sha": tree_sha256(ws)}:
        raise RuntimeError(f"REFUSED: {case.name} workspace differs from its declared FIXTURE_TREE")
    # Fichiers non versionnés (ex. .env factice) créés seulement dans la copie temporaire.
    for rel, text in sorted(setup.get("create_files", {}).items()):
        (ws / rel).parent.mkdir(parents=True, exist_ok=True)
        (ws / rel).write_text(text, encoding="utf-8")
    for rel, iso in sorted(setup.get("mtime_utc", {}).items()):
        ts = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        os.utime(ws / rel, (ts, ts))
    return mission, ws


def run_case(case, *, clock=None):
    with tempfile.TemporaryDirectory(prefix="obs-bench-") as tmp:
        mission, ws = prepare_case(case, tmp)
        kwargs = {"clock": clock} if clock else {}
        return audit(mission, ws, REPO, **kwargs)


def compare(report, expected):
    """Compare un rapport au résultat attendu. Retourne un dictionnaire de verdict."""
    ct = report["content"]
    mism = []
    if ct["status"] != expected["status"]:
        mism.append(f"status {ct['status']} != {expected['status']}")
    hops = {h["hop"]: h["level"] for h in ct["chain"]}
    for hop, lvl in expected.get("hops", {}).items():
        if hops.get(hop) != lvl:
            mism.append(f"hop {hop} {hops.get(hop)} != {lvl}")
    codes = [f["code"] for f in ct["findings"]]
    for code in expected.get("required_findings", []):
        if code not in codes:
            mism.append(f"missing finding {code}")
    allowed = set(expected.get("required_findings", [])) | set(expected.get("allowed_findings", []))
    false = sorted({x for x in codes if x not in allowed})
    errs = [e["code"] for e in ct["errors"]]
    for code in expected.get("required_errors", []):
        if code not in errs:
            mism.append(f"missing error {code}")
    if "freshness_verdict" in expected:
        got = (ct["freshness"] or {}).get("verdict")
        if got != expected["freshness_verdict"]:
            mism.append(f"freshness {got} != {expected['freshness_verdict']}")
    if "distinct_observations" in expected:
        got = (ct["observations"] or {}).get("distinct_observations")
        if got != expected["distinct_observations"]:
            mism.append(f"distinct_observations {got} != {expected['distinct_observations']}")
    refused = {r["path"]: r["code"] for r in ct["refused_paths"]}
    for path, code in expected.get("refused_paths", {}).items():
        if refused.get(path) != code:
            mism.append(f"refused {path} {refused.get(path)} != {code}")
    consulted = {s["path"] for s in ct["sources_consulted"]}
    for path in expected.get("never_read", []):
        if path in consulted:
            mism.append(f"read forbidden path {path}")
    unjustified = [f["code"] for f in ct["findings"] if not f["evidence"]]
    inconclusive = sum(h["level"] in ("INCONCLUSIVE", "NOT_FOUND") for h in ct["chain"])
    inconclusive += sum(f["level"] in ("INCONCLUSIVE", "NOT_FOUND") for f in ct["findings"])
    return {"passed": not mism and not false and not unjustified, "mismatches": mism,
            "false_findings": false, "unjustified_findings": unjustified,
            "justified_findings": len(ct["findings"]) - len(unjustified), "inconclusive": inconclusive}


def matrix():
    rows = []
    for case in cases():
        expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
        r1, r2 = run_case(case), run_case(case)
        verdict = compare(r1, expected)
        verdict["replay_identical"] = r1["content_sha256"] == r2["content_sha256"]
        verdict["passed"] = verdict["passed"] and verdict["replay_identical"]
        rows.append({"case": case.name, "title": expected["title"], "expected": expected,
                     "obtained": {"status": r1["content"]["status"],
                                  "hops": {h["hop"]: h["level"] for h in r1["content"]["chain"]},
                                  "findings": sorted({f["code"] for f in r1["content"]["findings"]}),
                                  "errors": [e["code"] for e in r1["content"]["errors"]],
                                  "freshness_verdict": (r1["content"]["freshness"] or {}).get("verdict")},
                     "verdict": verdict, "content_sha256": r1["content_sha256"], "run": r1["run"]})
    return rows


def verify_git_scope(repo_sha, paths):
    """Contrôle du harnais (pas de l'auditeur) : le périmètre est identique à repo_sha."""
    import subprocess
    subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", f"{repo_sha}^{{commit}}"], check=True)
    diff = subprocess.run(["git", "-C", str(REPO), "diff", "--quiet", repo_sha, "--", *paths], check=False)
    if diff.returncode != 0:
        raise SystemExit(f"REFUSED: scope differs from {repo_sha}")


def pilot(repo_sha):
    m = json.loads(PILOT_MISSION.read_text(encoding="utf-8"))
    if m["analyzed_ref"] != {"kind": "GIT_COMMIT", "sha": repo_sha}:
        raise SystemExit(f"REFUSED: pilot mission names {m['analyzed_ref']}, harness checked {repo_sha}")
    verify_git_scope(repo_sha, m["scope"]["read_paths"])
    return audit(m, REPO, REPO)


def matrix_markdown(rows):
    out = ["| Cas | Fixture | Attendu | Obtenu | Constats (codes) | Rejeu identique | Résultat |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        e, o, v = r["expected"], r["obtained"], r["verdict"]
        out.append(f"| {r['case']} | {r['title']} | {e['status']} ; {e.get('expected_summary', '')} | {o['status']} ; "
                   f"fraîcheur {o['freshness_verdict']} | {', '.join(o['findings']) or '—'} | "
                   f"{'oui' if v['replay_identical'] else 'NON'} (`{r['content_sha256'][:12]}`) | {'PASS' if v['passed'] else 'ÉCHEC'} |")
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="observation-bench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze")
    mx = sub.add_parser("matrix")
    mx.add_argument("--out", required=True)
    pl = sub.add_parser("pilot")
    pl.add_argument("--repo-sha", required=True)
    pl.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "freeze":
        for case in cases():
            print(case.name, freeze(case)["mission_id"])
        return 0
    if a.cmd == "matrix":
        rows = matrix()
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "matrix.json").write_text(_dump(rows), encoding="utf-8")
        (out / "matrix.md").write_text(matrix_markdown(rows), encoding="utf-8")
        print(json.dumps({"cases": len(rows), "passed": sum(r["verdict"]["passed"] for r in rows),
                          "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}))
        return 0 if all(r["verdict"]["passed"] for r in rows) else 1
    report = pilot(a.repo_sha)
    Path(a.out).write_text(_dump(report), encoding="utf-8")
    print(report["content"]["status"], report["content_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
