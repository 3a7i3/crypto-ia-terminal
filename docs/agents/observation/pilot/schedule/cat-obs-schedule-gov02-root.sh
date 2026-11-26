#!/bin/bash
# P6-GOV-02 (révisé P6-GOV-02-RV) — confinement, installation transactionnelle, vérification et retour
# arrière sécurisé de la chaîne privilégiée du programmateur du Repository Cartographer.
#
# À exécuter par l'opérateur, en root, sur GO runtime distinct, depuis un checkout du commit relu.
# Ne modifie jamais les timers des agents (cat-obs-*.timer), leurs drop-ins rhythm.conf, les runners,
# leurs rapports, ni PAPER/PPL/FIN/Advisor/exchange.
#
#   contain [--check]                 C1 : neutralise les 3 anciennes unités .path et vérifie qu'aucun
#                                     ancien applicateur ne tourne (--check : lecture seule)
#   preflight                         lecture seule : préconditions de l'installation
#   install --logins L --api-release D --web-release W
#                                     sauvegarde → C1 → installation pas à pas, chaque étape vérifiée
#   verify                            lecture seule : critères RV04 (fichiers, releases servies,
#                                     permissions, unités, rythmes, identité, journal, routes, rollback)
#   rollback <horodatage>             retour aux releases API/Web historiques SANS réactiver R1 :
#                                     les anciennes unités restent neutralisées, la planification
#                                     devient indisponible en écriture
#
# Tests : CAT_GOV02_ROOT=<racine factice> CAT_GOV02_TEST=1 ; les commandes systemctl, pgrep, curl,
# groupadd, getent, journalctl, systemd-analyze et tailscale sont prises dans PATH (bouchons en test).
set -Eeuo pipefail
umask 077

R="${CAT_GOV02_ROOT:-}"
TEST="${CAT_GOV02_TEST:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
G_SCHED="${CAT_GOV02_GROUP_SCHED:-cat-obs-sched}"
G_READ="${CAT_GOV02_GROUP_READ:-cat-obs-read}"
G_RELAY="${CAT_GOV02_GROUP_RELAY:-cat-obs-relay}"
OWNER="${CAT_GOV02_REQUEST_OWNER:-lecanada26}"
WAIT_S="${CAT_GOV02_WAIT_S:-30}"

UNITS="$R/etc/systemd/system"
APPLIER="$R/usr/local/sbin/cat-obs-schedule-apply"
APPLIER_REAL=/usr/local/sbin/cat-obs-schedule-apply
SCHED="$R/srv/cat-obs/schedule"
CONTROL="$R/srv/cat-obs/control"
TOKEN_DIR="$R/etc/cat-obs"
TOKEN="$TOKEN_DIR/relay.token"
STATE_FILE="$R/root/p6-gov-02-state"
# Préfixe long : ces drop-ins doivent être lus après tous les drop-ins existants (dont la release P6
# en 40 « z »). verify contrôle de toute façon les valeurs effectives, pas l'ordre des noms.
DROP="zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-p6-gov02"
API_DROPIN="$UNITS/crypto-operator-api.service.d/$DROP.conf"
WEB_DROPIN="$UNITS/crypto-operator-web.service.d/$DROP.conf"
OLD_PATHS=(cat-obs-schedule.path cat-obs-schedule-dpa.path cat-obs-schedule-market.path)
OLD_SERVICES=(cat-obs-schedule.service cat-obs-schedule-dpa.service cat-obs-schedule-market.service)
OLD_FILES=(cat-obs-schedule-dpa.path cat-obs-schedule-dpa.service cat-obs-schedule-market.path cat-obs-schedule-market.service)
NEW_UNITS=(cat-obs-schedule.path cat-obs-schedule.service)
TIMERS=(cat-obs-cartographer cat-obs-dpa cat-obs-market)
API_FILES=(observability/operator_api/app.py observability/operator_api/agent_schedule.py observability/operator_api/operator_identity.py)
WEB_SERVER=frontend/scripts/web01_local_frontend_server.mjs
ROUTES=(/api/operator/v1/agent-invocations/repository-cartographer
        /api/operator/v1/agent-invocations/repository-cartographer/history
        /api/operator/v1/agent-invocations/repository-cartographer/schedule
        /api/operator/v1/agent-invocations/data-provenance-auditor/schedule
        /api/operator/v1/agent-invocations/market-observer/schedule
        /api/operator/v1/runtime-service)
