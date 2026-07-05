#!/usr/bin/env bash
# scripts/vps_restart.sh — Redémarrage propre sur le VPS
set -e
cd ~/crypto_ai_terminal
mkdir -p logs

echo "[1/3] Arrêt process existant..."
# DS-002 (incident 2026-07-04) : motif ancré — jamais de sous-chaîne.
# "advisor_loop.py" sans ancrage tuerait aussi le bot passif racine
# (advisor_loop.py, géré séparément par systemd crypto_advisor.service).
pkill -f 'core/advisor_loop\.py$' 2>/dev/null && echo "  Arrêté" || echo "  Pas de process"
sleep 3

echo "[2/3] Démarrage core/advisor_loop.py..."
nohup env PYTHONPATH="$HOME/crypto_ai_terminal" \
    .venv/bin/python3 core/advisor_loop.py >> logs/advisor.log 2>&1 &
BGPID=$!
echo "  PID=$BGPID"
sleep 12

echo "[3/3] Vérification..."
if kill -0 $BGPID 2>/dev/null; then
    echo "  RUNNING — PID=$BGPID"
else
    echo "  FAILED — derniers logs :"
    tail -20 logs/advisor.log
    exit 1
fi

echo ""
echo "--- Derniers logs ---"
tail -25 logs/advisor.log
