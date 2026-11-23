#!/bin/bash
# Observateur Marché (décision Mathieu 2026-11-23 01:39Z) : premier agent de la famille Observation
# qui observe les DONNÉES du VPS. Lecture GET seulement vers 127.0.0.1 (scanner 18906, API 8090).
# Compte cat-obs-ro, checkout de code immuable, aucune écriture hors de son dossier, aucun accès
# exchange, PPL, FIN ni fichier JSONL. N'agit pas sur PAPER, le scanner ni le collecteur.
#
# Phases, dans l'ordre (une à la fois) :
#   sudo bash cat-obs-market-root.sh install <sha>   checkout, dossier, unités (timer NON activé)
#   sudo bash cat-obs-market-root.sh invoke  <sha>   un passage ; active le timer s'il réussit
#   sudo bash cat-obs-market-root.sh control <sha>   programmateur ⏰ (rythme initial 10 min, :03)
#   sudo bash cat-obs-market-root.sh api     <sha>   API = version en service + fichiers des agents
#   sudo bash cat-obs-market-root.sh web     <sha>   page = version en service + bloc Market Observer
#   sudo bash cat-obs-market-root.sh rollback <sha>
# Préparation sans root (build web/API par-dessus les versions en service) : ~/cat-market-block/prep.sh
set -uo pipefail
H=/home/lecanada26
P=$H/cat-obs-pilot
SRC=$P/src
B=$H/cat-market-block
FAM=/srv/cat-obs/agent-reports
OBSD=$FAM/observation
AGENT=market-observer
D=$OBSD/$AGENT
PY=/usr/bin/python3.10
U=/etc/systemd/system/cat-obs-market
RUNNER=obs-market-ro-01
MISSION=docs/agents/observation/examples/market_observer_mission.json
C=/srv/cat-obs/control
APPLY=/usr/local/sbin/cat-obs-schedule-apply
API_UNIT=crypto-operator-api
WEB_UNIT=crypto-operator-web
API_PREV=$H/crypto-install/releases/85376c5e-agent-invocation-c823cec1-storage-v1.hiA7Jf-reports.kxGnag-lab-sync.kNQ7rm-dpa-8872f635
API_DROP=/etc/systemd/system/$API_UNIT.service.d/zzzzzzzzzzzz-market-block.conf
WEB_PREV=/opt/cat-app/releases/CAT-AGENTS-DPA-8872f635
WEB_TARGET=/opt/cat-app/releases/CAT-FOOTPRINT-FINANCE-V6-RC1/frontend
WEB_SRV=/opt/cat-app/releases/CAT-SYSTEM-AGENTS-599-891e1865/server/web01_local_frontend_server.mjs
WEB_DROP=/etc/systemd/system/$WEB_UNIT.service.d/zzzzzzzzzzzzzzzzzzzzzzz-zzzz-market-block.conf
BASE=http://127.0.0.1:8090/api/operator/v1
WEB=http://127.0.0.1:8181
AG=$BASE/agent-invocations/$AGENT
[ "$(id -u)" = 0 ] || { echo "ECHEC: lancer avec sudo"; exit 1; }
PH=${1:-}; S=${2:-}
case "$PH" in install|invoke|control|api|web|rollback) ;; *) echo "usage: sudo bash $0 install|invoke|control|api|web|rollback <sha_code>"; exit 2;; esac
[[ "$S" =~ ^[0-9a-f]{40}$ ]] || { echo "ECHEC: sha de code (40 hex) requis"; exit 2; }
CK=/srv/cat-obs/checkout/$S
API_NEW=$API_PREV-market-${S:0:8}
WEB_NEW=/opt/cat-app/releases/CAT-AGENTS-MARKET-${S:0:8}
mkdir -p $B
LOG=$B/market-$PH-$(date -u +%Y%m%dT%H%M%SZ).log
exec > >(tee "$LOG") 2>&1
echo "== phase $PH code $S $(date -u +%FT%TZ)"
fail() { echo "ECHEC OBLIGATOIRE: $*"; exit 1; }
ok()   { echo "OK: $*"; }
asro() { runuser -u cat-obs-ro -- env -i PATH=/usr/bin:/bin HOME=/nonexistent LC_ALL=C PYTHONDONTWRITEBYTECODE=1 "$@"; }
code() { curl -s -o /dev/null -m 5 -w '%{http_code}' "$@"; }
paper() { sha256sum /run/cat/current/session.json; }
api_ready() { for _ in $(seq 1 30); do [ "$(code $BASE/storage-inventory)" = 200 ] && return 0; sleep 1; done; return 1; }