LOGIN_RE='^[A-Za-z0-9._%+@-]{1,128}(,[A-Za-z0-9._%+@-]{1,128})*$'
PHASE="aucune"
DONE=0
TS=""

die() { echo "REFUS : $*" >&2; exit 1; }
say() { echo "• $*"; }
need_root() { [ -n "$TEST" ] || [ "$(id -u)" = 0 ] || die "root requis"; }
sha() { sha256sum "$1" | cut -d' ' -f1; }
mark() { PHASE="$1"; printf '%s %s %s\n' "$2" "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$STATE_FILE"; }
last_state() { [ -f "$STATE_FILE" ] && tail -n1 "$STATE_FILE" | cut -d' ' -f1 || echo "AUCUN"; }

rhythm_snapshot() {   # empreinte des 3 drop-ins + état enabled/active des 3 timers
  local t f
  for t in "${TIMERS[@]}"; do
    f="$UNITS/$t.timer.d/rhythm.conf"
    if [ -f "$f" ] && [ ! -L "$f" ]; then printf '%s  %s.timer.d/rhythm.conf\n' "$(sha "$f")" "$t"
    else printf 'ABSENT  %s.timer.d/rhythm.conf\n' "$t"; fi
    printf 'timer %s %s %s\n' "$t" "$(systemctl is-enabled "$t.timer" 2>/dev/null || true)" "$(systemctl is-active "$t.timer" 2>/dev/null || true)"
  done
}

