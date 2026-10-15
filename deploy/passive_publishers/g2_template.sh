# G2 — INACTIVE installation of the reviewed passive-publisher units.
# Modes:  plan | verify  : read-only, any user, nothing written outside a private temp dir.
#         apply | rollback : must run as root (the OPERATOR runs it with sudo; no agent does).
# What `apply` writes, and ALL it writes (each one recorded in $STATE/manifest):
#   1. $STATE (0700 root)                  state, manifest and backups of pre-existing files
#   2. $OUTDIR (0700 $OWNER), if absent    the presentation directory (never chmod'ed if present)
#   3. $UNITDIR/crypto-publish-*.{service,timer}   mode 0644 root, the reviewed files only
#   4. `systemctl daemon-reload`           the ONLY interaction with the service manager
# What it never does: enable, start, stop, restart, link, mask, edit a drop-in, touch the
# Advisor / API / web units, read an EnvironmentFile or .env, or open any data source.
# A unit file alone starts nothing: the services have no [Install]; the timers' [Install]
# (WantedBy=timers.target) only acts on `systemctl enable`, which this script never calls.
# `apply` refuses when any guarded unit has NeedDaemonReload=yes, so the reload cannot apply
# somebody else's pending change. Rollback removes only files created by `apply` whose
# sha256 still matches the manifest, restores the backups of replaced files, and leaves
# anything that diverged in place (reported).
# Exit status: 0 all checks passed; 1 a check failed; 2 usage; 3 not root; 129/130/143 signals.
MODE="${1:-plan}"
case "$MODE" in plan|verify|apply|rollback) ;; *) echo "usage: sh g2.sh plan|verify|apply|rollback"; exit 2 ;; esac
UNITDIR=/etc/systemd/system
STATE=/var/lib/crypto-publishers-g2
OUTDIR=/home/mathieu/operator_presentation
OWNER=mathieu
if [ "${G2_TEST:-0}" = 1 ]; then
  UNITDIR="${G2_UNITDIR:-$UNITDIR}"; STATE="${G2_STATE:-$STATE}"
  OUTDIR="${G2_OUTDIR:-$OUTDIR}"; OWNER="${G2_OWNER:-$OWNER}"
fi
PUBS="@@PUBS@@"
GUARDED="crypto-advisor.service crypto-operator-api.service crypto-operator-web.service"
export LC_ALL=C
umask 077

expected() { case "$1" in
@@EXPECT@@
*) echo "" ;; esac; }
UNITLIST=""
for p in $PUBS; do UNITLIST="$UNITLIST crypto-publish-$p.service crypto-publish-$p.timer"; done

FAILS=0; FAILMSG=""; W=""
fail() { FAILS=$((FAILS + 1)); FAILMSG="${FAILMSG}  - $1
"; echo "!! $1"; }
cleanup() { [ -n "$W" ] && rm -rf "$W"; return 0; }
trap 'cleanup' EXIT
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM
trap 'cleanup; exit 129' HUP
sha() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }
val() { systemctl show -p "$2" --value -- "$1" 2>/dev/null; }
snap() { for u in $GUARDED; do
  echo "$u $(systemctl show -p ActiveState -p SubState -p MainPID -p NRestarts -p InvocationID -p ActiveEnterTimestamp -p DropInPaths -- "$u" 2>&1 | tr '\n' ' ')"
done; }

echo "== G2 mode=$MODE $(date -u +%Y-%m-%dT%H:%M:%SZ) user=$(id -un) uid=$(id -u)"
echo "== paths: units=$UNITDIR state=$STATE output=$OUTDIR owner=$OWNER"
echo "== units in this package:$UNITLIST"
if [ "$MODE" = apply ] || [ "$MODE" = rollback ]; then
  [ "$(id -u)" -eq 0 ] || { echo "!! $MODE must run as root; nothing was done"; exit 3; }
fi
W=$(mktemp -d "${TMPDIR:-/tmp}/g2.XXXXXX") || exit 1
mkdir "$W/units"
@@UNITS@@
BEFORE=$(snap)

