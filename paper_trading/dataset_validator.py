"""
paper_trading/dataset_validator.py — Invariant checker pour le corpus expérimental.

Joue le même rôle que les invariants Z3 pour la gouvernance,
mais appliqué au dataset : garantit que chaque événement JSONL
est scientifiquement exploitable.

Deux niveaux de diagnostic :
    violation — l'invariant est cassé, la donnée est peu fiable
    warning   — anomalie douce, la donnée est suspecte mais utilisable

Usage :
    from paper_trading.dataset_validator import DatasetValidator, validate_log

    # Valider un seul événement à l'écriture
    result = DatasetValidator().validate_event(event)
    if not result.valid:
        log.warning("Dataset integrity: %s", result.violations)

    # Audit complet du JSONL
    result = validate_log()
    result.report()
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

from paper_trading.recorder import (
    DecisionContext,
    MarketContext,
    PaperTradeRecorder,
    TradeEvent,
)

_DEFAULT_PATH = os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl")

_VALID_SCHEMA_VERSIONS = frozenset({1, 2})
_VALID_CONVICTION_LEVELS = frozenset({"NONE", "LOW", "MEDIUM", "HIGH", "EXTREME"})

# Bornes de plausibilité pour les variables de marché
_MARKET_BOUNDS: dict[str, tuple[float, float]] = {
    "rsi": (0.0, 100.0),
    "atr": (0.0, math.inf),
    "atr_ratio": (0.0, math.inf),
    "volume_ratio": (0.0, math.inf),
    "bb_pct": (-0.5, 1.5),  # peut légèrement dépasser en marché extrême
    "range_pos": (0.0, 1.0),
    "trend_strength": (0.0, 1.0),
}

# Plages générant un warning (anormalement élevé, non fatal)
_MARKET_SOFT_BOUNDS: dict[str, tuple[float, float]] = {
    "volume_ratio": (0.0, 50.0),
    "atr_ratio": (0.0, 0.20),
}

_FLOAT_MARKET_FIELDS = (
    "momentum",
    "realized_volatility",
    "trend_strength",
    "avg_volume",
    "volume_ratio",
    "atr",
    "atr_ratio",
    "rsi",
    "ema20",
    "ema50",
    "ema_cross",
    "macd_line",
    "macd_signal",
    "macd_hist",
    "bb_pct",
    "vwap_dist",
    "range_pos",
    "ob_imbalance",
    "funding_rate",
    "micro_spread_bps",
)


@dataclass
class ValidationResult:
    """Résultat d'une validation d'événement ou de batch."""

    valid: bool
    violations: list[str] = field(default_factory=list)  # invariant cassé
    warnings: list[str] = field(default_factory=list)  # anomalie douce

    def report(self) -> str:
        """Résumé lisible pour logs ou Telegram."""
        lines = [f"DatasetValidator — {'OK' if self.valid else 'VIOLATIONS'}"]
        if self.violations:
            lines.append(f"  Violations ({len(self.violations)}):")
            for v in self.violations:
                lines.append(f"    ✗ {v}")
        if self.warnings:
            lines.append(f"  Warnings ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"    ⚠ {w}")
        if self.valid and not self.warnings:
            lines.append("  ✓ Tous les invariants respectés")
        return "\n".join(lines)

    def __add__(self, other: "ValidationResult") -> "ValidationResult":
        """Fusion de deux résultats (pour batch)."""
        return ValidationResult(
            valid=self.valid and other.valid,
            violations=self.violations + other.violations,
            warnings=self.warnings + other.warnings,
        )


class DatasetValidator:
    """
    Vérifie les invariants d'intégrité scientifique sur les TradeEvent.

    Invariants vérifiés :
      - schema_version valide
      - market_context présent pour les events v2 OPEN
      - absence de NaN dans tous les champs float
      - plages de valeurs plausibles (RSI, ATR, bb_pct, range_pos…)
      - conviction_level dans l'enum attendu
      - cohérence DecisionContext ↔ champs legacy (score, regime)
    """

    def validate_event(self, event: TradeEvent) -> ValidationResult:
        violations: list[str] = []
        warnings: list[str] = []

        _check_schema_version(event, violations)
        _check_v2_completeness(event, violations)
        _check_core_fields(event, violations)

        if event.market_context is not None:
            mc_v, mc_w = _check_market_context(event.market_context)
            violations.extend(mc_v)
            warnings.extend(mc_w)

        if event.decision_context is not None:
            dc_v, dc_w = _check_decision_context(event.decision_context, event)
            violations.extend(dc_v)
            warnings.extend(dc_w)

        return ValidationResult(
            valid=not violations, violations=violations, warnings=warnings
        )

    def validate_batch(self, events: list[TradeEvent]) -> ValidationResult:
        """Valide une liste d'événements, préfixe chaque message par trade_id/event."""
        result = ValidationResult(valid=True)
        for evt in events:
            r = self.validate_event(evt)
            prefix = f"[{evt.trade_id}/{evt.event}]"
            result.violations.extend(f"{prefix} {v}" for v in r.violations)
            result.warnings.extend(f"{prefix} {w}" for w in r.warnings)
            if not r.valid:
                result.valid = False
        return result


