"""Sandbox self-test: reports what the child can reach. Run by the supervisor before any run."""

import os
import socket


def _denied(action) -> bool:
    try:
        action()
    except OSError:
        return True
    return False


def _empty(path: str) -> bool:
    """Hidden directories are empty mounts; hidden files read as /dev/null."""
    if not os.path.exists(path):
        return True
    if os.path.isdir(path):
        return not os.listdir(path)
    with open(path, "rb") as handle:
        return handle.read(1) == b""


def run(payload: dict) -> dict:
    def connect():
        with socket.create_connection(("1.1.1.1", 443), timeout=1):
            pass

    def write(directory):
        def attempt():
            with open(os.path.join(directory, ".colony-probe"), "w") as handle:
                handle.write("x")
        return attempt

    hidden = payload["hidden"]
    with open("/proc/self/status") as handle:
        caps = {line.split(":")[0]: line.split()[1] for line in handle if line.startswith("Cap")}
    return {
        "network_denied": _denied(connect),
        "writes_denied": all(_denied(write(d)) for d in payload["write_targets"]),
        "hidden_empty": all(_empty(p) for p in hidden),
        "capabilities_dropped": all(int(v, 16) == 0 for v in caps.values()) and len(caps) == 5,
        "environment_empty": set(os.environ) <= {"LC_CTYPE"},  # PEP 538 coercion only
    }
