#!/usr/bin/env bash
# backup_audit.sh — audit de sauvegarde avant réinitialisation de la machine.
#
# Outil de MESURE uniquement : lecture seule, aucune écriture dans le dépôt,
# aucun effet sur une décision de trading (ADR-0007).
#
# Répond à une seule question : « si je formate ce PC maintenant,
# qu'est-ce que je perds définitivement ? »
#
# Usage :
#   bash scripts/backup_audit.sh
#   bash scripts/backup_audit.sh --archive /chemin/vers/cle_usb
#
# Avec --archive : copie les artefacts non versionnés critiques vers le
# répertoire indiqué (jamais vers le dépôt lui-même).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

ARCHIVE_DIR=""
if [[ "${1:-}" == "--archive" ]]; then
    ARCHIVE_DIR="${2:-}"
    if [[ -z "$ARCHIVE_DIR" ]]; then
        echo "ERREUR : --archive attend un chemin de destination." >&2
        exit 1
    fi
fi

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'
BOLD=$'\033[1m'; NC=$'\033[0m'

PERTES=0

section() { printf '\n%s=== %s ===%s\n' "$BOLD" "$1" "$NC"; }
ok()      { printf '  %s[OK]%s   %s\n'    "$GREEN"  "$NC" "$1"; }
warn()    { printf '  %s[RISQUE]%s %s\n'  "$YELLOW" "$NC" "$1"; PERTES=$((PERTES+1)); }
danger()  { printf '  %s[PERTE]%s %s\n'   "$RED"    "$NC" "$1"; PERTES=$((PERTES+1)); }

printf '%sAUDIT DE SAUVEGARDE — %s%s\n' "$BOLD" "$REPO_ROOT" "$NC"
printf 'Date : %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# ---------------------------------------------------------------------------
# 1. Travail non commité
# ---------------------------------------------------------------------------
section "1. Travail non commité"

if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
    danger "Modifications non commitées :"
    git status --short | sed 's/^/          /'
else
    ok "Arbre de travail propre."
fi

STASHES=$(git stash list 2>/dev/null | wc -l | tr -d ' ')
if [[ "$STASHES" -gt 0 ]]; then
    danger "$STASHES stash(es) — invisibles sur GitHub :"
    git stash list | sed 's/^/          /'
else
    ok "Aucun stash en attente."
fi

# ---------------------------------------------------------------------------
# 2. Commits locaux non poussés
# ---------------------------------------------------------------------------
section "2. Commits locaux non poussés"

git fetch --all --quiet 2>/dev/null || warn "fetch impossible (réseau) — résultats ci-dessous potentiellement périmés."

NON_POUSSE=0
while read -r branche; do
    [[ -z "$branche" ]] && continue
    upstream=$(git rev-parse --abbrev-ref "${branche}@{upstream}" 2>/dev/null)
    if [[ -z "$upstream" ]]; then
        danger "Branche '$branche' n'a AUCUN équivalent distant — jamais poussée."
        NON_POUSSE=$((NON_POUSSE+1))
        continue
    fi
    ahead=$(git rev-list --count "${upstream}..${branche}" 2>/dev/null || echo 0)
    if [[ "$ahead" -gt 0 ]]; then
        danger "Branche '$branche' : $ahead commit(s) en avance sur $upstream."
        NON_POUSSE=$((NON_POUSSE+1))
    fi
done < <(git for-each-ref --format='%(refname:short)' refs/heads/)

[[ "$NON_POUSSE" -eq 0 ]] && ok "Toutes les branches locales sont poussées."

# Tags locaux non poussés (journal d'audit des déploiements)
TAGS_LOCAUX=$(git tag -l | sort)
TAGS_DISTANTS=$(git ls-remote --tags origin 2>/dev/null \
    | awk -F'refs/tags/' '{print $2}' | sed 's/\^{}$//' | sort -u)
TAGS_MANQUANTS=$(comm -23 <(echo "$TAGS_LOCAUX") <(echo "$TAGS_DISTANTS") | grep -v '^$' || true)
if [[ -n "$TAGS_MANQUANTS" ]]; then
    danger "Tags locaux absents de GitHub (journal d'audit des déploiements) :"
    echo "$TAGS_MANQUANTS" | sed 's/^/          /'
else
    ok "Tous les tags locaux sont sur GitHub."
fi

