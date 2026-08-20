#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(dirname "$SCRIPT_DIR")}"
ROTATE_THRESHOLD_MB="${ROTATE_THRESHOLD_MB:-100}"
KEEP_DAYS="${KEEP_DAYS:-7}"

log() { printf '[rotate %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

rotate_if_large() {
    local file="$1" threshold_mb="$2"
    [ ! -f "$file" ] && return 0
    local size_mb
    size_mb=$(du -m "$file" | cut -f1)
    if [ "$size_mb" -lt "$threshold_mb" ]; then
        log "$(basename "$file") : ${size_mb}Mo — skip"
        return 0
    fi
    local stamp archive
    stamp="$(date -u +%Y%m%d_%H%M%S)"
    archive="${file}.${stamp}"
    log "$(basename "$file") : ${size_mb}Mo — rotation..."
    mv "$file" "$archive"
    touch "$file"
    command -v gzip > /dev/null 2>&1 && gzip "$archive" &
}

log "=== Rotation databases ==="

rotate_if_large "$PROJECT_DIR/databases/black_box.jsonl" "$ROTATE_THRESHOLD_MB"
rotate_if_large "$PROJECT_DIR/databases/gate_rejections.csv" "$ROTATE_THRESHOLD_MB"
rotate_if_large "$PROJECT_DIR/databases/integrity_audit.jsonl" 50

cutoff="$(date -u -d "${KEEP_DAYS} days ago" +%Y-%m-%d)"
log "Purge fichiers dates avant $cutoff..."

count=0
for f in "$PROJECT_DIR"/databases/decision_packets_*.jsonl "$PROJECT_DIR"/databases/cycle_data.*.jsonl; do
    [ -f "$f" ] || continue
    fdate="$(basename "$f" | grep -oP '\d{4}-?\d{2}-?\d{2}' | head -1)"
    if [ ${#fdate} -eq 8 ]; then
        fdate="${fdate:0:4}-${fdate:4:2}-${fdate:6:2}"
    fi
    [ -z "$fdate" ] && continue
    if [[ "$fdate" < "$cutoff" ]]; then
        sz=$(du -m "$f" | cut -f1)
        log "  supprime $(basename "$f") (${sz}Mo)"
        rm -f "$f"
        count=$((count + 1))
    fi
done
log "$count fichier(s) purge(s)"

find "$PROJECT_DIR/databases" -name "*.gz" -mtime +30 -delete 2>/dev/null || true

wait
log "Termine — $(du -sh "$PROJECT_DIR/databases" 2>/dev/null | cut -f1) utilises"
