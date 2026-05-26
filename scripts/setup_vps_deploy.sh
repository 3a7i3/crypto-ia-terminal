#!/usr/bin/env bash
# scripts/setup_vps_deploy.sh — Configuration initiale SSH (à lancer UNE seule fois)
#
# Ce script :
#   1. Génère une clé SSH dédiée au VPS (si absente)
#   2. Installe la clé publique sur le VPS (demande le mot de passe une dernière fois)
#   3. Teste la connexion sans mot de passe
#
# Usage :
#   bash scripts/setup_vps_deploy.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"

# Charger les variables VPS depuis .env
if [[ -f "$ENV_FILE" ]]; then
    export $(grep -E '^VPS_' "$ENV_FILE" | xargs 2>/dev/null)
fi

VPS_HOST="${VPS_HOST:-}"
VPS_USER="${VPS_USER:-}"
VPS_PORT="${VPS_PORT:-22}"
VPS_KEY="${VPS_KEY:-$HOME/.ssh/crypto_vps}"

# ── Vérification des prérequis ────────────────────────────────────────────────
if [[ -z "$VPS_HOST" || -z "$VPS_USER" ]]; then
    echo ""
    echo "  ERREUR : VPS_HOST et VPS_USER doivent être définis dans .env"
    echo ""
    echo "  Ajoute ces lignes dans ton .env :"
    echo "    VPS_HOST=<ip_ou_domaine_du_vps>"
    echo "    VPS_USER=<ton_user_sur_le_vps>"
    echo "    VPS_PATH=<chemin_absolu_du_projet_sur_le_vps>  # ex: /home/ubuntu/crypto_ai_terminal"
    echo "    VPS_PORT=22"
    echo "    VPS_KEY=$HOME/.ssh/crypto_vps"
    echo "    VPS_RESTART_CMD=pkill -f advisor_loop.py || true"
    echo ""
    exit 1
fi

echo "=============================="
echo "  Setup déploiement VPS"
echo "  Host : $VPS_USER@$VPS_HOST:$VPS_PORT"
echo "  Clé  : $VPS_KEY"
echo "=============================="
echo ""

# ── 1. Générer la clé SSH ─────────────────────────────────────────────────────
if [[ ! -f "$VPS_KEY" ]]; then
    echo "[1/3] Génération de la clé SSH..."
    ssh-keygen -t ed25519 -f "$VPS_KEY" -N "" -C "crypto_ai_terminal_deploy"
    echo "      Clé créée : $VPS_KEY"
else
    echo "[1/3] Clé SSH déjà existante : $VPS_KEY — OK"
fi

# ── 2. Copier la clé publique sur le VPS ──────────────────────────────────────
echo ""
echo "[2/3] Copie de la clé publique sur le VPS..."
echo "      (Dernier mot de passe SSH demandé)"
echo ""
ssh-copy-id -i "${VPS_KEY}.pub" -p "$VPS_PORT" "$VPS_USER@$VPS_HOST"

# ── 3. Test de connexion ──────────────────────────────────────────────────────
echo ""
echo "[3/3] Test de connexion sans mot de passe..."
if ssh -i "$VPS_KEY" -p "$VPS_PORT" -o BatchMode=yes -o ConnectTimeout=10 \
       "$VPS_USER@$VPS_HOST" "echo OK" 2>/dev/null | grep -q "OK"; then
    echo "      Connexion réussie — plus aucun mot de passe nécessaire"
else
    echo "      ERREUR : la connexion a échoué. Vérifiez que ssh-copy-id a fonctionné."
    exit 1
fi

echo ""
echo "=============================="
echo "  Setup terminé !"
echo "  Le git hook post-commit déploiera automatiquement"
echo "  les fichiers modifiés à chaque commit."
echo "=============================="
