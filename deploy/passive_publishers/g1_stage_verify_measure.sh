#!/bin/sh
# G1 — stage, verify and measure the passive publishers. NOTHING PERSISTENT:
# every write goes to ONE private temporary directory (mode 0700) that is removed
# at the end. No sudo, no install, no /etc, no output directory, no timer, no
# service started or restarted, no restart of the API or the Advisor.
# To run as mathieu. The three publisher commands are the ones of the unit files
# below, run once per iteration against the temporary output directory; they only
# READ the runtime sources (alerts.jsonl, databases/ metadata, burn-in projection
# path, one `systemctl show crypto-advisor.service`).
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
[ "$(id -un)" = "mathieu" ] || echo "WARN: not running as mathieu ($(id -un))"
W=$(mktemp -d "${TMPDIR:-/tmp}/g1.XXXXXX") || { echo "ABORT: no temporary directory"; exit 1; }
cleanup() { rm -rf "$W"; }
trap cleanup EXIT INT TERM HUP
FREE=$(df -Pk "$W" | awk 'NR==2{print $4}')
[ "${FREE:-0}" -ge 65536 ] || { echo "ABORT: less than 64 MiB free in $W (free=${FREE:-?} KiB)"; exit 1; }
mkdir "$W/units" "$W/out"
echo "== G1 $(date -u +%FT%TZ) user=$(id -un) work=$W runs=$RUNS"
echo "== sole write area: $W (0700, removed at the end); output dir $OUTF is NOT created"

cat > "$W/units/crypto-publish-runtime-service.service" <<'G1_EOF'
# PASSIVE PUBLISHER — SOURCE FOR REVIEW ONLY. NOT AUTHORIZED FOR INSTALLATION
# while #286 is active (see docs/runbooks/PASSIVE_PUBLISHERS_GATE_PLAN.md).
# Runs the already-staged release code (1728b3ad952b87d903ccb7442579000da292b848); no checkout, no git, no network.
[Unit]
Description=Crypto AI Terminal — passive publisher: runtime-service (one fixed systemctl show)
ConditionPathIsDirectory=/home/mathieu/operator_presentation

[Service]
Type=oneshot
SyslogIdentifier=crypto_publish_runtime_service
ExecStart=/opt/crypto-ai-terminal/operator/staging-envs/1728b3ad952b87d903ccb7442579000da292b848/bin/python -m observability.runtime_service_snapshot --path /home/mathieu/operator_presentation/runtime_service_snapshot.json
User=mathieu
UMask=0077
WorkingDirectory=/opt/crypto-ai-terminal/operator/staging-src/1728b3ad952b87d903ccb7442579000da292b848
Environment=PYTHONPATH=/opt/crypto-ai-terminal/operator/staging-src/1728b3ad952b87d903ccb7442579000da292b848
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8
Environment=TZ=UTC
Environment=LC_ALL=C
TimeoutStartSec=20s
Nice=19
IOSchedulingClass=idle
CPUWeight=10
MemoryMax=128M
TasksMax=16
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
PrivateNetwork=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/mathieu/operator_presentation
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
ProtectClock=true
ProtectHostname=true
RestrictSUIDSGID=true
RestrictRealtime=true
RestrictNamespaces=true
LockPersonality=true
MemoryDenyWriteExecute=true
SystemCallArchitectures=native
CapabilityBoundingSet=
StandardOutput=journal
StandardError=journal
G1_EOF
cat > "$W/units/crypto-publish-runtime-service.timer" <<'G1_EOF'
# PASSIVE PUBLISHER TIMER — SOURCE FOR REVIEW ONLY. NOT AUTHORIZED FOR
# INSTALLATION while #286 is active. Cadence 30 s, TimeoutStartSec 20 s: 2 x 30 + 20 = 80 s < 90 s API stale threshold.
[Unit]
Description=Crypto AI Terminal — timer: runtime-service publisher (30 s)

[Timer]
OnActiveSec=2s
OnUnitActiveSec=30s
AccuracySec=1s
Persistent=false
Unit=crypto-publish-runtime-service.service

[Install]
WantedBy=timers.target
G1_EOF
cat > "$W/units/crypto-publish-storage.service" <<'G1_EOF'
# PASSIVE PUBLISHER — SOURCE FOR REVIEW ONLY. NOT AUTHORIZED FOR INSTALLATION
# while #286 is active (see docs/runbooks/PASSIVE_PUBLISHERS_GATE_PLAN.md).
# Runs the already-staged release code (1728b3ad952b87d903ccb7442579000da292b848); no checkout, no git, no network.
[Unit]
Description=Crypto AI Terminal — passive publisher: storage (metadata of decision_packets_*.jsonl, never opened)
ConditionPathIsDirectory=/home/mathieu/operator_presentation

