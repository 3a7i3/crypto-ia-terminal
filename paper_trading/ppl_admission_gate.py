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
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from paper_trading.ppl_authority_runtime import AuthorityManifestError
from paper_trading.ppl_interrupted_succession import (
    ActivationClearance,
    SuccessionRefusal,
    _authentic,
)

LOCK_TIMEOUT_S = 5.0

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


__all__ = ["OPEN_DECISION_SCHEMA", "AdmissionGate", "AdmissionGateRefusal"]
