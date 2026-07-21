"""tools/regret_repository.py — accès canonique au dataset de regret (MC-001).

Embodiment du Measurement Contract MC-001 (docs/measurement_contracts/) et de
l'ADR-0018 : UN producteur officiel (observability/regret_scheduler.py →
databases/regret/regret_horizons_*.jsonl), UN horizon canonique, UNE définition.
Les consommateurs (CRI, dossier Go/No-Go, audit) lisent via cet accesseur —
JAMAIS un chemin de fichier en dur.

Invariant clé (leçon de la rupture de traçabilité du 2026-07-10, où l'ancien
producteur s'est tu 11 jours sans alarme) : le dataset canonique doit être FRAIS.
is_fresh() / freshness() transforment une panne silencieuse en alarme visible.
Lecture seule — aucune influence sur le moteur.
"""

from __future__ import annotations

import glob
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DATASET_VERSION = "regret-v2"
CANONICAL_HORIZON = os.getenv("REGRET_CANONICAL_HORIZON", "1h")
REGRET_DIR = Path(os.getenv("REGRET_HORIZONS_DIR", "databases/regret"))
MAX_STALE_H = float(os.getenv("REGRET_MAX_STALE_H", "6"))


def _files() -> list[str]:
    return sorted(glob.glob(str(REGRET_DIR / "regret_horizons_*.jsonl")))


def read_canonical_regrets(
    since: Optional[datetime] = None, horizon: str = CANONICAL_HORIZON
) -> list[dict[str, Any]]:
    """Records de regret depuis `since`, normalisés au schéma consommateur :
    {ts_signal, score, regime, symbol, side, first_blocker, regret_type} où
    `regret_type` est le verdict à l'horizon canonique."""
    lo = since.timestamp() if since else None
    out: list[dict[str, Any]] = []
    for fp in _files():
        try:
            with open(fp, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = d.get("ts_signal")
                    if ts is None:
                        continue
                    ts = float(ts)
                    if lo is not None and ts < lo:
                        continue
                    h = (d.get("horizons") or {}).get(horizon) or {}
                    out.append(
                        {
                            "ts_signal": ts,
                            "score": d.get("score"),
                            "regime": d.get("regime"),
                            "symbol": d.get("symbol"),
                            "side": d.get("side"),
                            "first_blocker": d.get("first_blocker"),
                            "regret_type": h.get("regret_type"),
                        }
                    )
        except FileNotFoundError:
            continue
    return out


def last_write_ts() -> Optional[float]:
    last: Optional[float] = None
    for fp in _files():
        try:
            m = os.path.getmtime(fp)
        except OSError:
            continue
        if last is None or m > last:
            last = m
    return last


def is_fresh(max_stale_h: float = MAX_STALE_H) -> bool:
    lw = last_write_ts()
    return lw is not None and (time.time() - lw) <= max_stale_h * 3600.0


def freshness() -> dict[str, Any]:
    lw = last_write_ts()
    return {
        "dataset_version": DATASET_VERSION,
        "canonical_horizon": CANONICAL_HORIZON,
        "source_dir": str(REGRET_DIR),
        "last_write_utc": (
            datetime.fromtimestamp(lw, timezone.utc).isoformat() if lw else None
        ),
        "fresh": is_fresh(),
        "max_stale_h": MAX_STALE_H,
    }
