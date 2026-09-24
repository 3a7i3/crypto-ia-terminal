"""Research-owned immutable dataset tooling.

This package must remain outside PAPER runtime authority.  RL-DATA-01 exporters
consume explicit source paths and write only to caller-supplied Research storage.
"""

from .paper_exporter import (
    DatasetExistsError,
    ExportResult,
    PaperExportError,
    PaperExportRequest,
    SourceStatus,
    export_paper_dataset,
)

__all__ = [
    "DatasetExistsError",
    "ExportResult",
    "PaperExportError",
    "PaperExportRequest",
    "SourceStatus",
    "export_paper_dataset",
]