# ---- checks shared by plan and apply (read-only) ----------------------------
staged_ok() {
  for u in $UNITLIST; do
    h=$(sha "$W/units/$u"); e=$(expected "$u")
    echo "   $u sha256=$h"
    [ -n "$e" ] && [ "$h" = "$e" ] || fail "staged $u hash $h differs from the reviewed hash $e"
  done
  timeout 30 sh -c 'cd "$1" && exec systemd-analyze verify ./crypto-publish-*.service ./crypto-publish-*.timer' sh "$W/units" > "$W/verify.log" 2>&1
  RC=$?; cat "$W/verify.log"
  echo "   verify exit status: $RC (messages above, if any, are findings)"
  [ "$RC" -eq 0 ] || fail "systemd-analyze verify exit status $RC"
}
preflight() {
  echo "== preflight (read-only)"
  for u in $GUARDED; do
    n=$(val "$u" NeedDaemonReload)
    echo "   $u NeedDaemonReload=${n:-?}"
    [ "$n" = no ] || fail "$u NeedDaemonReload=${n:-unknown}: a daemon-reload would apply a pending unit change that is not ours"
  done
  for u in $UNITLIST; do
    t="$UNITDIR/$u"
    if [ ! -e "$t" ]; then echo "   $t: absent (will be created)"
    elif [ "$(sha "$t")" = "$(expected "$u")" ]; then echo "   $t: identical (will be left as is)"
    else echo "   $t: DIFFERENT (will be backed up to $STATE/backup, then replaced)"; fi
    s=$(val "$u" ActiveState); f=$(val "$u" UnitFileState)
    case "$f" in enabled*|linked*|alias) fail "$u is already $f: not a G2 situation" ;; esac
    case "$s" in ""|inactive|failed) ;; *) fail "$u is $s: not a G2 situation" ;; esac
  done
  if [ -d "$OUTDIR" ]; then
    own=$(stat -c '%U %a' "$OUTDIR")
    echo "   $OUTDIR exists: $own"
    [ "$own" = "$OWNER 700" ] || fail "$OUTDIR exists as '$own' (need '$OWNER 700'); it will not be changed"
  else
    echo "   $OUTDIR: absent (will be created 0700 $OWNER)"
    [ -d "$(dirname "$OUTDIR")" ] || fail "parent of $OUTDIR does not exist"
  fi
  id "$OWNER" >/dev/null 2>&1 || fail "user $OWNER does not exist"
  df -Pk "$UNITDIR" 2>/dev/null | awk 'NR==2 && $4 < 10240 {exit 1}' || fail "less than 10 MiB free on $UNITDIR"
  staged_ok
}

# ---- post-install checks (apply, verify) -----------------------------------
installed_ok() {
  echo "== installed units: hashes, configuration, state (nothing may be enabled or active)"
  for u in $UNITLIST; do
    t="$UNITDIR/$u"
    [ -f "$t" ] || { fail "$t missing"; continue; }
    h=$(sha "$t"); e=$(expected "$u"); m=$(stat -c '%U:%G %a' "$t")
    echo "   $u sha256=$h $m"
    [ "$h" = "$e" ] || fail "$t hash $h differs from the reviewed hash $e"
    [ "$m" = "root:root 644" ] || fail "$t is '$m' (expected root:root 644)"
    ld=$(val "$u" LoadState); as=$(val "$u" ActiveState); uf=$(val "$u" UnitFileState)
    ex=$(val "$u" ExecMainStartTimestampMonotonic)
    echo "   $u LoadState=$ld ActiveState=$as UnitFileState=$uf"
    [ "$ld" = loaded ] || fail "$u LoadState=$ld"
    [ "$as" = inactive ] || fail "$u ActiveState=$as (must be inactive)"
    case "$u" in
      *.timer) [ "$uf" = disabled ] || fail "$u UnitFileState=$uf (must be disabled)" ;;
      *.service) case "$uf" in static|disabled) ;; *) fail "$u UnitFileState=$uf (static or disabled expected)" ;; esac
                 [ -z "$ex" ] || [ "$ex" = 0 ] || fail "$u has run (ExecMainStartTimestampMonotonic=$ex)" ;;
    esac
    for pr in WantedBy RequiredBy BoundBy UpheldBy; do
      v=$(val "$u" $pr); [ -z "$v" ] || fail "$u $pr=$v (nothing may pull this unit in)"
    done
  done
  links=$(find "$UNITDIR" -maxdepth 2 -name 'crypto-publish-*' -type l 2>/dev/null)
  [ -z "$links" ] || fail "enable symlinks exist: $links"
  timeout 30 sh -c 'cd "$1" && shift && exec systemd-analyze verify "$@"' sh "$UNITDIR" $UNITLIST > "$W/verify2.log" 2>&1
  RC=$?; cat "$W/verify2.log"
  echo "   installed verify exit status: $RC"
  [ "$RC" -eq 0 ] || fail "systemd-analyze verify on installed units exit status $RC"
}
guards_unchanged() {
  AFTER=$(snap)
  echo "== Advisor / API / web before and after"
  echo "$BEFORE"
  if [ "$BEFORE" = "$AFTER" ]; then echo "UNCHANGED (state, PID, NRestarts, InvocationID, start time, drop-ins)"
  else fail "guarded units CHANGED"; echo "--- after"; echo "$AFTER"; fi
}
report() {
  echo "== summary"
  if [ "$FAILS" -eq 0 ]; then echo "RESULT: OK (all checks passed)"
  else echo "RESULT: FAILED ($FAILS finding(s))"; printf '%s' "$FAILMSG"; fi
}

case "$MODE" in
plan)
  preflight; echo "== nothing was written (plan)"; report ;;
verify)
  installed_ok; echo "== nothing was written (verify)"; report ;;
