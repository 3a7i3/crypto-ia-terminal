#!/bin/bash
# Pilote Repository Cartographer (#599, cd23922a) — étapes root, GO Mathieu 2026-11-22 04:45Z.
# Usage : sudo bash cat-obs-pilot-root.sh access|install|invoke|rollback
# Chaque phase s'arrête au premier contrôle obligatoire en échec.
# « install » revient automatiquement en arrière si l'API ou la session PAPER ne sont pas conformes.
set -uo pipefail

S=cd23922a99f64bac93fb16255b70d32387c54871
ANALYSED=e387318eeaed81d4e6dc90228d46943a65a5b73c
P=/home/lecanada26/cat-obs-pilot
API_OLD=/home/lecanada26/crypto-install/releases/85376c5e7725c9fa45f8d05fb0051f25a127aba4
API_NEW=/home/lecanada26/crypto-install/releases/85376c5e-agent-invocation-c1ecc3b4
CK=/srv/cat-obs/checkout/$S
R=/srv/cat-obs/reports
DROPIN=/etc/systemd/system/crypto-operator-api.service.d/zzzzzz-agent-invocation-599.conf
URL=http://127.0.0.1:8090/api/operator/v1/market

[ "$(id -u)" = 0 ] || { echo "ECHEC: lancer avec sudo"; exit 1; }
PH=${1:-}
case "$PH" in access|install|invoke|rollback) ;; *) echo "usage: sudo bash $0 access|install|invoke|rollback"; exit 2;; esac
LOG=$P/root-$PH-$(date -u +%Y%m%dT%H%M%SZ).log
exec > >(tee "$LOG") 2>&1
echo "== phase $PH $(date -u +%FT%TZ)"
fail() { echo "ECHEC OBLIGATOIRE: $*"; exit 1; }
ok()   { echo "OK: $*"; }

paper_check() {
  readlink /run/cat/current | diff - $P/paper.before >/dev/null || return 1
  sha256sum /run/cat/current/session.json | diff - $P/paper.sha.before >/dev/null || return 1
  ls -d /run/cat/PAPER-* | diff - $P/paper.sessions.before >/dev/null || return 1
}

api_ready() {
  for _ in $(seq 1 30); do
    [ "$(systemctl is-active crypto-operator-api)" = active ] && \
      [ "$(curl -s -o /dev/null -m 5 -w '%{http_code}' $URL)" = 200 ] && return 0
    sleep 1
  done
  return 1
}

do_rollback() {
  echo "== retour arrière"
  rm -f "$DROPIN"
  systemctl daemon-reload
  systemctl restart crypto-operator-api
  api_ready && ok "API active" || echo "ATTENTION: API non prête après retour arrière"
  systemctl show crypto-operator-api -p WorkingDirectory -p SupplementaryGroups
  paper_check && ok "session PAPER identique" || echo "ATTENTION: session PAPER différente"
  if getent group cat-obs-read >/dev/null; then
    chgrp -R cat-obs-ro $R && chmod 0750 $R
    [ -d $R/runs ] && chmod g-s $R/runs
    [ -d $R/locks ] && chmod g-s $R/locks
    groupdel cat-obs-read
  fi
  stat -c '%a %U:%G %n' $R
  echo "Conservés : $R (rapports), $API_NEW, $CK."
}

case "$PH" in
access)
  getent group cat-obs-read >/dev/null || groupadd --system cat-obs-read
  [ -z "$(getent group cat-obs-read | cut -d: -f4)" ] || fail "cat-obs-read a des membres"
  install -d -o cat-obs-ro -g cat-obs-read -m 2750 $R/runs $R/locks
  chgrp cat-obs-read $R && chmod 0710 $R
  stat -c '%a %U:%G %n' $R $R/runs $R/locks
  [ "$(stat -c '%a %U:%G' $R)" = "710 cat-obs-ro:cat-obs-read" ] || fail "mode reports"
  for d in runs locks; do
    [ "$(stat -c '%a %U:%G' $R/$d)" = "2750 cat-obs-ro:cat-obs-read" ] || fail "mode $d"
  done
  id lecanada26
  ok "accès minimaux posés (compte lecanada26 inchangé)"
  ;;
