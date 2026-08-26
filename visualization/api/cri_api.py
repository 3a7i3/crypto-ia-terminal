"""CRI API — read-only projection of the Calibration Readiness Index.

Wraps `tools/cri_calculator.py::compute_cri()` so clients (Telegram observer,
dashboards) never recompute the index or reimplement the clean-data filters.
The calculator stays the single source of truth for both the CRI formula and
the canonical dataset bound `CLEAN_DATA_SINCE_ACTIVE` (ADR-0017).

Strictly passive (ADR-0007): reads `paper_trades.jsonl` /
`regret_analysis.jsonl` through the canonical loader, computes nothing new,
writes nothing, and never feeds a decision.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from visualization.api.models import CriSnapshot

# Seuil constitutionnel — CLAUDE.md § Règle du statisticien
CRI_MIN = 90


def _empty(error: str) -> CriSnapshot:
    """Snapshot for an unmeasurable CRI — explicit absence, never a fake 0."""
    return CriSnapshot(
        ts=datetime.now(timezone.utc),
        cri=None,
        cri_min=CRI_MIN,
        gate_ready=False,
        n_clean=0,
        n_regrets_clean=0,
        clean_data_since="",
        validity="UNAVAILABLE",
        error=error,
    )


def load_cri_snapshot(
    trades_path: Optional[Path] = None,
    regret_path: Optional[Path] = None,
) -> CriSnapshot:
    """Compute the CRI via the canonical calculator and attach its provenance.

    Any failure (absent dataset, calculator import error) yields a snapshot
    with `cri=None` and `validity="UNAVAILABLE"` rather than an exception, so a
    read-only client cannot be taken down by a missing file.
    """
    try:
        from tools.cri_calculator import (
            compute_cri,
            default_trades_path,
            trades_provenance,
        )
    except Exception as exc:  # pragma: no cover - import guard
        return _empty(f"cri_calculator unavailable: {exc}")

    # An absent source is *not* a CRI of 0. compute_cri() reads a missing file
    # as an empty trade list and scores it 0.0, which reads downstream as
    # "measured, catastrophic" instead of "never measured" — the exact
    # confusion the statistician rule exists to prevent.
    source = trades_path or default_trades_path()
    if not Path(source).exists():
        return _empty(f"dataset absent: {source}")

    try:
        result = compute_cri(trades_path=trades_path, regret_path=regret_path)
    except Exception as exc:
        return _empty(f"compute_cri failed: {exc}")

    try:
        provenance = trades_provenance(trades_path)
    except Exception:
        # Provenance is auxiliary — a CRI without it is still reportable.
        provenance = {}

    cri = result.get("cri")
    n_clean = int(result.get("n_clean", 0))

    warnings = list(result.get("warnings", []))
    validity = str(result.get("validity", "UNKNOWN"))
    if n_clean == 0:
        # File present but every record filtered out — the index is arithmetically
        # defined and scientifically vacuous. Say so rather than reporting a bare 0.
        warnings.append(
            "N=0 après application des filtres canoniques — index sans signification"
        )
        validity = "PARTIAL"

    return CriSnapshot(
        ts=datetime.now(timezone.utc),
        cri=cri,
        cri_min=CRI_MIN,
        gate_ready=bool(result.get("gate_ready", False)),
        n_clean=n_clean,
        n_regrets_clean=int(result.get("n_regrets_clean", 0)),
        clean_data_since=str(result.get("clean_data_since", "")),
        sub_scores=dict(result.get("sub_scores", {})),
        weights=dict(result.get("weights", {})),
        validity=validity,
        regret_source=result.get("regret_source"),
        regret_fresh=result.get("regret_fresh"),
        regret_last_write=result.get("regret_last_write"),
        provenance=provenance,
        warnings=warnings,
    )