# ── Préconditions communes ─────────────────────────────────────────────────────────────────────
trusted_dir() {   # dossier réel, root, non inscriptible par groupe/autres
  local d="$1" m
  [ -d "$d" ] && [ ! -L "$d" ] || die "$d : absent ou lien symbolique"
  [ -n "$TEST" ] || [ "$(stat -c %u "$d")" = 0 ] || die "$d : propriétaire non root"
  m=$(stat -c %a "$d"); (( (8#$m & 8#022) == 0 )) || die "$d : inscriptible par groupe ou autres ($m)"
}

control_suspects() {
  [ -d "$CONTROL" ] || return 0
  find "$CONTROL" -xdev \( -type l -o -type p -o -type s -o -type b -o -type c -o \( -type f -links +1 \) \) -printf '%M %u:%g %n %p\n' 2>/dev/null
}

# ── C1 : confinement ───────────────────────────────────────────────────────────────────────────
old_applier_running() { pgrep -f -- "$APPLIER_REAL" >/dev/null 2>&1; }

c1_status() {   # imprime l'état ; code 0 si confiné
  local ok=0 u e a
  for u in "${OLD_PATHS[@]}"; do
    e=$(systemctl is-enabled "$u" 2>/dev/null || true); a=$(systemctl is-active "$u" 2>/dev/null || true)
    printf '  %-34s enabled=%-10s active=%s\n' "$u" "${e:-absent}" "${a:-inconnu}"
    [ "$a" = active ] || [ "$a" = activating ] && ok=1
    [ "$e" = enabled ] && ok=1
  done
  for u in "${OLD_SERVICES[@]}"; do
    a=$(systemctl is-active "$u" 2>/dev/null || true)
    printf '  %-34s active=%s\n' "$u" "${a:-inconnu}"
    [ "$a" = active ] || [ "$a" = activating ] || [ "$a" = deactivating ] && ok=1
  done
  if old_applier_running; then echo "  ancien applicateur : EN COURS"; ok=1; else echo "  ancien applicateur : aucun processus"; fi
  return $ok
}

contain() {
  need_root
  local check="${1:-}" ts B u i
  echo "C1 — état avant :"; if c1_status; then say "C1 déjà en place"; fi
  [ "$check" = "--check" ] && { say "rythmes (lecture seule) :"; rhythm_snapshot; return 0; }
  ts=$(date -u +%Y%m%dT%H%M%SZ); B="$R/root/p6-gov-02-c1-$ts"; install -d -m 0700 "$B"
  rhythm_snapshot > "$B/rhythms.before"; c1_status > "$B/c1.before" || true
  for u in "${OLD_PATHS[@]}"; do
    if [ "$(systemctl is-enabled "$u" 2>/dev/null || true)" = enabled ] || [ "$(systemctl is-active "$u" 2>/dev/null || true)" != inactive ]; then
      systemctl disable --now "$u" || die "C1 : échec de la désactivation de $u (rien d'autre n'est tenté)"
    fi
  done
  for u in "${OLD_SERVICES[@]}"; do
    case "$(systemctl is-active "$u" 2>/dev/null || true)" in active|activating|deactivating|reloading)
      systemctl stop "$u" || die "C1 : échec de l'arrêt de $u" ;; esac
  done
  for ((i = 0; i < WAIT_S; i++)); do old_applier_running || break; sleep 1; done
  rhythm_snapshot > "$B/rhythms.after"; c1_status > "$B/c1.after" || true
  echo "C1 — état après :"; cat "$B/c1.after"
  c1_status >/dev/null || die "C1 incomplet : une unité ou un applicateur reste actif (voir $B/c1.after)"
  diff -q "$B/rhythms.before" "$B/rhythms.after" >/dev/null || die "C1 : rythmes ou timers modifiés pendant le confinement (voir $B)"
  say "C1 en place ($B). Timers, rythmes et runners inchangés ; demandes de rythme non appliquées."
}

# ── Préparation de l'installation (lecture seule) ─────────────────────────────────────────────
check_release() {   # $1=api $2=web
  local api="$1" web="$2" f
  [ -d "$api" ] && [ ! -L "$api" ] || die "release API absente ou lien : $api"
  [ -d "$web/dist" ] && [ -f "$web/server/web01_local_frontend_server.mjs" ] || die "release Web incomplète : $web (dist/ et server/ attendus)"
  for f in "${API_FILES[@]}"; do
    [ -f "$api/$f" ] || die "release API : $f absent"
    [ "$(sha "$api/$f")" = "$(sha "$REPO/$f")" ] || die "release API : $f ≠ dépôt"
  done
  [ "$(sha "$web/server/web01_local_frontend_server.mjs")" = "$(sha "$REPO/$WEB_SERVER")" ] || die "release Web : serveur ≠ dépôt"
}

preflight() {
  need_root
  local s
  trusted_dir "$R/srv"; trusted_dir "$R/srv/cat-obs"; trusted_dir "$R/usr/local/sbin"; trusted_dir "$UNITS"
  [ -d "$R/root" ] || die "$R/root absent"
  s=$(control_suspects); [ -z "$s" ] || { echo "$s"; die "objets suspects dans control : INCIDENT, ne rien supprimer"; }
  getent group "$G_READ" >/dev/null || die "groupe $G_READ absent"
  getent passwd "$OWNER" >/dev/null || die "utilisateur $OWNER absent"
  for t in "${TIMERS[@]}"; do [ -f "$UNITS/$t.timer" ] || die "timer $t.timer absent"; done
  [ -n "$TEST" ] || /usr/bin/python3 -I -c 'import sys; sys.exit(sys.version_info < (3, 8))' || die "python3 ≥ 3.8 requis"
  systemd-analyze verify "$HERE/cat-obs-schedule.path" "$HERE/cat-obs-schedule.service" >/dev/null 2>&1 \
    || die "systemd-analyze verify refuse les unités (version : $(systemctl --version | head -n1))"
  say "systemd : $(systemctl --version | head -n1)"
  say "API : $(systemctl show crypto-operator-api.service -p WorkingDirectory --value 2>/dev/null)"
  say "état d'installation : $(last_state)"
  say "preflight OK"
}

refuse_ambiguous() {
  case "$(last_state)" in
    AUCUN|ROLLED_BACK) ;;
    *) die "état d'installation $(last_state) ($STATE_FILE) : réinstallation ambiguë refusée ; terminer par rollback ou verify" ;;
  esac
  [ ! -e "$SCHED" ] || die "$SCHED existe déjà : réinstallation ambiguë refusée"
  [ ! -e "$API_DROPIN" ] && [ ! -e "$WEB_DROPIN" ] || die "drop-ins P6-GOV-02 déjà présents"
  [ ! -e "$TOKEN" ] || die "$TOKEN existe déjà"
  if [ -f "$APPLIER" ] && [ "$(sha "$APPLIER")" = "$(sha "$HERE/cat-obs-schedule-apply.py")" ]; then
    die "le nouvel applicateur est déjà en place sans état d'installation : situation ambiguë"
  fi
}

