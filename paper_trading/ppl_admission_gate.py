"""PPL-SUCCESSION-01 §5 — dedicated, persisted admission gate.

A successor epoch is born with admissions CLOSED.  Opening is a separate,
recorded, one-time act bound to the exact epoch, manifest bytes and activation
clearance.  The gate never reads ``PB_MAX_POSITIONS`` (or any environment
variable): raising a position ceiling after birth is NOT an opening mechanism.

Fail-closed everywhere: a missing, unreadable, corrupted, mis-chained or
mis-bound journal reads as CLOSED.  Closing is never refused.

Concurrency / closure priority (contract §5):

* every journal mutation runs under an exclusive ``flock`` on ``<journal>.lock``
  and re-reads the chain inside the lock (instances and processes serialise);
* ``close()`` first creates ``<journal>.closed`` with ``O_EXCL`` (atomic, needs
  no lock, cannot be lost to a racing ``open``).  While that marker exists the
  gate reads CLOSED whatever the journal says, so a close always wins over a
  concurrent or later open.  The marker is permanent for this epoch/manifest;
  there is no reopening;
* an ``open()`` whose record cannot be durably written, or cannot be read back
  as OPEN, raises and leaves the gate CLOSED;
* a ``close()`` that cannot persist anything still closes this instance and
  returns ``False`` (the caller learns the closure is not durable).

This module is not wired into ``advisor_loop`` (separate lot).

PPL-QUIESCENCE-01 lot C1a (contract v0.3) adds two READ-ONLY entry points:

* ``admission_hold(lock_timeout_s=...)``: a context manager that checks the
  gate (marker, then journal under the journal ``flock``, then marker again)
  and, when the result is ``GATE_OPEN``, KEEPS the ``flock`` until the ``with``
  exits, i.e. until the caller's durable ``commit_open`` has returned;
* ``drain_barrier(timeout_s=...)``: after the closure marker exists, takes the
  same ``flock``.  ``DRAINED`` means no gate-consulting process is executing an
  admission any more; it says NOTHING about the integrity of the PPL ledger.

Neither ever creates, writes, syncs, renames or deletes anything: the lock file
is opened ``O_RDONLY | O_NOFOLLOW`` without ``O_CREAT`` (contract §4.6).
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import logging
import math
import os
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NamedTuple

from paper_trading.ppl_authority_runtime import AuthorityManifestError
from paper_trading.ppl_interrupted_succession import (
    ActivationClearance,
    SuccessionRefusal,
    _authentic,
)

LOCK_TIMEOUT_S = 5.0

_log = logging.getLogger(__name__)

# admission_hold result codes (contract C1 §8.1)
GATE_OPEN = "GATE_OPEN"
GATE_NEVER_OPENED = "GATE_NEVER_OPENED"
GATE_LOCK_INVALID = "GATE_LOCK_INVALID"
GATE_LOCK_TIMEOUT = "GATE_LOCK_TIMEOUT"
GATE_LOCK_IDENTITY_CHANGED = "GATE_LOCK_IDENTITY_CHANGED"
GATE_CLOSED_MARKER = "GATE_CLOSED_MARKER"
GATE_CLOSED_JOURNAL = "GATE_CLOSED_JOURNAL"
GATE_JOURNAL_INVALID = "GATE_JOURNAL_INVALID"
GATE_READ_ERROR = "GATE_READ_ERROR"
GATE_REFUSAL_CODES = frozenset(
    {
        GATE_NEVER_OPENED,
        GATE_LOCK_INVALID,
        GATE_LOCK_TIMEOUT,
        GATE_LOCK_IDENTITY_CHANGED,
        GATE_CLOSED_MARKER,
        GATE_CLOSED_JOURNAL,
        GATE_JOURNAL_INVALID,
        GATE_READ_ERROR,
    }
)

# drain_barrier statuses (contract C1 §4.3)
DRAINED = "DRAINED"
NOT_CLOSED = "NOT_CLOSED"
DRAIN_TIMEOUT = "DRAIN_TIMEOUT"
DRAIN_ERROR = "DRAIN_ERROR"

_RO_LOCK_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
_WOULD_BLOCK = (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES)


class GateCheck(NamedTuple):
    permitted: bool
    code: str
    detail: str = ""


class DrainResult(NamedTuple):
    status: str
    detail: str = ""


class _Refuse(Exception):
    """Internal: a typed refusal raised during acquisition/validation only."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code, detail)
        self.code = code
        self.detail = detail


