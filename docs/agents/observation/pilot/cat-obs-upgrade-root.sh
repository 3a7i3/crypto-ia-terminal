#!/bin/bash
# Cartographe : mini terminal + rythme 1 h (choix A, Mathieu 2026-11-22). Code ad2f46df.
# app.py = app.py servi (c1ecc3b4) + route /history seule : celui de la branche importe des modules absents de 85376c5e.
# Usage : sudo bash cat-obs-upgrade-root.sh stop-agent|api|web|hourly|rollback
set -uo pipefail
P=/home/lecanada26/cat-obs-pilot
S=cd23922a99f64bac93fb16255b70d32387c54871
ANALYSED=e387318eeaed81d4e6dc90228d46943a65a5b73c
API_OLD=/home/lecanada26/crypto-install/releases/85376c5e7725c9fa45f8d05fb0051f25a127aba4
API_PREV=/home/lecanada26/crypto-install/releases/85376c5e-agent-invocation-c1ecc3b4
API_NEW=/home/lecanada26/crypto-install/releases/85376c5e-agent-invocation-ad2f46df
CK=/srv/cat-obs/checkout/$S
R=/srv/cat-obs/reports
DROPIN=/etc/systemd/system/crypto-operator-api.service.d/zzzzzz-agent-invocation-599.conf
WEB_PREV=/opt/cat-app/releases/CAT-SYSTEM-AGENTS-599-cd23922a
WEB_NEW=/opt/cat-app/releases/CAT-SYSTEM-AGENTS-599-ad2f46df
WEB_DIST=/opt/cat-app/releases/CAT-FOOTPRINT-FINANCE-V6-RC1/frontend/dist
WEB_DROPIN=/etc/systemd/system/crypto-operator-web.service.d/zzzzzzzzzzzzzzzzzzz-system-agents-599.conf
U=/etc/systemd/system/cat-obs-cartographer
BASE=http://127.0.0.1:8090/api/operator/v1
[ "$(id -u)" = 0 ] || { echo "ECHEC: lancer avec sudo"; exit 1; }
PH=${1:-}
case "$PH" in stop-agent|api|web|hourly|rollback) ;; *) echo "usage: sudo bash $0 stop-agent|api|web|hourly|rollback"; exit 2;; esac
exec > >(tee "$P/upgrade-$PH-$(date -u +%Y%m%dT%H%M%SZ).log") 2>&1
echo "== phase $PH $(date -u +%FT%TZ)"
fail() { echo "ECHEC OBLIGATOIRE: $*"; exit 1; }
ok()   { echo "OK: $*"; }
paper_check() {
  readlink /run/cat/current | diff - $P/paper.before >/dev/null || return 1
  sha256sum /run/cat/current/session.json | diff - $P/paper.sha.before >/dev/null || return 1
  ls -d /run/cat/PAPER-* | diff - $P/paper.sessions.before >/dev/null || return 1
}
code() { curl -s -o /dev/null -m 5 -w '%{http_code}' "$1"; }
api_ready() { for _ in $(seq 1 30); do [ "$(code $BASE/market)" = 200 ] && return 0; sleep 1; done; return 1; }
set_api() { sed -i "s#$1#$2#g" "$DROPIN"; systemctl daemon-reload; systemctl restart crypto-operator-api; }

case "$PH" in
stop-agent)
  systemctl disable --now cat-obs-cartographer.timer 2>/dev/null
  systemctl stop cat-obs-cartographer.service 2>/dev/null
  rm -f $U.timer; systemctl daemon-reload
  # (grep sans correspondance sort en 1 : pas de pipeline sous pipefail)
  [ "$(systemctl is-active cat-obs-cartographer.timer)" != active ] && [ ! -e $U.timer ] \
    && [ "$(systemctl is-active cat-obs-cartographer.service)" != active ] && ok "agent arrêté, aucun timer" || fail "timer encore présent"
  ;;
api)
  [ -f "$DROPIN" ] || fail "drop-in API absent"
  [ "$(runuser -u lecanada26 -- git -C $API_NEW write-tree)" = bace0d1ed7e1e7a242e51c4fa1561a0bde636216 ] || fail "arbre API_NEW"
  [ "$(runuser -u lecanada26 -- git -C $API_NEW diff --cached --name-status ${API_OLD##*/} | wc -l)" = 7 ] || fail "API_NEW != 7 fichiers"
  ok "release API bace0d1e (7 fichiers)"
  paper_check || fail "session PAPER déjà différente avant action"
  grep -q "$API_PREV" "$DROPIN" || fail "drop-in ne pointe pas sur la release précédente"
  set_api "$API_PREV" "$API_NEW"
  undo() { set_api "$API_NEW" "$API_PREV"; api_ready; }
  api_ready || { undo; fail "API non prête — retour arrière fait"; }
  [ "$(systemctl show crypto-operator-api -p WorkingDirectory --value)" = $API_NEW ] || { undo; fail "WorkingDirectory"; }
  paper_check || { undo; fail "session PAPER modifiée — retour arrière fait"; }
  echo "route état : $(code $BASE/agent-invocations/repository-cartographer)  historique : $(code $BASE/agent-invocations/repository-cartographer/history)  inconnu : $(code $BASE/agent-invocations/x/history)"
  [ "$(code $BASE/agent-invocations/repository-cartographer/history)" = 200 ] || { undo; fail "route historique — retour arrière fait"; }
  curl -s -m 5 $BASE/agent-invocations/repository-cartographer/history | python3 -c 'import json,sys;d=json.load(sys.stdin);print("historique:",d["connection"],"total",d["total"],[i["verdict"] for i in d["items"]])'
  ok "API sur $API_NEW, session PAPER identique"
  ;;
