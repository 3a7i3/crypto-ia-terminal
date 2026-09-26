"""WEB-RL-01 offline Research Lab presentation publisher.

This module writes only the explicitly requested presentation artifact after
closed-schema validation. It never mutates Research source evidence.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from observability.research_lab_schema import (
    AUTHORITY,
    DOMAIN,
    PRODUCT,
    SCHEMA_VERSION,
    canonical_snapshot_bytes,
    snapshot_sha256,
    validate_research_lab_snapshot,
)


def publish_research_lab_snapshot(path: str | Path, doc: Mapping[str, Any]) -> str:
    """Validate then atomically publish one presentation snapshot."""

    if not validate_research_lab_snapshot(doc):
        raise ValueError("Research Lab snapshot failed WEB-RL closed schema validation")

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        doc,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8") + b"\n"

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    return snapshot_sha256(doc)


__all__ = [
    "AUTHORITY",
    "DOMAIN",
    "PRODUCT",
    "SCHEMA_VERSION",
    "canonical_snapshot_bytes",
    "publish_research_lab_snapshot",
    "snapshot_sha256",
    "validate_research_lab_snapshot",
]
