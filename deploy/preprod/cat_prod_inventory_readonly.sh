#!/bin/bash
# CAT-PREPROD-01, étapes 1 et 2 — inventaire LECTURE SEULE de l'API et du web servis sur crypto-restore-01.
# Révision S4-B-RV1 : liste FERMÉE de champs autorisés ; aucune configuration brute n'est reproduite.
#
# À lancer par l'opérateur, en utilisateur normal, SANS sudo :
#   bash cat_prod_inventory_readonly.sh > cat-prod-inventory-$(date -u +%Y%m%dT%H%M%SZ).json
#
# Garanties :
#   - n'écrit aucun fichier (sortie standard seulement), ne redémarre rien, n'envoie rien au réseau
#     hors requêtes GET locales (127.0.0.1) vers l'API et le web ;
#   - n'imprime JAMAIS une ligne de configuration telle quelle : ni ExecStart complet, ni ligne de
#     drop-in, ni valeur d'Environment, ni contenu d'EnvironmentFile ;
#   - chaque valeur imprimée appartient à une liste fermée et passe un filtre de forme
#     (chemin absolu simple, nom de variable, nombre, code). Toute autre valeur devient "<REDACTED>".
#
# Champs imprimés (liste fermée) :
#   units.<u>     : Id, ActiveState, SubState, ActiveEnterTimestamp, FragmentPath, DropInPaths,
#                   WorkingDirectory, EnvironmentFiles (chemins seulement), binds (src/dst des BindReadOnlyPaths,
#                   chemins seulement), exec_program, exec_entry
#                   (module Python après -m, ou script .mjs/.py), exec_host_port, env_names (NOMS seulement),
#                   env_paths (valeur des seules variables *_PATH dont la valeur est un chemin absolu simple),
#                   env_numbers (valeur des seules variables *_S / *_MS / *_PORT si entier),
#                   dropin_directives (NOMS des directives de chaque drop-in, sans valeur),
#                   fragment_blob / dropin_blobs (identifiant git du fichier, sans contenu) ;
#   releases      : noms des dossiers de /opt/cat-app/releases (noms seulement) ;
#   *_tree        : identifiant git (blob SHA-1) et taille des fichiers source servis (.py, .mjs, .js, .sh,
#                   unités, requirements .txt ; fichiers du dist web), sans contenu ; jamais .env* ;
#   openapi_paths : chemins et méthodes déclarés par l'API servie (aucun corps) ;
#   build_sources : mêmes empreintes pour les sources de build gardées par les scripts Scanner
#                   (~/cat-market-block/web/frontend, ~/cat-scanner-universe-block/{web,web-refonte}/frontend, api-v11) ;
#   api_python    : versions de Python et des paquets de l'API ;
#   routes_*      : code HTTP et, s'il a une forme de code, schema/schema_version/error_code.
set -uo pipefail
PY=$(command -v python3)
API=http://127.0.0.1:8090
WEB=http://127.0.0.1:8181
exec "$PY" -I - "$API" "$WEB" <<'PYEOF'
import hashlib, json, os, re, subprocess, sys, urllib.request, urllib.error
API, WEB = sys.argv[1], sys.argv[2]
UNITS = ["crypto-operator-api.service", "crypto-operator-web.service",
         "cat-scanner-universe.service", "cat-scanner-universe.timer"]
SHOW_PROPS = ["Id", "ActiveState", "SubState", "ActiveEnterTimestamp", "FragmentPath", "DropInPaths",
              "WorkingDirectory", "EnvironmentFiles", "ExecStart", "Environment", "BindReadOnlyPaths", "BindPaths"]
RELEASES = "/opt/cat-app/releases"
R = "<REDACTED>"

SAFE_PATH = re.compile(r"/[A-Za-z0-9._@+/-]{0,510}")
SAFE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
SAFE_MODULE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,127}(:[A-Za-z_][A-Za-z0-9_]{0,63})?")
SAFE_TAG = re.compile(r"[A-Za-z0-9_.:/-]{1,80}")
SAFE_STATE = re.compile(r"[A-Za-z0-9 :.+_-]{0,64}")
SAFE_DIRNAME = re.compile(r"[A-Za-z0-9._+-]{1,160}")


def only(value, pattern):
    return value if isinstance(value, str) and pattern.fullmatch(value) else R


def sh(*args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=20).stdout
    except Exception as e:  # noqa: BLE001
        return f"ERROR {type(e).__name__}"


