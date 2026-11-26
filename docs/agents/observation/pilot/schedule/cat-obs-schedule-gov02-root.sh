#!/bin/bash
# P6-GOV-02 — installation, vérification et retour arrière de la chaîne privilégiée du programmateur.
# À exécuter par l'opérateur, en root, sur GO runtime distinct. Ne touche ni aux timers des agents
# (cat-obs-*.timer), ni à leurs drop-ins rhythm.conf, ni aux runners, ni à PAPER/PPL/FIN/Advisor.
#
#   preflight                        lecture seule : empreintes, liens suspects, prérequis
#   install <login[,login…]>         sauvegarde, dossiers requests/state, applicateur, unités, drop-in API
#   verify                           lecture seule : fichiers installés == fichiers de ce dossier
#   rollback <horodatage>            restaure octet à octet la sauvegarde <horodatage>
#
# Tests : CAT_GOV02_ROOT=<racine factice> CAT_GOV02_TEST=1 (aucun appel réel à systemctl/groupadd ;
# les commandes sont prises dans PATH, que les tests remplacent par des bouchons).
set -euo pipefail
umask 077
R="${CAT_GOV02_ROOT:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
G_SCHED="${CAT_GOV02_GROUP_SCHED:-cat-obs-sched}"
G_READ="${CAT_GOV02_GROUP_READ:-cat-obs-read}"
OWNER="${CAT_GOV02_REQUEST_OWNER:-lecanada26}"
UNITS="$R/etc/systemd/system"
APPLIER="$R/usr/local/sbin/cat-obs-schedule-apply"
SCHED="$R/srv/cat-obs/schedule"
CONTROL="$R/srv/cat-obs/control"
API_DROPIN="$UNITS/crypto-operator-api.service.d/zzzzzzzzzzzzzz-schedule-gov02.conf"
WEB_DROPIN="$UNITS/crypto-operator-web.service.d/zzzzzz-schedule-gov02.conf"
OLD_UNITS=(cat-obs-schedule.path cat-obs-schedule.service cat-obs-schedule-dpa.path cat-obs-schedule-dpa.service
           cat-obs-schedule-market.path cat-obs-schedule-market.service)
RHYTHMS=(cat-obs-cartographer cat-obs-dpa cat-obs-market)
LOGIN_RE='^[A-Za-z0-9._%+@-]{1,128}(,[A-Za-z0-9._%+@-]{1,128})*$'

die() { echo "REFUS : $*" >&2; exit 1; }
say() { echo "• $*"; }
need_root() { [ -n "${CAT_GOV02_TEST:-}" ] || [ "$(id -u)" = 0 ] || die "root requis"; }
rhythm_hashes() { for t in "${RHYTHMS[@]}"; do f="$UNITS/$t.timer.d/rhythm.conf"; [ -f "$f" ] && sha256sum "$f" | sed "s#  $R#  #" || echo "ABSENT  /etc/systemd/system/$t.timer.d/rhythm.conf"; done; }

preflight() {
  need_root
  say "applicateur : $(sha256sum "$APPLIER" 2>/dev/null | cut -c1-16 || echo absent)"
  for u in "${OLD_UNITS[@]}"; do [ -e "$UNITS/$u" ] && say "unité présente : $u"; done
  say "rythmes (doivent rester identiques) :"; rhythm_hashes
  if [ -d "$CONTROL" ]; then
    suspects=$(find "$CONTROL" -xdev \( -type l -o -type p -o \( -type f -links +1 \) \) -printf '%M %u:%g %n %p -> %l\n' 2>/dev/null || true)
    [ -z "$suspects" ] && say "aucun lien/FIFO/lien physique dans control" || { echo "$suspects"; die "objets suspects dans control : INCIDENT, ne rien supprimer"; }
  fi
  command -v python3 >/dev/null || die "python3 absent"
  say "API (à relire, ajouts seulement) : $(systemctl show crypto-operator-api.service -p SupplementaryGroups -p ReadWritePaths 2>/dev/null | tr '\n' ' ')"
  say "preflight OK"
}

