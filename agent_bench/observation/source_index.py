"""Index statique des sources du périmètre (Python par ``ast``, TypeScript par motifs).

Analyse statique uniquement : aucun module du périmètre n'est importé ni exécuté.
Chaque fait indexé porte son fichier et sa ligne. Ce qui n'est pas reconnu par
ces règles n'est pas « absent » : le pilote le rapporte INCONCLUSIVE ou NOT_FOUND.
"""
from __future__ import annotations

import ast
import posixpath
import re
from dataclasses import dataclass, field

FILENAME = re.compile(r"^[A-Za-z0-9_{}.-]+\.(json|jsonl|bin|csv|ndjson)$")
NETWORK = re.compile(r"^(wss?|https?)://[^\s\"']+$")
TS_IMPORT = re.compile(r'^\s*import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+"([^"]+)"', re.MULTILINE)
TS_EXPORT_FN = re.compile(r"^export\s+(?:async\s+)?function\s+([A-Za-z_]\w*)", re.MULTILINE)
TS_EXPORT_CONST = re.compile(r"^export\s+const\s+([A-Za-z_]\w*)", re.MULTILINE)
TS_API = re.compile(r'"(/api/[A-Za-z0-9/_.-]+)"')
WRITE_ATTRS = {"write_bytes", "write_text"}
READ_ATTRS = {"read_bytes", "read_text"}


@dataclass
class Fact:
    path: str
    line: int
    symbol: str
    detail: str
    targets: tuple = ()


@dataclass
class PyModule:
    path: str
    module: str
    literals: list = field(default_factory=list)        # Fact(detail=value)
    templates: list = field(default_factory=list)       # Fact(detail=filename template)
    writes: list = field(default_factory=list)          # Fact(detail=kind), + .templates / .binding
    reads: list = field(default_factory=list)
    imports: list = field(default_factory=list)         # Fact(detail="module:name")
    env: list = field(default_factory=list)             # Fact(detail=ENV name)
    cli: list = field(default_factory=list)             # Fact(detail="--flag")
    routes: list = field(default_factory=list)          # Fact(detail=api path), symbol=handler
    route_calls: dict = field(default_factory=dict)     # handler -> [Fact(detail=global name)]
    globals_cls: dict = field(default_factory=dict)     # global name -> (class name, line)
    wallclock: list = field(default_factory=list)
    write_templates: list = field(default_factory=list)  # Fact(detail=template written)
    append_modes: list = field(default_factory=list)
    syntax_error: str | None = None
    argdest: dict = field(default_factory=dict)


@dataclass
class TsModule:
    path: str
    text: str
    imports: list = field(default_factory=list)   # (resolved_rel, [names], line)
    export_fns: list = field(default_factory=list)
    export_consts: list = field(default_factory=list)
    api_literals: list = field(default_factory=list)  # Fact


