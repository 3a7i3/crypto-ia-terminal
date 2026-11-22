#!/bin/bash
# Installation du Data Provenance Auditor (décision Mathieu 2026-11-22 23:05Z « on commence par le DPA »).
# Même modèle que le cartographe : compte cat-obs-ro, checkout de code immuable, aucune écriture hors du
# dossier de l'agent, aucun réseau pendant l'analyse, arbre analysé = main lu par le suivi du cartographe.
# N'agit pas sur l'API, le web, PAPER, le cartographe ni le scanner.
#
# Usage : sudo bash cat-obs-dpa-root.sh install <sha_code>   puis   sudo bash cat-obs-dpa-root.sh invoke <sha_code>
#         sudo bash cat-obs-dpa-root.sh rollback <sha_code>
set -uo pipefail
P=/home/lecanada26/cat-obs-pilot
SRC=$P/src
FAM=/srv/cat-obs/agent-reports
OBSD=$FAM/observation
D=$OBSD/data-provenance-auditor
UP=/srv/cat-obs/upstream
FOLLOW_ENV=/srv/cat-obs/follow/current.env
PY=/usr/bin/python3.10
U=/etc/systemd/system/cat-obs-dpa
RUNNER=obs-data-provenance-ro-01
[ "$(id -u)" = 0 ] || { echo "ECHEC: lancer avec sudo"; exit 1; }
PH=${1:-}; S=${2:-}
case "$PH" in install|invoke|rollback) ;; *) echo "usage: sudo bash $0 install|invoke|rollback <sha_code>"; exit 2;; esac
[[ "$S" =~ ^[0-9a-f]{40}$ ]] || { echo "ECHEC: sha de code (40 hex) requis"; exit 2; }
CK=/srv/cat-obs/checkout/$S
LOG=$P/dpa-$PH-$(date -u +%Y%m%dT%H%M%SZ).log
exec > >(tee "$LOG") 2>&1
echo "== phase $PH code $S $(date -u +%FT%TZ)"
fail() { echo "ECHEC OBLIGATOIRE: $*"; exit 1; }
ok()   { echo "OK: $*"; }
asro() { runuser -u cat-obs-ro -- env -i PATH=/usr/bin:/bin HOME=/nonexistent LC_ALL=C PYTHONDONTWRITEBYTECODE=1 "$@"; }

case "$PH" in
install)
  id cat-obs-ro >/dev/null 2>&1 || fail "compte cat-obs-ro absent"
  [ -x $PY ] || fail "$PY absent"
  [ -x /usr/local/sbin/cat-obs-prune ] || fail "cat-obs-prune absent"
  [ -s $FOLLOW_ENV ] || fail "suivi de main du cartographe absent ($FOLLOW_ENV)"
  [ -d $UP/.git ] || fail "arbre analysé $UP absent"
  [ -d $D ] && [ ! -L $D ] || fail "$D absent (arborescence agent-reports non préparée)"
  [ -z "$(ls -A $D)" ] || fail "$D non vide : installation déjà faite ?"
  [ ! -e $U.service ] && [ ! -e $U.timer ] || fail "unités déjà présentes"
  # 1. Checkout de code immuable au SHA $S (cloné depuis la copie locale, aucun accès root au réseau)
  if [ ! -d $CK ]; then
    runuser -u lecanada26 -- git -C $SRC cat-file -e $S^{commit} || fail "commit $S absent de $SRC"
    GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=$SRC \
      git clone -q --no-hardlinks $SRC $CK || fail "clone checkout"
    git -C $CK checkout -q --detach $S || fail "checkout $S"
    git -C $CK remote remove origin
    chown -R root:root $CK
    find $CK -type d -exec chmod 0555 {} +
    find $CK -type f -exec chmod 0444 {} +
    git -C $CK ls-files -s | awk '$1=="100755"{print $4}' | (cd $CK && xargs -r chmod 0555)
  fi
  H=$(asro env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=$CK git -C $CK rev-parse HEAD)
  [ "$H" = $S ] || fail "checkout vu par cat-obs-ro = $H"
  [ -z "$(git -C $CK status --porcelain)" ] || fail "checkout modifié"
  ok "checkout de code $CK"
  # 2. Dossier de l'agent : cat-obs-ro écrit, groupe cat-obs-read lit (même modèle que /srv/cat-obs/reports).
  #    Parents préparés en 0750 root : on n'ajoute que la traversée (o+x), jamais la lecture.
  chmod 0751 $FAM $OBSD || fail "traversée des parents"
  chown cat-obs-ro:cat-obs-read $D && chmod 2750 $D || fail "droits de $D"
  asro sh -c "cd $CK && $PY -B -m agent_bench.observation.agents manifest --agent data-provenance-auditor --root $D --write" \
    || fail "MANIFEST.json"
  ok "dossier $D prêt (MANIFEST.json écrit)"
  # 3. Unités (timer installé mais NON activé : la phase invoke l'active après un premier passage réussi)
  cat > $U.service <<UNIT
