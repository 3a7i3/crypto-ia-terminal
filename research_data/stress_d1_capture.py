"""PAPER-STRESS #404: offline D1 Research evidence capture (no runtime access).

Consumes an explicit Research-only, already immutable staged snapshot and a
caller-supplied request manifest. Never discovers producer paths, imports the
Advisor, reads environment credentials, or changes existing scientific data.

This source capability does NOT certify whole-epoch population completeness,
producer clocks, source-to-epoch authority, or counterfactual performance.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import stat
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "PAPER_STRESS_D1_CAPTURE_REQUEST_V1"
VERSION = "PAPER_STRESS_D1_OFFLINE_CAPTURE_V1"
KINDS = ("decision_packets", "decision_identity_records", "admission_ledger", "rejection_store")
MAX_SHARD_BYTES = 256 * 1024 * 1024
MAX_SHARDS = 64
MAX_TOTAL_BYTES = 512 * 1024 * 1024


class CaptureBlocked(ValueError):
    pass


def require(ok: bool, code: str) -> None:
    if not ok:
        raise CaptureBlocked(code)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise CaptureBlocked("NONFINITE_JSON")


def _finite_float(raw: str) -> float:
    value = float(raw)
    require(math.isfinite(value), "NONFINITE_JSON")
    return value


def strict_json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates,
                          parse_constant=_reject_nonfinite, parse_float=_finite_float)
    except CaptureBlocked:
        raise
    except (ValueError, UnicodeError) as exc:
        raise CaptureBlocked("INVALID_JSON_OR_UTF8") from exc


def directory(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise CaptureBlocked("DIRECTORY_NOT_FOUND") from exc
    require(stat.S_ISDIR(mode) and not stat.S_ISLNK(mode), "UNSAFE_DIRECTORY")


def regular_bytes(path: Path, *, max_bytes: int = MAX_SHARD_BYTES) -> bytes:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise CaptureBlocked("FILE_NOT_FOUND") from exc
    require(stat.S_ISREG(mode) and not stat.S_ISLNK(mode), "UNSAFE_SOURCE_FILE")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        first = os.fstat(fd)
        require(0 < first.st_size <= max_bytes, "SOURCE_SIZE_OUT_OF_BOUNDS")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(max_bytes + 1)
        second = os.fstat(fd)
        require(len(raw) == first.st_size, "SOURCE_SHORT_READ")
        require((first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns) ==
                (second.st_dev, second.st_ino, second.st_size, second.st_mtime_ns),
                "SOURCE_MUTATED_DURING_READ")
        return raw
    finally:
        os.close(fd)


def _safe_rel(value: Any) -> PurePosixPath:
    require(isinstance(value, str) and value and "\\" not in value, "INVALID_SOURCE_RELATIVE_PATH")
    rel = PurePosixPath(value)
    require(not rel.is_absolute() and all(x not in (".", "..", "") for x in rel.parts),
            "PATH_TRAVERSAL")
    # Staged component files are not raw runtime database tree names.
    require("databases" not in rel.parts and "ppl_authority" not in rel.parts,
            "PRODUCTION_SOURCE_PATH_FORBIDDEN")
    return rel


def _time(value: Any) -> datetime:
    require(isinstance(value, str) and value.endswith("Z"), "UTC_TIME_REQUIRED")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CaptureBlocked("INVALID_TIME_FORMAT") from exc
    require(parsed.utcoffset().total_seconds() == 0, "NON_UTC_TIME")
    return parsed


def _jsonl(raw: bytes) -> list[dict[str, Any]]:
    require(raw.endswith(b"\n"), "JSONL_FINAL_NEWLINE_MISSING")
    out = []
    for line in raw.splitlines():
        require(bool(line.strip()), "BLANK_JSONL_LINE")
        record = strict_json(line)
        require(isinstance(record, dict), "NON_OBJECT_JSONL")
        out.append(record)
    return out


def _coverage(records: dict[str, list[dict[str, Any]]], start: datetime, end: datetime) -> dict[str, Any]:
    failures: list[str] = []
    metrics: dict[str, Any] = {"records_by_kind": {kind: len(records[kind]) for kind in KINDS}}
    packets = records["decision_packets"]
    packet_ids = [row.get("packet_id") for row in packets]
    if not all(isinstance(pid, str) and pid for pid in packet_ids):
        failures.append("PACKET_ID_MISSING")
    if len(set(str(pid) for pid in packet_ids)) != len(packet_ids):
        failures.append("DUPLICATE_PACKET_ID")
    traces = []
    for row in packets:
        metadata = row.get("metadata")
        trace = metadata.get("trace_id") if isinstance(metadata, dict) else None
        if not isinstance(trace, str) or not trace:
            failures.append("PACKET_TRACE_MISSING")
        else:
            traces.append(trace)
    if len(set(traces)) != len(traces):
        failures.append("DUPLICATE_PACKET_TRACE")
    identity_ids = [row.get("decision_id") for row in records["decision_identity_records"]]
    if any(not isinstance(v, str) or not v for v in identity_ids):
        failures.append("DECISION_IDENTITY_MISSING")
    if len(set(str(x) for x in identity_ids)) != len(identity_ids):
        failures.append("DECISION_IDENTITY_DUPLICATE")
    metrics["packet_identity_join"] = {
        "packets": len(packet_ids),
        "matched": len(set(traces) & set(identity_ids)),
        "missing_identity": len(set(traces) - set(identity_ids)),
        "orphan_identity": len(set(identity_ids) - set(traces)),
    }
    if set(traces) != set(identity_ids):
        failures.append("PACKET_IDENTITY_COVERAGE_GAP")

    attempts: dict[str, dict[str, Any]] = {}
    outcomes: dict[str, dict[str, Any]] = {}
    for row in records["admission_ledger"]:
        attempt_id = row.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id:
            failures.append("ADMISSION_ATTEMPT_ID_MISSING")
            continue
        event = row.get("event")
        if event == "ADMISSION_ATTEMPT":
            target = attempts
        elif event == "ADMISSION_OUTCOME":
            target = outcomes
        else:
            failures.append("UNKNOWN_ADMISSION_EVENT")
            continue
        if attempt_id in target:
            failures.append("DUPLICATE_ADMISSION_EVENT_ID")
        target[attempt_id] = row
    metrics["admission_pairs"] = {
        "attempts": len(attempts), "outcomes": len(outcomes),
        "paired": len(set(attempts) & set(outcomes)),
        "unpaired_attempts": len(set(attempts) - set(outcomes)),
        "orphan_outcomes": len(set(outcomes) - set(attempts)),
    }
    if set(attempts) != set(outcomes):
        failures.append("ADMISSION_ORPHAN_OR_UNPAIRED")
    for aid in set(attempts) & set(outcomes):
        if attempts[aid].get("symbol") != outcomes[aid].get("symbol"):
            failures.append("ADMISSION_SYMBOL_MISMATCH")
        a, b = attempts[aid].get("ts"), outcomes[aid].get("ts")
        if not isinstance(a, (int,float)) or not isinstance(b, (int,float)) or isinstance(a, bool) or isinstance(b, bool) or b < a:
            failures.append("ADMISSION_TIME_ORDER_INVALID")
    rej = records["rejection_store"]
    rejection_keys = [row.get("observation_id") for row in rej]
    if any(not isinstance(k, str) or not k for k in rejection_keys):
        failures.append("REJECTION_OBSERVATION_ID_MISSING")
    if len(set(str(k) for k in rejection_keys)) != len(rejection_keys):
        failures.append("REJECTION_OBSERVATION_ID_DUPLICATE")
    metrics["rejection_records"] = len(rej)
    # These native schemas do not all carry epoch + decision + causal timestamps.
    metrics["native_epoch_coverage"] = {
        kind: sum(1 for row in records[kind] if row.get("paper_epoch_id"))
        for kind in KINDS
    }
    metrics["native_decision_id_coverage"] = {
        kind: sum(1 for row in records[kind] if row.get("decision_id"))
        for kind in KINDS
    }
    # Exclude no records silently: out-of-window or missing timestamp is explicit.
    time_fields = {"decision_packets": "created_at", "decision_identity_records": "ts", "admission_ledger": "ts", "rejection_store": "ts"}
    time_coverage: dict[str, Any] = {}
    for kind in KINDS:
        missing = out_of_window = present = 0
        for row in records[kind]:
            val = row.get(time_fields[kind])
            if val is None:
                missing += 1
                continue
            try:
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    moment = datetime.fromtimestamp(val, timezone.utc)
                elif isinstance(val, str):
                    moment = _time(val)
                else:
                    raise ValueError("unsupported time type")
                present += 1
                if not (start <= moment <= end):
                    out_of_window += 1
            except (ValueError, OverflowError, OSError, CaptureBlocked):
                failures.append("UNPARSABLE_CAUSAL_TIME")
        time_coverage[kind] = {"timestamp_present":present,"timestamp_missing":missing,"outside_window":out_of_window}
        if out_of_window:
            failures.append("EVENT_OUTSIDE_DECLARED_WINDOW")
    metrics["time_coverage"] = time_coverage
    if any(row["timestamp_missing"] for row in time_coverage.values()):
        failures.append("CAUSAL_TIMESTAMP_COVERAGE_GAP")
    metrics["structural_failures"] = sorted(set(failures))
    metrics["structural_status"] = "BLOCKED" if failures else "CONSISTENT_SUBSET_ONLY"
    metrics["epoch_binding"] = "NOT_PROVEN_BY_SOURCE_ATTESTATION_ALONE"
    metrics["independent_producer_denominator"] = "NOT_PROVEN"
    metrics["complete_decisions_rejections_admissions"] = "NOT_PROVEN"
    metrics["counterfactual_performance_eligibility"] = "NOT_PROVEN"
    return metrics


def capture(input_root: str | Path, request_file: str | Path, output_root: str | Path) -> dict[str, Any]:
    """Build a new immutable provisional Research bundle from *prestaged* sources.

    No live runtime source reading or network. Source manifest claims are not
    independent attestation and never justify a scientific GO.
    """
    root, output = Path(input_root).absolute(), Path(output_root).absolute()
    request_path = Path(request_file).absolute()
    directory(root)
    directory(output)
    for item in (root, *root.parents, output, *output.parents):
        require(not item.is_symlink(), "SYMLINKED_DIRECTORY_ANCESTOR")
    require(not (root == Path("/home/mathieu") or Path("/home/mathieu") in root.parents or
                 root == Path("/root") or Path("/root") in root.parents or
                 output == Path("/home/mathieu") or Path("/home/mathieu") in output.parents or
                 output == Path("/root") or Path("/root") in output.parents),
            "PRODUCER_OR_ROOT_HOME_FORBIDDEN")
    require(root != output and root not in output.parents and output not in root.parents,
            "INPUT_OUTPUT_ROOT_OVERLAP")
    require("crypto_ai_terminal" not in root.parts and "databases" not in root.parts,
            "RUNTIME_SOURCE_ACCESS_FORBIDDEN")
    require(any(x in root.parts for x in ("research_audit", "readonly_research_staging")),
            "APPROVED_RESEARCH_STAGING_ROOT_REQUIRED")
    require(request_path.parent == root and not request_path.is_symlink(), "REQUEST_MUST_BE_PRESTAGED")
    request_raw = regular_bytes(request_path, max_bytes=1024 * 1024)
    request = strict_json(request_raw)
    require(isinstance(request, dict) and request.get("schema_version") == SCHEMA, "REQUEST_SCHEMA_MISMATCH")
    require(request.get("source_class") == "PRESTAGED_IMMUTABLE_RESEARCH_COPY", "SOURCE_CLASS_NOT_CERTIFIED")
    require(isinstance(request.get("paper_epoch_id"), str) and request["paper_epoch_id"], "EPOCH_ID_REQUIRED")
    require(isinstance(request.get("source_boundary_id"), str) and len(request["source_boundary_id"]) == 64,
            "SOURCE_BOUNDARY_REQUIRED")
    require(isinstance(request.get("runtime_source_sha"), str) and
            len(request["runtime_source_sha"]) == 40 and
            all(ch in "0123456789abcdef" for ch in request["runtime_source_sha"]),
            "RUNTIME_SHA_CLAIM_REQUIRED")
    require(isinstance(request.get("experiment_config_sha256"), str) and
            len(request["experiment_config_sha256"]) == 64 and
            all(ch in "0123456789abcdef" for ch in request["experiment_config_sha256"]),
            "CONFIG_SHA_CLAIM_REQUIRED")
    start, end = _time(request.get("window_start_utc")), _time(request.get("window_end_utc"))
    require(start < end, "EMPTY_CAUSAL_WINDOW")
    sources = request.get("sources")
    require(isinstance(sources, list) and 1 <= len(sources) <= MAX_SHARDS, "SOURCES_COUNT_INVALID")
    require(set(row.get("kind") for row in sources if isinstance(row, dict)) == set(KINDS),
            "ALL_FOUR_COMPONENT_KINDS_REQUIRED")
    result_sources = []
    records: dict[str, list[dict[str, Any]]] = {kind: [] for kind in KINDS}
    bytes_by_source: list[tuple[str, bytes]] = []
    known_paths = set()
    total_bytes = 0
    for row in sources:
        require(isinstance(row, dict) and row.get("kind") in KINDS, "UNKNOWN_SOURCE_KIND")
        name = _safe_rel(row.get("path"))
        require(str(name) not in known_paths, "DUPLICATE_SOURCE_PATH")
        known_paths.add(str(name))
        require(len(name.parts) <= 2, "SOURCE_PATH_TOO_DEEP")
        source = root / str(name)
        if len(name.parts) == 2:
            directory(source.parent)
        declared_sha = row.get("sha256")
        require(isinstance(declared_sha, str) and len(declared_sha) == 64 and
                all(ch in "0123456789abcdef" for ch in declared_sha), "INVALID_SOURCE_SHA")
        raw = regular_bytes(source)
        total_bytes += len(raw)
        require(total_bytes <= MAX_TOTAL_BYTES, "TOTAL_DATASET_TOO_LARGE_PARTITION_BY_DAY")
        require(sha(raw) == declared_sha, "SOURCE_SHA_MISMATCH")
        records[row["kind"]].extend(_jsonl(raw))
        bytes_by_source.append((str(name), raw))
        result_sources.append({"kind":row["kind"],"path":str(name),"bytes":len(raw),
                               "sha256":declared_sha,"record_count":len(raw.splitlines())})
    coverage = _coverage(records, start, end)
    identity = {"schema_version":VERSION,
                "capture_tool_sha256":sha(Path(__file__).read_bytes()),
                "runtime_source_sha_claim":request["runtime_source_sha"],
                "experiment_config_sha256_claim":request["experiment_config_sha256"],
                "paper_epoch_id":request["paper_epoch_id"],
                "source_boundary_id":request["source_boundary_id"],
                "request_sha256":sha(request_raw),"sources":result_sources}
    dataset_id = sha(canonical(identity))
    target = output / dataset_id
    require(not os.path.lexists(target), "DATASET_ALREADY_EXISTS")
    staging = Path(tempfile.mkdtemp(prefix=".d1-capture-", dir=output))
    try:
        for name, raw in bytes_by_source:
            dest = staging / "components" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            require(sha(regular_bytes(dest)) == sha(raw), "STAGED_COMPONENT_MISMATCH")
        manifest = {"dataset_id":dataset_id,"identity":identity,"coverage":coverage,
                    "authority":"RESEARCH_PROVISIONAL_ONLY","producer_denominator_certified":False,
                    "counterfactual_go":False}
        for name, blob in (("manifest.json", canonical(manifest)+b"\n"),
                           ("capture_request.json", request_raw)):
            with (staging / name).open("xb") as handle:
                handle.write(blob)
                handle.flush()
                os.fsync(handle.fileno())
        for subroot, directories, files in os.walk(staging, topdown=False):
            for file in files:
                os.chmod(Path(subroot) / file, 0o440)
            for folder in directories:
                os.chmod(Path(subroot) / folder, 0o550)
        os.chmod(staging, 0o550)
        os.rename(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {"status":"D1_PROVISIONAL_BUNDLE_CREATED", "dataset_id":dataset_id,
            "structural_status":coverage["structural_status"],
            "scientific_completeness":"NOT_PROVEN", "counterfactual_go":False}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Offline Research-only D1 evidence capture")
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(capture(args.input_root, args.request, args.output_root), sort_keys=True))
    except (CaptureBlocked, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status":"BLOCKED_NO_PUBLISH","reason":str(exc) if isinstance(exc,CaptureBlocked) else type(exc).__name__},sort_keys=True))
        raise SystemExit(2)