#!/bin/bash
# Bouton ⏰ du cartographe — exception d'écriture unique (décision Mathieu 2026-11-22 07:23Z). Code e2fc713b.
# Usage : sudo bash cat-obs-button-root.sh control|api|web|rollback   (une phase à la fois, dans cet ordre)
set -uo pipefail
P=/home/lecanada26/cat-obs-pilot
SRC=$P/src
API_OLD=/home/lecanada26/crypto-install/releases/85376c5e7725c9fa45f8d05fb0051f25a127aba4
API_PREV=/home/lecanada26/crypto-install/releases/85376c5e-agent-invocation-e2fc713b
API_NEW=/home/lecanada26/crypto-install/releases/85376c5e-agent-invocation-32f5ce0a
API_TREE=7f009673bbf8f2e72df406c59158aaa750836e50
DROPIN=/etc/systemd/system/crypto-operator-api.service.d/zzzzzz-agent-invocation-599.conf
WEB_NEW=/opt/cat-app/releases/CAT-SYSTEM-AGENTS-599-16c5d07d
WEB_DIST=/opt/cat-app/releases/CAT-FOOTPRINT-FINANCE-V6-RC1/frontend/dist
WEB_SRV=/opt/cat-app/releases/CAT-FOOTPRINT-FINANCE-V6-RC1/frontend/scripts/web01_local_frontend_server.mjs
WEB_DROPIN=/etc/systemd/system/crypto-operator-web.service.d/zzzzzzzzzzzzzzzzzzz-system-agents-599.conf
SRV_SHA=463e53a256fbf25efa19b2a40c65cf62020bf71937c620488cb142c2c781ffc1
C=/srv/cat-obs/control
APPLY=/usr/local/sbin/cat-obs-schedule-apply
BASE=http://127.0.0.1:8090/api/operator/v1
AG=$BASE/agent-invocations/repository-cartographer
[ "$(id -u)" = 0 ] || { echo "ECHEC: lancer avec sudo"; exit 1; }
PH=${1:-}
case "$PH" in control|api|web|retention|rollback) ;; *) echo "usage: sudo bash $0 control|api|web|retention|rollback"; exit 2;; esac
LOG=$P/button-$PH-$(date -u +%Y%m%dT%H%M%SZ).log
exec > >(tee "$LOG") 2>&1
echo "== phase $PH $(date -u +%FT%TZ)"
fail() { echo "ECHEC OBLIGATOIRE: $*"; exit 1; }
ok()   { echo "OK: $*"; }
code() { curl -s -o /dev/null -m 5 -w '%{http_code}' "$@"; }
paper_check() {
  readlink /run/cat/current | diff - $P/paper.before >/dev/null || return 1
  sha256sum /run/cat/current/session.json | diff - $P/paper.sha.before >/dev/null || return 1
  ls -d /run/cat/PAPER-* | diff - $P/paper.sessions.before >/dev/null || return 1
}
api_ready() { for _ in $(seq 1 30); do [ "$(code $BASE/market)" = 200 ] && return 0; sleep 1; done; return 1; }

case "$PH" in
control)
  [ -f /etc/systemd/system/cat-obs-cartographer.timer ] || fail "timer de base absent (phase hourly non faite)"
  install -d -o root -g cat-obs-read -m 2770 $C
  T=$(mktemp); runuser -u lecanada26 -- git -C $SRC show e2fc713bb74adcc830b0f35ecf5a3d362fb2dfb8:docs/agents/observation/pilot/cat-obs-schedule-apply.sh > $T || fail "lecture applicateur"
  install -o root -g root -m 0755 $T $APPLY; rm -f $T
  bash -n $APPLY || fail "applicateur invalide"
  printf '[Unit]\nDescription=Programmateur cartographe : appliquer une demande de rythme\n[Service]\nType=oneshot\nExecStart=%s\n' $APPLY > /etc/systemd/system/cat-obs-schedule.service
  printf '[Unit]\nDescription=Programmateur cartographe : surveiller les demandes\n[Path]\nPathChanged=%s/repository-cartographer.rhythm\n[Install]\nWantedBy=paths.target\n' $C > /etc/systemd/system/cat-obs-schedule.path
  chmod 0644 /etc/systemd/system/cat-obs-schedule.service /etc/systemd/system/cat-obs-schedule.path
  systemd-analyze verify /etc/systemd/system/cat-obs-schedule.service /etc/systemd/system/cat-obs-schedule.path || fail "unités invalides"
  # État initial = rythme actuel (1 h), publié par l'applicateur lui-même
  printf '1h\n' > $C/repository-cartographer.rhythm; chgrp cat-obs-read $C/repository-cartographer.rhythm; chmod 0660 $C/repository-cartographer.rhythm
  systemctl daemon-reload && systemctl enable --now cat-obs-schedule.path
  $APPLY || fail "applicateur en échec"
  cat $C/repository-cartographer.status.json
  systemctl list-timers cat-obs-cartographer.timer --no-pager | head -2
  ok "programmateur en place, rythme 1 h"
  ;;
