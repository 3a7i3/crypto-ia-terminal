"""Scientific API — assembles ScientificSnapshot from certifications + dip.sqlite."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from visualization.api.models import ScientificSnapshot

_ROOT = Path(__file__).resolve().parents[2]
_CERT_FILE = _ROOT / "databases" / "certifications" / "observer_cert_history.jsonl"
_DIP_DB = _ROOT / "databases" / "dip" / "dip.sqlite"


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _load_latest_cert() -> dict:
    if not _CERT_FILE.exists():
        return {}
    lines = [
        ln for ln in _CERT_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    if not lines:
        return {}
    try:
        return json.loads(lines[-1])
    except Exception:
        return {}


def _dip_counts() -> tuple[int, int, int]:
    """Returns (n_knowledge, n_alerts_active, n_counterfactuals)."""
    if not _DIP_DB.exists():
        return 0, 0, 0
    try:
        conn = sqlite3.connect(str(_DIP_DB))
        n_k = conn.execute("SELECT COUNT(*) FROM dip_knowledge").fetchone()[0]
        n_a = conn.execute(
            "SELECT COUNT(*) FROM dip_alerts WHERE acknowledged=0"
        ).fetchone()[0]
        n_cf = conn.execute("SELECT COUNT(*) FROM dip_counterfactuals").fetchone()[0]
        conn.close()
        return n_k, n_a, n_cf
    except Exception:
        return 0, 0, 0


def load_scientific_snapshot() -> ScientificSnapshot:
    cert = _load_latest_cert()
    n_k, n_a, n_cf = _dip_counts()

    level = cert.get("level", 0)
    level_names = {
        0: "Uncertified",
        1: "Basic Instrumentation",
        2: "Certified Instrumentation",
        3: "Production Observer",
        4: "Scientific Observer",
    }

    checks = cert.get("checks", [])

    return ScientificSnapshot(
        ts=datetime.now(timezone.utc),
        certification_level=level,
        certification_name=cert.get("level_name", level_names.get(level, "Unknown")),
        iii=cert.get("iii", 0.0),
        ocs=cert.get("ocs", 0.0),
        n_decisions_production=cert.get("n_decisions_production", 0),
        n_knowledge_entries=n_k,
        n_alerts_active=n_a,
        n_counterfactuals=n_cf,
        last_cert_at=_parse_dt(cert.get("generated_at")),
        cert_decision=cert.get("decision", "No certification available"),
        checks=checks,
    )
