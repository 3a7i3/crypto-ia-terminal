"""Datasets API — assembles DatasetsSnapshot from observer_cert_history.jsonl."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from visualization.api.models import DatasetCertification, DatasetsSnapshot

_ROOT = Path(__file__).resolve().parents[2]
_CERT_FILE = _ROOT / "databases" / "certifications" / "observer_cert_history.jsonl"


def _parse_dt(s: Optional[str]) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def load_datasets_snapshot() -> DatasetsSnapshot:
    certs: list[DatasetCertification] = []

    if _CERT_FILE.exists():
        for line in _CERT_FILE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                certs.append(
                    DatasetCertification(
                        certification_id=raw.get("certification_id", "?"),
                        generated_at=_parse_dt(raw.get("generated_at")),
                        level=raw.get("level", 0),
                        level_name=raw.get("level_name", "Unknown"),
                        iii=raw.get("iii", 0.0),
                        ocs=raw.get("ocs", 0.0),
                        n_live_passed=raw.get("iv_live_passed", 0),
                        n_live_failed=raw.get("iv_live_failed", 0),
                        n_decisions_production=raw.get("n_decisions_production", 0),
                        decision=raw.get("decision", ""),
                        checks=raw.get("checks", []),
                    )
                )
            except Exception:
                continue

    # Sorted newest first
    certs.sort(key=lambda c: c.generated_at, reverse=True)

    latest = certs[0] if certs else None

    return DatasetsSnapshot(
        ts=datetime.now(timezone.utc),
        certifications=certs,
        latest_level=latest.level if latest else 0,
        latest_iii=latest.iii if latest else 0.0,
        latest_ocs=latest.ocs if latest else 0.0,
    )
