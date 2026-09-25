"""RL-DIAG-01 factual performance attribution kernel.

The kernel is offline and side-effect free. It combines:
- authoritative factual PPL lifecycle facts from RL-REPLAY;
- the exact certified DecisionPacket optional component from RL-DATA.

It never fabricates market paths, rejected opportunities, close causes, fills,
or counterfactual PnL. Associations are descriptive only.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.decision_packet import DecisionPacket
from paper_trading.ledger_events import LedgerEventType
from research_replay import FactualReplayResult, replay_factual_dataset, validate_dataset


_DIAG_IDENTITY_SCHEMA = "rl-diag-01.run-identity.v1"
_DIAG_METHOD = "FACTUAL_PPL_PLUS_EXACT_PACKET_CONTEXT_V1"
_RUN_KIND = "FACTUAL_PERFORMANCE_ATTRIBUTION"
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_DEFAULT_DIAG_CONFIG: Mapping[str, Any] = {
    "schema_version": 1,
    "semantics_version": "RL_DIAG_01_A4_V1",
    "population": "POSITION_CLOSED_FOR_PERFORMANCE",
    "evidence_policy": "CERTIFIED_FACTS_ONLY",
    "statistical_strength": "DESCRIPTIVE_ONLY",
    "causal_claims": "FORBIDDEN",
}


class DiagnosticError(ValueError):
    """The factual diagnostic boundary cannot be established."""


@dataclass(frozen=True)
class FactualAttributionResult:
    diagnostic_run_id: str
    diagnostic_run_identity: Mapping[str, Any]
    diagnostic_config_hash: str
    upstream_research_run_id: str
    dataset_id: str
    source_boundary_id: str
    paper_epoch_id: str
    summary: Mapping[str, Any]
    trade_attribution: tuple[Mapping[str, Any], ...]
    categorical_attribution: Mapping[str, Any]
    numeric_context: Mapping[str, Any]
    concentration: Mapping[str, Any]
    limitations: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "diagnostic_run_id": self.diagnostic_run_id,
            "diagnostic_run_identity": dict(self.diagnostic_run_identity),
            "diagnostic_config_hash": self.diagnostic_config_hash,
            "upstream_research_run_id": self.upstream_research_run_id,
            "dataset_id": self.dataset_id,
            "source_boundary_id": self.source_boundary_id,
            "paper_epoch_id": self.paper_epoch_id,
            "summary": dict(self.summary),
            "trade_attribution": [dict(row) for row in self.trade_attribution],
            "categorical_attribution": dict(self.categorical_attribution),
            "numeric_context": dict(self.numeric_context),
            "concentration": dict(self.concentration),
            "limitations": dict(self.limitations),
        }


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DiagnosticError(f"canonical JSON serialization failed: {exc}") from exc


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require_sha40(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA40_RE.fullmatch(value):
        raise DiagnosticError(f"{field} must be a lowercase 40-char Git SHA")
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r}")


def _no_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def _load_jsonl_objects(path: Path) -> tuple[dict[str, Any], ...]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DiagnosticError(f"cannot read {path}: {exc}") from exc

    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(
                line,
                object_pairs_hook=_no_duplicate_keys,
                parse_constant=_reject_constant,
            )
        except (json.JSONDecodeError, ValueError, UnicodeError) as exc:
            raise DiagnosticError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise DiagnosticError(f"{path}:{line_number} must contain an object")
        rows.append(value)
    return tuple(rows)


def _finite(name: str, value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DiagnosticError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise DiagnosticError(f"{name} must be finite")
    return result


def _required_mapping(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise DiagnosticError(f"{key} must be an object")
    return value


def _required_list(parent: Mapping[str, Any], key: str) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise DiagnosticError(f"{key} must be a list")
    return value


def _required_string(parent: Mapping[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value:
        raise DiagnosticError(f"{key} must be a non-empty string")
    return value


def _load_packet_map(
    dataset_root: Path,
    *,
    expected_decision_ids: set[str],
    manifest: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], str]:
    components = manifest.get("components")
    if not isinstance(components, dict):
        raise DiagnosticError("dataset manifest components must be an object")
    component = components.get("decision_packets")
    if not isinstance(component, dict) or component.get("status") != "COMPLETE":
        raise DiagnosticError("DecisionPacket component must be COMPLETE for A4")

    digest = component.get("canonical_subset_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise DiagnosticError("DecisionPacket component digest is missing")

    rows = _load_jsonl_objects(dataset_root / "optional" / "decision_packets.jsonl")
    packet_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        packet_id = _required_string(row, "packet_id")
        if packet_id in packet_map:
            raise DiagnosticError(f"duplicate DecisionPacket packet_id {packet_id!r}")
        packet = DecisionPacket.from_dict(row)
        if packet.packet_id != packet_id:
            raise DiagnosticError("DecisionPacket reconstruction changed packet_id")
        if not packet.verify_chain():
            raise DiagnosticError(f"DecisionPacket hash chain invalid: {packet_id}")
        packet_map[packet_id] = row

    actual_ids = set(packet_map)
    if actual_ids != expected_decision_ids:
        missing = sorted(expected_decision_ids - actual_ids)
        extra = sorted(actual_ids - expected_decision_ids)
        raise DiagnosticError(
            f"DecisionPacket population mismatch: missing={missing}, extra={extra}"
        )
    return packet_map, digest


def _outcome(net_pnl: float) -> str:
    if net_pnl > 0:
        return "WIN"
    if net_pnl < 0:
        return "LOSS"
    return "FLAT"


def _reasoning_summary(packet: Mapping[str, Any]) -> dict[str, Any]:
    rows = _required_list(packet, "reasoning")
    by_category: dict[str, dict[str, Any]] = {}
    total_impact = 0.0
    nonzero = 0
    for item in rows:
        if not isinstance(item, dict):
            raise DiagnosticError("reasoning entry must be an object")
        category = str(item.get("category", "uncategorized"))
        impact = _finite("reasoning.confidence_impact", item.get("confidence_impact", 0.0))
        total_impact += impact
        if impact != 0:
            nonzero += 1
        bucket = by_category.setdefault(
            category,
            {"entry_count": 0, "confidence_impact_sum": 0.0},
        )
        bucket["entry_count"] += 1
        bucket["confidence_impact_sum"] += impact
    return {
        "entry_count": len(rows),
        "nonzero_impact_count": nonzero,
        "confidence_impact_sum": total_impact,
        "by_category": {
            key: by_category[key]
            for key in sorted(by_category)
        },
    }


def _trade_rows(
    replay: FactualReplayResult,
    *,
    packet_map: Mapping[str, Mapping[str, Any]],
    events: Sequence[Any],
) -> tuple[dict[str, Any], ...]:
    open_events = {
        event.trade_id: event
        for event in events
        if event.event_type is LedgerEventType.POSITION_OPENED
    }

    rows: list[dict[str, Any]] = []
    for life in replay.lifecycle:
        if life.resolution_status != "CLOSED":
            continue
        if (
            life.decision_id is None
            or life.exit_price is None
            or life.exit_fee is None
            or life.gross_pnl is None
            or life.net_realized_pnl is None
            or life.resolved_at is None
        ):
            raise DiagnosticError(f"closed lifecycle {life.trade_id!r} is incomplete")

        packet = packet_map.get(life.decision_id)
        if packet is None:
            raise DiagnosticError(f"missing DecisionPacket for {life.decision_id!r}")
        if packet.get("symbol") != life.symbol:
            raise DiagnosticError(f"symbol mismatch for {life.trade_id!r}")
        if packet.get("side") != life.side:
            raise DiagnosticError(f"side mismatch for {life.trade_id!r}")

        open_event = open_events.get(life.trade_id)
        if open_event is None:
            raise DiagnosticError(f"missing authoritative OPEN for {life.trade_id!r}")

        features = _required_mapping(packet, "features")
        metadata = _required_mapping(packet, "metadata")
        conviction_dimensions = _required_mapping(metadata, "conviction_dimensions")
        mtf_tfs = _required_mapping(metadata, "mtf_tfs")

        principal = _finite("principal", life.principal)
        gross_pnl = _finite("gross_pnl", life.gross_pnl)
        net_pnl = _finite("net_realized_pnl", life.net_realized_pnl)
        entry_fee = _finite("entry_fee", life.entry_fee)
        exit_fee = _finite("exit_fee", life.exit_fee)
        total_fees = entry_fee + exit_fee
        if principal <= 0:
            raise DiagnosticError("principal must be > 0")

        opened_at = _finite("opened_at", life.opened_at)
        resolved_at = _finite("resolved_at", life.resolved_at)
        holding_seconds = resolved_at - opened_at
        if holding_seconds < 0:
            raise DiagnosticError("resolved_at precedes opened_at")

        timeout_at = open_event.payload.get("timeout_at")
        recovery_until = open_event.payload.get("recovery_eligible_until")
        tp_price = open_event.payload.get("tp_price")
        sl_price = open_event.payload.get("sl_price")

        reasoning = _reasoning_summary(packet)

        row = {
            "trade_id": life.trade_id,
            "decision_id": life.decision_id,
            "symbol": life.symbol,
            "side": life.side,
            "outcome": _outcome(net_pnl),
            "ppl_principal_usd": principal,
            "opened_at": opened_at,
            "resolved_at": resolved_at,
            "holding_seconds": holding_seconds,
            "entry_price": _finite("entry_price", life.entry_price),
            "exit_price": _finite("exit_price", life.exit_price),
            "entry_fee_usd": entry_fee,
            "exit_fee_usd": exit_fee,
            "total_fees_usd": total_fees,
            "gross_pnl_usd": gross_pnl,
            "net_realized_pnl_usd": net_pnl,
            "gross_return_on_principal": gross_pnl / principal,
            "net_return_on_principal": net_pnl / principal,
            "fee_drag_on_principal": total_fees / principal,
            "tp_price": None if tp_price is None else _finite("tp_price", tp_price),
            "sl_price": None if sl_price is None else _finite("sl_price", sl_price),
            "timeout_at": None if timeout_at is None else _finite("timeout_at", timeout_at),
            "recovery_eligible_until": (
                None
                if recovery_until is None
                else _finite("recovery_eligible_until", recovery_until)
            ),
            "close_after_timeout": (
                None
                if timeout_at is None
                else resolved_at > _finite("timeout_at", timeout_at)
            ),
            "packet_regime": _required_string(packet, "regime"),
            "packet_conviction": _required_string(packet, "conviction"),
            "packet_confidence": _finite("confidence", packet.get("confidence")),
            "packet_confidence_raw": _finite(
                "confidence_raw", packet.get("confidence_raw")
            ),
            "packet_adjusted_confidence": _finite(
                "adjusted_confidence", packet.get("adjusted_confidence")
            ),
            "conviction_score": _finite(
                "metadata.conviction_score", metadata.get("conviction_score")
            ),
            "conviction_size_factor": _finite(
                "metadata.conviction_size_factor",
                metadata.get("conviction_size_factor"),
            ),
            "conviction_dim_signal": _finite(
                "conviction_dimensions.signal", conviction_dimensions.get("signal")
            ),
            "conviction_dim_mtf": _finite(
                "conviction_dimensions.mtf", conviction_dimensions.get("mtf")
            ),
            "conviction_dim_regime": _finite(
                "conviction_dimensions.regime", conviction_dimensions.get("regime")
            ),
            "features_mtf": _finite("features.mtf", features.get("mtf")),
            "features_mtf_strength": _finite(
                "features.mtf_strength", features.get("mtf_strength")
            ),
            "features_regime_score": _finite(
                "features.regime", features.get("regime")
            ),
            "packet_os_size_usd": _finite(
                "features.os_size_usd", features.get("os_size_usd")
            ),
            "pb_capital_available": _finite(
                "features.pb_capital_available", features.get("pb_capital_available")
            ),
            "pb_exposure_pct": _finite(
                "features.pb_exposure_pct", features.get("pb_exposure_pct")
            ),
            "pb_symbol_pct": _finite(
                "features.pb_symbol_pct", features.get("pb_symbol_pct")
            ),
            "reasoning_entry_count": reasoning["entry_count"],
            "reasoning_nonzero_impact_count": reasoning["nonzero_impact_count"],
            "reasoning_confidence_impact_sum": reasoning["confidence_impact_sum"],
            "reasoning_by_category": reasoning["by_category"],
            "mtf_tfs": {
                str(key): str(value)
                for key, value in sorted(mtf_tfs.items())
            },
        }
        rows.append(row)

    rows.sort(key=lambda row: (row["resolved_at"], row["trade_id"]))
    return tuple(rows)


def _profit_factor(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    positive = sum(float(row["net_realized_pnl_usd"]) for row in rows if float(row["net_realized_pnl_usd"]) > 0)
    negative_abs = abs(
        sum(float(row["net_realized_pnl_usd"]) for row in rows if float(row["net_realized_pnl_usd"]) < 0)
    )
    if not rows:
        return {"status": "NOT_AVAILABLE", "value": None, "n": 0}
    if negative_abs > 0:
        return {"status": "COMPLETE", "value": positive / negative_abs, "n": len(rows)}
    if positive > 0:
        return {"status": "POSITIVE_INFINITY", "value": None, "n": len(rows)}
    return {"status": "UNDEFINED_ZERO_DENOMINATOR", "value": None, "n": len(rows)}


def _group_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    wins = sum(1 for row in rows if row["outcome"] == "WIN")
    losses = sum(1 for row in rows if row["outcome"] == "LOSS")
    flats = n - wins - losses
    net = sum(float(row["net_realized_pnl_usd"]) for row in rows)
    gross = sum(float(row["gross_pnl_usd"]) for row in rows)
    fees = sum(float(row["total_fees_usd"]) for row in rows)
    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "flats": flats,
        "win_rate": None if n == 0 else wins / n,
        "net_realized_pnl_usd": net,
        "gross_pnl_usd": gross,
        "fees_usd": fees,
        "expectancy_usd": None if n == 0 else net / n,
        "profit_factor": _profit_factor(rows),
        "statistical_strength": "DESCRIPTIVE_ONLY",
    }


def _group_by(
    rows: Sequence[Mapping[str, Any]],
    *,
    field: str,
) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        key = str(row[field])
        grouped.setdefault(key, []).append(row)
    return {
        key: _group_summary(grouped[key])
        for key in sorted(grouped)
    }


def _group_mtf_signals(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    timeframes = sorted(
        {
            timeframe
            for row in rows
            for timeframe in row["mtf_tfs"]
        }
    )
    result: dict[str, Any] = {}
    for timeframe in timeframes:
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for row in rows:
            signal = str(row["mtf_tfs"].get(timeframe, "MISSING"))
            grouped.setdefault(signal, []).append(row)
        result[timeframe] = {
            key: _group_summary(grouped[key])
            for key in sorted(grouped)
        }
    return result


def _mean(values: Sequence[float]) -> float | None:
    return None if not values else sum(values) / len(values)


def _numeric_context(
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in fields:
        values = [_finite(field, row[field]) for row in rows]
        wins = [
            _finite(field, row[field])
            for row in rows
            if row["outcome"] == "WIN"
        ]
        losses = [
            _finite(field, row[field])
            for row in rows
            if row["outcome"] == "LOSS"
        ]
        flats = [
            _finite(field, row[field])
            for row in rows
            if row["outcome"] == "FLAT"
        ]
        result[field] = {
            "n": len(values),
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "mean": _mean(values),
            "winner_mean": _mean(wins),
            "loser_mean": _mean(losses),
            "flat_mean": _mean(flats),
            "statistical_strength": "DESCRIPTIVE_ONLY",
        }
    return result


def _concentration(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "status": "NOT_AVAILABLE",
            "reason": "no closed trades",
        }

    ordered = sorted(
        rows,
        key=lambda row: float(row["net_realized_pnl_usd"]),
        reverse=True,
    )
    abs_total = sum(abs(float(row["net_realized_pnl_usd"])) for row in rows)
    largest_abs = max(
        rows,
        key=lambda row: abs(float(row["net_realized_pnl_usd"])),
    )
    total_net = sum(float(row["net_realized_pnl_usd"]) for row in rows)
    leave_one_out = [
        total_net - float(row["net_realized_pnl_usd"])
        for row in rows
    ]
    return {
        "status": "COMPLETE",
        "statistical_strength": "DESCRIPTIVE_ONLY",
        "largest_winner": {
            "trade_id": ordered[0]["trade_id"],
            "symbol": ordered[0]["symbol"],
            "net_realized_pnl_usd": ordered[0]["net_realized_pnl_usd"],
        },
        "largest_loser": {
            "trade_id": ordered[-1]["trade_id"],
            "symbol": ordered[-1]["symbol"],
            "net_realized_pnl_usd": ordered[-1]["net_realized_pnl_usd"],
        },
        "largest_absolute_trade_share": (
            None
            if abs_total == 0
            else abs(float(largest_abs["net_realized_pnl_usd"])) / abs_total
        ),
        "leave_one_out_net_pnl_min_usd": min(leave_one_out),
        "leave_one_out_net_pnl_max_usd": max(leave_one_out),
    }


def diagnose_factual_dataset(
    dataset_root: str | Path,
    *,
    replay_code_sha: str,
    diag_code_sha: str,
    diag_config: Mapping[str, Any] | None = None,
) -> FactualAttributionResult:
    """Build deterministic descriptive performance attribution for one dataset."""

    replay_sha = _require_sha40(replay_code_sha, field="replay_code_sha")
    diag_sha = _require_sha40(diag_code_sha, field="diag_code_sha")
    dataset = validate_dataset(dataset_root)
    replay = replay_factual_dataset(
        dataset.root,
        replay_code_sha=replay_sha,
    )

    expected_ids = {
        life.decision_id
        for life in replay.lifecycle
        if life.decision_id is not None
    }
    if len(expected_ids) != len(replay.lifecycle):
        raise DiagnosticError("every factual OPEN lifecycle must have a decision_id")

    packet_map, packet_digest = _load_packet_map(
        dataset.root,
        expected_decision_ids=set(expected_ids),
        manifest=dataset.manifest,
    )
    trades = _trade_rows(
        replay,
        packet_map=packet_map,
        events=dataset.events,
    )

    net_sum = sum(float(row["net_realized_pnl_usd"]) for row in trades)
    fee_sum = sum(float(row["total_fees_usd"]) for row in trades)
    terminal_net = _finite("terminal.realized_pnl", replay.terminal_state["realized_pnl"])
    terminal_fees = _finite("terminal.fees_paid", replay.terminal_state["fees_paid"])
    if not math.isclose(net_sum, terminal_net, rel_tol=1e-12, abs_tol=1e-12):
        raise DiagnosticError(
            f"trade net PnL does not reconcile: trades={net_sum}, terminal={terminal_net}"
        )
    if not math.isclose(fee_sum, terminal_fees, rel_tol=1e-12, abs_tol=1e-12):
        raise DiagnosticError(
            f"trade fees do not reconcile: trades={fee_sum}, terminal={terminal_fees}"
        )

    summary = _group_summary(trades)
    summary.update(
        {
            "paper_epoch_id": replay.paper_epoch_id,
            "initial_virtual_capital": replay.terminal_state["initial_virtual_capital"],
            "terminal_realized_pnl_usd": terminal_net,
            "terminal_fees_paid_usd": terminal_fees,
            "pnl_reconciliation": "PASS",
            "fee_reconciliation": "PASS",
            "evidence_status": "COMPLETE",
            "statistical_strength": "LOW_SAMPLE_DESCRIPTIVE_ONLY",
        }
    )

    categorical = {
        "by_symbol": _group_by(trades, field="symbol"),
        "by_side": _group_by(trades, field="side"),
        "by_regime": _group_by(trades, field="packet_regime"),
        "by_conviction": _group_by(trades, field="packet_conviction"),
        "by_mtf_signal": _group_mtf_signals(trades),
    }

    numeric_fields = (
        "ppl_principal_usd",
        "holding_seconds",
        "packet_confidence",
        "packet_confidence_raw",
        "packet_adjusted_confidence",
        "conviction_score",
        "conviction_size_factor",
        "conviction_dim_signal",
        "conviction_dim_mtf",
        "conviction_dim_regime",
        "features_mtf",
        "features_mtf_strength",
        "features_regime_score",
        "packet_os_size_usd",
        "pb_capital_available",
        "pb_exposure_pct",
        "pb_symbol_pct",
        "reasoning_entry_count",
        "reasoning_nonzero_impact_count",
        "reasoning_confidence_impact_sum",
    )
    numeric = _numeric_context(trades, numeric_fields)

    concentration = _concentration(trades)

    config_doc = dict(_DEFAULT_DIAG_CONFIG if diag_config is None else diag_config)
    config_hash = _sha256(_canonical_json_bytes(config_doc))
    identity = {
        "identity_schema": _DIAG_IDENTITY_SCHEMA,
        "run_kind": _RUN_KIND,
        "dataset_id": replay.dataset_id,
        "source_boundary_id": replay.source_boundary_id,
        "paper_epoch_id": replay.paper_epoch_id,
        "upstream_research_run_id": replay.research_run_id,
        "research_replay_code_sha": replay_sha,
        "research_diag_code_sha": diag_sha,
        "diagnostic_method": _DIAG_METHOD,
        "diagnostic_config_hash": config_hash,
        "population": {
            "definition": "POSITION_CLOSED_FOR_PERFORMANCE",
            "closed_trade_count": len(trades),
            "decision_packet_component_sha256": packet_digest,
        },
    }
    diagnostic_run_id = _sha256(_canonical_json_bytes(identity))

    limitations = {
        "causal_inference": {
            "status": "NOT_AVAILABLE",
            "reason": "A4 reports descriptive associations only; N is small and no intervention design exists",
        },
        "mark_to_market": {
            "status": "NOT_AVAILABLE",
            "reason": "certified F00 v1 has no complete mark-price trajectory",
        },
        "mfe_mae_slippage_adverse_selection": {
            "status": "NOT_AVAILABLE",
            "reason": "required certified market-path/reference-quote evidence is absent",
        },
        "rejected_opportunity_cost": {
            "status": "NOT_AVAILABLE",
            "reason": "rejected opportunity population is not provenance-bound in RL-DATA v1",
        },
        "close_cause": {
            "status": "NOT_AVAILABLE",
            "reason": "authoritative POSITION_CLOSED does not carry a canonical close-cause field",
        },
        "packet_os_size_usd": {
            "status": "CONTEXT_ONLY",
            "reason": "OrderSizer output is kept distinct from authoritative PPL principal",
        },
    }

    return FactualAttributionResult(
        diagnostic_run_id=diagnostic_run_id,
        diagnostic_run_identity=identity,
        diagnostic_config_hash=config_hash,
        upstream_research_run_id=replay.research_run_id,
        dataset_id=replay.dataset_id,
        source_boundary_id=replay.source_boundary_id,
        paper_epoch_id=replay.paper_epoch_id,
        summary=summary,
        trade_attribution=trades,
        categorical_attribution=categorical,
        numeric_context=numeric,
        concentration=concentration,
        limitations=limitations,
    )
