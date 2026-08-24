#!/usr/bin/env bash
# scripts/install_advisor_service.sh — Installe/répare l'unité systemd du moteur.
#
# R2 (audit forensic 2026-08-24). L'unité installée sur le VPS présentait un
# bloc [Service] EN DOUBLE, et les templates du repo codaient en dur un mauvais
# user/chemin (mathieuhasard111). Ce script GÉNÈRE une unité propre et unique
# avec le user et les chemins RÉELS ($USER/$HOME) + le python du venv, puis
# l'installe comme `crypto-advisor.service` (tiret) — le seul superviseur du
# moteur réel core/advisor_loop.py.
#
# Idempotent. À lancer une fois (fenêtre de maintenance) :
#   bash scripts/install_advisor_service.sh
set -e

SERVICE_NAME="crypto-advisor"
DEST="/etc/systemd/system/${SERVICE_NAME}.service"
PROJ_DIR="$HOME/crypto_ai_terminal"
PY_BIN="$PROJ_DIR/.venv/bin/python"

if [[ ! -x "$PY_BIN" ]]; then
    echo "ERREUR : interpréteur venv introuvable : $PY_BIN" >&2
    exit 1
fi
if [[ ! -f "$PROJ_DIR/core/advisor_loop.py" ]]; then
    echo "ERREUR : core/advisor_loop.py introuvable sous $PROJ_DIR" >&2
    exit 1
fi

echo "=== Installation crypto-advisor.service (user=$USER, dir=$PROJ_DIR) ==="

sudo tee "$DEST" >/dev/null <<EOF
[Unit]
Description=Crypto AI Terminal — Advisor Loop (moteur réel)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJ_DIR
EnvironmentFile=-$PROJ_DIR/.env
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8
Environment=TZ=UTC
Environment=PYTHONPATH=$PROJ_DIR
Environment=DP_LOG_DIR=$PROJ_DIR/databases
ExecStart=$PY_BIN core/advisor_loop.py
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

# Vérifie qu'il n'y a bien qu'UN seul bloc [Service] (garde-fou du bug d'origine)
_svc_count="$(grep -c '^\[Service\]' "$DEST")"
if [[ "$_svc_count" -ne 1 ]]; then
    echo "ERREUR : $_svc_count blocs [Service] dans l'unité générée (attendu 1)" >&2
    exit 1
fi

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
echo "[OK] Unité installée et activée. Redémarrage :"
echo "     sudo systemctl restart $SERVICE_NAME"
echo ""
echo "Vérification :"
echo "     systemctl status $SERVICE_NAME --no-pager | head -12"