case "$PH" in
install)
  id cat-obs-ro >/dev/null 2>&1 || fail "compte cat-obs-ro absent"
  [ -x $PY ] || fail "$PY absent"
  [ -x /usr/local/sbin/cat-obs-prune ] || fail "cat-obs-prune absent"
  [ ! -e $U.service ] && [ ! -e $U.timer ] || fail "unités déjà présentes"
  if [ ! -d $CK ]; then
    runuser -u lecanada26 -- git -C $SRC cat-file -e $S^{commit} || fail "commit $S absent de $SRC (git fetch)"
    GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=$SRC \
      git clone -q --no-hardlinks $SRC $CK || fail "clone checkout"
    git -C $CK checkout -q --detach $S || fail "checkout $S"
    git -C $CK remote remove origin
    chown -R root:root $CK
    find $CK -type d -exec chmod 0555 {} +
    find $CK -type f -exec chmod 0444 {} +
    git -C $CK ls-files -s | awk '$1=="100755"{print $4}' | (cd $CK && xargs -r chmod 0555)
  fi
  HD=$(asro env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=$CK git -C $CK rev-parse HEAD)
  [ "$HD" = $S ] || fail "checkout vu par cat-obs-ro = $HD"
  [ -z "$(git -C $CK status --porcelain)" ] || fail "checkout modifié"
  ok "checkout de code $CK"
  [ -d $OBSD ] || fail "$OBSD absent (arborescence agent-reports non préparée)"
  if [ ! -d $D ]; then install -d -o cat-obs-ro -g cat-obs-read -m 2750 $D || fail "création $D"; fi
  [ -L $D ] && fail "$D est un lien"
  [ -z "$(ls -A $D)" ] || fail "$D non vide : installation déjà faite ?"
  chown cat-obs-ro:cat-obs-read $D && chmod 2750 $D || fail "droits de $D"
  asro sh -c "cd $CK && $PY -B -m agent_bench.observation.agents manifest --agent $AGENT --root $D --write" || fail "MANIFEST.json"
  ok "dossier $D prêt (MANIFEST.json écrit)"
  cat > $U.service <<UNIT
[Unit]
Description=Market Observer - observation lecture seule des données de marché du VPS
[Service]
Type=oneshot
User=cat-obs-ro
Group=cat-obs-ro
WorkingDirectory=$CK
Environment=PYTHONDONTWRITEBYTECODE=1 HOME=/nonexistent LC_ALL=C
UMask=0027
# Réseau : boucle locale seulement (API opérateur 8090, scanner 18906), aucun accès sortant.
IPAddressAllow=localhost
IPAddressDeny=any
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
ProtectSystem=strict
ReadWritePaths=$D
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
TimeoutStartSec=120
ExecStart=$PY -B -m agent_bench.observation.runtime_observer --mission $MISSION --checkout $CK --reports $D --runner-id $RUNNER --code-sha $S
ExecStopPost=/bin/sh -c 'for d in $D/runs/*/; do [ -d "\$\$d" ] && /usr/local/sbin/cat-obs-prune "\$\$d"; done; exit 0'
ExecStopPost=$PY -B -m agent_bench.observation.agents summary --agent $AGENT --root $D --write
UNIT
  cat > $U.timer <<UNIT
[Unit]
Description=Market Observer, toutes les 10 minutes (:03, :13, ...)
[Timer]
OnCalendar=*:3/10
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
  systemctl start cat-obs-market.service
  R=$(systemctl show cat-obs-market.service -p Result --value)
  echo "premier passage : $R"
  journalctl -u cat-obs-market.service -n 6 --no-pager -o cat
  [ "$R" = success ] || fail "premier passage en échec : timer laissé inactif"
  systemctl enable --now cat-obs-market.timer
  systemctl list-timers cat-obs-market.timer --no-pager | head -2
  ok "Observateur Marché actif : un passage toutes les 10 minutes"
  ;;
