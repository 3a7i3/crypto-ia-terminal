#!/usr/bin/env bash
# scripts/vps_restart.sh — Redémarrage propre du moteur (core/advisor_loop.py).
#
# R2 (audit forensic 2026-08-24) : ce script délègue désormais à systemd quand
# l'unité `crypto-advisor.service` est installée (cas VPS). Auparavant il lançait
# le moteur via `nohup`, ce qui ENTRAIT EN CONFLIT avec systemd :
#   - systemd tenait déjà le process (Restart=on-failure) ;
#   - le nohup heurtait le verrou flock et sortait (exit 1) ;
#   - résultat : un `git checkout` + ce script pouvait laisser tourner du CODE
#     PÉRIMÉ sans que personne ne le voie (« je redémarre pour rien »).
#
# Un seul superviseur = un seul geste. Le watchdog (watchdog_vps.py) appelle ce
# même script, donc lui aussi passe maintenant par systemd — plus de course.
#
# Fallback nohup conservé pour les environnements SANS systemd (dev/local).
set -e
cd ~/crypto_ai_terminal
mkdir -p logs

SERVICE="crypto-advisor.service"

# ── Chemin systemd (VPS) ──────────────────────────────────────────────────────
if systemctl cat "$SERVICE" >/dev/null 2>&1; then
    echo "[systemd] restart $SERVICE (superviseur officiel, SIGTERM + grâce)"
    sudo systemctl restart "$SERVICE"
    sleep 5
    if systemctl is-active --quiet "$SERVICE"; then
        echo "  RUNNING — $(systemctl show -p MainPID --value "$SERVICE")"
        echo ""
        echo "--- Derniers logs ---"
        journalctl -u "$SERVICE" -n 20 --no-pager
        exit 0
    fi
    echo "  ÉCHEC — statut : $(systemctl is-active "$SERVICE")"
    journalctl -u "$SERVICE" -n 30 --no-pager
    exit 1
fi

# ── Fallback nohup (pas de systemd — dev/local) ───────────────────────────────
echo "[nohup] $SERVICE absent — lancement direct (dev/local uniquement)"
# DS-002 : motif ancré — ne jamais tuer par sous-chaîne (préserve le bot passif).
pkill -f 'core/advisor_loop\.py$' 2>/dev/null && echo "  Arrêté" || echo "  Pas de process"
sleep 3
nohup env PYTHONPATH="$HOME/crypto_ai_terminal" \
    .venv/bin/python3 core/advisor_loop.py >> logs/advisor.log 2>&1 &
BGPID=$!
echo "  PID=$BGPID"
sleep 12
if kill -0 "$BGPID" 2>/dev/null; then
    echo "  RUNNING — PID=$BGPID"
else
    echo "  FAILED — derniers logs :"
    tail -20 logs/advisor.log
    exit 1
fi
echo ""
echo "--- Derniers logs ---"
tail -25 logs/advisor.log
