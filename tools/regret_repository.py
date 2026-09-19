"""Accès canonique, passif et diagnostiquable au dataset ``regret-v2``.

Le contrat MC-001 expose des observations directionnelles endpoint. Il ne
constitue ni un PnL exécutable, ni une preuve de profit manqué. Les archives
``regret-v1`` ne sont jamais fusionnées implicitement avec ce dataset.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

DATASET_VERSION = "regret-v2"
CANONICAL_HORIZON = os.getenv("REGRET_CANONICAL_HORIZON", "1h")
REGRET_DIR = Path(os.getenv("REGRET_HORIZONS_DIR", "databases/regret"))
MAX_STALE_H = float(os.getenv("REGRET_MAX_STALE_H", "6"))


def _files(regret_dir: Optional[Path] = None) -> list[Path]:
    root = REGRET_DIR if regret_dir is None else Path(regret_dir)
    return sorted(root.glob("regret_horizons_*.jsonl"))


def _iter_lines(regret_dir: Optional[Path] = None) -> Iterable[tuple[Path, int, str]]:
    for path in _files(regret_dir):
        try:
            with open(path, encoding="utf-8") as stream:
                for line_no, line in enumerate(stream, start=1):
                    if line.strip():
                        yield path, line_no, line
        except OSError:
            continue


def _normalise_horizon(
    record: dict[str, Any], horizon: str
) -> Optional[dict[str, Any]]:
    """Normalise une preuve v2 incrémentale ou un ancien agrégat v2."""
    if record.get("record_type") == "HORIZON_EVIDENCE":
        if record.get("dataset_version") != DATASET_VERSION:
            return None
        if record.get("horizon") != horizon:
            return None
        result = record.get("result") if isinstance(record.get("result"), dict) else {}
        status = str(record.get("horizon_status") or "PENDING")
    else:
        # Compatibilité des agrégats produits par RegretScheduler v2 avant le
        # schema_version=2. Ce n'est jamais le schéma plat regret-v1.
        horizons = record.get("horizons")
        if not isinstance(horizons, dict) or horizon not in horizons:
            return None
        result = horizons.get(horizon)
        if not isinstance(result, dict):
            return None
        status = "EVALUATED"

    return {
        "dataset_version": DATASET_VERSION,
        "schema_version": record.get("schema_version", 1),
        "evidence_id": record.get("evidence_id")
        or f"{record.get('observation_id', '')}:{horizon}",
        "observation_id": record.get("observation_id"),
        "packet_id": record.get("packet_id", ""),
        "trace_id": record.get("trace_id", ""),
        "experiment_id": record.get("experiment_id"),
        "source_authority": record.get("source_authority"),
        "paper_epoch_id": record.get("paper_epoch_id"),
        "cycle": record.get("cycle"),
        "engine_version": record.get("engine_version", "unknown"),
        "ts_signal": record.get("ts_signal"),
        "ts_eval": record.get("ts_eval") or result.get("ts_eval"),
        "expected_eval_ts": record.get("expected_eval_ts")
        or result.get("expected_eval_ts"),
        "score": record.get("score"),
        "regime": record.get("regime"),
        "symbol": record.get("symbol"),
        "side": record.get("side"),
        "first_blocker": record.get("first_blocker"),
        "all_blockers": list(record.get("all_blockers") or []),
        "horizon": horizon,
        "horizon_status": status,
        "status_reason": record.get("status_reason"),
        "regret_type": result.get("regret_type") if status == "EVALUATED" else None,
        "return_pct": result.get("return_pct"),
        "direction_ok": result.get("direction_ok"),
        "favorable_endpoint_pct": result.get(
            "favorable_endpoint_pct", result.get("mfe_pct")
        ),
        "adverse_endpoint_pct": result.get(
            "adverse_endpoint_pct", result.get("mae_pct")
        ),
        "price_at_signal": result.get("price_at_signal", record.get("price_at_signal")),
        "price_at_eval": result.get("price_at_eval"),
        "price_source": result.get("price_source", "unavailable_historical"),
        "price_observed_ts": result.get("price_observed_ts"),
        "price_age_s": result.get("price_age_s"),
        "eval_delay_s": result.get("eval_delay_s"),
        "metric_semantics": result.get("metric_semantics", "endpoint_only"),
        "classification_semantics": result.get(
            "classification_semantics",
            "directional_observation_not_executable_pnl",
        ),
    }


def read_canonical_observations(
    since: Optional[datetime] = None,
    horizon: str = CANONICAL_HORIZON,
    *,
    regret_dir: Optional[Path] = None,
    include_non_evaluated: bool = True,
) -> list[dict[str, Any]]:
    """Lit les preuves du seul horizon demandé avec déduplication déterministe."""
    lo = since.timestamp() if since else None
    by_id: dict[str, dict[str, Any]] = {}
    for _path, _line_no, line in _iter_lines(regret_dir):
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        row = _normalise_horizon(raw, horizon)
        if row is None:
            continue
        try:
            ts_signal = float(row["ts_signal"])
        except (TypeError, ValueError):
            continue
        if lo is not None and ts_signal < lo:
            continue
        row["ts_signal"] = ts_signal
        by_id.setdefault(str(row["evidence_id"]), row)
    rows = list(by_id.values())
    if not include_non_evaluated:
        rows = [r for r in rows if r["horizon_status"] == "EVALUATED"]
    return sorted(rows, key=lambda r: (r["ts_signal"], str(r["evidence_id"])))


def read_canonical_regrets(
    since: Optional[datetime] = None,
    horizon: str = CANONICAL_HORIZON,
    *,
    regret_dir: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Retourne uniquement les horizons évalués du contrat regret-v2."""
    return read_canonical_observations(
        since,
        horizon,
        regret_dir=regret_dir,
        include_non_evaluated=False,
    )


def diagnostics(
    horizon: str = CANONICAL_HORIZON, *, regret_dir: Optional[Path] = None
) -> dict[str, Any]:
    """Expose corruption, incomplétude et états terminaux sans les masquer."""
    invalid_json = invalid_record = 0
    observation_ids: set[str] = set()
    seen_horizons: dict[str, set[str]] = {}
    statuses: dict[str, int] = {}
    for _path, _line_no, line in _iter_lines(regret_dir):
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            invalid_json += 1
            continue
        if not isinstance(raw, dict) or not raw.get("observation_id"):
            invalid_record += 1
            continue
        obs_id = str(raw["observation_id"])
        observation_ids.add(obs_id)
        if raw.get("record_type") == "HORIZON_EVIDENCE":
            if raw.get("dataset_version") != DATASET_VERSION:
                invalid_record += 1
                continue
            h = raw.get("horizon")