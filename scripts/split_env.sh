#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# split_env_secrets.sh — Sépare `.env` en deux fichiers :
#   .env          → flags, paramètres, chemins (non-secrets)
#   .env.secrets  → tokens, API keys, mots de passe (chmod 600)
#
# Idempotent : détecte si `.env.secrets` existe déjà et refuse d'écraser.
# Non destructif : produit `.env.secrets.new` et `.env.new`, à valider avant
# de renommer. Aucune modification appliquée automatiquement.
#
# Usage sur VPS :
#   cd ~/crypto_ai_terminal
#   bash scripts/split_env_secrets.sh
#   # → inspecter .env.secrets.new et .env.new
#   # → si OK : appliquer manuellement (les commandes sont affichées à la fin)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SRC=".env"
OUT_SECRETS=".env.secrets.new"
OUT_REST=".env.new"

if [[ ! -f "$SRC" ]]; then
    echo "[split_env] $SRC introuvable — rien à séparer."
    exit 1
fi

if [[ -f ".env.secrets" ]]; then
    echo "[split_env] REFUS : .env.secrets existe déjà."
    echo "    Ce script ne fusionne pas — si vous voulez re-séparer,"
    echo "    déplacez d'abord .env.secrets ailleurs manuellement."
    exit 1
fi

# Variables considérées comme SECRETS — critère : un match strict par nom OU
# une clé qui finit par _TOKEN / _API_KEY / _API_SECRET / _PASS / _PASSWORD.
# Liste explicite pour les cas qui ne matchent pas le suffixe (chat_id secondaires,
# EMAIL_FROM_ADDR, EMAIL_TO_ADDR — considérés secrets par prudence).
SECRET_EXACT_NAMES=(
    TELEGRAM_CHAT_ID
    TELEGRAM_BEHAVIOR_CHAT_ID
    REAL_ACCOUNT_CHAT_ID
    RAPPORT_AUTOMATIQUE_CHAT_ID
    PAPER_ARENA_CHAT_ID
    MON_PORTFOLIO_CHAT_ID
    QUANT_CRYPTO_CHAT_ID
    QC_PINNED_MSG_ID
    TELEMETRIE_IA_CHAT_ID
    EMAIL_FROM_ADDR
    EMAIL_TO_ADDR
    EMAIL_SMTP_SERVER
    EMAIL_SMTP_PORT
    SLACK_WEBHOOK_URL
)

is_secret_key() {
    local key="$1"
    case "$key" in
        *_TOKEN|*_API_KEY|*_API_SECRET|*_PASS|*_PASSWORD|*_SECRET) return 0 ;;
    esac
    for n in "${SECRET_EXACT_NAMES[@]}"; do
        [[ "$key" == "$n" ]] && return 0
    done
    return 1
}

: > "$OUT_SECRETS"
: > "$OUT_REST"

# En-têtes
cat > "$OUT_SECRETS" <<'HEADER'
# ═══════════════════════════════════════════════════════════════════════════
#  .env.secrets — SEULS les secrets (tokens Telegram, API keys, mots de passe)
# ═══════════════════════════════════════════════════════════════════════════
#
# Chargé par systemd APRÈS `.env` (les valeurs ici gagnent en cas de conflit).
# Ne jamais committer. chmod 600 obligatoire.
#
# Voir .env.secrets.example pour la documentation détaillée (quel token
# correspond à quel bot BotFather, quel processus le lit).
# ═══════════════════════════════════════════════════════════════════════════

HEADER

cat > "$OUT_REST" <<'HEADER'
# ═══════════════════════════════════════════════════════════════════════════
#  .env — Configuration NON-secrète (flags, seuils, chemins)
# ═══════════════════════════════════════════════════════════════════════════
#
# Les secrets (tokens, API keys, mots de passe) ont été déplacés dans
# `.env.secrets`, chargé automatiquement par systemd via un second
# EnvironmentFile= dans chaque unit.
# ═══════════════════════════════════════════════════════════════════════════

HEADER

# Buffer courant : accumule les commentaires jusqu'à trouver une KEY=…, puis
# route le tout (commentaires + ligne KEY) vers le bon fichier de sortie.
buf=""
routed_secret=0
routed_rest=0

flush_to() {
    # $1 = fichier cible
    if [[ -n "$buf" ]]; then
        printf '%s' "$buf" >> "$1"
        buf=""
    fi
}

while IFS= read -r line || [[ -n "$line" ]]; do
    # Ligne KEY=VALUE ?
    if [[ "$line" =~ ^([A-Z_][A-Z0-9_]*)= ]]; then
        key="${BASH_REMATCH[1]}"
        if is_secret_key "$key"; then
            flush_to "$OUT_SECRETS"
            printf '%s\n' "$line" >> "$OUT_SECRETS"
            routed_secret=$((routed_secret + 1))
        else
            flush_to "$OUT_REST"
            printf '%s\n' "$line" >> "$OUT_REST"
            routed_rest=$((routed_rest + 1))
        fi
    else
        # Commentaire, ligne vide → accumule
        buf+="$line"$'\n'
    fi
done < "$SRC"

# Vider le reste dans .env.new (tail commentaires en fin de fichier)
flush_to "$OUT_REST"

echo ""
echo "[split_env] Terminé."
echo "  $OUT_SECRETS : $routed_secret variables secrètes"
echo "  $OUT_REST    : $routed_rest variables non-secrètes"
echo ""
echo "Prochaines étapes MANUELLES (rien n'est appliqué automatiquement) :"
echo ""
echo "  1. Inspecter les deux nouveaux fichiers :"
echo "       diff <(sort .env) <(sort .env.new .env.secrets.new)"
echo "       # doit ne montrer que des différences de commentaires/ordre"
echo ""
echo "  2. Snapshot de sécurité :"
echo "       cp .env .env.backup-\$(date +%Y%m%d-%H%M)"
echo ""
echo "  3. Basculer :"
echo "       mv .env.secrets.new .env.secrets && chmod 600 .env.secrets"
echo "       mv .env.new .env"
echo ""
echo "  4. Redémarrer les services :"
echo "       sudo systemctl daemon-reload"
echo "       sudo systemctl restart crypto-advisor crypto-quant-observer \\"
echo "           crypto-radar-bot crypto-watchdog paper-arena"
echo ""
echo "  5. Vérifier avec le script whoami (getMe sur chaque token) — les"
echo "     6 blocs Telegram doivent revenir sur leurs bots respectifs."
