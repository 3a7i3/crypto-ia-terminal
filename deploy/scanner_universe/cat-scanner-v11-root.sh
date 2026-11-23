#!/bin/bash
# Scanner 1.1.0 — actifs par base (devise affichée, jamais confondue) et classe
# crypto / stablecoin / devise. Mise à jour par-dessus le Scanner V1 en service (bc259b23).
# Choix de Mathieu 2026-11-23 08:59Z (« Par actif, devise affichée ») ; GO merge + install 08:48Z.
# Ordre (l'API lit 1.0.0 et 1.1.0, donc elle passe AVANT le producteur) :
#   sudo bash cat-scanner-v11-root.sh api      <sha>   API = version en service + schéma 1.1.0
#   sudo bash cat-scanner-v11-root.sh producer <sha>   producteur sur le checkout <sha>, un passage
#   sudo bash cat-scanner-universe-root.sh web-refonte <sha>   page (Moniteur de marché, actifs)
#   sudo bash cat-scanner-v11-root.sh status   <sha>   lecture seule
#   sudo bash cat-scanner-v11-root.sh rollback <sha>   producteur et API reviennent à bc259b23
#     (page : sudo bash cat-scanner-universe-root.sh web-refonte-revert <sha>)
# Préparation sans root : bash ~/cat-scanner-universe-block/prep-v11.sh <sha> puis prep-refonte.sh <sha>
set -uo pipefail
H=/home/lecanada26
SRC=$H/cat-scanner-universe/src-979b450
B=$H/cat-scanner-universe-block
OUT=/var/lib/cat-scanner-universe
PUB=$OUT/scanner-universe.json
PY=/usr/bin/python3.10
U=/etc/systemd/system/cat-scanner-universe
OLD=bc259b234f41e9515b0cbcffd2a074005a2d055d
API_UNIT=crypto-operator-api
API_BASE=$H/crypto-install/releases/85376c5e-agent-invocation-c823cec1-storage-v1.hiA7Jf-reports.kxGnag-lab-sync.kNQ7rm-dpa-8872f635-market-ea6d077a
API_OLD=$API_BASE-scanner-${OLD:0:8}
API_DROP=/etc/systemd/system/$API_UNIT.service.d/zzzzzzzzzzzzz-scanner-universe.conf
BASE=http://127.0.0.1:8090/api/operator/v1
[ "$(id -u)" = 0 ] || { echo "ECHEC: lancer avec sudo"; exit 1; }
PH=${1:-}; S=${2:-}
case "$PH" in api|producer|status|rollback) ;; *) echo "usage: sudo bash $0 api|producer|status|rollback <sha_code>"; exit 2;; esac
[[ "$S" =~ ^[0-9a-f]{40}$ ]] || { echo "ECHEC: sha de code (40 hex) requis"; exit 2; }
CK=/opt/cat-scanner-universe/checkout/$S
CK_OLD=/opt/cat-scanner-universe/checkout/$OLD
API_NEW=$API_BASE-scanner-${S:0:8}
LOG=$B/scanner-v11-$PH-$(date -u +%Y%m%dT%H%M%SZ).log
exec > >(tee "$LOG") 2>&1
echo "== phase v11 $PH code $S $(date -u +%FT%TZ)"
fail() { echo "ECHEC OBLIGATOIRE: $*"; exit 1; }
ok()   { echo "OK: $*"; }
code() { curl -s -o /dev/null -m 5 -w '%{http_code}' "$@"; }
paper() { sha256sum /run/cat/current/session.json; }
api_ready() { for _ in $(seq 1 30); do [ "$(code $BASE/storage-inventory)" = 200 ] && return 0; sleep 1; done; return 1; }
summary() { curl -s -m 5 $BASE/scanner-universe | $PY -c 'import json,sys,collections; d=json.load(sys.stdin); print("univers :", d.get("schema_version"), d["status"], "· paires", d["pair_count"], "· actifs", d.get("asset_count"), dict(collections.Counter((a["asset_class"], a["market_count"]) for a in d.get("assets", []))))'; }
api_checks() {
  for u in $BASE/storage-inventory $BASE/lab-experiments $BASE/agent-invocations/repository-cartographer $BASE/agent-invocations/data-provenance-auditor $BASE/agent-invocations/market-observer $BASE/scanner-universe; do
    r=$(code $u); echo "$r $u"; [ "$r" = 200 ] || return 1
  done
}

case "$PH" in
api)
  [ -f $API_DROP ] || fail "drop-in API du Scanner V1 absent"
  CURWD=$(systemctl show $API_UNIT -p WorkingDirectory --value)
  [ "$CURWD" = "$API_OLD" ] || [ "$CURWD" = "$API_NEW" ] || fail "l'API tourne sur $CURWD (attendu $API_OLD) : rien n'a été basculé"
  [ -d $B/api-v11 ] || fail "préparation absente (prep-v11.sh)"
  [ -e $API_NEW ] || cp -a $B/api-v11 $API_NEW
  chown -R lecanada26:lecanada26 $API_NEW
  for f in observability/scanner_universe/universe.py observability/scanner_universe/schema.py; do
    runuser -u lecanada26 -- git -C $SRC show $S:$f | cmp -s - $API_NEW/$f || fail "$f != $S"
  done
  runuser -u lecanada26 -- bash -c "cd $API_NEW && $H/crypto-install/releases/85376c5e7725c9fa45f8d05fb0051f25a127aba4/.venv/bin/python -B -c 'import observability.operator_api.app'" || fail "la release ne s'importe pas : rien n'a été basculé"
  P0=$(paper)
  [ -f $B/api-dropin-v1.conf ] || cp -p $API_DROP $B/api-dropin-v1.conf
  printf '[Service]\nWorkingDirectory=%s\nBindReadOnlyPaths=%s\nEnvironment=OPERATOR_SCANNER_UNIVERSE_PATH=%s\n' $API_NEW $API_NEW $PUB > $API_DROP; chmod 0644 $API_DROP
  undo() { cp -p $B/api-dropin-v1.conf $API_DROP; systemctl daemon-reload; systemctl restart $API_UNIT; api_ready; }
  systemctl daemon-reload; systemctl restart $API_UNIT
  api_ready || { undo; fail "API non prête — retour arrière fait"; }
  [ "$(paper)" = "$P0" ] || { undo; fail "session PAPER modifiée — retour arrière fait"; }
  api_checks || { undo; fail "route en échec — retour arrière fait"; }
  summary
  ok "API sur $API_NEW : lit les publications 1.0.0 et 1.1.0. Suite : sudo bash $0 producer $S"
  ;;
