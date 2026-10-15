#!/usr/bin/env bash
# LAB-01 — installation / vérification / retrait sur l'hôte. SOURCE PRÉPARÉE, NON EXÉCUTÉE.
#
# Ce script ne s'exécute QUE depuis un staging root protégé (/root/lab01-staging/<commit>),
# jamais depuis un clone modifiable. Aucun paramètre ne passe par l'environnement (pas de sudo -E) :
#   plan | verify-staging --manifest-sha256 H | verify
#   apply  --auth ID --bundle F --bundle-sha256 H --manifest-sha256 H
#   remove --auth ID            (conserve les expériences et les preuves ; pas de purge)
set -euo pipefail
MODE="${1:-plan}"; [ $# -gt 0 ] && shift
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB_USER=lab01; LAB_ROOT=/srv/lab01; DATA="$LAB_ROOT/data"; IMG_DIR=/var/lib/lab01
IMG="$IMG_DIR/lab01.img"; IMG_MB=64; UNIT_DIR=/etc/systemd/system
UNITS=(lab01.slice srv-lab01-data.mount lab01-run.service lab01-export.service lab01-api.service)
AUTH=""; BUNDLE=""; BUNDLE_SHA=""; MANIFEST_SHA=""

say() { printf '%s\n' "$*"; }
die() { say "REFUS : $*"; exit "${2:-3}"; }
while [ $# -gt 0 ]; do
  case "$1" in
    --purge) die "--purge non prévu : les expériences et preuves sont conservées (décision séparée)" 2;;
    --auth|--bundle|--bundle-sha256|--manifest-sha256) [ $# -ge 2 ] || die "valeur manquante pour $1" 2;;
    *) die "argument inconnu : $1" 2;;
  esac
  case "$1" in
    --auth) AUTH="$2";; --bundle) BUNDLE="$2";; --bundle-sha256) BUNDLE_SHA="$2";;
    --manifest-sha256) MANIFEST_SHA="$2";;
  esac; shift 2
done

