"""Cartographie d'une surface affichée — profil ``observability-cartographer`` (banc isolé v2).

Question bornée (``METRIC_SURFACE_MAP``) : pour **une** surface (vue ``.ts``/``.tsx``), quelles
métriques sont affichées, quel code serveur les produit, sont-elles calculées à plusieurs endroits,
et le frontend recalcule-t-il une valeur d'autorité (PnL, equity, classement, verdict) ?

Analyse statique uniquement : ``ast`` pour Python, motifs pour TypeScript. Rien n'est importé ni
exécuté. La chaîne d'un dataset appartient au data-provenance-auditor : elle est citée en entrée
(``upstream_reports``), jamais recalculée. Le cycle de vie des messages Telegram et toute
observation runtime sont hors périmètre (mission séparée).
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

VERSION = "observability-cartographer.bench.v1"
MAX_FILES = c.METRIC_SURFACE_MAX_FILES
LIMITS = [
    "STATIC_ANALYSIS_ONLY_NO_IMPORT_NO_EXECUTION",
    "METRIC_IDENTIFICATION_SNAKE_CASE_FIELDS_ONLY",
    "PRODUCER_IS_A_DICT_KEY_LITERAL_IN_SCOPE",
    "DISPLAYED_IS_NOT_SOURCE_OF_TRUTH",
    "DATASET_CHAIN_DELEGATED_TO_DATA_PROVENANCE_AUDITOR",
    "TELEGRAM_MESSAGE_LIFECYCLE_OUT_OF_SCOPE",
    "NO_RUNTIME_OBSERVATION",
    "REPORT_IS_NOT_SELF_CERTIFYING",
]

# Un champ de charge utile serveur lu par la vue : propriété snake_case (au moins un « _ »).
FIELD_ACCESS = re.compile(r"\??\.([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b(?!\s*\()")
# Valeurs d'autorité que le frontend ne recalcule pas (CLAUDE.md §1).
# Jeton d'autorité : minuscule non précédé d'une lettre (pnl_usd, d.equity) ou Capitalisé (totalPnl),
# jamais suivi d'une minuscule (feedback, scoreboard ne correspondent pas).
TOK = (r"(?:(?<![A-Za-z])(?:pnl|equity|balance|realized|unrealized|capital|fees?|rank|ranking|score|verdict)"
       r"|(?:Pnl|PnL|PNL|Equity|Balance|Realized|Unrealized|Capital|Fees?|Rank|Ranking|Score|Verdict))(?![a-z])")
IDENT_AUTH = rf"[\w$]*{TOK}[\w$]*"
AUTH_ARITH = re.compile(rf"(?:{IDENT_AUTH}\s*[-+*/](?![-+*/=])\s*[\w.(]|[-+*/](?!=)\s*[\w.?]*{TOK})")
AUTH_ASSIGN = re.compile(rf"{IDENT_AUTH}\s*(?::|=(?![=>]))\s*[^;,]*?[\w)\]]\s*[-+*/](?![-+*/=])\s*[\w(]")
AUTH_REDUCE = re.compile(rf"\.(?:reduce|sort)\s*\(.*{TOK}")
STRING = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`[^`]*`')
NULL_AS_ZERO = re.compile(r"(\?\?|\|\|)\s*0(?![\d.\w])")
UNIT_SUFFIXES = ("_ms", "_s", "_sec", "_utc", "_at", "_ts", "_pct", "_percent", "_bps", "_usd",
                 "_usdt", "_count", "_ratio", "_bytes", "_days", "_hours", "_minutes", "_qty", "_price")
NON_NUMERIC_SUFFIXES = ("_status", "_state", "_label", "_name", "_kind", "_reason", "_id", "_code",
                        "_mode", "_type", "_text", "_title", "_url", "_path", "_symbol", "_source",
                        "_message", "_ref", "_list", "_items", "_rows", "_by", "_key", "_version")
ROUTE = re.compile(r"^/api/[A-Za-z0-9/_.{}-]+$")


def _strip_comment(line):
    line = STRING.sub('""', line)
    i = line.find("//")
    return line if i < 0 else line[:i]


def _line(text, pos):
    return text.count("\n", 0, pos) + 1


def _is_test(path):
    return "/test/" in f"/{path}" or "/tests/" in f"/{path}" or ".test." in path or path.split("/")[-1].startswith("test_")


# --------------------------------------------------------------------------- analyse pure

def _py_producers(rel, data, digest, unknowns):
    """Sites où une clé littérale de dict est produite : {"k": v}, x["k"] = v, dict(k=v), d.update(k=v)."""
    try:
        tree = ast.parse(data.decode("utf-8"), filename=rel)
    except (SyntaxError, UnicodeDecodeError, ValueError):
        unknowns.append({"path": rel, "line": None, "reason": "PARSE_FAILED", "level": "INCONCLUSIVE"})
        return [], []
    sites, routes = [], []
    parents = {}
    for node in ast.walk(tree):
        for ch in ast.iter_child_nodes(node):
            parents[ch] = node

    def owner(node):
        cur = node
        while cur in parents:
            cur = parents[cur]
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return cur.name
        return "<module>"

    def add(key, value, node):
        computed = isinstance(value, (ast.BinOp, ast.UnaryOp)) or (
            isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
            and value.func.id in ("sum", "round", "abs", "max", "min", "float", "int", "len"))
        sites.append({"field": key, "path": rel, "line": node.lineno, "symbol": owner(node),
                      "computed": computed, "formula": ast.unparse(value) if computed else None,
                      "sha256": digest})

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for kk, v in zip(node.keys, node.values):
                if isinstance(kk, ast.Constant) and isinstance(kk.value, str):
                    add(kk.value, v, kk)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) \
                        and isinstance(t.slice.value, str):
                    add(t.slice.value, node.value, t)
        elif isinstance(node, ast.Call) and ((isinstance(node.func, ast.Name) and node.func.id == "dict")
                                             or (isinstance(node.func, ast.Attribute) and node.func.attr == "update")):
            for kw in node.keywords:
                if kw.arg:
                    add(kw.arg, kw.value, kw.value)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ("get", "post") \
                        and d.args and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str) \
                        and ROUTE.match(d.args[0].value):
                    routes.append({"route": d.args[0].value, "path": rel, "line": d.lineno, "symbol": node.name,
                                   "sha256": digest})
    return sites, routes


def analyse(sources: dict[str, bytes], surface_path: str, *, max_files: int = MAX_FILES) -> dict:
    """Contenu déterministe (sans métadonnées d'exécution). Lève ValueError si budget/surface."""
    if len(sources) > max_files:
        raise ValueError("FILE_BUDGET_EXCEEDED")
    if surface_path not in sources:
        raise ValueError("SURFACE_UNREADABLE")
    digests = {p: hashlib.sha256(d).hexdigest() for p, d in sources.items()}
    texts = {p: d.decode("utf-8", errors="replace") for p, d in sources.items() if p.endswith((".ts", ".tsx"))}
    unknowns, findings = [], []

    # 1. Métriques affichées : champs snake_case lus par la surface.
    surface = texts[surface_path]
    displayed = defaultdict(list)
    for m in FIELD_ACCESS.finditer(surface):
        displayed[m.group(1)].append(_line(surface, m.start()))

    # 2. Producteurs côté serveur (Python hors tests).
    sites, routes = [], []
    for p, d in sorted(sources.items()):
        if p.endswith(".py") and not _is_test(p):
            s, r = _py_producers(p, d, digests[p], unknowns)
            sites += s
            routes += r
    by_field = defaultdict(list)
    for s in sites:
        by_field[s["field"]].append(s)

    metrics = []
    for field in sorted(displayed):
        lines = sorted(set(displayed[field]))
        prod = sorted(by_field.get(field, []), key=lambda s: (s["path"], s["line"]))
        files = sorted({s["path"] for s in prod})
        formulas = sorted({s["formula"] for s in prod if s["computed"]})
        computed_files = sorted({s["path"] for s in prod if s["computed"]})
        if not prod:
            cls, level = "SOURCE_UNRESOLVED", "NOT_FOUND"
            unknowns.append({"path": surface_path, "line": lines[0], "reason": "METRIC_SOURCE_NOT_IN_SCOPE",
                             "field": field, "level": "INCONCLUSIVE"})
        elif len(computed_files) >= 2 and len(formulas) >= 2:
            cls, level = "DUPLICATED", "PROVEN"
            findings.append(k.finding(
                "METRIC", "DUPLICATED_CALCULATION",
                f"La métrique « {field} » est calculée dans {len(computed_files)} fichiers avec "
                f"{len(formulas)} formules différentes.", "PROVEN", "HIGH",
                [k.evidence(s["path"], s["line"], s["symbol"], "CODE", s["sha256"]) for s in prod if s["computed"]]))
        elif len(files) == 1:
            cls, level = "CANONICAL_EXISTING", "SUPPORTED"
        else:
            cls, level = "DERIVED", "SUPPORTED"
        unit = "DECLARED_BY_NAME" if field.endswith(UNIT_SUFFIXES) else (
            "NOT_APPLICABLE" if field.endswith(NON_NUMERIC_SUFFIXES) else "NOT_DECLARED")
        if unit == "NOT_DECLARED" and prod:
            findings.append(k.finding(
                "METRIC", "UNIT_NOT_DECLARED",
                f"Aucune unité n'est portée par le nom « {field} » ; à confirmer dans le contrat de la route.",
                "INFERRED", "LOW", [k.evidence(surface_path, lines[0], field, "LITERAL", digests[surface_path])]))
        metrics.append({
            "metric_id": f"{field}", "displayed_at": [{"path": surface_path, "line": ln} for ln in lines],
            "classification": cls, "level": level, "unit": unit,
            "producers": [{"path": s["path"], "line": s["line"], "symbol": s["symbol"],
                           "computed": s["computed"], "formula": s["formula"]} for s in prod],
        })

    # 3. Frontend : recalcul d'une valeur d'autorité, null affiché 0 (tous les .ts/.tsx du périmètre).
    for p, text in sorted(texts.items()):
        if _is_test(p):
            continue
        for i, raw in enumerate(text.splitlines(), start=1):
            line = _strip_comment(raw)
            if AUTH_ARITH.search(line) or AUTH_ASSIGN.search(line) or AUTH_REDUCE.search(line):
                findings.append(k.finding(
                    "AUTHORITY", "FRONTEND_RECALCULATES_AUTHORITY",
                    f"{p}:{i} calcule sur une valeur d'autorité (PnL, equity, classement…) côté frontend ; "
                    "le frontend formate, il ne recalcule pas (CLAUDE.md §1).", "PROVEN", "MEDIUM",
                    [k.evidence(p, i, None, "CODE", digests[p])]))
            if NULL_AS_ZERO.search(line):
                findings.append(k.finding(
                    "NULL_SEMANTICS", "NULL_ZERO_AMBIGUITY",
                    f"{p}:{i} remplace une valeur absente par 0 : UNKNOWN ≠ 0.", "PROVEN", "MEDIUM",
                    [k.evidence(p, i, None, "CODE", digests[p])]))

    # 4. Routes lues par le frontend et routes servies dans le périmètre.
    served = {r["route"]: r for r in routes}
    endpoints = []
    for p, text in sorted(texts.items()):
        for m in re.finditer(r'"(/api/[A-Za-z0-9/_.-]+)"', text):
            ep = m.group(1)
            r = served.get(ep)
            endpoints.append({"endpoint": ep, "client": {"path": p, "line": _line(text, m.start())},
                              "route": ({"path": r["path"], "line": r["line"], "symbol": r["symbol"]} if r else None)})
            if not r:
                unknowns.append({"path": p, "line": _line(text, m.start()), "reason": "ROUTE_NOT_IN_SCOPE",
                                 "field": ep, "level": "INCONCLUSIVE"})

    if not metrics:
        unknowns.append({"path": surface_path, "line": None, "reason": "NO_METRIC_IDENTIFIED", "level": "INCONCLUSIVE"})
    unknowns = sorted({(u["path"], u["line"] or 0, u["reason"], u.get("field", "")): u for u in unknowns}.values(),
                      key=lambda u: (u["path"], u["line"] or 0, u["reason"], u.get("field", "")))
    return {
        "contract": c.REPORT_CONTRACT, "cartographer_version": VERSION,
        "status": "COMPLETE" if not unknowns else "PARTIAL",
        "metrics": metrics,
        "endpoints": sorted(endpoints, key=lambda e: (e["client"]["path"], e["client"]["line"], e["endpoint"])),
        "findings": k.sort_findings(findings),
        "unknowns": unknowns,
        "runtime_measurements_required": [],
        "limits": LIMITS,
    }


# --------------------------------------------------------------------------- mission

def _blocked(mission, code, detail, profile=None):
    q = (mission or {}).get("question") if isinstance(mission, dict) else None
    surface = {"id": q.get("surface_id"), "path": q.get("surface_path")} if isinstance(q, dict) else None
    return k.blocked_content(mission, version_key="cartographer_version", version=VERSION, code=code,
                             detail=detail, profile=profile, limits=LIMITS,
                             extra={"surface": surface, "metrics": [], "endpoints": [], "inputs_cited": []})


def audit_surface(mission, workspace_root, profile_root, *, clock=time.time_ns) -> dict:
    """Exécute la mission et retourne le rapport scellé. N'écrit rien."""
    return k.seal(lambda t0: _content(mission, workspace_root, profile_root, t0), mission, clock=clock,
                  failed_content=lambda code, d: _blocked(mission, code, d))


def _content(mission, workspace_root, profile_root, t0):
    try:
        c.validate_mission(mission)
    except c.MissionRejected as exc:
        return _blocked(mission, exc.code, exc.detail)
    if mission["agent_id"] != "observability-cartographer" or mission["question"]["kind"] != "METRIC_SURFACE_MAP":
        return _blocked(mission, "AGENT_NOT_QUALIFIED_FOR_BENCH", mission["agent_id"])
    try:
        pread = k.read_profile(mission, profile_root)
    except k.Blocked as exc:
        return _blocked(mission, exc.code, exc.detail, exc.profile)
    b, q = mission["budget"], mission["question"]
    reader = ScopedReader(workspace_root, mission["scope"]["read_paths"], max_files=b["max_files"],
                          max_bytes=b["max_bytes"])
    listed = reader.list_files()
    if len(listed) > b["max_files"]:
        return _blocked(mission, "FILE_BUDGET_EXCEEDED", f"{len(listed)} > {b['max_files']}", pread)
    sources, skipped = {}, []
    try:
        for rel in listed:
            if time.monotonic() - t0 > b["max_wall_ms"] / 1000:
                raise BudgetExceeded("max_wall_ms")
            if not rel.endswith((".py", ".ts", ".tsx")):
                skipped.append(rel)
                continue
            data = reader.read(rel)
            if data is not None:
                sources[rel] = data
        content = analyse(sources, q["surface_path"], max_files=b["max_files"])
    except BudgetExceeded as exc:
        out = _blocked(mission, "BUDGET_EXCEEDED", str(exc), pread)
        out["status"] = "FAILED"
        return out
    except ValueError as exc:
        return _blocked(mission, str(exc).split(":")[0], q["surface_path"], pread)
    content.update({
        "agent_id": mission["agent_id"], "profile": pread, "mission_id": mission["mission_id"],
        "analyzed_ref": mission["analyzed_ref"], "surface": {"id": q["surface_id"], "path": q["surface_path"]},
        "inputs_cited": q["upstream_reports"],
        "sources": [pread] + reader.inventory(), "refused_paths": reader.refusals(),
        "skipped_unsupported": sorted(skipped), "errors": [],
    })
    return content


# --------------------------------------------------------------------------- matrice attendu / obtenu

V = "src/views/Panel.tsx"
CASES = [
    {"id": "OBS_1_canonique", "title": "Métrique produite à un seul endroit",
     "surface": V,
     "sources": {V: b'export function Panel({d}) { return <b>{d.win_rate_pct}</b>; }\n',
                 "api/app.py": b'def build(x):\n    return {"win_rate_pct": x.rate}\n'},
     "expected": {"metrics": [["win_rate_pct", "CANONICAL_EXISTING"]], "findings": [], "unknowns": []}},
    {"id": "OBS_2_deux_formules", "title": "Même métrique calculée deux fois, deux formules",
     "surface": V,
     "sources": {V: b'export function Panel({d}) { return <b>{d.fill_ratio}</b>; }\n',
                 "api/a.py": b'def a(f, o):\n    return {"fill_ratio": f / o}\n',
                 "api/b.py": b'def b(f, o):\n    return {"fill_ratio": f / (o + 1)}\n'},
     "expected": {"metrics": [["fill_ratio", "DUPLICATED"]], "findings": ["DUPLICATED_CALCULATION"], "unknowns": []}},
    {"id": "OBS_3_pnl_recalcule", "title": "La vue recalcule un PnL",
     "surface": V,
     "sources": {V: b'export function Panel({d}) {\n  const pnl = d.exit_usd - d.entry_usd;\n  return <b>{pnl}</b>;\n}\n',
                 "api/app.py": b'def build(t):\n    return {"exit_usd": t.x, "entry_usd": t.e}\n'},
     "expected": {"metrics": [["entry_usd", "CANONICAL_EXISTING"], ["exit_usd", "CANONICAL_EXISTING"]],
                  "findings": ["FRONTEND_RECALCULATES_AUTHORITY"], "unknowns": []}},
    {"id": "OBS_4_null_zero", "title": "Valeur absente affichée 0",
     "surface": V,
     "sources": {V: b'export function Panel({d}) { return <b>{d.open_count ?? 0}</b>; }\n',
                 "api/app.py": b'def build(n):\n    return {"open_count": n}\n'},
     "expected": {"metrics": [["open_count", "CANONICAL_EXISTING"]], "findings": ["NULL_ZERO_AMBIGUITY"],
                  "unknowns": []}},
    {"id": "OBS_5_source_absente", "title": "Métrique sans producteur dans le périmètre",
     "surface": V,
     "sources": {V: b'export function Panel({d}) { return <b>{d.spread_bps}</b>; }\n'},
     "expected": {"metrics": [["spread_bps", "SOURCE_UNRESOLVED"]], "findings": [],
                  "unknowns": ["METRIC_SOURCE_NOT_IN_SCOPE"]}},
    {"id": "OBS_6_sans_unite", "title": "Métrique sans unité portée par le nom",
     "surface": V,
     "sources": {V: b'export function Panel({d}) { return <b>{d.signal_strength}</b>; }\n',
                 "api/app.py": b'def build(s):\n    return {"signal_strength": s}\n'},
     "expected": {"metrics": [["signal_strength", "CANONICAL_EXISTING"]], "findings": ["UNIT_NOT_DECLARED"],
                  "unknowns": []}},
    {"id": "OBS_7_route_hors_perimetre", "title": "Route lue par le client mais non servie dans le périmètre",
     "surface": V,
     "sources": {V: b'const URL = "/api/operator/v1/x";\nexport function Panel({d}) { return <b>{d.age_ms}</b>; }\n',
                 "api/app.py": b'def build(a):\n    return {"age_ms": a}\n'},
     "expected": {"metrics": [["age_ms", "CANONICAL_EXISTING"]], "findings": [], "unknowns": ["ROUTE_NOT_IN_SCOPE"]}},
    {"id": "OBS_8_budget", "title": "Budget de 30 fichiers dépassé",
     "surface": V, "sources": {**{f"api/m{i:02d}.py": b"x = 1\n" for i in range(30)}, V: b"x\n"},
     "expected": {"error": "FILE_BUDGET_EXCEEDED"}},
]


def summary(content):
    return {"metrics": sorted([m["metric_id"], m["classification"]] for m in content["metrics"]),
            "findings": sorted({f["code"] for f in content["findings"]}),
            "unknowns": sorted({u["reason"] for u in content["unknowns"]})}


def run_case(case):
    try:
        return summary(analyse(case["sources"], case["surface"]))
    except ValueError as exc:
        return {"error": str(exc).split(":")[0]}


def matrix() -> list[dict]:
    rows = []
    for case in CASES:
        got, want = run_case(case), case["expected"]
        passed = got.get("error") == want["error"] if "error" in want else all(
            got.get(key) == sorted(val) for key, val in want.items())
        rows.append({"id": case["id"], "title": case["title"], "expected": want, "obtained": got, "passed": passed})
    return rows
