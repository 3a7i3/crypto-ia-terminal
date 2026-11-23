#!/bin/bash
# Scanner V1 — univers commun MEXC × Kraken (Spot × Perpétuel). Mise en service sur crypto-restore-01.
# Choix de Mathieu 2026-11-23 03:12Z (« Mise en service sur le VPS ») ; chaque phase attend son GO.
# Producteur : compte système cat-scanner-universe, checkout de code immuable, 5 GET publics
# toutes les 15 min vers api.mexc.com, contract.mexc.com, api.kraken.com, futures.kraken.com.
# Aucune clé, aucune écriture exchange, aucun accès PPL, FIN, PAPER, JSONL ni scanner D1-RC1.
# Données : /var/lib/cat-scanner-universe seulement (disque du VPS), 24 relevés bruts conservés.
#
# Phases, dans l'ordre (une à la fois) :
#   sudo bash cat-scanner-universe-root.sh install  <sha>   compte, checkout, dossier, unités (timer NON activé)
#   sudo bash cat-scanner-universe-root.sh invoke   <sha>   un passage ; active le timer s'il réussit
#   sudo bash cat-scanner-universe-root.sh api      <sha>   API = version en service + route scanner-universe
#   sudo bash cat-scanner-universe-root.sh web      <sha>   page = version en service + univers dans Marché → Scanner
#   sudo bash cat-scanner-universe-root.sh status   <sha>   lecture seule
#   sudo bash cat-scanner-universe-root.sh rollback <sha>   retour à l'API et au web du bloc Market
# Préparation sans root : bash ~/cat-scanner-universe-block/prep.sh <sha>
set -uo pipefail
H=/home/lecanada26
SRC=$H/cat-scanner-universe/src-979b450
B=$H/cat-scanner-universe-block
SVC_USER=cat-scanner-universe
OUT=/var/lib/cat-scanner-universe
PUB=$OUT/scanner-universe.json
PY=/usr/bin/python3.10
U=/etc/systemd/system/cat-scanner-universe
API_UNIT=crypto-operator-api
WEB_UNIT=crypto-operator-web
API_PREV=$H/crypto-install/releases/85376c5e-agent-invocation-c823cec1-storage-v1.hiA7Jf-reports.kxGnag-lab-sync.kNQ7rm-dpa-8872f635-market-ea6d077a
API_DROP=/etc/systemd/system/$API_UNIT.service.d/zzzzzzzzzzzzz-scanner-universe.conf
WEB_PREV=/opt/cat-app/releases/CAT-AGENTS-MARKET-ea6d077a
WEB_TARGET=/opt/cat-app/releases/CAT-FOOTPRINT-FINANCE-V6-RC1/frontend
WEB_SRV=/opt/cat-app/releases/CAT-SYSTEM-AGENTS-599-891e1865/server/web01_local_frontend_server.mjs
WEB_DROP=/etc/systemd/system/$WEB_UNIT.service.d/zzzzzzzzzzzzzzzzzzzzzzz-zzzzz-scanner-universe.conf
BASE=http://127.0.0.1:8090/api/operator/v1
WEB=http://127.0.0.1:8181
[ "$(id -u)" = 0 ] || { echo "ECHEC: lancer avec sudo"; exit 1; }
PH=${1:-}; S=${2:-}
case "$PH" in install|invoke|api|web|status|rollback) ;; *) echo "usage: sudo bash $0 install|invoke|api|web|status|rollback <sha_code>"; exit 2;; esac
[[ "$S" =~ ^[0-9a-f]{40}$ ]] || { echo "ECHEC: sha de code (40 hex) requis"; exit 2; }
CK=/opt/cat-scanner-universe/checkout/$S
API_NEW=$API_PREV-scanner-${S:0:8}
WEB_NEW=/opt/cat-app/releases/CAT-SCANNER-UNIVERSE-${S:0:8}
mkdir -p $B
LOG=$B/scanner-$PH-$(date -u +%Y%m%dT%H%M%SZ).log
exec > >(tee "$LOG") 2>&1
echo "== phase $PH code $S $(date -u +%FT%TZ)"
fail() { echo "ECHEC OBLIGATOIRE: $*"; exit 1; }
ok()   { echo "OK: $*"; }
code() { curl -s -o /dev/null -m 5 -w '%{http_code}' "$@"; }
paper() { sha256sum /run/cat/current/session.json; }
api_ready() { for _ in $(seq 1 30); do [ "$(code $BASE/storage-inventory)" = 200 ] && return 0; sleep 1; done; return 1; }
summary() { curl -s -m 5 "$1" | $PY -c 'import json,sys; d=json.load(sys.stdin); print("univers :", d["status"], "· paires", d["pair_count"], "· blocages", d["blocking_sources"], "· calcul", d["computed_ms"])'; }

