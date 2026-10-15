#!/usr/bin/env bash
# LAB-01 — installation / vérification / retrait sur l'hôte. SOURCE PRÉPARÉE, NON EXÉCUTÉE.
# Modes : plan (défaut, ne touche à rien) | verify (lecture seule) | apply | remove [--purge]
# apply/remove exigent root ET LAB01_AUTH="<identifiant d'autorisation écrite de l'opérateur>".
set -euo pipefail
MODE="${1:-plan}"; shift || true
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNITS=(lab01.slice lab01-run.service lab01-api.service)
LAB_USER=lab01; LAB_ROOT=/srv/lab01; UNIT_DIR=/etc/systemd/system
BUNDLE="${LAB01_BUNDLE:-}"; BUNDLE_SHA="${LAB01_BUNDLE_SHA256:-}"

say() { printf '%s\n' "$*"; }
need_auth() {
  [ "$(id -u)" -eq 0 ] || { say "REFUS : root requis pour $MODE"; exit 3; }
  [ -n "${LAB01_AUTH:-}" ] || { say "REFUS : LAB01_AUTH (autorisation opérateur) absent"; exit 3; }
  say "autorisation citée : ${LAB01_AUTH}"
}
no_prod_refs() {  # les unités LAB ne doivent référencer aucune unité de production
  if grep -En '^(Requires|Wants|After|Before|BindsTo|PartOf|Conflicts|Upholds|OnFailure)=.*(crypto-|paper-|ollama)' \
      "$HERE/systemd/"*; then say "REFUS : référence de production dans une unité LAB"; exit 4; fi
}

case "$MODE" in
plan)
  say "PLAN (rien n'est modifié)"
  say " utilisateur  : $LAB_USER (système, nologin, sans sudo, sans groupe additionnel)"
  say " répertoires  : $LAB_ROOT/release (root:root 0755), $LAB_ROOT/runs ($LAB_USER 0700), $LAB_ROOT/token (root:$LAB_USER 0640)"
  say " unités       : ${UNITS[*]} -> $UNIT_DIR (aucune activation, aucun démarrage)"
  say " paquet       : \$LAB01_BUNDLE vérifié contre \$LAB01_BUNDLE_SHA256"
  no_prod_refs && say " contrôle      : aucune référence à une unité de production : OK"
  ;;
verify)
  say "VERIFY (lecture seule) $(date -u +%FT%TZ)"
  id "$LAB_USER" 2>&1 || say "utilisateur $LAB_USER : absent"
  ls -ld "$LAB_ROOT" "$LAB_ROOT"/* 2>&1 || true
  for u in "${UNITS[@]}"; do
    systemctl show "$u" -p LoadState -p ActiveState -p UnitFileState --no-pager 2>&1 | paste -sd' ' || true
  done
  systemd-analyze verify "$UNIT_DIR"/lab01*.service "$UNIT_DIR"/lab01.slice 2>&1 | head -20 || true
  systemctl show lab01.slice -p MemoryMax -p MemoryHigh -p CPUQuotaPerSecUSec -p TasksMax --no-pager 2>&1 || true
  ss -ltn 2>/dev/null | awk '$4 ~ /:18090$/' || true
  ;;
apply)
  need_auth; no_prod_refs
  [ -f "$BUNDLE" ] || { say "REFUS : LAB01_BUNDLE absent"; exit 5; }
  [ "$(sha256sum "$BUNDLE" | cut -d' ' -f1)" = "$BUNDLE_SHA" ] || { say "REFUS : empreinte du paquet différente"; exit 5; }
  id "$LAB_USER" >/dev/null 2>&1 || useradd --system --no-create-home --home-dir "$LAB_ROOT" \
      --shell /usr/sbin/nologin --user-group "$LAB_USER"
  install -d -m 0755 -o root -g root "$LAB_ROOT" "$LAB_ROOT/release"
  install -d -m 0700 -o "$LAB_USER" -g "$LAB_USER" "$LAB_ROOT/runs"
  REL="$LAB_ROOT/release/$BUNDLE_SHA"
  if [ ! -d "$REL" ]; then
    install -d -m 0755 -o root -g root "$REL"; tar -xzf "$BUNDLE" -C "$REL" --no-same-owner
    chown -R root:root "$REL"; chmod -R go-w "$REL"
  fi
  ln -sfn "$REL" "$LAB_ROOT/release/current"
  for u in "${UNITS[@]}"; do install -m 0644 -o root -g root "$HERE/systemd/$u" "$UNIT_DIR/$u"; done
  systemctl daemon-reload
  say "APPLY terminé : unités installées, NON activées, NON démarrées. Token à créer par l'opérateur."
  ;;
remove)
  need_auth
  for u in lab01-api.service lab01-run.service; do systemctl stop "$u" 2>/dev/null || true; done
  for u in "${UNITS[@]}"; do rm -f "$UNIT_DIR/$u"; done
  systemctl daemon-reload
  if [ "${1:-}" = "--purge" ]; then
    rm -rf --one-file-system "$LAB_ROOT"; userdel "$LAB_USER" 2>/dev/null || true
    say "REMOVE --purge : unités, $LAB_ROOT et utilisateur supprimés"
  else
    say "REMOVE : unités retirées ; données conservées dans $LAB_ROOT (utiliser --purge pour les supprimer)"
  fi
  ;;
*) say "usage : $0 plan|verify|apply|remove [--purge]"; exit 2 ;;
esac
