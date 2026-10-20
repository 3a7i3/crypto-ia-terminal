"""Sandbox self-test: reports what the child can reach. Run by the supervisor before any run.

A check passes only on the refusal it expects: creating a name must fail with a
read-only or permission error (or the directory must be absent from the root),
never with a size error after the file was created.
"""

import errno
import os
import socket

_REFUSED = {errno.EROFS, errno.EACCES, errno.EPERM}
_PROBE_NAME = ".colony-probe"


def _empty(path: str) -> bool:
    """Hidden directories are empty mounts; hidden files read as /dev/null."""
    if not os.path.exists(path):
        return True
    if os.path.isdir(path):
        return not os.listdir(path)
    with open(path, "rb") as handle:
        return handle.read(1) == b""


def _creation_refused(directory: str) -> bool:
    if not os.path.lexists(directory):
        return True  # not in the root at all
    target = os.path.join(directory, _PROBE_NAME)
    attempts = (
        lambda: os.mkdir(target),
        lambda: os.close(os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)),
        lambda: os.symlink("x", target),
        lambda: os.mkfifo(target),
    )
    for attempt in attempts:
        try:
            attempt()
        except OSError as exc:
            if exc.errno in _REFUSED:
                continue
            return False
        _remove(target)  # the sandbox is broken: undo, then report it
        return False
    return True


def _remove(target: str) -> None:
    try:
        os.rmdir(target) if os.path.isdir(target) and not os.path.islink(target) else os.unlink(target)
    except OSError:
        pass


def _open_for_write_refused(path: str) -> bool:
    try:
        os.close(os.open(path, os.O_WRONLY | os.O_APPEND))
    except OSError as exc:
        return exc.errno in _REFUSED
    return False


def _unix_refused(address: str) -> bool:
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(1)
        try:
            sock.connect("\0" + address[1:] if address.startswith("@") else address)  # @ = abstract
        except OSError:
            return True
    return False


def run(payload: dict) -> dict:
    def network_refused() -> bool:
        try:
            with socket.create_connection(("1.1.1.1", 443), timeout=1):
                return False
        except OSError:
            return True

    with open("/proc/self/status") as handle:
        caps = {line.split(":")[0]: line.split()[1] for line in handle if line.startswith("Cap")}
    return {
        "network_denied": network_refused(),
        "unix_sockets_denied": all(_unix_refused(address) for address in payload["unix_sockets"]),
        "writes_denied": all(_creation_refused(directory) for directory in payload["write_targets"]),
        "existing_files_read_only": all(_open_for_write_refused(path) for path in payload["existing_files"]),
        "hidden_empty": all(_empty(path) for path in payload["hidden"]),
        "capabilities_dropped": all(int(value, 16) == 0 for value in caps.values()) and len(caps) == 5,
        "environment_empty": set(os.environ) <= {"LC_CTYPE"},  # PEP 538 coercion only
        "root_entries": sorted(os.listdir("/")),
    }
