"""Plateformes & levier, lot 1: durable local store of derivatives positioning observations.

Entry point for a future collector: ``PositioningStore(data_dir).ingest(mapping)``.
The collector never sees the storage format. No network, service, API route,
scheduler or purge exists in this package. Observations stay in ``data_dir``.
"""

from .contract import CONTRACT_VERSION, ContractError, normalize
from .policy import PositioningPolicy
from .store import DB_NAME, BatchResult, IngestResult, PositioningStore, StorageError

__all__ = ["CONTRACT_VERSION", "ContractError", "normalize", "PositioningPolicy", "DB_NAME",
           "BatchResult", "IngestResult", "PositioningStore", "StorageError"]
