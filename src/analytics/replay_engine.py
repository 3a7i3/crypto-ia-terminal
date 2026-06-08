"""
src/analytics/replay_engine.py — Vérificateur de cohérence temporelle du pipeline.

Prend un AlphaPipelineResult archivé + les trades d'origine,
re-exécute le pipeline avec les mêmes paramètres, compare les hashes.

Ce module ne recalcule pas un nouvel alpha.
Il ne modifie pas C2/C5.
Il ne produit aucune décision de trading.

Propriété : si integrity_pass == True, le pipeline est reproductible
à l'identique depuis (trades, params) → run_hash.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.analytics.alpha_pipeline import AlphaPipelineResult, run_alpha_pipeline
from src.domain.trade_event import TradeEvent


@dataclass(frozen=True)
class ReplayResult:
    integrity_pass: bool  # run_hash recomputed == original.run_hash
    fingerprint_match: bool  # dataset fingerprint inchangé
    c1_is_count: int
    c1_oos_count: int
    bootstrap_ci: tuple[float, float]
    p_value: float
    alpha_significant: bool
    recomputed_run_hash: str  # pour audit diff externe


def replay_run(
    original: AlphaPipelineResult,
    trades: list[TradeEvent],
) -> ReplayResult:
    """
    Rejoue le pipeline avec les paramètres de `original` sur les `trades` fournis.

    Cas nominal : trades identiques → integrity_pass = True.
    Cas dérive  : trades modifiés  → fingerprint_match = False, integrity_pass = False.
    """
    recomputed = run_alpha_pipeline(
        trades,
        is_ratio=original.is_ratio,
        n_resamples=original.n_resamples,
        alpha_level=original.alpha_level,
        seed=original.seed,
    )

    return ReplayResult(
        integrity_pass=recomputed.run_hash == original.run_hash,
        fingerprint_match=recomputed.dataset_fingerprint
        == original.dataset_fingerprint,
        c1_is_count=recomputed.split_metadata.n_is,
        c1_oos_count=recomputed.split_metadata.n_oos,
        bootstrap_ci=(
            recomputed.bootstrap_result.ci_low,
            recomputed.bootstrap_result.ci_high,
        ),
        p_value=recomputed.bootstrap_result.p_value,
        alpha_significant=recomputed.alpha_significant,
        recomputed_run_hash=recomputed.run_hash,
    )
