# G1 — stage, verify and measure the passive publishers. NOTHING PERSISTENT:
# every write goes to ONE private temporary directory (mode 0700) that is removed
# at the end. No sudo, no install, no /etc, no output directory, no timer, no
# service started or restarted, no restart of the API or the Advisor.
# To run as mathieu. The three publisher commands are the ones of the unit files
# below, run against the temporary output directory; they only READ the runtime
# sources (alerts.jsonl, databases/ metadata, burn-in projection path, one
# `systemctl show crypto-advisor.service`).
# Exit status: 0 only if every check passed and the cleanup succeeded; 1 otherwise
# (verify, publisher, missing artifact, invalid contract, cleanup); 129/130/143 on
# HUP/INT/TERM. Cleanup always happens last, after the report.
SHA="${SHA:-1728b3ad952b87d903ccb7442579000da292b848}"
REL="${REL:-/opt/crypto-ai-terminal/operator}"
RT="${RT:-/home/mathieu/crypto_ai_terminal}"
OUTF=/home/mathieu/operator_presentation
PYBIN="${PYBIN:-$REL/staging-envs/$SHA/bin/python}"
SRC="${SRC:-$REL/staging-src/$SHA}"
RUNS="${RUNS:-5}"
case "$RUNS" in 1|2|3|4|5|6|7|8|9|10) ;; *) RUNS=5 ;; esac
export LC_ALL=C
umask 077

