#!/usr/bin/env bash
# LAB-01 — relevé complémentaire, LECTURE SEULE. SOURCE PRÉPARÉE, NON EXÉCUTÉE.
#   bash lab01_audit.sh user        (utilisateur non privilégié, aucune élévation)
#   sudo bash lab01_audit.sh priv   (lectures nécessitant root : règles réseau, propriétaires de ports)
# Règles : aucune erreur n'est masquée (stderr, code de retour et refus sont imprimés),
# aucune troncature silencieuse, aucune valeur de secret : seules des propriétés nommées
# (liste blanche) sont lues, jamais `systemctl cat`, jamais d'Environment/ExecStart.
set -u
MODE="${1:-}"
say() { printf '%s\n' "$*"; }

step() {  # step TITRE LIMITE commande...
  local title="$1" limit="$2" out err rc n
  shift 2
  out="$(mktemp)"; err="$(mktemp)"
  "$@" >"$out" 2>"$err"; rc=$?
  say "== $title"; say "\$ $*"; say "[rc=$rc]"
  if [ -s "$err" ]; then sed 's/^/STDERR: /' "$err"; fi
  if [ "$rc" -eq 126 ] || [ "$rc" -eq 127 ]; then say "[ERREUR : commande introuvable ou non exécutable]"
  elif grep -qiE 'permission denied|not permitted|access denied|must be root|a password is required' "$err"; then
    say "[REFUSÉ : droits insuffisants — résultat INCONNU, pas zéro]"
  elif [ "$rc" -ne 0 ]; then say "[ERREUR : échec rc=$rc — résultat INCONNU]"; fi
  n="$(wc -l <"$out")"
  head -n "$limit" "$out"
  if [ "$n" -gt "$limit" ]; then say "[SORTIE TRONQUÉE : $n lignes au total, $limit affichées]"; fi
  rm -f "$out" "$err"
}

oom_check() {
  local out err rc lines n first
  out="$(mktemp)"; err="$(mktemp)"
  journalctl -k --since "-14 days" --no-pager -q >"$out" 2>"$err"; rc=$?
  say "== OOM noyau (14 jours)"; say "\$ journalctl -k --since \"-14 days\" --no-pager -q"; say "[rc=$rc]"
  lines="$(wc -l <"$out")"
  if [ "$rc" -ne 0 ]; then
    say "OOM : INDÉTERMINÉ (journalctl rc=$rc ; STDERR : $(head -c 300 "$err"))"
  elif [ "$lines" -eq 0 ]; then
    say "OOM : INDÉTERMINÉ (0 ligne lue : journal vide, rotation ou accès refusé ; STDERR : $(head -c 300 "$err"))"
  else
    first="$(head -n1 "$out" | cut -c1-40)"
    n="$(grep -ciE 'out of memory|oom-kill|oom_reaper' "$out" || true)"
    say "OOM : $n événement(s) sur $lines lignes noyau lues (première ligne : $first)"
  fi
  rm -f "$out" "$err"
}

PROPS=(-p User -p Group -p MainPID -p NRestarts -p ActiveEnterTimestamp -p MemoryCurrent -p MemoryMax
       -p MemorySwapMax -p LoadState -p CPUQuotaPerSecUSec -p TasksMax -p TasksCurrent -p Slice -p ProtectSystem -p PrivateNetwork)
SERVICES=(crypto-advisor crypto-operator-api crypto-operator-web crypto-lmi-observatory
          crypto-market-snapshot crypto-dashboard crypto-radar-bot paper-arena ollama)

case "$MODE" in
user)
  say "AUDIT LAB-01 — non privilégié — $(date -u +%FT%TZ)"
  step "identité" 5 id
  step "espaces de noms utilisateur (max)" 5 sysctl user.max_user_namespaces
  step "espaces de noms non privilégiés" 5 sysctl kernel.unprivileged_userns_clone
  step "mémoire" 10 free -m
  step "charge et pression" 10 cat /proc/loadavg /proc/pressure/cpu /proc/pressure/memory /proc/pressure/io
  step "disque et inodes" 10 df -h -i /
  step "ports en écoute (propriétaires visibles = les vôtres seulement)" 80 ss -ltnp
  for s in "${SERVICES[@]}"; do
    step "propriétés (liste blanche) $s" 20 systemctl show "$s.service" "${PROPS[@]}" --no-pager
  done
  oom_check
  step "mémoire/CPU instantanés (3 échantillons)" 20 vmstat 5 3
  ;;
priv)
  say "AUDIT LAB-01 — privilégié (lecture seule) — $(date -u +%FT%TZ)"
  if [ "$(id -u)" -ne 0 ]; then say "REFUS : root requis pour le mode priv"; exit 3; fi
  step "règles nft" 120 nft list ruleset
  step "règles iptables" 80 iptables -S
  step "ports en écoute avec propriétaires" 80 ss -ltnp
  ;;
*) say "usage : $0 user | priv"; exit 2 ;;
esac
