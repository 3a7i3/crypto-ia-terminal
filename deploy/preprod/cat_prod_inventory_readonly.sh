#!/bin/bash
# CAT-PREPROD-01, étapes 1 et 2 — inventaire LECTURE SEULE de l'API et du web servis sur crypto-restore-01.
#
# À lancer par l'opérateur, en utilisateur normal (lecanada26), SANS sudo :
#   bash cat_prod_inventory_readonly.sh > cat-prod-inventory-$(date -u +%Y%m%dT%H%M%SZ).json
#
# Ce script n'écrit aucun fichier (sortie standard seulement), ne redémarre rien, ne lit aucun
# secret et n'envoie rien au réseau, hors requêtes GET locales (127.0.0.1) vers l'API et le web.
# Il n'imprime que :
#   - la configuration systemd des unités API/web/Scanner (ExecStart, WorkingDirectory, drop-ins) ;
#     des variables d'environnement, seuls les NOMS sont imprimés, plus la valeur des OPERATOR_*_PATH
#     (des chemins de publications, jamais des secrets) ;
#   - l'identifiant git (blob SHA-1) de chaque fichier source Python de l'API servie et de chaque fichier
#     du web servi : il permet de retrouver chaque fichier dans l'historique GitHub, ou de prouver qu'il
#     n'y est pas ;
#   - les versions Python et des paquets de l'API ;
#   - pour chaque route GET connue : le code HTTP et, s'il existe, le champ schema/schema_version/error_code.
# Aucun corps de réponse, aucune donnée PAPER, aucun contenu de publication n'est imprimé.
set -uo pipefail
PY=$(command -v python3)
API=http://127.0.0.1:8090
WEB=http://127.0.0.1:8181
exec "$PY" -I - "$API" "$WEB" <<'PYEOF'
import hashlib, json, os, re, subprocess, sys, urllib.request, urllib.error
API, WEB = sys.argv[1], sys.argv[2]
UNITS = ["crypto-operator-api.service", "crypto-operator-web.service",
         "cat-scanner-universe.service", "cat-scanner-universe.timer"]
PROPS = ["Id", "ActiveState", "SubState", "ActiveEnterTimestamp", "ExecStart", "WorkingDirectory",
         "DropInPaths", "FragmentPath", "BindReadOnlyPaths", "Environment"]

def sh(*args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=20).stdout
    except Exception as e:  # noqa: BLE001
        return f"ERROR {type(e).__name__}"

def env_safe(value):
    out = []
    for item in value.split():
        k, _, v = item.partition("=")
        out.append(f"{k}={v}" if re.fullmatch(r"OPERATOR_[A-Z0-9_]*_PATH|CAT_WEB_PORT", k) else k)
    return out

def blob(path):
    data = open(path, "rb").read()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest(), len(data)

def tree(root, keep):
    files = {}
    for d, dirs, names in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in (".venv", "node_modules", "__pycache__", ".git", "logs", "data", "databases"))
        for n in sorted(names):
            p = os.path.join(d, n)
            rel = os.path.relpath(p, root)
            if keep(rel) and os.path.isfile(p) and not os.path.islink(p):
                try:
                    files[rel] = blob(p)
                except OSError as e:
                    files[rel] = ["UNREADABLE", type(e).__name__]
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
            tag = {k: d[k] for k in ("schema", "schema_version", "error_code") if k in d and isinstance(d[k], str)}
    except Exception:  # noqa: BLE001
        pass
    return {"http": code, "tag": tag}

out = {"host": sh("hostname").strip(), "observed_utc": sh("date", "-u", "+%FT%TZ").strip(), "units": {}}
for u in UNITS:
    props = {}
    for line in sh("systemctl", "show", u, "-p", ",".join(PROPS)).splitlines():
        k, _, v = line.partition("=")
        props[k] = env_safe(v) if k == "Environment" else v
    drop = {}
    for p in props.get("DropInPaths", "").split():
        try:
            lines = open(p, encoding="utf-8").read().splitlines()
            drop[p] = [("Environment=" + " ".join(env_safe(x.split("=", 1)[1]))) if x.startswith("Environment=") else x
                       for x in lines]
        except OSError as e:
            drop[p] = ["UNREADABLE", type(e).__name__]
    props["DropIns"] = drop
    out["units"][u] = props

api_wd = out["units"]["crypto-operator-api.service"].get("WorkingDirectory", "")
web_wd = out["units"]["crypto-operator-web.service"].get("WorkingDirectory", "")
out["api_release"] = {"working_directory": api_wd,
                      "files": tree(api_wd, lambda r: r.endswith(".py") and r.split(os.sep)[0] in ("observability", "agent_bench"))
                      if api_wd and os.path.isdir(api_wd) else "NOT_READABLE"}
m = re.search(r"argv\[\]=(\S+)", out["units"]["crypto-operator-api.service"].get("ExecStart", ""))
if m and os.path.exists(m.group(1)):
    code = ("import sys,json\nfrom importlib import metadata as md\n"
            "print(json.dumps({'python':sys.version.split()[0],'packages':{n:md.version(n) for n in "
            "('fastapi','starlette','uvicorn','pydantic','pydantic_core','httpx','anyio') if any(d.metadata['Name'].lower()==n for d in md.distributions())}}))")
    out["api_python"] = sh(m.group(1), "-I", "-c", code).strip()
web_exec = out["units"]["crypto-operator-web.service"].get("ExecStart", "")
srv = re.search(r"argv\[\]=\S+ (\S+\.mjs)", web_exec)
out["web_server_script"] = {"path": srv.group(1), "blob": blob(srv.group(1))} if srv and os.path.exists(srv.group(1)) else None
dist = None
for cand in [os.path.join(web_wd, "dist")] + re.findall(r"(/\S+/dist)\b", " ".join(sum(out["units"]["crypto-operator-web.service"]["DropIns"].values(), []))):
    if cand and os.path.isdir(cand):
        dist = cand
out["web_dist"] = {"path": dist, "files": tree(dist, lambda r: True) if dist else "NOT_FOUND"}

routes = ["/healthz", "/api/operator/v1/snapshot", "/api/operator/v1/portfolio", "/api/operator/v1/decision-pipeline",
          "/api/operator/v1/system-health", "/api/operator/v1/ppl-comparison", "/api/operator/v1/ppl-accounting-history",
          "/api/operator/v1/financial-reconciliation", "/api/operator/v1/market-microstructure",
          "/api/operator/v1/agent-invocations/repository-cartographer", "/api/operator/v1/runtime-service",
          "/api/operator/v1/burn-in", "/api/operator/v1/burn-in/statistics", "/api/operator/v1/market",
          "/api/operator/v1/research-strategies", "/api/operator/v1/research-lab", "/api/operator/v1/venue-comparison",
          "/api/operator/v1/market-flow", "/api/operator/v1/bbo-composite-history", "/api/operator/v1/scanner-universe",
          "/api/operator/v1/storage", "/api/operator/v1/storage-inventory", "/api/operator/v1/lab-experiments",
          "/api/operator/v1/events", "/api/operator/v1/radar-projection", "/api/operator/v1/spot-radar/scanner",
          "/api/operator/v1/intraday/scanner", "/api/operator/v1/signals-indicators", "/api/operator/v1/paper-balance-history"]
out["routes_api"] = {r: get(API + r) for r in routes if not r.startswith("/api/operator/v1/spot-radar")}
out["routes_web"] = {r: get(WEB + r) for r in routes}
out["web_index"] = get(WEB + "/")
print(json.dumps(out, indent=1, sort_keys=True))
PYEOF