def _template(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            parts.append(v.value if isinstance(v, ast.Constant) else "{}")
        return "".join(parts)
    return None


def _templates_in(node):
    out = []
    for sub in ast.walk(node):
        t = _template(sub)
        if t and FILENAME.match(t):
            out.append(t)
    return out


def _enclosing(parents, node):
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = cur.name
            outer = _enclosing(parents, cur)
            return f"{outer}.{name}" if outer != "<module>" else name
        cur = parents.get(cur)
    return "<module>"


def _call_name(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = _call_name(func.value)
        return f"{base}.{func.attr}" if base else func.attr
    return None


def _open_mode(call):
    mode = None
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        mode = call.args[1].value
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            mode = kw.value.value
    return mode if isinstance(mode, str) else "r"


def index_python(rel, data: bytes) -> PyModule:
    mod = rel[:-3].replace("/", ".")
    mod = mod.removesuffix(".__init__")
    pm = PyModule(path=rel, module=mod)
    try:
        tree = ast.parse(data.decode("utf-8"), filename=rel)
    except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
        pm.syntax_error = type(exc).__name__
        return pm
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    argdest = {}
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            pm.literals.append(Fact(rel, line, _enclosing(parents, node), node.value))
        t = _template(node) if isinstance(node, (ast.Constant, ast.JoinedStr)) else None
        if t and FILENAME.match(t) and not isinstance(parents.get(node), ast.JoinedStr):
            pm.templates.append(Fact(rel, line, _enclosing(parents, node), t))
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                pm.imports.append(Fact(rel, line, "<module>", f"{node.module}:{alias.name}"))
        if isinstance(node, ast.Assign) and isinstance(parents.get(node), ast.Module) \
                and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    pm.globals_cls[target.id] = (node.value.func.id, line)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) \
                        and dec.func.attr in ("get", "post", "put", "delete", "api_route") and dec.args:
                    path = _template(dec.args[0])
                    if path and path.startswith("/"):
                        pm.routes.append(Fact(rel, dec.lineno, node.name, path))
                        calls = []
                        for stmt in node.body:  # corps seulement : le décorateur n'est pas un appel du handler
                            for sub in ast.walk(stmt):
                                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                                        and isinstance(sub.func.value, ast.Name):
                                    calls.append(Fact(rel, sub.lineno, node.name, sub.func.value.id, (sub.func.attr,)))
                        # Les appels .read() d'abord : c'est la lecture servie par la route.
                        pm.route_calls[node.name] = sorted(calls, key=lambda f: (f.targets != ("read",), f.line))
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func) or ""
        sym = _enclosing(parents, node)
        if name in ("os.getenv", "os.environ.get", "getenv") and node.args:
            v = _template(node.args[0])
            if v:
                pm.env.append(Fact(rel, line, sym, v))
        if name.endswith("add_argument") and node.args:
            v = _template(node.args[0])
            if v and v.startswith("--"):
                pm.cli.append(Fact(rel, line, sym, v))
                argdest[v[2:].replace("-", "_")] = v
        if name in ("datetime.now", "datetime.utcnow", "time.time"):
            pm.wallclock.append(Fact(rel, line, sym, name))
        attr = node.func.attr if isinstance(node.func, ast.Attribute) else None
        if attr in WRITE_ATTRS or name in ("os.replace", "os.rename") or (name == "open" and set(_open_mode(node)) & set("wax")):
            kind = "os.replace" if name in ("os.replace", "os.rename") else (attr or f"open:{_open_mode(node)}")
            pm.writes.append(Fact(rel, line, sym, kind))
            target = node.func.value if attr in WRITE_ATTRS else (node.args[-1] if name.startswith("os.") else node.args[0] if node.args else node)
            for t in _templates_in(target):
                pm.write_templates.append(Fact(rel, line, sym, t))
            if name == "open" and "a" in _open_mode(node):
                pm.append_modes.append(Fact(rel, line, sym, _open_mode(node)))
            # Attributs du chemin écrit, pour relier plus tard un argument argparse (--x).
            pm.writes[-1].targets = tuple(sorted({sub.attr for sub in ast.walk(target) if isinstance(sub, ast.Attribute)}))
        elif attr in READ_ATTRS or name in ("os.open", "json.load") or (name == "open" and not set(_open_mode(node)) & set("wax")):
            pm.reads.append(Fact(rel, line, sym, attr or name))
    pm.argdest = argdest
    return pm


def _resolve_ts(rel, spec, known):
    if not spec.startswith("."):
        return None
    base = posixpath.normpath(posixpath.join(posixpath.dirname(rel), spec))
    for ext in (".ts", ".tsx", "/index.ts"):
        if base + ext in known:
            return base + ext
    return None


def index_ts(rel, data: bytes, known) -> TsModule:
    text = data.decode("utf-8", errors="replace")
    tm = TsModule(path=rel, text=text)

    def line_of(pos):
        return text.count("\n", 0, pos) + 1

    for m in TS_IMPORT.finditer(text):
        names = [n.strip().split(" as ")[0].replace("type ", "").strip() for n in m.group(1).split(",") if n.strip()]
        tm.imports.append((_resolve_ts(rel, m.group(2), known), names, line_of(m.start())))
    tm.export_fns = [(m.group(1), line_of(m.start())) for m in TS_EXPORT_FN.finditer(text)]
    tm.export_consts = [(m.group(1), line_of(m.start())) for m in TS_EXPORT_CONST.finditer(text)]
    tm.api_literals = [Fact(rel, line_of(m.start()), "<module>", m.group(1)) for m in TS_API.finditer(text)]
    return tm


def ts_literal_lines(tm, literal):
    out, start = [], 0
    needle = f'"{literal}"'
    while True:
        i = tm.text.find(needle, start)
        if i < 0:
            return out
        out.append(tm.text.count("\n", 0, i) + 1)
        start = i + 1
