"""Owned synthetic workers: native out-of-contract operations must be refused."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys

_SPEC = importlib.util.spec_from_file_location(
    "binding_lab", pathlib.Path(__file__).with_name("qualify_fsync_binding_lab.py")
)
_BINDING = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BINDING)
bind_trace = _BINDING.bind_trace

MODES = ("normal", "partial_record", "seek", "truncate", "rotation", "second_fsync")
WORKER = r"""
import json,os,sys
path,mode=sys.argv[1:]
fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
initial_fd=fd
for i in (1,2,3):
    raw=(json.dumps({'scope':'SYNTHETIC_BINDING_LAB','attempt_id':f'LAB-A{i}',
        'packet_id':f'LAB-P{i}','trace_id':f'LAB-T{i}','decision_id':f'LAB-D{i}'},separators=(',',':'))+'\n').encode()
    if i==1 and mode=='partial_record': raw=raw[:len(raw)//2]
    assert os.write(fd,raw)==len(raw)
    if i==2:
        os.fsync(fd)
        if mode=='seek': os.lseek(fd,0,os.SEEK_SET)
        if mode=='truncate': os.ftruncate(fd,0)
        if mode=='rotation':
            os.close(fd)
            os.rename(path,path+'.rotated')
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
if mode=='second_fsync': os.fsync(fd)
os.close(fd)
print(json.dumps({'pid':os.getpid(),'initial_fd':initial_fd,'final_fd':fd,'mode':mode}))
"""


def evaluate_case(mode: str, trace: str, path: str, fd: int, raw: bytes) -> dict:
    """Parser verdict only; callers must separately establish evidence provenance."""
    if mode not in MODES:
        raise ValueError("UNKNOWN_LAB_MODE")
    try:
        binding = bind_trace(trace, path, fd, raw)
    except ValueError as exc:
        return {
            "mode": mode,
            "expected": "ACCEPT" if mode == "normal" else "REFUSE",
            "actual": "REFUSE",
            "reason": str(exc),
            "expectation_met": mode != "normal",
        }
    return {
        "mode": mode,
        "expected": "ACCEPT" if mode == "normal" else "REFUSE",
        "actual": "ACCEPT",
        "expectation_met": mode == "normal",
        "binding": binding,
    }


def _run_owned(command: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=10)
        return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate(timeout=5)


def qualify(output: pathlib.Path) -> tuple[dict, int]:
    output.mkdir(mode=0o700, exist_ok=False)
    report = {
        "scope": "SYNTHETIC_OWNED_CHILDREN_ONLY",
        "qualification": "NOT_OBSERVED",
        "future_capture_activation": "DENIED",
        "paper_stress_runtime_go": "DENIED",
        "real_producer_completeness": "NOT_PROVEN",
        "real_per_packet_durability": "NOT_PROVEN",
        "independent_custody": "NOT_VERIFIED",
        "rotation_support": "NOT_QUALIFIED",
        "kernel_short_write_return": "NOT_INJECTED",
        "native_tracer_loss": "NOT_INJECTED",
        "script_sha256": hashlib.sha256(
            pathlib.Path(__file__).read_bytes()
        ).hexdigest(),
        "binding_parser_sha256": hashlib.sha256(
            pathlib.Path(__file__)
            .with_name("qualify_fsync_binding_lab.py")
            .read_bytes()
        ).hexdigest(),
        "worker_sha256": hashlib.sha256(WORKER.encode()).hexdigest(),
        "cases": [],
    }
    tracer = shutil.which("strace")
    if tracer is None:
        return {**report, "reason": "NO_STRACE"}, 2
    pre = _run_owned(
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
        ]
    )
    (output / "preflight.stderr").write_text(pre.stderr)
    if pre.returncode:
        return {**report, "reason": "PTRACE_PREFLIGHT_FAILED"}, 2
    report["observer_binary_sha256"] = hashlib.sha256(
        pathlib.Path(tracer).read_bytes()
    ).hexdigest()
    for mode in MODES:
        directory = output / mode
        directory.mkdir(mode=0o700)
        path = directory / "records.jsonl"
        result = _run_owned(
            [
                tracer,
                "-ff",
                "-qq",
                "-s",
                "65536",
                "-yy",
                "-e",
                "trace=write,pwrite64,lseek,ftruncate,dup,dup2,dup3,fsync,close,rename,openat",
                "-o",
                str(directory / "writer.trace"),
                sys.executable,
                "-I",
                "-B",
                "-c",
                WORKER,
                str(path),
                mode,
            ]
        )
        (directory / "worker.stderr").write_text(result.stderr)
        (directory / "worker.stdout").write_text(result.stdout)
        if result.returncode:
            return {
                **report,
                "reason": "WORKER_OR_TRACER_FAILED",
                "failed_mode": mode,
            }, 1
        identity = json.loads(result.stdout)
        traces = list(directory.glob("writer.trace.*"))
        if len(traces) != 1 or traces[0].name != f"writer.trace.{identity['pid']}":
            raise ValueError("NATIVE_PID_TRACE_MISMATCH")
        if identity["mode"] != mode or type(identity["initial_fd"]) is not int:
            raise ValueError("WORKER_MODE_OR_FD_MISMATCH")
        text = traces[0].read_text()
        # open/rename observations are retained in raw evidence, but #425's
        # verifier covers only its declared syscall vocabulary. Remove only
        # those two operations in an explicitly documented derived transcript.
        binding_text = "\n".join(
            line
            for line in text.splitlines()
            if not re.match(r"^(openat|rename)\(", line)
        )
        (directory / "binding-input.trace").write_text(binding_text)
        verdict = evaluate_case(
            mode, binding_text, str(path), identity["initial_fd"], path.read_bytes()
        )
        verdict["evidence"] = "NATIVE_STRACE_WITH_DERIVED_BINDING_INPUT"
        verdict["worker_identity"] = identity
        verdict["files"] = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.iterdir()
            if p.is_file()
        }
        report["cases"].append(verdict)
    if not all(case["expectation_met"] for case in report["cases"]):
        return {**report, "qualification": "FAULT_EXPECTATION_FAILED"}, 1
    return {**report, "qualification": "LAB_NATIVE_FAULT_REFUSALS_OBSERVED"}, 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    report, status = qualify(args.output.absolute())
    (args.output / "report.json").write_text(
        json.dumps(report, sort_keys=True, indent=2)
    )
    print(json.dumps(report, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
