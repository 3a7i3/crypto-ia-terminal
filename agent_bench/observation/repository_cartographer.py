"""Cartographie statique d'une zone — profil ``repository-cartographer`` (banc isolé).

Le cœur ``map_repository`` vient du prototype reçu (4 tests d'origine conservés) :
il lit le code en mémoire avec ``ast`` sans jamais l'importer ni l'exécuter.
L'intégration à la PR #598 ajoute :

- le validateur de chemins et de secrets du contrat (``contract.path_violation``) ;
- le lecteur borné qui inventorie chaque fichier lu (``scoped_io.ScopedReader``) ;
- l'index de sources de ``source_index`` (écritures, flags, routes) pour les
  constats de producteurs et de flags ;
- une classification des appels : un import non utilisé, un import réservé aux
  tests ou un appel à une cible réservée aux tests n'est jamais une preuve
  d'activité en production ; un appel de secours est CONDITIONAL ; une cible
  dynamique est INCONCLUSIVE.

Ce module ne crée aucun runner. Un rapport scellé n'est pas une validation.
"""
from __future__ import annotations

import ast
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path, PurePosixPath

from agent_bench.observation import contract as c
from agent_bench.observation.scoped_io import BudgetExceeded, ScopedReader
from agent_bench.observation.source_index import index_python

CARTOGRAPHER_VERSION = "repository-cartographer.bench.v1"
MAX_FILES = c.REPOSITORY_MAP_MAX_FILES
LIMITS = [
    "STATIC_ANALYSIS_ONLY_NO_IMPORT_NO_EXECUTION",
    "DEFINED_IS_NOT_CALLED_IS_NOT_ACTIVE",
    "IMPORT_IS_NOT_CALL",
    "CONDITIONAL_CALL_IS_NOT_PROVEN_REACHABLE",
    "DYNAMIC_CALL_TARGET_IS_INCONCLUSIVE",
    "ONE_HOP_NAME_RESOLUTION_ONLY",
    "FLAG_ATTRIBUTION_LIMITED_TO_THE_ZONE",
    "NO_RUNTIME_OBSERVATION",
    "REPORT_IS_NOT_SELF_CERTIFYING",
]


# --------------------------------------------------------------------------- noyau (prototype)

def _root_name(func):
    """Nom de tête d'une cible d'appel, lu dans l'arbre (``Path('x').write_text`` -> ``Path``)."""
    cur = func
    while True:
        if isinstance(cur, ast.Attribute):
            cur = cur.value
        elif isinstance(cur, ast.Call):
            cur = cur.func
        elif isinstance(cur, ast.Name):
            return cur.id
        else:
            return None


def _condition(node, parents):
    """Classe un appel : EXCEPT_HANDLER (secours), BRANCH (sous un if/ternaire/court-circuit) ou None."""
    ancestors = []
    cur = node
    while cur in parents:
        cur = parents[cur]
        ancestors.append(cur)
    if any(isinstance(a, ast.ExceptHandler) for a in ancestors):
        return "EXCEPT_HANDLER"
    if any(isinstance(a, (ast.If, ast.IfExp, ast.BoolOp)) for a in ancestors):
        return "BRANCH"
    return None