[Unit]
Description=Data Provenance Auditor - une invocation par heure (:30), sans relance
After=cat-obs-follow.service
[Service]
Type=oneshot
User=cat-obs-ro
Group=cat-obs-ro
WorkingDirectory=$CK
Environment=PYTHONDONTWRITEBYTECODE=1 HOME=/nonexistent LC_ALL=C
EnvironmentFile=$FOLLOW_ENV
UMask=0027
PrivateNetwork=yes
IPAddressDeny=any
RestrictAddressFamilies=AF_UNIX
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
MemoryMax=1G
TasksMax=16
CPUQuota=100%
TimeoutStartSec=180
ExecStartPre=$PY -B -m agent_bench.observation.follow_main --template docs/agents/observation/examples/pilot_mission.json --analysed-sha \${ANALYSED_SHA} --out $D/mission
ExecStart=$PY -B -m agent_bench.observation.executor --agent-id data-provenance-auditor --mission $D/mission/mission.json --checkout $CK --reports $D --runner-id $RUNNER --code-sha $S --analysed-sha \${ANALYSED_SHA} --analysed-tree $UP
ExecStopPost=/bin/sh -c 'for d in $D/runs/*/; do [ -d "\$\$d" ] && /usr/local/sbin/cat-obs-prune "\$\$d"; done; exit 0'
ExecStopPost=$PY -B -m agent_bench.observation.agents summary --agent data-provenance-auditor --root $D --write
UNIT
  cat > $U.timer <<UNIT
[Unit]
Description=Data Provenance Auditor, toutes les heures à la demie
[Timer]
OnCalendar=*-*-* *:30:00
Persistent=false
AccuracySec=1s
[Install]
WantedBy=timers.target
UNIT
  chmod 0644 $U.service $U.timer
  install -d -o cat-obs-ro -g cat-obs-read -m 2750 $D/mission || fail "dossier mission"
  systemctl daemon-reload
  systemd-analyze verify $U.service $U.timer 2>&1 | grep -v -e '^$' | head -5
  ok "unités installées, timer NON activé. Suite : sudo bash $0 invoke $S"
  ;;
invoke)
  [ -e $U.service ] || fail "phase install non faite"
  systemctl start cat-obs-dpa.service
  R=$(systemctl show cat-obs-dpa.service -p Result --value)
  echo "premier passage : $R"
  journalctl -u cat-obs-dpa.service -n 8 --no-pager -o cat
  asro cat $D/summary.json || fail "summary.json absent"
  [ "$R" = success ] || fail "premier passage en échec : timer laissé inactif"
  systemctl enable --now cat-obs-dpa.timer
  systemctl list-timers cat-obs-dpa.timer --no-pager
  ok "DPA actif : un passage par heure à la demie"
  ;;
rollback)
  systemctl disable --now cat-obs-dpa.timer 2>/dev/null
  systemctl stop cat-obs-dpa.service 2>/dev/null
  rm -f $U.service $U.timer; systemctl daemon-reload
  chmod 0750 $FAM $OBSD
  [ ! -e $U.timer ] && [ "$(systemctl is-active cat-obs-dpa.service)" != active ] && ok "DPA arrêté, unités retirées" || fail "unité encore présente"
  echo "Conservés (preuves, CLAUDE.md §5) : $D et le checkout $CK. Rien d'autre n'a été touché."
  ;;
esac
