#!/usr/bin/env bash
# =============================================================================
# compare_vps.sh — Compare deux machines de production, dimension par dimension.
#
# À lancer APRÈS bootstrap_vps.sh et APRÈS la copie des données, AVANT
# d'éteindre l'ancienne machine. Il ne modifie rien, nulle part.
#
# Usage :
#   bash compare_vps.sh <hôte_ancien> <hôte_nouveau> [chemin_clé_ssh]
#
# Exemple :
#   bash compare_vps.sh mathieu@35.240.166.72 mathieu@34.x.x.x ~/.ssh/gcp_key
#
# Sortie : une ligne par dimension. IDENTIQUE / DIFFERENT / ABSENT.
# Code de sortie 0 seulement si toutes les dimensions critiques concordent.
# =============================================================================

set -uo pipefail

ANCIEN="${1:-}"
NOUVEAU="${2:-}"
CLE="${3:-$HOME/.ssh/gcp_key}"
RACINE="/home/mathieu/crypto_ai_terminal"

if [[ -z "$ANCIEN" || -z "$NOUVEAU" ]]; then
    sed -n '3,16p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
fi

ROUGE=$'\033[31m'; VERT=$'\033[32m'; JAUNE=$'\033[33m'; RAZ=$'\033[0m'
SSH_OPTS="-n -i $CLE -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=30"
ECARTS_CRITIQUES=0
ECARTS_TOLERES=0

# Interroge une machine. Toute erreur devient une chaîne visible plutôt qu'un
# silence : une dimension illisible ne doit jamais passer pour identique.
interroge() {
    local hote="$1" cmd="$2" out
    out="$(ssh $SSH_OPTS "$hote" "cd $RACINE 2>/dev/null; $cmd" 2>/dev/null)" \
        || { echo "<INJOIGNABLE>"; return; }
    [[ -z "$out" ]] && echo "<VIDE>" || echo "$out"
}

# $1 libellé, $2 commande, $3 criticite (critique|tolere)
compare() {
    local libelle="$1" cmd="$2" criticite="${3:-critique}"
    local a b
    a="$(interroge "$ANCIEN" "$cmd")"
    b="$(interroge "$NOUVEAU" "$cmd")"

    if [[ "$a" == "$b" ]]; then
        printf '  %sIDENTIQUE%s  %-38s %s\n' "$VERT" "$RAZ" "$libelle" \
            "$(echo "$a" | head -1 | cut -c1-30)"
    else
        if [[ "$criticite" == "critique" ]]; then
            printf '  %sDIFFERENT%s  %-38s\n' "$ROUGE" "$RAZ" "$libelle"
            ECARTS_CRITIQUES=$((ECARTS_CRITIQUES + 1))
        else
            printf '  %sECART%s      %-38s (toléré)\n' "$JAUNE" "$RAZ" "$libelle"
            ECARTS_TOLERES=$((ECARTS_TOLERES + 1))
        fi
        printf '      ancien  : %s\n' "$(echo "$a" | head -3 | tr '\n' ' ' | cut -c1-100)"
        printf '      nouveau : %s\n' "$(echo "$b" | head -3 | tr '\n' ' ' | cut -c1-100)"
    fi
}

echo
echo "  ancien  : $ANCIEN"
echo "  nouveau : $NOUVEAU"
echo

echo "── RUNTIME ──────────────────────────────────────────────────────────────"
compare "version Python du venv"    ".venv/bin/python --version"
compare "nombre de paquets pip"     ".venv/bin/pip freeze | wc -l"
compare "empreinte du pip freeze"   ".venv/bin/pip freeze | sort | sha256sum | cut -d' ' -f1"
compare "version ccxt"              ".venv/bin/python -c 'import ccxt;print(ccxt.__version__)'"
compare "étanchéité du venv"        ".venv/bin/python -c \"import sys;print('dist-packages' in ' '.join(sys.path))\""

echo
echo "── PROJET ───────────────────────────────────────────────────────────────"
compare "commit git HEAD"           "git rev-parse HEAD"
compare "branche courante"          "git branch --show-current"
compare "empreinte du code Python"  "find . -name '*.py' -not -path './.venv/*' -not -path '*/__pycache__/*' -type f -exec sha256sum {} + | sort -k2 | sha256sum | cut -d' ' -f1"
compare "nb de fichiers .py"        "find . -name '*.py' -not -path './.venv/*' -not -path '*/__pycache__/*' | wc -l"

echo
echo "── DONNÉES (le patrimoine) ──────────────────────────────────────────────"
compare "sha256 paper_trades.jsonl" "sha256sum databases/paper_trades.jsonl | cut -d' ' -f1"
compare "lignes paper_trades.jsonl" "wc -l < databases/paper_trades.jsonl"
compare "sha256 runtime_config"     "sha256sum databases/runtime_config.json | cut -d' ' -f1"
compare "fichiers regret/"          "ls databases/regret/ | wc -l"
compare "fichiers rejections/"      "ls databases/rejections/ | wc -l"
compare "fichiers observation/"     "ls databases/observation/ | wc -l"
compare "taille databases/"         "du -sm databases/ | cut -f1" tolere

echo
echo "── CONFIGURATION ────────────────────────────────────────────────────────"
# Noms de variables uniquement — aucune valeur n'est lue ni comparée.
compare "noms de variables .env"    "grep -oE '^[A-Z_][A-Z0-9_]*' .env | sort -u | sha256sum | cut -d' ' -f1"
compare "nombre de variables .env"  "grep -cE '^[A-Z_][A-Z0-9_]*=' .env"
compare "doublons dans .env"        "grep -oE '^[A-Z_][A-Z0-9_]*' .env | sort | uniq -d | tr '\n' ','"

echo
echo "── SERVICES ─────────────────────────────────────────────────────────────"
compare "unités systemd du projet"  "systemctl list-unit-files | grep -c '^crypto-'"
compare "timers actifs"             "systemctl list-timers --all 2>/dev/null | grep -c crypto"
compare "fuseau horaire"            "timedatectl show -p Timezone --value"

echo
echo "── SYSTÈME ──────────────────────────────────────────────────────────────"
compare "distribution"              ". /etc/os-release; echo \$VERSION_CODENAME"
compare "architecture"              "dpkg --print-architecture"
compare "python3.11 système"        "/usr/bin/python3.11 --version"

echo
echo "════════════════════════════════════════════════════════════════════════"
if [[ "$ECARTS_CRITIQUES" -eq 0 ]]; then
    printf '  %sMigration fidèle%s'"$RAZ"' — %d écart(s) toléré(s).\n' "$VERT" "$RAZ" "$ECARTS_TOLERES"
    echo "  L'ancienne machine peut être arrêtée."
    echo
    echo "  Vérifier tout de même, à la main, ce que ce script NE PEUT PAS voir :"
    echo "    - la nouvelle IP est-elle dans la whitelist MEXC ?"
    echo "    - les valeurs des secrets sont-elles correctes (jamais comparées ici) ?"
    echo "    - le moteur produit-il un cycle complet sans erreur ?"
    echo
    exit 0
else
    printf '  %s%d écart(s) CRITIQUE(S)%s — ne pas arrêter l'\''ancienne machine.\n' \
        "$ROUGE" "$ECARTS_CRITIQUES" "$RAZ"
    echo
    exit 1
fi
