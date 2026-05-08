#!/bin/bash
# setup_vps.sh — Installation automatique sur Oracle Cloud (Ubuntu 22.04)
# Usage : bash setup_vps.sh
set -e

echo "========================================"
echo " Crypto AI Terminal — Setup VPS"
echo "========================================"

# 1. Mise à jour système
sudo apt-get update -qq && sudo apt-get upgrade -y -qq

# 2. Python 3.11 + pip + outils
sudo apt-get install -y python3.11 python3.11-venv python3-pip git screen htop

# 3. Dossier projet
PROJECT_DIR="$HOME/crypto_ai_terminal"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# 4. Virtualenv isolé
python3.11 -m venv .venv
source .venv/bin/activate

# 5. Dépendances
pip install --upgrade pip -q
pip install -r requirements-vps.txt -q

# 6. Dossiers runtime
mkdir -p logs databases

# 7. Service systemd (auto-démarrage + redémarrage auto si crash)
SERVICE_FILE="/etc/systemd/system/crypto-advisor.service"
sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=Crypto AI Terminal — Advisor Loop
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/python advisor_loop.py --interval 60
Restart=always
RestartSec=10
StandardOutput=append:$PROJECT_DIR/logs/advisor_loop.log
StandardError=append:$PROJECT_DIR/logs/advisor_loop_err.log
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable crypto-advisor
echo ""
echo "========================================"
echo " Setup terminé !"
echo ""
echo " Copier le .env avant de démarrer :"
echo "   scp .env ubuntu@<IP_VPS>:$PROJECT_DIR/.env"
echo ""
echo " Puis démarrer le service :"
echo "   sudo systemctl start crypto-advisor"
echo "   sudo systemctl status crypto-advisor"
echo ""
echo " Logs en temps réel :"
echo "   tail -f $PROJECT_DIR/logs/advisor_loop.log"
echo "========================================"