api)
  [ -f $C/repository-cartographer.status.json ] || fail "phase control non faite"
  [ "$(runuser -u lecanada26 -- git -C $API_NEW write-tree)" = $API_TREE ] || fail "arbre API_NEW"
  # Démarrage vérifié AVANT bascule (leçon du 22 nov 06:59Z)
  runuser -u lecanada26 -- bash -c "cd $API_NEW && AGENT_INVOCATION_REPORTS_PATH=/nonexistent $API_OLD/.venv/bin/python -B -c 'import observability.operator_api.app'" \
    || fail "la release ne s'importe pas : rien n'a été basculé"
  ok "release API $API_TREE importable"
  paper_check || fail "session PAPER déjà différente avant action"
  grep -q "$API_PREV" "$DROPIN" || fail "drop-in ne pointe pas sur la release précédente"
  [ -f $P/api-dropin.before-button ] || cp "$DROPIN" $P/api-dropin.before-button
  cp "$DROPIN" $P/api-dropin.prev
  sed -i "s#$API_PREV#$API_NEW#g" "$DROPIN"
  grep -q "^ReadWritePaths=$C" "$DROPIN" || echo "ReadWritePaths=$C" >> "$DROPIN"
  undo() { cp $P/api-dropin.prev "$DROPIN"; systemctl daemon-reload; systemctl restart crypto-operator-api; api_ready; }
  systemctl daemon-reload; systemctl restart crypto-operator-api
  api_ready || { undo; fail "API non prête — retour arrière fait"; }
  paper_check || { undo; fail "session PAPER modifiée — retour arrière fait"; }
  echo "état $(code $AG)  historique $(code $AG/history)  programmateur $(code $AG/schedule)  sans en-tête $(code -X POST -H 'content-type: application/json' -d '{"rhythm":"1h"}' $AG/schedule)  valeur hors liste $(code -X POST -H 'content-type: application/json' -H 'x-cat-operator: schedule' -d '{"rhythm":"x"}' $AG/schedule)"
  [ "$(code $AG/schedule)" = 200 ] || { undo; fail "route programmateur — retour arrière fait"; }
  curl -s -m 5 $AG/schedule; echo
  ok "API sur $API_NEW, session PAPER identique"
  ;;
