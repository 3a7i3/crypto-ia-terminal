# G2 — INACTIVE installation of the reviewed passive-publisher units.
# Modes:  plan | verify  : read-only, any user, nothing written outside a private temp dir.
#         apply | rollback : must run as root, from a PROTECTED copy of this script (root-owned,
#                            not group/other-writable, in a directory that is not either). The
#                            paste block (g2_paste_block.sh) creates that copy itself and re-hashes
#                            it as root before running it. The OPERATOR launches it; no agent does.
# What `apply` writes, and ALL it writes (each step is recorded BEFORE it is done, in the
# write-ahead manifest $STATE/manifest, so an interruption always leaves a recoverable state):
#   1. $STATE (0700 root)                  manifest and backups of pre-existing files
#   2. $OUTDIR (0700 $OWNER), if absent    the presentation directory (never chmod'ed if present)
#   3. $UNITDIR/crypto-publish-*.{service,timer}   0644 root, written to a hidden temp name in the
#                                          same directory, hash-checked, then renamed (atomic)
#   4. `systemctl daemon-reload`           the ONLY interaction with the service manager
# What it never does: enable, start, stop, restart, link, mask, edit a drop-in, touch the
# Advisor / API / web units, read an EnvironmentFile or .env, or open any data source.
# A unit file alone starts nothing: the services have no [Install]; the timers' [Install]
# (WantedBy=timers.target) only acts on `systemctl enable`, which this script never calls.
# `apply` refuses when any guarded unit has NeedDaemonReload=yes, so the reload cannot apply
# somebody else's pending change.
# Failure accounting: EVERY write, copy, rename, removal, restore and reload is checked and
# counted. `rollback` prints RESULT: OK only if every restoration was done AND verified (hash
# of each restored file, absence of each removed one); otherwise RESULT: FAILED with the list
# of what could not be undone, and the manifest and backups are kept. Files that diverged since
# G2 (modified by someone else) are never overwritten and count as a failure of the rollback.
# Exit status: 0 all checks passed; 1 a check failed; 2 usage; 3 not root / not protected;
# 129/130/143 signals (partial state is kept and the recovery command is printed).
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

FAILS=0; FAILMSG=""; W=""; WRITING=0; M="$STATE/manifest"
fail() { FAILS=$((FAILS + 1)); FAILMSG="${FAILMSG}  - $1
"; echo "!! $1"; }
cleanup() { [ -n "$W" ] && rm -rf "$W"; return 0; }
interrupted() {
  cleanup
  if [ "$WRITING" -eq 1 ]; then
    echo "!! INTERRUPTED ($1) while writing: the state is KEPT and is recoverable."
    echo "!! Recovery: run this block again with G2_MODE=rollback (manifest: $M)."
  fi
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
# write-ahead record: appended and fsync'ed BEFORE the action it announces
wal() { printf '%s\n' "$1" >> "$M" || return 1; sync "$M" 2>/dev/null || sync; return 0; }
# a file is "protected" if it is a regular, non-symlink file owned by root without group/other write
protected() {
  [ -e "$1" ] && [ ! -L "$1" ] || return 1
  set -- "$1" "$(stat -c '%u %a' "$1")"
  [ "${2%% *}" = 0 ] || return 1
  perm="${2#* }"; other="${perm#"${perm%?}"}"; rest="${perm%?}"; group="${rest#"${rest%?}"}"
  case "$group$other" in *[2367]*) return 1 ;; esac
  return 0
}

echo "== G2 mode=$MODE $(date -u +%Y-%m-%dT%H:%M:%SZ) user=$(id -un) uid=$(id -u)"
echo "== paths: units=$UNITDIR state=$STATE output=$OUTDIR owner=$OWNER"
echo "== units in this package:$UNITLIST"
if [ "$MODE" = apply ] || [ "$MODE" = rollback ]; then
  [ "$(id -u)" -eq 0 ] || { echo "!! $MODE must run as root; nothing was done"; exit 3; }
  if ! protected "$0" || ! protected "$(dirname "$0")"; then
    echo "!! $MODE refuses to run: $0 and its directory must be root-owned and not group/other-writable (use the paste block, which makes a protected copy); nothing was done"
    exit 3
  fi
  echo "== running from a protected copy: $0 sha256=$(sha "$0")"
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

# ---- apply helpers: every step checked, counted, and verified ---------------
# place SRC (staged, hash-checked) at TARGET atomically: hidden temp name, verify, rename, verify
place() {
  src="$1"; target="$2"; want="$3"; tmp="$(dirname "$target")/.$(basename "$target").g2tmp"
  rm -f "$tmp" || { fail "cannot clear stale temp $tmp"; return 1; }
  install -m 0644 -o root -g root "$src" "$tmp" || { fail "install of $tmp failed"; rm -f "$tmp"; return 1; }
  [ "$(sha "$tmp")" = "$want" ] || { fail "copy $tmp has hash $(sha "$tmp"), expected $want"; rm -f "$tmp" || fail "cannot remove $tmp"; return 1; }
  mv -f "$tmp" "$target" || { fail "rename $tmp -> $target failed"; rm -f "$tmp" || fail "cannot remove $tmp"; return 1; }
  [ "$(sha "$target")" = "$want" ] || { fail "$target has hash $(sha "$target") after rename, expected $want"; return 1; }
  return 0
}

case "$MODE" in
plan)
  preflight; echo "== nothing was written (plan)"; report ;;
