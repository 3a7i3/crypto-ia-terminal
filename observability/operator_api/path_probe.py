"""Classify an artifact path without letting filesystem errors escape.

``Path.exists()``/``is_file()`` swallow only ENOENT-like errors; EACCES on a
parent directory raises ``PermissionError``, which would reach the HTTP layer
as an unstructured 500.  The probe keeps the four causes distinct: absent,
not a regular file, unreadable (access refused or other OSError).  It never
carries the path or the exception text, so callers cannot leak either.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

ProbeFailure = Literal["MISSING", "INVALID_PATH", "UNREADABLE"]


def probe_artifact_path(
    path: Path, *, reject_symlink: bool = False
) -> Optional[ProbeFailure]:
    """Return None for a readable-candidate regular file, else the failure kind."""

    try:
        if not path.exists():
            return "MISSING"
        if not path.is_file() or (reject_symlink and path.is_symlink()):
            return "INVALID_PATH"
    except OSError:
        return "UNREADABLE"
    return None
