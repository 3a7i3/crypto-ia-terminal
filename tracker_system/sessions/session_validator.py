from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tracker_system.sessions.schemas.session_schema import ALLOWED_REGIMES
from tracker_system.sessions.schemas.trade_schema import (
    MAX_POSITION_SIZE_USD,
    PNL_COHERENCE_TOLERANCE,
    REQUIRED_TRADE_FIELDS,
)


@dataclass
class ValidationResult:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.valid = False
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }


class SessionValidator:
    """Valide l'intégrité et la cohérence d'une session."""

    def validate_session(self, session_dir: Path) -> ValidationResult:
        result = ValidationResult()

        metadata_file = session_dir / "session_metadata.json"
        trades_file = session_dir / "trades.jsonl"
        config_file = session_dir / "config_snapshot.json"

        if not metadata_file.exists():
            result.fail("session_metadata.json manquant")
        if not config_file.exists():
            result.warn("config_snapshot.json manquant — reproductibilité compromise")
        if not trades_file.exists():
            result.warn("trades.jsonl manquant — session sans trades")
            return result

        trades = _load_trades_file(trades_file)
        if not trades:
            result.warn("Aucun trade dans la session")
            return result

        self._validate_trade_fields(trades, result)
        self._validate_timestamps(trades, result)
        self._validate_pnl_coherence(trades, result)
        self._validate_sizes(trades, result)
        self._validate_regimes(trades, result)

        return result

    def validate_trade(self, trade: dict) -> ValidationResult:
        """Valide un trade individuel avant enregistrement."""
        result = ValidationResult()
        self._check_required_fields([trade], result)
        self._validate_pnl_coherence([trade], result)
        self._validate_sizes([trade], result)
        self._validate_regimes([trade], result)
        return result

    def _validate_trade_fields(
        self, trades: list[dict], result: ValidationResult
    ) -> None:
        missing_counts: dict[str, int] = {}
        for trade in trades:
            for field_name in REQUIRED_TRADE_FIELDS:
                if field_name not in trade:
                    missing_counts[field_name] = missing_counts.get(field_name, 0) + 1
        for field_name, count in missing_counts.items():
            result.fail(f"Champ requis '{field_name}' absent dans {count} trade(s)")

    def _check_required_fields(
        self, trades: list[dict], result: ValidationResult
    ) -> None:
        self._validate_trade_fields(trades, result)

    def _validate_timestamps(
        self, trades: list[dict], result: ValidationResult
    ) -> None:
        timestamps = []
        for i, trade in enumerate(trades):
            ts = trade.get("timestamp")
            if ts is None:
                continue
            try:
                timestamps.append((i, str(ts)))
            except Exception:
                result.fail(f"Trade #{i} : timestamp illisible '{ts}'")

        # Check monotonic order (by string comparison — ISO format is lexicographically ordered)
        for i in range(1, len(timestamps)):
            idx_prev, ts_prev = timestamps[i - 1]
            idx_curr, ts_curr = timestamps[i]
            if ts_curr < ts_prev:
                result.fail(
                    f"Timestamps non-monotones : trade #{idx_prev} ({ts_prev}) > trade #{idx_curr} ({ts_curr})"
                )

    def _validate_pnl_coherence(
        self, trades: list[dict], result: ValidationResult
    ) -> None:
        for i, trade in enumerate(trades):
            entry = trade.get("entry_price")
            exit_ = trade.get("exit_price")
            pnl_usd = trade.get("pnl_usd")
            size = trade.get("size")

            if None in (entry, exit_, pnl_usd, size):
                continue

            try:
                side = trade.get("side", "long").lower()
                if side == "long":
                    calc_pnl = (float(exit_) - float(entry)) * float(size)
                else:
                    calc_pnl = (float(entry) - float(exit_)) * float(size)

                deviation = abs(calc_pnl - float(pnl_usd))
                tolerance = abs(float(pnl_usd)) * PNL_COHERENCE_TOLERANCE + 0.01
                if deviation > tolerance:
                    result.warn(
                        f"Trade #{i} : PnL déclaré {pnl_usd} ≠ calculé {calc_pnl:.4f} "
                        f"(écart {deviation:.4f})"
                    )
            except (TypeError, ValueError, ZeroDivisionError):
                pass

    def _validate_sizes(self, trades: list[dict], result: ValidationResult) -> None:
        for i, trade in enumerate(trades):
            size = trade.get("size")
            if size is None:
                continue
            try:
                s = float(size)
                if s <= 0:
                    result.fail(f"Trade #{i} : size <= 0 ({size})")
                elif s > MAX_POSITION_SIZE_USD:
                    result.warn(
                        f"Trade #{i} : size anormalement élevée ({size} > {MAX_POSITION_SIZE_USD})"
                    )
            except (TypeError, ValueError):
                result.fail(f"Trade #{i} : size non numérique ({size})")

    def _validate_regimes(self, trades: list[dict], result: ValidationResult) -> None:
        unknown_regimes: set[str] = set()
        for trade in trades:
            regime = trade.get("regime")
            if regime and regime not in ALLOWED_REGIMES:
                unknown_regimes.add(str(regime))
        if unknown_regimes:
            result.warn(
                f"Régimes non reconnus : {unknown_regimes} — ajouter à ALLOWED_REGIMES si intentionnel"
            )


def _load_trades_file(path: Path) -> list[dict]:
    trades = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                trades.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return trades