[Service]
Type=oneshot
SyslogIdentifier=crypto_publish_storage
# Sub-second UTC stamp: a whole-second stamp is rejected as INVALID_METADATA whenever a
# packet file was modified in the same second (latest_file_modified <= observed is required).
ExecStart=/bin/sh -c 'exec /opt/crypto-ai-terminal/operator/staging-envs/1728b3ad952b87d903ccb7442579000da292b848/bin/python -m observability.storage_snapshot --out /home/mathieu/operator_presentation/storage_snapshot.json --source-directory /home/mathieu/crypto_ai_terminal/databases --generated-at-utc "$(date -u +%%Y-%%m-%%dT%%H:%%M:%%S.%%6NZ)"'
User=mathieu
UMask=0077
WorkingDirectory=/opt/crypto-ai-terminal/operator/staging-src/1728b3ad952b87d903ccb7442579000da292b848
Environment=PYTHONPATH=/opt/crypto-ai-terminal/operator/staging-src/1728b3ad952b87d903ccb7442579000da292b848
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8
Environment=TZ=UTC
Environment=LC_ALL=C
TimeoutStartSec=20s
Nice=19
IOSchedulingClass=idle
CPUWeight=10
MemoryMax=128M
TasksMax=16
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
PrivateNetwork=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/mathieu/operator_presentation
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
ProtectClock=true
ProtectHostname=true
RestrictSUIDSGID=true
RestrictRealtime=true
RestrictNamespaces=true
LockPersonality=true
MemoryDenyWriteExecute=true
SystemCallArchitectures=native
CapabilityBoundingSet=
StandardOutput=journal
StandardError=journal
G1_EOF
cat > "$W/units/crypto-publish-storage.timer" <<'G1_EOF'
# PASSIVE PUBLISHER TIMER — SOURCE FOR REVIEW ONLY. NOT AUTHORIZED FOR
# INSTALLATION while #286 is active. Cadence 30 s, TimeoutStartSec 20 s: 2 x 30 + 20 = 80 s < 90 s API stale threshold (one failed or hung run stays FRESH).
[Unit]
Description=Crypto AI Terminal — timer: storage publisher (30 s)

[Timer]
OnActiveSec=2s
OnUnitActiveSec=30s
AccuracySec=1s
Persistent=false
Unit=crypto-publish-storage.service

[Install]
WantedBy=timers.target
G1_EOF
cat > "$W/units/crypto-publish-events.service" <<'G1_EOF'
# PASSIVE PUBLISHER — SOURCE FOR REVIEW ONLY. NOT AUTHORIZED FOR INSTALLATION
# while #286 is active (see docs/runbooks/PASSIVE_PUBLISHERS_GATE_PLAN.md).
# Runs the already-staged release code (1728b3ad952b87d903ccb7442579000da292b848); no checkout, no git, no network.
[Unit]
Description=Crypto AI Terminal — passive publisher: event-center (bounded read of explicit sources)
ConditionPathIsDirectory=/home/mathieu/operator_presentation

[Service]
Type=oneshot
SyslogIdentifier=crypto_publish_events
ExecStart=/bin/sh -c 'exec /opt/crypto-ai-terminal/operator/staging-envs/1728b3ad952b87d903ccb7442579000da292b848/bin/python -m observability.event_center_snapshot --out /home/mathieu/operator_presentation/event_center_snapshot.json --generated-at-utc "$(date -u +%%Y-%%m-%%dT%%H:%%M:%%S.%%6NZ)" --p12-alerts /home/mathieu/crypto_ai_terminal/cache/startup/alerts.jsonl --ppl-lifecycles /home/mathieu/crypto_ai_terminal/databases/burn_in_status_snapshot.json'
User=mathieu
UMask=0077
WorkingDirectory=/opt/crypto-ai-terminal/operator/staging-src/1728b3ad952b87d903ccb7442579000da292b848
Environment=PYTHONPATH=/opt/crypto-ai-terminal/operator/staging-src/1728b3ad952b87d903ccb7442579000da292b848
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8
Environment=TZ=UTC
Environment=LC_ALL=C
TimeoutStartSec=20s
Nice=19
IOSchedulingClass=idle
CPUWeight=10
MemoryMax=128M
TasksMax=16
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
PrivateNetwork=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/mathieu/operator_presentation
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
ProtectClock=true
ProtectHostname=true
RestrictSUIDSGID=true
RestrictRealtime=true
RestrictNamespaces=true
LockPersonality=true
MemoryDenyWriteExecute=true
SystemCallArchitectures=native
CapabilityBoundingSet=
StandardOutput=journal
StandardError=journal
G1_EOF
cat > "$W/units/crypto-publish-events.timer" <<'G1_EOF'
# PASSIVE PUBLISHER TIMER — SOURCE FOR REVIEW ONLY. NOT AUTHORIZED FOR
# INSTALLATION while #286 is active. Cadence 30 s, TimeoutStartSec 20 s: 2 x 30 + 20 = 80 s < 90 s API stale threshold (one failed or hung run stays FRESH).
[Unit]
Description=Crypto AI Terminal — timer: event-center publisher (30 s)

