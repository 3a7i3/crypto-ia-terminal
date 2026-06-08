#!/usr/bin/env bash
# scripts/vps_mexc_focus.sh — Vue centrée simulation MEXC (one-shot ou follow)
# Usage:
#   bash scripts/vps_mexc_focus.sh            # snapshot (300 dernières lignes)
#   bash scripts/vps_mexc_focus.sh --follow   # suivi temps réel

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"

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
    echo "ERREUR: VPS_HOST, VPS_USER et VPS_PATH doivent etre definis dans .env"
    exit 2
fi

if [[ ! -f "$VPS_KEY" ]]; then
    echo "ERREUR: cle SSH introuvable: $VPS_KEY"
    exit 2
fi

FOLLOW=0
if [[ "${1:-}" == "--follow" || "${1:-}" == "-f" ]]; then
    FOLLOW=1
fi

SSH_OPTS=(
    -i "$VPS_KEY"
    -p "$VPS_PORT"
    -o BatchMode=yes
    -o StrictHostKeyChecking=no
    -o ConnectTimeout=15
)

FILTER="mexc_simulator|\\[SIM\\]|PortfolioBrain|VERDICT|SIGNAL ACTIONABLE|GATE|TRADE_REFUSED|RAPPORT|Telegram"

echo "===================================="
echo "VPS MEXC Focus"
echo "Target : $VPS_USER@$VPS_HOST:$VPS_PORT"
echo "Path   : $VPS_PATH/logs/advisor.log"
echo "Mode   : $([[ $FOLLOW -eq 1 ]] && echo 'follow' || echo 'snapshot')"
echo "===================================="

if [[ $FOLLOW -eq 1 ]]; then
    ssh "${SSH_OPTS[@]}" "$VPS_USER@$VPS_HOST" \
        "tail -n 200 -F '$VPS_PATH/logs/advisor.log' | grep --line-buffered -Ei '$FILTER'"
else
    ssh "${SSH_OPTS[@]}" "$VPS_USER@$VPS_HOST" \
        "tail -n 300 '$VPS_PATH/logs/advisor.log' | grep -Ei '$FILTER' || true"
fi