# ── Fonctions de validation internes ─────────────────────────────────────────


def _check_schema_version(evt: TradeEvent, violations: list[str]) -> None:
    if evt.schema_version not in _VALID_SCHEMA_VERSIONS:
        violations.append(
            f"schema_version={evt.schema_version} inconnu "
            f"(attendu: {sorted(_VALID_SCHEMA_VERSIONS)})"
        )


def _check_v2_completeness(evt: TradeEvent, violations: list[str]) -> None:
    if evt.schema_version >= 2 and evt.event == "OPEN":
        if evt.market_context is None:
            violations.append("schema_version=2 mais market_context absent")
        if evt.decision_context is None:
            violations.append("schema_version=2 mais decision_context absent")


def _check_core_fields(evt: TradeEvent, violations: list[str]) -> None:
    for fname in ("price", "size_usd"):
        val = getattr(evt, fname, None)
        if val is not None and isinstance(val, float) and math.isnan(val):
            violations.append(f"{fname}=NaN")


def _check_market_context(
    mc: MarketContext,
) -> tuple[list[str], list[str]]:
    violations: list[str] = []
    warnings: list[str] = []
    prefix = "market_context"

    # NaN sur tous les champs float
    for fname in _FLOAT_MARKET_FIELDS:
        val = getattr(mc, fname, None)
        if val is not None and isinstance(val, float) and math.isnan(val):
            violations.append(f"{prefix}.{fname}=NaN")

    # Bornes strictes
    for fname, (lo, hi) in _MARKET_BOUNDS.items():
        val = getattr(mc, fname, None)
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        if hi == math.inf:
            if val < lo:
                violations.append(f"{prefix}.{fname}={val:.4g} < {lo} (négatif)")
        else:
            if not (lo <= val <= hi):
                violations.append(f"{prefix}.{fname}={val:.4g} hors [{lo}, {hi}]")

    # Bornes souples (warning)
    for fname, (lo, hi) in _MARKET_SOFT_BOUNDS.items():
        val = getattr(mc, fname, None)
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        if not (lo <= val <= hi):
            warnings.append(
                f"{prefix}.{fname}={val:.4g} inhabituel (plage normale [{lo}, {hi}])"
            )

    return violations, warnings


def _check_decision_context(
    dc: DecisionContext, evt: TradeEvent
) -> tuple[list[str], list[str]]:
    violations: list[str] = []
    warnings: list[str] = []
    prefix = "decision_context"

    # conviction_level dans l'enum
    if dc.conviction_level is not None:
        if dc.conviction_level not in _VALID_CONVICTION_LEVELS:
            violations.append(
                f"{prefix}.conviction_level={dc.conviction_level!r} inconnu "
                f"(attendu: {sorted(_VALID_CONVICTION_LEVELS)})"
            )

    # NaN
    if dc.score is not None and isinstance(dc.score, float) and math.isnan(dc.score):
        violations.append(f"{prefix}.score=NaN")
    if (
        dc.conviction_value is not None
        and isinstance(dc.conviction_value, float)
        and math.isnan(dc.conviction_value)
    ):
        violations.append(f"{prefix}.conviction_value=NaN")

    # conviction_value ≥ 0
    if dc.conviction_value is not None and not math.isnan(dc.conviction_value):
        if dc.conviction_value < 0:
            warnings.append(
                f"{prefix}.conviction_value={dc.conviction_value:.4g} négatif"
            )

    # Cohérence regime legacy ↔ DecisionContext
    if dc.regime and evt.regime and dc.regime != evt.regime:
        warnings.append(
            f"{prefix}.regime={dc.regime!r} ≠ event.regime={evt.regime!r} "
            f"(incohérence v1→v2)"
        )

    # Cohérence score legacy ↔ DecisionContext (tolérance ±1 pour les arrondis int/float)
    if dc.score is not None and evt.score and not math.isnan(dc.score):
        if abs(dc.score - evt.score) > 1.0:
            warnings.append(
                f"{prefix}.score={dc.score} ≠ event.score={evt.score} "
                f"(delta={abs(dc.score - evt.score):.2f})"
            )

    return violations, warnings


# ── Audit de fichier complet ──────────────────────────────────────────────────


def validate_log(log_path: str = _DEFAULT_PATH) -> ValidationResult:
    """Valide l'intégralité du fichier JSONL paper_trades."""
    recorder = PaperTradeRecorder(log_path)
    events = recorder.events()
    if not events:
        return ValidationResult(
            valid=True, warnings=["Aucun événement dans le fichier"]
        )
    return DatasetValidator().validate_batch(events)