def _valid_timeout(value: Any) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("timeout must be a finite non-negative number")
    return float(value)


def _flock_ro(fd: int, timeout: float) -> bool:
    """Exclusive ``flock`` on an already-open descriptor, bounded.  No write."""

    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError as exc:
            if exc.errno not in _WOULD_BLOCK:
                raise
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.005)


def _close_fd(fd: int | None) -> None:
    """Close once, never twice.  On Linux ``close(2)`` releases the descriptor
    (and its ``flock``) even when it reports an error; retrying could close a
    descriptor number already reused by another thread.  An error is logged and
    absorbed so that it never replaces an exception already propagating."""

    if fd is None:
        return
    try:
        os.close(fd)
    except OSError as exc:
        _log.warning("[PPL-GATE] close(lock fd) reported %s; not retried", exc)


class _AdmissionHold:
    """Context manager returned by :meth:`AdmissionGate.admission_hold`.

    Two strictly separated phases (contract C1 v0.2 §4.1, C-01):

    * ``__enter__`` (acquisition and validation): only ``Exception`` raised by
      these steps becomes a refusal; ``BaseException`` (``KeyboardInterrupt``,
      ``SystemExit``...) propagates unchanged after the descriptor is closed;
    * the ``with`` body (the caller's durable commit): never intercepted.
      ``__exit__`` closes the descriptor (releasing the ``flock``) and returns
      ``False`` so every body exception propagates as the same object.

    A class, not a ``@contextmanager`` generator, so that no ``except`` clause
    can ever surround the body.
    """

    __slots__ = ("_gate", "_timeout", "_fd", "_entered")

    def __init__(self, gate: "AdmissionGate", lock_timeout_s: Any) -> None:
        self._gate = gate
        self._timeout = lock_timeout_s
        self._fd: int | None = None
        self._entered = False

    def __enter__(self) -> GateCheck:
        if self._entered:
            raise RuntimeError("admission_hold is single-use")
        self._entered = True
        try:
            check = self._acquire()
        except _Refuse as refusal:
            check = GateCheck(False, refusal.code, refusal.detail)
        except Exception as exc:  # noqa: BLE001 - acquisition only: fail closed
            check = GateCheck(False, GATE_READ_ERROR, f"{type(exc).__name__}: {exc}")
        except BaseException:
            fd, self._fd = self._fd, None
            _close_fd(fd)
            raise
        if not check.permitted:
            fd, self._fd = self._fd, None
            _close_fd(fd)
        return check

    def __exit__(self, exc_type, exc, tb) -> bool:
        fd, self._fd = self._fd, None
        _close_fd(fd)  # never raises; releases the flock
        return False  # never suppress a body exception

    def _acquire(self) -> GateCheck:
        gate = self._gate
        timeout = _valid_timeout(self._timeout)
        lock_path = gate._lock_path
        # t0 — the lock file is created by open()/close() only, never here.
        try:
            info = os.lstat(lock_path)
        except FileNotFoundError:
            raise _Refuse(GATE_NEVER_OPENED, "no lock file: gate never opened") from None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise _Refuse(GATE_LOCK_INVALID, "lock path is not a regular file")
        # t1
        if gate._forced_closed or gate._marker_present():
            raise _Refuse(GATE_CLOSED_MARKER, "closure marker present (t1)")
        self._fd = os.open(lock_path, _RO_LOCK_FLAGS)
        if not _flock_ro(self._fd, timeout):
            raise _Refuse(GATE_LOCK_TIMEOUT, "gate flock not obtained in time")
        held = os.fstat(self._fd)
        try:
            current = os.lstat(lock_path)
        except FileNotFoundError:
            raise _Refuse(GATE_LOCK_IDENTITY_CHANGED, "lock file removed") from None
        if (
            not stat.S_ISREG(current.st_mode)
            or (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise _Refuse(GATE_LOCK_IDENTITY_CHANGED, "lock file replaced")
        # t2 — journal under the flock
        records = gate._records()
        if records is None:
            raise _Refuse(GATE_JOURNAL_INVALID, "admission journal invalid")
        if not records:
            raise _Refuse(GATE_NEVER_OPENED, "admission journal empty or absent")
        if records[-1]["action"] != "OPEN":
            raise _Refuse(GATE_CLOSED_JOURNAL, "last journal record is CLOSE")
        # t3
        if gate._forced_closed or gate._marker_present():
            raise _Refuse(GATE_CLOSED_MARKER, "closure marker present (t3)")
        return GateCheck(True, GATE_OPEN, "")

OPEN_DECISION_SCHEMA = "PPL-ADMISSION-OPEN-DECISION-V1"
_GENESIS = "0" * 64
_RECORD_FIELDS = {
    "seq",
    "prev_sha256",
    "action",
    "paper_epoch_id",
    "manifest_sha256",
    "decision_sha256",
    "clearance_proof_sha256",
    "decided_by",
    "reason",
    "record_sha256",
}


class AdmissionGateRefusal(AuthorityManifestError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _record_hash(body: dict[str, Any]) -> str:
    raw = json.dumps(
        body, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _sha(raw)


class AdmissionGate:
    def __init__(
        self, path: os.PathLike[str] | str, *, paper_epoch_id: str, manifest_sha256: str
    ) -> None:
        self.path = Path(path)
        self.paper_epoch_id = paper_epoch_id
        self.manifest_sha256 = manifest_sha256
        self._forced_closed = False

    @property
    def _lock_path(self) -> Path:
        return self.path.with_name(self.path.name + ".lock")

    @property
    def _closed_marker(self) -> Path:
        return self.path.with_name(self.path.name + ".closed")

    def _marker_present(self) -> bool:
        try:
            self._closed_marker.lstat()
        except FileNotFoundError:
            return False
        except OSError:
            return True  # unreadable marker location: fail closed
        return True

    def _marker_body(self, decided_by: str, reason: str) -> bytes:
        return json.dumps(
            {
                "paper_epoch_id": self.paper_epoch_id,
                "manifest_sha256": self.manifest_sha256,
                "decided_by": str(decided_by),
                "reason": str(reason),
            },
            sort_keys=True,
        ).encode("utf-8")

    def _marker_complete(self, raw: bytes) -> bool:
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return False
        return (
            isinstance(doc, dict)
            and doc.get("paper_epoch_id") == self.paper_epoch_id
            and doc.get("manifest_sha256") == self.manifest_sha256
        )

    def _ensure_marker(self, *, decided_by: str, reason: str) -> bool:
        """Create or re-confirm the closure marker; True only on proven persistence.

        A pre-existing marker is never trusted by its mere presence: it must be
        a regular file with a complete body bound to this epoch/manifest (an
        incomplete one is rewritten in place), then file and directory are
        synced again.  Any failure returns False (the marker still closes the
        gate for every reader that sees it).
        """

        body = self._marker_body(decided_by, reason)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(
                    self._closed_marker,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                )
                created = True
            except FileExistsError:
                fd = os.open(self._closed_marker, os.O_RDWR | os.O_NOFOLLOW)
                created = False
            try:
                if not created:
                    if not stat.S_ISREG(os.fstat(fd).st_mode):
                        return False
                    raw = b""
                    while chunk := os.read(fd, 65536):
                        raw += chunk
                    if self._marker_complete(raw):
                        os.fsync(fd)
                        self._fsync_parent()
                        return True
                    os.ftruncate(fd, 0)
                    os.lseek(fd, 0, os.SEEK_SET)
                self._write_all(fd, body)
                os.fsync(fd)
            finally:
                os.close(fd)
            self._fsync_parent()
            return True
        except OSError:
            return False

    def _confirm_journal_durable(self) -> bool:
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            self._fsync_parent()
            return True
        except OSError:
            return False

    @contextmanager
    def _locked(self, timeout: float | None = None) -> Iterator[None]:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(
                self._lock_path,
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                0o600,
            )
        except OSError as exc:
            raise AdmissionGateRefusal(f"admission gate lock unavailable: {exc}") from exc
        try:
            deadline = time.monotonic() + (
                LOCK_TIMEOUT_S if timeout is None else timeout
            )
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise AdmissionGateRefusal(
                            "admission gate lock timeout; gate stays CLOSED"
                        ) from exc
                    time.sleep(0.01)
            yield
        finally:
            os.close(fd)

    @staticmethod
    def _write_all(fd: int, data: bytes) -> None:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]

    def _fsync_parent(self) -> None:
        dir_fd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    # ------------------------------------------------------------- reading

    def _records(self) -> list[dict[str, Any]] | None:
        """Validated chain, ``[]`` when absent, ``None`` when invalid."""

        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return []
        except OSError:
            return None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            return None
        try:
            lines = self.path.read_bytes().splitlines()
        except OSError:
            return None
        records: list[dict[str, Any]] = []
        prev = _GENESIS
        for number, line in enumerate(lines, start=1):
            try:
                rec = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                return None
            if not isinstance(rec, dict) or set(rec) != _RECORD_FIELDS:
                return None
            body = {k: v for k, v in rec.items() if k != "record_sha256"}
            if (
                rec["seq"] != number
                or rec["prev_sha256"] != prev
                or rec["action"] not in ("OPEN", "CLOSE")
                or rec["paper_epoch_id"] != self.paper_epoch_id
                or rec["manifest_sha256"] != self.manifest_sha256
                or rec["record_sha256"] != _record_hash(body)
            ):
                return None
            prev = rec["record_sha256"]
            records.append(rec)
        return records

    def state(self) -> str:
        if self._forced_closed or self._marker_present():
            return "CLOSED"
        records = self._records()
        if not records:
            return "CLOSED"
        return "OPEN" if records[-1]["action"] == "OPEN" else "CLOSED"

    def is_open(self) -> bool:
        return self.state() == "OPEN"

    # ------------------------------------------------ C1a read-only checks

    def admission_hold(self, *, lock_timeout_s: float) -> _AdmissionHold:
        """Read-only admission check that keeps the journal ``flock`` while the
        caller commits (contract C1 v0.3 §4.1-§4.2).  Usage::

            with gate.admission_hold(lock_timeout_s=0.25) as chk:
                if chk.permitted:
                    ...durable commit...
        """

        return _AdmissionHold(self, lock_timeout_s)

    def drain_barrier(self, *, timeout_s: float) -> DrainResult:
        """Read-only drain barrier (contract C1 §4.3, §4.8).

        ``DRAINED``: the closure marker exists and the journal ``flock`` was
        obtained after it, so no gate-consulting process is still inside an
        admission.  It is NOT evidence of PPL ledger integrity.
        """

        fd: int | None = None
        try:
            timeout = _valid_timeout(timeout_s)
            if not self._marker_present():
                return DrainResult(NOT_CLOSED, "no closure marker")
            lock_path = self._lock_path
            try:
                info = os.lstat(lock_path)
            except FileNotFoundError:
                return DrainResult(DRAINED, "no lock file: no admission ever held it")
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                return DrainResult(DRAIN_ERROR, "lock path is not a regular file")
            fd = os.open(lock_path, _RO_LOCK_FLAGS)
            if not _flock_ro(fd, timeout):
                return DrainResult(DRAIN_TIMEOUT, "gate flock not obtained in time")
            held = os.fstat(fd)
            try:
                current = os.lstat(lock_path)
            except FileNotFoundError:
                return DrainResult(DRAIN_ERROR, "lock file removed")
            if (
                not stat.S_ISREG(current.st_mode)
                or (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
            ):
                return DrainResult(DRAIN_ERROR, "lock file replaced")
            if not self._marker_present():
                return DrainResult(DRAIN_ERROR, "closure marker vanished")
            return DrainResult(DRAINED, "")
        except Exception as exc:  # noqa: BLE001 - fail closed, read-only
            return DrainResult(DRAIN_ERROR, f"{type(exc).__name__}: {exc}")
        finally:
            _close_fd(fd)

    # ------------------------------------------------------------- writing

    def _append(self, body: dict[str, Any]) -> None:
        record = dict(body)
        record["record_sha256"] = _record_hash(body)
        line = (
            json.dumps(
                record, ensure_ascii=False, allow_nan=False, sort_keys=True
            )
            + "\n"
        ).encode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(
            self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600
        )
        try:
            self._write_all(fd, line)
            os.fsync(fd)
        finally:
            os.close(fd)
        self._fsync_parent()

    def open(
        self,
        *,
        decision_bytes: bytes,
        clearance: ActivationClearance,
        now: float,
    ) -> None:
        """Open once.  The clearance is validated here, at the point of use:
        authenticity, epoch, manifest bytes and freshness (``now`` is the
        caller's clock; the clearance carries its own maximum age)."""

        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(now)
        ):
            raise AdmissionGateRefusal("opening requires an explicit finite time")
        try:
            valid = _authentic(clearance)
        except SuccessionRefusal as exc:
            raise AdmissionGateRefusal(f"activation clearance refused: {exc}") from exc
        if (
            valid.paper_epoch_id != self.paper_epoch_id
            or valid.manifest_sha256 != self.manifest_sha256
        ):
            raise AdmissionGateRefusal("activation clearance does not match this gate")
        age = float(now) - valid.issued_at
        if age < 0 or age > valid.max_age_s:
            raise AdmissionGateRefusal("activation clearance is stale or from the future")
        if not isinstance(decision_bytes, (bytes, bytearray)) or not decision_bytes:
            raise AdmissionGateRefusal("opening decision bytes are required")
        try:
            decision = json.loads(bytes(decision_bytes).decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise AdmissionGateRefusal(f"opening decision is not JSON: {exc}") from exc
        expected = {
            "schema",
            "paper_epoch_id",
            "manifest_sha256",
            "clearance_proof_sha256",
            "decided_by",
            "decided_at_utc",
        }
        if not isinstance(decision, dict) or set(decision) != expected:
            raise AdmissionGateRefusal("opening decision fields mismatch")
        if (
            decision["schema"] != OPEN_DECISION_SCHEMA
            or decision["paper_epoch_id"] != self.paper_epoch_id
            or decision["manifest_sha256"] != self.manifest_sha256
            or decision["clearance_proof_sha256"] != valid.exclusivity_proof_sha256
            or not isinstance(decision["decided_by"], str)
            or not decision["decided_by"].strip()
            or not isinstance(decision["decided_at_utc"], str)
            or not decision["decided_at_utc"].strip()
        ):
            raise AdmissionGateRefusal("opening decision does not bind this gate")

        with self._locked():
            if self._forced_closed or self._marker_present():
                raise AdmissionGateRefusal("admission gate was closed; it cannot reopen")
            records = self._records()
            if records is None:
                raise AdmissionGateRefusal("admission journal is invalid; gate stays CLOSED")
            if any(r["action"] == "OPEN" for r in records):
                raise AdmissionGateRefusal(
                    "admission gate was already opened once for this epoch/manifest"
                )
            prev = records[-1]["record_sha256"] if records else _GENESIS
            try:
                self._append(
                    {
                        "seq": len(records) + 1,
                        "prev_sha256": prev,
                        "action": "OPEN",
                        "paper_epoch_id": self.paper_epoch_id,
                        "manifest_sha256": self.manifest_sha256,
                        "decision_sha256": _sha(bytes(decision_bytes)),
                        "clearance_proof_sha256": valid.exclusivity_proof_sha256,
                        "decided_by": decision["decided_by"],
                        "reason": "",
                    }
                )
            except OSError as exc:
                # A partly persisted OPEN must not read as OPEN: close durably.
                self.close(decided_by="gate", reason="open persistence failure")
                raise AdmissionGateRefusal(
                    f"admission journal write failed; gate stays CLOSED: {exc}"
                ) from exc
            if self.state() != "OPEN":
                raise AdmissionGateRefusal(
                    "admission journal could not be read back as OPEN; gate stays CLOSED"
                )

    def close(self, *, decided_by: str, reason: str) -> bool:
        """Close the gate.  Never refused and never raises.

        Returns ``True`` when the closure is durable (marker or CLOSE record
        persisted), ``False`` when only this instance is closed.
        """

        self._forced_closed = True
        durable = self._ensure_marker(decided_by=decided_by, reason=reason)
        try:
            with self._locked(timeout=1.0):
                records = self._records()
                if records and records[-1]["action"] == "OPEN":
                    self._append(
                        {
                            "seq": len(records) + 1,
                            "prev_sha256": records[-1]["record_sha256"],
                            "action": "CLOSE",
                            "paper_epoch_id": self.paper_epoch_id,
                            "manifest_sha256": self.manifest_sha256,
                            "decision_sha256": "",
                            "clearance_proof_sha256": "",
                            "decided_by": str(decided_by),
                            "reason": str(reason),
                        }
                    )
                    durable = True
                elif records and records[-1]["action"] == "CLOSE" and not durable:
                    # A valid CLOSE already exists (marker missing): it counts
                    # only if file and directory sync again successfully now.
                    durable = self._confirm_journal_durable()
        except (AdmissionGateRefusal, OSError):
            pass
        return durable


__all__ = [
    "DRAINED",
    "DRAIN_ERROR",
    "DRAIN_TIMEOUT",
    "GATE_CLOSED_JOURNAL",
    "GATE_CLOSED_MARKER",
    "GATE_JOURNAL_INVALID",
    "GATE_LOCK_IDENTITY_CHANGED",
    "GATE_LOCK_INVALID",
    "GATE_LOCK_TIMEOUT",
    "GATE_NEVER_OPENED",
    "GATE_OPEN",
    "GATE_READ_ERROR",
    "GATE_REFUSAL_CODES",
    "NOT_CLOSED",
    "OPEN_DECISION_SCHEMA",
    "AdmissionGate",
    "AdmissionGateRefusal",
    "DrainResult",
    "GateCheck",
]
