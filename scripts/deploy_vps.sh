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
#   1. Lit les fichiers modifiés/ajoutés depuis le dernier tag deploy-*
#      jusqu'à HEAD (tous les commits accumulés depuis le dernier
#      déploiement réel — pas seulement le dernier commit, cf. incident
#      2026-07-07 : 5 commits accumulés, seul le dernier aurait été vu).
#      Sans tag deploy-* existant (premier déploiement) : dernier commit
#      seul, comportement historique. Applique le filtre d'exclusion
#      (databases/cache/logs/tests/docs — jamais de données runtime/état
#      sur le VPS, cf. ADR runtime_config.json).
#   2. Affiche la liste EXACTE des fichiers à transférer, demande une
#      confirmation interactive y/N (sautée avec --yes).
#   3. Transfère par SSH — sauté avec --dry-run.
#   4. Vérifie CHAQUE fichier par SHA256 (local vs distant) — un scp qui
#      retourne exit 0 sans avoir réellement écrit n'est plus une preuve
#      suffisante (incident 2026-07-04, tag deploy-20260704-1837 corrigé).
#   5. UNIQUEMENT si la vérification est à 100% (jamais avant, jamais si
#      --dry-run) : crée un tag git annoté deploy-YYYYMMDD-HHMM (SHA du
#      commit + liste des fichiers dans le message) et le pousse. Le tag
#      EST le journal d'audit des déploiements — auditable comme le reste
#      du projet.
#   6. Redémarre le service UNIQUEMENT si VPS_RESTART_CMD est défini ET
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
Usage: bash scripts/deploy_vps.sh --confirm [--yes] [--dry-run] [--restart core|advisor]

Deploiement DELIBERE vers le VPS. Le hook post-commit automatique a ete
aboli (voir .git/hooks/post-commit.disabled) — un commit ne deploie plus
jamais rien tout seul.

  --confirm         Obligatoire. Sans ce flag : ce message, exit 1.
  --yes             Saute la confirmation interactive y/N (usage scripte).
  --dry-run         Simule tout (resolution des fichiers, affichage, tag)
                    SANS transfert SSH ni tag git reel.
  --restart <cible> Autorise le redemarrage du service — en plus de
                    VPS_RESTART_CMD qui doit AUSSI etre defini. Cible
                    OBLIGATOIRE et exacte :
                      core     -> core/advisor_loop.py   (moteur reel)
                      advisor  -> advisor_loop.py         (bot passif)
                    Aucune sous-chaine : DS-002 (incident 2026-07-04) —
                    un pkill -f "advisor_loop.py" matche les DEUX scripts
                    a la fois. Refuse avec erreur si le fichier cible
                    n'existe pas sur le disque VPS (voir RECOVERY.md).
                    Sans --restart : jamais de redemarrage, meme si un
                    fichier critique est deploye.

Exemples :
  bash scripts/deploy_vps.sh --confirm --dry-run
  bash scripts/deploy_vps.sh --confirm --yes
  bash scripts/deploy_vps.sh --confirm --restart core
USAGE
}

CONFIRM=0
YES=0
DRY_RUN=0
RESTART=0
RESTART_TARGET=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --confirm) CONFIRM=1; shift ;;
        --yes) YES=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --restart)
            RESTART=1
            RESTART_TARGET="${2:-}"
            if [[ "$RESTART_TARGET" != "core" && "$RESTART_TARGET" != "advisor" ]]; then
                echo "ERREUR — --restart exige une cible explicite : --restart core|advisor" >&2
                usage
                exit 1
            fi
            shift 2
            ;;
        *)
            echo "Argument inconnu : $1" >&2
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
    # Exporter les variables VPS_* (avec expansion du tilde) et
    # RESTART_DISABLED_UNTIL_RECONCILIATION — source de vérité UNIQUE,
    # partagée avec watchdog_vps.py, jamais deux copies indépendantes.
    while IFS='=' read -r key value; do
        if [[ "$key" =~ ^VPS_ ]]; then
            value="${value/#\~/$HOME}"
            export "$key=$value"
        elif [[ "$key" == "RESTART_DISABLED_UNTIL_RECONCILIATION" ]]; then
            export "$key=$value"
        fi
    done < <(grep -E '^(VPS_|RESTART_DISABLED_UNTIL_RECONCILIATION=)' "$ENV_FILE" 2>/dev/null)
fi

VPS_HOST="${VPS_HOST:-}"
VPS_USER="${VPS_USER:-}"
VPS_PORT="${VPS_PORT:-22}"
VPS_PATH="${VPS_PATH:-}"
VPS_KEY="${VPS_KEY:-$HOME/.ssh/gcp_key}"
VPS_RESTART_CMD="${VPS_RESTART_CMD:-}"

# DS-002 (incident 2026-07-04) : défaut sûr si absent de .env — désactive tout
# --restart tant que main et feat/stack-unification ne sont pas réconciliés
# sur le VPS. Même variable lue par watchdog_vps.py (.env = source unique).
# Repasser à 0 uniquement lors de la manœuvre de réconciliation. Voir RECOVERY.md.
RESTART_DISABLED_UNTIL_RECONCILIATION="${RESTART_DISABLED_UNTIL_RECONCILIATION:-1}"

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

# ── Collecter les fichiers modifiés depuis le dernier déploiement ────────────
cd "$ROOT_DIR"

# Base = dernier tag deploy-* (tous les commits accumulés depuis le dernier
# déploiement réel). Fallback sur le dernier commit seul si aucun tag deploy-*
# n'existe encore (premier déploiement du dépôt).
LAST_DEPLOY_TAG=$(git tag -l "deploy-*" --sort=-creatordate | head -1)
if [[ -n "$LAST_DEPLOY_TAG" ]]; then
    log "Base de comparaison : tag $LAST_DEPLOY_TAG"
    CHANGED_FILES=$(git diff --name-only --diff-filter=AMR "$LAST_DEPLOY_TAG" HEAD 2>/dev/null)
