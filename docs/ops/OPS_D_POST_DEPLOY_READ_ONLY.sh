#!/usr/bin/env bash
set -u

# OPS-D / LMI-RUNTIME-CERT-01 — post-deploy evidence capture.
# READ-ONLY: aucun restart, aucune mutation Git, aucune clé affichée.

cd /home/mathieu/crypto_ai_terminal || exit 1

SERVICE="crypto-lmi-observatory.service"
PID="$(systemctl show "$SERVICE" -p MainPID --value 2>/dev/null || true)"
LMI_DIR_RUNTIME=""

if [ -n "$PID" ] && [ "$PID" != "0" ] && [ -r "/proc/$PID/environ" ]; then
  LMI_DIR_RUNTIME="$(
    tr '\0' '\n' < "/proc/$PID/environ" \
      | sed -n 's/^LMI_DIR=//p' \
      | tail -n 1
  )"
fi

if [ -z "$LMI_DIR_RUNTIME" ]; then
  LMI_DIR_RUNTIME="databases/trade_analysis"
fi

case "$LMI_DIR_RUNTIME" in
  /*) ;;
  *) LMI_DIR_RUNTIME="$PWD/$LMI_DIR_RUNTIME" ;;
esac

STATE="$LMI_DIR_RUNTIME/lmi_live_state.json"
export STATE

echo "============================================================"
echo "OPS-D / LMI-RUNTIME-CERT-01 — POST-DEPLOY READ-ONLY"
echo "============================================================"
date -u --iso-8601=seconds
hostname

echo
echo "=== 1. PROVENANCE ==="
printf 'head='; git rev-parse HEAD
printf 'branch='; git branch --show-current
printf 'origin_main='; git rev-parse origin/main 2>/dev/null || true
git status --short --untracked-files=no

echo
echo "=== 2. PROCESS ==="
systemctl show "$SERVICE" --no-pager \
  -p LoadState \
  -p ActiveState \
  -p SubState \
  -p MainPID \
  -p NRestarts \
  -p ExecMainStartTimestamp \
  -p ActiveEnterTimestamp \
  -p MemoryCurrent \
  -p CPUUsageNSec \
  -p TasksCurrent \
  -p FragmentPath

echo "PID=$PID"
if [ -n "$PID" ] && [ "$PID" != "0" ] && [ -d "/proc/$PID" ]; then
  ps -p "$PID" -o pid,ppid,lstart,etime,%cpu,%mem,rss,vsz,nlwp,stat,cmd
  grep -E '^(VmRSS|VmSize|Threads|FDSize):' "/proc/$PID/status" || true
  printf 'fd_count='
  find "/proc/$PID/fd" -maxdepth 1 -type l 2>/dev/null | wc -l
  printf 'socket_fd_count='
  for f in /proc/"$PID"/fd/*; do
    readlink "$f" 2>/dev/null || true
  done | grep -c '^socket:' || true
fi

echo
echo "=== 3. SIDECAR ==="
echo "STATE=$STATE"
stat --printf='size_bytes=%s\nmtime=%y\nowner=%U:%G\nmode=%a\n' "$STATE" 2>/dev/null \
  || echo "STATE_FILE_ABSENT"

echo
echo "=== 4. COVERAGE/FRESHNESS — 60 s ==="
python3 - <<'PY'
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

path = Path(os.environ["STATE"])
samples = []


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


print("observation_start =", utc())
print("state_path =", path)

for i in range(7):
    data = json.loads(path.read_text(encoding="utf-8"))
    stats = data.get("stats") or {}
    coverage = data.get("coverage") or {}
    watch = data.get("watchlist") or []
    streams = data.get("stream_watchlist") or []
    symbols = data.get("symbols") or {}

    sample = {
        "time": utc(),
        "updated_at": data.get("updated_at"),
        "events": stats.get("events"),
        "watch": list(watch),
        "streams": list(streams),
        "symbols": symbols,
        "coverage": coverage,
        "stats": stats,
    }
    samples.append(sample)

    print(
        f"SAMPLE {i} time={sample['time']} "
        f"updated_at={sample['updated_at']} "
        f"pressure_fields={sample['events']} "
        f"watched={stats.get('symbols_watched')} "
        f"streamable={stats.get('symbols_streamable')} "
        f"active={stats.get('symbols_active')} "
        f"fresh={stats.get('symbols_fresh')} "
        f"stale={stats.get('symbols_stale')} "
        f"unavailable={stats.get('symbols_unavailable')}"
    )

    if i in (0, 6):
        print("  watchlist =", watch)
        print("  stream_watchlist =", streams)
        for sym in watch:
            cov = coverage.get(sym)
            st = symbols.get(sym)
            print(
                " ",
                sym,
                "coverage=",
                cov,
                "timestamp_ms=",
                (st or {}).get("timestamp_ms"),
                "price=",
                (st or {}).get("price"),
            )

    if i < 6:
        time.sleep(10)

print("observation_end =", utc())

first = samples[0]
last = samples[-1]
e0 = first.get("events")
e1 = last.get("events")
if isinstance(e0, int) and isinstance(e1, int):
    delta = e1 - e0
    print("pressure_field_delta =", delta)
    print("pressure_fields_per_second_approx =", round(delta / 60.0, 4))

advanced = []
stagnant = []
for sym in first["watch"]:
    t0 = (first["symbols"].get(sym) or {}).get("timestamp_ms")
    t1 = (last["symbols"].get(sym) or {}).get("timestamp_ms")
    if t0 and t1 and int(t1) > int(t0):
        advanced.append(sym)
    else:
        stagnant.append(sym)

print("symbols_timestamp_advanced =", advanced)
print("symbols_timestamp_not_advanced =", stagnant)
PY

echo
echo "=== 5. JOURNAL — 2 h ==="
journalctl \
  -u "$SERVICE" \
  --since "2 hours ago" \
  --no-pager \
  -o short-iso-precise \
  | grep -Ei \
    'Observatory|symbols unavailable|stream error|task done|restart|timeout|stall|StreamPipeline|keepalive|Traceback' \
  || true

echo
echo "=== 6. STORAGE ==="
df -h "$PWD" "$LMI_DIR_RUNTIME" 2>/dev/null || true
du -sh "$LMI_DIR_RUNTIME" logs/runtime logs/errors 2>/dev/null || true

echo
echo "=== FIN ==="
date -u --iso-8601=seconds
