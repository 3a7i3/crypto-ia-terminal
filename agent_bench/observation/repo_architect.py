"""Analyse d'impact d'un changement — profil ``repo-architect`` (banc isolé v2).

Question bornée (``CHANGE_IMPACT``) : ce diff (base → SHA analysé) touche-t-il une autorité ou une
frontière gelée, quels composants touche-t-il, quels tests manquent ?

Frontière avec ``repository-cartographer`` : l'architecte n'extrait pas de graphe. Il lit le diff
et les fichiers modifiés au SHA analysé, et **cite** la carte du cartographe de la base
(``upstream_map``). Un chemin modifié que la carte ne couvre pas rend l'analyse INCONCLUSIVE,
jamais « sans risque ». Aucun rapport ne vaut autorisation de fusion.
"""
from __future__ import annotations

import ast
import hashlib
import re
import time
from collections import defaultdict

from agent_bench.observation import common as k
from agent_bench.observation import contract as c
from agent_bench.observation.scoped_io import BudgetExceeded, ScopedReader

VERSION = "repo-architect.bench.v1"
MAX_FILES = c.CHANGE_IMPACT_MAX_FILES
MAX_DIFF_BYTES = 2_000_000
LIMITS = [
    "STATIC_ANALYSIS_ONLY_NO_IMPORT_NO_EXECUTION",
    "NO_OWN_REPOSITORY_EXTRACTION_MAP_IS_CITED",
    "FROZEN_OBJECT_LIST_IS_VERSIONED_IN_THIS_MODULE",
    "NO_BOUNDARY_FOUND_IS_NOT_SAFE_TO_MERGE",
    "NO_RUNTIME_OBSERVATION",
    "REPORT_IS_NOT_SELF_CERTIFYING",
]

# Liste versionnée des objets gelés (CLAUDE.md §2–3, #286). Toute modification = nouvelle version.
FROZEN_PATHS = [
    ("risk/", "FROZEN_OBJECT_TOUCHED", "risk"),
    ("signal/", "FROZEN_OBJECT_TOUCHED", "signaux"),
    ("config/", "FROZEN_OBJECT_TOUCHED", "configuration"),
    ("capital_deployment/", "FROZEN_OBJECT_TOUCHED", "capital"),
    ("core/advisor_loop.py", "FROZEN_OBJECT_TOUCHED", "boucle Advisor"),
    ("paper_trading/", "PPL_AUTHORITY_TOUCHED", "autorité PPL"),
    ("observability/financial_", "FIN_AUTHORITY_TOUCHED", "autorité FIN"),
]
FROZEN_IDENTIFIERS = re.compile(
    r"\b(PB_MAX_POSITIONS|FEATURE_AUTO_CALIBRATION|WALLET_PAPER_CAPITAL|[A-Z_]*THRESHOLD[A-Z_]*|"
    r"stop_loss|take_profit|position_size|sizing|epoch_id|manifest_sha256|initial_capital)\b")
RUNTIME_PATH = re.compile(r"(^deploy/|^scripts/systemd/|^infra/|^k8s/|\.service$|\.timer$|\.conf$|^Dockerfile)")
RESEARCH_IMPORT = re.compile(r"^\s*(?:from|import)\s+(research[\w.]*|research_candidate[\w.]*|research_\w+)")
AUTH_TS = re.compile(
    r"(?:(?<![A-Za-z])(?:pnl|equity|balance|capital|rank|score|verdict)|(?:Pnl|PnL|Equity|Balance|Capital|Rank|Score|Verdict))"
    r"(?![a-z])[\w$]*\s*(?:[-+*/](?![-+*/=])|(?::|=(?![=>]))\s*[^;,]*?[\w)\]]\s*[-+*/](?![-+*/=]))")
DIFF_FILE = re.compile(r"^\+\+\+ (?:b/)?(.+)$")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _is_test(path):
    name = path.split("/")[-1]
    return "/tests/" in f"/{path}" or "/test/" in f"/{path}" or name.startswith("test_") or ".test." in name


