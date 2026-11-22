#!/bin/bash
# Suivi de main du cartographe (décision Mathieu 2026-11-22 10:28Z). Code c823cec1.
# Usage : sudo bash cat-obs-follow-root.sh api|follow|rollback   (une phase à la fois, dans cet ordre)
set -uo pipefail
P=/home/lecanada26/cat-obs-pilot
SRC=$P/src
S=c823cec17891c54d814aa9f4bec759925445579e
FOLLOW_REV=99ffc002f926b5a5828deaaaaa3f3923a991a48b
CKN=/srv/cat-obs/checkout/$S
API_OLD=/home/lecanada26/crypto-install/releases/85376c5e7725c9fa45f8d05fb0051f25a127aba4
API_PREV=/home/lecanada26/crypto-install/releases/85376c5e-agent-invocation-32f5ce0a
API_NEW=/home/lecanada26/crypto-install/releases/85376c5e-agent-invocation-c823cec1
API_TREE=6e61fbf0ac651f15b01be4295cd66d404b7af825
DROPIN=/etc/systemd/system/crypto-operator-api.service.d/zzzzzz-agent-invocation-599.conf
UP=/srv/cat-obs/upstream
OUT=/srv/cat-obs/follow
FU=/etc/systemd/system/cat-obs-follow.service
CD=/etc/systemd/system/cat-obs-cartographer.service.d/zz-follow-main.conf
BASE=http://127.0.0.1:8090/api/operator/v1
AG=$BASE/agent-invocations/repository-cartographer
[ "$(id -u)" = 0 ] || { echo "ECHEC: lancer avec sudo"; exit 1; }
PH=${1:-}
case "$PH" in api|follow|rollback) ;; *) echo "usage: sudo bash $0 api|follow|rollback"; exit 2;; esac
LOG=$P/follow-$PH-$(date -u +%Y%m%dT%H%M%SZ).log
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
api)
  [ "$(runuser -u lecanada26 -- git -C $API_NEW write-tree)" = $API_TREE ] || fail "arbre API_NEW"
  runuser -u lecanada26 -- bash -c "cd $API_NEW && AGENT_INVOCATION_REPORTS_PATH=/nonexistent $API_OLD/.venv/bin/python -B -c 'import observability.operator_api.app'" \
    || fail "la release ne s'importe pas : rien n'a été basculé"
  ok "release API $API_TREE importable"
  paper_check || fail "session PAPER déjà différente avant action"
  grep -q "$API_PREV" "$DROPIN" || fail "drop-in ne pointe pas sur la release précédente"
  [ -f $P/api-dropin.before-follow ] || cp "$DROPIN" $P/api-dropin.before-follow
  cp "$DROPIN" $P/api-dropin.prev
  sed -i "s#$API_PREV#$API_NEW#g" "$DROPIN"
  undo() { cp $P/api-dropin.prev "$DROPIN"; systemctl daemon-reload; systemctl restart crypto-operator-api; api_ready; }
  systemctl daemon-reload; systemctl restart crypto-operator-api
  api_ready || { undo; fail "API non prête — retour arrière fait"; }
  paper_check || { undo; fail "session PAPER modifiée — retour arrière fait"; }
  echo "état $(code $AG)  historique $(code $AG/history)  programmateur $(code $AG/schedule)"
  [ "$(code $AG/history)" = 200 ] || { undo; fail "route historique — retour arrière fait"; }
  ok "API sur $API_NEW (mission figée tant que le suivi n'est pas installé), session PAPER identique"
  ;;