install)
  getent group cat-obs-read >/dev/null || fail "phase access non faite"
  # Release API (préparée par lecanada26) : arbre et 7 fichiers exacts
  [ "$(runuser -u lecanada26 -- git -C $API_NEW write-tree)" = c1ecc3b436e8a9617004ca0c8f142ec9e7ff7012 ] || fail "arbre API_NEW"
  [ "$(runuser -u lecanada26 -- git -C $API_NEW diff --cached --name-status ${API_OLD##*/} | wc -l)" = 7 ] || fail "API_NEW != 7 fichiers"
  ok "release API c1ecc3b4, 7 fichiers"
  # Checkout runner immuable
  if [ ! -d $CK ]; then
    GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=$P/src \
      git clone -q --no-hardlinks $P/src $CK || fail "clone checkout"
    git -C $CK checkout -q --detach $S || fail "checkout $S"
    git -C $CK remote remove origin
    chown -R root:root $CK
    find $CK -type d -exec chmod 0555 {} +
    find $CK -type f -exec chmod 0444 {} +
  fi
  # Exécutables suivis par git : 0555 (lecture+exécution, jamais écriture), sinon git voit un changement de mode
  git -C $CK ls-files -s | awk '$1=="100755"{print $4}' | (cd $CK && xargs -r chmod 0555)
  H=$(runuser -u cat-obs-ro -- env -i PATH=/usr/bin:/bin HOME=/nonexistent GIT_CONFIG_COUNT=1 \
      GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=$CK git -C $CK rev-parse HEAD)
  [ "$H" = $S ] || fail "checkout vu par cat-obs-ro = $H"
  [ -z "$(git -C $CK status --porcelain)" ] || { git -C $CK status --porcelain | head; fail "checkout modifié"; }
  ok "checkout runner $CK = $S"
  # État avant redémarrage
  paper_check || fail "session PAPER déjà différente de l'état consigné avant toute action"
  cat > "$DROPIN" <<EOF
[Service]
WorkingDirectory=$API_NEW
ExecStart=
ExecStart=$API_OLD/.venv/bin/python -B -m uvicorn observability.operator_api.app:app --host 127.0.0.1 --port 8090 --no-access-log
BindReadOnlyPaths=
BindReadOnlyPaths=$API_NEW $API_OLD /home/lecanada26/crypto-install/python/cpython-3.11.17-linux-x86_64-gnu /home/lecanada26/crypto-install/presentation
SupplementaryGroups=cat-obs-read
Environment=AGENT_INVOCATION_REPORTS_PATH=$R
EOF
  chmod 0644 "$DROPIN"
  systemctl daemon-reload
  systemctl show crypto-operator-api -p MainPID > $P/api.mainpid.before-restart
  systemctl restart crypto-operator-api
  if ! api_ready; then
    systemctl status crypto-operator-api --no-pager -n 30
    do_rollback; fail "API non prête après redémarrage — retour arrière fait"
  fi
  systemctl show crypto-operator-api -p MainPID -p WorkingDirectory -p SupplementaryGroups
  [ "$(systemctl show crypto-operator-api -p WorkingDirectory --value)" = $API_NEW ] || { do_rollback; fail "WorkingDirectory"; }
  grep -Eq "^Groups:.*\b$(getent group cat-obs-read | cut -d: -f3)\b" /proc/$(systemctl show crypto-operator-api -p MainPID --value)/status \
    || { do_rollback; fail "groupe cat-obs-read absent du processus API"; }
  paper_check || { do_rollback; fail "session PAPER modifiée — retour arrière fait"; }
  ok "API redémarrée sur $API_NEW, groupe cat-obs-read, session PAPER identique ($(cat $P/paper.before))"
  ;;