FAILS=0; FAILMSG=""; CHILD=""; CLEANED=0; CLEANFAIL=0; STRAY=0; W=""
fail() { FAILS=$((FAILS + 1)); FAILMSG="${FAILMSG}  - $1
"; }

# Stop the running child (and anything still using the work dir) BEFORE removing it.
stop_child() {
  if [ -n "$CHILD" ] && kill -0 "$CHILD" 2>/dev/null; then
    kill -TERM "$CHILD" 2>/dev/null
    n=0; while kill -0 "$CHILD" 2>/dev/null && [ "$n" -lt 20 ]; do sleep 0.1; n=$((n + 1)); done
    kill -0 "$CHILD" 2>/dev/null && kill -KILL "$CHILD" 2>/dev/null
    wait "$CHILD" 2>/dev/null
  fi
  CHILD=""
  if [ -n "$W" ] && command -v pgrep >/dev/null 2>&1; then
    n=0
    while pgrep -f -- "$W" >/dev/null 2>&1 && [ "$n" -lt 40 ]; do
      [ "$n" -eq 0 ] && pkill -TERM -f -- "$W" 2>/dev/null
      [ "$n" -eq 15 ] && pkill -KILL -f -- "$W" 2>/dev/null
      sleep 0.1; n=$((n + 1))
    done
    pgrep -f -- "$W" >/dev/null 2>&1 && STRAY=1
  fi
}
safe_cleanup() {
  [ "$CLEANED" -eq 1 ] && return 0
  [ -n "$W" ] || { CLEANED=1; return 0; }
  stop_child
  if [ "$STRAY" -eq 1 ]; then
    echo "!! CLEANUP REFUSED: processes using $W are still running; directory KEPT for inspection"
    CLEANFAIL=1; CLEANED=1; return 1
  fi
  rm -rf "$W"
  if [ -e "$W" ]; then echo "!! CLEANUP FAILED: $W still exists"; CLEANFAIL=1
  else echo "cleanup OK: $W removed, no child process left"; fi
  CLEANED=1
}
report() {
  echo "== summary (before cleanup)"
  if [ "$FAILS" -eq 0 ]; then echo "RESULT: OK (all checks passed)"
  else echo "RESULT: FAILED ($FAILS problem(s)):"; printf '%s' "$FAILMSG"; fi
}
on_signal() {
  trap '' INT TERM HUP
  echo "!! interrupted by SIG$1: stopping children, then cleaning up"
  fail "interrupted by SIG$1"
  report
  safe_cleanup
  exit "$2"
}
# Run argv in the background and wait for it: a trapped signal then acts at once and
# the child can be stopped (a foreground child would delay the trap until it ends).
runbg() { LOG=$1; shift; "$@" >"$LOG" 2>&1 & CHILD=$!; wait "$CHILD"; RC=$?; CHILD=""; }

[ "$(id -un)" = "mathieu" ] || echo "WARN: not running as mathieu ($(id -un))"
W=$(mktemp -d "${TMPDIR:-/tmp}/g1.XXXXXX") || { echo "ABORT: no temporary directory"; exit 1; }
trap 'on_signal INT 130' INT
trap 'on_signal TERM 143' TERM
trap 'on_signal HUP 129' HUP
trap 'safe_cleanup' EXIT
FREE=$(df -Pk "$W" | awk 'NR==2{print $4}')
if [ "${FREE:-0}" -lt 65536 ]; then
  fail "less than 64 MiB free in $W (free=${FREE:-?} KiB)"; report; safe_cleanup; exit 1
fi
mkdir "$W/units" "$W/out"
echo "== G1 $(date -u +%FT%TZ) user=$(id -un) work=$W runs=$RUNS"
echo "== sole write area: $W (0700, removed at the end); output dir $OUTF is NOT created"
echo "== code under test: $SRC (release $SHA = the DEPLOYED code, as deployed)"
if grep -q PARTIAL_TAIL "$SRC/observability/event_center_contract.py" 2>/dev/null; then
  echo "   PARTIAL_TAIL / events 1.1.0 in this code: YES (this is NOT the deployed release)"
else
  echo "   PARTIAL_TAIL / events 1.1.0 in this code: no (expected for 1728b3ad). G1 does NOT validate the new tail read."
fi

@@UNITS@@
cat > "$W/check.py" <<'PY'
import json, sys
kind, path = sys.argv[1], sys.argv[2]
doc = json.load(open(path))
if kind == "runtime":
    from observability.runtime_service_contract import validate_runtime_service_snapshot as ok
    extra = {k: doc["service"].get(k) for k in ("query_status", "load_state", "active_state")}
elif kind == "storage":
    from observability.storage_contract import validate_storage_snapshot as ok
    extra = {k: doc.get(k) for k in ("source_status", "entries_observed", "matched_file_count", "total_bytes")}
else:
    from observability.event_center_contract import validate_event_center as ok
    extra = {"schema_version": doc["schema_version"], "sources": [(s["source_id"], s["status"]) for s in doc["sources"]]}
valid = bool(ok(doc))
print("   contract-valid=%s %s" % (valid, extra))
sys.exit(0 if valid else 1)
PY
echo "== 1. staged $(ls "$W/units" | wc -l) unit files"
runbg "$W/verify.log" sh -c 'cd "$1" && exec systemd-analyze verify ./crypto-publish-*.service ./crypto-publish-*.timer' sh "$W/units"
cat "$W/verify.log"
echo "verify exit status: $RC  (0 = no error; messages above, if any, are findings)"
[ "$RC" -eq 0 ] || fail "systemd-analyze verify exit status $RC: $(head -c 300 "$W/verify.log" | tr '\n' ' ')"

echo "== 2. offline security exposure (systemd-analyze security --offline)"
if systemd-analyze security --help 2>&1 | grep -q -- '--offline'; then
  for u in "$W"/units/*.service; do
    runbg "$W/sec.log" timeout 10 systemd-analyze security --offline=true --no-pager "$u"
    echo "$(basename "$u"): exit $RC $(tail -n 1 "$W/sec.log")"
    [ "$RC" -eq 0 ] || fail "security --offline exit status $RC for $(basename "$u")"
  done
else
  echo "SKIPPED: this systemd-analyze has no --offline (security is then checked at G2 on installed units)"
fi

# stat-only fingerprints of live sources (informational: live writers may change them)
fp() { stat -c '%n size=%s mtime=%Y ctime=%Z' "$RT/cache/startup/alerts.jsonl" "$RT/databases/burn_in_status_snapshot.json" 2>&1; stat -c '%n mtime=%Y ctime=%Z' "$RT/databases" 2>&1; }
BEFORE=$(fp)

echo "== 3. measure each publisher: $RUNS runs, 20 s limit, nice 19, fresh output dir and immediate validation per run"
if ! cd "$SRC"; then fail "source directory $SRC is not accessible"; fi
for pair in runtime-service:runtime:runtime_service_snapshot.json storage:storage:storage_snapshot.json events:events:event_center_snapshot.json; do
  NAME=${pair%%:*}; REST=${pair#*:}; KIND=${REST%%:*}; ART=${REST#*:}
  CMD=$(sed -n 's/^ExecStart=//p' "$W/units/crypto-publish-$NAME.service" | sed 's/%%/%/g')
  CMD=$(printf '%s' "$CMD" | sed "s#$REL/staging-envs/$SHA/bin/python#$PYBIN#g; s#$OUTF#$W/out#g; s#/home/mathieu/crypto_ai_terminal#$RT#g")
  echo "-- $NAME"
  TIMES=""; BAD=0; I=0
  while [ "$I" -lt "$RUNS" ]; do
    I=$((I + 1))
    rm -rf "$W/out"; mkdir "$W/out"   # no artifact of a previous run can validate this one
    S=$(date +%s.%N)
    runbg "$W/run.log" env -i PATH=/usr/bin:/bin PYTHONPATH="$SRC" PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 TZ=UTC LC_ALL=C \
        timeout 20 nice -n 19 sh -c "$CMD"
    PRC=$RC
    E=$(date +%s.%N)
    T=$(echo "$E $S" | awk '{printf "%.3f", $1-$2}')
    TIMES="$TIMES $T"
    if [ "$PRC" -ne 0 ]; then
      BAD=$((BAD + 1)); MSG="$NAME run $I: publisher exit status $PRC (124 = TIMEOUT) in ${T}s: $(head -c 300 "$W/run.log" | tr '\n' ' ')"
      echo "   $MSG"; fail "$MSG"
    elif [ ! -f "$W/out/$ART" ]; then
      BAD=$((BAD + 1)); MSG="$NAME run $I: exit 0 but artifact $ART not produced"
      echo "   $MSG"; fail "$MSG"
    else
      runbg "$W/check.log" env -i PATH=/usr/bin:/bin PYTHONPATH="$SRC" PYTHONDONTWRITEBYTECODE=1 "$PYBIN" "$W/check.py" "$KIND" "$W/out/$ART"
      if [ "$RC" -ne 0 ]; then
        BAD=$((BAD + 1)); MSG="$NAME run $I: contract check exit status $RC (1 = invalid, other = error): $(head -c 300 "$W/check.log" | tr '\n' ' ')"
        echo "   $MSG"; fail "$MSG"
      elif [ "$I" -eq "$RUNS" ]; then
        echo "   artifact: $(stat -c %s "$W/out/$ART") bytes"; cat "$W/check.log"
      fi
    fi
  done
  echo "   wall seconds per run:$TIMES   failed runs: $BAD/$RUNS"
  echo "$TIMES" | tr ' ' '\n' | grep -v '^$' | sort -n | awk '{a[NR]=$1} END{printf "   min=%s median=%s max=%s (whole process: interpreter start + read + JSON + fsync)\n", a[1], a[int((NR+1)/2)], a[NR]}'
done

AFTER=$(fp)
echo "== 4. sources before/after (stat only; live writers may legitimately change them)"
if [ "$BEFORE" = "$AFTER" ]; then echo "UNCHANGED"; else echo "CHANGED (informational):"; echo "--- before"; echo "$BEFORE"; echo "--- after"; echo "$AFTER"; fi

report
echo "== 5. cleanup"
safe_cleanup
echo "== end G1"
if [ "$FAILS" -ne 0 ] || [ "$CLEANFAIL" -ne 0 ]; then exit 1; fi
exit 0