follow)
  grep -q "$API_NEW" "$DROPIN" || fail "phase api non faite"
  # Checkout de code immuable au SHA $S
  if [ ! -d $CKN ]; then
    runuser -u lecanada26 -- git -C $SRC cat-file -e $S^{commit} || fail "commit $S absent de $SRC"
    GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=$SRC \
      git clone -q --no-hardlinks $SRC $CKN || fail "clone checkout"
    git -C $CKN checkout -q --detach $S || fail "checkout $S"
    git -C $CKN remote remove origin
    chown -R root:root $CKN
    find $CKN -type d -exec chmod 0555 {} +
    find $CKN -type f -exec chmod 0444 {} +
    git -C $CKN ls-files -s | awk '$1=="100755"{print $4}' | (cd $CKN && xargs -r chmod 0555)
  fi
  [ -z "$(git -C $CKN status --porcelain)" ] || fail "checkout modifié"
  ok "checkout de code $CKN"
  # Script de suivi
  T=$(mktemp); runuser -u lecanada26 -- git -C $SRC show $FOLLOW_REV:docs/agents/observation/pilot/cat-obs-follow.sh > $T || fail "lecture du script de suivi"
  install -o root -g root -m 0755 $T /usr/local/sbin/cat-obs-follow; rm -f $T
  bash -n /usr/local/sbin/cat-obs-follow || fail "script de suivi invalide"
  # Arbre analysé (main) et sorties du suivi
  install -d -o cat-obs-ro -g cat-obs-ro -m 0750 $UP
  if [ ! -d $UP/.git ]; then
    runuser -u cat-obs-ro -- env HOME=/nonexistent git init -q $UP || fail "init arbre analysé"
    runuser -u cat-obs-ro -- env HOME=/nonexistent git -C $UP remote add origin https://github.com/3a7i3/crypto-ia-terminal
  fi
  install -d -o cat-obs-ro -g cat-obs-read -m 2750 $OUT
  {
    echo "[Unit]"; echo "Description=Repository Cartographer : lire main avant chaque passage (lecture seule)"
    echo "[Service]"; echo "Type=oneshot"; echo "User=cat-obs-ro"; echo "Group=cat-obs-ro"; echo "UMask=0027"
    for o in ProtectSystem=strict "ReadWritePaths=$UP $OUT" ProtectHome=yes PrivateTmp=yes PrivateDevices=yes \
      ProtectProc=invisible NoNewPrivileges=yes CapabilityBoundingSet= ProtectKernelTunables=yes \
      ProtectKernelModules=yes ProtectControlGroups=yes RestrictSUIDSGID=yes LockPersonality=yes \
      "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" MemoryMax=512M TasksMax=32 TimeoutStartSec=120; do echo "$o"; done
    echo "ExecStart=/usr/local/sbin/cat-obs-follow $CKN"
  } > $FU
  chmod 0644 $FU
  systemd-analyze verify $FU || fail "unité de suivi invalide"
  systemctl daemon-reload
  systemctl start cat-obs-follow.service || { journalctl -u cat-obs-follow -n 20 --no-pager; fail "premier suivi en échec"; }
  cat $OUT/current.env
  # Passage du cartographe : mission et révision publiées par le suivi
  [ -f $P/cartographer-dropins.before-follow.tgz ] || tar czf $P/cartographer-dropins.before-follow.tgz -C /etc/systemd/system cat-obs-cartographer.service.d
  cat > $CD <<EOF
[Unit]
Requires=cat-obs-follow.service
After=cat-obs-follow.service
[Service]
EnvironmentFile=$OUT/current.env
WorkingDirectory=$CKN
ExecStart=
ExecStart=/usr/bin/python3.10 -B -m agent_bench.observation.executor --mission $OUT/mission.json --checkout $CKN --reports /srv/cat-obs/reports --runner-id obs-repo-cartographer-ro-01 --code-sha $S --analysed-sha \${ANALYSED_SHA} --analysed-tree $UP
ExecStopPost=
ExecStopPost=/usr/local/sbin/cat-obs-prune /srv/cat-obs/reports/runs/\${MISSION_ID}
EOF
  chmod 0644 $CD
  systemctl daemon-reload
  systemctl start cat-obs-cartographer.service; echo "passage : $(systemctl show cat-obs-cartographer.service -p Result --value)"
  . $OUT/current.env
  ls /srv/cat-obs/reports/runs/$MISSION_ID | tail -2
  curl -s -m 5 $AG | head -c 400; echo
  systemctl list-timers cat-obs-cartographer.timer --no-pager | head -2
  ok "suivi de main actif : main = $ANALYSED_SHA, mission $MISSION_ID"
  ;;
rollback)
  rm -f $CD
  [ -f $P/api-dropin.before-follow ] && cp $P/api-dropin.before-follow "$DROPIN"
  systemctl daemon-reload; systemctl restart crypto-operator-api; api_ready && ok "API revenue sur la mission figée"
  paper_check && ok "session PAPER identique" || echo "ATTENTION: session PAPER différente"
  echo "Le cartographe repasse sur la mission figée e387318e. $UP et $OUT sont conservés (supprimables à la main)."
  ;;
esac
