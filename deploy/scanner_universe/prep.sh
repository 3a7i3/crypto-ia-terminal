#!/bin/bash
# Scanner V1 (univers commun MEXC × Kraken) : préparation SANS root, par-dessus les
# versions en service (bloc Market Observer, API …-market-ea6d077a, web CAT-AGENTS-MARKET-ea6d077a).
# Usage (lecanada26) : bash prep.sh <sha_code_40hex>
# Produit ~/cat-scanner-universe-block/{api,web,web.manifest,tests.log,producer-dryrun}.
# N'installe rien, ne touche à aucune unité systemd, ne redémarre rien.
set -euo pipefail
C=${1:-}
[[ "$C" =~ ^[0-9a-f]{40}$ ]] || { echo "usage: bash $0 <sha_code_40hex>"; exit 2; }
H=/home/lecanada26
B=$H/cat-scanner-universe-block
SRC=$H/cat-scanner-universe/src-979b450
BRANCH=claude/project-thread-982unz
BASE=766f4fd7d8a797a684c5b89de9fd0e83bc8b74b3   # main sur lequel la PR #602 est construite
GW=$H/cat-market-block/web/frontend              # source web en service (bloc Market)
GA=$H/crypto-install/releases/85376c5e-agent-invocation-c823cec1-storage-v1.hiA7Jf-reports.kxGnag-lab-sync.kNQ7rm-dpa-8872f635-market-ea6d077a
WEB_LIVE=/opt/cat-app/releases/CAT-AGENTS-MARKET-ea6d077a/dist
VENV=$H/crypto-install/releases/85376c5e7725c9fa45f8d05fb0051f25a127aba4/.venv/bin/python
PY310=/usr/bin/python3.10
FE_REPLACE="src/views/MarketView.tsx src/views/SymbolScanner.tsx src/views/SpotRadarMap.tsx src/views/BboCompositeHistory.tsx src/test/App.test.tsx src/test/AppRouting.test.tsx src/test/MarketMicrostructureView.test.tsx src/test/MarketNavigation.test.tsx"
FE_NEW="src/lib/scannerUniverseClient.ts src/views/ScannerUniverse.tsx src/views/scanner-universe.css src/test/ScannerUniverse.test.tsx src/test/scannerUniverseFixtures.ts"
PY_NEW="observability/scanner_universe/__init__.py observability/scanner_universe/catalogues.py observability/scanner_universe/collect.py observability/scanner_universe/schema.py observability/scanner_universe/universe.py observability/operator_api/scanner_universe_reader.py"
manifest() { (cd "$1" && find . -type f | sort | xargs sha256sum | sha256sum | cut -d' ' -f1); }
fail() { echo "ECHEC: $*"; exit 1; }
echo "== $(date -u +%FT%TZ) code $C"

git -C $SRC fetch -q --depth=20 origin $BRANCH
git -C $SRC merge-base --is-ancestor $C FETCH_HEAD || fail "$C n'est pas sur $BRANCH"
git -C $SRC merge-base --is-ancestor $BASE $C || fail "$BASE n'est pas un ancêtre de $C"
for f in $FE_REPLACE; do
  git -C $SRC show $BASE:frontend/$f | cmp -s - $GW/$f || fail "$f diffère de la version web en service"
done
for f in $FE_NEW; do [ ! -e $GW/$f ] || fail "$f existe déjà dans le web en service"; done
for f in $PY_NEW; do [ ! -e $GA/$f ] || fail "$f existe déjà dans l'API en service"; done
grep -q scanner_universe $GA/observability/operator_api/app.py && fail "app.py en service mentionne déjà scanner_universe"
[ "$(manifest $GW/dist)" = "$(manifest $WEB_LIVE)" ] || fail "source web de référence != dist servi"
echo "OK: fichiers remplacés identiques aux versions en service, nouveaux fichiers absents"