producer)
  [ -f $U.service ] || fail "producteur Scanner V1 non installé"
  [ "$(systemctl show $API_UNIT -p WorkingDirectory --value)" = "$API_NEW" ] || fail "phase api non faite : l'API rejetterait une publication 1.1.0"
  if [ -d $CK ] && { [ "$(git -C $CK rev-parse -q --verify HEAD 2>/dev/null)" != $S ] || [ -n "$(git -C $CK status --porcelain 2>/dev/null)" ]; }; then rm -rf $CK; fi
  if [ ! -d $CK ]; then
    runuser -u lecanada26 -- git -C $SRC cat-file -e $S^{commit} || fail "commit $S absent de $SRC (lancer prep-v11.sh)"
    runuser -u lecanada26 -- git -C $SRC update-ref refs/heads/deploy/${S:0:12} $S || fail "référence de déploiement"
    rm -rf $CK.tmp
    GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=$SRC \
      git clone -q --no-hardlinks --no-checkout --branch deploy/${S:0:12} $SRC $CK.tmp || fail "clone checkout"
    git -C $CK.tmp checkout -q --detach $S || fail "checkout $S"
    git -C $CK.tmp remote remove origin
    chown -R root:root $CK.tmp
    find $CK.tmp -type d -exec chmod 0555 {} +
    find $CK.tmp -type f -exec chmod 0444 {} +
    git -C $CK.tmp ls-files -s | awk '$1=="100755"{print $4}' | (cd $CK.tmp && xargs -r chmod 0555)
    mv $CK.tmp $CK || fail "mise en place du checkout"
  fi
  [ "$(git -C $CK rev-parse HEAD)" = $S ] && [ -z "$(git -C $CK status --porcelain)" ] || fail "checkout $CK incorrect"
  FROM=$(sed -n 's|^WorkingDirectory=||p' $U.service)
  [ "$FROM" = "$CK_OLD" ] || [ "$FROM" = "$CK" ] || fail "le producteur tourne sur $FROM (attendu $CK_OLD)"
  [ -f $B/producer-unit-v1.service ] || cp -p $U.service $B/producer-unit-v1.service
  sed -i "s|$FROM|$CK|g" $U.service
  undo() { cp -p $B/producer-unit-v1.service $U.service; systemctl daemon-reload; systemctl start cat-scanner-universe.service; }
  systemctl daemon-reload
  systemctl start cat-scanner-universe.service
  R=$(systemctl show cat-scanner-universe.service -p Result --value)
  journalctl -u cat-scanner-universe.service -n 3 --no-pager -o cat
  [ "$R" = success ] || { undo; fail "passage en échec — producteur remis sur $CK_OLD"; }
  V=$($PY -c 'import json; print(json.load(open("'$PUB'"))["schema_version"])')
  [ "$V" = scanner-universe/1.1.0 ] || { undo; fail "publication $V — producteur remis sur $CK_OLD"; }
  [ "$(code $BASE/scanner-universe)" = 200 ] || { undo; fail "route univers en échec — producteur remis sur $CK_OLD"; }
  summary
  ok "producteur sur $CK (timer inchangé, *:7/15). Suite : sudo bash ~/cat-scanner-universe-block/cat-scanner-universe-root.sh web-refonte $S"
  ;;
status)
  echo "producteur : $(sed -n 's|^WorkingDirectory=||p' $U.service) · $(systemctl show cat-scanner-universe.service -p Result --value)"
  echo "API : $(systemctl show $API_UNIT -p WorkingDirectory --value)"
  echo "web : $(systemctl show crypto-operator-web -p BindReadOnlyPaths --value | cut -d: -f1)"
  [ "$(code $BASE/scanner-universe)" = 200 ] && summary
  ;;
rollback)
  if [ -f $B/producer-unit-v1.service ]; then cp -p $B/producer-unit-v1.service $U.service; systemctl daemon-reload; fi
  systemctl start cat-scanner-universe.service; echo "producteur : $(systemctl show cat-scanner-universe.service -p Result --value)"
  if [ -f $B/api-dropin-v1.conf ]; then cp -p $B/api-dropin-v1.conf $API_DROP; systemctl daemon-reload; systemctl restart $API_UNIT; api_ready && ok "API revenue"; fi
  [ "$(systemctl show $API_UNIT -p WorkingDirectory --value)" = "$API_OLD" ] && ok "API sur $API_OLD"
  [ "$(code $BASE/scanner-universe)" = 200 ] && summary
  echo "Conservés : $CK, $API_NEW. Page : sudo bash ~/cat-scanner-universe-block/cat-scanner-universe-root.sh web-refonte-revert $S"
  ok "producteur et API revenus au Scanner V1 ($OLD)"
  ;;
esac
