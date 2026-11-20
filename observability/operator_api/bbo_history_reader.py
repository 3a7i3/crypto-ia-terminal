"""Read one explicitly configured BBO composite history publication. GET-only presentation.

The publication (``bbo-composite-history/1.0.0``) is built offline from sealed
evidence by ``observability.radar_composite.bbo_history``. This reader opens no
network connection, recomputes nothing and never reads raw evidence. Unset path
=> NOT_CONFIGURED; a read failure is a typed error, never an empty history.
The publication is historical: no freshness is claimed for it.
"""

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from observability.radar_composite.bbo_history import validate_history

MAX_BYTES = 200_000


@dataclass(frozen=True)
class BboHistoryReadResult:
    ok: bool
    snapshot: dict | None = None
    error_code: str | None = None


class BboHistoryReader:
    def __init__(self, path=None):
        configured = os.getenv("OPERATOR_BBO_HISTORY_PATH") if path is None else path
        self.path = Path(configured) if configured else None

    def read(self):
        def failure(code):
            return BboHistoryReadResult(False, error_code="BBO_HISTORY_" + code)

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
            errors = validate_history(doc)
        except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
            errors = ["EXCEPTION"]
        if errors:
            return failure("INVALID_SCHEMA")
        # Serving provenance only; the published values are returned unchanged.
        return BboHistoryReadResult(True, {**doc, "serving": {"freshness_classification": "HISTORICAL_NOT_LIVE"}})
