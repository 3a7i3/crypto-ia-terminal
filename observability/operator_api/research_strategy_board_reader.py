"""Read one admitted strategy presentation, never source catalogs or engines."""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from observability.research_evidence_io import read_evidence
from observability.research_strategy_board_contract import (
    MAX_BYTES,
    validate_strategy_board,
)

DEFAULT_PATH = Path("databases/research_presentation/research_strategy_board.json")


@dataclass(frozen=True)
class StrategyBoardReadResult:
    ok: bool
    snapshot: dict | None = None
    error_code: str | None = None


class ResearchStrategyBoardReader:
    def __init__(self, path=DEFAULT_PATH):
        self.path = Path(path)

    def read(self):
        try:
            doc, _ = read_evidence(self.path, limit=MAX_BYTES)
        except FileNotFoundError:
            return StrategyBoardReadResult(
                False, error_code="RESEARCH_STRATEGY_BOARD_MISSING"
            )
        except (
            OSError,
            ValueError,
            TypeError,
            UnicodeError,
            OverflowError,
            RecursionError,
        ):
            return StrategyBoardReadResult(
                False, error_code="RESEARCH_STRATEGY_BOARD_INVALID_ARTIFACT"
            )
        if not validate_strategy_board(doc):
            return StrategyBoardReadResult(
                False, error_code="RESEARCH_STRATEGY_BOARD_INVALID_SCHEMA"
            )
        return StrategyBoardReadResult(True, doc)
