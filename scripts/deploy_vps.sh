#!/usr/bin/env bash
# scripts/deploy_vps.sh — Déploiement DÉLIBÉRÉ des fichiers modifiés vers le VPS.
#
# Ancien mode : déclenché automatiquement par .git/hooks/post-commit à CHAQUE
# commit — aboli (voir .git/hooks/post-commit.disabled). Un déploiement est
# désormais un geste explicite, jamais un effet de bord d'un commit, cohérent
# avec le gel scientifique.
#
# Usage :
#   bash scripts/deploy_vps.sh --confirm [--yes] [--dry-run] [--restart]
#
# Fonctionnement :
#   1. Lit les fichiers modifiés/ajoutés depuis git (dernier commit), applique
#      le filtre d'exclusion (databases/cache/logs/tests/docs — jamais de
#      données runtime/état sur le VPS, cf. ADR runtime_config.json).
#   2. Affiche la liste EXACTE des fichiers à transférer, demande une
#      confirmation interactive y/N (sautée avec --yes).
#   3. Transfère par SSH — sauté avec --dry-run.
#   4. UNIQUEMENT si le transfert réussit (jamais avant, jamais si --dry-run) :
#      crée un tag git annoté deploy-YYYYMMDD-HHMM (SHA du commit + liste des
#      fichiers dans le message) et le pousse. Le tag EST le journal d'audit
#      des déploiements — auditable comme le reste du projet.
#   5. Redémarre le service UNIQUEMENT si VPS_RESTART_CMD est défini ET
#      --restart est passé explicitement (double opt-in, jamais implicite).
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"
LOG_FILE="$ROOT_DIR/logs/deploy_vps.log"

mkdir -p "$ROOT_DIR/logs"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

usage() {
    cat <<'USAGE'
Usage: bash scripts/deploy_vps.sh --confirm [--yes] [--dry-run] [--restart]

Deploiement DELIBERE vers le VPS. Le hook post-commit automatique a ete
aboli (voir .git/hooks/post-commit.disabled) — un commit ne deploie plus
jamais rien tout seul.

  --confirm   Obligatoire. Sans ce flag : ce message, exit 1.
  --yes       Saute la confirmation interactive y/N (usage scripte).
  --dry-run   Simule tout (resolution des fichiers, affichage, tag)
              SANS transfert SSH ni tag git reel.
  --restart   Autorise le redemarrage du service — en plus de
              VPS_RESTART_CMD qui doit AUSSI etre defini. Sans --restart :
              jamais de redemarrage, meme si un fichier critique
              (advisor_loop.py, etc.) est deploye.

Exemples :
  bash scripts/deploy_vps.sh --confirm --dry-run
  bash scripts/deploy_vps.sh --confirm --yes
  bash scripts/deploy_vps.sh --confirm --restart
USAGE
}

CONFIRM=0
YES=0
DRY_RUN=0
RESTART=0
for arg in "$@"; do
    case "$arg" in
        --confirm) CONFIRM=1 ;;
        --yes) YES=1 ;;
        --dry-run) DRY_RUN=1 ;;
        --restart) RESTART=1 ;;
        *)
            echo "Argument inconnu : $arg" >&2
            usage
            exit 1
            ;;
    esac
done

if [[ $CONFIRM -ne 1 ]]; then
    usage
    exit 1
fi

# ── Charger variables VPS ─────────────────────────────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
    # Exporter uniquement les variables VPS_* avec expansion du tilde
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
VPS_RESTART_CMD="${VPS_RESTART_CMD:-}"

# ── Vérification de la configuration ─────────────────────────────────────────
if [[ -z "$VPS_HOST" || -z "$VPS_USER" || -z "$VPS_PATH" ]]; then
    log "ERREUR — VPS_HOST / VPS_USER / VPS_PATH non configurés dans .env"
    exit 1
fi

if [[ $DRY_RUN -eq 0 && ! -f "$VPS_KEY" ]]; then
    log "ERREUR — Clé SSH introuvable : $VPS_KEY"
    log "         Lance : bash scripts/setup_vps_deploy.sh"
    exit 1
fi

SSH_OPTS="-i $VPS_KEY -p $VPS_PORT -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o ServerAliveInterval=5 -o ServerAliveCountMax=6"

# ── Collecter les fichiers modifiés dans le dernier commit ───────────────────
cd "$ROOT_DIR"

# Fichiers du dernier commit (A=ajouté, M=modifié, R=renommé)
CHANGED_FILES=$(git diff-tree --no-commit-id -r --name-only --diff-filter=AMR HEAD 2>/dev/null)

# Ajouter aussi les fichiers non-commités (untracked nouveaux connus)
STAGED_NEW=$(git diff --cached --name-only --diff-filter=A 2>/dev/null || true)

# ── Exclusion — jamais déployer de données runtime/état sur le VPS ───────────
# Quelques fichiers sous databases/ restent trackés par git (ajoutés avant
# la règle .gitignore) : un commit qui les touche (même accidentellement,
# ex. git add -A) écraserait sinon l'état runtime du VPS — y compris des
# paramètres de risque live (runtime_config.json) — sans jamais toucher
# advisor_loop.py. Le gel scientifique doit rester intact même via ce tuyau.
EXCLUDE_PATTERN='^(databases/|cache/|logs/|tests/|docs/)'

