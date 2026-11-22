#!/bin/bash
# Suivi de main du cartographe (décision Mathieu 2026-11-22 10:28Z). Lancé avant chaque passage
# sous cat-obs-ro. Lecture GitHub seule (fetch anonyme de main), aucune écriture vers GitHub.
# Si la lecture échoue, la dernière mission publiée reste en place : le passage analyse la
# dernière révision connue au lieu d'échouer.
set -uo pipefail
CK=${1:?checkout de code requis}
UP=/srv/cat-obs/upstream
OUT=/srv/cat-obs/follow
export HOME=/nonexistent LC_ALL=C GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0
g() { git -C "$UP" -c safe.directory="$UP" -c credential.helper= "$@"; }
log() { logger -t cat-obs-follow "$*" 2>/dev/null || true; echo "$*"; }
if timeout 60 g fetch -q --depth=1 origin main && g checkout -q --detach --force FETCH_HEAD && g clean -qfdx; then
  SHA=$(g rev-parse HEAD)
else
  log "lecture de main impossible : dernière mission conservée"
  [ -s "$OUT/current.env" ] && exit 0 || exit 1
fi
cd "$CK" || exit 1
/usr/bin/python3.10 -B -m agent_bench.observation.follow_main \
  --template docs/agents/observation/examples/cartographer_zone_mission.json --analysed-sha "$SHA" --out "$OUT" || exit 1
log "main = $SHA"
