"""
src/analytics/alpha_pipeline.py — Pipeline auditable C1→C2→C5.

Encapsule le triangle analytique dans un résultat fingerprinted + hashé.
Propriétés :
  - dataset_fingerprint : empreinte déterministe de l'input (trade_ids × timestamps)
  - run_hash            : hash des paramètres + sorties statistiques (excl. timestamp)
  - computed_at         : UTC — métadonnée d'audit, non incluse dans le hash

Invariant : même trades + mêmes params → même run_hash, toujours.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.analytics.bootstrap_stability import BootstrapResult, run_bootstrap_stability
from src.analytics.is_oos_splitter import SplitMetadata, split_is_oos
from src.analytics.significance_gate import is_alpha_significant
from src.domain.trade_event import TradeEvent


@dataclass(frozen=True)
class AlphaPipelineResult:
    # ── Input fingerprint ──────────────────────────────────────────────────
    dataset_fingerprint: str  # sha256[:16] des trade_ids + closed_at triés
    n_trades_total: int

    # ── Paramètres du run ─────────────────────────────────────────────────
    is_ratio: float
    n_resamples: int
    alpha_level: float
    seed: Optional[int]

    # ── Sorties des stages ────────────────────────────────────────────────
    split_metadata: SplitMetadata
    bootstrap_result: BootstrapResult
    alpha_significant: bool

    # ── Audit ─────────────────────────────────────────────────────────────
    run_hash: str  # sha256[:16] de (fingerprint + params + outputs)
    computed_at: datetime = field(compare=False, hash=False)  # métadonnée, hors hash


def _dataset_fingerprint(trades: list[TradeEvent]) -> str:
    entries = sorted(f"{t.trade_id}:{t.closed_at.isoformat()}" for t in trades)
    return hashlib.sha256("|".join(entries).encode()).hexdigest()[:16]


def _compute_run_hash(fingerprint: str, params: dict, outputs: dict) -> str:
    payload = json.dumps(
        {"fp": fingerprint, "params": params, "outputs": outputs},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def run_alpha_pipeline(
    trades: list[TradeEvent],
    is_ratio: float = 0.6,
    n_resamples: int = 30,
    alpha_level: float = 0.05,
    seed: Optional[int] = None,
) -> AlphaPipelineResult:
    """
    Exécute C1→C2→C5 et retourne un résultat entièrement traçable.
    Entrée directe de BURNIN_CALIBRATION_V3 lorsque n_trades >= 100.
    """
    fingerprint = _dataset_fingerprint(trades)

    split = split_is_oos(trades, is_ratio=is_ratio)
    bootstrap = run_bootstrap_stability(
        split.is_trades,
        n_resamples=n_resamples,
        alpha=alpha_level,
        seed=seed,
    )
    significant = is_alpha_significant(bootstrap, split.is_trades)

    params = {
        "is_ratio": is_ratio,
        "n_resamples": n_resamples,
        "alpha_level": alpha_level,
        "seed": seed,
    }
    outputs = {
        "n_is": split.metadata.n_is,
        "n_oos": split.metadata.n_oos,
        "mean_expectancy": bootstrap.mean_expectancy,
        "ci_low": bootstrap.ci_low,
        "ci_high": bootstrap.ci_high,
        "p_value": bootstrap.p_value,
        "alpha_significant": significant,
    }

    return AlphaPipelineResult(
        dataset_fingerprint=fingerprint,
        n_trades_total=len(trades),
        is_ratio=is_ratio,
        n_resamples=n_resamples,
        alpha_level=alpha_level,
        seed=seed,
        split_metadata=split.metadata,
        bootstrap_result=bootstrap,
        alpha_significant=significant,
        run_hash=_compute_run_hash(fingerprint, params, outputs),
        computed_at=datetime.now(tz=timezone.utc),
    )