# ---------------------------------------------------------------------------
# 3. Artefacts non versionnés critiques
# ---------------------------------------------------------------------------
section "3. Artefacts non versionnés (exclus par .gitignore)"

# Chemin => description. Ces fichiers ne sont JAMAIS sur GitHub par conception.
CRITIQUES=(
    "databases/paper_trades.jsonl|Dataset scientifique — base de N, du CRI et de tous les seuils"
    "databases/paper_trades_vps.jsonl|Miroir local des trades VPS"
    "databases/regret_analysis.jsonl|Analyse de regret — MISSED_WIN / GOOD_REFUSAL"
    ".env|Clés API, VPS_RESTART_CMD, credentials"
    ".env.smtp|Credentials SMTP"
)

A_ARCHIVER=()
for entree in "${CRITIQUES[@]}"; do
    chemin="${entree%%|*}"
    desc="${entree##*|}"
    if [[ -e "$chemin" ]]; then
        taille=$(du -h "$chemin" 2>/dev/null | cut -f1)
        lignes=""
        [[ "$chemin" == *.jsonl ]] && lignes=" — $(wc -l < "$chemin" | tr -d ' ') lignes"
        danger "$chemin ($taille$lignes) : $desc"
        A_ARCHIVER+=("$chemin")
    else
        ok "$chemin absent localement — rien à perdre ici."
    fi
done

# Répertoires ignorés volumineux
section "4. Répertoires ignorés présents localement"
for rep in databases logs data archives cache setup; do
    [[ -d "$rep" ]] || continue
    # Ne compter que ce qui n'est PAS suivi par git : le reste est déjà sur GitHub.
    nb=$(git ls-files --others --directory --no-empty-directory -- "$rep" 2>/dev/null \
        | while read -r p; do
              if [[ -d "$p" ]]; then find "$p" -type f; else echo "$p"; fi
          done | wc -l | tr -d ' ')
    if [[ "$nb" -gt 0 ]]; then
        taille=$(du -sh "$rep" 2>/dev/null | cut -f1)
        warn "$rep/ — $nb fichier(s) non versionné(s) (répertoire : $taille)"
    else
        ok "$rep/ — tout son contenu est suivi par git."
    fi
done

# Tout autre fichier ignoré non couvert ci-dessus
AUTRES=$(git status --ignored --porcelain 2>/dev/null | grep '^!!' | sed 's/^!! //' \
    | grep -vE '^(__pycache__|\.venv/|venv/|node_modules/|\.pytest_cache|.*\.pyc$)' || true)
if [[ -n "$AUTRES" ]]; then
    printf '\n  Autres chemins ignorés (hors caches) :\n'
    echo "$AUTRES" | head -30 | sed 's/^/          /'
fi

# ---------------------------------------------------------------------------
# 5. Archivage optionnel
# ---------------------------------------------------------------------------
if [[ -n "$ARCHIVE_DIR" ]]; then
    section "5. Archivage vers $ARCHIVE_DIR"
    if [[ ! -d "$ARCHIVE_DIR" ]]; then
        echo "  ERREUR : $ARCHIVE_DIR n'existe pas." >&2
        exit 1
    fi
    DEST="$ARCHIVE_DIR/crypto-ia-terminal-backup-$(date -u '+%Y%m%dT%H%M%SZ')"
    mkdir -p "$DEST"
    for chemin in "${A_ARCHIVER[@]}"; do
        mkdir -p "$DEST/$(dirname "$chemin")"
        cp -p "$chemin" "$DEST/$chemin" && ok "copié : $chemin"
    done
    for rep in databases logs data archives; do
        [[ -d "$rep" ]] && cp -rp "$rep" "$DEST/" && ok "copié : $rep/"
    done
    printf '  Archive : %s\n' "$DEST"
    printf '  Vérifiez son contenu AVANT de réinitialiser la machine.\n'
fi

# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
section "VERDICT"
if [[ "$PERTES" -eq 0 ]]; then
    printf '  %sTout est sur GitHub. Réinitialisation sans perte.%s\n' "$GREEN" "$NC"
    exit 0
fi
printf '  %s%d point(s) de perte potentielle.%s\n' "$YELLOW" "$PERTES" "$NC"
printf '  Ne réinitialisez pas avant d'\''avoir traité chaque ligne [PERTE].\n'
printf '  Rappel : le VPS détient peut-être la copie vivante du dataset —\n'
printf '  vérifiez-la avant de considérer une perte locale comme acceptable.\n'
exit 1
