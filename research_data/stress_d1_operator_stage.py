#!/usr/bin/env python3
"""Operator-only D1 2026-10-10 UTC Research pilot: exact bounded read-only copy.

Reads four ALLOWLISTED producer files, never PPL/FIN, and publishes a root-owned
immutable-to-chatgpt-ro subset under /var/lib. No runtime wiring, no restart.
Hashes the complete captured prefix twice, including selected-line offsets.
NOT an epoch/full population/market path scientific certification.
"""
from __future__ import annotations

import grp
import hashlib
import json
import math
import os
import shutil
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path('/home/mathieu/crypto_ai_terminal/databases')
BASE = Path('/var/lib/crypto-ai-research-audit')
TARGET_NAME = 'readonly_research_staging'
START = datetime(2026, 10, 10, tzinfo=timezone.utc).timestamp()
END = datetime(2026, 10, 11, tzinfo=timezone.utc).timestamp()
CHUNK = 1024 * 1024
MAX_LINE = 4 * 1024 * 1024
SPECS = (
    ('decision_packets', 'decision_packets_2026-10-10.jsonl', 'created_at', 'closed', 128 * CHUNK),
    ('rejection_store', 'rejections/rejections_2026-10-10.jsonl', 'ts', 'closed', 64 * CHUNK),
    ('admission_ledger', 'admission_ledger.jsonl', 'ts', 'prefix', 64 * CHUNK),
    ('decision_identity_records', 'decision_identity_journal.jsonl', 'ts', 'prefix', 384 * CHUNK),
)

class Block(Exception):
    pass


def check(value, reason):
    if not value:
        raise Block(reason)


def directory(path):
    st = path.lstat()
    check(stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode), 'INVALID_DIRECTORY')
    return st


def json_strict(raw):
    def pairs(items):
        d = {}
        for key, val in items:
            check(key not in d, 'DUPLICATE_JSON_KEY')
            d[key] = val
        return d
    def nonfinite(_):
        raise Block('NONFINITE_JSON_VALUE')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=nonfinite)
    except (ValueError, UnicodeError) as exc:
        raise Block('INVALID_JSON_OR_UTF8') from exc
    check(isinstance(value, dict), 'JSONL_ROW_NOT_OBJECT')
    return value