ALL_FILES=$(printf "%s\n%s" "$CHANGED_FILES" "$STAGED_NEW" \
    | sort -u | grep -v '^$' | grep -vE "$EXCLUDE_PATTERN" || true)

if [[ -z "$ALL_FILES" ]]; then
    log "SKIP — Aucun fichier à déployer (dernier commit vide ou filtré)"
    exit 0
fi

COMMIT_SHA=$(git rev-parse HEAD)
FILE_COUNT=$(echo "$ALL_FILES" | wc -l | tr -d ' ')

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  DÉPLOIEMENT VPS — $VPS_USER@$VPS_HOST:$VPS_PATH"
echo "  Commit  : $COMMIT_SHA"
echo "  Fichiers ($FILE_COUNT) :"
echo "$ALL_FILES" | sed 's/^/    - /'
echo "════════════════════════════════════════════════════════════"
[[ $DRY_RUN -eq 1 ]] && echo "  (--dry-run : aucun transfert réel, aucun tag réel)"
echo ""

if [[ $YES -ne 1 ]]; then
    read -r -p "Déployer ces fichiers ? [y/N] " reply
    case "$reply" in
        [yY] | [yY][eE][sS]) ;;
        *)
            log "ABANDON — non confirmé"
            exit 0
            ;;
    esac
fi

TAG_NAME="deploy-$(date +%Y%m%d-%H%M)"

if [[ $DRY_RUN -eq 1 ]]; then
    log "[DRY-RUN] Transfert simulé ($FILE_COUNT fichier(s)) — aucun scp réel"
    log "[DRY-RUN] Tag simulé : $TAG_NAME — non créé, non poussé"
    if [[ $RESTART -eq 1 && -n "$VPS_RESTART_CMD" ]]; then
        log "[DRY-RUN] Redémarrage aurait été déclenché (--restart + VPS_RESTART_CMD définis)"
    fi
    log "Dry-run terminé — rien n'a été transféré ni tagué."
    exit 0
fi

# ── Vérifier connectivité ────────────────────────────────────────────────────
if ! ssh $SSH_OPTS "$VPS_USER@$VPS_HOST" "echo ping" &>/dev/null; then
    log "ERREUR — VPS inaccessible ($VPS_HOST:$VPS_PORT)"
    exit 1
fi

# ── Transférer via scp (robuste sur Windows/UTF-8) ───────────────────────────
SCP_OPTS="-i $VPS_KEY -P $VPS_PORT -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=15"
_transfer_ok=1
while IFS= read -r _file; do
    [[ -z "$_file" ]] && continue
    _dir="$(dirname "$_file")"
    if [[ "$_dir" != "." ]]; then
        ssh $SSH_OPTS "$VPS_USER@$VPS_HOST" "mkdir -p '$VPS_PATH/$_dir'" 2>/dev/null
    fi
    if ! scp $SCP_OPTS "$_file" "$VPS_USER@$VPS_HOST:$VPS_PATH/$_file" 2>/dev/null; then
        log "ERREUR — scp échoué pour : $_file"
        _transfer_ok=0
    fi
done <<<"$ALL_FILES"

if [[ $_transfer_ok -eq 0 ]]; then
    log "ERREUR — un ou plusieurs fichiers non transférés — PAS de tag créé"
    exit 1
fi
log "Transfert OK"

# ── Tag d'audit — créé UNIQUEMENT après un transfert réussi ──────────────────
# Un tag ne doit jamais pointer vers un déploiement raté.
TAG_MSG="$(printf "Déploiement %s -> %s@%s:%s\nCommit: %s\nFichiers (%s):\n%s\n" \
    "$TAG_NAME" "$VPS_USER" "$VPS_HOST" "$VPS_PATH" "$COMMIT_SHA" "$FILE_COUNT" "$ALL_FILES")"
git tag -a "$TAG_NAME" -m "$TAG_MSG"
git push origin "$TAG_NAME"
log "Tag d'audit créé et poussé : $TAG_NAME"

# ── Redémarrage du service — double opt-in, jamais implicite ─────────────────
if [[ $RESTART -eq 1 && -n "$VPS_RESTART_CMD" ]]; then
    log "Redémarrage (--restart + VPS_RESTART_CMD définis)..."
    # shellcheck disable=SC2029
    ssh $SSH_OPTS "$VPS_USER@$VPS_HOST" \
        "cd '$VPS_PATH' && { pkill -f advisor_loop.py 2>/dev/null; sleep 3; true; } && export P6_SAFE_MODE=${P6_SAFE_MODE:-false} && nohup .venv/bin/python3 advisor_loop.py < /dev/null >> logs/advisor.log 2>&1 & sleep 18 && pgrep -f advisor_loop.py > /dev/null && echo RUNNING" \
        | grep -q RUNNING \
        && log "Service redémarré (PID OK)" \
        || log "AVERTISSEMENT — PID non détecté après redémarrage"
elif [[ -n "$VPS_RESTART_CMD" ]]; then
    log "SKIP restart — --restart non passé (VPS_RESTART_CMD défini mais redémarrage jamais implicite)"
fi

log "Déploiement terminé"
