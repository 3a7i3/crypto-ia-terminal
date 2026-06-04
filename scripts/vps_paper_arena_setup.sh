#!/usr/bin/env bash
# scripts/vps_paper_arena_setup.sh — Déploiement Paper Arena V1 sur VPS
# Usage : bash scripts/vps_paper_arena_setup.sh
set -e

ENV_FILE="$HOME/crypto_ai_terminal/.env"
SERVICE_NAME="paper-arena"
SERVICE_SRC="$HOME/crypto_ai_terminal/scripts/paper-arena.service"
SERVICE_DEST="/etc/systemd/system/${SERVICE_NAME}.service"
LOG_FILE="$HOME/crypto_ai_terminal/logs/paper_arena.log"

echo "=== Paper Arena V1 — Setup ==="

# ── 1. Variables requises ─────────────────────────────────────────────────────
if ! grep -q "PAPER_ARENA_TG_TOKEN" "$ENV_FILE" 2>/dev/null; then
    echo ""
    echo "ERREUR : PAPER_ARENA_TG_TOKEN manquant dans $ENV_FILE"
    echo "Ajouter dans .env :"
    echo "  PAPER_ARENA_TG_TOKEN=<token_bot_dédié>"
    echo "  PAPER_ARENA_TG_CHAT_ID=<chat_id>"
    exit 1
fi

if ! grep -q "PAPER_ARENA_TG_CHAT_ID" "$ENV_FILE" 2>/dev/null; then
    echo ""
    echo "ERREUR : PAPER_ARENA_TG_CHAT_ID manquant dans $ENV_FILE"
    exit 1
fi

echo "[1/5] Variables OK"

# ── 2. Logs ───────────────────────────────────────────────────────────────────
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
echo "[2/5] Logs : $LOG_FILE"

# ── 3. Service systemd ────────────────────────────────────────────────────────
sudo cp "$SERVICE_SRC" "$SERVICE_DEST"
sudo systemctl daemon-reload
echo "[3/5] Service installé : $SERVICE_DEST"

# ── 4. Démarrage ──────────────────────────────────────────────────────────────
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sleep 5
echo "[4/5] Service démarré"

# ── 5. Vérification ───────────────────────────────────────────────────────────
STATUS=$(systemctl is-active "$SERVICE_NAME")
if [ "$STATUS" = "active" ]; then
    echo "[5/5] RUNNING — $SERVICE_NAME actif"
else
    echo "[5/5] ERREUR — statut : $STATUS"
    echo "--- Logs ---"
    tail -30 "$LOG_FILE"
    exit 1
fi

echo ""
echo "=== Déploiement terminé ==="
echo ""
echo "Commandes utiles :"
echo "  systemctl status $SERVICE_NAME"
echo "  journalctl -u $SERVICE_NAME -f"
echo "  tail -f $LOG_FILE"
