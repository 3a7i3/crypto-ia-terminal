# G3 — one-shot systemd trials of ONE passive publisher (timers stay disabled).
# Usage:  sh g3.sh plan <runtime-service|storage>      read-only, any user, nothing written
#         sh g3.sh run  <runtime-service|storage>      root, from a PROTECTED copy, 3 trials
# `run` starts crypto-publish-<pub>.service exactly RUNS times (>= GAP s apart), one trial after
# the other, and after each one checks: systemd Result/ExecMainStatus, the artifact (regular file,
# owner, mode, size, nothing else in the output directory, refreshed), the artifact contract
# (validators of the DEPLOYED release, run as the output owner with an empty environment), the
# timers (still disabled and inactive), and Advisor / API / web (unchanged). The first failure
# stops the series: nothing is retried, nothing is "repaired".
# The ONLY systemctl verbs in this script: `show`, and `start` of the one selected .service.
# Never enable, stop, restart, reload, edit, mask, link, or touch a timer, a drop-in, Advisor,
# API, web, any EnvironmentFile or .env, any data source other than what the unit itself reads.
# Exit status: 0 all checks passed; 1 a check failed; 2 usage; 3 not root / not protected;
# 129/130/143 signals (a oneshot already started ends by itself within its TimeoutStartSec=20s).
MODE="${1:-plan}"; PUB="${2:-}"
case "$MODE" in plan|run) ;; *) echo "usage: sh g3.sh plan|run runtime-service|storage"; exit 2 ;; esac
case "$PUB" in
  runtime-service) ART=runtime_service_snapshot.json; KIND=runtime ;;
  storage) ART=storage_snapshot.json; KIND=storage ;;
  *) echo "usage: sh g3.sh plan|run runtime-service|storage (one publisher per run)"; exit 2 ;;
esac
SERVICE="crypto-publish-$PUB.service"; TIMER="crypto-publish-$PUB.timer"
UNITDIR=/etc/systemd/system
OUTDIR=/home/mathieu/operator_presentation
OWNER=mathieu
SHA=1728b3ad952b87d903ccb7442579000da292b848
SRC=/opt/crypto-ai-terminal/operator/staging-src/$SHA
PYBIN=/opt/crypto-ai-terminal/operator/staging-envs/$SHA/bin/python
HEALTH=http://127.0.0.1:8090/healthz
RUNS=3; GAP=5
if [ "${G3_TEST:-0}" = 1 ]; then
  UNITDIR="${G3_UNITDIR:-$UNITDIR}"; OUTDIR="${G3_OUTDIR:-$OUTDIR}"; OWNER="${G3_OWNER:-$OWNER}"
  SRC="${G3_SRC:-$SRC}"; PYBIN="${G3_PYBIN:-$PYBIN}"; HEALTH="${G3_HEALTH:-$HEALTH}"
  RUNS="${G3_RUNS:-$RUNS}"; GAP="${G3_GAP:-$GAP}"
fi
GUARDED="crypto-advisor.service crypto-operator-api.service crypto-operator-web.service"
OURS="@@UNITS@@"
export LC_ALL=C
umask 077

expected() { case "$1" in
@@EXPECT@@
*) echo "" ;; esac; }

