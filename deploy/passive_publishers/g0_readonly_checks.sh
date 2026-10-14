#!/bin/sh
# G0 — read-only, bounded checks for the passive publishers. To be run by the
# operator account (mathieu): chatgpt-ro cannot traverse /home/mathieu.
# Writes nothing, creates nothing, follows no recursion deeper than 2 levels,
# never opens a data file (stat / directory listings / df / findmnt only).
# Optional block G0-b (cycle duration) is OFF unless G0B=1.
RT="${RT:-/home/mathieu/crypto_ai_terminal}"
OUT="${OUT:-/home/mathieu/operator_presentation}"
SHA="${SHA:-1728b3ad952b87d903ccb7442579000da292b848}"
REL="${REL:-/opt/crypto-ai-terminal/operator}"
export LC_ALL=C
T() { timeout 5 "$@" 2>&1 | head -n 40; }

echo "== G0 $(date -u +%FT%TZ) user=$(id -un) uid=$(id -u)"

echo "== source files (stat only: path owner:group mode bytes mtime)"
for f in "$RT/cache/startup/alerts.jsonl" \
         "$RT/databases/burn_in_status_snapshot.json" \
         "$RT/alerts_audit.jsonl"; do
  stat -c '%n %U:%G %a %s %y' "$f" 2>&1
done

echo "== bounded search for the supervision audit (depth <= 2)"
T find "$RT" -maxdepth 2 -name 'alerts_audit.jsonl' -printf '%p %s %TY-%Tm-%TdT%TH:%TM:%TSZ\n'

echo "== directories (mode owner)"
T ls -ld "$RT" "$RT/databases" "$RT/cache" "$RT/cache/startup" "$OUT" 2>&1

echo "== databases/: direct entries only (depth 1), count and packet files"
START=$(date +%s.%N)
ENTRIES=$(timeout 10 find "$RT/databases" -mindepth 1 -maxdepth 1 -printf '.' 2>/dev/null | wc -c)
PACKETS=$(timeout 10 find "$RT/databases" -mindepth 1 -maxdepth 1 -name 'decision_packets_*.jsonl' -printf '%s\n' 2>/dev/null | awk '{n++; b+=$1} END {printf "%d files, %d bytes", n, b}')
END=$(date +%s.%N)
echo "entries=$ENTRIES (publisher cap 10000) packets: $PACKETS"
echo "listing wall time: $(echo "$END $START" | awk '{printf "%.3f s", $1-$2}')"
echo "five newest packet files:"
T find "$RT/databases" -mindepth 1 -maxdepth 1 -name 'decision_packets_*.jsonl' -printf '%TY-%Tm-%TdT%TH:%TM:%TSZ %s %f\n' | sort | tail -n 5

echo "== mount options and space"
T findmnt -T "$RT/databases" -no TARGET,FSTYPE,OPTIONS
T df -P "$RT/databases" "$(dirname "$OUT")"
T df -Pi "$RT/databases"

echo "== staged release used by the units"
stat -c '%n %U:%G %a' "$REL/staging-envs/$SHA/bin/python" "$REL/staging-src/$SHA" 2>&1
for m in runtime_service_snapshot storage_snapshot event_center_snapshot; do
  stat -c '%n %a %s' "$REL/staging-src/$SHA/observability/$m.py" 2>&1
done

if [ "${G0B:-0}" = "1" ]; then
  echo "== G0-b optional: duration of the last Advisor cycle (single small atomic file)"
  F="$RT/databases/live_snapshot.json"
  SIZE=$(stat -c %s "$F" 2>/dev/null || echo 0)
  if [ "$SIZE" -gt 0 ] && [ "$SIZE" -le 1048576 ]; then
    grep -o '"cycle": *[0-9]*\|"cycle_duration_ms": *[0-9.]*\|"ts": *[0-9.]*' "$F" | head -n 6
  else
    echo "live_snapshot.json absent or > 1 MiB: skipped (size=$SIZE)"
  fi
fi
echo "== end G0"
