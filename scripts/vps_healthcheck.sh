#!/usr/bin/env bash
# scripts/vps_healthcheck.sh — Check santé VPS (process, logs, ports) en one-shot
# Usage: bash scripts/vps_healthcheck.sh

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
HEALTH_LOG_FILE="${HEALTH_LOG_FILE:-logs/advisor.log}"

if [[ -z "$VPS_HOST" || -z "$VPS_USER" || -z "$VPS_PATH" ]]; then
    echo "ERREUR: VPS_HOST, VPS_USER et VPS_PATH doivent etre definis dans .env"
    exit 2
fi

if [[ ! -f "$VPS_KEY" ]]; then
    echo "ERREUR: cle SSH introuvable: $VPS_KEY"
    exit 2
fi

SSH_OPTS=(
    -i "$VPS_KEY"
    -p "$VPS_PORT"
    -o BatchMode=yes
    -o StrictHostKeyChecking=no
    -o ConnectTimeout=15
)

echo "===================================="
echo "VPS Healthcheck"
echo "Target : $VPS_USER@$VPS_HOST:$VPS_PORT"
echo "Path   : $VPS_PATH"
echo "Log    : $HEALTH_LOG_FILE"
echo "===================================="

ssh "${SSH_OPTS[@]}" "$VPS_USER@$VPS_HOST" \
    "VPS_PATH='$VPS_PATH' HEALTH_LOG_FILE='$HEALTH_LOG_FILE' bash -s" <<'REMOTE'
set -euo pipefail

ROOT_DIR="$VPS_PATH"
LOG_PATH="$ROOT_DIR/$HEALTH_LOG_FILE"

if [[ ! -d "$ROOT_DIR" ]]; then
    echo "CRIT: chemin projet introuvable: $ROOT_DIR"
    exit 10
fi

echo
echo "=== 1) Processus ==="
PROC_OUTPUT="$(ps -eo pid,ppid,etimes,cmd | grep -E 'advisor_loop.py|main_v91.py|main_v16.py|quant_dashboard.py|streamlit|uvicorn|watchdog_vps.py' | grep -v grep || true)"
if [[ -z "$PROC_OUTPUT" ]]; then
    echo "WARN: aucun processus cible detecte"
else
    echo "$PROC_OUTPUT"
fi

echo
echo "=== 2) Logs (80 dernieres lignes) ==="
if [[ -f "$LOG_PATH" ]]; then
    tail -n 80 "$LOG_PATH"
else
    echo "WARN: log absent: $LOG_PATH"
fi

echo
echo "=== 3) Ports d'ecoute (cibles) ==="
PORT_OUTPUT=""
if command -v ss >/dev/null 2>&1; then
    PORT_OUTPUT="$(ss -ltn | grep -E ':(5010|5011|5013|5026|8000|8501|8502)([^0-9]|$)' || true)"
elif command -v netstat >/dev/null 2>&1; then
    PORT_OUTPUT="$(netstat -ltn 2>/dev/null | grep -E ':(5010|5011|5013|5026|8000|8501|8502)([^0-9]|$)' || true)"
else
    echo "WARN: ni ss ni netstat disponibles"
fi

if [[ -n "$PORT_OUTPUT" ]]; then
    echo "$PORT_OUTPUT"
else
    echo "WARN: aucun port cible detecte en ecoute"
fi

echo
echo "=== 4) Resume ==="
FAIL=0
if ! echo "$PROC_OUTPUT" | grep -q 'advisor_loop.py'; then
    echo "CRIT: advisor_loop.py non detecte"
    FAIL=1
else
    echo "OK: advisor_loop.py actif"
fi

if ! echo "$PORT_OUTPUT" | grep -qE ':(8000|8501)([^0-9]|$)'; then
    echo "WARN: ports 8000/8501 non detectes"
else
    echo "OK: au moins un port applicatif (8000/8501) detecte"
fi

if [[ -f "$LOG_PATH" ]]; then
    if tail -n 80 "$LOG_PATH" | grep -qiE 'traceback|fatal|segmentation fault'; then
        echo "CRIT: motif d'erreur critique detecte dans les logs"
        FAIL=1
    else
        echo "OK: pas de motif critique evident dans les 80 dernieres lignes"
    fi
fi

if [[ $FAIL -ne 0 ]]; then
    echo "HEALTHCHECK: FAIL"
    exit 1
fi

echo "HEALTHCHECK: OK"
REMOTE