FAILS=0; FAILMSG=""; W=""
fail() { FAILS=$((FAILS + 1)); FAILMSG="${FAILMSG}  - $1
"; echo "!! $1"; }
cleanup() { [ -n "$W" ] && rm -rf "$W"; return 0; }
interrupted() {
  cleanup
  echo "!! INTERRUPTED ($1). A oneshot that was already started ends by itself (TimeoutStartSec=20s)."
  echo "!! Nothing is undone automatically. Check: systemctl show $SERVICE -p ActiveState -p Result"
  exit "$2"
}
trap 'cleanup' EXIT
trap 'interrupted INT 130' INT
trap 'interrupted TERM 143' TERM
trap 'interrupted HUP 129' HUP
sha() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }
val() { systemctl show -p "$2" --value -- "$1" 2>/dev/null; }
snap() { for u in $GUARDED; do
  echo "$u $(systemctl show -p ActiveState -p SubState -p MainPID -p NRestarts -p InvocationID -p ActiveEnterTimestamp -p DropInPaths -- "$u" 2>&1 | tr '\n' ' ')"
done; }
health() { curl -s -m 5 -o /dev/null -w '%{http_code}' "$HEALTH" 2>/dev/null || echo "000"; }
protected() {
  [ -e "$1" ] && [ ! -L "$1" ] || return 1
  set -- "$1" "$(stat -c '%u %a' "$1")"
  [ "${2%% *}" = 0 ] || return 1
  perm="${2#* }"; other="${perm#"${perm%?}"}"; rest="${perm%?}"; group="${rest#"${rest%?}"}"
  case "$group$other" in *[2367]*) return 1 ;; esac
  return 0
}
# run the artifact contract of the DEPLOYED release as the output owner, empty environment
CHECK_PY='
import json, os, sys
from datetime import datetime, timezone
try:
    kind, path, t0, t1 = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
    doc = json.load(open(path))
    if kind == "runtime":
        from observability.runtime_service_contract import validate_runtime_service_snapshot as ok
    else:
        from observability.storage_contract import validate_storage_snapshot as ok
    valid = ok(doc) is True
    def epoch(key):
        return datetime.fromisoformat(doc[key].replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
    stamps = {k: epoch(k) for k in ("generated_at_utc", "observed_at_utc")}
    mtime = os.stat(path).st_mtime
    lo, hi = t0 - 0.5, t1 + 0.5
    fresh = all(lo <= v <= hi for v in stamps.values()) and lo <= mtime <= hi
    print("contract-valid=%s fresh-from-this-launch=%s generated_at_utc=%s observed_at_utc=%s" % (
        valid, fresh, doc["generated_at_utc"], doc["observed_at_utc"]))
    sys.exit(0 if (valid and fresh) else 1)
except SystemExit:
    raise
except BaseException as exc:
    print("contract-check-error: %s: %s" % (type(exc).__name__, exc))
    sys.exit(2)
'
contract() {
  ( cd "$SRC" && timeout 20 runuser -u "$OWNER" -- env -i PATH=/usr/bin:/bin PYTHONPATH="$SRC" PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 "$PYBIN" -c "$CHECK_PY" "$KIND" "$1" "$2" "$3" ) 2>&1
}
# the other publisher's artifact (e.g. the runtime-service file during the storage series) is
# ALLOWED in the output directory but must stay byte-for-byte what it was before this series
case "$PUB" in runtime-service) OTHER=storage_snapshot.json ;; *) OTHER=runtime_service_snapshot.json ;; esac
other_state() {
  if [ -e "$OUTDIR/$OTHER" ] || [ -L "$OUTDIR/$OTHER" ]; then
    echo "present $(stat -c '%i:%s:%y' "$OUTDIR/$OTHER" 2>&1) sha256=$(sha "$OUTDIR/$OTHER")"
  else echo "absent"; fi
}

echo "== G3 mode=$MODE publisher=$PUB $(date -u +%Y-%m-%dT%H:%M:%SZ) user=$(id -un) uid=$(id -u)"
echo "== service=$SERVICE timer=$TIMER (timer is never touched) artifact=$OUTDIR/$ART runs=$RUNS gap>=${GAP}s"
if [ "$MODE" = run ]; then
  [ "$(id -u)" -eq 0 ] || { echo "!! run must be root; nothing was done"; exit 3; }
  if ! protected "$0" || ! protected "$(dirname "$0")"; then
    echo "!! run refuses: $0 and its directory must be root-owned and not group/other-writable (use the paste block); nothing was done"
    exit 3
  fi
  echo "== running from a protected copy: $0 sha256=$(sha "$0")"
fi
W=$(mktemp -d "${TMPDIR:-/tmp}/g3.XXXXXX") || exit 1

echo "== preconditions (read-only)"
for u in $GUARDED $OURS; do
  n=$(val "$u" NeedDaemonReload); echo "   $u NeedDaemonReload=${n:-?}"
  [ "$n" = no ] || fail "$u NeedDaemonReload=${n:-unknown}"