verify)
  installed_ok; echo "== nothing was written (verify)"; report ;;
apply)
  preflight
  [ -e "$M" ] && fail "$M exists: already applied (run verify, or rollback first)"
  if [ "$FAILS" -ne 0 ]; then echo "== preflight FAILED: nothing was written"; report; exit 1; fi
  echo "== apply: writing (write-ahead: each step is recorded and synced before it is done)"
  WRITING=1
  mkdir -m 0700 "$STATE" || { echo "!! cannot create $STATE: nothing else was written"; exit 1; }
  if ! mkdir -m 0700 "$STATE/backup"; then
    rmdir "$STATE" || echo "!! could not remove the empty $STATE: remove it by hand"
    echo "!! cannot create $STATE/backup: nothing else was written"; exit 1
  fi
  wal "V1|$(date -u +%Y-%m-%dT%H:%M:%SZ)|$PUBS" || { fail "cannot write the manifest $M: stopping"; }
  if [ "$FAILS" -eq 0 ]; then
    if [ -d "$OUTDIR" ]; then wal "OUTDIR|$OUTDIR|-|existing" || fail "manifest write failed"
    else
      wal "OUTDIR|$OUTDIR|-|intent-created" || fail "manifest write failed (before creating $OUTDIR)"
      if [ "$FAILS" -eq 0 ]; then
        if install -d -m 0700 -o "$OWNER" -g "$OWNER" "$OUTDIR"; then
          wal "OUTDIR|$OUTDIR|-|created" || fail "manifest write failed (after creating $OUTDIR)"
          echo "   created $OUTDIR"
        else fail "creation of $OUTDIR failed"; fi
      fi
    fi
  fi
  for u in $UNITLIST; do
    [ "$FAILS" -eq 0 ] || break
    t="$UNITDIR/$u"; e=$(expected "$u")
    if [ -e "$t" ] && [ "$(sha "$t")" = "$e" ]; then echo "   $t identical: untouched"; continue; fi
    if [ -e "$t" ]; then
      b="$STATE/backup/$u"; orig=$(sha "$t")
      cp -p "$t" "$b" || { fail "backup of $t failed: stopping"; break; }
      [ "$(sha "$b")" = "$orig" ] || { fail "backup $b does not match $t: stopping"; break; }
      wal "FILE|$t|$e|intent-replaced|$b|$orig" || { fail "manifest write failed (before replacing $t)"; break; }
      place "$W/units/$u" "$t" "$e" || break
      wal "FILE|$t|$e|replaced|$b|$orig" || { fail "manifest write failed (after replacing $t)"; break; }
      echo "   replaced $t (backup $b)"
    else
      wal "FILE|$t|$e|intent-created" || { fail "manifest write failed (before creating $t)"; break; }
      place "$W/units/$u" "$t" "$e" || break
      wal "FILE|$t|$e|created" || { fail "manifest write failed (after creating $t)"; break; }
      echo "   created $t"
    fi
  done
  if [ "$FAILS" -eq 0 ]; then
    systemctl daemon-reload; RC=$?; echo "   daemon-reload exit status: $RC"
    [ "$RC" -eq 0 ] || fail "daemon-reload exit status $RC"
    installed_ok
    guards_unchanged
  fi
  WRITING=0
  report
  if [ "$FAILS" -ne 0 ]; then
    echo "== apply FAILED: the partial state is KEPT and recorded in $M"
    echo "== to undo: re-run this block with G2_MODE=rollback"; exit 1
  fi ;;
