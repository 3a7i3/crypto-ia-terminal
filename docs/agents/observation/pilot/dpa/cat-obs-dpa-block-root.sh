#!/bin/bash
# Bloc Système du Data Provenance Auditor : mini terminal, gyrophare, programmateur ⏰ (opérateur 2026-11-23).
# Construit PAR-DESSUS les versions GPT en service (API …-lab-sync.kNQ7rm, web CAT-LAB-REGISTRY-SYNC) :
# seuls les fichiers des agents sont remplacés, tout le reste (stockage, labo) est conservé.
# Préparation sans root : ~/cat-dpa-block/prep.sh (code 8872f635).
# Usage : sudo bash cat-obs-dpa-block-root.sh control|api|web|rollback   (dans cet ordre)
set -uo pipefail
H=/home/lecanada26
B=$H/cat-dpa-block
C=/srv/cat-obs/control
APPLY=/usr/local/sbin/cat-obs-schedule-apply
AGENT=data-provenance-auditor
API_UNIT=crypto-operator-api
WEB_UNIT=crypto-operator-web
API_PREV=$H/crypto-install/releases/85376c5e-agent-invocation-c823cec1-storage-v1.hiA7Jf-reports.kxGnag-lab-sync.kNQ7rm
API_NEW=$H/crypto-install/releases/85376c5e-agent-invocation-c823cec1-storage-v1.hiA7Jf-reports.kxGnag-lab-sync.kNQ7rm-dpa-8872f635
API_DROP=/etc/systemd/system/$API_UNIT.service.d/zzzzzzzzzzz-dpa-block.conf
WEB_PREV=/opt/cat-app/releases/CAT-LAB-REGISTRY-SYNC
WEB_NEW=/opt/cat-app/releases/CAT-AGENTS-DPA-8872f635
WEB_TARGET=/opt/cat-app/releases/CAT-FOOTPRINT-FINANCE-V6-RC1/frontend
WEB_SRV=/opt/cat-app/releases/CAT-SYSTEM-AGENTS-599-891e1865/server/web01_local_frontend_server.mjs
WEB_DROP=/etc/systemd/system/$WEB_UNIT.service.d/zzzzzzzzzzzzzzzzzzzzzzz-zzz-dpa-block.conf
BASE=http://127.0.0.1:8090/api/operator/v1
WEB=http://127.0.0.1:8181
AG=$BASE/agent-invocations/$AGENT
[ "$(id -u)" = 0 ] || { echo "ECHEC: lancer avec sudo"; exit 1; }
PH=${1:-}
case "$PH" in control|api|web|rollback) ;; *) echo "usage: sudo bash $0 control|api|web|rollback"; exit 2;; esac
LOG=$B/block-$PH-$(date -u +%Y%m%dT%H%M%SZ).log
exec > >(tee "$LOG") 2>&1
echo "== phase $PH $(date -u +%FT%TZ)"
fail() { echo "ECHEC OBLIGATOIRE: $*"; exit 1; }
ok()   { echo "OK: $*"; }
code() { curl -s -o /dev/null -m 5 -w '%{http_code}' "$@"; }
paper() { sha256sum /run/cat/current/session.json; }
api_ready() { for _ in $(seq 1 30); do [ "$(code $BASE/market)" = 200 ] && return 0; sleep 1; done; return 1; }

case "$PH" in
control)
  [ -f /etc/systemd/system/cat-obs-dpa.timer ] || fail "timer DPA absent (installation DPA non faite)"
  [ -d $C ] || fail "dossier de contrôle absent"
  T=$(mktemp); runuser -u lecanada26 -- git -C $H/cat-obs-pilot/src show 8872f635:docs/agents/observation/pilot/cat-obs-schedule-apply.sh > $T || fail "lecture applicateur"
  bash -n $T || fail "applicateur invalide"
  [ -f $B/apply.before ] || cp $APPLY $B/apply.before
  install -o root -g root -m 0755 $T $APPLY; rm -f $T
  printf '[Unit]\nDescription=Programmateur DPA : appliquer une demande de rythme\n[Service]\nType=oneshot\nExecStart=%s %s\n' $APPLY $AGENT > /etc/systemd/system/cat-obs-schedule-dpa.service
  printf '[Unit]\nDescription=Programmateur DPA : surveiller les demandes\n[Path]\nPathChanged=%s/%s.rhythm\n[Install]\nWantedBy=paths.target\n' $C $AGENT > /etc/systemd/system/cat-obs-schedule-dpa.path
  chmod 0644 /etc/systemd/system/cat-obs-schedule-dpa.service /etc/systemd/system/cat-obs-schedule-dpa.path
  systemd-analyze verify /etc/systemd/system/cat-obs-schedule-dpa.service /etc/systemd/system/cat-obs-schedule-dpa.path || fail "unités invalides"
  # État initial = rythme actuel (1 h à la demie), publié par l'applicateur lui-même
  printf '1h\n' > $C/$AGENT.rhythm; chgrp cat-obs-read $C/$AGENT.rhythm; chmod 0660 $C/$AGENT.rhythm
  systemctl daemon-reload && systemctl enable --now cat-obs-schedule-dpa.path
  $APPLY $AGENT || fail "applicateur en échec"
  cat $C/$AGENT.status.json
  systemctl list-timers cat-obs-dpa.timer cat-obs-cartographer.timer --no-pager | head -3
  ok "programmateur DPA en place, rythme 1 h (à la demie) ; cartographe inchangé"
  ;;
