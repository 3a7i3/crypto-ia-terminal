"""Exclusive run directory; immutable intent/raw/receipt evidence before publication."""

from pathlib import Path
import hashlib
import os
import re
import stat
from .plan import canonical
from observability.market_venues.schema import validate_publication

RESERVE = 4096


class StorageBudgetExceeded(RuntimeError):
    pass


def open_directory(path):
    p = Path(path)
    if not p.is_absolute() or ".." in p.parts:
        raise ValueError("ABSOLUTE_RUN_ROOT_REQUIRED")
    if p.name != "market-venue-pilot-runs" or any(
        part in {"presentation", "releases", "crypto-migration", ".ssh", ".config"}
        for part in p.parts
    ):
        raise ValueError("ISOLATED_RUN_ROOT_REQUIRED")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in p.parts[1:]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("RUN_ROOT_OWNER_OR_MODE")
        return fd
    except BaseException:
        os.close(fd)
        raise


class RunStore:
    def __init__(self, parent, run_id, *, max_bytes):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", run_id):
            raise ValueError("INVALID_RUN_ID")
        if type(max_bytes) is not int or not 16384 <= max_bytes <= 16777216:
            raise ValueError("INVALID_STORAGE_LIMIT")
        parent_fd = open_directory(parent)
        try:
            os.mkdir(run_id, mode=0o700, dir_fd=parent_fd)
            self.fd = os.open(
                run_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd
            )
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        self.path = Path(parent) / run_id
        self.limit = max_bytes
        self.used = 0
        self.latest = None

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _name(self, name):
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,95}", name):
            raise ValueError("INVALID_EVIDENCE_NAME")

    def _write(self, name, data, *, final=False):
        self._name(name)
        ceiling = self.limit if final else self.limit - RESERVE
        if not isinstance(data, bytes) or self.used + len(data) > ceiling:
            raise StorageBudgetExceeded("RUN_BYTE_BUDGET")
        fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o400,
            dir_fd=self.fd,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        self.used += len(data)
        os.fsync(self.fd)
        return hashlib.sha256(data).hexdigest()

    def json(self, name, value, *, final=False):
        return self._write(name, canonical(value), final=final)

    def intent(self, index, spec, before, clock_id, evidence_kind):
        from observability.market_venues.models import iso

        value = {
            "ordinal": index,
            "request": spec.document(),
            "requested_at_utc": iso(before.utc),
            "requested_utc_ns": str(before.utc_ns),
            "requested_monotonic_ns": str(before.monotonic_ns),
            "observer_clock_id": clock_id,
            "evidence_kind": evidence_kind,
        }
        return self.json(f"attempt-{index:04d}.intent.json", value)

    def capture(self, index, capture, intent_hash):
        from observability.market_venues.models import iso

        body = capture.response.body
        raw_name = f"response-{index:04d}.bin" if body is not None else None
        receipt = {
            "ordinal": index,
            "intent_sha256": intent_hash,
            "request": capture.spec.document(),
            "http_status": capture.response.status,
            "response_headers": capture.response.headers,
            "error": capture.response.error,
            "body_complete": capture.response.complete,
            "raw_file": raw_name,
            "raw_sha256": capture.payload_sha256,
            "raw_bytes": None if body is None else len(body),
            "received_at_utc": iso(capture.after.utc),
            "received_utc_ns": str(capture.after.utc_ns),
            "received_monotonic_ns": str(capture.after.monotonic_ns),
        }
        size = (len(body) if body is not None else 0) + len(canonical(receipt))
        if self.used + size > self.limit - RESERVE:
            raise StorageBudgetExceeded("CAPTURE_EVIDENCE_BUDGET")
        if body is not None:
            self._write(raw_name, body)
        return self.json(f"attempt-{index:04d}.receipt.json", receipt)

    def _latest_identity(self):
        try:
            fd = os.open("latest.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
        except FileNotFoundError:
            return None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o400:
                raise RuntimeError("FOREIGN_LATEST_POINTER")
            with os.fdopen(os.dup(fd), "rb") as stream:
                data = stream.read(4000001)
            return (info.st_dev, info.st_ino, hashlib.sha256(data).hexdigest())
        finally:
            os.close(fd)

    def publish(self, index, document):
        if not validate_publication(document):
            raise ValueError("INVALID_PUBLICATION")
        if self._latest_identity() != self.latest:
            raise RuntimeError("FOREIGN_LATEST_POINTER")
        name = f"publication-{index:04d}.json"
        digest = self.json(name, document)
        temporary = f"latest-{index:04d}.next"
        os.link(
            name,
            temporary,
            src_dir_fd=self.fd,
            dst_dir_fd=self.fd,
            follow_symlinks=False,
        )
        # One cooperating writer owns this exclusive run; never overwrite an observed foreign pointer.
        if self._latest_identity() != self.latest:
            raise RuntimeError("FOREIGN_LATEST_POINTER")
        os.replace(temporary, "latest.json", src_dir_fd=self.fd, dst_dir_fd=self.fd)
        os.fsync(self.fd)
        self.latest = self._latest_identity()
        return {"file": name, "sha256": digest}