[Timer]
OnActiveSec=2s
OnUnitActiveSec=30s
AccuracySec=1s
Persistent=false
Unit=crypto-publish-events.service

[Install]
WantedBy=timers.target
G1_EOF
echo "== 1. staged $(ls "$W/units" | wc -l) unit files"
( cd "$W/units" && systemd-analyze verify ./crypto-publish-*.service ./crypto-publish-*.timer ) 2>&1
echo "verify exit status: $?  (0 = no error; messages above, if any, are findings)"

echo "== 2. offline security exposure (systemd-analyze security --offline)"
if systemd-analyze security --help 2>&1 | grep -q -- '--offline'; then
  for u in "$W"/units/*.service; do
    S=$(systemd-analyze security --offline=true --no-pager "$u" 2>&1 | tail -n 1)
    echo "$(basename "$u"): ${S:-no output}"
  done
else
  echo "SKIPPED: this systemd-analyze has no --offline (security is then checked at G2 on installed units)"
fi

# stat-only fingerprints of live sources (informational: live writers may change them)
fp() { stat -c '%n size=%s mtime=%Y ctime=%Z' "$RT/cache/startup/alerts.jsonl" "$RT/databases/burn_in_status_snapshot.json" 2>&1; stat -c '%n mtime=%Y ctime=%Z' "$RT/databases" 2>&1; }
BEFORE=$(fp)

# validity of an artifact with the repository's own validator (read-only import)
check() {
  ( cd "$SRC" && PYTHONPATH="$SRC" PYTHONDONTWRITEBYTECODE=1 "$PYBIN" - "$1" "$2" <<'PY'
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
print("   contract-valid=%s %s" % (ok(doc), extra))
PY
  )
}

echo "== 3. measure each publisher: $RUNS runs, 20 s limit, nice 19 (one process per run)"
for pair in runtime-service:runtime:runtime_service_snapshot.json storage:storage:storage_snapshot.json events:events:event_center_snapshot.json; do
  NAME=${pair%%:*}; REST=${pair#*:}; KIND=${REST%%:*}; ART=${REST#*:}
  CMD=$(sed -n 's/^ExecStart=//p' "$W/units/crypto-publish-$NAME.service" | sed 's/%%/%/g')
  CMD=$(printf '%s' "$CMD" | sed "s#$REL/staging-envs/$SHA/bin/python#$PYBIN#g; s#$OUTF#$W/out#g; s#/home/mathieu/crypto_ai_terminal#$RT#g")
  echo "-- $NAME"
  TIMES=""; BAD=0; I=0
  while [ "$I" -lt "$RUNS" ]; do
    I=$((I + 1))
    S=$(date +%s.%N)
    ( cd "$SRC" && env -i PATH=/usr/bin:/bin PYTHONPATH="$SRC" PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 TZ=UTC LC_ALL=C \
        timeout 20 nice -n 19 sh -c "$CMD" ) >"$W/run.log" 2>&1
    RC=$?
    E=$(date +%s.%N)
    T=$(echo "$E $S" | awk '{printf "%.3f", $1-$2}')
    TIMES="$TIMES $T"
    [ "$RC" -eq 0 ] || { BAD=$((BAD + 1)); echo "   run $I: exit status $RC (124 = TIMEOUT) in ${T}s: $(head -c 300 "$W/run.log")"; }
  done
  echo "   wall seconds per run:$TIMES   failed runs: $BAD/$RUNS"
  echo "$TIMES" | tr ' ' '\n' | grep -v '^$' | sort -n | awk '{a[NR]=$1} END{printf "   min=%s median=%s max=%s (whole process: interpreter start + read + JSON + fsync)\n", a[1], a[int((NR+1)/2)], a[NR]}'
  if [ -f "$W/out/$ART" ]; then
    echo "   artifact: $(stat -c %s "$W/out/$ART") bytes"; check "$KIND" "$W/out/$ART"
  else
    echo "   artifact: NOT PRODUCED (see exit status above)"
  fi
done

AFTER=$(fp)
echo "== 4. sources before/after (stat only; live writers may legitimately change them)"
if [ "$BEFORE" = "$AFTER" ]; then echo "UNCHANGED"; else echo "CHANGED (informational):"; echo "--- before"; echo "$BEFORE"; echo "--- after"; echo "$AFTER"; fi
echo "files left in the work dir other than outputs: $(find "$W" -mindepth 1 -maxdepth 1 | wc -l) entries (units, out, run.log)"

echo "== 5. cleanup"
cleanup
if [ -e "$W" ]; then echo "CLEANUP FAILED: $W still exists"; else echo "cleanup OK: $W removed"; fi
echo "== end G1"
