"""Observe synthetic child fsync only; never attach to existing processes."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import platform
import re
import shutil
import subprocess
import sys

DATA = b'{"scope":"SYNTHETIC_FSYNC_LAB_ONLY","record":1}\n'
WORKER = r"""
import json,os,sys
path,mode=sys.argv[1:]
invalid_fd=None
data=b'{"scope":"SYNTHETIC_FSYNC_LAB_ONLY","record":1}\n'
with open(path,'xb') as f:
    f.write(data); f.flush()
    if mode=='real':
        os.fsync(f.fileno())
    elif mode=='error':
        invalid_fd=os.dup(f.fileno()); os.close(invalid_fd)
        try: os.fsync(invalid_fd)
        except OSError: pass
print(json.dumps({'writer_claimed_success':mode!='error','invalid_fd':invalid_fd}))
"""
LINE = re.compile(
    r"^(\d+\.\d+)\s+fsync\((-?\d+)(?:<([^>]+)>)?\)\s*=\s*(-?\d+)(?:\s+([A-Z][A-Z0-9_]*)(?:\s+.*)?)?$"
)


def parse_trace(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        match = LINE.fullmatch(line.strip())
        if match is None:
            raise ValueError("INCOMPLETE_OR_UNSUPPORTED_TRACE")
        at, fd, path, returned, errno = match.groups()
        returned = int(returned)
        if returned not in (-1, 0) or (returned == 0 and errno is not None):
            raise ValueError("CONTRADICTORY_SYSCALL_RETURN")
        if returned == -1 and errno is None:
            raise ValueError("MISSING_NATIVE_ERRNO")
        rows.append(
            {
                "at_utc_epoch": at,
                "fd": int(fd),
                "path": path,
                "returned": returned,
                "errno": errno,
            }
        )
    return rows


def qualify(output: pathlib.Path) -> tuple[dict, int]:
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    base = {
        "scope": "SYNTHETIC_CHILDREN_ONLY",
        "future_capture_activation": "DENIED",
        "paper_stress_runtime_go": "DENIED",
        "real_producer_completeness": "NOT_PROVEN",
        "real_per_packet_durability": "NOT_PROVEN",
        "crash_durability": "NOT_PROVEN",
        "directory_durability": "NOT_PROVEN",
        "independent_custody": "NOT_VERIFIED",
    }
    base["script_sha256"] = hashlib.sha256(
        pathlib.Path(__file__).read_bytes()
    ).hexdigest()
    base["platform"] = platform.platform()
    tracer = shutil.which("strace")
    if tracer is None:
        return {
            **base,
            "qualification": "NOT_OBSERVED",
            "reason": "STRACE_UNAVAILABLE",
        }, 2
    base["observer_binary_sha256"] = hashlib.sha256(
        pathlib.Path(tracer).read_bytes()
    ).hexdigest()
    base["observer_version"] = subprocess.run(
        [tracer, "-V"], capture_output=True, text=True, timeout=5, check=True
    ).stdout.splitlines()[0]
    base["python_version"] = sys.version.split()[0]
    base["worker_sha256"] = hashlib.sha256(WORKER.encode()).hexdigest()
    preflight = subprocess.run(
        [
            tracer,
            "-qq",
            "-e",
            "trace=fsync",
            "-yy",
            "-ttt",
            "-o",
            str(output / "preflight.trace"),
            sys.executable,
            "-I",
            "-B",
            "-c",
            "pass",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    (output / "preflight.stderr").write_text(preflight.stderr)
    if preflight.returncode != 0:
        return {
            **base,
            "qualification": "NOT_OBSERVED",
            "reason": "TRACER_PREFLIGHT_FAILED",
            "preflight_exit": preflight.returncode,
            "diagnostic": preflight.stderr[:2000],
        }, 2
    cases = []
    for mode in ("real", "claim_without_call", "error"):
        path, trace = output / f"{mode}.jsonl", output / f"{mode}.trace"
        result = subprocess.run(
            [
                tracer,
                "-qq",
                "-e",
                "trace=fsync",
                "-yy",
                "-ttt",
                "-o",
                str(trace),
                sys.executable,
                "-I",
                "-B",
                "-c",
                WORKER,
                str(path),
                mode,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        (output / f"{mode}.stderr").write_text(result.stderr)
        if result.returncode != 0:
            raise RuntimeError("LAB_WORKER_OR_TRACER_FAILED")
        raw_trace = trace.read_bytes()
        calls = parse_trace(raw_trace.decode())
        worker_output = json.loads(result.stdout)
        claimed = worker_output["writer_claimed_success"]
        raw = path.read_bytes()
        if raw != DATA:
            raise RuntimeError("LAB_RECORD_BYTES_MISMATCH")
        stat = path.stat()
        if mode == "real":
            if (
                len(calls) != 1
                or calls[0]["returned"] != 0
                or calls[0]["path"] != str(path)
                or calls[0]["fd"] < 0
            ):
                raise RuntimeError("FSYNC_SUCCESS_NOT_EXTERNALLY_OBSERVED")
        elif mode == "claim_without_call":
            if calls or claimed is not True:
                raise RuntimeError("NEGATIVE_NO_CALL_CASE_FAILED")
        elif (
            len(calls) != 1
            or calls[0]["returned"] != -1
            or calls[0]["errno"] != "EBADF"
            or calls[0]["fd"] != worker_output["invalid_fd"]
            or calls[0]["fd"] < 0
        ):
            raise RuntimeError("NEGATIVE_ERRNO_CASE_FAILED")
        cases.append(
            {
                "mode": mode,
                "calls": calls,
                "writer_claimed_success": claimed,
                "syscall_success_observed": mode == "real",
                "trace_sha256": hashlib.sha256(raw_trace).hexdigest(),
                "record_sha256": hashlib.sha256(raw).hexdigest(),
                "record_bytes": len(raw),
                "post_close_file_device": stat.st_dev,
                "post_close_file_inode": stat.st_ino,
            }
        )
    return {
        **base,
        "qualification": "LAB_SYSCALL_MECHANISM_OBSERVED",
        "cases": cases,
        "physical_generation_binding": "NOT_QUALIFIED",
        "write_range_binding": "NOT_QUALIFIED",
    }, 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        required=True,
        help="Fresh lab directory under an existing owned temporary parent",
    )
    args = parser.parse_args()
    report, exit_code = qualify(args.output.absolute())
    (args.output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True)
    )
    print(json.dumps(report, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