web)
  manifest() { (cd "$1" && find . -type f | sort | xargs sha256sum | sha256sum | cut -d' ' -f1); }
  [ "$(manifest $SRC/frontend/dist)" = "$(cat $P/web7.manifest)" ] || fail "dist construit != manifeste"
  [ "$(sha256sum < $SRC/frontend/scripts/web01_local_frontend_server.mjs | cut -d' ' -f1)" = $SRV_SHA ] || fail "serveur web != empreinte"
  if [ ! -d $WEB_NEW/dist ]; then
    install -d -o root -g root -m 0755 $WEB_NEW $WEB_NEW/server && cp -a $SRC/frontend/dist $WEB_NEW/ \
      && install -o root -g root -m 0644 $SRC/frontend/scripts/web01_local_frontend_server.mjs $WEB_NEW/server/
    chown -R root:root $WEB_NEW; find $WEB_NEW -type d -exec chmod 0755 {} +; find $WEB_NEW -type f -exec chmod 0644 {} +
  fi
  [ "$(manifest $WEB_NEW/dist)" = "$(cat $P/web7.manifest)" ] || fail "copie du dist"
  [ -f $P/web-dropin.before-button ] || cp "$WEB_DROPIN" $P/web-dropin.before-button
  cp "$WEB_DROPIN" $P/web-dropin.prev
  printf '[Service]\nBindReadOnlyPaths=\nBindReadOnlyPaths=%s/dist:%s %s/server/web01_local_frontend_server.mjs:%s\n' "$WEB_NEW" "$WEB_DIST" "$WEB_NEW" "$WEB_SRV" > "$WEB_DROPIN"
  chmod 0644 "$WEB_DROPIN"
  undo() { cp $P/web-dropin.prev "$WEB_DROPIN"; systemctl daemon-reload; systemctl restart crypto-operator-web; }
  systemctl daemon-reload && systemctl restart crypto-operator-web
  for _ in $(seq 1 30); do [ "$(code http://127.0.0.1:8181/)" = 200 ] && break; sleep 1; done
  M=/proc/$(systemctl show crypto-operator-web -p MainPID --value)/mountinfo
  grep -q "CAT-SYSTEM-AGENTS-599-16c5d07d/dist" $M && grep -q "CAT-SYSTEM-AGENTS-599-16c5d07d/server" $M || { undo; fail "montages absents — retour arrière fait"; }
  W=http://127.0.0.1:8181/api/operator/v1/agent-invocations/repository-cartographer
  R1=$(code -X POST -H 'content-type: application/json' -H 'x-cat-operator: schedule' -d '{"rhythm":"x"}' $W/schedule)
  R2=$(code -X POST -d '{}' $W/history); R3=$(code -X POST -d '{}' http://127.0.0.1:8181/api/operator/v1/market)
  echo "via web : programmateur valeur hors liste $R1 (attendu 422) · POST historique $R2 (405) · POST market $R3 (405) · page $(code http://127.0.0.1:8181/)"
  [ "$R1" = 422 ] && [ "$R2" = 405 ] && [ "$R3" = 405 ] || { undo; fail "relais web non conforme — retour arrière fait"; }
  paper_check && ok "session PAPER identique" || echo "ATTENTION: session PAPER différente"
  ok "web sur $WEB_NEW (bouton actif)"
  ;;
retention)
  RUNS=/srv/cat-obs/reports/runs/02e0f78f43d1062ee0efed015ad9fe37329dbe480062f02c53e32c82e19fdece
  T=$(mktemp); runuser -u lecanada26 -- git -C $SRC show a77d81bbb02ff21b53c8165bab199576e159b691:docs/agents/observation/pilot/cat-obs-prune.sh > $T || fail "lecture du script de rétention"
  install -o root -g root -m 0755 $T /usr/local/sbin/cat-obs-prune; rm -f $T
  install -d -m 0755 /etc/systemd/system/cat-obs-cartographer.service.d
  printf '[Service]\nExecStopPost=/usr/local/sbin/cat-obs-prune %s\n' $RUNS > /etc/systemd/system/cat-obs-cartographer.service.d/retention.conf
  chmod 0644 /etc/systemd/system/cat-obs-cartographer.service.d/retention.conf
  systemctl daemon-reload
  echo "rapports avant : $(find $RUNS -maxdepth 1 -type f -name '*.json' | wc -l)"
  runuser -u cat-obs-ro -- /usr/local/sbin/cat-obs-prune $RUNS || fail "rétention en échec"
  echo "rapports après : $(find $RUNS -maxdepth 1 -type f -name '*.json' | wc -l) (20 au plus)"
  echo "taille du dossier : $(du -sh /srv/cat-obs/reports | cut -f1)"
  ok "rétention active : 20 derniers rapports après chaque passage"
  ;;
rollback)
  [ -f $P/web-dropin.before-button ] && cp $P/web-dropin.before-button "$WEB_DROPIN"
  [ -f $P/api-dropin.before-button ] && cp $P/api-dropin.before-button "$DROPIN"
  systemctl disable --now cat-obs-schedule.path 2>/dev/null
  rm -f /etc/systemd/system/cat-obs-cartographer.service.d/retention.conf
  systemctl daemon-reload; systemctl restart crypto-operator-api crypto-operator-web; api_ready && ok "API revenue"
  paper_check && ok "session PAPER identique" || echo "ATTENTION: session PAPER différente"
  echo "Rythme de l'agent inchangé (timer tel quel). Arrêt complet : sudo bash $P/cat-obs-upgrade-root.sh stop-agent"
  ;;
esac
