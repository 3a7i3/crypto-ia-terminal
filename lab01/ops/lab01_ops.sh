#!/usr/bin/env bash
# LAB-01 — installation / vérification / retrait sur l'hôte. SOURCE PRÉPARÉE, NON EXÉCUTÉE, INACTIVE.
#
# S'exécute uniquement depuis un staging root protégé /root/lab01-staging/<commit> (jamais depuis
# un clone modifiable). Aucun paramètre par l'environnement (pas de sudo -E). Modes :
#   plan                                              lecture seule, n'écrit rien
#   verify-staging --commit C --manifest-sha256 H     le paquet est celui qui a été épinglé et publié
#   preflight      --commit C --manifest-sha256 H     préconditions de l'hôte (lecture seule)
#   status                                            état réel de chaque étape (lecture seule)
#   apply  --auth ID --commit C --bundle F --bundle-sha256 H --manifest-sha256 H
#   remove --auth ID                                  conserve preuves et expériences ; pas de purge
#   verify                                            relevé de l'installation (lecture seule)
# `apply` est reprenable : chaque étape contrôle l'état réel et est atomique (fichier temporaire puis
# renommage) ; un échec laisse un état partiel INERTE (aucune unité activée ni démarrée).
# `remove` écrit d'abord un dossier de preuves vérifié ; si ce dossier ne peut pas être vérifié,
# RIEN n'est retiré.
set -euo pipefail

LAB_USER=lab01; ROOT_USER=root; ROOT_GRP=root
LAB_ROOT=/srv/lab01; DATA="$LAB_ROOT/data"; STATE_DIR=/var/lib/lab01
IMG="$STATE_DIR/lab01.img"; IMG_MB=64; UNIT_DIR=/etc/systemd/system; PORT=18090
JOURNAL="$STATE_DIR/install.journal"; EVID_DIR="$STATE_DIR/evidence"
MIN_FREE_MB=256; MIN_AVAIL_MEM_MB=512
UNITS=(lab01.slice srv-lab01-data.mount lab01-run.service lab01-export.service lab01-api.service)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTH=""; BUNDLE=""; BUNDLE_SHA=""; MANIFEST_SHA=""; COMMIT=""; MODE=""

say() { printf '%s\n' "$*"; }
die() { say "REFUS : $*"; exit "${2:-3}"; }
now() { date -u +%Y%m%dT%H%M%SZ; }
is_root() { [ "$(id -u)" -eq 0 ]; }
run() { say "\$ $*"; "$@" 2>&1 || say "[rc=$?]"; }