need_auth() {
  [ "$(id -u)" -eq 0 ] || die "root requis pour $MODE"
  [ -n "$AUTH" ] || die "--auth (identifiant de l'autorisation opérateur) absent"
  say "autorisation citée : $AUTH"
}
no_prod_refs() {  # les unités LAB ne doivent référencer aucune unité de production
  if grep -En '^(Requires|Wants|After|Before|BindsTo|PartOf|Conflicts|Upholds|OnFailure)=.*(crypto-|paper-|ollama)' \
      "$HERE"/systemd/*; then die "référence de production dans une unité LAB" 4; fi
}
verify_staging() {
  [[ "$MANIFEST_SHA" =~ ^[0-9a-f]{64}$ ]] || die "--manifest-sha256 (64 hex) requis" 5
  [ -f "$HERE/INSTALLER.sha256" ] || die "INSTALLER.sha256 absent du staging" 5
  [ "$(sha256sum "$HERE/INSTALLER.sha256" | cut -d' ' -f1)" = "$MANIFEST_SHA" ] \
    || die "empreinte du manifeste d'installation différente de celle publiée" 5
  (cd "$HERE" && sha256sum --strict --quiet -c INSTALLER.sha256) \
    || die "un fichier d'installation diffère du manifeste" 5
  local listed present
  listed="$(awk '{print $2}' "$HERE/INSTALLER.sha256" | sed 's#^\*##' | sort)"
  present="$(cd "$HERE" && find . -type f ! -name INSTALLER.sha256 ! -name '*.tar.gz' | sed 's#^\./##' | sort)"
  [ "$listed" = "$present" ] || die "fichiers du staging différents du manifeste (en trop ou manquants)" 5
  no_prod_refs
  say "staging vérifié : manifeste $MANIFEST_SHA, fichiers conformes"
}
staging_perms() {  # le staging doit être à root et non inscriptible par d'autres : pas de TOCTOU
  [ "$(find "$HERE" ! -user root | wc -l)" -eq 0 ] || die "staging contient des fichiers non root" 5
  [ "$(find "$HERE" -perm /022 | wc -l)" -eq 0 ] || die "staging inscriptible par groupe/autres" 5
}
run() { say "\$ $*"; "$@" 2>&1 || say "[rc=$?]"; }

case "$MODE" in
plan)
  say "PLAN (rien n'est modifié)"
  say " utilisateur  : $LAB_USER (système, nologin, sans sudo, sans groupe additionnel)"
  say " volume borné : image ext4 ${IMG_MB} Mo ($IMG) montée sur $DATA (nodev,nosuid,noexec) ; le LAB ne peut pas la dépasser"
  say " répertoires  : $LAB_ROOT/release (root 0755), $DATA/runs ($LAB_USER 0700, privé), $DATA/reports ($LAB_USER 0755, rapports nettoyés lisibles), $LAB_ROOT/token (root:$LAB_USER 0640, créé par l'opérateur)"
  say " unités       : ${UNITS[*]} -> $UNIT_DIR (le volume est monté ; rien n'est activé ni démarré)"
  say " entrées      : --bundle/--bundle-sha256/--manifest-sha256 vérifiés depuis le staging root"
  no_prod_refs && say " contrôle      : aucune référence à une unité de production : OK"
  ;;
verify-staging) verify_staging ;;
verify)
  say "VERIFY (lecture seule) $(date -u +%FT%TZ)"
  run id "$LAB_USER"
  run ls -ld "$LAB_ROOT" "$DATA" "$DATA/runs" "$DATA/reports" "$LAB_ROOT/token" "$IMG"
  run findmnt "$DATA"
  run df -h "$DATA"
  for u in "${UNITS[@]}"; do
    run systemctl show "$u" -p LoadState -p ActiveState -p UnitFileState --no-pager
  done
  run systemd-analyze verify "$UNIT_DIR"/lab01*.service "$UNIT_DIR"/lab01.slice "$UNIT_DIR"/srv-lab01-data.mount
  run systemctl show lab01.slice -p MemoryMax -p MemoryHigh -p CPUQuotaPerSecUSec -p TasksMax --no-pager
  run ss -ltn
  ;;
apply)
  need_auth; verify_staging; staging_perms
  [ -f "$BUNDLE" ] || die "--bundle absent ou introuvable" 5
  [[ "$BUNDLE_SHA" =~ ^[0-9a-f]{64}$ ]] || die "--bundle-sha256 (64 hex) requis" 5
  [ "$(sha256sum "$BUNDLE" | cut -d' ' -f1)" = "$BUNDLE_SHA" ] || die "empreinte du paquet différente" 5
  id "$LAB_USER" >/dev/null 2>&1 || useradd --system --no-create-home --home-dir "$LAB_ROOT" \
      --shell /usr/sbin/nologin --user-group "$LAB_USER"
  install -d -m 0755 -o root -g root "$LAB_ROOT" "$LAB_ROOT/release" "$DATA" "$IMG_DIR"
  if [ ! -f "$IMG" ]; then
    truncate -s "${IMG_MB}M" "$IMG"; chmod 0600 "$IMG"
    mkfs.ext4 -q -F -L LAB01 -m 0 "$IMG"
  fi
  for u in "${UNITS[@]}"; do install -m 0644 -o root -g root "$HERE/systemd/$u" "$UNIT_DIR/$u"; done
  systemctl daemon-reload
  systemctl start srv-lab01-data.mount || die "montage du volume LAB impossible : apply interrompu, aucun stockage non borné créé" 6
  install -d -m 0700 -o "$LAB_USER" -g "$LAB_USER" "$DATA/runs"
  install -d -m 0755 -o "$LAB_USER" -g "$LAB_USER" "$DATA/reports"
  REL="$LAB_ROOT/release/$BUNDLE_SHA"
  if [ ! -d "$REL" ]; then
    install -d -m 0755 -o root -g root "$REL"; tar -xzf "$BUNDLE" -C "$REL" --no-same-owner
    chown -R root:root "$REL"; chmod -R go-w "$REL"
  fi
  ln -sfn "$REL" "$LAB_ROOT/release/current"
  say "APPLY terminé : utilisateur, volume monté, unités installées ; services NON activés, NON démarrés. Jeton à créer par l'opérateur."
  ;;
remove)
  need_auth
  for u in lab01-api.service lab01-run.service lab01-export.service; do run systemctl stop "$u"; done
  run systemctl stop srv-lab01-data.mount
  for u in "${UNITS[@]}"; do rm -f "$UNIT_DIR/$u"; done
  systemctl daemon-reload
  say "REMOVE : unités retirées et volume démonté. Conservés : $IMG (expériences et preuves), $LAB_ROOT, utilisateur $LAB_USER."
  ;;
*) say "usage : $0 plan|verify-staging|verify|apply|remove (voir l'en-tête)"; exit 2 ;;
esac