rm -rf $B/web && mkdir -p $B/web && cp -a $GW $B/web/frontend
cd $B/web/frontend
# Témoin : la source en service, reconstruite telle quelle, redonne le dist servi.
rm -rf dist && VITE_CARTOGRAPHER_INVOCATION=1 npm run build > $B/web-build-control.log 2>&1 || { tail -20 $B/web-build-control.log; fail "build témoin"; }
[ "$(manifest dist)" = "$(manifest $WEB_LIVE)" ] || fail "build témoin non reproductible (dist != dist servi)"
echo "OK: build témoin identique au dist servi"
for f in $FE_REPLACE $FE_NEW; do git -C $SRC show $C:frontend/$f > $f; done
npx vitest run src/test/ScannerUniverse.test.tsx src/test/App.test.tsx src/test/AppRouting.test.tsx src/test/MarketNavigation.test.tsx src/test/MarketMicrostructureView.test.tsx > $B/web-tests.log 2>&1 || { grep -E "Test Files|Tests |×|FAIL" $B/web-tests.log | head -20; fail "tests web"; }
grep -E "Test Files|Tests " $B/web-tests.log
rm -rf dist && VITE_CARTOGRAPHER_INVOCATION=1 npm run build > $B/web-build.log 2>&1 || { tail -20 $B/web-build.log; fail "build"; }
A=$(sed -n 's/.*src="\(\/assets\/[^"]*\.js\)".*/\1/p' dist/index.html)
for s in /api/operator/v1/scanner-universe /api/operator/v1/storage-inventory data-provenance-auditor market-observer; do grep -qF "$s" dist$A || fail "$s absent du bundle"; done
manifest dist > $B/web.manifest
echo "OK: web construit, manifeste $(cat $B/web.manifest)"

rm -rf $B/api && mkdir -p $B/api && cp -a $GA/. $B/api/
for f in $PY_NEW; do mkdir -p $B/api/$(dirname $f); git -C $SRC show $C:$f > $B/api/$f; done
git -C $SRC show $C:observability/operator_api/app.py > $B/app.py.pr
$PY310 -I - $B/api/observability/operator_api/app.py $B/app.py.pr <<'PYEOF'
import sys
live, pr = sys.argv[1], sys.argv[2]
src = open(live, encoding="utf-8").read()
pr_src = open(pr, encoding="utf-8").read()
anchor = "from observability.operator_api.market_flow_reader import MarketFlowReader\n"
imp = "from observability.operator_api.scanner_universe_reader import ScannerUniverseReader\n"
assert src.count(anchor) == 1 and imp in pr_src and imp not in src, "ancre d'import"
block = pr_src[pr_src.index("\n\n# SCANNER-V1"):]
assert block.rstrip().endswith('headers={"Cache-Control": "no-store"})'), "bloc de route"
src = src.replace(anchor, anchor + imp)
open(live, "w", encoding="utf-8").write(src.rstrip("\n") + "\n" + block.rstrip("\n") + "\n")
PYEOF
diff $GA/observability/operator_api/app.py $B/api/observability/operator_api/app.py | grep -q '^<' && fail "app.py : une ligne en service serait modifiée"
echo "OK: app.py = version en service + $(diff $GA/observability/operator_api/app.py $B/api/observability/operator_api/app.py | grep -c '^>') lignes ajoutées"
(cd $B/api && $VENV -B -c 'import observability.operator_api.app') || fail "API non importable"
echo "OK: API importable"

rm -rf $B/src && mkdir -p $B/src && git -C $SRC archive $C observability agent_bench tests/__init__.py tests/scanner_universe | tar -x -C $B/src
(cd $B/src && $VENV -B -m pytest -q -p no:cacheprovider tests/scanner_universe) > $B/tests.log 2>&1 || { tail -20 $B/tests.log; fail "tests Python"; }
tail -1 $B/tests.log

# Passage à blanc du producteur (5 GET publics), avec l'interpréteur du futur service.
rm -rf $B/producer-dryrun
(cd $B/src && $PY310 -B -s -E -m observability.scanner_universe.collect --out-dir $B/producer-dryrun --keep-runs 2) || echo "producteur : code de sortie $? (2 = UNVERIFIABLE)"
[ "$(stat -c %a $B/producer-dryrun/scanner-universe.json)" = 644 ] || fail "publication non lisible (mode)"
cd $B/api && OPERATOR_SCANNER_UNIVERSE_PATH=$B/producer-dryrun/scanner-universe.json $VENV -B -c '
from fastapi.testclient import TestClient
from observability.operator_api import app as api
c = TestClient(api.app)
r = c.get("/api/operator/v1/scanner-universe"); d = r.json()
print("route", r.status_code, d.get("status"), "paires", d.get("pair_count"), [(s["market"], s["admissible"]) for s in d.get("sources", [])])
assert r.status_code == 200
for u in ("/api/operator/v1/storage-inventory", "/api/operator/v1/agent-invocations/market-observer"):
    print("témoin", u, c.get(u).status_code)'
echo "== prêt : sudo bash cat-scanner-universe-root.sh install $C"