def parse_diff(diff: bytes) -> dict:
    """{chemin: {"added": [(ligne, texte)], "removed": [(ligne, texte)]}}. Lève ValueError si illisible."""
    if len(diff) > MAX_DIFF_BYTES:
        raise ValueError("DIFF_TOO_LARGE")
    try:
        text = diff.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("DIFF_UNREADABLE") from exc
    files, cur, old_ln, new_ln, prev_minus = {}, None, 0, 0, None
    for raw in text.splitlines():
        if raw.startswith("--- "):
            prev_minus = raw[4:].removeprefix("a/")
            continue
        m = DIFF_FILE.match(raw)
        if m:
            path = m.group(1)
            if path == "/dev/null":  # suppression : on garde l'ancien chemin
                path = prev_minus
            cur = files.setdefault(path, {"added": [], "removed": []})
            continue
        m = HUNK.match(raw)
        if m and cur is not None:
            old_ln, new_ln = int(m.group(1)), int(m.group(3))
            continue
        if cur is None or raw.startswith(("diff --git", "index ", "new file", "deleted file", "similarity", "rename ")):
            continue
        if raw.startswith("+"):
            cur["added"].append((new_ln, raw[1:]))
            new_ln += 1
        elif raw.startswith("-"):
            cur["removed"].append((old_ln, raw[1:]))
            old_ln += 1
        elif raw.startswith(" "):
            old_ln += 1
            new_ln += 1
    if not files:
        raise ValueError("DIFF_EMPTY")
    return files


def _components(rel, data, lines, unknowns):
    """Fonctions et classes (au SHA analysé) qui contiennent une ligne ajoutée."""
    try:
        tree = ast.parse(data.decode("utf-8"), filename=rel)
    except (SyntaxError, UnicodeDecodeError, ValueError):
        unknowns.append({"path": rel, "line": None, "reason": "PARSE_FAILED", "level": "INCONCLUSIVE"})
        return []
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            end = getattr(node, "end_lineno", node.lineno)
            if any(node.lineno <= ln <= end for ln in lines):
                out.add(node.name)
    return sorted(out)