def blob(path):
    try:
        data = open(path, "rb").read()
    except OSError as e:
        return ["UNREADABLE", type(e).__name__]
    return [hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest(), len(data)]


def argv_tokens(execstart):
    # systemctl show: "{ path=/x ; argv[]=/x a b ; ignore_errors=no ; ... }". Only argv is parsed,
    # and only its token SHAPES are used below; the raw string is never printed.
    m = re.search(r"argv\[\]=(.*?) ;", execstart)
    return m.group(1).split() if m else []


def exec_summary(execstart):
    t = argv_tokens(execstart)
    out = {"exec_program": only(t[0], SAFE_PATH) if t else None, "exec_entry": None, "exec_host_port": None}
    rest = t[1:]
    if rest and rest[0] == "node":  # "/usr/bin/env node script.mjs"
        rest = rest[1:]
    for i, tok in enumerate(rest):
        if tok == "-m" and i + 1 < len(rest):
            mod = [x for x in rest[i + 1:i + 3] if SAFE_MODULE.fullmatch(x)]
            out["exec_entry"] = {"module": mod[:2]}
            break
        if tok.endswith((".mjs", ".py", ".js")):
            out["exec_entry"] = {"script": only(tok, SAFE_PATH)}
            break
    hp = {}
    for i, tok in enumerate(rest[:-1]):
        if tok == "--host" and re.fullmatch(r"[0-9.:]{1,45}|localhost", rest[i + 1]):
            hp["host"] = rest[i + 1]
        if tok == "--port" and re.fullmatch(r"[0-9]{1,5}", rest[i + 1]):
            hp["port"] = rest[i + 1]
    out["exec_host_port"] = hp or None
    return out


def env_summary(raw):
    names, paths, numbers, fragments = [], {}, {}, 0
    for item in raw.split():
        k, eq, v = item.partition("=")
        if not eq or not SAFE_NAME.fullmatch(k):
            fragments += 1  # part of a quoted value containing spaces: never printed
            continue
        names.append(k)
        if k.endswith("_PATH") and k not in ("PYTHONPATH",) and SAFE_PATH.fullmatch(v):
            paths[k] = v
        if re.fullmatch(r"[A-Z0-9_]*_(S|MS|PORT)", k) and re.fullmatch(r"[0-9]{1,9}", v):
            numbers[k] = v
    return {"env_names": sorted(set(names)), "env_paths": paths, "env_numbers": numbers,
            "env_unparsed_fragments": fragments}


def dropin_directives(path):
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError as e:
        return ["UNREADABLE", type(e).__name__]
    names = []
    for line in lines:
        s = line.strip()
        if s.startswith("[") and s.endswith("]") and SAFE_NAME.fullmatch(s[1:-1]):
            names.append(s)
        elif "=" in s and not s.startswith(("#", ";")):
            k = s.split("=", 1)[0].strip()
            names.append(k if SAFE_NAME.fullmatch(k) else R)
    return names


def binds(raw):
    # "src:dst[:opts] ..." ; only the two paths are kept, each through the path filter.
    out = []
    for item in raw.split():
        parts = item.lstrip("-").split(":")
        src = parts[0]
        dst = parts[1] if len(parts) > 1 and parts[1].startswith("/") else src
        out.append({"src": only(src, SAFE_PATH), "dst": only(dst, SAFE_PATH)})
    return out


def host_path(path, unit_binds):
    """Path seen by the service (inside its mount namespace) -> file on the host, via its binds."""
    if not path or path == R:
        return None
    best = None
    for b in unit_binds:
        d = b["dst"].rstrip("/")
        if R in (b["src"], b["dst"]):
            continue
        if (path == d or path.startswith(d + "/")) and (best is None or len(d) > len(best["dst"].rstrip("/"))):
            best = b
    return path if best is None else best["src"].rstrip("/") + path[len(best["dst"].rstrip("/")):]