api)
  [ -f $C/$AGENT.status.json ] || fail "phase control non faite"
  [ "$(systemctl show $API_UNIT -p WorkingDirectory --value)" = "$API_PREV" ] || fail "l'API ne tourne plus sur la version GPT attendue : rien n'a été basculé"
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
  for u in $BASE/storage-inventory $BASE/lab-experiments $BASE/agent-invocations/repository-cartographer $AG $AG/history $AG/schedule; do
    r=$(code $u); echo "$r $u"; [ "$r" = 200 ] || { undo; fail "$u — retour arrière fait"; }
  done
  curl -s -m 5 $AG | python3 -c 'import json,sys; d=json.load(sys.stdin); print("DPA :", d["connection"], d["last_result"], d["display"]["light"], d["display"]["reason"])'
  curl -s -m 5 $AG/schedule; echo
  ok "API sur $API_NEW (stockage et labo GPT conservés), session PAPER identique"
  ;;
web)
  [ -e "$WEB_DROP" ] && fail "drop-in web déjà présent"
  CUR=$(systemctl show $WEB_UNIT -p BindReadOnlyPaths --value)
  [[ "$CUR" == "$WEB_PREV/dist:$WEB_TARGET/dist:rbind "* ]] || fail "le web ne sert plus CAT-LAB-REGISTRY-SYNC : rien n'a été basculé"
  manifest() { (cd "$1" && find . -type f | sort | xargs sha256sum | sha256sum | cut -d' ' -f1); }
  [ "$(manifest $B/web/frontend/dist)" = "$(cat $B/web.manifest)" ] || fail "dist != manifeste"
  if [ ! -d $WEB_NEW/dist ]; then install -d -m 0755 $WEB_NEW && cp -r $B/web/frontend/dist $WEB_NEW/dist; fi
  chown -R root:root $WEB_NEW; chmod -R a+rX $WEB_NEW
  [ "$(manifest $WEB_NEW/dist)" = "$(cat $B/web.manifest)" ] || fail "copie du dist"
  AP=$(systemctl show $API_UNIT -p MainPID --value)
  printf '[Service]\nBindReadOnlyPaths=\nBindReadOnlyPaths=%s/dist:%s/dist %s:%s/scripts/web01_local_frontend_server.mjs\n' $WEB_NEW $WEB_TARGET $WEB_SRV $WEB_TARGET > $WEB_DROP
  chmod 0644 $WEB_DROP
  undo() { rm -f $WEB_DROP; systemctl daemon-reload; systemctl restart $WEB_UNIT; }
  systemctl daemon-reload && systemctl restart $WEB_UNIT
  A=$(sed -n 's/.*src="\(\/assets\/[^"]*\.js\)".*/\1/p' $WEB_NEW/dist/index.html)
  curl -fsS --retry 8 --retry-connrefused --retry-delay 1 -m 5 $WEB/paper-live/system | cmp - $WEB_NEW/dist/index.html || { undo; fail "page servie != build — retour arrière fait"; }
  curl -fsS -m 5 $WEB$A | cmp - $WEB_NEW/dist$A || { undo; fail "bundle servi != build — retour arrière fait"; }
  r=$(code $WEB/api/operator/v1/agent-invocations/$AGENT/history); echo "via web : historique DPA $r · stockage $(code $WEB/api/operator/v1/storage-inventory) · labo $(code $WEB/api/operator/v1/lab-experiments)"
  [ "$r" = 200 ] || { undo; fail "relais web — retour arrière fait"; }
  [ "$(systemctl show $API_UNIT -p MainPID --value)" = "$AP" ] || echo "ATTENTION: l'API a redémarré pendant la phase web"
  ok "web sur $WEB_NEW : bloc DPA visible dans Système (recharger la page)"
  ;;
rollback)
  rm -f $WEB_DROP $API_DROP
  systemctl disable --now cat-obs-schedule-dpa.path 2>/dev/null
  rm -f /etc/systemd/system/cat-obs-schedule-dpa.service /etc/systemd/system/cat-obs-schedule-dpa.path
  [ -f $B/apply.before ] && install -o root -g root -m 0755 $B/apply.before $APPLY
  systemctl daemon-reload; systemctl restart $API_UNIT $WEB_UNIT; api_ready && ok "API revenue sur la version GPT"
  echo "Rythme du DPA laissé tel quel (drop-in /etc/systemd/system/cat-obs-dpa.timer.d s'il existe)."
  ok "retour à API $API_PREV et web $WEB_PREV"
  ;;
esac
