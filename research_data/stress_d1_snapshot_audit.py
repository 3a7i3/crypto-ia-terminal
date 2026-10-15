"""Independent D1 snapshot auditor for PAPER-STRESS #404 (READ ONLY).

Reads only the operator-created Research staging root, never production files.
No output files, database connections, orders, service control, or imports from
production source. A passing copy integrity check is NOT producer completeness.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path('/var/lib/crypto-ai-research-audit/readonly_research_staging')
EXPECTED_MANIFEST_SHA = 'a57d64a69aa4c65df5d5c601a5d56b169a8e31e7f81fd9b39de6a277bfeeb657'
WINDOW_START = datetime(2026, 10, 10, tzinfo=timezone.utc).timestamp()
WINDOW_END = datetime(2026, 10, 11, tzinfo=timezone.utc).timestamp()
KINDS = ('decision_packets', 'decision_identity_records', 'admission_ledger', 'rejection_store')
EXPECTED_COUNTS = {
    'decision_packets': 10824,
    'decision_identity_records': 10824,
    'admission_ledger': 210,
    'rejection_store': 5486,
}
SHA256 = re.compile(r'^[0-9a-f]{64}$')
MAX_LINE = 4 * 1024 * 1024
MAX_MANIFEST = 1024 * 1024


class AuditBlocked(ValueError):
    pass


def require(test: bool, code: str) -> None:
    if not test:
        raise AuditBlocked(code)


def strict_json(raw: bytes) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in d, 'DUPLICATE_JSON_KEY')
            d[key] = value
        return d

    def nonfinite(_value: str) -> None:
        raise AuditBlocked('NONFINITE_JSON')

    def finite_float(value: str) -> float:
        number = float(value)
        require(math.isfinite(number), 'NONFINITE_JSON')
        return number

    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=no_duplicates,
                           parse_constant=nonfinite, parse_float=finite_float)
    except (ValueError, UnicodeError) as exc:
        raise AuditBlocked('INVALID_JSON_OR_UTF8') from exc
    require(isinstance(value, dict), 'JSON_NOT_OBJECT')
    return value


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open_regular(path) as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def open_regular(path: Path):
    st = path.lstat()
    require(stat.S_ISREG(st.st_mode) and not stat.S_ISLNK(st.st_mode), 'NOT_REGULAR_FILE')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        fst = os.fstat(fd)
        require(stat.S_ISREG(fst.st_mode) and fst.st_ino == st.st_ino and fst.st_dev == st.st_dev,
                'FILE_REPLACED_DURING_OPEN')
        return os.fdopen(fd, 'rb')
    except Exception:
        os.close(fd)
        raise


def time_value(obj: dict[str, Any], kind: str) -> tuple[float, bool]:
    field = 'created_at' if kind == 'decision_packets' else 'ts'
    value = obj.get(field)
    require(value is not None and not isinstance(value, bool), 'MISSING_OR_INVALID_CAUSAL_TIME')
    if isinstance(value, (float, int)):
        require(math.isfinite(value), 'NONFINITE_TIME')
        return float(value), False
    require(isinstance(value, str), 'UNSUPPORTED_TIME_TYPE')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        naive = parsed.tzinfo is None
        require(not naive or kind == 'decision_packets', 'NAIVE_TIME_NOT_AUTHORIZED')
        if naive:
            parsed = parsed.replace(tzinfo=timezone.utc)
        require(parsed.utcoffset().total_seconds() == 0, 'NON_UTC_OFFSET')
        return parsed.timestamp(), naive
    except (OverflowError, ValueError, AttributeError) as exc:
        raise AuditBlocked('INVALID_TIME') from exc


def count_summary(records: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    packets = records['decision_packets']
    identities = records['decision_identity_records']
    admissions = records['admission_ledger']
    rejections = records['rejection_store']
    defects: Counter[str] = Counter()

    def key(o: dict[str, Any], field: str) -> str | None:
        v = o.get(field)
        return v if isinstance(v, str) and v else None

    packet_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    trace_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    packet_traces: dict[str, set[str]] = defaultdict(set)
    for row in packets:
        pid = key(row, 'packet_id')
        metadata = row.get('metadata')
        trace = key(metadata, 'trace_id') if isinstance(metadata, dict) else None
        if not pid:
            defects['PACKET_ID_MISSING'] += 1
        else:
            packet_groups[pid].append(row)
        if not trace:
            defects['PACKET_TRACE_MISSING'] += 1
        else:
            trace_groups[trace].append(row)
        if pid and trace:
            packet_traces[pid].add(trace)

    duplicate_packet_ids = sum(len(v) - 1 for v in packet_groups.values() if len(v) > 1)
    duplicate_packet_traces = sum(len(v) - 1 for v in trace_groups.values() if len(v) > 1)
    many_trace_per_packet = sum(1 for v in packet_traces.values() if len(v) != 1)
    identities_by_trace: dict[str, list[dict[str, Any]]] = defaultdict(list)
    identity_payload_conflicts = 0
    identity_digest_invalid = 0
    for row in identities:
        trace = key(row, 'decision_id')
        if trace is None:
            defects['IDENTITY_TRACE_MISSING'] += 1
            continue
        identities_by_trace[trace].append(row)
        payload = row.get('payload')
        digest = row.get('payload_digest')
        if isinstance(payload, dict) and isinstance(digest, str) and SHA256.fullmatch(digest):
            raw = json.dumps(payload, sort_keys=True, separators=(',', ':'),
                             default=str).encode('utf-8')
            if hashlib.sha256(raw).hexdigest() != digest:
                identity_digest_invalid += 1
        else:
            identity_digest_invalid += 1

    identity_history_extra_rows = sum(len(v) - 1 for v in identities_by_trace.values() if len(v) > 1)
    for group in identities_by_trace.values():
        digest_values = {row.get('payload_digest') for row in group}
        if len(digest_values) > 1:
            identity_payload_conflicts += 1

    packet_trace_set = set(trace_groups)
    identity_trace_set = set(identities_by_trace)
    joined_trace_ids = packet_trace_set & identity_trace_set
    symbol_mismatch = cycle_mismatch = 0
    for trace in joined_trace_ids:
        packet_group = trace_groups[trace]
        id_group = identities_by_trace[trace]
        packet_symbols = {str(row.get('symbol')) for row in packet_group}
        identity_symbols = {str(row.get('symbol')) for row in id_group}
        packet_cycles = {str(row.get('created_cycle_id')) for row in packet_group}
        identity_cycles = {str(row.get('cycle')) for row in id_group}
        if packet_symbols != identity_symbols:
            symbol_mismatch += 1
        if packet_cycles != identity_cycles:
            cycle_mismatch += 1

    attempts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    outcomes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in admissions:
        aid = key(row, 'attempt_id')
        if not aid:
            defects['ADMISSION_ATTEMPT_ID_MISSING'] += 1
            continue
        if row.get('event') == 'ADMISSION_ATTEMPT':
            attempts[aid].append(row)
        elif row.get('event') == 'ADMISSION_OUTCOME':
            outcomes[aid].append(row)
        else:
            defects['ADMISSION_UNKNOWN_EVENT'] += 1
    pairs = set(attempts) & set(outcomes)
    admission_symbol_mismatch = admission_time_invalid = 0
    for aid in pairs:
        a, b = attempts[aid], outcomes[aid]
        if len(a) != 1 or len(b) != 1:
            continue
        if a[0].get('symbol') != b[0].get('symbol'):
            admission_symbol_mismatch += 1
        try:
            ta, _ = time_value(a[0], 'admission_ledger')
            tb, _ = time_value(b[0], 'admission_ledger')
            if tb < ta:
                admission_time_invalid += 1
        except AuditBlocked:
            admission_time_invalid += 1

    rejection_observation_ids = [key(o, 'observation_id') for o in rejections]
    rejection_packet_ids = [key(o, 'packet_id') for o in rejections]
    rej_obs_counter = Counter(k for k in rejection_observation_ids if k)
    matched_rej_packet = sum(1 for k in rejection_packet_ids if k in packet_groups)
    rej_trace_match = sum(1 for r in rejections if (key(r, 'trace_id') or '') in joined_trace_ids)

    return {
        'step3_causes': {
            'packets': {'rows': len(packets), 'unique_packet_ids': len(packet_groups),
                        'duplicate_packet_id_rows': duplicate_packet_ids,
                        'unique_trace_ids': len(trace_groups),
                        'duplicate_trace_id_rows': duplicate_packet_traces,
                        'packet_ids_linked_to_multiple_traces': many_trace_per_packet},
            'identities': {'rows': len(identities), 'unique_decision_ids': len(identities_by_trace),
                           'history_extra_rows': identity_history_extra_rows,
                           'payload_digest_invalid_rows': identity_digest_invalid,
                           'identity_ids_with_conflicting_payload_digest': identity_payload_conflicts},
            'packet_identity_join': {'matched_unique_trace_ids': len(joined_trace_ids),
                                     'packet_traces_without_identity': len(packet_trace_set - identity_trace_set),
                                     'identities_without_packet_trace': len(identity_trace_set - packet_trace_set),
                                     'symbol_mismatched_trace_ids': symbol_mismatch,
                                     'cycle_mismatched_trace_ids': cycle_mismatch},
            'admissions': {'attempt_rows': sum(map(len, attempts.values())),
                           'outcome_rows': sum(map(len, outcomes.values())),
                           'unique_attempt_ids': len(attempts),
                           'unique_outcome_ids': len(outcomes),
                           'paired_distinct_attempt_ids': len(pairs),
                           'unpaired_attempt_ids': len(set(attempts) - set(outcomes)),
                           'orphan_outcome_ids': len(set(outcomes) - set(attempts)),
                           'duplicate_attempt_rows': sum(len(v) - 1 for v in attempts.values()),
                           'duplicate_outcome_rows': sum(len(v) - 1 for v in outcomes.values()),
                           'symbol_mismatched_pairs': admission_symbol_mismatch,
                           'noncausal_time_order_pairs': admission_time_invalid},
        },
        'step4_coverage': {
            'rejections': {'rows': len(rejections),
                           'unique_observation_ids': len(rej_obs_counter),
                           'missing_observation_id': rejection_observation_ids.count(None),
                           'duplicate_observation_rows': sum(v - 1 for v in rej_obs_counter.values()),
                           'linked_to_selected_packet_id_rows': matched_rej_packet,
                           'unlinked_to_selected_packet_id_rows': len(rejections) - matched_rej_packet,
                           'linked_to_joined_trace_id_rows': rej_trace_match},
            'producer_complete_denominator': 'NOT_PROVEN',
            'epoch_bound_identity': 'NOT_PROVEN',
            'market_paths': 'NOT_INCLUDED',
            'live_ppl_open_verification': 'NOT_PERFORMED',
            'causal_admission_to_packet_join': 'NOT_PROVEN_BY_NATIVE_SCHEMA',
            'counterfactual_eligibility': 'DENIED',
            'other_record_defects': dict(sorted(defects.items())),
        },
    }


def audit(root: Path, *, expected_manifest_sha: str = EXPECTED_MANIFEST_SHA,
          enforce_root_custody: bool = True) -> dict[str, Any]:
    """Rehash the custody snapshot and produce only aggregate, non-ID metrics."""
    status: dict[str, Any] = {
        'scope': 'PRESTAGED_READONLY_RESEARCH_ONLY',
        'snapshot_window_utc': '[2026-10-10T00:00:00Z,2026-10-11T00:00:00Z)',
        'counterfactual_go': False,
    }
    try:
        st = root.lstat()
        require(stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode), 'ROOT_NOT_DIRECTORY')
        if enforce_root_custody:
            require(st.st_uid == 0 and not st.st_mode & (stat.S_IWGRP | stat.S_IWOTH),
                    'STAGING_NOT_ROOT_OWNED_READONLY')
        manifest_path = root / 'custody_manifest.json'
        with open_regular(manifest_path) as f:
            manifest_raw = f.read(MAX_MANIFEST + 1)
        require(0 < len(manifest_raw) <= MAX_MANIFEST, 'MANIFEST_TOO_LARGE')
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        require(manifest_sha == expected_manifest_sha, 'MANIFEST_SHA256_MISMATCH')
        manifest = strict_json(manifest_raw)
        require(manifest.get('schema') == 'PAPER_STRESS_D1_OPERATOR_PREFIX_CUSTODY_V1',
                'MANIFEST_SCHEMA_MISMATCH')
        require(manifest.get('authority') == 'RESEARCH_PROVISIONAL_ONLY', 'WRONG_AUTHORITY')
        require(manifest.get('source_epoch_binding') == 'UNVERIFIED',
                'UNEXPECTED_EPOCH_AUTHORITY_CLAIM')
        require(manifest.get('population_completeness') == 'NOT_PROVEN',
                'UNEXPECTED_COMPLETENESS_CLAIM')
        require(manifest.get('window') == {'start_utc': '2026-10-10T00:00:00Z',
                                          'end_utc_exclusive': '2026-10-11T00:00:00Z'},
                'MANIFEST_WINDOW_MISMATCH')
        source_rows = manifest.get('records')
        require(isinstance(source_rows, list) and len(source_rows) == 4,
                'MANIFEST_COMPONENTS_INVALID')
        meta = {record.get('kind'): record for record in source_rows
                if isinstance(record, dict)}
        require(set(meta) == set(KINDS), 'MANIFEST_COMPONENTS_MISMATCH')
        rows: dict[str, list[dict[str, Any]]] = {}
        step1: dict[str, Any] = {'manifest_sha256': manifest_sha, 'components': {}}
        step2: dict[str, Any] = {'offset_index_validation': {}}
        for kind in KINDS:
            record = meta[kind]
            dat = root / f'{kind}.jsonl'
            idx = root / f'{kind}.offsets.jsonl'
            expected_count = EXPECTED_COUNTS[kind]
            require(record.get('selected_rows') == expected_count,
                    f'{kind}:UNEXPECTED_CAPTURE_RECORD_COUNT')
            expected_data_sha = record.get('selected_sha256')
            expected_index_sha = record.get('offset_index_sha256')
            require(isinstance(expected_data_sha, str) and SHA256.fullmatch(expected_data_sha),
                    f'{kind}:BAD_MANIFEST_DATA_SHA')
            require(isinstance(expected_index_sha, str) and SHA256.fullmatch(expected_index_sha),
                    f'{kind}:BAD_MANIFEST_INDEX_SHA')
            require(sha_file(dat) == expected_data_sha, f'{kind}:COMPONENT_SHA_MISMATCH')
            require(sha_file(idx) == expected_index_sha, f'{kind}:INDEX_SHA_MISMATCH')
            require(dat.stat().st_size == record.get('selected_bytes'),
                    f'{kind}:COMPONENT_SIZE_MISMATCH')
            require(record.get('source_total_rows') ==
                    record.get('selected_rows') + record.get('outside_utc_window'),
                    f'{kind}:SOURCE_ROW_ACCOUNTING_INCONSISTENT')
            prefix_bytes = record.get('source_prefix_bytes')
            require(type(prefix_bytes) is int and prefix_bytes > 0,
                    f'{kind}:INVALID_SOURCE_PREFIX_SIZE')
            require(isinstance(record.get('source_prefix_sha256'), str) and
                    SHA256.fullmatch(record['source_prefix_sha256']),
                    f'{kind}:SOURCE_PREFIX_DIGEST_CLAIM_MALFORMED')
            if kind in ('decision_packets', 'rejection_store'):
                require(record.get('source_mode') == 'closed' and
                        record.get('outside_utc_window') == 0 and
                        record.get('source_total_rows') == expected_count,
                        f'{kind}:CLOSED_SOURCE_COUNTS_MISMATCH')
            else:
                require(record.get('source_mode') == 'prefix',
                        f'{kind}:CUMULATIVE_PREFIX_FLAG_MISSING')

            data_rows: list[dict[str, Any]] = []
            last_line = last_end = 0
            closed_contiguous = True
            naive_count = 0
            row_count = 0
            with open_regular(dat) as data_file, open_regular(idx) as index_file:
                while True:
                    line = data_file.readline(MAX_LINE + 1)
                    offset_line = index_file.readline(MAX_LINE + 1)
                    if not line and not offset_line:
                        break
                    require(bool(line) and bool(offset_line), f'{kind}:INDEX_CARDINALITY_MISMATCH')
                    require(len(line) <= MAX_LINE and line.endswith(b'\n') and
                            len(offset_line) <= MAX_LINE and offset_line.endswith(b'\n'),
                            f'{kind}:MALFORMED_JSONL_LINE')
                    obj = strict_json(line)
                    off = strict_json(offset_line)
                    source_line = off.get('source_line')
                    start = off.get('source_byte_offset')
                    span = off.get('source_line_bytes')
                    require(type(source_line) is int and source_line > last_line,
                            f'{kind}:SOURCE_LINE_NOT_INCREASING')
                    require(type(start) is int and start >= last_end,
                            f'{kind}:SOURCE_OFFSETS_NOT_MONOTONIC')
                    require(type(span) is int and span == len(line),
                            f'{kind}:SOURCE_SPAN_MISMATCH')
                    require(start + span <= prefix_bytes,
                            f'{kind}:SOURCE_OFFSET_EXCEEDS_PREFIX')
                    require(off.get('source_line_sha256') == hashlib.sha256(line).hexdigest(),
                            f'{kind}:SOURCE_LINE_SHA_MISMATCH')
                    if start != last_end or source_line != last_line + 1:
                        closed_contiguous = False
                    moment, naive = time_value(obj, kind)
                    require(WINDOW_START <= moment < WINDOW_END,
                            f'{kind}:ROW_OUTSIDE_CAPTURE_WINDOW')
                    naive_count += int(naive)
                    last_line, last_end = source_line, start + span
                    data_rows.append(obj)
                    row_count += 1
            require(row_count == expected_count, f'{kind}:ACTUAL_ROW_COUNT_MISMATCH')
            if kind in ('decision_packets', 'rejection_store'):
                require(closed_contiguous and last_end == prefix_bytes,
                        f'{kind}:CLOSED_SOURCE_HAS_UNEXPLAINED_GAPS')
            rows[kind] = data_rows
            step1['components'][kind] = {'sha256': 'PASS', 'index_sha256': 'PASS',
                                         'selected_rows': row_count,
                                         'source_prefix_sha256': 'CLAIM_RECORDED_NOT_INDEPENDENTLY_REHASHED'}
            step2['offset_index_validation'][kind] = {
                'sha_per_selected_line': 'PASS', 'monotonic_source_offsets': 'PASS',
                'in_capture_window': 'PASS',
                'closed_day_source_contiguity': 'PASS' if kind in ('decision_packets', 'rejection_store') else 'NOT_APPLICABLE',
                'source_prefix_rehash_without_original': 'NOT_POSSIBLE_IN_RESEARCH_ONLY',
                'naive_utc_assumed_not_clock_certified': naive_count,
                'source_selected_rows': row_count,
                'source_total_rows_claim': record['source_total_rows'],
                'outside_window_rows_claim': record['outside_utc_window'],
            }
        status['step1'] = {'status': 'PASS_RESEARCH_COPIES', **step1}
        status['step2'] = {'status': 'PASS_SELECTED_ROW_INDEXES', **step2}
        status.update(count_summary(rows))
        step3 = status['step3_causes']
        status['step3_status'] = 'AGGREGATES_OBSERVED_NOT_FULL_JOIN_CERTIFIED'
        if (step3['packets']['duplicate_packet_id_rows'] == 0 and
            step3['packets']['duplicate_trace_id_rows'] == 0 and
            step3['packet_identity_join']['packet_traces_without_identity'] == 0 and
            step3['packet_identity_join']['identities_without_packet_trace'] == 0 and
            step3['packet_identity_join']['symbol_mismatched_trace_ids'] == 0 and
            step3['packet_identity_join']['cycle_mismatched_trace_ids'] == 0 and
            step3['identities']['payload_digest_invalid_rows'] == 0 and
            step3['identities']['identity_ids_with_conflicting_payload_digest'] == 0):
            status['step3_status'] = 'PACKET_IDENTITY_JOIN_PASS_LIMITED'
        admissions = step3['admissions']
        if (admissions['duplicate_attempt_rows'] or admissions['duplicate_outcome_rows'] or
            admissions['unpaired_attempt_ids'] or admissions['orphan_outcome_ids'] or
            admissions['symbol_mismatched_pairs'] or admissions['noncausal_time_order_pairs']):
            status['admission_pairing_status'] = 'GAPS_OR_CONFLICTS_PRESENT'
        else:
            status['admission_pairing_status'] = 'PAIRING_PASS_LIMITED_TO_CAPTURE_WINDOW'
        status['step4_status'] = 'EPOCH_WIDE_POPULATION_COVERAGE_NOT_PROVEN'
        status['status'] = 'D1_4STEP_COPY_AUDIT_COMPLETE_NOT_COUNTERFACTUAL_CERTIFIED'
    except (AuditBlocked, OSError, ValueError, TypeError) as exc:
        status['status'] = 'D1_AUDIT_BLOCKED'
        status['reason'] = str(exc) if isinstance(exc, AuditBlocked) else type(exc).__name__
        status['step4_status'] = 'NOT_CERTIFIED'
    return status


def main() -> None:
    result = audit(ROOT)
    print(json.dumps(result, sort_keys=True, indent=2))
    if result['status'] == 'D1_AUDIT_BLOCKED':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