backup() {   # $1=dossier ; sauvegarde complète, identifiable, vérifiable
  local B="$1" u d r
  install -d -m 0700 "$B" "$B/units" "$B/sbin" "$B/dropins" "$B/rhythm"
  printf 'P6-GOV-02 sauvegarde\nhorodatage=%s\nsource=%s\napplier_source_sha256=%s\n' \
    "$(basename "$B")" "$REPO" "$(sha "$HERE/cat-obs-schedule-apply.py")" > "$B/LABEL"
  for u in "${OLD_PATHS[@]}" "${OLD_SERVICES[@]}"; do [ -e "$UNITS/$u" ] && cp -a "$UNITS/$u" "$B/units/"; done
  [ -e "$APPLIER" ] && cp -a "$APPLIER" "$B/sbin/"
  for d in crypto-operator-api.service.d crypto-operator-web.service.d; do
    [ -d "$UNITS/$d" ] && cp -a "$UNITS/$d" "$B/dropins/"
  done
  for t in "${TIMERS[@]}"; do [ -d "$UNITS/$t.timer.d" ] && cp -a "$UNITS/$t.timer.d" "$B/rhythm/"; done
  [ -d "$CONTROL" ] && { stat -c '%a %U:%G' "$CONTROL" > "$B/control.mode"; ls -la "$CONTROL" > "$B/control.ls"; }
  rhythm_snapshot > "$B/rhythms"
  for u in "${OLD_PATHS[@]}"; do echo "$u $(systemctl is-enabled "$u" 2>/dev/null || true) $(systemctl is-active "$u" 2>/dev/null || true)"; done > "$B/old-units.state"
  for s in crypto-operator-api crypto-operator-web; do
    for p in WorkingDirectory BindReadOnlyPaths SupplementaryGroups MainPID; do
      printf '%s %s=%s\n' "$s" "$p" "$(systemctl show "$s.service" -p "$p" --value 2>/dev/null || true)"
    done
  done > "$B/services.state"
  systemctl --version | head -n1 > "$B/systemd.version"
  tailscale serve status > "$B/tailscale-serve.txt" 2>&1 || true
  for r in "${ROUTES[@]}"; do printf '%s %s %s\n' "$r" "$(route_code 8090 "$r")" "$(route_code 8181 "$r")"; done > "$B/routes.codes"
  (cd "$B" && find . -type f ! -name MANIFEST.sha256 -print0 | sort -z | xargs -0 sha256sum) > "$B/MANIFEST.sha256"
  (cd "$B" && sha256sum -c --quiet MANIFEST.sha256) || die "sauvegarde illisible après écriture"
}

route_code() { curl -s -o /dev/null -m 5 -w '%{http_code}' "http://127.0.0.1:$1$2" 2>/dev/null || echo 000; }

# ── Installation transactionnelle ─────────────────────────────────────────────────────────────
# Toute sortie avant la fin (refus, erreur, signal) laisse une trace PARTIAL et la marche à suivre.
on_exit() {
  local rc=$?
  [ "$DONE" = 1 ] || [ "$PHASE" = aucune ] && return 0
  if [ "$MODE" = rollback ]; then
    printf 'ROLLBACK_PARTIAL %s %s\n' "$PHASE" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$STATE_FILE"
    echo "ÉCHEC du retour arrière pendant « $PHASE » (code $rc). Les anciennes unités ne sont pas réactivées." >&2
  else
    printf 'PARTIAL %s %s\n' "$PHASE" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$STATE_FILE"
    echo "ÉCHEC pendant « $PHASE » (code $rc). Installation partielle ; R1 reste confiné si l'étape c1 est passée." >&2
    echo "Lancer : $0 rollback $TS   (n'active jamais les anciennes unités)" >&2
  fi
}
MODE=""
trap on_exit EXIT
trap 'exit 130' INT TERM HUP