web)
  SRC=$P/src/frontend/dist
  manifest() { (cd "$1" && find . -type f | sort | xargs sha256sum | sha256sum | cut -d' ' -f1); }
  [ "$(manifest $SRC)" = "$(cat $P/web2.manifest)" ] || fail "dist construit != manifeste"
  if [ ! -d $WEB_NEW/dist ]; then
    install -d -o root -g root -m 0755 $WEB_NEW && cp -a $SRC $WEB_NEW/ && chown -R root:root $WEB_NEW
    find $WEB_NEW -type d -exec chmod 0755 {} + && find $WEB_NEW -type f -exec chmod 0644 {} +
  fi
  [ "$(manifest $WEB_NEW/dist)" = "$(cat $P/web2.manifest)" ] || fail "copie du dist"
  sed -i "s#$WEB_PREV/dist#$WEB_NEW/dist#" "$WEB_DROPIN"
  systemctl daemon-reload && systemctl restart crypto-operator-web
  for _ in $(seq 1 30); do [ "$(code http://127.0.0.1:8181/)" = 200 ] && break; sleep 1; done
  undo() { sed -i "s#$WEB_NEW/dist#$WEB_PREV/dist#" "$WEB_DROPIN"; systemctl daemon-reload; systemctl restart crypto-operator-web; }
  grep -q "CAT-SYSTEM-AGENTS-599-ad2f46df/dist" /proc/$(systemctl show crypto-operator-web -p MainPID --value)/mountinfo || { undo; fail "dist non monté — retour arrière fait"; }
  echo "historique via web : $(code http://127.0.0.1:8181/api/operator/v1/agent-invocations/repository-cartographer/history)"
  paper_check && ok "session PAPER identique" || echo "ATTENTION: session PAPER différente"
  ok "web sur $WEB_NEW/dist"
  ;;
hourly)
  {
    echo "[Unit]"; echo "Description=Repository Cartographer (#599) - une invocation par heure, sans relance"
    echo "[Service]"; echo "Type=oneshot"; echo "User=cat-obs-ro"; echo "Group=cat-obs-ro"
    echo "WorkingDirectory=$CK"; echo "Environment=PYTHONDONTWRITEBYTECODE=1 HOME=/nonexistent LC_ALL=C"; echo "UMask=0027"
    for o in PrivateNetwork=yes IPAddressDeny=any RestrictAddressFamilies=AF_UNIX ProtectSystem=strict \
      ReadWritePaths=$R ProtectHome=yes PrivateTmp=yes PrivateDevices=yes ProtectProc=invisible \
      NoNewPrivileges=yes CapabilityBoundingSet= ProtectKernelTunables=yes ProtectKernelModules=yes \
      ProtectControlGroups=yes RestrictSUIDSGID=yes LockPersonality=yes MemoryMax=1G TasksMax=16 \
      CPUQuota=100% TimeoutStartSec=180; do echo "$o"; done
    echo "ExecStart=/usr/bin/python3.10 -B -m agent_bench.observation.executor --mission docs/agents/observation/examples/cartographer_zone_mission.json --checkout $CK --reports $R --runner-id obs-repo-cartographer-ro-01 --code-sha $S --analysed-sha $ANALYSED"
  } > $U.service
  printf '[Unit]\nDescription=Repository Cartographer (#599), toutes les heures\n[Timer]\nOnCalendar=hourly\nPersistent=false\nAccuracySec=1s\n[Install]\nWantedBy=timers.target\n' > $U.timer
  chmod 0644 $U.service $U.timer
  systemd-analyze verify $U.service $U.timer || fail "unités invalides"
  systemctl daemon-reload
  systemctl start cat-obs-cartographer.service; echo "première invocation : $(systemctl show cat-obs-cartographer.service -p Result --value)"
  systemctl enable --now cat-obs-cartographer.timer
  systemctl list-timers cat-obs-cartographer.timer --no-pager
  ok "rythme 1 h actif ; arrêt complet : sudo bash $0 stop-agent"
  ;;
rollback)
  sed -i "s#$WEB_NEW/dist#$WEB_PREV/dist#" "$WEB_DROPIN"; grep -q "$API_NEW" "$DROPIN" && sed -i "s#$API_NEW#$API_PREV#g" "$DROPIN"
  systemctl daemon-reload; systemctl restart crypto-operator-api crypto-operator-web; api_ready && ok "API revenue sur $API_PREV"
  paper_check && ok "session PAPER identique" || echo "ATTENTION: session PAPER différente"
  echo "Le rythme de l'agent n'est pas modifié ; pour l'arrêter : sudo bash $0 stop-agent"
  ;;
esac