def unit(u):
    props = {}
    for line in sh("systemctl", "show", u, "-p", ",".join(SHOW_PROPS)).splitlines():
        k, _, v = line.partition("=")
        props[k] = v
    out = {k: only(props.get(k, ""), SAFE_STATE) for k in ("Id", "ActiveState", "SubState", "ActiveEnterTimestamp")}
    for k in ("FragmentPath", "WorkingDirectory"):
        v = props.get(k, "").lstrip("!-")
        out[k] = only(v, SAFE_PATH) if v else None
    out["DropInPaths"] = [only(p, SAFE_PATH) for p in props.get("DropInPaths", "").split()]
    out["EnvironmentFiles"] = [only(p.lstrip("-"), SAFE_PATH) for p in props.get("EnvironmentFiles", "").split()
                               if p.startswith(("/", "-/"))]
    out["binds"] = binds(props.get("BindReadOnlyPaths", "") + " " + props.get("BindPaths", ""))
    out.update(exec_summary(props.get("ExecStart", "")))
    out.update(env_summary(props.get("Environment", "")))
    out["fragment_blob"] = blob(out["FragmentPath"]) if out["FragmentPath"] not in (None, R) else None
    out["dropins"] = {p: {"blob": blob(p), "directives": dropin_directives(p)} for p in out["DropInPaths"] if p != R}
    return out


SKIP_DIRS = {".venv", "venv", "node_modules", "__pycache__", ".git", "logs", "data", "databases", ".cache", "dist"}
SRC_EXT = (".py", ".mjs", ".js", ".cjs", ".sh", ".service", ".timer", ".txt")
WEB_EXT = (".html", ".js", ".mjs", ".css", ".svg", ".json", ".webmanifest", ".map", ".ico", ".png", ".woff2")


def tree(root, exts, limit=6000):
    if not root or root == R or not os.path.isdir(root):
        return "NOT_READABLE"
    files = {}
    for d, dirs, names in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        for n in sorted(names):
            p = os.path.join(d, n)
            rel = os.path.relpath(p, root)
            if n.endswith(exts) and not n.startswith(".env") and os.path.isfile(p) and not os.path.islink(p):
                files[only(rel, re.compile(r"[A-Za-z0-9._@+/ -]{1,400}"))] = blob(p)
                if len(files) >= limit:
                    files["<TRUNCATED>"] = limit
                    return files
    return files


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=5) as r:
            code, body = r.status, r.read(2_000_000)
    except urllib.error.HTTPError as e:
        code, body = e.code, e.read(2_000_000)
    except Exception as e:  # noqa: BLE001
        return {"error": type(e).__name__}
    tag = None
    try:
        d = json.loads(body)
        if isinstance(d, dict):
            tag = {k: only(d[k], SAFE_TAG) for k in ("schema", "schema_version", "error_code") if isinstance(d.get(k), str)}
    except Exception:  # noqa: BLE001
        pass
    return {"http": code, "tag": tag}


out = {"inventory_schema": "cat-prod-inventory/2.0.0", "host": only(sh("hostname").strip(), SAFE_DIRNAME),
       "observed_utc": only(sh("date", "-u", "+%FT%TZ").strip(), SAFE_STATE),
       "units": {u: unit(u) for u in UNITS}}
try:
    out["releases"] = sorted(only(n, SAFE_DIRNAME) for n in os.listdir(RELEASES))
except OSError as e:
    out["releases"] = ["UNREADABLE", type(e).__name__]

api, web, scan = (out["units"][u] for u in UNITS[:3])
out["api_tree"] = {"root": api["WorkingDirectory"],
                   "root_on_host": host_path(api["WorkingDirectory"], api["binds"]),
                   "files": tree(host_path(api["WorkingDirectory"], api["binds"]), SRC_EXT)}
out["scanner_tree"] = {"root": scan["WorkingDirectory"], "files": tree(scan["WorkingDirectory"], SRC_EXT)}
# The web unit serves files bind-mounted over its WorkingDirectory (drop-ins of the Scanner
# deployments): the files on disk under WorkingDirectory are NOT necessarily the served ones.
# Every served path is therefore translated through the unit's binds before hashing.
script = (web.get("exec_entry") or {}).get("script")
script_host = host_path(script, web["binds"])
out["web_server"] = {"script_seen_by_service": script, "script_on_host": script_host,
                     "script_blob": blob(script_host) if script_host else None,
                     "host_dir_files": tree(os.path.dirname(script_host), SRC_EXT, limit=500) if script_host else None}
cands = [os.path.join(web["WorkingDirectory"], "dist") if web["WorkingDirectory"] not in (None, R) else None]
if script and script != R:
    cands.append(os.path.join(os.path.dirname(os.path.dirname(script)), "dist"))
