#!/usr/bin/env bash
# LAB-01 — relevé OOM ciblé sur 14 jours (LECTURE SEULE ; ne modifie ni groupe, ni droit, ni service).
# N'affiche jamais le journal complet : un compteur, la plus ancienne entrée lisible et au plus 20 lignes.
# Quatre états distincts, jamais confondus :
#   ACCÈS_REFUSÉ            le journal noyau n'est pas lisible par ce compte (ce n'est PAS « zéro événement »)
#   RÉTENTION_INSUFFISANTE  le journal conservé ne remonte pas jusqu'à la fenêtre demandée
#   AUCUNE_CORRESPONDANCE   journal lisible ET fenêtre complète couverte, aucune ligne OOM
#   ÉVÉNEMENTS              N lignes OOM (avec la même réserve si la rétention est insuffisante)
# Autres : ERREUR (outil en échec, filtre non pris en charge). Le code retour du script ne dit rien
# du résultat : lire la ligne finale « ÉTAT_OOM=… ».
# Écritures : un dossier temporaire privé (mktemp -d, 0700), supprimé en fin d'exécution.
set -uo pipefail
DAYS=14
MAXLINES=20
PATTERN='Out of memory|oom-kill|oom_kill|invoked oom-killer|Killed process|Memory cgroup out of memory'
umask 077
W="$(mktemp -d "${TMPDIR:-/tmp}/lab01-oom.XXXXXXXX")" || { echo "ERREUR : dossier temporaire impossible"; exit 2; }
trap 'rm -rf "$W"' EXIT
say() { printf '%s\n' "$*"; }

say "RELEVÉ OOM LAB-01 — $(date -u +%FT%TZ) — compte : $(id -un) ; groupes : $(id -Gn)"

# 0. Compteur noyau, lisible sans privilège, indépendant du journal : OOM-kills depuis le démarrage.
if [ -r /proc/vmstat ]; then
  k="$(awk '$1=="oom_kill"{print $2}' /proc/vmstat 2>/dev/null)"
  up_s="$(cut -d' ' -f1 /proc/uptime 2>/dev/null | cut -d. -f1)"
  if [ -n "$k" ] && [ -n "$up_s" ]; then
    say "compteur noyau oom_kill = $k depuis le démarrage du $(date -u -d "-${up_s} seconds" +%FT%TZ) (uptime ${up_s} s)"
  else
    say "compteur noyau oom_kill : INDÉTERMINÉ (/proc/vmstat sans oom_kill ou /proc/uptime illisible)"
  fi
else
  say "compteur noyau oom_kill : INDÉTERMINÉ (/proc/vmstat illisible)"
fi

verdict() { say "ÉTAT_OOM=$1"; say "OOM : $2"; exit 0; }

# 1. Accès au journal noyau.
journalctl -k -n 1 -q --no-pager -o short-unix >"$W/probe.out" 2>"$W/probe.err"; rc=$?
say "\$ journalctl -k -n 1 -q   [rc=$rc]"
if grep -Eqi 'insufficient permissions|not seeing messages|Permission denied' "$W/probe.err"; then
  say "STDERR: $(head -c 300 "$W/probe.err")"
  verdict ACCÈS_REFUSÉ "INDÉTERMINÉ — journal noyau illisible pour ce compte ; aucun événement n'a été compté (≠ 0). Relancer avec un compte autorisé par l'opérateur."
fi
if [ "$rc" -ne 0 ]; then
  say "STDERR: $(head -c 300 "$W/probe.err")"
  verdict ERREUR "INDÉTERMINÉ — journalctl a échoué (rc=$rc) ; aucun événement n'a été compté (≠ 0)."
fi
if [ ! -s "$W/probe.out" ]; then
  verdict RÉTENTION_INSUFFISANTE "INDÉTERMINÉ — journal lisible mais aucune entrée noyau conservée (rotation ou journal volatil)."
fi

# 2. Rétention : plus ancienne entrée noyau lisible (le flux est consommé, rien n'est affiché ni stocké).
journalctl -k -q --no-pager -o short-unix 2>"$W/first.err" | awk 'NR==1{f=$1} END{print (f==""?"NONE":f); print NR}' >"$W/first.out"
first="$(sed -n 1p "$W/first.out")"; total="$(sed -n 2p "$W/first.out")"
first_i="${first%.*}"
if ! [[ "$first_i" =~ ^[0-9]+$ ]]; then
  say "STDERR: $(head -c 300 "$W/first.err")"
  verdict ERREUR "INDÉTERMINÉ — plus ancienne entrée illisible ; aucun événement n'a été compté (≠ 0)."
fi
cutoff="$(date -d "-${DAYS} days" +%s)"
first_iso="$(date -u -d "@$first_i" +%FT%TZ)"
say "entrées noyau lisibles : $total ; plus ancienne : $first_iso ; fenêtre demandée : ${DAYS} jours (depuis $(date -u -d "@$cutoff" +%FT%TZ))"
ret=COMPLETE
[ "$first_i" -le "$cutoff" ] || ret=INSUFFISANTE

# 3. Recherche : stdout, stderr et code retour séparés.
journalctl -k --since "-${DAYS} days" --no-pager -q -o short-iso -g "$PATTERN" >"$W/match.out" 2>"$W/match.err"; rc=$?
say "\$ journalctl -k --since -${DAYS}d -g <motif OOM>   [rc=$rc]"
if { [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; } || { [ -s "$W/match.err" ] && [ ! -s "$W/match.out" ]; }; then
  say "STDERR: $(head -c 300 "$W/match.err")"
  verdict ERREUR "INDÉTERMINÉ — la recherche a échoué (rc=$rc) ; ce n'est pas « aucune correspondance »."
fi
n="$(wc -l <"$W/match.out" | tr -d ' ')"
if [ "$n" -gt 0 ]; then
  head -n "$MAXLINES" "$W/match.out" | cut -c1-220
  [ "$n" -le "$MAXLINES" ] || say "[AFFICHAGE LIMITÉ : $MAXLINES lignes sur $n]"
fi
if [ "$ret" = INSUFFISANTE ]; then
  if [ "$n" -gt 0 ]; then
    verdict ÉVÉNEMENTS "$n ligne(s) OOM dans la partie conservée ; RÉTENTION_INSUFFISANTE : le journal ne remonte qu'à $first_iso, la fenêtre de ${DAYS} jours est incomplète."
  fi
  verdict RÉTENTION_INSUFFISANTE "INDÉTERMINÉ — aucune ligne OOM dans la partie conservée, mais le journal ne remonte qu'à $first_iso : l'absence n'est pas prouvée sur ${DAYS} jours."
fi
if [ "$n" -gt 0 ]; then
  verdict ÉVÉNEMENTS "$n ligne(s) OOM sur ${DAYS} jours complets (plus ancienne entrée : $first_iso)."
fi
verdict AUCUNE_CORRESPONDANCE "aucune ligne OOM sur ${DAYS} jours complets (journal lisible, plus ancienne entrée : $first_iso)."
