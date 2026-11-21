"""Read one explicitly configured MarketDerivativesStress publication. GET-only presentation.

The publication is built offline by ``observability.market_stress.publication``. This
reader opens no network connection, recomputes nothing and reads no raw capture.
Unset path => NOT_CONFIGURED; a read failure is a typed error, never an empty market.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import stat
import time

from observability.market_stress.schema import stamp, validate_publication

MAX_BYTES = 4_000_000


@dataclass(frozen=True)
class StressReadResult:
    ok: bool
    snapshot: dict | None = None
    error_code: str | None = None


def _pairs(items):
    out = {}
    for k, v in items:
        if k in out:
            raise ValueError("duplicate field")
        out[k] = v
    return out


def _constant(_):
    raise ValueError("nonfinite")


class DerivativesStressReader:
    def __init__(self, path=None, *, now_fn=time.time):
        configured = os.getenv("OPERATOR_DERIVATIVES_STRESS_PATH") if path is None else path
        self.path = Path(configured) if configured else None
        self.now_fn = now_fn

    def read(self):
        def failure(code):
            return StressReadResult(False, error_code="DERIVATIVES_STRESS_" + code)

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
            doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        except (OSError, UnicodeError):
            return failure("UNREADABLE")
        except (ValueError, RecursionError):
            return failure("MALFORMED_JSON")
        if not validate_publication(doc):
            return failure("INVALID_SCHEMA")
        try:
            now = float(self.now_fn())
            if not math.isfinite(now):
                return failure("INVALID_READER_CLOCK")
            instant = datetime.fromtimestamp(now, timezone.utc)
        except (ValueError, TypeError, OverflowError, OSError):
            return failure("INVALID_READER_CLOCK")
        generated = stamp(doc["generated_at_utc"])
        if generated > instant:
            return failure("FUTURE")
        expiry = stamp(doc["valid_until_utc"])
        freshness = "UNRESOLVED" if expiry is None else ("STALE" if instant > expiry else "FRESH")
        return StressReadResult(True, {**doc, "publication_age_ms": (instant - generated).total_seconds() * 1000,
                                       "freshness_classification": freshness})
