#!/usr/bin/env bash
# scripts/vps_burnin_snapshot.sh — Snapshot burn-in centré simulation MEXC
# Usage:
#   bash scripts/vps_burnin_snapshot.sh
#   bash scripts/vps_burnin_snapshot.sh --hours 24

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

HOURS=24
if [[ "${1:-}" == "--hours" && -n "${2:-}" ]]; then
    HOURS="$2"
fi

SSH_OPTS=(
    -i "$VPS_KEY"
    -p "$VPS_PORT"
    -o BatchMode=yes
    -o StrictHostKeyChecking=no
    -o ConnectTimeout=15
)

echo "===================================="
echo "Burn-in Snapshot"
echo "Target : $VPS_USER@$VPS_HOST:$VPS_PORT"
echo "Window : ${HOURS}h"
echo "===================================="

ssh "${SSH_OPTS[@]}" "$VPS_USER@$VPS_HOST" \
    "VPS_PATH='$VPS_PATH' HOURS='$HOURS' bash -s" <<'REMOTE'
set -euo pipefail

LOG_FILE="$VPS_PATH/logs/advisor.log"
if [[ ! -f "$LOG_FILE" ]]; then
    echo "ERREUR: log introuvable: $LOG_FILE"
    exit 1
fi

# Fenetre approximative: 300 lignes par heure (cycles + debug)
LINES=$((HOURS * 300 + 2000))
[[ $LINES -lt 3000 ]] && LINES=3000

TMP_FILE="$(mktemp)"
tail -n "$LINES" "$LOG_FILE" > "$TMP_FILE"

count() {
    local pattern="$1"
    grep -cE "$pattern" "$TMP_FILE" 2>/dev/null || true
}

SIM_OPEN_BUY="$(count '\\[SIM\\] MEXC SIM .* ORDRE BUY')"
SIM_OPEN_SELL="$(count '\\[SIM\\] MEXC SIM .* ORDRE SELL')"
SIM_FILL="$(count '\\[SIM\\] FILL')"
SIM_CLOSE="$(count '\\[SIM\\] CLOSE')"
VERDICT_OK="$(count 'VERDICT . OK')"
VERDICT_BLOCK="$(count 'VERDICT . BLOQU')"
GATE_BLOCK="$(count 'GATE BLOCK')"
PORTFOLIO_BLOCK="$(count '\\[PortfolioBrain\\] Bloqu')"
TELEGRAM_SENT="$(count 'Telegram envoye')"
HEARTBEAT="$(count '\\[Heartbeat\\] \\[ALIVE\\]')"

TOTAL_SIM_OPEN=$((SIM_OPEN_BUY + SIM_OPEN_SELL))
TOTAL_REJECT=$((GATE_BLOCK + PORTFOLIO_BLOCK))
TOTAL_DECISIONS=$((VERDICT_OK + VERDICT_BLOCK))

echo "SIM_OPEN_BUY=$SIM_OPEN_BUY"
echo "SIM_OPEN_SELL=$SIM_OPEN_SELL"
echo "SIM_OPEN_TOTAL=$TOTAL_SIM_OPEN"
echo "SIM_FILL=$SIM_FILL"
echo "SIM_CLOSE=$SIM_CLOSE"
echo "VERDICT_OK=$VERDICT_OK"
echo "VERDICT_BLOCK=$VERDICT_BLOCK"
echo "GATE_BLOCK=$GATE_BLOCK"
echo "PORTFOLIO_BLOCK=$PORTFOLIO_BLOCK"
echo "REJECT_TOTAL=$TOTAL_REJECT"
echo "TELEGRAM_SENT=$TELEGRAM_SENT"
echo "HEARTBEAT=$HEARTBEAT"

if [[ $TOTAL_DECISIONS -gt 0 ]]; then
    BLOCK_RATE=$(awk -v b="$VERDICT_BLOCK" -v t="$TOTAL_DECISIONS" 'BEGIN { printf "%.2f", (100*b)/t }')
    echo "VERDICT_BLOCK_RATE_PCT=$BLOCK_RATE"
fi

echo "---- RECENT SIM LINES ----"
grep -Ei '\\[SIM\\]|mexc_simulator|VERDICT|PortfolioBrain|GATE BLOCK' "$TMP_FILE" | tail -n 25 || true

rm -f "$TMP_FILE"
REMOTE