invoke)
  [ -f "$DROPIN" ] || fail "phase install non faite"
  [ -z "$(ls -A $R/runs)" ] || { ls -la $R/runs; fail "runs/ non vide : une invocation existe déjà, pas de seconde invocation"; }
  systemd-run --unit=cat-obs-cartographer-$(date -u +%Y%m%dT%H%M%SZ) --wait --collect --pipe \
    --uid=cat-obs-ro --gid=cat-obs-ro \
    -p WorkingDirectory=$CK \
    -p Environment=PYTHONDONTWRITEBYTECODE=1 -p Environment=HOME=/nonexistent -p Environment=LC_ALL=C -p UMask=0027 \
    -p PrivateNetwork=yes -p IPAddressDeny=any -p RestrictAddressFamilies=AF_UNIX \
    -p ProtectSystem=strict -p ReadWritePaths=$R -p ProtectHome=yes \
    -p PrivateTmp=yes -p PrivateDevices=yes -p ProtectProc=invisible -p NoNewPrivileges=yes \
    -p CapabilityBoundingSet= -p ProtectKernelTunables=yes -p ProtectKernelModules=yes \
    -p ProtectControlGroups=yes -p RestrictSUIDSGID=yes -p LockPersonality=yes \
    -p MemoryMax=1G -p TasksMax=16 -p CPUQuota=100% -p RuntimeMaxSec=180 \
    /usr/bin/python3.10 -B -m agent_bench.observation.executor \
      --mission docs/agents/observation/examples/cartographer_zone_mission.json \
      --checkout $CK --reports $R --runner-id obs-repo-cartographer-ro-01 \
      --code-sha $S --analysed-sha $ANALYSED < /dev/null | tee $P/invocation.out
  RC=${PIPESTATUS[0]}
  echo "code=$RC"
  chown lecanada26:lecanada26 $P/invocation.out
  [ "$RC" = 0 ] || fail "code de sortie $RC"
  grep -q '"outcome": "PUBLISHED"' $P/invocation.out && grep -q '"state": "COMPLETED"' $P/invocation.out \
    && grep -q '"result_status": "PARTIAL"' $P/invocation.out \
    && grep -q '"content_sha256": "67bdcc05ec67e54013991028275d78ff4727c299fe2f9b6762c2b3da35a3fa4e"' $P/invocation.out \
    || fail "sortie d'invocation inattendue"
  ok "invocation PUBLISHED/COMPLETED/PARTIAL, content_sha256 67bdcc05…"
  stat -c '%a %U:%G %n' $R/runs/* $R/runs/*/* $R/locks/*
  for f in $R/runs/* ; do [ "$(stat -c '%a %G' $f)" = "2750 cat-obs-read" ] || fail "mode $f"; done
  for f in $R/runs/*/* $R/locks/*; do [ "$(stat -c '%a %G' $f)" = "640 cat-obs-read" ] || fail "mode $f"; done
  ok "dossiers 2750, fichiers 640, groupe cat-obs-read"
  sha256sum $R/runs/*/*.json $R/locks/* | tee $P/envelope.sha
  python3 -c 'import json,glob;[print(e["invocation_id"],e["state"],e["result_status"],e["content_sha256"]) for e in map(lambda p:json.load(open(p)),glob.glob("/srv/cat-obs/reports/runs/*/*.json"))]' | tee $P/envelope.id
  [ "$(wc -l < $P/envelope.id)" = 1 ] || fail "nombre d'enveloppes"
  grep -q " COMPLETED PARTIAL 67bdcc05ec67e54013991028275d78ff4727c299fe2f9b6762c2b3da35a3fa4e$" $P/envelope.id || fail "enveloppe"
  chown lecanada26:lecanada26 $P/envelope.sha $P/envelope.id
  ok "enveloppe sur disque conforme (traces locales $P, jamais publiées)"
  ;;
rollback)
  do_rollback
  ;;
*) echo "usage: sudo bash $0 access|install|invoke|rollback"; exit 2 ;;
esac
echo "== fin phase $PH (journal $LOG)"
