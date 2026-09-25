"""RL-REPLAY-01 factual offline replay over immutable RL-DATA datasets.

This module is intentionally source-path explicit and side-effect free:
- no runtime/service discovery;
- no network;
- no PAPER/PPL durable-store construction;
- no writes;
- no counterfactual synthesis.

It validates one immutable RL-DATA dataset and replays its authoritative PPL
stream through the pure paper_portfolio_ledger.project() domain kernel.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from paper_trading.ledger_events import LedgerEvent, LedgerEventType
from paper_trading.paper_portfolio_ledger import PaperPortfolioState, project

_RUN_KIND = "FACTUAL_BASELINE"
_RUN_IDENTITY_SCHEMA = "rl-replay-01.run-identity.v1"
_REPLAY_METHOD = "PPL_PROJECT_FACTUAL_V1"
_DEFAULT_REPLAY_CONFIG = {
    "schema_version": 1,
    "metric_semantics_version": "RL_REPLAY_01_METRICS_V1",
    "population": "POSITION_CLOSED_FOR_PERFORMANCE",
    "drawdown": "REALIZED_CLOSE_TO_CLOSE",
    "financial_interpretation": "PPL_NATIVE",
    "counterfactual": "DISABLED",
}
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ReplayError(ValueError):
    """Base error for deterministic Research replay."""


class DatasetValidationError(ReplayError):
    """The immutable RL-DATA dataset failed validation."""


@dataclass(frozen=True)
class ValidatedDataset:
    root: Path
    manifest: Mapping[str, Any]
    events: tuple[LedgerEvent, ...]
    dataset_id: str
    source_boundary_id: str
    paper_epoch_id: str


@dataclass(frozen=True)
class LifecycleRecord:
    trade_id: str
    symbol: str
    side: str
    principal: float
    open_event_id: str
    open_sequence: int
    opened_at: float
    decision_id: str | None
    entry_price: float
    entry_fee: float
    resolution_status: str
    resolution_event_id: str | None
    resolution_sequence: int | None
    resolved_at: float | None
    exit_price: float | None
    exit_fee: float | None
    gross_pnl: float | None
    net_realized_pnl: float | None
    unresolved_reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "principal": self.principal,
            "open_event_id": self.open_event_id,
            "open_sequence": self.open_sequence,
            "opened_at": self.opened_at,
            "decision_id": self.decision_id,
            "entry_price": self.entry_price,
            "entry_fee": self.entry_fee,
            "resolution_status": self.resolution_status,
            "resolution_event_id": self.resolution_event_id,
            "resolution_sequence": self.resolution_sequence,
            "resolved_at": self.resolved_at,
            "exit_price": self.exit_price,
            "exit_fee": self.exit_fee,
            "gross_pnl": self.gross_pnl,
            "net_realized_pnl": self.net_realized_pnl,
            "unresolved_reason": self.unresolved_reason,
        }


@dataclass(frozen=True)
class FactualReplayResult:
    research_run_id: str
    research_run_identity: Mapping[str, Any]
    replay_config_hash: str
    dataset_id: str
    source_boundary_id: str
    paper_epoch_id: str
    terminal_state: Mapping[str, Any]
    lifecycle: tuple[LifecycleRecord, ...]
    metrics: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "research_run_id": self.research_run_id,
            "research_run_identity": dict(self.research_run_identity),
            "replay_config_hash": self.replay_config_hash,
            "dataset_id": self.dataset_id,
            "source_boundary_id": self.source_boundary_id,
            "paper_epoch_id": self.paper_epoch_id,
            "terminal_state": dict(self.terminal_state),
            "lifecycle": [record.as_dict() for record in self.lifecycle],
            "metrics": dict(self.metrics),
        }


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r}")


def _object_without_duplicate_keys(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def _strict_json_loads(raw: str, *, source: Path) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, ValueError, UnicodeError) as exc:
        raise DatasetValidationError(f"invalid JSON in {source}: {exc}") from exc


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
        raise ReplayError(f"canonical JSON serialization failed: {exc}") from exc


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_regular_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise DatasetValidationError(f"required regular file missing: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise DatasetValidationError(f"cannot read {path}: {exc}") from exc


def _require_sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise DatasetValidationError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def _require_sha40(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA40_RE.fullmatch(value):
        raise ReplayError(f"{field} must be a lowercase 40-char Git SHA")
    return value


def _load_manifest(root: Path) -> dict[str, Any]:
    raw = _read_regular_file(root / "manifest.json")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DatasetValidationError("manifest.json is not valid UTF-8") from exc
    value = _strict_json_loads(text, source=root / "manifest.json")
    if not isinstance(value, dict):
        raise DatasetValidationError("manifest.json must contain a JSON object")
    return value


def _validate_component(
    root: Path,
    manifest: Mapping[str, Any],
    *,
    component_name: str,
    relative_path: str,
    digest_field: str,
    required: bool = True,
) -> None:
    components = manifest.get("components")
    if not isinstance(components, dict):
        raise DatasetValidationError("manifest components must be a JSON object")
    component = components.get(component_name)
    if not isinstance(component, dict):
        if required:
            raise DatasetValidationError(f"missing component {component_name!r}")
        return

    status = component.get("status")
    path = root / relative_path
    if status != "COMPLETE":
        if required:
            raise DatasetValidationError(
                f"required component {component_name!r} is not COMPLETE: {status!r}"
            )
        if path.exists():
            raise DatasetValidationError(
                f"component {component_name!r} is {status!r} but file exists"
            )
        return

    expected = _require_sha256(
        component.get(digest_field),
        field=f"components.{component_name}.{digest_field}",
    )
    raw = _read_regular_file(path)
    actual = _sha256_bytes(raw)
    if actual != expected:
        raise DatasetValidationError(
            f"component digest mismatch for {component_name}: "
            f"expected={expected}, actual={actual}"
        )


def _decode_ppl_events(path: Path) -> tuple[LedgerEvent, ...]:
    raw = _read_regular_file(path)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DatasetValidationError(f"{path} is not valid UTF-8") from exc

    events: list[LedgerEvent] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        value = _strict_json_loads(line, source=path)
        if not isinstance(value, dict):
            raise DatasetValidationError(
                f"{path}:{line_number} must contain a JSON object"
            )
        try:
            event = LedgerEvent(
                event_id=value["event_id"],
                paper_epoch_id=value["paper_epoch_id"],
                sequence=value["sequence"],
                event_type=LedgerEventType(value["event_type"]),
                timestamp=value["timestamp"],
                trade_id=value.get("trade_id"),
                decision_id=value.get("decision_id"),
                payload=value["payload"],
                schema_version=value["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DatasetValidationError(
                f"invalid PPL event at {path}:{line_number}: {exc}"
            ) from exc
        events.append(event)

    if not events:
        raise DatasetValidationError("PPL event stream must not be empty")
    return tuple(events)


def validate_dataset(dataset_root: str | Path) -> ValidatedDataset:
    root = Path(dataset_root).resolve()
    if not root.is_dir():
        raise DatasetValidationError(f"dataset root is not a directory: {root}")

    manifest = _load_manifest(root)

    dataset_id = _require_sha256(manifest.get("dataset_id"), field="dataset_id")
    source_boundary_id = _require_sha256(
        manifest.get("source_boundary_id"), field="source_boundary_id"
    )
    if root.name != dataset_id:
        raise DatasetValidationError(
            f"dataset directory name {root.name!r} != dataset_id {dataset_id!r}"
        )
    if manifest.get("derivation") != "PAPER_EXPORT":
        raise DatasetValidationError("dataset derivation must be PAPER_EXPORT")
    if manifest.get("source_domain") != "PAPER":
        raise DatasetValidationError("dataset source_domain must be PAPER")
    if manifest.get("source_authority") != "PPL_AUTHORITY":
        raise DatasetValidationError(
            "dataset source_authority must be PPL_AUTHORITY"
        )

    boundary_doc = manifest.get("source_boundary_identity")
    if not isinstance(boundary_doc, dict):
        raise DatasetValidationError("source_boundary_identity must be an object")
    actual_boundary_id = _sha256_bytes(_canonical_json_bytes(boundary_doc))
    if actual_boundary_id != source_boundary_id:
        raise DatasetValidationError(
            "source_boundary_id does not match source_boundary_identity"
        )

    dataset_identity = manifest.get("dataset_identity")
    if not isinstance(dataset_identity, dict):
        raise DatasetValidationError("dataset_identity must be an object")
    if dataset_identity.get("source_boundary_id") != source_boundary_id:
        raise DatasetValidationError(
            "dataset_identity source_boundary_id mismatch"
        )
    actual_dataset_id = _sha256_bytes(_canonical_json_bytes(dataset_identity))
    if actual_dataset_id != dataset_id:
        raise DatasetValidationError("dataset_id does not match dataset_identity")

    _validate_component(
        root,
        manifest,
        component_name="ppl_events",
        relative_path="authoritative/ppl_events.jsonl",
        digest_field="sha256",
    )
    _validate_component(
        root,
        manifest,
        component_name="f00_experiment_manifest",
        relative_path="authoritative/f00_experiment_manifest.json",
        digest_field="sha256",
    )
    _validate_component(
        root,
        manifest,
        component_name="f00_experiment_config",
        relative_path="authoritative/f00_experiment_config.json",
        digest_field="sha256",
    )

    for component_name, relative_path in (
        ("decision_packets", "optional/decision_packets.jsonl"),
        ("decision_identity_records", "optional/decision_identity_records.jsonl"),
    ):
        component = manifest.get("components", {}).get(component_name)
        if not isinstance(component, dict):
            raise DatasetValidationError(
                f"missing optional component declaration {component_name!r}"
            )
        if component.get("status") == "COMPLETE":
            _validate_component(
                root,
                manifest,
                component_name=component_name,
                relative_path=relative_path,
                digest_field="canonical_subset_sha256",
                required=False,
            )
        elif (root / relative_path).exists():
            raise DatasetValidationError(
                f"{component_name} file exists despite non-COMPLETE status"
            )

    events = _decode_ppl_events(root / "authoritative/ppl_events.jsonl")
    ppl_component = manifest["components"]["ppl_events"]
    if len(events) != ppl_component.get("record_count"):
        raise DatasetValidationError(
            "decoded PPL event count does not match manifest component count"
        )

    try:
        terminal = project(events)
    except Exception as exc:
        raise DatasetValidationError(f"PPL replay validation failed: {exc}") from exc

    paper_epoch_id = manifest.get("paper_epoch_id")
    if not isinstance(paper_epoch_id, str) or not paper_epoch_id:
        raise DatasetValidationError("paper_epoch_id must be a non-empty string")
    if terminal.paper_epoch_id != paper_epoch_id:
        raise DatasetValidationError(
            "PPL replay epoch does not match manifest paper_epoch_id"
        )

    return ValidatedDataset(
        root=root,
        manifest=manifest,
        events=events,
        dataset_id=dataset_id,
        source_boundary_id=source_boundary_id,
        paper_epoch_id=paper_epoch_id,
    )


def _finite_number(name: str, value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ReplayError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ReplayError(f"{name} must be finite")
    return result


def _closed_pnl(open_event: LedgerEvent, close_event: LedgerEvent) -> tuple[float, float]:
    principal = _finite_number("principal", open_event.payload["principal"])
    entry_price = _finite_number("entry_price", open_event.payload["entry_price"])
    entry_fee = _finite_number("entry_fee", open_event.payload["entry_fee"])
    exit_price = _finite_number("exit_price", close_event.payload["exit_price"])
    exit_fee = _finite_number("exit_fee", close_event.payload["exit_fee"])
    side = str(open_event.payload["side"])

    if side == "LONG":
        gross_pct = (exit_price - entry_price) / entry_price
    elif side == "SHORT":
        gross_pct = (entry_price - exit_price) / entry_price
    else:
        raise ReplayError(f"unsupported canonical side {side!r}")

    gross_pnl = principal * gross_pct
    net_pnl = gross_pnl - entry_fee - exit_fee
    if not math.isfinite(gross_pnl) or not math.isfinite(net_pnl):
        raise ReplayError("derived trade PnL is non-finite")
    return gross_pnl, net_pnl


def _build_lifecycle(events: Sequence[LedgerEvent]) -> tuple[LifecycleRecord, ...]:
    opens: dict[str, LedgerEvent] = {}
    resolutions: dict[str, LedgerEvent] = {}

    for event in events:
        if event.event_type is LedgerEventType.POSITION_OPENED:
            assert event.trade_id is not None
            opens[event.trade_id] = event
        elif event.event_type in {
            LedgerEventType.POSITION_CLOSED,
            LedgerEventType.POSITION_UNRESOLVED,
        }:
            assert event.trade_id is not None
            resolutions[event.trade_id] = event

    records: list[LifecycleRecord] = []
    for trade_id, open_event in sorted(opens.items(), key=lambda item: item[1].sequence):
        resolution = resolutions.get(trade_id)
        resolution_status = "OPEN"
        resolution_event_id = None
        resolution_sequence = None
        resolved_at = None
        exit_price = None
        exit_fee = None
        gross_pnl = None
        net_pnl = None
        unresolved_reason = None

        if resolution is not None:
            resolution_event_id = resolution.event_id
            resolution_sequence = resolution.sequence
            resolved_at = resolution.timestamp
            if resolution.event_type is LedgerEventType.POSITION_CLOSED:
                resolution_status = "CLOSED"
                exit_price = _finite_number(
                    "exit_price", resolution.payload["exit_price"]
                )
                exit_fee = _finite_number("exit_fee", resolution.payload["exit_fee"])
                gross_pnl, net_pnl = _closed_pnl(open_event, resolution)
            else:
                resolution_status = "UNRESOLVED"
                unresolved_reason = str(resolution.payload["reason"])

        records.append(
            LifecycleRecord(
                trade_id=trade_id,
                symbol=str(open_event.payload["symbol"]),
                side=str(open_event.payload["side"]),
                principal=_finite_number("principal", open_event.payload["principal"]),
                open_event_id=open_event.event_id,
                open_sequence=open_event.sequence,
                opened_at=open_event.timestamp,
                decision_id=open_event.decision_id,
                entry_price=_finite_number(
                    "entry_price", open_event.payload["entry_price"]
                ),
                entry_fee=_finite_number("entry_fee", open_event.payload["entry_fee"]),
                resolution_status=resolution_status,
                resolution_event_id=resolution_event_id,
                resolution_sequence=resolution_sequence,
                resolved_at=resolved_at,
                exit_price=exit_price,
                exit_fee=exit_fee,
                gross_pnl=gross_pnl,
                net_realized_pnl=net_pnl,
                unresolved_reason=unresolved_reason,
            )
        )
    return tuple(records)


def _metric(status: str, value: Any, **extra: Any) -> dict[str, Any]:
    result = {"status": status, "value": value}
    result.update(extra)
    return result


def _performance_metrics(
    lifecycle: Sequence[LifecycleRecord],
    *,
    initial_capital: float,
) -> dict[str, Any]:
    closed = [
        item
        for item in lifecycle
        if item.resolution_status == "CLOSED" and item.net_realized_pnl is not None
    ]
    closed.sort(key=lambda item: int(item.resolution_sequence or 0))
    pnls = [float(item.net_realized_pnl) for item in closed]
    n = len(pnls)

    if n == 0:
        wr = _metric("NOT_AVAILABLE", None, n=0)
        pf = _metric("NOT_AVAILABLE", None, n=0)
        expectancy = _metric("NOT_AVAILABLE", None, n=0)
    else:
        wins = sum(1 for value in pnls if value > 0)
        wr = _metric("COMPLETE", wins / n, n=n)
        positive = sum(value for value in pnls if value > 0)
        negative_abs = abs(sum(value for value in pnls if value < 0))
        if negative_abs > 0:
            pf = _metric("COMPLETE", positive / negative_abs, n=n)
        elif positive > 0:
            pf = _metric("POSITIVE_INFINITY", None, n=n)
        else:
            pf = _metric("UNDEFINED_ZERO_DENOMINATOR", None, n=n)
        expectancy = _metric("COMPLETE", sum(pnls) / n, n=n)

    equity = initial_capital
    peak = initial_capital
    max_dd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)

    return {
        "closed_trade_count": n,
        "win_rate": wr,
        "profit_factor": pf,
        "expectancy_usd": expectancy,
        "realized_close_to_close_max_drawdown": _metric(
            "COMPLETE",
            max_dd,
            n=n,
            definition="initial capital + cumulative closed-trade net realized PnL",
        ),
        "mark_to_market_max_drawdown": _metric(
            "NOT_AVAILABLE",
            None,
            reason="RL-DATA v1 has no certified mark-price trajectory",
        ),
        "sharpe": _metric(
            "NOT_AVAILABLE",
            None,
            reason="deferred to RL-DIAG-01; sampling/annualization semantics not defined here",
        ),
    }


def _terminal_state(state: PaperPortfolioState, events: Sequence[LedgerEvent]) -> dict[str, Any]:
    if state.epoch is None:
        raise ReplayError("replayed PPL state has no epoch")
    return {
        "paper_epoch_id": state.paper_epoch_id,
        "initial_virtual_capital": state.epoch.initial_virtual_capital,
        "source_event_count": len(events),
        "last_source_sequence": state.last_sequence,
        "available_cash": state.available_cash,
        "reserved_principal": state.reserved_principal,
        "unresolved_capital": state.unresolved_capital,
        "realized_pnl": state.realized_pnl,
        "fees_paid": state.fees_paid,
        "open_position_count": len(state.open_positions),
        "closed_trade_count": len(state.closed_trade_ids),
        "unresolved_position_count": len(state.unresolved_positions),
    }


def replay_factual_dataset(
    dataset_root: str | Path,
    *,
    replay_code_sha: str,
    replay_config: Mapping[str, Any] | None = None,
) -> FactualReplayResult:
    """Validate and replay one immutable RL-DATA dataset deterministically."""

    code_sha = _require_sha40(replay_code_sha, field="replay_code_sha")
    dataset = validate_dataset(dataset_root)
    try:
        state = project(dataset.events)
    except Exception as exc:
        raise ReplayError(f"factual PPL replay failed: {exc}") from exc

    lifecycle = _build_lifecycle(dataset.events)
    terminal = _terminal_state(state, dataset.events)
    initial_capital = _finite_number(
        "initial_virtual_capital", terminal["initial_virtual_capital"]
    )
    metrics = _performance_metrics(lifecycle, initial_capital=initial_capital)

    config_doc = dict(_DEFAULT_REPLAY_CONFIG if replay_config is None else replay_config)
    replay_config_hash = _sha256_bytes(_canonical_json_bytes(config_doc))

    source_identity = dataset.manifest["source_boundary_identity"]
    source_experiment_identity = {
        key: source_identity.get(key)
        for key in (
            "ppl_birth_code_sha",
            "ppl_semantic_config_snapshot_hash",
            "experiment_config_file_sha256",
            "experiment_config_snapshot_sha256",
            "experiment_runtime_source_sha",
            "ppl_stream_sha256",
        )
    }
    population = {
        "component": "ppl_events",
        "event_count": len(dataset.events),
        "first_sequence": dataset.events[0].sequence,
        "last_sequence": dataset.events[-1].sequence,
        "closed_trade_count": metrics["closed_trade_count"],
    }
    run_identity = {
        "identity_schema": _RUN_IDENTITY_SCHEMA,
        "run_kind": _RUN_KIND,
        "dataset_id": dataset.dataset_id,
        "source_boundary_id": dataset.source_boundary_id,
        "paper_epoch_id": dataset.paper_epoch_id,
        "research_replay_code_sha": code_sha,
        "replay_method": _REPLAY_METHOD,
        "replay_config_hash": replay_config_hash,
        "population": population,
        "source_experiment_identity": source_experiment_identity,
        "candidate_config_hash": None,
        "counterfactual_spec_digest": None,
    }
    research_run_id = _sha256_bytes(_canonical_json_bytes(run_identity))

    return FactualReplayResult(
        research_run_id=research_run_id,
        research_run_identity=run_identity,
        replay_config_hash=replay_config_hash,
        dataset_id=dataset.dataset_id,
        source_boundary_id=dataset.source_boundary_id,
        paper_epoch_id=dataset.paper_epoch_id,
        terminal_state=terminal,
        lifecycle=lifecycle,
        metrics=metrics,
    )