control)
  [ -f $U.timer ] || fail "phase install non faite"
  [ -d $C ] || fail "dossier de contrôle absent"
  T=$(mktemp); runuser -u lecanada26 -- git -C $SRC show $S:docs/agents/observation/pilot/cat-obs-schedule-apply.sh > $T || fail "lecture applicateur"
  bash -n $T || fail "applicateur invalide"
  grep -q "market-observer" $T || fail "applicateur sans market-observer"
  [ -f $B/apply.before ] || cp $APPLY $B/apply.before
  install -o root -g root -m 0755 $T $APPLY; rm -f $T
  printf '[Unit]\nDescription=Programmateur Market Observer : appliquer une demande de rythme\n[Service]\nType=oneshot\nExecStart=%s %s\n' $APPLY $AGENT > /etc/systemd/system/cat-obs-schedule-market.service
  printf '[Unit]\nDescription=Programmateur Market Observer : surveiller les demandes\n[Path]\nPathChanged=%s/%s.rhythm\n[Install]\nWantedBy=paths.target\n' $C $AGENT > /etc/systemd/system/cat-obs-schedule-market.path
  chmod 0644 /etc/systemd/system/cat-obs-schedule-market.service /etc/systemd/system/cat-obs-schedule-market.path
  printf '10min\n' > $C/$AGENT.rhythm; chgrp cat-obs-read $C/$AGENT.rhythm; chmod 0660 $C/$AGENT.rhythm
  systemctl daemon-reload && systemctl enable --now cat-obs-schedule-market.path
  $APPLY $AGENT || fail "applicateur en échec"
  cat $C/$AGENT.status.json
  systemctl list-timers cat-obs-market.timer cat-obs-dpa.timer cat-obs-cartographer.timer --no-pager | head -4
  ok "programmateur Market Observer en place, rythme 10 min ; autres agents inchangés"
  ;;
api)
  [ -f $C/$AGENT.status.json ] || fail "phase control non faite"
  [ "$(systemctl show $API_UNIT -p WorkingDirectory --value)" = "$API_PREV" ] || fail "l'API ne tourne plus sur la version attendue : rien n'a été basculé"
  [ -e "$API_DROP" ] && fail "drop-in déjà présent"
  [ -d $B/api ] || fail "préparation absente (prep.sh)"
  [ -e $API_NEW ] || cp -a $B/api $API_NEW
  chown -R lecanada26:lecanada26 $API_NEW
  runuser -u lecanada26 -- bash -c "cd $API_NEW && $H/crypto-install/releases/85376c5e7725c9fa45f8d05fb0051f25a127aba4/.venv/bin/python -B -c 'import observability.operator_api.app'" \
    || fail "la release ne s'importe pas : rien n'a été basculé"
  P0=$(paper)
  printf '[Service]\nWorkingDirectory=%s\nBindReadOnlyPaths=%s\n' $API_NEW $API_NEW > $API_DROP; chmod 0644 $API_DROP
  undo() { rm -f $API_DROP; systemctl daemon-reload; systemctl restart $API_UNIT; api_ready; }
  systemctl daemon-reload; systemctl restart $API_UNIT
  api_ready || { undo; fail "API non prête — retour arrière fait"; }
  [ "$(paper)" = "$P0" ] || { undo; fail "session PAPER modifiée — retour arrière fait"; }
  for u in $BASE/storage-inventory $BASE/lab-experiments $BASE/agent-invocations/repository-cartographer $BASE/agent-invocations/data-provenance-auditor $AG $AG/history $AG/schedule; do
    r=$(code $u); echo "$r $u"; [ "$r" = 200 ] || { undo; fail "$u — retour arrière fait"; }
  done
  curl -s -m 5 $AG | python3 -c 'import json,sys; d=json.load(sys.stdin); print("Market :", d["connection"], d["last_result"], d["display"]["light"], d["display"]["reason"])'
  ok "API sur $API_NEW (stockage, labo, DPA conservés), session PAPER identique"
  ;;
web)
  [ -e "$WEB_DROP" ] && fail "drop-in web déjà présent"
  CUR=$(systemctl show $WEB_UNIT -p BindReadOnlyPaths --value)
  [[ "$CUR" == "$WEB_PREV/dist:$WEB_TARGET/dist:rbind "* ]] || fail "le web ne sert plus $WEB_PREV : rien n'a été basculé"
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
  r=$(code $WEB/api/operator/v1/agent-invocations/$AGENT/history); echo "via web : historique Market $r · DPA $(code $WEB/api/operator/v1/agent-invocations/data-provenance-auditor) · stockage $(code $WEB/api/operator/v1/storage-inventory)"
  [ "$r" = 200 ] || { undo; fail "relais web — retour arrière fait"; }
  ok "web sur $WEB_NEW : bloc Market Observer visible dans Système (recharger la page)"
  ;;
rollback)
  rm -f $WEB_DROP $API_DROP
  systemctl disable --now cat-obs-schedule-market.path cat-obs-market.timer 2>/dev/null
  systemctl stop cat-obs-market.service 2>/dev/null
  rm -f /etc/systemd/system/cat-obs-schedule-market.service /etc/systemd/system/cat-obs-schedule-market.path $U.service $U.timer
  rm -rf /etc/systemd/system/cat-obs-market.timer.d
  systemctl daemon-reload; systemctl restart $API_UNIT $WEB_UNIT; api_ready && ok "API revenue"
  echo "Conservés : $D (rapports), le checkout $CK et l'applicateur (il garde le cartographe et le DPA)."
  ok "retour à API $API_PREV et web $WEB_PREV"
  ;;
esac
