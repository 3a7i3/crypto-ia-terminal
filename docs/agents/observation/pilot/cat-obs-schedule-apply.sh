#!/bin/bash
# RETIRED (P6-GOV-02, 2026-11-26) : remplacé par schedule/cat-obs-schedule-apply.py. Conservé comme
# archive ; ne plus installer (écriture de l'état sensible aux liens symboliques, risque R1).
# Applicateur root du programmateur (exception d'écriture unique, Mathieu 2026-11-22 07:23Z ;
# étendue au Data Provenance Auditor puis au Market Observer le 2026-11-23).
# Déclenché par cat-obs-schedule*.path à chaque nouvelle demande déposée par l'API.
# Usage : cat-obs-schedule-apply [agent]   (sans argument : repository-cartographer, comme avant)
# Lit UN mot, le compare à une liste fermée, règle le timer de l'agent, publie l'état appliqué.
# N'exécute jamais le contenu de la demande ; tout mot ou agent inconnu est refusé et journalisé.
set -uo pipefail
C=/srv/cat-obs/control
AGENT=${1:-repository-cartographer}
case "$AGENT" in
  repository-cartographer) UNIT=cat-obs-cartographer; CAL10='*:0/10'; CAL1H='hourly' ;;
  data-provenance-auditor) UNIT=cat-obs-dpa;          CAL10='*:5/10'; CAL1H='*:30' ;;
  market-observer)         UNIT=cat-obs-market;       CAL10='*:3/10'; CAL1H='*:45' ;;
  *) logger -t cat-obs-schedule "agent refusé (hors liste)"; exit 1 ;;
esac
REQ=$C/$AGENT.rhythm
STATUS=$C/$AGENT.status.json
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
  10min) CAL=$CAL10 ;;
  1h)    CAL=$CAL1H ;;
  off)   CAL='' ;;
  *) logger -t cat-obs-schedule "$AGENT : demande refusée (valeur hors liste)"; exit 1 ;;
esac
if [ "$V" = off ]; then
  systemctl disable --now $UNIT.timer >/dev/null 2>&1
  systemctl stop $UNIT.service >/dev/null 2>&1
  publish off; logger -t cat-obs-schedule "$AGENT appliqué : off (arrêt complet)"; exit 0
fi
[ -f /etc/systemd/system/$UNIT.timer ] || { logger -t cat-obs-schedule "$AGENT : timer de base absent"; exit 1; }
install -d -m 0755 $DROP
printf '[Timer]\nOnCalendar=\nOnCalendar=%s\n' "$CAL" > $DROP/rhythm.conf
chmod 0644 $DROP/rhythm.conf
systemctl daemon-reload
systemctl enable $UNIT.timer >/dev/null 2>&1
systemctl restart $UNIT.timer
publish "$V"; logger -t cat-obs-schedule "$AGENT appliqué : $V"
