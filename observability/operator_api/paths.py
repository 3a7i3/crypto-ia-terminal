"""observability/operator_api/paths.py — neutral, side-effect-free default
paths for the O-02W-D1 read-only API.

This module exists ONLY so the API package never has to import the
producer/writer modules (`observability.operator_snapshot_builder`,
`observability.operator_runtime_manifest`) just to learn their default
file paths. Those modules transitively import
`observability.json_logger`, whose module-level initialization creates
log directories on disk (`logs/<category>/`) — an application-owned
filesystem write the read-only API must never trigger merely by being
imported.

This module performs NO filesystem writes, no logging initialization, no
subprocess call, no exchange import, and no runtime initialization. It
only computes two `Path` values, optionally overridden by environment
variables — mirroring (but never importing) the producer's own
`OPERATOR_SNAPSHOT_PATH`/`OPERATOR_RUNTIME_MANIFEST_PATH` env var
contract.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_SNAPSHOT_PATH = Path(
    os.getenv("OPERATOR_SNAPSHOT_PATH", "databases/operator_snapshot.json")
)

DEFAULT_MANIFEST_PATH = Path(
    os.getenv(
        "OPERATOR_RUNTIME_MANIFEST_PATH",
        "databases/operator_runtime_manifest.json",
    )
)

__all__ = ["DEFAULT_SNAPSHOT_PATH", "DEFAULT_MANIFEST_PATH"]
