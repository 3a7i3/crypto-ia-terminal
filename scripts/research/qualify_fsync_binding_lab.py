"""Owned ephemeral child only: inspect held fd and trace exact write/fsync ranges."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import select
import shutil
import signal
import subprocess
import sys
import time

RECORDS = tuple(
    (
        json.dumps(
            {
                "scope": "SYNTHETIC_BINDING_LAB",
                "attempt_id": f"LAB-A{i}",
                "packet_id": f"LAB-P{i}",
                "trace_id": f"LAB-T{i}",
                "decision_id": f"LAB-D{i}",
            },
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    for i in (1, 2, 3)
)
WORKER = r"""
import json,os,sys
path=sys.argv[1]
fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
print(json.dumps({'pid':os.getpid(),'fd':fd}),flush=True)
assert sys.stdin.readline().strip()=='GO'
for i in (1,2,3):
    raw=(json.dumps({'scope':'SYNTHETIC_BINDING_LAB','attempt_id':f'LAB-A{i}',
        'packet_id':f'LAB-P{i}','trace_id':f'LAB-T{i}','decision_id':f'LAB-D{i}'},separators=(',',':'))+'\n').encode()
    assert os.write(fd,raw)==len(raw)
    if i==2: os.fsync(fd)
print(json.dumps({'done':True,'pid':os.getpid(),'fd':fd}),flush=True)
assert sys.stdin.readline().strip()=='GO'
os.close(fd)
"""


def bind_trace(text: str, path: str, fd: int, raw: bytes) -> dict:
    """Qualify this sequential mono-writer/no-reopen scenario only.

    Raw trace is external evidence in the actual harness; test fixture traces are
    not native evidence. No D1-E V1 conversion or production verdict is emitted.
    """
    marker = f"{fd}<{path}>"
    writes = []
    offsets = []
    synced = 0
    fsyncs = 0
    closed = False
    offset = 0
    for line in text.splitlines():
        if path not in line:
            continue
        if marker not in line or closed:
            raise ValueError("FD_PATH_OR_GENERATION_MISMATCH")
        prefix = re.escape(marker)
        write = re.fullmatch(
            r"write\(" + prefix + r', ("(?:\\.|[^"\\])*"), (\d+)\)\s*=\s*(\d+)',
            line.strip(),
        )
        if write:
            literal, count, returned = write.groups()
            data = json.loads(literal).encode("utf-8")
            if len(data) != int(count) or int(returned) != int(count):
                raise ValueError("SHORT_OR_TRUNCATED_WRITE")
            writes.append(data)
            offsets.append((offset, offset + len(data)))
            offset += len(data)
        elif re.fullmatch(r"fsync\(" + prefix + r"\)\s*=\s*0", line.strip()):
            synced = len(writes)
            fsyncs += 1
        elif re.fullmatch(r"close\(" + prefix + r"\)\s*=\s*0", line.strip()):
            closed = True
        else:
            raise ValueError("UNSUPPORTED_TARGET_TRACE")
    if (
        tuple(writes) != RECORDS
        or b"".join(writes) != raw
        or not closed
        or fsyncs != 1
        or synced != 2
    ):
        raise ValueError("LAB_CHAIN_OR_RECORD_BYTES_MISMATCH")
    rows = []
    for i, (data, (start, end)) in enumerate(zip(writes, offsets, strict=True)):
        record = json.loads(data)
        rows.append(
            {
                **record,
                "byte_start": start,
                "byte_end": end,
                "record_sha256": hashlib.sha256(data).hexdigest(),
                "lab_fsync_return_covers_range": i < synced,
            }
        )
    return {
        "records": rows,
        "native_fsync_calls": fsyncs,
        "synced_records": synced,
        "records_without_fsync_return": len(writes) - synced,
    }


def _line(proc) -> dict:
    if not select.select([proc.stdout], [], [], 10)[0]:
        raise TimeoutError("LAB_HANDSHAKE_TIMEOUT")
    return json.loads(proc.stdout.readline())


def _fd_observation(pid: int, fd: int, path: pathlib.Path) -> dict:
    fdpath = f"/proc/{pid}/fd/{fd}"
    if os.readlink(fdpath) != str(path):
        raise ValueError("LIVE_FD_PATH_MISMATCH")
    live = os.stat(fdpath)
    named = path.stat()
    if (live.st_dev, live.st_ino) != (named.st_dev, named.st_ino):
        raise ValueError("LIVE_FD_INODE_MISMATCH")
    return {
        "pid": pid,
        "fd": fd,
        "device": live.st_dev,
        "inode": live.st_ino,
        "observer_monotonic_ns": time.monotonic_ns(),
    }


def qualify(output: pathlib.Path) -> tuple[dict, int]:
    output.mkdir(mode=0o700, exist_ok=False)
    base = {
        "scope": "SYNTHETIC_MONO_WRITER_NO_REOPEN",
        "future_capture_activation": "DENIED",
        "paper_stress_runtime_go": "DENIED",
        "real_per_packet_durability": "NOT_PROVEN",
        "real_producer_completeness": "NOT_PROVEN",
        "independent_custody": "NOT_VERIFIED",
        "crash_durability": "NOT_PROVEN",
        "directory_durability": "NOT_PROVEN",
    }
    tracer = shutil.which("strace")
    if tracer is None:
        return {**base, "qualification": "NOT_OBSERVED", "reason": "NO_STRACE"}, 2
    pre = subprocess.run(
        [
            tracer,
            "-qq",
            "-e",
            "trace=fsync",
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
    (output / "preflight.stderr").write_text(pre.stderr)
    if pre.returncode:
        return {
            **base,
            "qualification": "NOT_OBSERVED",
            "reason": "PTRACE_PREFLIGHT_FAILED",
            "diagnostic": pre.stderr[:2000],
        }, 2
    path = output / "records.jsonl"
    trace_prefix = output / "writer.trace"
    proc = subprocess.Popen(
        [
            tracer,
            "-ff",
            "-qq",
            "-s",
            "65536",
            "-yy",
            "-e",
            "trace=write,pwrite64,lseek,ftruncate,dup,dup2,dup3,fsync,close",
            "-o",
            str(trace_prefix),
            sys.executable,
            "-I",
            "-B",
            "-c",
            WORKER,
            str(path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        hello = _line(proc)
        pid, fd = hello["pid"], hello["fd"]
        if type(pid) is not int or type(fd) is not int or pid <= 0 or fd < 0:
            raise ValueError("INVALID_LAB_CHILD_IDENTITY")
        before = _fd_observation(pid, fd, path)
        proc.stdin.write("GO\n")
        proc.stdin.flush()
        done = _line(proc)
        if done != {"done": True, "pid": pid, "fd": fd}:
            raise ValueError("LAB_CHILD_IDENTITY_CHANGED")
        after = _fd_observation(pid, fd, path)
        if (before["device"], before["inode"]) != (after["device"], after["inode"]):
            raise ValueError("LIVE_FILE_GENERATION_CHANGED")
        proc.stdin.write("GO\n")
        proc.stdin.flush()
        rest, stderr = proc.communicate(timeout=10)
        (output / "worker.stderr").write_text(stderr)
        if proc.returncode or rest.strip():
            raise ValueError("LAB_PROCESS_FAILED")
        traces = list(output.glob("writer.trace.*"))
        if len(traces) != 1 or traces[0].name != "writer.trace." + str(pid):
            raise ValueError("OBSERVER_PID_TRACE_MISMATCH")
        traced = traces[0].read_bytes()
        raw = path.read_bytes()
        bindings = bind_trace(traced.decode(), str(path), fd, raw)
        for row in bindings["records"]:
            row["lab_file_identity"] = {
                "device": before["device"],
                "inode": before["inode"],
                "pid": pid,
                "fd": fd,
                "lifetime": "INSPECTED_OPEN_TO_TRACED_CLOSE",
            }
        return {
            **base,
            **bindings,
            "qualification": "LAB_FD_FILE_RANGE_FSYNC_BINDING_OBSERVED",
            "fd_before": before,
            "fd_after": after,
            "trace_sha256": hashlib.sha256(traced).hexdigest(),
            "record_file_sha256": hashlib.sha256(raw).hexdigest(),
            "script_sha256": hashlib.sha256(
                pathlib.Path(__file__).read_bytes()
            ).hexdigest(),
            "worker_sha256": hashlib.sha256(WORKER.encode()).hexdigest(),
            "observer_binary_sha256": hashlib.sha256(
                pathlib.Path(tracer).read_bytes()
            ).hexdigest(),
        }, 0
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate(timeout=5)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=pathlib.Path, required=True)
    args = p.parse_args()
    report, status = qualify(args.output.absolute())
    (args.output / "report.json").write_text(
        json.dumps(report, sort_keys=True, indent=2)
    )
    print(json.dumps(report, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
