"""Read the Scanner V1 common-universe publication. GET-only presentation.

The publication (``scanner-universe/1.0.0``) is produced by
``observability.scanner_universe.collect`` on the host allowed to reach the
exchanges. This reader opens no network connection and never reads raw
catalogues. It validates the publication and applies the serving-time
freshness rule (``universe.requalify``): a source older than the documented
bound withdraws every pair from the current list. Unset path => NOT_CONFIGURED;
a read failure is a typed error, never an empty universe.
"""

import json
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path

from observability.scanner_universe.schema import validate_publication
from observability.scanner_universe.universe import requalify

MAX_BYTES = 1_000_000


@dataclass(frozen=True)
class ScannerUniverseReadResult:
    ok: bool
    snapshot: dict | None = None
    error_code: str | None = None


class ScannerUniverseReader:
    def __init__(self, path=None, *, now_fn=None):
        configured = os.getenv("OPERATOR_SCANNER_UNIVERSE_PATH") if path is None else path
        self.path = Path(configured) if configured else None
        self.now_fn = now_fn or (lambda: time.time_ns() // 1_000_000)

    def read(self):
        def failure(code):
            return ScannerUniverseReadResult(False, error_code="SCANNER_UNIVERSE_" + code)

        if self.path is None:
            return failure("NOT_CONFIGURED")
        if any(p.is_symlink() for p in (self.path, *self.path.parents)):
            return failure("INVALID_PATH")
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return failure("MISSING")
        except OSError:
            return failure("UNREADABLE")
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                os.close(fd)
                return failure("INVALID_PATH")
            if before.st_size > MAX_BYTES:
                os.close(fd)
                return failure("TOO_LARGE")
            with os.fdopen(fd, "rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
                after = os.fstat(stream.fileno())
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if any(getattr(before, k) != getattr(after, k) for k in fields):
                return failure("CHANGED_DURING_READ")
            if len(raw) > MAX_BYTES:
                return failure("TOO_LARGE")

            def pairs(items):
                out = {}
                for k, v in items:
                    if k in out:
                        raise ValueError("duplicate field")
                    out[k] = v
                return out

            def constant(_):
                raise ValueError("nonfinite")

            doc = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
        except (OSError, UnicodeError):
            return failure("UNREADABLE")
        except (ValueError, RecursionError):
            return failure("MALFORMED_JSON")
        try:
            errors = validate_publication(doc)
            served = None if errors else requalify(doc, self.now_fn())
            if served is not None:
                errors = validate_publication(served)
        except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
            errors = ["EXCEPTION"]
        if errors:
            return failure("INVALID_SCHEMA")
        return ScannerUniverseReadResult(True, served)