write_dropins() {   # $1=logins $2=api_release $3=web_release
  local api_dir web_dir
  api_dir="$(dirname "$API_DROPIN")"; web_dir="$(dirname "$WEB_DROPIN")"
  [ -d "$api_dir" ] && [ -d "$web_dir" ] || die "dossiers de drop-ins API/Web absents"
  printf '%s\n' '# P6-GOV-02 : release, écriture limitée au dossier des demandes, identité et transport vérifiés.' \
    '[Service]' "WorkingDirectory=$2" "BindReadOnlyPaths=$2" \
    "SupplementaryGroups=$G_SCHED $G_RELAY" 'ReadWritePaths=/srv/cat-obs/schedule/requests' \
    'Environment=AGENT_SCHEDULE_ROOT=/srv/cat-obs/schedule' "Environment=CAT_OPERATOR_LOGINS=$1" \
    'Environment=CAT_RELAY_TOKEN_FILE=/etc/cat-obs/relay.token' 'UnsetEnvironment=AGENT_SCHEDULE_ALLOW_TEST' > "$API_DROPIN.tmp"
  printf '%s\n' '# P6-GOV-02 : release Web, opérateurs autorisés (non secret), jeton du relais par groupe.' \
    '[Service]' 'BindReadOnlyPaths=' \
    "BindReadOnlyPaths=$3/dist:/opt/cat-app/releases/CAT-FOOTPRINT-FINANCE-V6-RC1/frontend/dist $3/server/web01_local_frontend_server.mjs:/opt/cat-app/releases/CAT-FOOTPRINT-FINANCE-V6-RC1/frontend/scripts/web01_local_frontend_server.mjs" \
    "SupplementaryGroups=$G_RELAY" "Environment=CAT_OPERATOR_LOGINS=$1" \
    'Environment=CAT_RELAY_TOKEN_FILE=/etc/cat-obs/relay.token' > "$WEB_DROPIN.tmp"
  chmod 0644 "$API_DROPIN.tmp" "$WEB_DROPIN.tmp"
  mv -f "$API_DROPIN.tmp" "$API_DROPIN"; mv -f "$WEB_DROPIN.tmp" "$WEB_DROPIN"
}

expect_mode() {   # chemin mode propriétaire:groupe
  local got; got=$(stat -c '%a %U:%G' "$1")
  if [ -n "$TEST" ]; then [ "${got%% *}" = "$2" ] || die "$1 : $got, attendu $2 $3"
  else [ "$got" = "$2 $3" ] || die "$1 : $got, attendu $2 $3"; fi
}

wait_restart() {   # unité ancien_pid
  local i pid st
  for ((i = 0; i < WAIT_S; i++)); do
    st=$(systemctl is-active "$1" 2>/dev/null || true); pid=$(systemctl show "$1" -p MainPID --value 2>/dev/null || echo 0)
    [ "$st" = active ] && [ "$pid" != 0 ] && [ "$pid" != "$2" ] && return 0
    sleep 1
  done
  die "$1 n'a pas redémarré (état $st, PID $pid)"
}