def analyse(changes: dict, sources: dict[str, bytes], changed_paths: list, upstream_map) -> dict:
    """Contenu déterministe. `changes` = parse_diff ; `sources` = fichiers modifiés lisibles au SHA analysé."""
    if len(changed_paths) > MAX_FILES:
        raise ValueError("FILE_BUDGET_EXCEEDED")
    if not set(changes) <= set(changed_paths):
        raise ValueError("DIFF_PATHS_MISMATCH")
    digests = {p: hashlib.sha256(d).hexdigest() for p, d in sources.items()}
    findings, unknowns, touched = [], [], []

    def ev(path, line, symbol=None, etype="CODE"):
        return k.evidence(path, line, symbol, etype, digests.get(path))

    for path in sorted(set(changed_paths) - set(changes)):
        unknowns.append({"path": path, "line": None, "reason": "CHANGE_NOT_TEXTUAL", "level": "INCONCLUSIVE"})
    boundary = defaultdict(list)
    for path in sorted(changes):
        ch = changes[path]
        lines_all = ch["added"] + ch["removed"]
        for prefix, code, label in FROZEN_PATHS:
            if path.startswith(prefix):
                ln = lines_all[0][0] if lines_all else None
                boundary[(code, label)].append(ev(path, ln, None, "MISSION_INPUT"))
        for ln, text in lines_all:
            for m in FROZEN_IDENTIFIERS.finditer(text):
                boundary[("FROZEN_OBJECT_TOUCHED", m.group(1))].append(ev(path, ln, m.group(1), "LITERAL"))
        if RUNTIME_PATH.search(path):
            boundary[("RUNTIME_PATH_TOUCHED", path)].append(ev(path, None, None, "MISSION_INPUT"))
        if not path.startswith(("research", "tests/")) and path.endswith(".py"):
            for ln, text in ch["added"]:
                m = RESEARCH_IMPORT.match(text)
                if m:
                    boundary[("RESEARCH_TO_ACTIVE_PATH", m.group(1))].append(ev(path, ln, m.group(1), "IMPORT"))
        if path.startswith("frontend/") and path.endswith((".ts", ".tsx")) and not _is_test(path):
            for ln, text in ch["added"]:
                if AUTH_TS.search(re.sub(r'"[^"]*"|\'[^\']*\'|`[^`]*`', '""', text.split("//")[0])):
                    boundary[("FRONTEND_RECALCULATES_AUTHORITY", path)].append(ev(path, ln))
        comps = []
        if path.endswith(".py") and path in sources:
            comps = _components(path, sources[path], [ln for ln, _ in ch["added"]], unknowns)
        elif path not in sources:
            comps = ["<supprimé>"] if ch["added"] == [] else []
            if ch["added"]:
                unknowns.append({"path": path, "line": None, "reason": "CHANGED_FILE_UNREADABLE",
                                 "level": "INCONCLUSIVE"})
        touched.append({"path": path, "added": len(ch["added"]), "removed": len(ch["removed"]),
                        "symbols": comps, "test": _is_test(path)})

    claims = {
        "FROZEN_OBJECT_TOUCHED": "Le diff touche un objet gelé ({}) : stratégie, seuils, risk, sizing, capital ou config "
                                 "restent immuables pendant le burn-in (#286).",
        "PPL_AUTHORITY_TOUCHED": "Le diff touche l'{} : vérité lifecycle, mutation interdite sans gate.",
        "FIN_AUTHORITY_TOUCHED": "Le diff touche l'{} : vérité financière, mutation interdite sans gate.",
        "RUNTIME_PATH_TOUCHED": "Le diff modifie un fichier de déploiement ou d'unité ({}) : une fusion source "
                                "n'autorise aucune publication runtime.",
        "RESEARCH_TO_ACTIVE_PATH": "Un module hors Research importe {} : flux Research → chemin actif interdit.",
        "FRONTEND_RECALCULATES_AUTHORITY": "{} ajoute un calcul sur une valeur d'autorité côté frontend.",
    }
    for (code, label), evs in sorted(boundary.items()):
        uniq = {(e["path"], e["line"], e["symbol"]): e for e in evs}
        level = "SUPPORTED" if all(e["evidence_type"] == "MISSION_INPUT" for e in uniq.values()) else "PROVEN"
        findings.append(k.finding("BOUNDARY", code, claims[code].format(label), level, "HIGH" if level == "PROVEN" else "MEDIUM",
                                  list(uniq.values())))

    prod = [t["path"] for t in touched if not t["test"] and t["path"].endswith((".py", ".ts", ".tsx")) and t["added"]]
    if prod and not any(t["test"] for t in touched):
        findings.append(k.finding("TESTS", "MISSING_TESTS",
                                  f"{len(prod)} fichier(s) de code modifié(s) sans aucun fichier de test modifié.",
                                  "SUPPORTED", "MEDIUM", [ev(p, None, None, "MISSION_INPUT") for p in prod]))

    if upstream_map is None:
        unknowns.append({"path": None, "line": None, "reason": "REPOSITORY_MAP_NOT_PROVIDED", "level": "INCONCLUSIVE"})
    else:
        mapped = upstream_map["mapped_paths"]
        for p in sorted(changed_paths):
            if not any(p == m or (m.endswith("/") and p.startswith(m)) for m in mapped):
                unknowns.append({"path": p, "line": None, "reason": "DIFF_OUTSIDE_MAPPED_ZONE", "level": "INCONCLUSIVE"})
    unknowns = sorted({(u["path"] or "", u["reason"]): u for u in unknowns}.values(),
                      key=lambda u: (u["path"] or "", u["reason"]))
    return {
        "contract": c.REPORT_CONTRACT, "architect_version": VERSION,
        "status": "COMPLETE" if not unknowns else "PARTIAL",
        "touched_components": touched,
        "boundaries_crossed": sorted({f["code"] for f in findings if f["category"] == "BOUNDARY"}),
        "findings": k.sort_findings(findings),
        "unknowns": unknowns,
        "runtime_measurements_required": [],
        "limits": LIMITS,
    }


# --------------------------------------------------------------------------- mission

def _blocked(mission, code, detail, profile=None):
    q = (mission or {}).get("question") if isinstance(mission, dict) else None
    return k.blocked_content(mission, version_key="architect_version", version=VERSION, code=code, detail=detail,
                             profile=profile, limits=LIMITS,
                             extra={"change_id": q.get("change_id") if isinstance(q, dict) else None,
                                    "touched_components": [], "boundaries_crossed": [], "inputs_cited": None})