else
    log "Aucun tag deploy-* trouvé — base de comparaison : dernier commit seul"
    CHANGED_FILES=$(git diff-tree --no-commit-id -r --name-only --diff-filter=AMR HEAD 2>/dev/null)
fi

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
        if [[ $RESTART_DISABLED_UNTIL_RECONCILIATION -eq 1 ]]; then
            log "[DRY-RUN] Redémarrage ($RESTART_TARGET) désactivé jusqu'à réconciliation (voir RECOVERY.md)"
        else
            log "[DRY-RUN] Redémarrage de la cible '$RESTART_TARGET' aurait été déclenché"
        fi
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

# ── Vérification post-transfert — SHA256 local vs distant ────────────────────
# Incident 2026-07-04 : scp a retourné succès (exit 0) alors que 2 fichiers
# sur 5 n'avaient pas réellement été transférés (mtime distant inchangé) —
# et un tag d'audit avait été créé sur la foi de ce faux succès. "scp exit 0"
# ne suffit plus comme preuve : on vérifie le contenu réellement présent sur
# le VPS, fichier par fichier, avant de créer le moindre tag.
_verify_ok=1
while IFS= read -r _file; do
    [[ -z "$_file" ]] && continue
    _local_sha=$(sha256sum "$_file" | awk '{print $1}')
    _remote_sha=$(ssh $SSH_OPTS "$VPS_USER@$VPS_HOST" "sha256sum '$VPS_PATH/$_file' 2>/dev/null" | awk '{print $1}')
    if [[ -z "$_remote_sha" || "$_local_sha" != "$_remote_sha" ]]; then
        log "ERREUR — vérification SHA256 échouée pour : $_file (local=$_local_sha distant=${_remote_sha:-absent})"
        _verify_ok=0
    fi
done <<<"$ALL_FILES"

if [[ $_verify_ok -eq 0 ]]; then
    log "ERREUR — vérification post-transfert échouée — PAS de tag créé"
    exit 1
fi
log "Vérification SHA256 OK — $FILE_COUNT fichier(s) confirmés identiques sur le VPS"

# ── Tag d'audit — créé UNIQUEMENT après un transfert réussi ──────────────────
# Un tag ne doit jamais pointer vers un déploiement raté.
TAG_MSG="$(printf "Déploiement %s -> %s@%s:%s\nCommit: %s\nFichiers (%s):\n%s\n" \
    "$TAG_NAME" "$VPS_USER" "$VPS_HOST" "$VPS_PATH" "$COMMIT_SHA" "$FILE_COUNT" "$ALL_FILES")"
git tag -a "$TAG_NAME" -m "$TAG_MSG"
git push origin "$TAG_NAME"
log "Tag d'audit créé et poussé : $TAG_NAME"

# ── Redémarrage du service — double opt-in, jamais implicite ─────────────────
# DS-002 (incident 2026-07-04) : l'ancien "pkill -f advisor_loop.py" matche
# par SOUS-CHAINE — il tuait indifféremment core/advisor_loop.py (moteur réel,
# détient logs/advisor.lock) et advisor_loop.py racine (bot d'observation
# passif), puis ne relançait que le second. Un --restart déclenché par
# habitude aurait pu couper le moteur réel sans le relancer, silencieusement.
# Correctif : cible exacte obligatoire (--restart core|advisor), motif de
# recherche ancré (jamais de sous-chaîne), et refus si le fichier cible est
# absent du disque VPS plutôt qu'un échec silencieux.
if [[ $RESTART -eq 1 ]]; then
    if [[ $RESTART_DISABLED_UNTIL_RECONCILIATION -eq 1 ]]; then
        log "SKIP restart — désactivé jusqu'à réconciliation des branches (voir RECOVERY.md)"
    elif [[ -z "$VPS_RESTART_CMD" ]]; then
        log "SKIP restart — --restart passé mais VPS_RESTART_CMD non défini dans .env"
    else
        case "$RESTART_TARGET" in
            core) _target_path="core/advisor_loop.py"; _pgrep_pattern='core/advisor_loop\.py$' ;;
            advisor) _target_path="advisor_loop.py"; _pgrep_pattern='[[:space:]]advisor_loop\.py$' ;;
        esac

        if ! ssh $SSH_OPTS "$VPS_USER@$VPS_HOST" "test -f '$VPS_PATH/$_target_path'"; then
            log "ERREUR — $_target_path introuvable sur le VPS : refus de redémarrer (voir RECOVERY.md)"
            exit 1
        fi

        log "Redémarrage de $_target_path (--restart $RESTART_TARGET + VPS_RESTART_CMD définis)..."
        # shellcheck disable=SC2029
        ssh $SSH_OPTS "$VPS_USER@$VPS_HOST" \
            "cd '$VPS_PATH' && { pkill -f '$_pgrep_pattern' 2>/dev/null; sleep 3; true; } && export P6_SAFE_MODE=${P6_SAFE_MODE:-false} && nohup .venv/bin/python3 '$_target_path' < /dev/null >> logs/advisor.log 2>&1 & sleep 18 && pgrep -f '$_pgrep_pattern' > /dev/null && echo RUNNING" \
            | grep -q RUNNING \
            && log "Service redémarré (PID OK)" \
            || log "AVERTISSEMENT — PID non détecté après redémarrage"
    fi
elif [[ -n "$VPS_RESTART_CMD" ]]; then
    log "SKIP restart — --restart non passé (VPS_RESTART_CMD défini mais redémarrage jamais implicite)"
fi

log "Déploiement terminé"
