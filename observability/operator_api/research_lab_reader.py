"""WEB-RL-01 strict read-only Research Lab presentation reader.

The Operator API consumes one validated presentation artifact only. It never
reads RL-DATA/PPL JSONL, scans candidate directories, or instantiates Research
engines.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from observability.research_evidence_io import EvidenceReadError, read_evidence
from observability.research_lab_schema import validate_research_lab_snapshot

DEFAULT_RESEARCH_LAB_SNAPSHOT_PATH = Path(
    "databases/research_presentation/research_lab_snapshot.json"
)


@dataclass(frozen=True)
class ResearchLabReadResult:
    ok: bool
    snapshot: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class ResearchLabSnapshotReader:
    def __init__(
        self,
        path: Path = DEFAULT_RESEARCH_LAB_SNAPSHOT_PATH,
    ) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> ResearchLabReadResult:
        if not self._path.exists():
            return ResearchLabReadResult(
                ok=False,
                error_code="RESEARCH_LAB_SNAPSHOT_MISSING",
                error_message="Research Lab presentation snapshot not found.",
            )
        if self._path.is_symlink() or not self._path.is_file():
            return ResearchLabReadResult(
                ok=False,
                error_code="RESEARCH_LAB_INVALID_PATH",
                error_message="Research Lab presentation path is not a regular file.",
            )
        try:
            doc, _ = read_evidence(self._path, limit=1024 * 1024)
        except (OSError, UnicodeError):
            return ResearchLabReadResult(
                ok=False,
                error_code="RESEARCH_LAB_UNREADABLE",
                error_message="Research Lab presentation could not be read safely.",
            )
        except (EvidenceReadError, ValueError, RecursionError):
            return ResearchLabReadResult(
                ok=False,
                error_code="RESEARCH_LAB_MALFORMED_JSON",
                error_message="Research Lab presentation could not be read safely.",
            )

        if not validate_research_lab_snapshot(doc):
            return ResearchLabReadResult(
                ok=False,
                error_code="RESEARCH_LAB_INVALID_SCHEMA",
                error_message=(
                    "Research Lab snapshot failed the WEB-RL closed schema contract."
                ),
            )

        return ResearchLabReadResult(ok=True, snapshot=dict(doc))


__all__ = [
    "DEFAULT_RESEARCH_LAB_SNAPSHOT_PATH",
    "ResearchLabReadResult",
    "ResearchLabSnapshotReader",
]