need_auth() {
  is_root || die "root requis pour $MODE"
  [ -n "$AUTH" ] || die "--auth (identifiant de l'autorisation opérateur) absent"
  say "autorisation citée : $AUTH"
}
no_prod_refs() {  # les unités LAB ne doivent référencer aucune unité de production
  if grep -En '^(Requires|Wants|After|Before|BindsTo|PartOf|Conflicts|Upholds|OnFailure)=.*(crypto-|paper-|ollama)' \
      "$HERE"/systemd/*; then die "référence de production dans une unité LAB" 4; fi
}
need_hex() { [[ "$2" =~ ^[0-9a-f]{$3}$ ]] || die "$1 ($3 hex) requis" 5; }

verify_staging() {
  need_hex --commit "$COMMIT" 40; need_hex --manifest-sha256 "$MANIFEST_SHA" 64
  [ -f "$HERE/INSTALLER.sha256" ] || die "INSTALLER.sha256 absent du staging" 5
  [ "$(sha256sum "$HERE/INSTALLER.sha256" | cut -d' ' -f1)" = "$MANIFEST_SHA" ] \
    || die "empreinte du manifeste d'installation différente de celle publiée" 5
  (cd "$HERE" && sha256sum --strict --quiet -c INSTALLER.sha256) \
    || die "un fichier d'installation diffère du manifeste" 5
  local listed present
  listed="$(awk '{print $2}' "$HERE/INSTALLER.sha256" | sed 's#^\*##' | sort)"
  present="$(cd "$HERE" && find . -type f ! -name INSTALLER.sha256 ! -name '*.tar.gz' | sed 's#^\./##' | sort)"
  [ "$listed" = "$present" ] || die "fichiers du staging différents du manifeste (en trop ou manquants)" 5
  [ "$(tr -d '[:space:]' <"$HERE/COMMIT")" = "$COMMIT" ] || die "le commit épinglé dans le paquet n'est pas $COMMIT" 5
  [ "$(basename "$HERE")" = "$COMMIT" ] || die "le staging doit s'appeler <commit> (trouvé : $(basename "$HERE"))" 5
  no_prod_refs
  say "staging vérifié : commit $COMMIT, manifeste $MANIFEST_SHA, fichiers conformes"
}
staging_perms() {  # le staging doit être à root et non inscriptible par d'autres : pas de TOCTOU
  [ "$(find "$HERE" ! -user "$ROOT_USER" | wc -l)" -eq 0 ] || die "staging contient des fichiers non root" 5
  [ "$(find "$HERE" -perm /022 | wc -l)" -eq 0 ] || die "staging inscriptible par groupe/autres" 5
}

# ---- préconditions (lecture seule) ------------------------------------------------------------
PF_FAIL=0; PF_UNK=0
pf() {  # pf STATUT texte
  say "PRÉCONDITION $1 : $2"
  case "$1" in FAIL) PF_FAIL=$((PF_FAIL + 1));; INDÉTERMINÉ) PF_UNK=$((PF_UNK + 1));; esac
}
nearest_dir() { local d="$1"; while [ ! -d "$d" ]; do d="$(dirname "$d")"; done; printf '%s' "$d"; }
preflight() {
  PF_FAIL=0; PF_UNK=0
  local c
  for c in python3.11 mkfs.ext4 mount truncate useradd tar sha256sum systemd-analyze install findmnt ss; do
    if command -v "$c" >/dev/null 2>&1; then pf PASS "commande $c présente"; else pf FAIL "commande $c absente"; fi
  done
  local sv; sv="$(systemctl --version 2>/dev/null | awk 'NR==1{print $2}')" || sv=""
  if [[ "$sv" =~ ^[0-9]+$ ]] && [ "$sv" -ge 249 ]; then pf PASS "systemd $sv (≥ 249)"
  elif [[ "$sv" =~ ^[0-9]+$ ]]; then pf FAIL "systemd $sv < 249 (propriétés des unités non garanties)"
  else pf INDÉTERMINÉ "version de systemd illisible"; fi
  if [ -e /dev/loop-control ]; then pf PASS "support loop présent (/dev/loop-control)"
  else pf INDÉTERMINÉ "/dev/loop-control absent : le montage loop peut échouer (le montage est l'étape qui tranche)"; fi
  local d free; d="$(nearest_dir "$STATE_DIR")"
  free="$(df -Pm "$d" 2>/dev/null | awk 'NR==2{print $4}')" || free=""
  if [[ "$free" =~ ^[0-9]+$ ]] && [ "$free" -ge "$MIN_FREE_MB" ]; then pf PASS "espace libre ${free} Mo sur $d (≥ ${MIN_FREE_MB} : image ${IMG_MB} + preuves ${IMG_MB} + marge)"
  elif [[ "$free" =~ ^[0-9]+$ ]]; then pf FAIL "espace libre ${free} Mo sur $d < ${MIN_FREE_MB}"
  else pf INDÉTERMINÉ "espace libre illisible sur $d"; fi
  local mem; mem="$(awk '/^MemAvailable:/{print int($2/1024)}' /proc/meminfo 2>/dev/null)" || mem=""
  if [[ "$mem" =~ ^[0-9]+$ ]] && [ "$mem" -ge "$MIN_AVAIL_MEM_MB" ]; then pf PASS "mémoire disponible ${mem} Mo à cet instant (≥ ${MIN_AVAIL_MEM_MB} ; relevé ponctuel)"
  elif [[ "$mem" =~ ^[0-9]+$ ]]; then pf FAIL "mémoire disponible ${mem} Mo < ${MIN_AVAIL_MEM_MB}"
  else pf INDÉTERMINÉ "mémoire disponible illisible"; fi
  if ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${PORT}\$"; then pf FAIL "le port $PORT est déjà en écoute"
  else pf PASS "port $PORT libre (vu par ss ; propriétaire non nécessaire)"; fi
  local pw
  if pw="$(getent passwd "$LAB_USER" 2>/dev/null)"; then
    local uid shell grp
    uid="$(cut -d: -f3 <<<"$pw")"; shell="$(cut -d: -f7 <<<"$pw")"
    grp="$(id -Gn "$LAB_USER" 2>/dev/null | tr ' ' '\n' | grep -vxc "$LAB_USER" || true)"
    if [ "$uid" -lt 1000 ] && [[ "$shell" == */nologin || "$shell" == */false ]] && [ "${grp:-0}" -eq 0 ]; then
      pf PASS "utilisateur $LAB_USER déjà présent et conforme (uid $uid, $shell, sans groupe additionnel)"
    else pf FAIL "utilisateur $LAB_USER présent mais non conforme (uid $uid, shell $shell, ${grp:-?} groupe(s) additionnel(s))"; fi
  else pf PASS "utilisateur $LAB_USER absent : sera créé"; fi
  local src
  if findmnt -rn "$DATA" >/dev/null 2>&1; then
    src="$(findmnt -rno SOURCE "$DATA" 2>/dev/null)"
    if [ "$src" = "$IMG" ] || losetup -j "$IMG" 2>/dev/null | grep -q "^$src"; then pf PASS "$DATA déjà monté depuis l'image LAB"
    else pf FAIL "$DATA est monté depuis autre chose ($src) : refus"; fi
  else pf PASS "$DATA non monté"; fi
  local u
  for u in "${UNITS[@]}"; do
    if [ -e "${UNIT_DIR:?}/$u" ] && ! cmp -s "${UNIT_DIR:?}/$u" "$HERE/systemd/$u"; then
      pf FAIL "unité $u déjà présente et différente du paquet (non écrasée)"
    fi
  done
  if ! compgen -G "$HERE/systemd/*" >/dev/null; then pf FAIL "aucune unité dans le paquet"; fi
  if grep -En '^(Requires|Wants|After|Before|BindsTo|PartOf|Conflicts|Upholds|OnFailure)=.*(crypto-|paper-|ollama)' \
      "$HERE"/systemd/* >/dev/null 2>&1; then pf FAIL "référence de production dans une unité LAB"
  else pf PASS "aucune dépendance de production dans les unités LAB"; fi
  if [ -f "$JOURNAL" ] && ! grep -q ' COMPLETE$' "$JOURNAL"; then
    pf PASS "reprise : un apply précédent est incomplet ($(tail -n1 "$JOURNAL")) ; il sera repris"
  fi
  say "PRÉFLIGHT : $PF_FAIL échec(s), $PF_UNK indéterminé(s)"
  [ "$PF_FAIL" -eq 0 ]
}

# ---- étapes d'installation : atomiques, idempotentes, état réel contrôlé ---------------------------
jr() { install -d -m 0700 -o "$ROOT_USER" -g "$ROOT_GRP" "$STATE_DIR" && printf '%s %s\n' "$(now)" "$*" >>"$JOURNAL"; }
chmod_journal() { [ ! -f "$JOURNAL" ] || chmod 0600 "$JOURNAL"; }
step() {  # step NOM fonction
  local name="$1" fn="$2" rc=0
  jr "$name START"
  "$fn" || rc=$?
  if [ "$rc" -eq 0 ]; then jr "$name DONE"; say "étape $name : faite"; return 0; fi
  jr "$name FAILED rc=$rc"
  say "ÉCHEC à l'étape $name (rc=$rc). État partiel INERTE : aucune unité activée ni démarrée."
  say "Reprise : relancer le même apply (reprenable) ; ou retrait qui conserve les preuves : remove."
  exit 6
}
s_user() {
  id "$LAB_USER" >/dev/null 2>&1 && return 0
  useradd --system --no-create-home --home-dir "$LAB_ROOT" --shell /usr/sbin/nologin --user-group "$LAB_USER"
}
s_dirs() {
  install -d -m 0755 -o "$ROOT_USER" -g "$ROOT_GRP" "$LAB_ROOT" "$LAB_ROOT/release" "$DATA" || return 1
  install -d -m 0700 -o "$ROOT_USER" -g "$ROOT_GRP" "$STATE_DIR"
}
s_image() {
  rm -f "${IMG:?}.partial"   # reste d'un essai interrompu : fichier créé par ce script, jamais monté
  [ ! -f "$IMG" ] || { say "image déjà présente : conservée telle quelle"; return 0; }
  truncate -s "${IMG_MB}M" "$IMG.partial" || return 1
  chmod 0600 "$IMG.partial" || return 1
  mkfs.ext4 -q -F -L LAB01 -m 0 "$IMG.partial" || return 1
  mv "$IMG.partial" "$IMG"
}
s_units() {
  local u
  for u in "${UNITS[@]}"; do
    install -m 0644 -o "$ROOT_USER" -g "$ROOT_GRP" "$HERE/systemd/$u" "$UNIT_DIR/.$u.new" || return 1
    mv "$UNIT_DIR/.$u.new" "$UNIT_DIR/$u" || return 1
  done
  systemctl daemon-reload
}
s_mount() {
  if findmnt -rn "$DATA" >/dev/null 2>&1; then return 0; fi
  systemctl start srv-lab01-data.mount || { say "montage du volume LAB impossible : apply interrompu, aucun stockage non borné créé"; return 1; }
}
s_data() {
  findmnt -rn "$DATA" >/dev/null 2>&1 || { say "volume non monté : aucune écriture dans $DATA"; return 1; }
  install -d -m 0700 -o "$LAB_USER" -g "$LAB_USER" "$DATA/runs" || return 1
  install -d -m 0755 -o "$LAB_USER" -g "$LAB_USER" "$DATA/reports"
}
s_release() {
  local rel="$LAB_ROOT/release/$BUNDLE_SHA"
  rm -rf "${rel:?}.partial"
  if [ ! -d "$rel" ]; then
    install -d -m 0755 -o "$ROOT_USER" -g "$ROOT_GRP" "$rel.partial" || return 1
    tar -xzf "$BUNDLE" -C "$rel.partial" --no-same-owner || return 1
    chown -R "$ROOT_USER:$ROOT_GRP" "$rel.partial" || return 1
    chmod -R go-w "$rel.partial" || return 1
    mv "$rel.partial" "$rel" || return 1
  fi
  ln -sfn "$rel" "$LAB_ROOT/release/current"
}
do_apply() {
  need_auth; verify_staging; staging_perms
  [ -f "$BUNDLE" ] || die "--bundle absent ou introuvable" 5
  need_hex --bundle-sha256 "$BUNDLE_SHA" 64
  [ "$(sha256sum "$BUNDLE" | cut -d' ' -f1)" = "$BUNDLE_SHA" ] || die "empreinte du paquet différente" 5
  preflight || die "préconditions non satisfaites : rien n'a été modifié" 6
  step user s_user; step dirs s_dirs; step image s_image; step units s_units
  step mount s_mount; step data s_data; step release s_release
  jr "apply COMPLETE"; chmod_journal
  say "APPLY terminé : utilisateur, volume monté, unités installées ; services NON activés, NON démarrés. Jeton à créer par l'opérateur."
}

# ---- état réel, relevé, retrait avec preuves ------------------------------------------------------
do_status() {
  say "STATUT (lecture seule) $(now)"
  if id "$LAB_USER" >/dev/null 2>&1; then say "user        : FAIT"; else say "user        : ABSENT"; fi
  if [ -d "$LAB_ROOT/release" ]; then say "dirs        : FAIT"; else say "dirs        : ABSENT"; fi
  if [ -f "$IMG" ]; then say "image       : FAIT"
  elif [ -f "$IMG.partial" ]; then say "image       : PARTIEL (.partial d'un essai interrompu)"
  else say "image       : ABSENT"; fi
  local u n=0
  for u in "${UNITS[@]}"; do if [ -f "$UNIT_DIR/$u" ]; then n=$((n + 1)); fi; done
  if [ "$n" -eq "${#UNITS[@]}" ]; then say "units       : FAIT"
  elif [ "$n" -gt 0 ]; then say "units       : PARTIEL ($n/${#UNITS[@]})"
  else say "units       : ABSENT"; fi
  if findmnt -rn "$DATA" >/dev/null 2>&1; then say "mount       : FAIT"; else say "mount       : ABSENT"; fi
  if [ -d "$DATA/runs" ]; then say "data        : FAIT"; else say "data        : ABSENT"; fi
  if [ -L "$LAB_ROOT/release/current" ]; then say "release     : FAIT"
  elif compgen -G "$LAB_ROOT/release/*.partial" >/dev/null; then say "release     : PARTIEL"
  else say "release     : ABSENT"; fi
  if [ -f "$JOURNAL" ]; then say "journal (5 dernières lignes) :"; tail -n 5 "$JOURNAL"; fi
}
evidence_snapshot() {  # écrit ET vérifie les preuves ; échec = rien n'est retiré
  EV="$EVID_DIR/$(now)"
  install -d -m 0700 -o "$ROOT_USER" -g "$ROOT_GRP" "$EVID_DIR" "$EV" "$EV/units" || return 1
  local u need free
  if findmnt -rn "$DATA" >/dev/null 2>&1; then
    need="$(du -sm "$DATA" 2>/dev/null | awk '{print $1}')"; free="$(df -Pm "$EVID_DIR" | awk 'NR==2{print $4}')"
    [ "${free:-0}" -gt "$(( ${need:-0} + 8 ))" ] || { say "espace insuffisant pour les preuves (${free:-?} Mo libres, ${need:-?} Mo nécessaires)"; return 1; }
    tar -C "$DATA" -czf "$EV/data.tar.gz" runs reports || return 1
  else
    say "volume non monté : les données restent dans l'image conservée ($IMG)" | tee "$EV/NOTE.txt"
  fi
  for u in "${UNITS[@]}"; do
    if [ -f "$UNIT_DIR/$u" ]; then cp -p "$UNIT_DIR/$u" "$EV/units/$u" || return 1; fi
  done
  if [ -f "$JOURNAL" ]; then cp -p "$JOURNAL" "$EV/install.journal" || return 1; fi
  { id "$LAB_USER" 2>&1 || true; ls -ld "$LAB_ROOT" "$DATA" "$DATA/runs" "$DATA/reports" "$IMG" 2>&1 || true
    findmnt -rn "$DATA" 2>&1 || true; } >"$EV/state.txt"
  if [ -f "$IMG" ]; then sha256sum "$IMG" >"$EV/image.sha256" || return 1; fi
  (cd "$EV" && find . -type f ! -name MANIFEST.sha256 -print0 | sort -z | xargs -0 sha256sum >MANIFEST.sha256) || return 1
  (cd "$EV" && sha256sum --strict --quiet -c MANIFEST.sha256) || return 1
  say "preuves conservées et vérifiées : $EV ($(wc -l <"$EV/MANIFEST.sha256") fichier(s))"
}
do_remove() {
  need_auth
  evidence_snapshot || die "preuves non conservées ou non vérifiées : RIEN n'a été retiré" 7
  local u
  for u in lab01-api.service lab01-run.service lab01-export.service; do run systemctl stop "$u"; done
  run systemctl stop srv-lab01-data.mount
  for u in "${UNITS[@]}"; do rm -f "${UNIT_DIR:?}/${u:?}"; done
  systemctl daemon-reload
  jr "remove DONE evidence=$EV"
  say "REMOVE : unités retirées et volume démonté. Conservés : $IMG (expériences), $EV (preuves vérifiées), $JOURNAL, $LAB_ROOT, utilisateur $LAB_USER. Aucune purge."
}
do_verify() {
  say "VERIFY (lecture seule) $(date -u +%FT%TZ)"
  run id "$LAB_USER"
  run ls -ld "$LAB_ROOT" "$DATA" "$DATA/runs" "$DATA/reports" "$LAB_ROOT/token" "$IMG"
  run findmnt "$DATA"
  run df -h "$DATA"
  local u
  for u in "${UNITS[@]}"; do run systemctl show "$u" -p LoadState -p ActiveState -p UnitFileState --no-pager; done
  run systemd-analyze verify "$UNIT_DIR"/lab01*.service "$UNIT_DIR"/lab01.slice "$UNIT_DIR"/srv-lab01-data.mount
  run systemctl show lab01.slice -p MemoryMax -p MemoryHigh -p CPUQuotaPerSecUSec -p TasksMax --no-pager
  run ss -ltn
}
do_plan() {
  say "PLAN (rien n'est modifié)"
  say " utilisateur  : $LAB_USER (système, nologin, sans sudo, sans groupe additionnel)"
  say " volume borné : image ext4 ${IMG_MB} Mo ($IMG) montée sur $DATA (nodev,nosuid,noexec) ; le LAB ne peut pas la dépasser"
  say " répertoires  : $LAB_ROOT/release (root 0755), $DATA/runs ($LAB_USER 0700, privé), $DATA/reports ($LAB_USER 0755, rapports nettoyés lisibles), $LAB_ROOT/token (root:$LAB_USER 0640, créé par l'opérateur)"
  say " unités       : ${UNITS[*]} -> $UNIT_DIR (le volume est monté ; rien n'est activé ni démarré)"
  say " étapes       : user, dirs, image, units, mount, data, release (atomiques, reprenables ; journal $JOURNAL)"
  say " retrait      : preuves vérifiées dans $EVID_DIR/<date> AVANT tout retrait ; image conservée ; pas de purge"
  no_prod_refs && say " contrôle      : aucune référence à une unité de production : OK"
}

main() {
  PATH=/usr/sbin:/usr/bin:/sbin:/bin; export PATH
  MODE="${1:-plan}"; [ $# -gt 0 ] && shift
  while [ $# -gt 0 ]; do
    case "$1" in
      --purge) die "--purge non prévu : les expériences et preuves sont conservées (décision séparée)" 2;;
      --auth|--bundle|--bundle-sha256|--manifest-sha256|--commit) [ $# -ge 2 ] || die "valeur manquante pour $1" 2;;
      *) die "argument inconnu : $1" 2;;
    esac
    case "$1" in
      --auth) AUTH="$2";; --bundle) BUNDLE="$2";; --bundle-sha256) BUNDLE_SHA="$2";;
      --manifest-sha256) MANIFEST_SHA="$2";; --commit) COMMIT="$2";;
    esac; shift 2
  done
  case "$MODE" in
    plan) do_plan ;;
    verify-staging) verify_staging ;;
    preflight) verify_staging; preflight || exit 6 ;;
    status) do_status ;;
    verify) do_verify ;;
    apply) do_apply ;;
    remove) do_remove ;;
    *) say "usage : $0 plan|verify-staging|preflight|status|verify|apply|remove (voir l'en-tête)"; exit 2 ;;
  esac
}
# Exécuté directement : main ; chargé par `source` (tests) : seules les fonctions sont définies.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi
