#!/bin/bash
# Rétention des rapports du cartographe (règle Mathieu 2026-11-22 : rapports à valeur momentanée).
# Garde les KEEP derniers rapports publiés de la mission, supprime les plus anciens.
# Exécuté après chaque passage (ExecStopPost) sous cat-obs-ro. Ne touche qu'aux fichiers
# réguliers au nom canonique AAAAMMJJTHHMMSSZ_<32 hex>.json ; ignore liens, .partial et le reste.
set -uo pipefail
KEEP=${KEEP:-20}
D=${1:?dossier runs/<mission> requis}
[ -d "$D" ] && [ ! -L "$D" ] || exit 0
cd "$D" || exit 0
mapfile -t ALL < <(find . -maxdepth 1 -type f ! -type l -regextype posix-extended \
  -regex '\./[0-9]{8}T[0-9]{6}Z_[0-9a-f]{32}\.json' -printf '%f\n' | LC_ALL=C sort)
N=${#ALL[@]}
(( N > KEEP )) || exit 0
for f in "${ALL[@]:0:N-KEEP}"; do rm -f -- "./$f"; done
logger -t cat-obs-prune "rétention : $((N-KEEP)) rapport(s) supprimé(s), $KEEP conservés" 2>/dev/null || true
