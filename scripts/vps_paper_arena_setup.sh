#!/usr/bin/env bash
# scripts/vps_paper_arena_setup.sh — Déploiement Paper Arena V1 sur VPS
# Usage : bash scripts/vps_paper_arena_setup.sh
set -e

ENV_FILE="$HOME/crypto_ai_terminal/.env"
SERVICE_NAME="paper-arena"
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
# L'unité est GÉNÉRÉE avec l'utilisateur et les chemins RÉELS ($USER/$HOME) au
# lieu de copier scripts/paper-arena.service tel quel — ce template contenait
# un user/chemin codés en dur (mathieuhasard111) qui ne correspondent pas
# forcément au VPS, ce qui faisait échouer le service au démarrage (CHDIR).
PROJ_DIR="$HOME/crypto_ai_terminal"
PY_BIN="$PROJ_DIR/.venv/bin/python3"
sudo tee "$SERVICE_DEST" >/dev/null <<EOF
[Unit]
Description=Paper Arena V1 — ETH 4h RSI 15/85
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJ_DIR
EnvironmentFile=$PROJ_DIR/.env
Environment=PYTHONPATH=$PROJ_DIR
ExecStart=$PY_BIN -m src.paper.paper_runner
Restart=always
RestartSec=10
StandardOutput=append:$LOG_FILE
StandardError=append:$LOG_FILE

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
echo "[3/5] Service installé : $SERVICE_DEST (user=$USER, dir=$PROJ_DIR)"

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
