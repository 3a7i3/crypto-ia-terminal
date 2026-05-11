#!/usr/bin/env bash
# deploy/setup_vps.sh — Setup VPS pour crypto_ai_terminal (Ubuntu 22.04 LTS)
# Usage : bash deploy/setup_vps.sh
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/crypto_ai_terminal}"
DATA_DIR="$PROJECT_DIR/databases"
SERVICE_USER="${SUDO_USER:-$USER}"

if [[ ! -d "$PROJECT_DIR" ]]; then
    echo "Erreur: PROJECT_DIR introuvable: $PROJECT_DIR"
    echo "Clonez d'abord le repo ou exportez PROJECT_DIR avant d'executer ce script."
    exit 1
fi

echo "========================================"
echo " Crypto AI Terminal — Setup VPS"
echo "========================================"

# ── [1] Timezone UTC (horloge = source de vérité causale) ─────────────────────
echo "[1/8] Timezone UTC..."
sudo timedatectl set-timezone UTC
echo "  Timezone: $(timedatectl show -p Timezone --value)"

# ── [2] Système ───────────────────────────────────────────────────────────────
echo "[2/8] Mise a jour systeme..."
sudo apt-get update -qq && sudo apt-get upgrade -y -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv python3-pip git htop curl

# ── [3] Dossiers persistants ──────────────────────────────────────────────────
echo "[3/8] Dossiers persistants..."
mkdir -p "$DATA_DIR"
mkdir -p "$PROJECT_DIR/logs"
echo "  Traces DecisionPacket : $DATA_DIR"
echo "  Logs runtime          : $PROJECT_DIR/logs"

# ── [4] Virtualenv ────────────────────────────────────────────────────────────
echo "[4/8] Virtualenv Python..."
cd "$PROJECT_DIR"
if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN="python3.11"
else
    PYTHON_BIN="python3"
fi

if [[ ! -d ".venv" ]]; then
    "$PYTHON_BIN" -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip -q
if [ -f "requirements-vps.txt" ]; then
    pip install -r requirements-vps.txt -q
elif [ -f "requirements.txt" ]; then
    pip install -r requirements.txt -q
fi

# ── [5] Service bot principal ─────────────────────────────────────────────────
echo "[5/8] Service bot principal..."
sudo tee /etc/systemd/system/crypto-advisor.service > /dev/null << EOF
[Unit]
Description=Crypto AI Terminal — Advisor Loop
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=120
StartLimitBurst=5

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=-$PROJECT_DIR/.env
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8
Environment=TZ=UTC
Environment=DP_LOG_DIR=$DATA_DIR
ExecStart=$PROJECT_DIR/.venv/bin/python advisor_loop.py
Restart=on-failure
RestartSec=10s
TimeoutStopSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=crypto_advisor
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# ── [6] Service dashboard ─────────────────────────────────────────────────────
echo "[6/8] Service dashboard..."
sudo tee /etc/systemd/system/crypto-dashboard.service > /dev/null << EOF
[Unit]
Description=Crypto AI Terminal — Decision Trace Dashboard
After=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=-$PROJECT_DIR/.env
Environment=TZ=UTC
Environment=DP_LOG_DIR=$DATA_DIR
ExecStart=$PROJECT_DIR/.venv/bin/streamlit run dashboard_decision_trace.py \
    --server.port=8501 \
    --server.address=127.0.0.1 \
    --server.headless=true \
    --browser.gatherUsageStats=false
Restart=on-failure
RestartSec=15s
TimeoutStopSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=crypto_dashboard
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable crypto-advisor.service
sudo systemctl enable crypto-dashboard.service

# ── [7] Rotation JSONL — suppression traces > 30 jours ───────────────────────
echo "[7/8] Rotation logs (cron)..."
CRON_LINE="0 3 * * * find $DATA_DIR -name 'decision_packets_*.jsonl' -mtime +30 -delete"
CURRENT_CRON="$(crontab -l 2>/dev/null || true)"
FILTERED_CRON="$(printf '%s\n' "$CURRENT_CRON" | grep -Fv "decision_packets_" || true)"
printf '%s\n%s\n' "$FILTERED_CRON" "$CRON_LINE" | sed '/^$/d' | crontab -
echo "  Rotation : traces > 30j supprimees a 03:00 UTC"

# ── [8] Verification finale ───────────────────────────────────────────────────
echo "[8/8] Verification..."
echo "  Timezone    : $(timedatectl show -p Timezone --value)"
echo "  Python      : $(.venv/bin/python --version)"
echo "  Project dir : $PROJECT_DIR"
echo "  Traces dir  : $DATA_DIR"

echo ""
echo "========================================"
echo " Setup termine !"
echo ""
echo " Avant de demarrer — copier le .env :"
echo "   scp .env user@vps-ip:$PROJECT_DIR/.env"
echo ""
echo " Demarrer les services :"
echo "   sudo systemctl start crypto-advisor"
echo "   sudo systemctl start crypto-dashboard"
echo ""
echo " Status :"
echo "   sudo systemctl status crypto-advisor"
echo "   sudo journalctl -u crypto-advisor -f"
echo ""
echo " Dashboard (SSH tunnel depuis votre machine locale) :"
echo "   ssh -L 8501:localhost:8501 user@vps-ip"
echo "   http://localhost:8501"
echo "========================================"
