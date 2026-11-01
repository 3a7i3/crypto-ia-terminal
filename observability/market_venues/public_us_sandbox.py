"""Opt-in unprivileged restrictions for one capture child, never a service manager.

Linux x86_64 Landlock ABI >=4 only. No best-effort fallback and no added rights.
Filesystem reads and UDP are not confined by this ruleset; the pinned transport
uses fixed public HTTPS hosts and the worker has an explicit minimal environment.
"""

import ctypes
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import time

from .pilot.store import open_directory


class Ruleset(ctypes.Structure):
    _fields_ = [("fs", ctypes.c_uint64), ("net", ctypes.c_uint64)]


class Beneath(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


class NetPort(ctypes.Structure):
    _fields_ = [("access", ctypes.c_uint64), ("port", ctypes.c_uint64)]


def restrict_child(parent):
    """Irreversibly reduce this single-threaded process's rights; never root."""
    if os.uname().machine != "x86_64" or os.getuid() != 1001:
        raise RuntimeError("UNSUPPORTED_CAPTURE_IDENTITY")
    path = Path(parent)
    directory = open_directory(path)
    libc = ctypes.CDLL(None, use_errno=True)

    def check(value):
        if value < 0:
            raise OSError(ctypes.get_errno(), "LANDLOCK_REFUSED")
        return value

    rules_fd = None
    try:
        abi = check(libc.syscall(444, 0, 0, 1))
        if abi < 4:
            raise RuntimeError("LANDLOCK_ABI_4_REQUIRED")
        # Handle every ABI4 write/create/remove/rename/truncate right, and TCP
        # bind/connect. Reads, execute and UDP are deliberately not claimed.
        fs = ((1 << 15) - 1) & ~((1 << 0) | (1 << 2) | (1 << 3))
        rules = Ruleset(fs, 3)
        rules_fd = check(
            libc.syscall(444, ctypes.byref(rules), ctypes.sizeof(rules), 0)
        )
        permitted = sum(1 << bit for bit in (1, 4, 5, 7, 8, 13, 14))
        beneath = Beneath(permitted, directory)
        check(libc.syscall(445, rules_fd, 1, ctypes.byref(beneath), 0))
        port = NetPort(2, 443)
        check(libc.syscall(445, rules_fd, 2, ctypes.byref(port), 0))
        check(
            libc.prctl(38, 1, 0, 0, 0)
        )  # PR_SET_NO_NEW_PRIVS, no capabilities gained.
        check(libc.syscall(446, rules_fd, 0))
        return {
            "landlock_abi": abi,
            "write_parent": str(path),
            "tcp_connect_ports": [443],
            "tcp_bind_allowed": False,
            "no_new_privs": True,
            "uid": os.getuid(),
            "read_confined": False,
            "udp_confined": False,
        }
    finally:
        if rules_fd is not None:
            os.close(rules_fd)
        os.close(directory)


def child_limits():
    resource.setrlimit(resource.RLIMIT_AS, (268435456, 268435456))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_FSIZE, (524288, 524288))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))


def disk_usage(parent):
    """Bounded walk; symlinks/non-regular objects refuse the new private run."""
    files = logical = allocated = 0
    pending = [Path(parent)]
    directories = 0
    while pending:
        p = pending.pop()
        with os.scandir(p) as items:
            for entry in items:
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    directories += 1
                    if directories > 2:
                        raise RuntimeError("UNEXPECTED_CAPTURE_DIRECTORIES")
                    pending.append(Path(entry.path))
                elif stat.S_ISREG(info.st_mode):
                    files += 1
                    logical += info.st_size
                    allocated += info.st_blocks * 512
                    if files > 80 or logical > 16777216 or allocated > 33554432:
                        raise RuntimeError("OUTER_DISK_BUDGET")
                else:
                    raise RuntimeError("UNEXPECTED_CAPTURE_OBJECT")
    return {"files": files, "logical_bytes": logical, "allocated_bytes": allocated}


def supervise(command, *, source_directory, run_parent, timeout_seconds=35):
    """One owned process group; no retry, service operation or environment reuse.

    Caller must first pin/review the command and write the one-use admission
    receipt. This function supplies boundaries, not activation authority.
    """
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 35:
        raise ValueError("INVALID_OUTER_DEADLINE")
    parent_fd = open_directory(run_parent)
    try:
        if os.listdir(parent_fd):
            raise ValueError("FRESH_CAPTURE_PARENT_REQUIRED")
    finally:
        os.close(parent_fd)
    env = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(source_directory),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    child = subprocess.Popen(
        command,
        cwd=source_directory,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        preexec_fn=child_limits,
        close_fds=True,
    )

    started = time.monotonic()
    reason = None
    usage = None
    output = bytearray()
    os.set_blocking(child.stdout.fileno(), False)

    def drain():
        try:
            block = os.read(child.stdout.fileno(), max(1, 8193 - len(output)))
        except BlockingIOError:
            return
        output.extend(block)

    try:
        while child.poll() is None:
            drain()
            if len(output) > 8192:
                reason = "OUTPUT_BUDGET"
                break
            try:
                usage = disk_usage(run_parent)
            except (OSError, RuntimeError) as exc:
                reason = str(exc)
                break
            if time.monotonic() - started > timeout_seconds:
                reason = "OUTER_DEADLINE"
                break
            time.sleep(0.05)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=1)
        drain()
        child.stdout.close()
    if len(output) > 8192:
        reason = reason or "OUTPUT_BUDGET"
    return {
        "returncode": child.returncode,
        "stopped_reason": reason,
        "elapsed_seconds": time.monotonic() - started,
        "usage": usage,
        "output": bytes(output[:8192]).decode("utf-8", errors="replace"),
        "collector_is_persistent": False,
        "service_action_performed": False,
    }