rollback)
  [ -f "$M" ] || { echo "!! no manifest at $M: nothing to roll back"; exit 1; }
  for u in $UNITLIST; do
    s=$(val "$u" ActiveState); f=$(val "$u" UnitFileState)
    case "$f" in enabled*|linked*|alias) fail "$u is $f: undo the later gate (timers) first" ;; esac
    case "$s" in ""|inactive|failed) ;; *) fail "$u is $s: undo the later gate first" ;; esac
  done
  if [ "$FAILS" -ne 0 ]; then echo "== rollback REFUSED: nothing was changed"; report; exit 1; fi
  WRITING=1
  echo "== manifest being rolled back"; cat "$M"
  # last record per (kind,path), in reverse order of first appearance (units before the directory)
  awk -F'|' '$1=="FILE"||$1=="OUTDIR"{k=$1"|"$2; if(!(k in s)){o[++n]=k; s[k]=1} l[k]=$0} END{for(i=n;i>0;i--)print l[o[i]]}' "$M" > "$W/plan"
  LEFT=""; REMOVED=""
  while IFS='|' read -r kind path hash how backup bhash; do
    case "$kind" in
    FILE)
      tmp="$(dirname "$path")/.$(basename "$path").g2tmp"
      if [ -e "$tmp" ]; then rm -f "$tmp" && echo "   removed leftover temp $tmp" || fail "cannot remove leftover temp $tmp"; fi
      cur=$(sha "$path")
      case "$how" in
      created|intent-created)
        if [ ! -e "$path" ]; then echo "   $path already absent"; REMOVED="$REMOVED $(basename "$path")"
        elif [ "$cur" != "$hash" ]; then fail "DIVERGED: $path has sha256 $cur, not the installed $hash: left in place, NOT undone"
        else
          rm -f "$path" || fail "cannot remove $path"
          if [ -e "$path" ]; then fail "$path still exists after removal"; else echo "   removed $path"; REMOVED="$REMOVED $(basename "$path")"; fi
        fi ;;
      replaced|intent-replaced)
        if [ "$cur" = "$bhash" ]; then echo "   $path already holds the original content"
        elif [ "$cur" != "$hash" ]; then fail "DIVERGED: $path has sha256 $cur, neither the original nor the installed content: left in place, NOT restored"
        elif [ ! -f "$backup" ] || [ "$(sha "$backup")" != "$bhash" ]; then fail "backup $backup is missing or altered: $path CANNOT be restored"
        elif place "$backup" "$path" "$bhash"; then echo "   restored $path from $backup (hash verified)"
        else fail "restoration of $path failed"; fi ;;
      esac ;;
    OUTDIR)
      case "$how" in
      created|intent-created)
        if [ ! -d "$path" ]; then echo "   $path already absent"
        elif [ -n "$(ls -A "$path" 2>/dev/null)" ]; then echo "   LEFT IN PLACE by design: $path is not empty (artifacts are never deleted)"; LEFT="$LEFT $path"
        else
          rmdir "$path" || fail "cannot remove the empty directory $path"
          [ ! -d "$path" ] && echo "   removed empty $path"
        fi ;;
      *) echo "   $path pre-existing: untouched" ;;
      esac ;;
    esac
  done < "$W/plan"
  systemctl daemon-reload; RC=$?; echo "   daemon-reload exit status: $RC"
  [ "$RC" -eq 0 ] || fail "daemon-reload exit status $RC"
  for n in $REMOVED; do
    l=$(val "$n" LoadState); echo "   $n LoadState=${l:-?}"
    case "$l" in not-found|"") ;; *) fail "$n is still loaded (LoadState=$l) after its file was removed" ;; esac
  done
  guards_unchanged
  WRITING=0
  if [ "$FAILS" -eq 0 ]; then
    rm -rf "$STATE"
    if [ -e "$STATE" ]; then fail "cannot remove $STATE"; else echo "   removed $STATE"; fi
  fi
  if [ "$FAILS" -eq 0 ]; then
    echo "== summary"; echo "RESULT: OK (rollback complete and verified)"
    [ -z "$LEFT" ] || echo "   left in place by design:$LEFT"
  else
    echo "== summary"
    echo "RESULT: FAILED — ROLLBACK INCOMPLETE ($FAILS finding(s)); the previous state is NOT confirmed restored"
    printf '%s' "$FAILMSG"
    echo "   $STATE KEPT: manifest and backups are preserved for manual recovery"
  fi ;;
esac
[ "$FAILS" -eq 0 ] && exit 0
exit 1
