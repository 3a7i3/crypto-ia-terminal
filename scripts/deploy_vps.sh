#!/usr/bin/env bash
# scripts/deploy_vps.sh — Déploiement des fichiers modifiés vers le VPS.
#
# Déployé automatiquement par .git/hooks/post-commit.
# Peut aussi être lancé manuellement :  bash scripts/deploy_vps.sh
#
# Fonctionnement :
#   1. Lit les fichiers modifiés/ajoutés depuis git (dernier commit)
#   2. Les compresse dans une archive tar en mémoire
#   3. La transfère par SSH et l'extrait sur le VPS
#   4. Redémarre le service si VPS_RESTART_CMD est défini
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"
LOG_FILE="$ROOT_DIR/logs/deploy_vps.log"

mkdir -p "$ROOT_DIR/logs"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# ── Charger variables VPS ─────────────────────────────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
    # Exporter uniquement les variables VPS_* avec expansion du tilde
    while IFS='=' read -r key value; do
        if [[ "$key" =~ ^VPS_ ]]; then
            # Expand ~ en chemin absolu
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
VPS_RESTART_CMD="${VPS_RESTART_CMD:-}"

# ── Vérification de la configuration ─────────────────────────────────────────
if [[ -z "$VPS_HOST" || -z "$VPS_USER" || -z "$VPS_PATH" ]]; then
    log "SKIP — VPS_HOST / VPS_USER / VPS_PATH non configurés dans .env"
    exit 0
fi

if [[ ! -f "$VPS_KEY" ]]; then
    log "ERREUR — Clé SSH introuvable : $VPS_KEY"
    log "         Lance : bash scripts/setup_vps_deploy.sh"
    exit 1
fi

SSH_OPTS="-i $VPS_KEY -p $VPS_PORT -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=15"

# ── Collecter les fichiers modifiés dans le dernier commit ───────────────────
cd "$ROOT_DIR"

# Fichiers du dernier commit (A=ajouté, M=modifié, R=renommé)
CHANGED_FILES=$(git diff-tree --no-commit-id -r --name-only --diff-filter=AMR HEAD 2>/dev/null)

# Ajouter aussi les fichiers non-commités (untracked nouveaux connus)
STAGED_NEW=$(git diff --cached --name-only --diff-filter=A 2>/dev/null || true)

ALL_FILES=$(printf "%s\n%s" "$CHANGED_FILES" "$STAGED_NEW" | sort -u | grep -v '^$' || true)

if [[ -z "$ALL_FILES" ]]; then
    log "SKIP — Aucun fichier modifié dans le dernier commit"
    exit 0
fi

FILE_COUNT=$(echo "$ALL_FILES" | wc -l | tr -d ' ')
log "Déploiement — $FILE_COUNT fichier(s) → $VPS_USER@$VPS_HOST:$VPS_PATH"
log "Fichiers : $(echo "$ALL_FILES" | tr '\n' ' ')"

# ── Vérifier connectivité ────────────────────────────────────────────────────
if ! ssh $SSH_OPTS "$VPS_USER@$VPS_HOST" "echo ping" &>/dev/null; then
    log "ERREUR — VPS inaccessible ($VPS_HOST:$VPS_PORT)"
    exit 1
fi

# ── Transférer via tar + SSH pipe ────────────────────────────────────────────
# Crée l'archive localement → pipe SSH → extrait sur VPS
# Préserve la structure de répertoires, aucun fichier temporaire sur disque.
echo "$ALL_FILES" | tr '\n' '\0' | \
    xargs -0 tar czf - 2>/dev/null | \
    ssh $SSH_OPTS "$VPS_USER@$VPS_HOST" \
        "mkdir -p '$VPS_PATH' && cd '$VPS_PATH' && tar xzf -"

log "Transfert OK"

# ── Redémarrage du service (optionnel) ───────────────────────────────────────
# Redémarre seulement si advisor_loop.py est dans les fichiers déployés,
# ou si VPS_RESTART_CMD est explicitement forcé avec FORCE_RESTART=1.
NEEDS_RESTART=0
if echo "$ALL_FILES" | grep -qE "advisor_loop\.py|position_manager\.py|execution_engine\.py|exchange_monitor\.py"; then
    NEEDS_RESTART=1
fi
[[ "${FORCE_RESTART:-0}" == "1" ]] && NEEDS_RESTART=1

if [[ $NEEDS_RESTART -eq 1 && -n "$VPS_RESTART_CMD" ]]; then
    log "Redémarrage (fichier critique modifié)..."
    # shellcheck disable=SC2029
    ssh $SSH_OPTS "$VPS_USER@$VPS_HOST" \
        "cd '$VPS_PATH' && { pkill -f advisor_loop.py 2>/dev/null; true; }; sleep 2; nohup python3 advisor_loop.py >> logs/advisor.log 2>&1 < /dev/null & disown; sleep 1; pgrep -f advisor_loop.py > /dev/null && echo RUNNING" \
        | grep -q RUNNING \
        && log "Service redémarré (PID OK)" \
        || log "AVERTISSEMENT — PID non détecté après redémarrage"
elif [[ -n "$VPS_RESTART_CMD" ]]; then
    log "SKIP restart — aucun fichier critique modifié (utilise FORCE_RESTART=1 pour forcer)"
fi

log "Déploiement terminé"