def map_repository(sources: dict[str, bytes], allowed: frozenset[str], *, max_files: int = MAX_FILES) -> dict:
    """Map explicit syntax in memory without executing fixture code."""
    if len(sources) > max_files:
        raise ValueError("FILE_BUDGET_EXCEEDED")

    for path in sources:
        code = c.path_violation(path)
        if code or path not in allowed or PurePosixPath(path).suffix != ".py":
            raise ValueError(f"SOURCE_OUT_OF_SCOPE: {code or 'NOT_ALLOWED_OR_NOT_PYTHON'}")

    facts, unknowns = [], []

    for path, data in sorted(sources.items()):
        digest = hashlib.sha256(data).hexdigest()
        try:
            tree = ast.parse(data, filename=path)
        except (SyntaxError, ValueError, UnicodeError):
            unknowns.append({"path": path, "reason": "PARSE_FAILED"})
            continue

        parents = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent

        for node in ast.walk(tree):
            targets = []

            if isinstance(node, ast.Import):
                targets = [("IMPORTS", alias.name, alias.asname or alias.name.split(".")[0])
                           for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = "." * node.level + (node.module or "")
                targets = [("IMPORTS", f"{module}:{alias.name}", alias.asname or alias.name)
                           for alias in node.names]
            elif isinstance(node, ast.Call):
                if isinstance(node.func, (ast.Name, ast.Attribute)):
                    targets = [("CALL_EXPRESSION", ast.unparse(node.func), _condition(node, parents))]
                else:
                    unknowns.append(
                        {
                            "path": path,
                            "line": node.lineno,
                            "reason": "DYNAMIC_CALL_TARGET",
                        }
                    )
            elif isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                targets = [("DEFINES", node.name, None)]

            for relation, target, extra in targets:
                fact = {
                    "path": path,
                    "line": node.lineno,
                    "column": node.col_offset,
                    "sha256": digest,
                    "relation": relation,
                    "target": target,
                }
                if relation == "IMPORTS":
                    fact["binding"] = extra
                elif relation == "CALL_EXPRESSION":
                    fact["condition"] = extra
                    fact["root"] = _root_name(node.func)
                facts.append(fact)

    content = {"facts": facts, "unknowns": unknowns}
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    return {**content, "content_sha256": hashlib.sha256(encoded).hexdigest()}


# --------------------------------------------------------------------------- classification

def is_test_path(path: str) -> bool:
    p = PurePosixPath(path)
    return "tests" in p.parts[:-1] or "test" in p.parts[:-1] or p.name.startswith("test_") or p.name.endswith("_test.py")


def _is_test_module(module: str) -> bool:
    head = module.split(".")[0]
    return head in ("tests", "test") or head.startswith("test_")


def _ref(path, line, symbol, digest, kind):
    return {"path": path, "line": line, "symbol": symbol, "sha256": digest, "evidence_type": kind}


def classify(result: dict, sources: dict[str, bytes]) -> dict:
    """Classe imports et appels sans en créer. Un import n'est jamais un appel."""
    scope = {p: ("TEST" if is_test_path(p) else "PRODUCTION") for p in sources}
    facts = result["facts"]
    calls = [f for f in facts if f["relation"] == "CALL_EXPRESSION"]
    imports = [f for f in facts if f["relation"] == "IMPORTS"]

    call_roots = defaultdict(set)
    for f in calls:
        call_roots[f["path"]].add(f["root"])

    test_scope_bindings = defaultdict(set)
    import_rows = []
    for f in imports:
        module = f["target"].split(":")[0]
        used = f["binding"] in call_roots[f["path"]]
        if _is_test_module(module) and scope[f["path"]] == "PRODUCTION":
            status = "IMPORT_TEST_SCOPE"
            test_scope_bindings[f["path"]].add(f["binding"])
        elif not used:
            status = "IMPORT_ONLY"
        else:
            status = "IMPORT_USED"
        import_rows.append({"path": f["path"], "line": f["line"], "target": f["target"],
                            "binding": f["binding"], "status": status, "sha256": f["sha256"]})

    call_rows = []
    for f in calls:
        root = f["root"]
        if scope[f["path"]] == "TEST":
            status = "TEST_CALL"
        elif root in test_scope_bindings[f["path"]]:
            status = "TEST_SCOPE_CALL"
        elif f["condition"]:
            status = "CONDITIONAL_PRODUCTION_CALL"
        else:
            status = "PRODUCTION_CALL"
        call_rows.append({"path": f["path"], "line": f["line"], "target": f["target"],
                          "condition": f["condition"], "scope": scope[f["path"]],
                          "status": status, "sha256": f["sha256"]})

    activity = {
        "production_calls": sum(r["status"] == "PRODUCTION_CALL" for r in call_rows),
        "conditional_production_calls": sum(r["status"] == "CONDITIONAL_PRODUCTION_CALL" for r in call_rows),
        "test_calls": sum(r["status"] == "TEST_CALL" for r in call_rows),
        "test_scope_calls": sum(r["status"] == "TEST_SCOPE_CALL" for r in call_rows),
        "imports_only": sum(r["status"] == "IMPORT_ONLY" for r in import_rows),
        "imports_test_scope": sum(r["status"] == "IMPORT_TEST_SCOPE" for r in import_rows),
    }
    return {"imports": sorted(import_rows, key=_k), "calls": sorted(call_rows, key=_k), "activity": activity}


def _k(row):
    return (row["path"], row["line"], row.get("target", ""))


def constats(sources: dict[str, bytes]) -> tuple[list, dict]:
    """Producteurs candidats et flags, depuis l'index de sources. Chaque constat cite ses sources."""
    idx = {p: index_python(p, d) for p, d in sorted(sources.items())}
    digests = {p: hashlib.sha256(d).hexdigest() for p, d in sources.items()}
    findings = []

    writers = defaultdict(list)
    for p, pm in idx.items():
        for f in pm.write_templates:
            writers[f.detail].append(_ref(p, f.line, f.symbol, digests[p], "CALL_SITE"))
    for tmpl, refs in sorted(writers.items()):
        if len({(r["path"], r["symbol"]) for r in refs}) >= 2:
            findings.append({
                "code": "MULTIPLE_PRODUCER_CANDIDATES", "level": "PROVEN", "confidence": "HIGH",
                "claim": f"{len(refs)} écritures candidates vers le même fichier « {tmpl} » : producteur non unique.",
                "evidence": sorted(refs, key=lambda r: (r["path"], r["line"])),
            })

    readers = defaultdict(list)
    for p, pm in idx.items():
        for f in pm.env:
            readers[f.detail].append(_ref(p, f.line, f.symbol, digests[p], "CALL_SITE"))
    for flag, refs in sorted(readers.items()):
        places = {(r["path"], r["symbol"]) for r in refs}
        refs = sorted(refs, key=lambda r: (r["path"], r["line"]))
        if len(places) == 1:
            r = refs[0]
            findings.append({
                "code": "FLAG_SINGLE_PATH", "level": "SUPPORTED", "confidence": "MEDIUM",
                "claim": f"Le flag {flag} n'est lu que dans {r['path']}:{r['symbol']} (dans la zone seulement).",
                "evidence": refs, "attributed_to": {"path": r["path"], "symbol": r["symbol"]},
            })
        else:
            findings.append({
                "code": "FLAG_MULTI_PATH", "level": "PROVEN", "confidence": "HIGH",
                "claim": f"Le flag {flag} est lu sur {len(places)} chemins : pas d'attribution unique.",
                "evidence": refs,
            })
    return sorted(findings, key=lambda f: (f["code"], f["evidence"][0]["path"], f["evidence"][0]["line"])), {
        "flags": sorted(readers), "write_templates": sorted(writers)}


def analyse(sources: dict[str, bytes], allowed=None, *, max_files: int = MAX_FILES) -> dict:
    """Contenu déterministe de la cartographie d'un ensemble de sources (aucune métadonnée d'exécution)."""
    allowed = frozenset(sources) if allowed is None else allowed
    result = map_repository(sources, allowed, max_files=max_files)
    cls = classify(result, sources)
    findings, meta = constats(sources)
    unknowns = []
    for u in result["unknowns"]:
        level = "INCONCLUSIVE"
        unknowns.append({**u, "level": level})
    status = "COMPLETE" if not unknowns else "PARTIAL"
    return {
        "contract": c.REPORT_CONTRACT,
        "cartographer_version": CARTOGRAPHER_VERSION,
        "status": status,
        "sources": [{"path": p, "bytes": len(d), "sha256": hashlib.sha256(d).hexdigest()}
                    for p, d in sorted(sources.items())],
        "imports": cls["imports"],
        "calls": cls["calls"],
        "activity": cls["activity"],
        "findings": findings,
        "flags": meta["flags"],
        "write_templates": meta["write_templates"],
        "unknowns": sorted(unknowns, key=lambda u: (u["path"], u.get("line") or 0, u["reason"])),
        "limits": LIMITS,
    }


# --------------------------------------------------------------------------- mission de zone

def _blocked(mission, code, detail, profile=None):
    m = mission if isinstance(mission, dict) else {}
    return {
        "contract": c.REPORT_CONTRACT, "cartographer_version": CARTOGRAPHER_VERSION,
        "agent_id": m.get("agent_id") if isinstance(m.get("agent_id"), str) else None,
        "profile": profile, "mission_id": m.get("mission_id") if isinstance(m.get("mission_id"), str) else None,
        "analyzed_ref": m.get("analyzed_ref") if isinstance(m.get("analyzed_ref"), dict) else None,
        "zone_id": (m.get("question") or {}).get("zone_id") if isinstance(m.get("question"), dict) else None,
        "status": "BLOCKED", "sources": [], "imports": [], "calls": [], "activity": None, "findings": [],
        "flags": [], "write_templates": [], "unknowns": [], "refused_paths": [], "skipped_non_python": [],
        "errors": [{"code": code, "detail": detail}], "limits": LIMITS,
    }


def audit_zone(mission, workspace_root, profile_root, *, clock=time.time_ns) -> dict:
    """Exécute la cartographie d'une zone et retourne le rapport scellé. N'écrit rien."""
    started = clock()
    t0 = time.monotonic()
    try:
        content = _zone_content(mission, workspace_root, profile_root, t0)
    except Exception as exc:  # noqa: BLE001 — un échec interne devient FAILED, jamais un succès
        content = _blocked(mission, "INTERNAL_ERROR", type(exc).__name__)
        content["status"] = "FAILED"
    ended = clock()
    run = {"started_utc_ns": started, "ended_utc_ns": ended,
           "duration_ms": round((time.monotonic() - t0) * 1000, 3),
           "sources_read": len(content["sources"])}
    return c.seal_report(content, run)


def _zone_content(mission, workspace_root, profile_root, t0):
    try:
        c.validate_mission(mission)
    except c.MissionRejected as exc:
        return _blocked(mission, exc.code, exc.detail)
    if mission["agent_id"] != "repository-cartographer" or mission["question"]["kind"] != "REPOSITORY_MAP":
        return _blocked(mission, "AGENT_NOT_QUALIFIED_FOR_BENCH", mission["agent_id"])
    prof = mission["profile"]
    try:
        pdata = (Path(profile_root) / prof["source_path"]).read_bytes()
    except OSError:
        return _blocked(mission, "PROFILE_UNREADABLE", prof["source_path"])
    pread = {"path": "profile:" + prof["source_path"], "bytes": len(pdata),
             "sha256": hashlib.sha256(pdata).hexdigest()}
    if c.git_blob_sha1(pdata) != prof["blob_sha1"]:
        return _blocked(mission, "PROFILE_VERSION_MISMATCH", prof["source_path"], pread)

    b = mission["budget"]
    reader = ScopedReader(workspace_root, mission["scope"]["read_paths"],
                          max_files=b["max_files"], max_bytes=b["max_bytes"])
    listed = reader.list_files()
    if len(listed) > b["max_files"]:
        return _blocked(mission, "FILE_BUDGET_EXCEEDED", f"{len(listed)} > {b['max_files']}", pread)
    sources, skipped = {}, []
    try:
        for rel in listed:
            if time.monotonic() - t0 > b["max_wall_ms"] / 1000:
                raise BudgetExceeded("max_wall_ms")
            if not rel.endswith(".py"):
                skipped.append(rel)
                continue
            data = reader.read(rel)
            if data is not None:
                sources[rel] = data
        content = analyse(sources, frozenset(sources), max_files=b["max_files"])
    except BudgetExceeded as exc:
        content = _blocked(mission, "BUDGET_EXCEEDED", str(exc), pread)
        content["status"] = "FAILED"
        return content
    except ValueError as exc:
        return _blocked(mission, str(exc).split(":")[0], str(exc), pread)

    content.update({
        "agent_id": mission["agent_id"], "profile": pread, "mission_id": mission["mission_id"],
        "analyzed_ref": mission["analyzed_ref"], "zone_id": mission["question"]["zone_id"],
        "sources": [pread] + [s for s in reader.inventory()],
        "refused_paths": reader.refusals(), "skipped_non_python": sorted(skipped), "errors": [],
    })
    return content


# --------------------------------------------------------------------------- matrice attendu / obtenu

CASES = [
    {
        "id": "CARTO_1_import_seul", "title": "Import sans appel",
        "sources": {"main.py": b"from worker import run\n",
                    "worker.py": b"def run():\n    pass\n"},
        "expected": {"calls": [], "imports": [["main.py", "worker:run", "IMPORT_ONLY"]],
                     "production_calls": 0, "findings": [], "unknowns": []},
    },
    {
        "id": "CARTO_2_test_seul", "title": "Appel seulement dans un test",
        "sources": {"main.py": b"def run():\n    pass\n",
                    "tests/test_main.py": b"from main import run\n\n\ndef test_run():\n    run()\n"},
        "expected": {"calls": [["tests/test_main.py", "run", "TEST_CALL"]],
                     "imports": [["tests/test_main.py", "main:run", "IMPORT_USED"]],
                     "production_calls": 0, "findings": [], "unknowns": []},
    },
    {
        "id": "CARTO_3_import_test_en_production", "title": "Helper de test importé par le code de production",
        "sources": {"app.py": b"from tests.helpers import make\n\n\ndef go():\n    make()\n",
                    "tests/helpers.py": b"def make():\n    pass\n"},
        "expected": {"calls": [["app.py", "make", "TEST_SCOPE_CALL"]],
                     "imports": [["app.py", "tests.helpers:make", "IMPORT_TEST_SCOPE"]],
                     "production_calls": 0, "findings": [], "unknowns": []},
    },
    {
        "id": "CARTO_4_fallback_conditionnel", "title": "Appel de secours identifié comme conditionnel",
        "sources": {"main.py": b"try:\n    primary.run()\nexcept ValueError:\n    fallback.run()\n"},
        "expected": {"calls": [["main.py", "primary.run", "PRODUCTION_CALL"],
                               ["main.py", "fallback.run", "CONDITIONAL_PRODUCTION_CALL"]],
                     "imports": [], "production_calls": 1, "findings": [], "unknowns": []},
    },
    {
        "id": "CARTO_5_cible_dynamique", "title": "Cible d'appel dynamique reste INCONCLUSIVE",
        "sources": {"main.py": b"handlers = {}\nk = 'a'\nhandlers[k]()\n"},
        "expected": {"calls": [], "imports": [], "production_calls": 0, "findings": [],
                     "unknowns": ["DYNAMIC_CALL_TARGET"]},
    },
    {
        "id": "CARTO_6_deux_producteurs", "title": "Deux producteurs candidats du même fichier",
        "sources": {"export_a.py": b"def dump():\n    with open('out.json', 'w') as fh:\n        fh.write('{}')\n",
                    "export_b.py": b"from pathlib import Path\n\n\ndef dump_again():\n    Path('out.json').write_text('{}')\n"},
        "expected": {"calls": [["export_a.py", "fh.write", "PRODUCTION_CALL"], ["export_a.py", "open", "PRODUCTION_CALL"],
                               ["export_b.py", "Path", "PRODUCTION_CALL"],
                               ["export_b.py", "Path('out.json').write_text", "PRODUCTION_CALL"]],
                     "imports": [["export_b.py", "pathlib:Path", "IMPORT_USED"]],
                     "production_calls": 4, "findings": ["MULTIPLE_PRODUCER_CANDIDATES"], "unknowns": []},
    },
    {
        "id": "CARTO_7_flag_un_chemin", "title": "Flag lu sur un seul chemin",
        "sources": {"cfg.py": b"import os\n\n\ndef load():\n    return os.getenv('CAT_ZONE_FLAG')\n"},
        "expected": {"calls": [["cfg.py", "os.getenv", "PRODUCTION_CALL"]], "imports": [["cfg.py", "os", "IMPORT_USED"]],
                     "production_calls": 1, "findings": ["FLAG_SINGLE_PATH"], "unknowns": []},
    },
    {
        "id": "CARTO_8_flag_deux_chemins", "title": "Flag lu sur deux chemins",
        "sources": {"a.py": b"import os\n\n\ndef f():\n    return os.getenv('CAT_ZONE_FLAG')\n",
                    "b.py": b"import os\n\n\ndef g():\n    return os.environ.get('CAT_ZONE_FLAG')\n"},
        "expected": {"calls": [["a.py", "os.getenv", "PRODUCTION_CALL"], ["b.py", "os.environ.get", "PRODUCTION_CALL"]],
                     "imports": [["a.py", "os", "IMPORT_USED"], ["b.py", "os", "IMPORT_USED"]],
                     "production_calls": 2, "findings": ["FLAG_MULTI_PATH"], "unknowns": []},
    },
    {
        "id": "CARTO_9_source_illisible", "title": "Source non analysable",
        "sources": {"broken.py": b"def ?", "worker.py": b"def run(): pass\n"},
        "expected": {"calls": [], "imports": [], "production_calls": 0, "findings": [], "unknowns": ["PARSE_FAILED"]},
    },
    {
        "id": "CARTO_10_budget_31_fichiers", "title": "Budget de 30 fichiers dépassé",
        "sources": {f"m{i:02d}.py": b"x = 1\n" for i in range(31)},
        "expected": {"error": "FILE_BUDGET_EXCEEDED"},
    },
]


def _summary(content):
    return {
        "calls": sorted([r["path"], r["target"], r["status"]] for r in content["calls"]),
        "imports": sorted([r["path"], r["target"], r["status"]] for r in content["imports"]),
        "production_calls": content["activity"]["production_calls"],
        "findings": sorted(f["code"] for f in content["findings"]),
        "unknowns": sorted(u["reason"] for u in content["unknowns"]),
    }


def run_case(case):
    try:
        content = analyse(case["sources"])
    except ValueError as exc:
        return {"error": str(exc).split(":")[0]}
    return _summary(content)


def _normalised(expected):
    return {k: (sorted(v) if isinstance(v, list) else v) for k, v in expected.items()}


def cartographer_matrix() -> list[dict]:
    rows = []
    for case in CASES:
        obtained = run_case(case)
        expected = case["expected"]
        if "error" in expected:
            passed = obtained.get("error") == expected["error"]
        else:
            want = _normalised(expected)
            passed = all(obtained[k] == want[k] for k in want)
        rows.append({"id": case["id"], "title": case["title"], "expected": expected,
                     "obtained": obtained, "passed": passed})
    return rows


def cartographer_matrix_markdown(rows) -> str:
    out = ["| Cas | Titre | Attendu | Obtenu | Résultat |", "|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['id']} | {r['title']} | `{json.dumps(r['expected'], ensure_ascii=False, sort_keys=True)}` | "
                   f"`{json.dumps(r['obtained'], ensure_ascii=False, sort_keys=True)}` | {'PASS' if r['passed'] else 'ÉCHEC'} |")
    return "\n".join(out) + "\n"
