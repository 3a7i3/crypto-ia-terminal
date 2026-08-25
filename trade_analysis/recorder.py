"""
trade_analysis/recorder.py — Enregistrement JSONL des observations LMI.

Ecrit les PressureField dans des fichiers JSONL compresses
pour analyse scientifique ulterieure.

Suit le pattern de observation/market_observer.py :
  - Repertoire dedie (databases/trade_analysis/)
  - Fichiers journaliers compresses (.jsonl.gz)
  - Garde-fou disque
  - Rotation automatique

Strictement passif (ADR-0007).
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from trade_analysis.models import PressureField

DEFAULT_DIR = "databases/trade_analysis"
MIN_FREE_DISK_GB = 1.5
RETENTION_DAYS = 45


class LMIRecorder:
    """Enregistre les PressureField en JSONL compresse."""

    def __init__(
        self,
        output_dir: str | None = None,
        min_free_disk_gb: float = MIN_FREE_DISK_GB,
        retention_days: int = RETENTION_DAYS,
    ) -> None:
        self.output_dir = Path(
            output_dir or os.getenv("LMI_DIR", DEFAULT_DIR)
        )
        self.min_free_disk_gb = min_free_disk_gb
        self.retention_days = retention_days
        self._current_date: str = ""
        self._file = None
        self._records_written: int = 0

    def record(self, pf: PressureField) -> bool:
        if not self._check_disk():
            return False

        date_str = datetime.fromtimestamp(
            pf.timestamp_ms / 1000.0, tz=timezone.utc
        ).strftime("%Y-%m-%d")

        if date_str != self._current_date:
            self._rotate(date_str)

        line = json.dumps(pf.as_dict(), separators=(",", ":")) + "\n"
        self._file.write(line.encode("utf-8"))
        self._records_written += 1
        return True

    def flush(self) -> None:
        if self._file:
            self._file.flush()

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
        self._current_date = ""

    def purge_old(self) -> int:
        if not self.output_dir.exists():
            return 0
        cutoff = datetime.now(timezone.utc).timestamp() - (
            self.retention_days * 86400
        )
        removed = 0
        for f in self.output_dir.glob("lmi_*.jsonl.gz"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        return removed

    def _rotate(self, date_str: str) -> None:
        self.close()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"lmi_{date_str}.jsonl.gz"
        self._file = gzip.open(path, "ab")
        self._current_date = date_str

    def _check_disk(self) -> bool:
        try:
            usage = shutil.disk_usage(self.output_dir.parent)
            free_gb = usage.free / (1024**3)
            return free_gb >= self.min_free_disk_gb
        except OSError:
            return True

    @property
    def records_written(self) -> int:
        return self._records_written

    def __enter__(self) -> "LMIRecorder":
        return self

    def __exit__(self, *args) -> None:
        self.close()
