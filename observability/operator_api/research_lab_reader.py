"""WEB-RL-01 strict read-only Research Lab presentation reader.

The Operator API consumes one validated presentation artifact only. It never
reads RL-DATA/PPL JSONL, scans candidate directories, or instantiates Research
engines.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from observability.research_lab_snapshot import validate_research_lab_snapshot

DEFAULT_RESEARCH_LAB_SNAPSHOT_PATH = Path(
    "databases/research_presentation/research_lab_snapshot.json"
)


@dataclass(frozen=True)
class ResearchLabReadResult:
    ok: bool
    snapshot: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value}")


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
                error_message=f"Research Lab presentation snapshot not found: {self._path}",
            )
        if not self._path.is_file():
            return ResearchLabReadResult(
                ok=False,
                error_code="RESEARCH_LAB_INVALID_PATH",
                error_message="Research Lab presentation path is not a regular file.",
            )
        try:
            doc = json.loads(
                self._path.read_text(encoding="utf-8"),
                parse_constant=_reject_json_constant,
            )
        except (OSError, UnicodeError) as exc:
            return ResearchLabReadResult(
                ok=False,
                error_code="RESEARCH_LAB_UNREADABLE",
                error_message=str(exc),
            )
        except (json.JSONDecodeError, ValueError) as exc:
            return ResearchLabReadResult(
                ok=False,
                error_code="RESEARCH_LAB_MALFORMED_JSON",
                error_message=str(exc),
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