def record_time(row, key):
    t = row.get(key)
    check(t is not None and not isinstance(t, bool), 'MISSING_OR_INVALID_TIMESTAMP')
    if isinstance(t, (float, int)):
        check(math.isfinite(t), 'NONFINITE_TIMESTAMP')
        return float(t)
    if isinstance(t, str):
        try:
            dt = datetime.fromisoformat(t.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                # core/decision_packet.py uses datetime.utcnow().isoformat()
                # as of the reviewed main source. This is an ASSUMPTION, not
                # independent producer-clock certification.
                check(key == 'created_at', 'TIMESTAMP_WITHOUT_TIMEZONE')
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except (ValueError, OverflowError) as exc:
            raise Block('INVALID_TIMESTAMP_STRING') from exc
    raise Block('UNKNOWN_TIMESTAMP_TYPE')


def sha_file_prefix(path, size):
    digest = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        with os.fdopen(fd, 'rb', closefd=False) as f:
            remaining = size
            while remaining:
                chunk = f.read(min(remaining, CHUNK))
                check(bool(chunk), 'PREFIX_SHORT_READ_VERIFY')
                digest.update(chunk)
                remaining -= len(chunk)
    finally:
        os.close(fd)
    return digest.hexdigest()


def acquire_one(root, kind, rel, timekey, mode, cap):
    src = SOURCE / rel
    directory(src.parent)
    st = src.lstat()
    check(stat.S_ISREG(st.st_mode) and not stat.S_ISLNK(st.st_mode), 'UNSAFE_SOURCE')
    check(0 < st.st_size <= cap, 'FILE_SIZE_NOT_ALLOWED')
    prefix_length = st.st_size
    source_fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(source_fd)
        check((before.st_dev, before.st_ino, before.st_size) == (st.st_dev, st.st_ino, st.st_size), 'SOURCE_CHANGED_BEFORE_READ')
        original_sha = hashlib.sha256()
        selected_sha = hashlib.sha256()
        positions_sha = hashlib.sha256()
        count = selected = outwindow = 0
        first_ts = last_ts = None
        dest = root / (kind + '.jsonl')
        index = root / (kind + '.offsets.jsonl')
        with os.fdopen(os.dup(source_fd), 'rb') as source, dest.open('xb') as output, index.open('xb') as idx:
            position = 0
            while position < prefix_length:
                # Enforce bounded line lengths, including a final newline.
                line = source.readline(min(MAX_LINE + 1, prefix_length - position))
                check(bool(line) and len(line) <= MAX_LINE and line.endswith(b'\n'), 'INCOMPLETE_OR_OVERSIZE_SOURCE_LINE')
                original_sha.update(line)
                obj = json_strict(line)
                timestamp = record_time(obj, timekey)
                count += 1
                first_ts = timestamp if first_ts is None else min(first_ts, timestamp)
                last_ts = timestamp if last_ts is None else max(last_ts, timestamp)
                in_window = START <= timestamp < END
                if mode == 'closed':
                    check(in_window, 'CLOSED_DAY_OUTSIDE_WINDOW')
                if in_window:
                    output.write(line)
                    selected_sha.update(line)
                    selected += 1
                    metadata = json.dumps({
                        'source_line': count, 'source_byte_offset': position,
                        'source_line_bytes': len(line),
                        'source_line_sha256': hashlib.sha256(line).hexdigest(),
                    }, sort_keys=True, separators=(',', ':')).encode('utf-8') + b'\n'
                    idx.write(metadata)
                    positions_sha.update(metadata)
                else:
                    outwindow += 1
                position += len(line)
            check(position == prefix_length, 'PREFIX_POSITION_MISMATCH')
            output.flush()
            idx.flush()
            os.fsync(output.fileno())
            os.fsync(idx.fileno())
        after = os.fstat(source_fd)
        by_name = src.lstat()
        check((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino), 'SOURCE_INODE_CHANGED')
        check((before.st_dev, before.st_ino) == (by_name.st_dev, by_name.st_ino), 'SOURCE_PATH_REPLACED')
        check(after.st_size >= prefix_length and by_name.st_size >= prefix_length, 'SOURCE_TRUNCATED')
        if mode == 'closed':
            check(after.st_size == prefix_length and by_name.st_size == prefix_length and
                  after.st_mtime_ns == before.st_mtime_ns and by_name.st_mtime_ns == before.st_mtime_ns,
                  'CLOSED_DAY_MUTATED')
        check(original_sha.hexdigest() == sha_file_prefix(src, prefix_length), 'SOURCE_PREFIX_MUTATED')
        check(sha_file_prefix(dest, dest.stat().st_size) == selected_sha.hexdigest(), 'STAGED_SUBSET_MUTATED')
        check(sha_file_prefix(index, index.stat().st_size) == positions_sha.hexdigest(), 'STAGED_INDEX_MUTATED')
        return {
            'kind': kind, 'source_relative_path': rel, 'source_mode': mode,
            'source_inode': before.st_ino, 'source_device': before.st_dev,
            'source_prefix_bytes': prefix_length, 'source_prefix_sha256': original_sha.hexdigest(),
            'source_total_rows': count, 'selected_rows': selected,
            'outside_utc_window': outwindow, 'source_first_ts': first_ts, 'source_last_ts': last_ts,
            'selected_sha256': selected_sha.hexdigest(), 'selected_bytes': dest.stat().st_size,
            'offset_index_sha256': positions_sha.hexdigest(),
            'capture_policy': 'FULL_CLOSED_DAY' if mode == 'closed' else 'COMPLETE_VERIFIED_APPEND_ONLY_PREFIX_THEN_TIME_SUBSET',
        }
    finally:
        os.close(source_fd)


def main():
    os.umask(0o077)
    staging = None
    result = None
    try:
        check(os.geteuid() == 0, 'RUN_ONLY_AS_ROOT_OPERATOR')
        for p in (SOURCE, SOURCE.parent, SOURCE.parent.parent, SOURCE.parent.parent.parent):
            directory(p)
        # The parent is root-owned and not writable by chatgpt-ro.
        if not BASE.exists():
            BASE.mkdir(mode=0o750)
            os.chown(BASE, 0, grp.getgrnam('chatgpt-ro').gr_gid)
        base_st = directory(BASE)
        check(base_st.st_uid == 0 and not base_st.st_mode & (stat.S_IWGRP | stat.S_IWOTH), 'UNSAFE_RESEARCH_PARENT')
        target = BASE / TARGET_NAME
        check(not os.path.lexists(target), 'TARGET_EXISTS_NEVER_OVERWRITE')
        staging = Path(tempfile.mkdtemp(dir=BASE, prefix='.d1-pilot-staging-'))
        evidence = []
        for spec in SPECS:
            evidence.append(acquire_one(staging, *spec))
        check(all(e['selected_rows'] > 0 for e in evidence), 'EMPTY_REQUIRED_COMPONENT')
        manifest = {
            'schema': 'PAPER_STRESS_D1_OPERATOR_PREFIX_CUSTODY_V1',
            'window': {'start_utc': '2026-10-10T00:00:00Z', 'end_utc_exclusive': '2026-10-11T00:00:00Z'},
            'generated_at_utc': datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
            'source_epoch_binding': 'UNVERIFIED',
            'decision_packet_created_at_clock_basis': 'NAIVE_ISO8601_ASSUMED_UTC_FROM_SOURCE_IMPL_NOT_CLOCK_CERTIFIED',
            'producer_denominator': 'NOT_PROVEN',
            'population_completeness': 'NOT_PROVEN',
            'market_path': 'NOT_INCLUDED',
            'authority': 'RESEARCH_PROVISIONAL_ONLY',
            'records': evidence,
        }
        mraw = json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False).encode('utf-8') + b'\n'
        (staging / 'custody_manifest.json').write_bytes(mraw)
        gid = grp.getgrnam('chatgpt-ro').gr_gid
        for p in staging.iterdir():
            check(p.is_file() and not p.is_symlink(), 'UNSAFE_OUTPUT_ITEM')
            os.chown(p, 0, gid)
            os.chmod(p, 0o440)
        os.chown(staging, 0, gid)
        os.chmod(staging, 0o550)
        os.rename(staging, target)
        staging = None
        result = {'status': 'D1_BOUNDED_RESEARCH_SNAPSHOT_STAGED_PROVISIONAL',
                  'target': str(target),
                  'manifest_sha256': hashlib.sha256(mraw).hexdigest(),
                  'rows_by_source': {x['kind']:x['selected_rows'] for x in evidence},
                  'scientific_completeness': 'NOT_PROVEN', 'counterfactual_go':False}
    except (Block, OSError, ValueError, KeyError) as exc:
        result = {'status': 'BLOCKED_NO_PUBLISH',
                  'reason': str(exc) if isinstance(exc, Block) else type(exc).__name__}
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)
    print(json.dumps(result,sort_keys=True,indent=2))

if __name__ == '__main__':
    main()