def audit_change(mission, workspace_root, profile_root, diff: bytes, *, clock=time.time_ns) -> dict:
    """Exécute la mission sur le diff fourni et retourne le rapport scellé. N'écrit rien."""
    return k.seal(lambda t0: _content(mission, workspace_root, profile_root, diff, t0), mission, clock=clock,
                  failed_content=lambda code, d: _blocked(mission, code, d))


def _content(mission, workspace_root, profile_root, diff, t0):
    try:
        c.validate_mission(mission)
    except c.MissionRejected as exc:
        return _blocked(mission, exc.code, exc.detail)
    if mission["agent_id"] != "repo-architect" or mission["question"]["kind"] != "CHANGE_IMPACT":
        return _blocked(mission, "AGENT_NOT_QUALIFIED_FOR_BENCH", mission["agent_id"])
    try:
        pread = k.read_profile(mission, profile_root)
    except k.Blocked as exc:
        return _blocked(mission, exc.code, exc.detail, exc.profile)
    q, b = mission["question"], mission["budget"]
    if not isinstance(diff, (bytes, bytearray)) or hashlib.sha256(diff).hexdigest() != q["diff_sha256"]:
        return _blocked(mission, "DIFF_FINGERPRINT_MISMATCH", q["change_id"], pread)
    reader = ScopedReader(workspace_root, mission["scope"]["read_paths"], max_files=b["max_files"],
                          max_bytes=b["max_bytes"])
    try:
        changes = parse_diff(bytes(diff))
        sources = {}
        for rel in q["changed_paths"]:
            if time.monotonic() - t0 > b["max_wall_ms"] / 1000:
                raise BudgetExceeded("max_wall_ms")
            data = reader.read(rel)
            if data is not None:
                sources[rel] = data
        content = analyse(changes, sources, q["changed_paths"], q["upstream_map"])
    except BudgetExceeded as exc:
        out = _blocked(mission, "BUDGET_EXCEEDED", str(exc), pread)
        out["status"] = "FAILED"
        return out
    except ValueError as exc:
        return _blocked(mission, str(exc).split(":")[0], q["change_id"], pread)
    content.update({
        "agent_id": mission["agent_id"], "profile": pread, "mission_id": mission["mission_id"],
        "analyzed_ref": mission["analyzed_ref"], "change_id": q["change_id"], "base_sha": q["base_sha"],
        "diff_sha256": q["diff_sha256"], "inputs_cited": q["upstream_map"],
        "sources": [pread] + reader.inventory(), "refused_paths": reader.refusals(), "errors": [],
    })
    return content


# --------------------------------------------------------------------------- matrice attendu / obtenu

def _patch(path, added, removed=(), start=1):
    body = [f"--- a/{path}", f"+++ b/{path}", f"@@ -{start},{len(removed)} +{start},{len(added)} @@"]
    body += [f"-{x}" for x in removed] + [f"+{x}" for x in added]
    return "\n".join(body) + "\n"


MAP_ALL = {"agent_id": "repository-cartographer", "content_sha256": "0" * 64, "analysed_sha": "1" * 40,
           "mapped_paths": ["api/", "frontend/", "paper_trading/", "research/", "risk/", "tests/", "deploy/"]}
