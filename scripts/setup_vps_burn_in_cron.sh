#!/usr/bin/env bash
# scripts/setup_vps_burn_in_cron.sh — Installation du cron de collecte burn-in sur VPS.
#
# Configure deux tâches cron sur le VPS :
#   1. Snapshot horaire   → logs/burn_in_hourly.log
#   2. Rapport journalier → logs/burn_in_daily.log  (avec envoi Telegram)
#
# Utilise les mêmes variables .env que deploy_vps.sh (VPS_HOST, VPS_USER, VPS_PATH, VPS_KEY).
#
# Usage :
#   bash scripts/setup_vps_burn_in_cron.sh
#   bash scripts/setup_vps_burn_in_cron.sh --dry-run   # affiche les commandes sans les exécuter
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# ── Charger variables VPS ─────────────────────────────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
    while IFS='=' read -r key value; do
        if [[ "$key" =~ ^VPS_ ]]; then
            value="${value/#\~/$HOME}"
            export "$key=$value"
        fi
    done < <(grep -E '^VPS_' "$ENV_FILE" 2>/dev/null)
fi

VPS_HOST="${VPS_HOST:-}"
VPS_USER="${VPS_USER:-}"
VPS_PORT="${VPS_PORT:-22}"
VPS_PATH="${VPS_PATH:-}"
VPS_KEY="${VPS_KEY:-$HOME/.ssh/gcp_key}"

if [[ -z "$VPS_HOST" || -z "$VPS_USER" || -z "$VPS_PATH" ]]; then
    log "ERREUR — VPS_HOST / VPS_USER / VPS_PATH non configurés dans .env"
    exit 1
fi

SSH_OPTS="-i $VPS_KEY -p $VPS_PORT -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=15"

# ── Vérifier la connectivité ──────────────────────────────────────────────────
if [[ $DRY_RUN -eq 0 ]]; then
    if ! ssh $SSH_OPTS "$VPS_USER@$VPS_HOST" "echo ping" &>/dev/null; then
        log "ERREUR — VPS inaccessible ($VPS_HOST:$VPS_PORT)"
        exit 1
    fi
    log "VPS accessible : $VPS_USER@$VPS_HOST:$VPS_PATH"
fi

# ── Définition des tâches cron ───────────────────────────────────────────────
# python3 est utilisé explicitement (compatibilité VPS Linux)
PYTHON="python3"
COLLECTOR="$VPS_PATH/scripts/vps_burn_in_collector.py"
LOG_DIR="$VPS_PATH/logs"

CRON_HOURLY="0 * * * * cd $VPS_PATH && $PYTHON $COLLECTOR --snapshot >> $LOG_DIR/burn_in_hourly.log 2>&1"
CRON_DAILY="55 23 * * * cd $VPS_PATH && $PYTHON $COLLECTOR --report --telegram >> $LOG_DIR/burn_in_daily.log 2>&1"
CRON_WEEKLY="30 8 * * 1 cd $VPS_PATH && $PYTHON $COLLECTOR --report --hours 168 --telegram >> $LOG_DIR/burn_in_weekly.log 2>&1"

log "Tâches cron à installer :"
log "  [HORAIRE]  $CRON_HOURLY"
log "  [JOURNALIER] $CRON_DAILY"
log "  [HEBDO]    $CRON_WEEKLY"

if [[ $DRY_RUN -eq 1 ]]; then
    log "[DRY-RUN] Aucune modification effectuée."
    exit 0
fi

# ── Installation des crons sur le VPS ────────────────────────────────────────
REMOTE_CMD=$(cat <<'HEREDOC'
set -e

# Créer les répertoires nécessaires
mkdir -p "$LOG_DIR"
mkdir -p "$(dirname "$COLLECTOR")"

# Rendre le script exécutable
chmod +x "$COLLECTOR" 2>/dev/null || true

# Récupérer la crontab existante (sans les entrées burn_in)
EXISTING=$(crontab -l 2>/dev/null | grep -v "vps_burn_in_collector" || true)

# Écrire la nouvelle crontab
{
    echo "$EXISTING"
    echo ""
    echo "# === Burn-In Metrics Collector (installé par setup_vps_burn_in_cron.sh) ==="
    echo "$CRON_HOURLY"
    echo "$CRON_DAILY"
    echo "$CRON_WEEKLY"
} | crontab -

echo "Crontab installée avec succès"
crontab -l | grep "burn_in"
HEREDOC
)

ssh $SSH_OPTS "$VPS_USER@$VPS_HOST" \
    "LOG_DIR='$LOG_DIR' COLLECTOR='$COLLECTOR' \
     CRON_HOURLY='$CRON_HOURLY' \
     CRON_DAILY='$CRON_DAILY' \
     CRON_WEEKLY='$CRON_WEEKLY' \
     bash -s" <<< "$REMOTE_CMD"

log "Cron burn-in installé sur $VPS_HOST"
log ""
log "Vérification avec : ssh $VPS_USER@$VPS_HOST 'crontab -l | grep burn_in'"
log "Logs horaires    : $LOG_DIR/burn_in_hourly.log"
log "Logs journaliers : $LOG_DIR/burn_in_daily.log"
log "Logs hebdo       : $LOG_DIR/burn_in_weekly.log"
