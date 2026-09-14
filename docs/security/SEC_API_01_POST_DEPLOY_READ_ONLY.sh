#!/usr/bin/env bash
# SEC-API-01 — post-deploy evidence collector.
# READ-ONLY: no restart, no daemon-reload, no key values printed.
set -uo pipefail

ROOT="${ROOT:-/home/mathieu/crypto_ai_terminal}"
cd "$ROOT" || exit 1

EXCHANGE_VARS=(
  MEXC_API_KEY MEXC_API_SECRET MEXC_SECRET_KEY
  BINANCE_API_KEY BINANCE_API_SECRET BINANCE_LIVE_API_KEY BINANCE_LIVE_API_SECRET
  BINANCE_FUTURES_DEMO_KEY BINANCE_FUTURES_DEMO_SECRET BINANCE_SECRET
  KRAKEN_API_KEY KRAKEN_API_SECRET GATEIO_API_KEY GATEIO_API_SECRET
  BYBIT_API_KEY BYBIT_API_SECRET OKX_API_KEY OKX_API_SECRET OKX_PASSWORD
  LIVE_READER_API_KEY LIVE_READER_API_SECRET
)

printf '%s\n' '============================================================'
printf '%s\n' 'SEC-API-01 — POST-DEPLOY READ-ONLY EVIDENCE'
printf '%s\n' '============================================================'
date -Is
hostname

echo
echo '=== 1. PROVENANCE ==='
printf 'head=%s\n' "$(git rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
printf 'branch=%s\n' "$(git branch --show-current 2>/dev/null || echo UNKNOWN)"
printf 'origin_main=%s\n' "$(git rev-parse origin/main 2>/dev/null || echo UNKNOWN)"

echo
echo '=== 2. UNIT BOUNDARIES ==='
for svc in \
  crypto-lmi-observatory.service \
  crypto-market-observer.service \
  crypto-market-radar.service \
  crypto-market-horizons.service \
  crypto-quant-observer.service \
  crypto-radar-bot.service \
  crypto-dashboard.service \
  paper-arena.service \
  crypto-watchdog.service \
  crypto-advisor.service
do
  echo "--- $svc"
  if systemctl cat "$svc" >/dev/null 2>&1; then
    systemctl cat "$svc" 2>/dev/null \
      | grep -E '^EnvironmentFile=|^UnsetEnvironment=|^ExecStart=' \
      || true
  else
    echo 'UNIT_NOT_INSTALLED'
  fi
done

echo
echo '=== 3. PROCESS SECRET-STATE MATRIX (NAMES/STATES ONLY) ==='
python3 - <<'PY'
from pathlib import Path
import subprocess

exchange_vars = {
    "MEXC_API_KEY", "MEXC_API_SECRET", "MEXC_SECRET_KEY",
    "BINANCE_API_KEY", "BINANCE_API_SECRET", "BINANCE_LIVE_API_KEY",
    "BINANCE_LIVE_API_SECRET", "BINANCE_FUTURES_DEMO_KEY",
    "BINANCE_FUTURES_DEMO_SECRET", "BINANCE_SECRET",
    "KRAKEN_API_KEY", "KRAKEN_API_SECRET", "GATEIO_API_KEY",
    "GATEIO_API_SECRET", "BYBIT_API_KEY", "BYBIT_API_SECRET",
    "OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSWORD",
    "LIVE_READER_API_KEY", "LIVE_READER_API_SECRET",
}
identity_vars = {
    "crypto-quant-observer.service": {"QUANT_CRYPTO_BOT_TOKEN", "QUANT_CRYPTO_CHAT_ID"},
    "crypto-radar-bot.service": {"RADAR_BOT_TOKEN", "RADAR_CHAT_ID"},
    "crypto-dashboard.service": {"DASHBOARD_PASSWORD"},
    "paper-arena.service": {"PAPER_ARENA_BOT_TOKEN", "PAPER_ARENA_CHAT_ID"},
    "crypto-watchdog.service": {"TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"},
}
all_identity_vars = set().union(*identity_vars.values())
services = [
    "crypto-lmi-observatory.service",
    "crypto-quant-observer.service",
    "crypto-radar-bot.service",
    "crypto-dashboard.service",
    "paper-arena.service",
    "crypto-watchdog.service",
    "crypto-advisor.service",
]

def pid_for(service: str) -> int:
    p = subprocess.run(
        ["systemctl", "show", service, "-p", "MainPID", "--value"],
        text=True,
        capture_output=True,
    )
    try:
        return int((p.stdout or "0").strip() or "0")
    except ValueError:
        return 0

for service in services:
    pid = pid_for(service)
    print(f"--- {service} pid={pid}")
    if pid <= 0 or not Path(f"/proc/{pid}/environ").exists():
        print("process=NOT_RUNNING")
        continue
    raw = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    env = {}
    for item in raw:
        if b"=" not in item:
            continue
        k, v = item.split(b"=", 1)
        env[k.decode(errors="replace")] = v
    present_private = sorted(k for k in exchange_vars if env.get(k))
    print("exchange_private_nonempty=" + (",".join(present_private) if present_private else "NONE"))
    expected = identity_vars.get(service, set())
    for name in sorted(expected):
        if name not in env:
            state = "ABSENT"
        elif env[name]:
            state = "NONEMPTY"
        else:
            state = "EMPTY"
        print(f"{name}={state}")
    foreign_nonempty = sorted(
        name for name in (all_identity_vars - expected) if env.get(name)
    )
    print(
        "foreign_identity_nonempty="
        + (",".join(foreign_nonempty) if foreign_nonempty else "NONE")
    )
PY

echo
echo '=== 4. SERVICE HEALTH ==='
for svc in \
  crypto-lmi-observatory.service \
  crypto-quant-observer.service \
  crypto-radar-bot.service \
  crypto-dashboard.service \
  paper-arena.service \
  crypto-watchdog.service \
  crypto-advisor.service
do
  if systemctl cat "$svc" >/dev/null 2>&1; then
    systemctl show "$svc" \
      -p ActiveState -p SubState -p MainPID -p NRestarts \
      --no-pager 2>/dev/null | tr '\n' ' '
    echo " service=$svc"
  fi
done

echo
echo '=== 5. MARKET TIMERS ==='
for timer in crypto-market-observer.timer crypto-market-radar.timer crypto-market-horizons.timer; do
  if systemctl cat "$timer" >/dev/null 2>&1; then
    systemctl show "$timer" -p ActiveState -p SubState -p NextElapseUSecRealtime --no-pager 2>/dev/null \
      | tr '\n' ' '
    echo " timer=$timer"
  else
    echo "timer=$timer NOT_INSTALLED"
  fi
done

echo
echo '=== 6. RECENT PASSIVE ERRORS ==='
for svc in crypto-lmi-observatory.service crypto-quant-observer.service crypto-radar-bot.service crypto-dashboard.service paper-arena.service crypto-watchdog.service; do
  if systemctl cat "$svc" >/dev/null 2>&1; then
    echo "--- $svc"
    journalctl -u "$svc" --since '10 minutes ago' --no-pager 2>/dev/null \
      | grep -Ei 'traceback|fatal|exception|error|failed|401|403|409' \
      | tail -20 || true
  fi
done

echo
echo '=== END SEC-API-01 READ-ONLY EVIDENCE ==='