case "$PH" in
install)
  [ -x $PY ] || fail "$PY absent"
  [ ! -e $U.service ] && [ ! -e $U.timer ] || fail "unités déjà présentes"
  id $SVC_USER >/dev/null 2>&1 || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin $SVC_USER || fail "création du compte $SVC_USER"
  if [ ! -d $CK ]; then
    runuser -u lecanada26 -- git -C $SRC cat-file -e $S^{commit} || fail "commit $S absent de $SRC (lancer prep.sh)"
    install -d -m 0755 /opt/cat-scanner-universe/checkout
    GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=$SRC \
      git clone -q --no-hardlinks --no-checkout $SRC $CK || fail "clone checkout"
    git -C $CK checkout -q --detach $S || fail "checkout $S"
    git -C $CK remote remove origin
    chown -R root:root $CK
    find $CK -type d -exec chmod 0555 {} +
    find $CK -type f -exec chmod 0444 {} +
  fi
  [ "$(git -C $CK rev-parse HEAD)" = $S ] || fail "checkout != $S"
  [ -z "$(git -C $CK status --porcelain)" ] || fail "checkout modifié"
  ok "checkout de code $CK"
  [ -L $OUT ] && fail "$OUT est un lien"
  install -d -o $SVC_USER -g $SVC_USER -m 0755 $OUT || fail "création $OUT"
  cat > $U.service <<UNIT
[Unit]
Description=Scanner V1 - univers commun MEXC x Kraken (lecture des 4 catalogues publics)
Documentation=file://$CK/docs/contracts/SCANNER_UNIVERSE_V1.md
[Service]
Type=oneshot
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$CK
Environment=PYTHONDONTWRITEBYTECODE=1 HOME=/nonexistent LC_ALL=C.UTF-8 TZ=UTC
UMask=0022
ExecStart=$PY -B -s -E -m observability.scanner_universe.collect --out-dir $OUT --keep-runs 24
# Réseau : HTTPS public seulement. Boucle locale (sauf le résolveur DNS 127.0.0.53),
# réseaux privés et serveur de métadonnées refusés : ni API opérateur, ni scanner, ni PAPER.
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
IPAddressAllow=127.0.0.53/32
IPAddressDeny=127.0.0.0/8 ::1/128 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 100.64.0.0/10 fc00::/7 fe80::/10
ProtectSystem=strict
ReadWritePaths=$OUT
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectProc=invisible
NoNewPrivileges=yes
CapabilityBoundingSet=
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
MemoryMax=512M
TasksMax=16
CPUQuota=50%
TimeoutStartSec=180
UNIT
  cat > $U.timer <<UNIT
[Unit]
Description=Scanner V1 - univers commun, toutes les 15 minutes (:07, :22, :37, :52)
[Timer]
OnCalendar=*:7/15
Persistent=false
AccuracySec=1s
[Install]
WantedBy=timers.target
UNIT
  chmod 0644 $U.service $U.timer
  systemctl daemon-reload
  systemd-analyze verify $U.service $U.timer 2>&1 | grep -v -e '^$' -e snapd | head -5
  ok "unités installées, timer NON activé. Suite : sudo bash $0 invoke $S"
  ;;
invoke)
  [ -e $U.service ] || fail "phase install non faite"
  systemctl start cat-scanner-universe.service
  R=$(systemctl show cat-scanner-universe.service -p Result --value)
  echo "premier passage : $R"
  journalctl -u cat-scanner-universe.service -n 4 --no-pager -o cat
  [ "$R" = success ] || fail "premier passage en échec (UNVERIFIABLE ou erreur) : timer laissé inactif"
  [ "$(stat -c '%a %U' $PUB)" = "644 $SVC_USER" ] || fail "publication : droits inattendus"
  runuser -u lecanada26 -- test -r $PUB || fail "publication illisible par lecanada26 (compte de l'API)"
  systemctl enable --now cat-scanner-universe.timer
  systemctl list-timers cat-scanner-universe.timer --no-pager | head -2
  ok "producteur actif : un relevé toutes les 15 minutes"
  ;;
api)
  [ -f $PUB ] || fail "phase invoke non faite (publication absente)"
  [ "$(systemctl show $API_UNIT -p WorkingDirectory --value)" = "$API_PREV" ] || fail "l'API ne tourne plus sur la version attendue : rien n'a été basculé"
  [ -e "$API_DROP" ] && fail "drop-in déjà présent"
  [ -d $B/api ] || fail "préparation absente (prep.sh)"
  [ -e $API_NEW ] || cp -a $B/api $API_NEW
  chown -R lecanada26:lecanada26 $API_NEW
  runuser -u lecanada26 -- bash -c "cd $API_NEW && $H/crypto-install/releases/85376c5e7725c9fa45f8d05fb0051f25a127aba4/.venv/bin/python -B -c 'import observability.operator_api.app'" \
    || fail "la release ne s'importe pas : rien n'a été basculé"
  P0=$(paper)
  printf '[Service]\nWorkingDirectory=%s\nBindReadOnlyPaths=%s\nEnvironment=OPERATOR_SCANNER_UNIVERSE_PATH=%s\n' $API_NEW $API_NEW $PUB > $API_DROP; chmod 0644 $API_DROP
  undo() { rm -f $API_DROP; systemctl daemon-reload; systemctl restart $API_UNIT; api_ready; }
  systemctl daemon-reload; systemctl restart $API_UNIT
  api_ready || { undo; fail "API non prête — retour arrière fait"; }
  [ "$(paper)" = "$P0" ] || { undo; fail "session PAPER modifiée — retour arrière fait"; }
  for u in $BASE/storage-inventory $BASE/lab-experiments $BASE/agent-invocations/repository-cartographer $BASE/agent-invocations/data-provenance-auditor $BASE/agent-invocations/market-observer $BASE/scanner-universe; do
    r=$(code $u); echo "$r $u"; [ "$r" = 200 ] || { undo; fail "$u — retour arrière fait"; }
  done
  summary $BASE/scanner-universe
  ok "API sur $API_NEW (stockage, labo, agents conservés), session PAPER identique"
  ;;
