#!/bin/bash
# deploy.sh — Pousser le projet vers le VPS depuis le PC local
# Usage : bash deploy/deploy.sh <IP_VPS> [user]
# Exemple : bash deploy/deploy.sh 152.67.10.45 ubuntu

set -e

VPS_IP="${1:?Usage: bash deploy/deploy.sh <IP_VPS> [user]}"
VPS_USER="${2:-ubuntu}"
VPS_DIR="~/crypto_ai_terminal"
SSH_TARGET="$VPS_USER@$VPS_IP"

echo "=> Déploiement vers $SSH_TARGET:$VPS_DIR"

# Créer le dossier distant si besoin
ssh "$SSH_TARGET" "mkdir -p $VPS_DIR"

# Synchroniser le code (exclut .env, databases, .venv, logs, __pycache__)
rsync -avz --progress \
  --exclude='.env' \
  --exclude='databases/' \
  --exclude='.venv/' \
  --exclude='logs/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.git/' \
  --exclude='.vscode/' \
  --exclude='.cursor/' \
  --exclude='*.sqlite' \
  --exclude='*.db' \
  . "$SSH_TARGET:$VPS_DIR/"

# Copier le .env séparément (sensible)
echo "=> Copie du .env..."
scp .env "$SSH_TARGET:$VPS_DIR/.env"

echo ""
echo "=> Code envoyé. Sur le VPS, lancer :"
echo "   ssh $SSH_TARGET"
echo "   cd $VPS_DIR && bash deploy/setup_vps.sh"
echo ""
echo "=> Ou si déjà installé, redémarrer le service :"
echo "   ssh $SSH_TARGET 'sudo systemctl restart crypto-advisor'"
