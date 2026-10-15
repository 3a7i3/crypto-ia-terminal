#!/bin/sh
# G0 — read-only, bounded checks for the passive publishers. To be run by the
# operator account (mathieu): chatgpt-ro cannot traverse /home/mathieu.
# Writes nothing, creates nothing (no temporary file), recurses at most 2 levels
# (audit search) and never opens a data file (stat / listings / df / findmnt).
# Every command keeps its error and timeout status: a result is COMPLETE only
# when its command finished with status 0 inside its time limit; otherwise it is
# reported INCOMPLETE and its numbers are lower bounds, never a full answer.
# Optional G0-b (cycle duration of the last Advisor cycle) is OFF unless G0B=1.
RT="${RT:-/home/mathieu/crypto_ai_terminal}"
OUT="${OUT:-/home/mathieu/operator_presentation}"
SHA="${SHA:-1728b3ad952b87d903ccb7442579000da292b848}"
REL="${REL:-/opt/crypto-ai-terminal/operator}"
CAP="${CAP:-10000}"
FIND_TIMEOUT="${FIND_TIMEOUT:-10}"
export LC_ALL=C
# T: run with a 5 s limit, print everything (no truncation), then the status.
T() {
  timeout 5 "$@" 2>&1; rc=$?
  if [ "$rc" -eq 124 ]; then echo "!! TIMEOUT after 5 s -> INCOMPLETE, no result: $*"
  elif [ "$rc" -ne 0 ]; then echo "!! exit status $rc (error shown above, not a valid result): $*"; fi
}

echo "== G0 $(date -u +%FT%TZ) user=$(id -un) uid=$(id -u) cap=$CAP"

echo "== source files (path owner:group mode bytes mtime)"
for f in "$RT/cache/startup/alerts.jsonl" \
         "$RT/databases/burn_in_status_snapshot.json" \
         "$RT/alerts_audit.jsonl"; do
  T stat -c '%n %U:%G %a %s %y' "$f"
done

echo "== supervision audit search (depth <= 2)"
T find "$RT" -maxdepth 2 -name 'alerts_audit.jsonl' -printf '%p %s %TY-%Tm-%TdT%TH:%TM:%TSZ\n'

echo "== directories (mode owner)"
T ls -ld "$RT" "$RT/databases" "$RT/cache" "$RT/cache/startup" "$OUT"

echo "== databases/: ONE depth-1 traversal (entries, packets, five newest)"
START=$(date +%s.%N)
# find prints one 'E' record per direct child; its own errors are merged into the
# stream (lines not starting with 'E') and its exit status is appended as 'RC='.
# awk stops reading once more than CAP entries were seen (INCOMPLETE, no head).
RESULT=$( { timeout "$FIND_TIMEOUT" find "$RT/databases" -mindepth 1 -maxdepth 1 \
              -printf 'E\t%s\t%T@\t%f\n' 2>&1; echo "RC=$?"; } |
  awk -F'\t' -v cap="$CAP" '
    /^RC=/ { rc = substr($0, 4); seen_rc = 1; next }
    $1 != "E" || NF != 4 { err++; next }
    { n++
      if (n > cap) { over = 1; exit }
      if ($4 ~ /^decision_packets_.*\.jsonl$/) {
        p++; b += $2
        # keep the five most recent by mtime (no sort, no truncation of input)
        for (i = 1; i <= 5; i++) if (!(i in t) || $3 + 0 > t[i] + 0) break
        if (i <= 5) {
          for (j = 5; j > i; j--) { t[j] = t[j-1]; s[j] = s[j-1]; f[j] = f[j-1] }
          t[i] = $3; s[i] = $2; f[i] = $4
        }
      } }
    END {
      status = "COMPLETE"
      if (over) status = "INCOMPLETE(more than " cap " entries; counts are lower bounds)"
      else if (!seen_rc) status = "INCOMPLETE(no exit status)"
      else if (rc != 0) status = "INCOMPLETE(find status " rc "; 124=TIMEOUT)"
      else if (err > 0) status = "INCOMPLETE(" err " find error line(s))"
      printf "STATUS=%s\nENTRIES=%d\nPACKETS=%d\nPACKET_BYTES=%d\n", status, n - (over ? 1 : 0), p, b
      for (i = 1; i <= 5; i++) if (i in t) printf "NEWEST=%s\t%s\t%s\n", t[i], s[i], f[i]
    }' )
END=$(date +%s.%N)
echo "$RESULT" | grep -v '^NEWEST=' || true
echo "traversal wall time (find+awk, ONE pass): $(echo "$END $START" | awk '{printf "%.3f s", $1-$2}')"
echo "note: this is the duration of one listing, NOT the cost of the publisher"
echo "      (Python start-up + scandir + stat + JSON + fsync): measured later, G1 only."
case "$RESULT" in
  *STATUS=COMPLETE*) echo "five newest packet files (UTC mtime, bytes, name), from that same pass:" ;;
  *) echo "five newest packet files among the entries READ BEFORE THE STOP (PARTIAL, NOT the true newest):" ;;
esac
echo "$RESULT" | grep '^NEWEST=' | sed 's/^NEWEST=//' | while IFS="$(printf '\t')" read -r mt sz nm; do
  echo "$(date -u -d "@${mt%.*}" +%FT%TZ 2>/dev/null || echo "$mt") $sz $nm"
done

echo "== mount options and space"
T findmnt -T "$RT/databases" -no TARGET,FSTYPE,OPTIONS
T df -P "$RT/databases" "$(dirname "$OUT")"
T df -Pi "$RT/databases"

echo "== staged release used by the units"
T stat -c '%n %U:%G %a' "$REL/staging-envs/$SHA/bin/python" "$REL/staging-src/$SHA"
for m in runtime_service_snapshot storage_snapshot event_center_snapshot; do
  T stat -c '%n %a %s' "$REL/staging-src/$SHA/observability/$m.py"
done

if [ "${G0B:-0}" = "1" ]; then
  echo "== G0-b optional: last Advisor cycle (one small file, read once, <= 1 MiB)"
  F="$RT/databases/live_snapshot.json"
  SIZE=$(stat -c %s "$F" 2>/dev/null || echo 0)
  if [ "$SIZE" -gt 0 ] && [ "$SIZE" -le 1048576 ]; then
    T grep -o '"cycle": *[0-9]*\|"cycle_duration_ms": *[0-9.]*\|"ts": *[0-9.]*' "$F"
  else
    echo "live_snapshot.json absent or > 1 MiB: NOT READ (size=$SIZE) -> INCOMPLETE"
  fi
fi
echo "== end G0"