install_all() {
  need_root
  local logins="" api="" web="" u old_api old_web
  while [ $# -gt 0 ]; do
    case "$1" in
      --logins) logins="${2:-}"; shift 2 ;;
      --api-release) api="${2:-}"; shift 2 ;;
      --web-release) web="${2:-}"; shift 2 ;;
      *) die "argument inconnu : $1" ;;
    esac
  done
  [[ "$logins" =~ $LOGIN_RE ]] || die "liste d'opérateurs invalide"
  [ -n "$api" ] && [ -n "$web" ] || die "--api-release et --web-release requis"
  [[ "$api$web" != *[[:space:]:]* ]] || die "chemins de release : espaces et « : » interdits"
  preflight >/dev/null
  refuse_ambiguous
  check_release "$R$api" "$R$web"
  [ -f "$HERE/cat-obs-schedule.path" ] && [ -f "$HERE/cat-obs-schedule.service" ] || die "unités source absentes"

  TS=$(date -u +%Y%m%dT%H%M%SZ); local B="$R/root/p6-gov-02-backup-$TS"
  MODE=install
  mark backup START; backup "$B"; say "sauvegarde : $B"

  mark c1 STEP; contain >/dev/null

  mark groups STEP
  getent group "$G_SCHED" >/dev/null || groupadd --system "$G_SCHED"
  getent group "$G_RELAY" >/dev/null || groupadd --system "$G_RELAY"
  getent group "$G_SCHED" >/dev/null && getent group "$G_RELAY" >/dev/null || die "groupes absents après création"

  mark token STEP
  install -d -o root -g root -m 0755 "$TOKEN_DIR"
  ( umask 077; /usr/bin/env python3 -I -c 'import secrets; print(secrets.token_hex(32))' > "$TOKEN.tmp" )
  [ -n "$TEST" ] || chown root:"$G_RELAY" "$TOKEN.tmp"
  chmod 0640 "$TOKEN.tmp"; mv -f "$TOKEN.tmp" "$TOKEN"; expect_mode "$TOKEN" 640 "root:$G_RELAY"

  mark dirs STEP
  install -d -o root -g root -m 0755 "$SCHED"
  install -d -o root -g "$G_SCHED" -m 2730 "$SCHED/requests"
  install -d -o root -g "$G_READ" -m 2750 "$SCHED/state"
  expect_mode "$SCHED/requests" 2730 "root:$G_SCHED"; expect_mode "$SCHED/state" 2750 "root:$G_READ"
  trusted_dir "$SCHED"

  mark units STEP
  for u in "${OLD_FILES[@]}"; do rm -f "$UNITS/$u"; [ ! -e "$UNITS/$u" ] || die "$u non retiré"; done
  install -o root -g root -m 0755 "$HERE/cat-obs-schedule-apply.py" "$APPLIER"
  for u in "${NEW_UNITS[@]}"; do install -o root -g root -m 0644 "$HERE/$u" "$UNITS/$u"; done
  [ "$(sha "$APPLIER")" = "$(sha "$HERE/cat-obs-schedule-apply.py")" ] || die "applicateur installé ≠ source"

  mark dropins STEP; write_dropins "$logins" "$api" "$web"
  mark control STEP; [ -d "$CONTROL" ] && chmod g-w "$CONTROL"

  mark reload STEP
  systemctl daemon-reload
  [ "$(systemctl show crypto-operator-api.service -p WorkingDirectory --value)" = "$api" ] || die "release API effective ≠ $api"
  systemctl show crypto-operator-api.service -p Environment --value | grep -q "CAT_RELAY_TOKEN_FILE=" || die "environnement API non appliqué"
  systemctl enable --now cat-obs-schedule.path
  [ "$(systemctl is-active cat-obs-schedule.path)" = active ] || die "cat-obs-schedule.path inactive"
  for u in cat-obs-schedule-dpa.path cat-obs-schedule-market.path; do
    [ "$(systemctl is-active "$u" 2>/dev/null || true)" != active ] || die "$u encore active"
  done

  mark publish STEP
  if [ -n "$TEST" ]; then install -m 0640 /dev/null "$SCHED/state/repository-cartographer.json"
  else CAT_SCHEDULE_REQUEST_OWNER="$OWNER" /usr/bin/python3 -I -B "$APPLIER" --publish-only; fi
  [ -f "$SCHED/state/repository-cartographer.json" ] || die "état initial non publié"

  mark restart STEP
  old_api=$(systemctl show crypto-operator-api.service -p MainPID --value); old_web=$(systemctl show crypto-operator-web.service -p MainPID --value)
  systemctl restart crypto-operator-api.service; wait_restart crypto-operator-api.service "$old_api"
  systemctl restart crypto-operator-web.service; wait_restart crypto-operator-web.service "$old_web"

  mark rhythms STEP
  diff -q <(rhythm_snapshot) "$B/rhythms" >/dev/null || die "rythmes ou timers modifiés"
  mark "$TS" INSTALLED; DONE=1
  say "installé ($TS). Lancer maintenant : $0 verify"
}

