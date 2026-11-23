#!/bin/bash
# Scanner 1.1.0 (actifs par base, classe crypto/stablecoin/devise) : préparation SANS root de
# l'API et du producteur, par-dessus les versions en service (API …-scanner-bc259b23).
# Le web se prépare avec prep-refonte.sh <même sha>.
# Usage (lecanada26) : bash prep-v11.sh <sha_code_40hex>
# Produit ~/cat-scanner-universe-block/{api-v11,v11-dryrun.json,prep-v11.log}. N'installe rien.
set -euo pipefail
C=${1:-}
[[ "$C" =~ ^[0-9a-f]{40}$ ]] || { echo "usage: bash $0 <sha_code_40hex>"; exit 2; }
H=/home/lecanada26
B=$H/cat-scanner-universe-block
SRC=$H/cat-scanner-universe/src-979b450
BRANCH=claude/project-thread-982unz
DEPLOYED=bc259b234f41e9515b0cbcffd2a074005a2d055d
API_CUR=$H/crypto-install/releases/85376c5e-agent-invocation-c823cec1-storage-v1.hiA7Jf-reports.kxGnag-lab-sync.kNQ7rm-dpa-8872f635-market-ea6d077a-scanner-${DEPLOYED:0:8}
VENV=$H/crypto-install/releases/85376c5e7725c9fa45f8d05fb0051f25a127aba4/.venv/bin/python
PY310=/usr/bin/python3.10
PUB=/var/lib/cat-scanner-universe/scanner-universe.json
FILES="observability/scanner_universe/universe.py observability/scanner_universe/schema.py"
fail() { echo "ECHEC: $*"; exit 1; }
echo "== $(date -u +%FT%TZ) code $C"
git -C $SRC fetch -q --depth=60 origin $BRANCH
git -C $SRC merge-base --is-ancestor $C FETCH_HEAD || fail "$C n'est pas sur $BRANCH"
git -C $SRC merge-base --is-ancestor $DEPLOYED $C || fail "$DEPLOYED n'est pas un ancêtre de $C"
CHANGED=$(git -C $SRC diff --name-only $DEPLOYED $C -- observability | sort | tr '\n' ' ')
[ "$CHANGED" = "$(echo $FILES | tr ' ' '\n' | sort | tr '\n' ' ')" ] || fail "fichiers Python modifiés inattendus : $CHANGED"
[ "$(systemctl show crypto-operator-api -p WorkingDirectory --value)" = "$API_CUR" ] || fail "l'API ne tourne pas sur $API_CUR"
for f in $FILES; do git -C $SRC show $DEPLOYED:$f | cmp -s - $API_CUR/$f || fail "$f diffère de l'API en service"; done
echo "OK: API en service = $DEPLOYED pour les deux fichiers remplacés"

rm -rf $B/api-v11 && cp -a $API_CUR $B/api-v11
for f in $FILES; do git -C $SRC show $C:$f > $B/api-v11/$f; done
(cd $B/api-v11 && $VENV -B -c 'import observability.operator_api.app') || fail "API non importable"
echo "OK: API 1.1.0 importable"

# Producteur 1.1.0 rejoué sur le dernier relevé réel (lecture seule de /var/lib), puis lu par la nouvelle API.
rm -rf $B/src-v11 && mkdir -p $B/src-v11 && git -C $SRC archive $C observability tests/__init__.py tests/scanner_universe | tar -x -C $B/src-v11
RUN=$(ls -d /var/lib/cat-scanner-universe/runs/* | tail -1)
(cd $B/src-v11 && $PY310 -B -s -E -m observability.scanner_universe.collect --replay $RUN) > $B/v11-dryrun.json
(cd $B/src-v11 && $PY310 -B -m unittest -q tests.scanner_universe.test_assets tests.scanner_universe.test_universe 2>&1 | tail -2)
cd $B/api-v11
for doc in $PUB $B/v11-dryrun.json; do
  OPERATOR_SCANNER_UNIVERSE_PATH=$doc $VENV -B -c '
import collections, os
from fastapi.testclient import TestClient
from observability.operator_api import app as api
from observability.scanner_universe.schema import validate_publication
from observability.scanner_universe.universe import requalify
import json
raw = json.load(open(os.environ["OPERATOR_SCANNER_UNIVERSE_PATH"]))
print(os.path.basename(os.environ["OPERATOR_SCANNER_UNIVERSE_PATH"]), raw["schema_version"], "validation", validate_publication(raw) or "OK")
r = TestClient(api.app).get("/api/operator/v1/scanner-universe"); d = r.json()
print("  route", r.status_code, d.get("status"), "paires", d.get("pair_count"), "actifs", d.get("asset_count"),
      dict(collections.Counter((a["asset_class"], a["market_count"]) for a in d.get("assets", []))))'
done
echo "== prêt : sudo bash ~/cat-scanner-universe-block/cat-scanner-v11-root.sh api $C"
