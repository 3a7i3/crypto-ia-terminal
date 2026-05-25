#!/usr/bin/env bash
# S3/06_apply_S3.sh — Installation complète du package S3.
#
# Ce script :
#   1. Crée les dossiers nécessaires
#   2. Copie les modules importables dans scripts/ (pour les imports advisor_loop.py)
#   3. Crée le template config/telegram_config.json si absent
#   4. Installe le cron de surveillance logs (toutes les 6h)
#   5. Vérifie l'installation
#
# Usage : bash S3/06_apply_S3.sh

set -e
cd "$(dirname "$0")/.."  # se placer à la racine du projet

PYTHON=${PYTHON:-python3}
VENV_PYTHON=".venv/bin/python3"
[ -f "$VENV_PYTHON" ] && PYTHON="$VENV_PYTHON"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║              INSTALLATION S3                             ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── 1. Créer les dossiers ──────────────────────────────────────────────────────
echo "[1/5] Création des dossiers..."
mkdir -p config databases S3 scripts
echo "      config/ databases/ S3/ scripts/ — OK"

# ── 2. Copier les modules importables ─────────────────────────────────────────
echo ""
echo "[2/5] Copie des modules dans scripts/ (pour imports Python)..."
cp S3/01_telegram_alerts.py  scripts/telegram_alerts.py
cp S3/03_shadow_execution.py scripts/shadow_execution.py
echo "      scripts/telegram_alerts.py — OK"
echo "      scripts/shadow_execution.py — OK"

# Créer __init__.py si absent (namespace package)
touch scripts/__init__.py 2>/dev/null || true

# ── 3. Template Telegram config ────────────────────────────────────────────────
echo ""
echo "[3/5] Config Telegram..."
if [ ! -f "config/telegram_config.json" ]; then
    cat > config/telegram_config.json << 'JSON'
{
  "_comment": "Remplir bot_token et chat_id AVANT d'activer les alertes.",
  "_how_to": "1. Créer un bot via @BotFather sur Telegram → obtenir le token",
  "_how_to2": "2. Envoyer un message au bot, puis GET https://api.telegram.org/botTOKEN/getUpdates → chat_id",
  "bot_token": "VOTRE_BOT_TOKEN_ICI",
  "chat_id": "VOTRE_CHAT_ID_ICI",
  "enabled": false
}
JSON
    echo "      config/telegram_config.json créé — À REMPLIR avant activation"
else
    echo "      config/telegram_config.json déjà existant — ignoré"
fi

# ── 4. Cron surveillance logs (toutes les 6h) ──────────────────────────────────
echo ""
echo "[4/5] Installation cron surveillance logs..."
CRON_CMD="0 */6 * * * cd $(pwd) && $PYTHON S3/02_log_surveillance.py --telegram >> /tmp/s3_surveillance.log 2>&1"
CRON_COMMENT="# S3 log surveillance"

# Vérifier si le cron existe déjà
if crontab -l 2>/dev/null | grep -q "02_log_surveillance"; then
    echo "      Cron déjà installé — ignoré"
else
    # Ajouter le cron sans écraser les existants
    (crontab -l 2>/dev/null; echo "$CRON_COMMENT"; echo "$CRON_CMD") | crontab -
    echo "      Cron installé: $CRON_CMD"
fi

# ── 5. Vérification ────────────────────────────────────────────────────────────
echo ""
echo "[5/5] Vérification..."

check_file() {
    if [ -f "$1" ]; then
        echo "      ✓ $1"
    else
        echo "      ✗ MANQUANT: $1"
    fi
}

check_file "scripts/telegram_alerts.py"
check_file "scripts/shadow_execution.py"
check_file "config/telegram_config.json"
check_file "S3/02_log_surveillance.py"
check_file "S3/04_resilience_test.py"
check_file "S3/05_s3_report.py"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  S3 installé !                                           ║"
echo "║                                                          ║"
echo "║  Prochaines étapes :                                     ║"
echo "║  1. Remplir config/telegram_config.json                  ║"
echo "║     (bot_token + chat_id)                                ║"
echo "║                                                          ║"
echo "║  2. Tester la connexion Telegram :                       ║"
echo "║     python3 S3/01_telegram_alerts.py                     ║"
echo "║                                                          ║"
echo "║  3. Ajouter dans advisor_loop.py :                       ║"
echo "║     from scripts.telegram_alerts import TelegramAlert    ║"
echo "║     from scripts.shadow_execution import ShadowTracker   ║"
echo "║     alert = TelegramAlert()                              ║"
echo "║     shadow = ShadowTracker()                             ║"
echo "║                                                          ║"
echo "║  4. Bilan S3 (après 2 semaines) :                        ║"
echo "║     python3 S3/05_s3_report.py                           ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
