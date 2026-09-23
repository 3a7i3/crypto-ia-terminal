"""FIN-02 closed-schema read-only financial reconciliation reader."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from observability.financial_paths import (
    DEFAULT_FINANCIAL_RECONCILIATION_PATH,
)


DEFAULT_FINANCIAL_RECONCILIATION_STALE_AFTER_S = 90.0

_TOP_KEYS = {
    "schema_version",
    "product",
    "domain",
    "authority",
    "generated_at_utc",
    "reconciliation_id",
    "paper_epoch_id",
    "financial_snapshot_id",
    "reconciliation_code_sha",
    "source_stream_digest",
    "last_source_sequence",
    "fin_schema_version",
    "fin_code_sha",
    "source_code_sha",
    "config_hash",
    "financial_model",
    "asset",
    "financial",
    "reconciliation",
    "sources",
    "records",
}
_FINANCIAL_KEYS = {
    "initial_epoch_capital",
    "cash_available",
    "capital_reserved",
    "capital_deployed",
    "capital_unresolved",
    "gross_realized_price_pnl",
    "fees_paid",
    "funding_net",
    "funding_status",
    "funding_evidence_ref",
    "realized_pnl",
    "known_unrealized_pnl",
    "unrealized_pnl",
    "certified_equity",
    "evidence_status",
    "reconciliation_status",
    "valuation_as_of",
    "valuation_statuses",
    "open_position_count",
    "settled_position_count",
    "unresolved_position_count",
}
_RECONCILIATION_KEYS = {
    "overall_status",
    "as_of",
    "unresolved_capital",
    "unreconciled_capital",
    "policy",
    "ppl_observation_digest",
    "simulator_observation_digest",
    "external_observation_digest",
}
_POLICY_KEYS = {
    "absolute_tolerance",
    "relative_tolerance",
    "stale_after_s",
}
_SOURCE_KEYS = {"ppl", "simulator", "external"}
_RECORD_KEYS = {
    "record_id",
    "source_kind",
    "source_id",
    "field",
    "projected_value",
    "observed_value",
    "delta_observed_minus_projected",
    "unreconciled_amount",
    "status",
    "comparability",
    "freshness",
    "observed_at",
    "projected_provenance",
    "observed_provenance",
    "note",
}

_RECON_STATUSES = {
    "EXACT",
    "WITHIN_TOLERANCE",
    "DIVERGENT",
    "UNRESOLVED",
}
_EVIDENCE_STATUSES = {
    "COMPLETE",
    "PARTIAL",
    "UNRESOLVED",
    "NOT_APPLICABLE",
}
_VALUATION_STATUSES = {"LIVE", "STALE", "UNAVAILABLE"}
_COMPARABILITY = {
    "COMPARABLE",
    "NON_COMPARABLE",
    "UNAVAILABLE",
    "NOT_APPLICABLE",
}
_FRESHNESS = {"LIVE", "STALE", "UNAVAILABLE", "NOT_APPLICABLE"}
_SOURCE_KINDS = {"PPL", "SIMULATOR", "EXCHANGE_READ_ONLY"}


@dataclass(frozen=True)
class FinancialReconciliationReadResult:
    ok: bool
    snapshot: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    snapshot_age_s: Optional[float] = None
    freshness_classification: Optional[str] = None


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value}")


def _parse_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _decimal_text(value: Any, *, nullable: bool = False) -> bool:
    if value is None:
        return nullable
    if not isinstance(value, str) or not value:
        return False
    try:
        number = float(value)
    except ValueError:
        return False
    return math.isfinite(number)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _nonnegative_int(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def _valid_financial(doc: Any) -> bool:
    if not isinstance(doc, dict) or set(doc) != _FINANCIAL_KEYS:
        return False
    for name in (
        "initial_epoch_capital",
        "cash_available",
        "capital_reserved",
        "capital_deployed",
        "capital_unresolved",
        "gross_realized_price_pnl",
        "fees_paid",
        "known_unrealized_pnl",
        "valuation_as_of",
    ):
        if not _decimal_text(doc[name]):
            return False
    for name in (
        "funding_net",
        "realized_pnl",
        "unrealized_pnl",
        "certified_equity",
    ):
        if not _decimal_text(doc[name], nullable=True):
            return False
    if doc["funding_status"] not in _EVIDENCE_STATUSES:
        return False
    if doc["evidence_status"] not in _EVIDENCE_STATUSES:
        return False
    if doc["reconciliation_status"] not in _RECON_STATUSES:
        return False
    if doc["funding_evidence_ref"] is not None and not _nonempty(
        doc["funding_evidence_ref"]
    ):
        return False
    statuses = doc["valuation_statuses"]
    if not isinstance(statuses, list) or any(
        status not in _VALUATION_STATUSES for status in statuses
    ):
        return False
    for name in (
        "open_position_count",
        "settled_position_count",
        "unresolved_position_count",
    ):
        if not _nonnegative_int(doc[name]):
            return False
    return len(statuses) == doc["open_position_count"]


def _valid_reconciliation(doc: Any) -> bool:
    if not isinstance(doc, dict) or set(doc) != _RECONCILIATION_KEYS:
        return False
    if doc["overall_status"] not in _RECON_STATUSES:
        return False
    if not _decimal_text(doc["as_of"]):
        return False
    if not _decimal_text(doc["unresolved_capital"]):
        return False
    if not _decimal_text(doc["unreconciled_capital"], nullable=True):
        return False
    policy = doc["policy"]
    if not isinstance(policy, dict) or set(policy) != _POLICY_KEYS:
        return False
    if any(not _decimal_text(policy[name]) for name in _POLICY_KEYS):
        return False
    if not _nonempty(doc["ppl_observation_digest"]):
        return False
    for name in (
        "simulator_observation_digest",
        "external_observation_digest",
    ):
        if doc[name] is not None and not _nonempty(doc[name]):
            return False
    return True


def _valid_sources(doc: Any) -> bool:
    if not isinstance(doc, dict) or set(doc) != _SOURCE_KEYS:
        return False
    ppl = doc["ppl"]
    if not isinstance(ppl, dict):
        return False
    for name in (
        "paper_epoch_id",
        "source_stream_digest",
        "observed_at",
        "provenance",
    ):
        if not _nonempty(ppl.get(name)):
            return False
    if not _nonnegative_int(ppl.get("last_sequence")):
        return False
    for name in (
        "cash_available",
        "capital_reserved",
        "capital_unresolved",
        "lifecycle_realized_pnl",
        "fees_paid",
    ):
        if not _decimal_text(ppl.get(name)):
            return False
    for name in (
        "open_position_ids",
        "closed_trade_ids",
        "unresolved_position_ids",
    ):
        values = ppl.get(name)
        if (
            not isinstance(values, list)
            or any(not _nonempty(value) for value in values)
            or len(values) != len(set(values))
        ):
            return False

    simulator = doc["simulator"]
    if simulator is not None:
        if not isinstance(simulator, dict):
            return False
        if not _nonempty(simulator.get("source_id")):
            return False
        if not _decimal_text(simulator.get("observed_at")):
            return False
        if not _decimal_text(
            simulator.get("cash_available"), nullable=True
        ):
            return False
        if not _decimal_text(
            simulator.get("capital_reserved"), nullable=True
        ):
            return False
        ids = simulator.get("open_position_ids")
        if ids is not None and (
            not isinstance(ids, list)
            or any(not _nonempty(value) for value in ids)
            or len(ids) != len(set(ids))
        ):
            return False
        for name in (
            "lifecycle_transitions_in_flight",
            "pending_order_count",
        ):
            value = simulator.get(name)
            if value is not None and not _nonnegative_int(value):
                return False
        if not _nonempty(simulator.get("provenance")):
            return False

    external = doc["external"]
    if external is not None:
        if not isinstance(external, dict):
            return False
        for name in ("source_id", "observed_at", "asset", "provenance"):
            if not _nonempty(external.get(name)):
                return False
        for name in ("free_cash", "equity"):
            if not _decimal_text(external.get(name), nullable=True):
                return False
        if external.get("applicability") not in _FRESHNESS:
            return False
    return True


def _valid_record(row: Any) -> bool:
    if not isinstance(row, dict) or set(row) != _RECORD_KEYS:
        return False
    for name in (
        "record_id",
        "source_id",
        "field",
        "projected_provenance",
        "observed_provenance",
        "observed_at",
    ):
        if not _nonempty(row[name]):
            return False
    if row["source_kind"] not in _SOURCE_KINDS:
        return False
    if row["status"] not in _RECON_STATUSES:
        return False
    if row["comparability"] not in _COMPARABILITY:
        return False
    if row["freshness"] not in _FRESHNESS:
        return False
    for name in (
        "projected_value",
        "observed_value",
        "delta_observed_minus_projected",
        "unreconciled_amount",
    ):
        if not _decimal_text(row[name], nullable=True):
            return False
    if row["note"] is not None and not isinstance(row["note"], str):
        return False
    return True


def validate_financial_reconciliation_snapshot(doc: Any) -> bool:
    if not isinstance(doc, dict) or set(doc) != _TOP_KEYS:
        return False
    if doc["schema_version"] != "1.0.0":
        return False
    if doc["product"] != "FIN02FinancialCockpit":
        return False
    if doc["domain"] != "financial_reconciliation":
        return False
    if doc["authority"] != "FINANCIAL_OBSERVATION":
        return False
    if _parse_utc(doc["generated_at_utc"]) is None:
        return False
    for name in (
        "reconciliation_id",
        "paper_epoch_id",
        "financial_snapshot_id",
        "reconciliation_code_sha",
        "source_stream_digest",
        "fin_code_sha",
        "source_code_sha",
        "config_hash",
        "financial_model",
        "asset",
    ):
        if not _nonempty(doc[name]):
            return False
    if not _nonnegative_int(doc["last_source_sequence"]):
        return False
    if doc["last_source_sequence"] < 1:
        return False
    if not _nonnegative_int(doc["fin_schema_version"]):
        return False
    if doc["fin_schema_version"] < 1:
        return False
    if not _valid_financial(doc["financial"]):
        return False
    if not _valid_reconciliation(doc["reconciliation"]):
        return False
    if not _valid_sources(doc["sources"]):
        return False
    records = doc["records"]
    if not isinstance(records, list) or not all(
        _valid_record(row) for row in records
    ):
        return False
    ids = [row["record_id"] for row in records]
    if len(ids) != len(set(ids)):
        return False
    return True


class FinancialReconciliationSnapshotReader:
    def __init__(
        self,
        path: Path = DEFAULT_FINANCIAL_RECONCILIATION_PATH,
        *,
        stale_after_s: float = DEFAULT_FINANCIAL_RECONCILIATION_STALE_AFTER_S,
        now_fn=time.time,
    ) -> None:
        self._path = Path(path)
        self._stale_after_s = float(stale_after_s)
        self._now_fn = now_fn
        if (
            not math.isfinite(self._stale_after_s)
            or self._stale_after_s <= 0
        ):
            raise ValueError("stale_after_s must be finite and > 0")

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> FinancialReconciliationReadResult:
        if not self._path.exists():
            return FinancialReconciliationReadResult(
                ok=False,
                error_code="FINANCIAL_RECONCILIATION_SNAPSHOT_MISSING",
                error_message=(
                    f"Financial reconciliation snapshot not found: {self._path}"
                ),
            )
        if not self._path.is_file():
            return FinancialReconciliationReadResult(
                ok=False,
                error_code="FINANCIAL_RECONCILIATION_INVALID_PATH",
                error_message="Financial reconciliation path is not a regular file.",
            )
        try:
            doc = json.loads(
                self._path.read_text(encoding="utf-8"),
                parse_constant=_reject_json_constant,
            )
        except (OSError, UnicodeError) as exc:
            return FinancialReconciliationReadResult(
                ok=False,
                error_code="FINANCIAL_RECONCILIATION_UNREADABLE",
                error_message=str(exc),
            )
        except (json.JSONDecodeError, ValueError) as exc:
            return FinancialReconciliationReadResult(
                ok=False,
                error_code="FINANCIAL_RECONCILIATION_MALFORMED_JSON",
                error_message=str(exc),
            )

        if not validate_financial_reconciliation_snapshot(doc):
            return FinancialReconciliationReadResult(
                ok=False,
                error_code="FINANCIAL_RECONCILIATION_INVALID_SCHEMA",
                error_message=(
                    "Financial reconciliation snapshot failed the FIN-02 "
                    "closed schema contract."
                ),
            )

        generated = _parse_utc(doc["generated_at_utc"])
        assert generated is not None
        age = max(0.0, float(self._now_fn()) - generated.timestamp())
        freshness = "STALE" if age > self._stale_after_s else "FRESH"
        return FinancialReconciliationReadResult(
            ok=True,
            snapshot=dict(doc),
            snapshot_age_s=age,
            freshness_classification=freshness,
        )


__all__ = [
    "DEFAULT_FINANCIAL_RECONCILIATION_PATH",
    "DEFAULT_FINANCIAL_RECONCILIATION_STALE_AFTER_S",
    "FinancialReconciliationReadResult",
    "FinancialReconciliationSnapshotReader",
    "validate_financial_reconciliation_snapshot",
]