apply)
  preflight
  [ -e "$STATE/manifest" ] && fail "$STATE/manifest exists: already applied (run verify, or rollback first)"
  if [ "$FAILS" -ne 0 ]; then echo "== preflight FAILED: nothing was written"; report; exit 1; fi
  echo "== apply: writing"
  mkdir -m 0700 "$STATE" && mkdir -m 0700 "$STATE/backup" || { echo "!! cannot create $STATE: nothing else was written"; exit 1; }
  M="$STATE/manifest"
  echo "V1|$(date -u +%Y-%m-%dT%H:%M:%SZ)|$PUBS" > "$M"
  if [ -d "$OUTDIR" ]; then echo "OUTDIR|$OUTDIR|-|existing" >> "$M"
  else
    install -d -m 0700 -o "$OWNER" -g "$OWNER" "$OUTDIR" && echo "OUTDIR|$OUTDIR|-|created" >> "$M" && echo "   created $OUTDIR"
  fi
  for u in $UNITLIST; do
    t="$UNITDIR/$u"; e=$(expected "$u")
    if [ -e "$t" ] && [ "$(sha "$t")" = "$e" ]; then echo "   $t identical: untouched"; continue; fi
    if [ -e "$t" ]; then
      b="$STATE/backup/$u"; cp -p "$t" "$b" || { fail "backup of $t failed: stopping"; break; }
      install -m 0644 -o root -g root "$W/units/$u" "$t" && echo "FILE|$t|$e|replaced|$b|$(sha "$b")" >> "$M" && echo "   replaced $t (backup $b)"
    else
      install -m 0644 -o root -g root "$W/units/$u" "$t" && echo "FILE|$t|$e|created" >> "$M" && echo "   created $t"
    fi
  done
  if [ "$FAILS" -eq 0 ]; then
    systemctl daemon-reload; RC=$?; echo "   daemon-reload exit status: $RC"
    [ "$RC" -eq 0 ] || fail "daemon-reload exit status $RC"
    installed_ok
    guards_unchanged
  fi
  report
  if [ "$FAILS" -ne 0 ]; then echo "== to undo: re-run this block with G2_MODE=rollback (manifest: $STATE/manifest)"; exit 1; fi ;;
rollback)
  M="$STATE/manifest"
  [ -f "$M" ] || { echo "!! no manifest at $M: nothing to roll back"; exit 1; }
  for u in $UNITLIST; do
    s=$(val "$u" ActiveState); f=$(val "$u" UnitFileState)
    case "$f" in enabled*|linked*|alias) fail "$u is $f: undo the later gate (timers) first" ;; esac
    case "$s" in ""|inactive|failed) ;; *) fail "$u is $s: undo the later gate first" ;; esac
  done
  if [ "$FAILS" -ne 0 ]; then echo "== rollback REFUSED: nothing was changed"; report; exit 1; fi
  echo "== manifest being rolled back"; cat "$M"
  DIVERGED=0
  awk '{a[NR]=$0} END{for(i=NR;i>0;i--)print a[i]}' "$M" > "$W/rev"
  while IFS='|' read -r kind path hash how backup bhash; do
    case "$kind" in
    FILE)
      cur=$(sha "$path")
      if [ ! -e "$path" ]; then echo "   $path already absent"
      elif [ "$cur" != "$hash" ]; then echo "   DIVERGED: $path (sha256 $cur != recorded $hash): left in place"; DIVERGED=1
      elif [ "$how" = created ]; then rm -f "$path" && echo "   removed $path"
      else
        if [ "$(sha "$backup")" = "$bhash" ]; then install -m 0644 -o root -g root "$backup" "$path" && echo "   restored $path from $backup"
        else echo "   DIVERGED: backup $backup altered: $path left in place"; DIVERGED=1; fi
      fi ;;
    OUTDIR)
      if [ "$how" = created ]; then
        rmdir "$path" 2>/dev/null && echo "   removed empty $path" || { [ -d "$path" ] && echo "   $path not empty or busy: left in place (artifacts are regenerable; remove by hand if wanted)"; }
      else echo "   $path pre-existing: untouched"; fi ;;
    esac
  done < "$W/rev"
  systemctl daemon-reload; RC=$?; echo "   daemon-reload exit status: $RC"
  [ "$RC" -eq 0 ] || fail "daemon-reload exit status $RC"
  for u in $UNITLIST; do
    l=$(val "$u" LoadState); echo "   $u LoadState=${l:-?}"
  done
  guards_unchanged
  if [ "$DIVERGED" -eq 0 ] && [ "$FAILS" -eq 0 ]; then rm -rf "$STATE" && echo "   removed $STATE"
  else echo "   $STATE KEPT (diverged files or findings): manifest and backups preserved"; [ "$DIVERGED" -eq 0 ] || fail "diverged files left in place"; fi
  report ;;
esac
[ "$FAILS" -eq 0 ] && exit 0
exit 1