done
for u in $OURS; do
  t="$UNITDIR/$u"; h=$(sha "$t"); e=$(expected "$u"); m=$(stat -c '%U:%G %a' "$t" 2>/dev/null)
  echo "   $u sha256=${h:-absent} ${m:-}"
  [ -n "$h" ] && [ "$h" = "$e" ] || fail "$t hash ${h:-absent} differs from the reviewed hash $e"
  [ "$m" = "root:root 644" ] || fail "$t is '${m:-absent}' (expected root:root 644)"
  as=$(val "$u" ActiveState); uf=$(val "$u" UnitFileState)
  echo "   $u ActiveState=$as UnitFileState=$uf"
  [ "$as" = inactive ] || fail "$u ActiveState=$as (must be inactive)"
  case "$u" in
    *.timer) [ "$uf" = disabled ] || fail "$u UnitFileState=$uf (must be disabled)" ;;
    *.service) case "$uf" in static|disabled) ;; *) fail "$u UnitFileState=$uf (static or disabled expected)" ;; esac ;;
  esac
  for pr in WantedBy RequiredBy BoundBy UpheldBy; do
    v=$(val "$u" $pr); [ -z "$v" ] || fail "$u $pr=$v (nothing may pull this unit in)"
  done
done
links=$(find "$UNITDIR" -maxdepth 2 -name 'crypto-publish-*' -type l 2>/dev/null)
[ -z "$links" ] || fail "enable symlinks exist: $links"
if [ -d "$OUTDIR" ]; then
  own=$(stat -c '%U %a' "$OUTDIR"); echo "   $OUTDIR: $own"
  [ "$own" = "$OWNER 700" ] || fail "$OUTDIR is '$own' (need '$OWNER 700')"
else fail "$OUTDIR does not exist (G2 creates it)"; fi
echo "   output directory now: $(ls -A "$OUTDIR" 2>/dev/null | tr '\n' ' ')(artifact present: $([ -e "$OUTDIR/$ART" ] && echo yes || echo no))"
echo "   other publisher's artifact ($OTHER): $(other_state) (allowed; must stay unchanged during the series)"
[ -d "$SRC" ] && [ -x "$PYBIN" ] || fail "deployed release code or interpreter missing ($SRC, $PYBIN)"
ex=$(val "$SERVICE" ExecMainStartTimestampMonotonic)
echo "   $SERVICE ExecMainStartTimestampMonotonic=${ex:-?} (0 = never run since boot/reload)"
( cd "$SRC" && env -i PATH=/usr/bin:/bin PYTHONPATH="$SRC" PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -c "import observability.runtime_service_contract, observability.storage_contract" ) >/dev/null 2>&1 \
  || fail "the contract validators of the deployed release cannot be imported"
df -Pk "$OUTDIR" 2>/dev/null | awk 'NR==2 && $4 < 10240 {exit 1}' || fail "less than 10 MiB free for $OUTDIR"
BEFORE=$(snap); OTHER0=$(other_state); H0=$(health); echo "   healthz before: $H0"
[ "$H0" = 200 ] || fail "healthz before is $H0 (expected 200)"

if [ "$MODE" = plan ]; then
  [ "$FAILS" -eq 0 ] && echo "== nothing was started or written (plan)"
  echo "== summary"
  if [ "$FAILS" -eq 0 ]; then echo "RESULT: OK (preconditions hold)"; exit 0; fi
  echo "RESULT: FAILED ($FAILS finding(s))"; printf '%s' "$FAILMSG"; exit 1
fi
if [ "$FAILS" -ne 0 ]; then
  echo "== summary"; echo "RESULT: FAILED ($FAILS finding(s)): nothing was started"; printf '%s' "$FAILMSG"; exit 1
fi