cands += [v for v in web["env_paths"].values() if v.rstrip("/").endswith("dist")]
cands = list(dict.fromkeys(c for c in cands if c))
served = [(c, host_path(c, web["binds"])) for c in cands]
dists = [(c, h) for c, h in served if h and os.path.isdir(h)]
out["web_dist"] = {"candidates_seen_by_service": cands, "used_seen_by_service": dists[0][0] if dists else None,
                   "used_on_host": dists[0][1] if dists else None,
                   "files": tree(dists[0][1], WEB_EXT) if dists else "NOT_FOUND"}


# Build sources kept on the VPS by the Scanner deployment scripts (prep.sh, prep-refonte.sh, prep-v11.sh):
# the served web bundle was built from them, so their blobs are what can be matched against GitHub.
HOME_DIR = os.path.expanduser("~")
BUILD_EXT = (".ts", ".tsx", ".css", ".json", ".mjs", ".js", ".cjs", ".html", ".py", ".txt")
out["build_sources"] = {}
for rel in ("cat-market-block/web/frontend", "cat-scanner-universe-block/web/frontend",
            "cat-scanner-universe-block/web-refonte/frontend", "cat-scanner-universe-block/api-v11"):
    d = os.path.join(HOME_DIR, rel)
    out["build_sources"]["~/" + rel] = tree(d, BUILD_EXT, limit=8000) if os.path.isdir(d) else "ABSENT"

prog = api.get("exec_program")
if prog and prog != R and os.path.exists(prog):
    code = ("import sys,json\nfrom importlib import metadata as md\n"
            "names=('fastapi','starlette','uvicorn','pydantic','pydantic_core','httpx','anyio')\n"
            "have={d.metadata['Name'].lower():d.version for d in md.distributions()}\n"
            "print(json.dumps({'python':sys.version.split()[0],'packages':{n:have[n] for n in names if n in have}}))")
    raw = sh(prog, "-I", "-c", code).strip()
    try:
        d = json.loads(raw)
        out["api_python"] = {"python": only(d.get("python"), SAFE_TAG),
                             "packages": {k: only(v, SAFE_TAG) for k, v in d.get("packages", {}).items()}}
    except Exception:  # noqa: BLE001
        out["api_python"] = "UNPARSEABLE"

routes = ["/healthz", "/api/operator/v1/snapshot", "/api/operator/v1/portfolio", "/api/operator/v1/decision-pipeline",
          "/api/operator/v1/system-health", "/api/operator/v1/ppl-comparison", "/api/operator/v1/ppl-accounting-history",
          "/api/operator/v1/financial-reconciliation", "/api/operator/v1/market-microstructure",
          "/api/operator/v1/agent-invocations/repository-cartographer",
          "/api/operator/v1/agent-invocations/repository-cartographer/history",
          "/api/operator/v1/agent-invocations/repository-cartographer/schedule",
          "/api/operator/v1/runtime-service", "/api/operator/v1/burn-in", "/api/operator/v1/burn-in/statistics",
          "/api/operator/v1/market", "/api/operator/v1/research-strategies", "/api/operator/v1/research-lab",
          "/api/operator/v1/venue-comparison", "/api/operator/v1/market-flow", "/api/operator/v1/bbo-composite-history",
          "/api/operator/v1/scanner-universe", "/api/operator/v1/storage", "/api/operator/v1/storage-inventory",
          "/api/operator/v1/lab-experiments", "/api/operator/v1/events", "/api/operator/v1/radar-projection",
          "/api/operator/v1/spot-radar/scanner", "/api/operator/v1/intraday/scanner",
          "/api/operator/v1/signals-indicators", "/api/operator/v1/paper-balance-history"]
out["openapi_paths"] = None
o = None
try:
    with urllib.request.urlopen(API + "/openapi.json", timeout=5) as r:
        o = json.loads(r.read(4_000_000))
except Exception as e:  # noqa: BLE001
    out["openapi_paths"] = {"error": type(e).__name__}
if isinstance(o, dict):
    out["openapi_paths"] = {only(p, SAFE_TAG): sorted(m.upper() for m in v if m in ("get", "post", "put", "delete", "patch"))
                            for p, v in sorted(o.get("paths", {}).items())}
out["routes_api"] = {r: get(API + r) for r in routes if not r.startswith("/api/operator/v1/spot-radar")}
out["routes_web"] = {r: get(WEB + r) for r in routes}
out["web_index"] = get(WEB + "/")
print(json.dumps(out, indent=1, sort_keys=True))
PYEOF