web)
  [ -e "$WEB_DROP" ] && fail "drop-in web déjà présent"
  CUR=$(systemctl show $WEB_UNIT -p BindReadOnlyPaths --value)
  [[ "$CUR" == "$WEB_PREV/dist:$WEB_TARGET/dist:rbind "* ]] || fail "le web ne sert plus $WEB_PREV : rien n'a été basculé"
  [ "$(code $BASE/scanner-universe)" = 200 ] || fail "phase api non faite"
  manifest() { (cd "$1" && find . -type f | sort | xargs sha256sum | sha256sum | cut -d' ' -f1); }
  [ "$(manifest $B/web/frontend/dist)" = "$(cat $B/web.manifest)" ] || fail "dist != manifeste"
  if [ ! -d $WEB_NEW/dist ]; then install -d -m 0755 $WEB_NEW && cp -r $B/web/frontend/dist $WEB_NEW/dist; fi
  chown -R root:root $WEB_NEW; chmod -R a+rX $WEB_NEW
  [ "$(manifest $WEB_NEW/dist)" = "$(cat $B/web.manifest)" ] || fail "copie du dist"
  printf '[Service]\nBindReadOnlyPaths=\nBindReadOnlyPaths=%s/dist:%s/dist %s:%s/scripts/web01_local_frontend_server.mjs\n' $WEB_NEW $WEB_TARGET $WEB_SRV $WEB_TARGET > $WEB_DROP
  chmod 0644 $WEB_DROP
  undo() { rm -f $WEB_DROP; systemctl daemon-reload; systemctl restart $WEB_UNIT; }
  systemctl daemon-reload && systemctl restart $WEB_UNIT
  A=$(sed -n 's/.*src="\(\/assets\/[^"]*\.js\)".*/\1/p' $WEB_NEW/dist/index.html)
  curl -fsS --retry 8 --retry-connrefused --retry-delay 1 -m 5 $WEB/paper-live/system 2>/dev/null | cmp - $WEB_NEW/dist/index.html || { undo; fail "page servie != build — retour arrière fait"; }
  curl -fsS -m 5 $WEB$A | cmp - $WEB_NEW/dist$A || { undo; fail "bundle servi != build — retour arrière fait"; }
  r=$(code $WEB/api/operator/v1/scanner-universe); echo "via web : univers $r · Market $(code $WEB/api/operator/v1/agent-invocations/market-observer) · stockage $(code $WEB/api/operator/v1/storage-inventory)"
  [ "$r" = 200 ] || { undo; fail "relais web — retour arrière fait"; }
  ok "web sur $WEB_NEW : Marché → Scanner n'affiche que l'univers commun (recharger la page)"
  ;;
status)
  systemctl list-timers cat-scanner-universe.timer --no-pager | head -2
  systemctl show cat-scanner-universe.service -p Result -p ExecMainStatus --value | paste -sd' '
  ls $OUT/runs 2>/dev/null | tail -3; du -sh $OUT 2>/dev/null
  echo "API $(code $BASE/scanner-universe) · web $(code $WEB/api/operator/v1/scanner-universe)"
  [ "$(code $BASE/scanner-universe)" = 200 ] && summary $BASE/scanner-universe
  ;;
rollback)
  rm -f $WEB_DROP $API_DROP
  systemctl disable --now cat-scanner-universe.timer 2>/dev/null
  systemctl stop cat-scanner-universe.service 2>/dev/null
  rm -f $U.service $U.timer
  systemctl daemon-reload; systemctl restart $API_UNIT $WEB_UNIT; api_ready && ok "API revenue"
  [ "$(systemctl show $API_UNIT -p WorkingDirectory --value)" = "$API_PREV" ] && ok "API sur $API_PREV"
  echo "Conservés : $OUT (relevés), le checkout $CK, le compte $SVC_USER, les releases $API_NEW et $WEB_NEW."
  ok "retour à API $API_PREV et web $WEB_PREV ; producteur arrêté"
  ;;
esac