install_all() {
  need_root
  local logins="${1:-}"; [[ "$logins" =~ $LOGIN_RE ]] || die "liste d'opérateurs invalide"
  preflight >/dev/null
  local ts; ts=$(date -u +%Y%m%dT%H%M%SZ); local B="$R/root/p6-gov-02-backup-$ts"
  install -d -m 0700 "$B/units" "$B/sbin"
  for u in "${OLD_UNITS[@]}"; do [ -e "$UNITS/$u" ] && cp -a "$UNITS/$u" "$B/units/"; done
  [ -e "$APPLIER" ] && cp -a "$APPLIER" "$B/sbin/"
  [ -d "$CONTROL" ] && stat -c '%a' "$CONTROL" > "$B/control.mode"
  rhythm_hashes > "$B/rhythms.sha256"
  for u in "${OLD_UNITS[@]}"; do [[ "$u" == *.path ]] && { systemctl is-enabled "$u" >/dev/null 2>&1 && echo "$u" >> "$B/enabled-paths" || true; }; done
  touch "$B/enabled-paths"
  say "sauvegarde : $B"

  getent group "$G_SCHED" >/dev/null || groupadd --system "$G_SCHED"
  install -d -o root -g root -m 0755 "$SCHED"
  install -d -o root -g "$G_SCHED" -m 2730 "$SCHED/requests"
  install -d -o root -g "$G_READ" -m 2750 "$SCHED/state"
  install -d -o root -g root -m 0755 "$UNITS/cat-obs-cartographer.timer.d"

  systemctl disable --now cat-obs-schedule.path cat-obs-schedule-dpa.path cat-obs-schedule-market.path >/dev/null 2>&1 || true
  rm -f "$UNITS/cat-obs-schedule-dpa.path" "$UNITS/cat-obs-schedule-dpa.service" \
        "$UNITS/cat-obs-schedule-market.path" "$UNITS/cat-obs-schedule-market.service"
  install -o root -g root -m 0755 "$HERE/cat-obs-schedule-apply.py" "$APPLIER"
  install -o root -g root -m 0644 "$HERE/cat-obs-schedule.path" "$UNITS/cat-obs-schedule.path"
  install -o root -g root -m 0644 "$HERE/cat-obs-schedule.service" "$UNITS/cat-obs-schedule.service"
  install -d -o root -g root -m 0755 "$(dirname "$API_DROPIN")" "$(dirname "$WEB_DROPIN")"
  # Ajouts seulement (aucune remise à zéro) : les valeurs de l'unité de base ne sont pas connues du
  # dépôt. L'ancien droit d'écriture sur control est retiré par les permissions (chmod g-w ci-dessous).
  printf '%s\n' '# P6-GOV-02 : écriture limitée au dossier des demandes ; identité opérateur exigée.' '[Service]' \
    "SupplementaryGroups=$G_SCHED" 'ReadWritePaths=/srv/cat-obs/schedule/requests' \
    'Environment=AGENT_SCHEDULE_ROOT=/srv/cat-obs/schedule' "Environment=CAT_OPERATOR_LOGINS=$logins" \
    'UnsetEnvironment=AGENT_SCHEDULE_ALLOW_TEST' > "$API_DROPIN"
  printf '%s\n' '# P6-GOV-02 : liste des opérateurs autorisés (non secrète).' '[Service]' \
    "Environment=CAT_OPERATOR_LOGINS=$logins" > "$WEB_DROPIN"
  chmod 0644 "$API_DROPIN" "$WEB_DROPIN"
  [ -d "$CONTROL" ] && chmod g-w "$CONTROL"

  systemctl daemon-reload
  systemctl enable --now cat-obs-schedule.path
  if [ -n "${CAT_GOV02_TEST:-}" ]; then say "test : publication initiale non exécutée"
  else CAT_SCHEDULE_REQUEST_OWNER="$OWNER" /usr/bin/python3 -I -B "$APPLIER" --publish-only; fi
  rhythm_hashes | diff -q - "$B/rhythms.sha256" >/dev/null || die "rythmes modifiés : lancer rollback $ts"
  say "installé ($ts). Redémarrer l'API et le Web avec la release P6-GOV-02 dans la même fenêtre, puis : verify"
}

verify() {
  local ok=1
  chk() { if [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$(sha256sum "$2" | cut -d' ' -f1)" ]; then say "OK $1"; else echo "ÉCART $1"; ok=0; fi; }
  chk "$APPLIER" "$HERE/cat-obs-schedule-apply.py"
  chk "$UNITS/cat-obs-schedule.path" "$HERE/cat-obs-schedule.path"
  chk "$UNITS/cat-obs-schedule.service" "$HERE/cat-obs-schedule.service"
  for u in cat-obs-schedule-dpa.path cat-obs-schedule-market.path; do [ -e "$UNITS/$u" ] && { echo "ÉCART $u présent"; ok=0; }; done
  [ "$(stat -c '%a %U:%G' "$SCHED/requests")" = "2730 root:$G_SCHED" ] || { echo "ÉCART requests $(stat -c '%a %U:%G' "$SCHED/requests")"; ok=0; }
  [ "$(stat -c '%a %U:%G' "$SCHED/state")" = "2750 root:$G_READ" ] || { echo "ÉCART state $(stat -c '%a %U:%G' "$SCHED/state")"; ok=0; }
  say "rythmes :"; rhythm_hashes
  [ "$ok" = 1 ] && say "verify OK" || die "verify : écarts"
}

rollback() {
  need_root
  local ts="${1:-}"; [[ "$ts" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || die "horodatage attendu"
  local B="$R/root/p6-gov-02-backup-$ts"; [ -d "$B" ] || die "sauvegarde absente : $B"
  systemctl disable --now cat-obs-schedule.path >/dev/null 2>&1 || true
  rm -f "$API_DROPIN" "$WEB_DROPIN" "$UNITS/cat-obs-schedule.path" "$UNITS/cat-obs-schedule.service"
  for f in "$B"/units/*; do [ -e "$f" ] && cp -a "$f" "$UNITS/"; done
  [ -e "$B/sbin/cat-obs-schedule-apply" ] && cp -a "$B/sbin/cat-obs-schedule-apply" "$APPLIER"
  [ -f "$B/control.mode" ] && chmod "$(cat "$B/control.mode")" "$CONTROL"
  systemctl daemon-reload
  while read -r u; do [ -n "$u" ] && systemctl enable --now "$u"; done < "$B/enabled-paths"
  rhythm_hashes | diff -q - "$B/rhythms.sha256" >/dev/null || echo "ATTENTION : rythmes différents de la sauvegarde"
  say "retour arrière effectué ($ts). /srv/cat-obs/schedule conservé comme preuve."
  say "R1 est rouvert : réappliquer le confinement C1 (désactiver les unités .path) si l'incident n'est pas clos."
}

case "${1:-}" in
  preflight) preflight ;;
  install) install_all "${2:-}" ;;
  verify) verify ;;
  rollback) rollback "${2:-}" ;;
  *) echo "usage : $0 preflight | install <logins> | verify | rollback <horodatage>"; exit 2 ;;
esac
