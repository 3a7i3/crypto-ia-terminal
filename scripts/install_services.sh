#!/bin/bash
# install_services.sh — Installe les services systemd sur le VPS
# Usage : bash scripts/install_services.sh

set -e
PROJ=/home/mathieuhasard111/crypto_ai_terminal

echo "=== Installation services systemd Crypto AI ==="

# Copier les fichiers service
sudo cp "$PROJ/scripts/crypto_advisor.service" /etc/systemd/system/
sudo cp "$PROJ/scripts/crypto_watchdog.service" /etc/systemd/system/

# Recharger systemd
sudo systemctl daemon-reload

# Activer au démarrage
sudo systemctl enable crypto_advisor.service
sudo systemctl enable crypto_watchdog.service

# Arrêter les screens existants si actifs
screen -S bot -X quit 2>/dev/null || true
screen -S watchdog -X quit 2>/dev/null || true

# Démarrer les services
sudo systemctl start crypto_advisor.service
sleep 5
sudo systemctl start crypto_watchdog.service

echo ""
echo "=== Services installés et démarrés ==="
sudo systemctl status crypto_advisor.service --no-pager
echo ""
sudo systemctl status crypto_watchdog.service --no-pager
echo ""
echo "Commandes utiles :"
echo "  sudo journalctl -u crypto_advisor -f      # logs en temps réel"
echo "  sudo systemctl restart crypto_advisor     # redémarrage manuel"
echo "  sudo systemctl stop crypto_advisor        # arrêt"
