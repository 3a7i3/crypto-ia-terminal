#!/bin/bash
# Refonte Marché → Scanner (Moniteur de marché, Radar Spot, Radar de signaux · Démo sur
# fixture SYNTHÉTIQUE, actifs par base) : préparation SANS root du WEB, à partir de la
# source du web Scanner V1 (CAT-SCANNER-UNIVERSE-bc259b23) + les fichiers frontend modifiés.
# Les changements Python éventuels (Scanner 1.1.0) sont préparés par prep-v11.sh.
# Usage (lecanada26) : bash prep-refonte.sh <sha_code_40hex>
# Produit ~/cat-scanner-universe-block/{web-refonte,web-refonte.manifest,web-refonte-tests.log}.
# N'installe rien, ne touche à aucune unité systemd, ne redémarre rien.
set -euo pipefail
C=${1:-}
[[ "$C" =~ ^[0-9a-f]{40}$ ]] || { echo "usage: bash $0 <sha_code_40hex>"; exit 2; }
H=/home/lecanada26
B=$H/cat-scanner-universe-block
SRC=$H/cat-scanner-universe/src-979b450
BRANCH=claude/project-thread-982unz
DEPLOYED=bc259b234f41e9515b0cbcffd2a074005a2d055d
GW=$B/web/frontend                                  # source du web en service (phase web)
WEB_LIVE=/opt/cat-app/releases/CAT-SCANNER-UNIVERSE-${DEPLOYED:0:8}/dist
manifest() { (cd "$1" && find . -type f | sort | xargs sha256sum | sha256sum | cut -d' ' -f1); }
fail() { echo "ECHEC: $*"; exit 1; }
echo "== $(date -u +%FT%TZ) code $C"

git -C $SRC fetch -q --depth=50 origin $BRANCH
git -C $SRC merge-base --is-ancestor $C FETCH_HEAD || fail "$C n'est pas sur $BRANCH"
git -C $SRC merge-base --is-ancestor $DEPLOYED $C || fail "$DEPLOYED n'est pas un ancêtre de $C"
OTHER=$(git -C $SRC diff --name-only $DEPLOYED $C -- . ':!frontend' ':!deploy' ':!docs' ':!tests/scanner_universe' ':!observability/scanner_universe/universe.py' ':!observability/scanner_universe/schema.py')
[ -z "$OTHER" ] || fail "changements hors périmètre : $OTHER"
[ "$(manifest $GW/dist)" = "$(manifest $WEB_LIVE)" ] || fail "source web de référence != dist servi"
CHANGES=$(git -C $SRC diff --name-status $DEPLOYED $C -- frontend/src | tr '\t' ':')
for x in $CHANGES; do st=${x%%:*}; f=${x#*:}; r=${f#frontend/}
  case $st in
    A) [ ! -e $GW/$r ] || fail "$r existe déjà dans le web en service" ;;
    M|D) git -C $SRC show $DEPLOYED:$f | cmp -s - $GW/$r || fail "$r diffère de la version en service" ;;
    *) fail "changement non pris en charge : $x" ;;
  esac
done
echo "OK: $(echo $CHANGES | wc -w) fichiers, tous identiques à la version en service ou nouveaux"

rm -rf $B/web-refonte && mkdir -p $B/web-refonte && cp -a $GW $B/web-refonte/frontend
cd $B/web-refonte/frontend
for x in $CHANGES; do st=${x%%:*}; f=${x#*:}; r=${f#frontend/}
  if [ $st = D ]; then rm -f $r; else mkdir -p $(dirname $r); git -C $SRC show $C:$f > $r; fi
done
npx vitest run src/test/ScannerUniverse.test.tsx src/test/SignalsRadar.test.tsx src/test/MarketMonitor.test.tsx src/test/MarketNavigation.test.tsx src/test/SymbolScanner.test.tsx src/test/SpotRadarMap.test.tsx src/test/App.test.tsx src/test/UnifiedLanding.test.tsx src/test/AppRouting.test.tsx src/test/MarketMicrostructureView.test.tsx > $B/web-refonte-tests.log 2>&1 || { grep -E "Test Files|Tests |×|FAIL" $B/web-refonte-tests.log | head -20; fail "tests web"; }
grep -E "Test Files|Tests " $B/web-refonte-tests.log
npx tsc --noEmit -p . || fail "TypeScript"
rm -rf dist && VITE_CARTOGRAPHER_INVOCATION=1 npm run build > $B/web-refonte-build.log 2>&1 || { tail -20 $B/web-refonte-build.log; fail "build"; }
A=$(sed -n 's/.*src="\(\/assets\/[^"]*\.js\)".*/\1/p' dist/index.html)
for s in /api/operator/v1/scanner-universe /api/operator/v1/storage-inventory data-provenance-auditor market-observer "Radar de signaux" "Moniteur de marché" "Programmateur de lecture"; do grep -qF "$s" dist$A || fail "« $s » absent du bundle"; done
grep -qF "signals-indicators" dist$A && fail "le bundle appelle une route de signaux (attendu : démo seulement)"
manifest dist > $B/web-refonte.manifest
echo "OK: web refonte construit, manifeste $(cat $B/web-refonte.manifest)"
echo "== prêt : sudo bash ~/cat-scanner-universe-block/cat-scanner-universe-root.sh web-refonte $C"