CASES = [
    {"id": "ARCH_1_inoffensif", "title": "Diff inoffensif avec test, zone cartographiée",
     "diff": _patch("api/util.py", ["def label(x):", "    return str(x)"]) + _patch("tests/test_util.py", ["def test_label():", "    assert True"]),
     "sources": {"api/util.py": b"def label(x):\n    return str(x)\n", "tests/test_util.py": b"def test_label():\n    assert True\n"},
     "map": MAP_ALL, "expected": {"boundaries": [], "findings": [], "unknowns": [], "status": "COMPLETE"}},
    {"id": "ARCH_2_seuil_gele", "title": "Diff qui modifie un seuil gelé",
     "diff": _patch("risk/limits.py", ["MAX_DRAWDOWN_THRESHOLD = 0.2"], ["MAX_DRAWDOWN_THRESHOLD = 0.1"]),
     "sources": {"risk/limits.py": b"MAX_DRAWDOWN_THRESHOLD = 0.2\n"},
     "map": MAP_ALL, "expected": {"boundaries": ["FROZEN_OBJECT_TOUCHED"], "findings": ["FROZEN_OBJECT_TOUCHED", "MISSING_TESTS"],
                                  "unknowns": [], "status": "COMPLETE"}},
    {"id": "ARCH_3_pnl_frontend", "title": "Diff qui ajoute un recalcul de PnL au frontend",
     "diff": _patch("frontend/src/views/W.tsx", ["const pnl = d.exit_usd - d.entry_usd;"]),
     "sources": {"frontend/src/views/W.tsx": b"const pnl = d.exit_usd - d.entry_usd;\n"},
     "map": MAP_ALL, "expected": {"boundaries": ["FRONTEND_RECALCULATES_AUTHORITY"],
                                  "findings": ["FRONTEND_RECALCULATES_AUTHORITY", "MISSING_TESTS"], "unknowns": [], "status": "COMPLETE"}},
    {"id": "ARCH_4_hors_zone", "title": "Diff hors zone cartographiée : INCONCLUSIVE, jamais « sans risque »",
     "diff": _patch("other/x.py", ["y = 1"]) + _patch("tests/test_x.py", ["z = 1"]),
     "sources": {"other/x.py": b"y = 1\n", "tests/test_x.py": b"z = 1\n"},
     "map": MAP_ALL, "expected": {"boundaries": [], "findings": [], "unknowns": ["DIFF_OUTSIDE_MAPPED_ZONE"], "status": "PARTIAL"}},
    {"id": "ARCH_5_sans_carte", "title": "Pas de carte du cartographe fournie",
     "diff": _patch("api/util.py", ["x = 1"]) + _patch("tests/test_util.py", ["y = 1"]),
     "sources": {"api/util.py": b"x = 1\n", "tests/test_util.py": b"y = 1\n"},
     "map": None, "expected": {"boundaries": [], "findings": [], "unknowns": ["REPOSITORY_MAP_NOT_PROVIDED"], "status": "PARTIAL"}},
    {"id": "ARCH_6_ppl_et_research", "title": "Autorité PPL touchée et import Research",
     "diff": _patch("paper_trading/engine.py", ["from research.alpha import boost"]) + _patch("tests/test_e.py", ["a = 1"]),
     "sources": {"paper_trading/engine.py": b"from research.alpha import boost\n", "tests/test_e.py": b"a = 1\n"},
     "map": MAP_ALL, "expected": {"boundaries": ["PPL_AUTHORITY_TOUCHED", "RESEARCH_TO_ACTIVE_PATH"],
                                  "findings": ["PPL_AUTHORITY_TOUCHED", "RESEARCH_TO_ACTIVE_PATH"], "unknowns": [], "status": "COMPLETE"}},
    {"id": "ARCH_7_runtime", "title": "Unité systemd modifiée",
     "diff": _patch("deploy/cat-x.service", ["ExecStart=/bin/true"]),
     "sources": {"deploy/cat-x.service": b"ExecStart=/bin/true\n"},
     "map": MAP_ALL, "expected": {"boundaries": ["RUNTIME_PATH_TOUCHED"], "findings": ["RUNTIME_PATH_TOUCHED"],
                                  "unknowns": [], "status": "COMPLETE"}},
]


def summary(content):
    return {"boundaries": content["boundaries_crossed"], "findings": sorted({f["code"] for f in content["findings"]}),
            "unknowns": sorted({u["reason"] for u in content["unknowns"]}), "status": content["status"]}


def run_case(case):
    changes = parse_diff(case["diff"].encode())
    return summary(analyse(changes, case["sources"], sorted(changes), case["map"]))


def matrix() -> list[dict]:
    rows = []
    for case in CASES:
        got, want = run_case(case), case["expected"]
        rows.append({"id": case["id"], "title": case["title"], "expected": want, "obtained": got,
                     "passed": got == {kk: (sorted(v) if isinstance(v, list) else v) for kk, v in want.items()}})
    return rows
