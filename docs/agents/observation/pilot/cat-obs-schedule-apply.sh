#!/bin/bash
# RETIRED (P6-GOV-02, 2026-11-26) : remplacé par schedule/cat-obs-schedule-apply.py. Conservé comme
# archive ; ne plus installer (écriture de l'état sensible aux liens symboliques, risque R1).
# Applicateur root du programmateur (exception d'écriture unique, Mathieu 2026-11-22 07:23Z).
# Déclenché par cat-obs-schedule.path à chaque nouvelle demande déposée par l'API.
# Lit UN mot, le compare à une liste fermée, règle le timer de l'agent, publie l'état appliqué.
# N'exécute jamais le contenu de la demande ; tout mot inconnu est refusé et journalisé.
set -uo pipefail
C=/srv/cat-obs/control
AGENT=repository-cartographer
REQ=$C/$AGENT.rhythm
STATUS=$C/$AGENT.status.json
UNIT=cat-obs-cartographer
DROP=/etc/systemd/system/$UNIT.timer.d
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
publish() {  # $1 = rythme appliqué
  local nxt=""
  if [ "$1" != off ]; then
    local us; us=$(systemctl show $UNIT.timer -p NextElapseUSecRealtime --value)
    [ -n "$us" ] && nxt=$(date -u -d "$us" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || true)
  fi
  local tmp=$C/.$AGENT.status.tmp
  printf '{"applied":"%s","applied_utc":"%s","next_utc":%s}\n' "$1" "$(now)" \
    "$( [ -n "$nxt" ] && printf '"%s"' "$nxt" || printf null )" > $tmp
  chgrp cat-obs-read $tmp && chmod 0640 $tmp && mv -f $tmp $STATUS
}
[ -f "$REQ" ] && [ ! -L "$REQ" ] || exit 0
V=$(head -c 16 "$REQ" | tr -d '[:space:]')
case "$V" in
  10min) CAL='*:0/10' ;;
  1h)    CAL='hourly' ;;
  off)   CAL='' ;;
  *) logger -t cat-obs-schedule "demande refusée (valeur hors liste)"; exit 1 ;;
esac
if [ "$V" = off ]; then
  systemctl disable --now $UNIT.timer >/dev/null 2>&1
  systemctl stop $UNIT.service >/dev/null 2>&1
  publish off; logger -t cat-obs-schedule "appliqué : off (arrêt complet)"; exit 0
fi
[ -f /etc/systemd/system/$UNIT.timer ] || { logger -t cat-obs-schedule "timer de base absent"; exit 1; }
install -d -m 0755 $DROP
printf '[Timer]\nOnCalendar=\nOnCalendar=%s\n' "$CAL" > $DROP/rhythm.conf
chmod 0644 $DROP/rhythm.conf
systemctl daemon-reload
systemctl enable $UNIT.timer >/dev/null 2>&1
systemctl restart $UNIT.timer
publish "$V"; logger -t cat-obs-schedule "appliqué : $V"