# ── Vérification (lecture seule) ──────────────────────────────────────────────────────────────
verify() {
  local ok=1 ts B api web u v
  bad() { echo "ÉCART $*"; ok=0; }
  good() { say "OK $*"; }
  [ "$(last_state)" = INSTALLED ] && good "état INSTALLED" || bad "état $(last_state)"
  ts=$(grep '^INSTALLED ' "$STATE_FILE" 2>/dev/null | tail -n1 | cut -d' ' -f2); B="$R/root/p6-gov-02-backup-$ts"
  # 1. empreintes source == installé
  [ "$(sha "$APPLIER")" = "$(sha "$HERE/cat-obs-schedule-apply.py")" ] && good applicateur || bad applicateur
  for u in "${NEW_UNITS[@]}"; do [ "$(sha "$UNITS/$u")" = "$(sha "$HERE/$u")" ] && good "$u" || bad "$u"; done
  # 2. releases réellement servies
  api=$(systemctl show crypto-operator-api.service -p WorkingDirectory --value)
  for u in "${API_FILES[@]}"; do [ -f "$R$api/$u" ] && [ "$(sha "$R$api/$u")" = "$(sha "$REPO/$u")" ] && good "API $u" || bad "API $u ($api)"; done
  if [ -z "$TEST" ]; then
    v=$(readlink "/proc/$(systemctl show crypto-operator-api.service -p MainPID --value)/cwd" 2>/dev/null || true)
    [ "$v" = "$api" ] && good "processus API dans $api" || bad "processus API dans « $v »"
  fi
  web=$(grep -o 'BindReadOnlyPaths=[^ ]*/dist:' "$WEB_DROPIN" 2>/dev/null | sed 's/BindReadOnlyPaths=//; s#/dist:##' || true)
  [ -n "$web" ] && [ "$(sha "$R$web/server/web01_local_frontend_server.mjs")" = "$(sha "$REPO/$WEB_SERVER")" ] && good "Web serveur ($web)" || bad "Web serveur"
  systemctl show crypto-operator-web.service -p BindReadOnlyPaths --value | grep -q "$web/server/web01_local_frontend_server.mjs" && good "Web monté" || bad "Web non monté"
  # 3. permissions effectives
  check_mode() { local g; g=$(stat -c '%a %U:%G' "$1" 2>/dev/null || echo absent); if [ -n "$TEST" ]; then [ "${g%% *}" = "$2" ]; else [ "$g" = "$2 $3" ]; fi && good "$1 $g" || bad "$1 $g (attendu $2 $3)"; }
  check_mode "$SCHED/requests" 2730 "root:$G_SCHED"; check_mode "$SCHED/state" 2750 "root:$G_READ"
  check_mode "$TOKEN" 640 "root:$G_RELAY"; check_mode "$APPLIER" 755 root:root
  for d in "$R/srv" "$R/srv/cat-obs" "$SCHED" "$R/usr/local/sbin" "$UNITS"; do (trusted_dir "$d") >/dev/null 2>&1 && good "parent $d" || bad "parent $d"; done
  [ -d "$CONTROL" ] && { (( (8#$(stat -c %a "$CONTROL") & 8#020) == 0 )) && good "control sans écriture de groupe" || bad "control inscriptible par le groupe"; }
  # 4. unités
  for u in "${OLD_FILES[@]}"; do [ ! -e "$UNITS/$u" ] && good "$u absent" || bad "$u présent"; done
  for u in cat-obs-schedule-dpa.path cat-obs-schedule-market.path; do [ "$(systemctl is-active "$u" 2>/dev/null || true)" != active ] && good "$u inactive" || bad "$u active"; done
  [ "$(systemctl is-enabled cat-obs-schedule.path 2>/dev/null || true)" = enabled ] && [ "$(systemctl is-active cat-obs-schedule.path 2>/dev/null || true)" = active ] && good "cat-obs-schedule.path active" || bad "cat-obs-schedule.path"
  old_applier_running && bad "un applicateur tourne en dehors d'une demande" || good "aucun applicateur en cours"
  for v in ProtectSystem=strict NoNewPrivileges=yes PrivateNetwork=yes; do
    [ "$(systemctl show cat-obs-schedule.service -p "${v%%=*}" --value)" = "${v#*=}" ] && good "service $v" || bad "service $v non effectif"
  done
  # 5. rythmes
  [ -f "$B/rhythms" ] && diff -q <(rhythm_snapshot) "$B/rhythms" >/dev/null && good "rythmes et timers identiques à la sauvegarde" || bad "rythmes ou timers"
  # 6. identité et transport (GET en lecture seule, sans en-tête forgé)
  v=$(curl -s -m 5 http://127.0.0.1:8090/api/operator/v1/operator-identity || true)
  [[ "$v" == *'"authorized":false'* && "$v" == *RELAY_TOKEN_INVALID* ]] && good "API : transport sans jeton refusé" || bad "API identité : $v"
  v=$(curl -s -m 5 http://127.0.0.1:8181/api/operator/v1/operator-identity || true)
  [[ "$v" == *'"authorized":false'* && "$v" == *OPERATOR_IDENTITY_REQUIRED* ]] && good "relais : sans identité Tailscale refusé" || bad "relais identité : $v"
  systemctl show crypto-operator-api.service -p Environment --value | grep -q 'CAT_OPERATOR_LOGINS=[A-Za-z0-9]' && good "liste d'opérateurs effective (API)" || bad "liste API"
  systemctl show crypto-operator-web.service -p Environment --value | grep -q 'CAT_RELAY_TOKEN_FILE=' && good "jeton configuré (Web)" || bad "jeton Web"
  # 7. journal
  journalctl -u cat-obs-schedule.service -n 1 --no-pager >/dev/null 2>&1 && good "journal du service lisible" || bad "journal du service"
  # 8. systemd réel (aucune conclusion tirée d'un bouchon)
  v=$(systemctl --version | head -n1); say "systemd : $v"
  if [ -n "$TEST" ]; then say "TEST : compatibilité systemd NON démontrée (bouchon)"
  else systemd-analyze verify "$UNITS/cat-obs-schedule.path" "$UNITS/cat-obs-schedule.service" >/dev/null 2>&1 && good "systemd-analyze verify" || bad "systemd-analyze verify"; fi
  # 9. non-régression des routes historiques (codes == sauvegarde)
  if [ -f "$B/routes.codes" ]; then
    while read -r r a w; do
      [ "$(route_code 8090 "$r")" = "$a" ] && [ "$(route_code 8181 "$r")" = "$w" ] && good "route $r ($a/$w)" || bad "route $r ≠ $a/$w"
    done < "$B/routes.codes"
  else bad "codes de routes de référence absents"; fi
  # 10. capacité de retour arrière
  [ -f "$B/MANIFEST.sha256" ] && (cd "$B" && sha256sum -c --quiet MANIFEST.sha256) >/dev/null 2>&1 && good "sauvegarde $ts intègre" || bad "sauvegarde $ts"
  [ "$ok" = 1 ] && say "verify OK" || die "verify : écarts"
}

# ── Retour arrière sécurisé ───────────────────────────────────────────────────────────────────
rollback() {
  need_root
  local ts="${1:-}" B u old_api old_web exp
  [[ "$ts" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || die "horodatage attendu"
  B="$R/root/p6-gov-02-backup-$ts"; [ -d "$B" ] || die "sauvegarde absente : $B"
  (cd "$B" && sha256sum -c --quiet MANIFEST.sha256) >/dev/null 2>&1 || die "sauvegarde altérée : aucun retour arrière (C1 inchangé)"
  TS="$ts"; MODE=rollback; PHASE="rollback"
  PHASE="c1"; contain >/dev/null
  PHASE="nouvelle-chaine"
  if [ "$(systemctl is-active cat-obs-schedule.path 2>/dev/null || true)" != inactive ] || [ "$(systemctl is-enabled cat-obs-schedule.path 2>/dev/null || true)" = enabled ]; then
    systemctl disable --now cat-obs-schedule.path
  fi
  rm -f "$UNITS/cat-obs-schedule.path" "$UNITS/cat-obs-schedule.service" "$API_DROPIN" "$WEB_DROPIN"
  PHASE="releases"
  systemctl daemon-reload
  exp=$(grep '^crypto-operator-api WorkingDirectory=' "$B/services.state" | cut -d= -f2-)
  [ "$(systemctl show crypto-operator-api.service -p WorkingDirectory --value)" = "$exp" ] || die "release API historique non restaurée ($exp)"
  old_api=$(systemctl show crypto-operator-api.service -p MainPID --value); old_web=$(systemctl show crypto-operator-web.service -p MainPID --value)
  systemctl restart crypto-operator-api.service; wait_restart crypto-operator-api.service "$old_api"
  systemctl restart crypto-operator-web.service; wait_restart crypto-operator-web.service "$old_web"
  PHASE="controle"
  c1_status >/dev/null || die "une ancienne unité est active après retour arrière"
  for u in "${OLD_PATHS[@]}"; do [ "$(systemctl is-enabled "$u" 2>/dev/null || true)" != enabled ] || die "$u réactivée"; done
  diff -q <(rhythm_snapshot) "$B/rhythms" >/dev/null || echo "ATTENTION : rythmes ou timers différents de la sauvegarde"
  mark "$ts" ROLLED_BACK; DONE=1
  say "retour arrière effectué ($ts) : releases historiques servies, anciennes unités NEUTRALISÉES (R1 confiné)."
  say "La planification est indisponible en écriture ; lecture des états et rapports conservée."
  say "Anciennes unités et ancien applicateur conservés uniquement dans $B (preuve) ; ne pas les réinstaller."
}

case "${1:-}" in
  contain) contain "${2:-}" ;;
  preflight) preflight ;;
  install) shift; install_all "$@" ;;
  verify) verify ;;
  rollback) rollback "${2:-}" ;;
  *) echo "usage : $0 contain [--check] | preflight | install --logins L --api-release D --web-release W | verify | rollback <horodatage>"; exit 2 ;;
esac
