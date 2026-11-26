"""CAT-PREPROD-01 HTTP checks against the isolated preprod servers (loopback only)."""
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request

API, WEB = "http://127.0.0.1:8090", "http://127.0.0.1:18181"
app = open(sys.argv[1]).read()
routes = sorted(set(re.findall(r'@app\.get\("([^"]+)"\)', app)))
def get(url, method="GET"):
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
out = {"routes": []}
for r in routes:
    if "{" in r:
        r = r.replace("{agent_id}", "repository-cartographer")
    s_api, _, b_api = get(API + r)
    s_web, h_web, b_web = get(WEB + r)
    code = None
    try:
        j = json.loads(b_web)
        code = j.get("error_code") if isinstance(j, dict) else None
    except Exception:
        pass
    def strip(b):
        try:
            d = json.loads(b)
        except Exception:
            return b
        def rm(x):
            if isinstance(x, dict):
                return {k: rm(v) for k, v in x.items() if k not in ("served_ms", "age_ms", "served_at", "now_ms")}
            if isinstance(x, list):
                return [rm(v) for v in x]
            return x
        return rm(d)
    out["routes"].append({"route": r, "api": s_api, "web": s_web, "same_bytes": b_api == b_web,
                          "same_except_serving_time": strip(b_api) == strip(b_web),
                          "web_cache_control": h_web.get("cache-control") or h_web.get("Cache-Control"), "error_code": code})
s, h, b = get(WEB + "/api/operator/v1/radar-projection")
d = json.loads(b)
out["radar_projection"] = {"status": s, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(),
    "service": {k: d["service"][k] for k in ("schema", "status", "scope", "publication")},
    "e1": {"relation": d["service"]["catalogue_provenance"]["relation"],
           "markets": [(m["market"], m["relation"]) for m in d["service"]["catalogue_provenance"]["markets"]]},
    "projection_schema": d["projection"]["schema"], "evidence": d["projection"]["evidence"]["kind"],
    "candidates": [(c["rank"], c["market_id"]) for c in d["projection"]["candidates"]],
    "scanner_universe_sha256_in_projection": d["projection"]["scanner_universe"]["sha256"]}
out["post_radar_projection_via_web"] = get(WEB + "/api/operator/v1/radar-projection", "POST")[0]
out["index_html"] = get(WEB + "/")[0]
print(json.dumps(out, indent=1))
