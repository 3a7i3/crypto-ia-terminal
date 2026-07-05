"""
paper_trading/dataset_validator.py — Invariant checker pour le corpus expérimental.

Joue le même rôle que les invariants Z3 pour la gouvernance,
mais appliqué au dataset : garantit que chaque événement JSONL
est scientifiquement exploitable.

Deux niveaux de diagnostic :
    violation — l'invariant est cassé, la donnée est peu fiable
    warning   — anomalie douce, la donnée est suspecte mais utilisable

Usage :
    from paper_trading.dataset_validator import DatasetValidator, validate_log, validate_corpus

    # Valider un seul événement à l'écriture
    result = DatasetValidator().validate_event(event)
    if not result.valid:
        log.warning("Dataset integrity: %s", result.violations)

    # Audit complet du JSONL (événements individuels)
    result = validate_log()
    result.report()

    # Certification corpus complète (paires, stats population, burn-in eligibility)
    report = validate_corpus()
    print(report.report())
    if report.burnin_eligible:
        run_burnin()
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

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


# ── Validation corpus (population) ───────────────────────────────────────────

# Seuil à partir duquel un win_rate=1.0 est une violation (impossible statistiquement)
_WR_SAMPLE_THRESHOLD = 20


@dataclass
class CorpusReport:
    """Résultat de la certification du corpus de trades."""

    # Métriques brutes
    total_events: int = 0
    open_count: int = 0
    close_count: int = 0
    paired_trades: int = 0
    orphaned_opens: int = 0  # OPEN sans CLOSE correspondant
    orphaned_closes: int = 0  # CLOSE sans OPEN correspondant
    duplicate_trade_ids: int = 0
    expired_on_restore: int = 0  # clôturés via guard restauration

    # Statistiques population
    win_count: int = 0
    loss_count: int = 0
    tp_count: int = 0
    sl_count: int = 0
    win_rate: float = 0.0
    tp_rate: float = 0.0
    mean_duration_s: float = 0.0

    # Résultat certification
    integrity_pct: float = 0.0  # paired / (orphaned_opens + paired) * 100
    burnin_eligible: bool = False
    violations: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    certified_at: str = ""

    def report(self) -> str:
        status = "CERTIFIÉ" if self.burnin_eligible else "NON CERTIFIÉ"
        lines = [
            f"Trade Dataset Certification — {status}",
            f"{'─' * 45}",
            f"Événements total  : {self.total_events}",
            f"OPEN              : {self.open_count}",
            f"CLOSE             : {self.close_count}",
            f"Trades appariés   : {self.paired_trades}",
            f"Orphelins OPEN    : {self.orphaned_opens}",
            f"Orphelins CLOSE   : {self.orphaned_closes}",
            f"IDs dupliqués     : {self.duplicate_trade_ids}",
            f"Expirés restore   : {self.expired_on_restore}",
            f"{'─' * 45}",
            f"Win rate          : {self.win_rate:.1%}  (W={self.win_count} L={self.loss_count})",
            f"TP rate           : {self.tp_rate:.1%}  (TP={self.tp_count} SL={self.sl_count})",
            f"Durée moyenne     : {self.mean_duration_s:.0f}s",
            f"Intégrité         : {self.integrity_pct:.1f}%",
            f"{'─' * 45}",
            f"Burn-in eligible  : {'OUI' if self.burnin_eligible else 'NON'}",
        ]
        if self.violations:
            lines.append(f"Violations ({len(self.violations)}):")
            for v in self.violations:
                lines.append(f"  ✗ {v}")
        if self.warnings:
            lines.append(f"Warnings ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        if self.burnin_eligible and not self.warnings and not self.violations:
            lines.append("  ✓ Tous les invariants respectés")
        if self.certified_at:
            lines.append(f"Certifié le       : {self.certified_at}")
        return "\n".join(lines)

    def to_metadata(self) -> dict:
        """Format JSON pour paper_trades.metadata.json."""
        return {
            "schema_version": 1,
            "certified_at": self.certified_at,
            "burnin_eligible": self.burnin_eligible,
            "integrity_pct": round(self.integrity_pct, 2),
            "stats": {
                "total_events": self.total_events,
                "paired_trades": self.paired_trades,
                "orphaned_opens": self.orphaned_opens,
                "orphaned_closes": self.orphaned_closes,
                "duplicate_trade_ids": self.duplicate_trade_ids,
                "expired_on_restore": self.expired_on_restore,
                "win_rate": round(self.win_rate, 4),
                "tp_rate": round(self.tp_rate, 4),
                "mean_duration_s": round(self.mean_duration_s, 1),
            },
            "violations": self.violations,
            "warnings": self.warnings,
        }


def validate_corpus(log_path: str = _DEFAULT_PATH) -> CorpusReport:
    """
    Certification corpus : paires OPEN/CLOSE, doublons, statistiques population.

    Vérifie les invariants impossibles à détecter événement par événement :
      - Toute OPEN a exactement un CLOSE correspondant
      - Aucun trade_id dupliqué
      - Cohérence chronologique (open_ts < close_ts)
      - Win rate < 1.0 avec N suffisant (100% = données corrompues)
      - Au moins un SL déclenché dans la population
    """
    recorder = PaperTradeRecorder(log_path)
    events = recorder.events()
    report = CorpusReport(
        total_events=len(events),
        certified_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    if not events:
        report.warnings.append("Dataset vide — aucun trade à certifier")
        report.burnin_eligible = False
        return report

    # ── Comptage brut ────────────────────────────────────────────────────────
    opens: dict[str, object] = {}
    closes: dict[str, object] = {}
    seen_ids: set = set()

    for evt in events:
        if evt.event == "OPEN":
            report.open_count += 1
            if evt.trade_id in seen_ids:
                report.duplicate_trade_ids += 1
            else:
                seen_ids.add(evt.trade_id)
                opens[evt.trade_id] = evt
        elif evt.event == "CLOSE":
            report.close_count += 1
            closes[evt.trade_id] = evt

    # ── Paires & orphelins ───────────────────────────────────────────────────
    paired_ids = set(opens.keys()) & set(closes.keys())
    report.paired_trades = len(paired_ids)
    report.orphaned_opens = len(set(opens.keys()) - set(closes.keys()))
    report.orphaned_closes = len(set(closes.keys()) - set(opens.keys()))

    # ── Statistiques population (trades appariés uniquement) ─────────────────
    durations = []
    for tid in paired_ids:
        cl = closes[tid]
        op = opens[tid]

        reason = getattr(cl, "reason", "") or ""
        pnl = getattr(cl, "pnl_usd", 0.0) or 0.0
        dur = getattr(cl, "duration_s", None)

        if reason.lower() == "expired_on_restore":
            report.expired_on_restore += 1
            continue  # exclus des stats de trading

        if pnl > 0:
            report.win_count += 1
        else:
            report.loss_count += 1

        if "tp" in reason.lower():
            report.tp_count += 1
        elif "sl" in reason.lower():
            report.sl_count += 1

        # Cohérence chronologique
        open_ts = getattr(op, "ts", 0.0) or 0.0
        close_ts = getattr(cl, "ts", 0.0) or 0.0
        if open_ts > 0 and close_ts > 0 and close_ts < open_ts:
            report.violations.append(
                f"[{tid}] close_ts ({close_ts:.0f}) < open_ts ({open_ts:.0f})"
            )

        if dur is not None and dur >= 0:
            durations.append(dur)

    tradable = report.win_count + report.loss_count
    if tradable > 0:
        report.win_rate = report.win_count / tradable
        report.tp_rate = report.tp_count / tradable if tradable else 0.0
    if durations:
        report.mean_duration_s = sum(durations) / len(durations)

    # ── Intégrité globale ────────────────────────────────────────────────────
    total_opens = report.orphaned_opens + report.paired_trades
    report.integrity_pct = (
        report.paired_trades / total_opens * 100.0 if total_opens > 0 else 100.0
    )

    # ── Invariants corpus ────────────────────────────────────────────────────
    if report.duplicate_trade_ids > 0:
        report.violations.append(
            f"{report.duplicate_trade_ids} trade_id(s) dupliqué(s)"
        )

    if report.orphaned_opens > 0:
        report.violations.append(
            f"{report.orphaned_opens} OPEN sans CLOSE (positions fantômes)"
        )

    if report.orphaned_closes > 0:
        report.warnings.append(
            f"{report.orphaned_closes} CLOSE sans OPEN (VPS décalé ou restore partiel)"
        )

    if tradable >= _WR_SAMPLE_THRESHOLD and report.win_rate == 1.0:
        report.violations.append(
            f"win_rate=100% sur {tradable} trades — statistiquement impossible, "
            "données probablement corrompues (bug restore ?)"
        )

    if tradable >= _WR_SAMPLE_THRESHOLD and report.sl_count == 0:
        report.violations.append(
            f"Zéro SL déclenché sur {tradable} trades — indicateur de corruption "
            "(TP hardcodé ou restore immédiat)"
        )

    if report.expired_on_restore > 0:
        rate = report.expired_on_restore / max(1, report.paired_trades) * 100
        report.warnings.append(
            f"{report.expired_on_restore} trade(s) expiré(s) au restore "
            f"({rate:.0f}% du corpus) — exclus des stats"
        )

    if tradable > 0 and report.mean_duration_s < 10:
        report.warnings.append(
            f"Durée moyenne={report.mean_duration_s:.1f}s — trades très courts, "
            "probable fermeture immédiate post-restore"
        )

    # ── Décision burn-in ─────────────────────────────────────────────────────
    report.burnin_eligible = len(report.violations) == 0

    return report


def write_metadata(
    report: CorpusReport,
    metadata_path: str = "databases/paper_trades.metadata.json",
) -> None:
    """Écrit la certification dans databases/paper_trades.metadata.json."""
    p = Path(metadata_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(report.to_metadata(), f, indent=2, ensure_ascii=False)
        f.write("\n")
