"""Read one explicitly configured MarketFlowArtifact file. GET-only presentation.

No exchange access, no calculation, no writer. Unset path => NOT_CONFIGURED; a read
failure is a typed error, never an empty population. A synthetic artifact is served
as synthetic: no freshness is claimed for it.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat

from observability.market_flow.artifact import validate_artifact

MAX_BYTES = 4_000_000


@dataclass(frozen=True)
class FlowReadResult:
    ok: bool
    snapshot: dict | None = None
    error_code: str | None = None


class MarketFlowReader:
    def __init__(self, path=None):
        configured = os.getenv("OPERATOR_MARKET_FLOW_PATH") if path is None else path
        self.path = Path(configured) if configured else None

    def read(self):
        def failure(code):
            return FlowReadResult(False, error_code="MARKET_FLOW_" + code)

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
            validate_artifact(doc)
        except (ValueError, TypeError, KeyError, AttributeError):
            return failure("INVALID_SCHEMA")
        # The reader adds provenance of serving only; it recomputes nothing.
        return FlowReadResult(True, {**doc, "serving": {"freshness_classification": "NOT_ASSESSED_" + doc["state_label"]}})