echo "== run: $RUNS trials of $SERVICE (one at a time; first failure stops the series)"
I=0; DONE=0
while [ "$I" -lt "$RUNS" ] && [ "$FAILS" -eq 0 ]; do
  I=$((I + 1))
  [ "$I" -gt 1 ] && sleep "$GAP"
  M0=$(stat -c '%i:%Y.%y' "$OUTDIR/$ART" 2>/dev/null || echo none)
  echo "-- trial $I/$RUNS: systemctl start $SERVICE"
  T0=$(date +%s.%N)
  timeout 60 systemctl start "$SERVICE"; RC=$?
  T1=$(date +%s.%N)
  echo "   start exit status: $RC"
  [ "$RC" -eq 0 ] || fail "trial $I: systemctl start exit status $RC"
  R=$(val "$SERVICE" Result); S=$(val "$SERVICE" ExecMainStatus); C=$(val "$SERVICE" ExecMainCode)
  A=$(val "$SERVICE" ActiveState)
  MS0=$(val "$SERVICE" ExecMainStartTimestampMonotonic); MS1=$(val "$SERVICE" ExecMainExitTimestampMonotonic)
  MP=$(val "$SERVICE" MemoryPeak); CPU=$(val "$SERVICE" CPUUsageNSec)
  D=NOT_AVAILABLE
  case "$MS0$MS1" in *[!0-9]*|"") ;; *) [ "$MS1" -ge "$MS0" ] && D=$(( (MS1 - MS0) / 1000 ))ms ;; esac
  case "$MP" in ""|"[not set]"|infinity|18446744073709551615) MP=NOT_AVAILABLE ;; esac
  case "$CPU" in ""|"[not set]"|18446744073709551615) CPU=NOT_AVAILABLE ;; esac
  echo "   Result=$R ExecMainStatus=$S ExecMainCode=$C ActiveState=$A duration=$D MemoryPeak=$MP CPUUsageNSec=$CPU"
  [ "$R" = success ] || fail "trial $I: Result=$R"
  [ "$S" = 0 ] || fail "trial $I: ExecMainStatus=$S"
  [ "$A" = inactive ] || fail "trial $I: ActiveState=$A after the run"
  f="$OUTDIR/$ART"
  if [ -L "$f" ] || [ ! -f "$f" ]; then fail "trial $I: artifact $f missing or not a regular file"
  else
    am=$(stat -c '%U %a %s' "$f"); echo "   artifact: $am"
    sz=${am##* }; own=${am% *}
    [ "$own" = "$OWNER 600" ] || fail "trial $I: artifact owner/mode '$own' (expected '$OWNER 600')"
    [ "$sz" -gt 0 ] && [ "$sz" -le 1048576 ] || fail "trial $I: artifact size $sz out of bounds (1..1048576)"
    [ "$(stat -c '%i:%Y.%y' "$f")" != "$M0" ] || fail "trial $I: artifact was not refreshed by this trial"
    out=$(contract "$f" "$T0" "$T1"); CRC=$?; echo "   $out"
    [ "$CRC" -eq 0 ] || fail "trial $I: contract/freshness check exit status $CRC (1 = invalid or not from this launch, 2 = error)"
  fi
  extras=$(ls -A "$OUTDIR" | grep -v -x -e runtime_service_snapshot.json -e storage_snapshot.json)
  [ -z "$extras" ] || fail "trial $I: unexpected files in $OUTDIR: $(echo $extras)"
  for t in $OURS; do
    case "$t" in *.timer)
      a=$(val "$t" ActiveState); u=$(val "$t" UnitFileState)
      [ "$a" = inactive ] && [ "$u" = disabled ] || fail "trial $I: $t is $a/$u (must stay inactive/disabled)" ;;
    esac
  done
  [ "$(other_state)" = "$OTHER0" ] || fail "trial $I: $OTHER changed during this series (before: $OTHER0 / now: $(other_state))"
  AFTER=$(snap)
  [ "$BEFORE" = "$AFTER" ] || { fail "trial $I: Advisor/API/web CHANGED"; echo "--- before"; echo "$BEFORE"; echo "--- after"; echo "$AFTER"; }
  H1=$(health); echo "   healthz after: $H1"
  [ "$H1" = 200 ] || fail "trial $I: healthz after is $H1"
  [ "$FAILS" -eq 0 ] && DONE=$((DONE + 1))
done
if command -v journalctl >/dev/null 2>&1; then
  echo "== journal of $SERVICE (last lines, read-only)"
  journalctl -u "$SERVICE" -n 12 --no-pager -o short-iso 2>&1 | tail -n 14
fi
echo "== guarded units before and after"
echo "$BEFORE"
[ "$BEFORE" = "$(snap)" ] && echo "UNCHANGED (state, PID, NRestarts, InvocationID, start time, drop-ins)" || fail "guarded units CHANGED at the end"
echo "== summary"
echo "trials passed: $DONE/$RUNS"
if [ "$FAILS" -eq 0 ]; then echo "RESULT: OK (all checks passed)"; exit 0; fi
echo "RESULT: FAILED ($FAILS finding(s)); the series stopped at the first failure"
printf '%s' "$FAILMSG"
echo "== nothing was repaired or retried; the artifact, if any, is left as written"
exit 1
