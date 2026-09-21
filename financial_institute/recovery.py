"""PPL-RECOVERY-01 — deterministic durable replay certification.

This module is read-only with respect to authoritative PPL. It opens two
independent DurableEventStore instances over the same explicit root and proves
that durable PPL facts reproduce the same lifecycle state, restart plan and
Financial Institute snapshot under identical explicit valuation inputs.

It performs no append, no exchange call, no wall-clock read, no environment
lookup and no runtime mutation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from os import PathLike
from typing import Any, Mapping, Sequence

from financial_institute.models import (
    FinancialContext,
    FinancialSnapshot,
    ValuationObservation,
)
from financial_institute.ppl_adapter import ppl_stream_digest
from financial_institute.snapshot import build_financial_snapshot
from paper_trading.durable_event_store import DurableEventStore
from paper_trading.paper_portfolio_ledger import (
    OpenPositionState,
    PaperPortfolioState,
    UnresolvedPositionState,
    project,
)
from paper_trading.ppl_recovery import (
    RestartRecoveryPlan,
    plan_restart_recovery,
)


class RecoveryCertificationError(RuntimeError):
    """Durable restart/replay evidence is not exactly reproducible."""


@dataclass(frozen=True)
class RecoveryReplayProof:
    paper_epoch_id: str
    source_event_count: int
    last_source_sequence: int
    source_stream_digest_before: str
    source_stream_digest_after: str
    ppl_state_digest_before: str
    ppl_state_digest_after: str
    recovery_plan_digest_before: str
    recovery_plan_digest_after: str
    financial_snapshot_id_before: str
    financial_snapshot_id_after: str
    financial_state_digest_before: str
    financial_state_digest_after: str

    @property
    def exact_replay_equivalent(self) -> bool:
        return all(
            (
                self.source_stream_digest_before
                == self.source_stream_digest_after,
                self.ppl_state_digest_before == self.ppl_state_digest_after,
                self.recovery_plan_digest_before
                == self.recovery_plan_digest_after,
                self.financial_snapshot_id_before
                == self.financial_snapshot_id_after,
                self.financial_state_digest_before
                == self.financial_state_digest_after,
            )
        )


def _hash(namespace: str, payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(namespace.encode("utf-8") + b"\n" + encoded).hexdigest()


def _open_position_record(position: OpenPositionState) -> dict[str, Any]:
    return {
        "trade_id": position.trade_id,
        "symbol": position.symbol,
        "side": position.side.value,
        "principal": position.principal,
        "entry_price": position.entry_price,
        "entry_fee": position.entry_fee,
        "opened_sequence": position.opened_sequence,
        "opened_at": position.opened_at,
        "tp_price": position.tp_price,
        "sl_price": position.sl_price,
        "timeout_at": position.timeout_at,
        "recovery_eligible_until": position.recovery_eligible_until,
    }


def _unresolved_position_record(
    position: UnresolvedPositionState,
) -> dict[str, Any]:
    return {
        "trade_id": position.trade_id,
        "symbol": position.symbol,
        "side": position.side.value,
        "principal": position.principal,
        "entry_price": position.entry_price,
        "entry_fee": position.entry_fee,
        "reason": position.reason,
        "unresolved_sequence": position.unresolved_sequence,
    }


def ppl_state_digest(state: PaperPortfolioState) -> str:
    """Hash every replay-relevant PPL state field without inference."""

    epoch = state.epoch
    epoch_record = None
    if epoch is not None:
        epoch_record = {
            "paper_epoch_id": epoch.paper_epoch_id,
            "created_at": epoch.created_at,
            "initial_virtual_capital": epoch.initial_virtual_capital,
            "code_sha": epoch.code_sha,
            "config_snapshot_hash": epoch.config_snapshot_hash,
            "status": epoch.status.value,
            "schema_version": epoch.schema_version,
        }

    return _hash(
        "PPL_RECOVERY_STATE_V1",
        {
            "paper_epoch_id": state.paper_epoch_id,
            "epoch": epoch_record,
            "available_cash": state.available_cash,
            "reserved_principal": state.reserved_principal,
            "unresolved_capital": state.unresolved_capital,
            "realized_pnl": state.realized_pnl,
            "fees_paid": state.fees_paid,
            "open_positions": [
                _open_position_record(state.open_positions[trade_id])
                for trade_id in sorted(state.open_positions)
            ],
            "unresolved_positions": [
                _unresolved_position_record(
                    state.unresolved_positions[trade_id]
                )
                for trade_id in sorted(state.unresolved_positions)
            ],
            "closed_trade_ids": sorted(state.closed_trade_ids),
            "last_sequence": state.last_sequence,
            "seen_event_ids": sorted(state.seen_event_ids),
            "restored_count_total": state.restored_count_total,
            "unresolved_count_total": state.unresolved_count_total,
        },
    )


def recovery_plan_digest(plan: RestartRecoveryPlan) -> str:
    return _hash(
        "PPL_RECOVERY_PLAN_V1",
        {
            "paper_epoch_id": plan.paper_epoch_id,
            "positions": [
                {
                    "trade_id": item.trade_id,
                    "disposition": item.disposition.value,
                }
                for item in plan.positions
            ],
        },
    )


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def financial_state_digest(snapshot: FinancialSnapshot) -> str:
    """Hash accounting meaning, independent of the snapshot identity field."""

    return _hash(
        "PPL_FINANCIAL_RECOVERY_STATE_V1",
        {
            "paper_epoch_id": snapshot.paper_epoch_id,
            "source_authority": snapshot.source_authority,
            "source_stream_digest": snapshot.source_stream_digest,
            "last_source_sequence": snapshot.last_source_sequence,
            "fin_schema_version": snapshot.fin_schema_version,
            "semantic_context_digest": snapshot.semantic_context_digest,
            "fin_code_sha": snapshot.fin_code_sha,
            "source_code_sha": snapshot.source_code_sha,
            "config_hash": snapshot.config_hash,
            "financial_model": snapshot.financial_model.value,
            "asset": snapshot.asset,
            "initial_epoch_capital": _decimal_text(
                snapshot.initial_epoch_capital
            ),
            "cash_available": _decimal_text(snapshot.cash_available),
            "capital_reserved": _decimal_text(snapshot.capital_reserved),
            "capital_deployed": _decimal_text(snapshot.capital_deployed),
            "capital_unresolved": _decimal_text(snapshot.capital_unresolved),
            "gross_realized_price_pnl": _decimal_text(
                snapshot.gross_realized_price_pnl
            ),
            "fees_paid": _decimal_text(snapshot.fees_paid),
            "funding_net": _decimal_text(snapshot.funding_net),
            "funding_status": snapshot.funding_status.value,
            "funding_evidence_ref": snapshot.funding_evidence_ref,
            "realized_pnl": _decimal_text(snapshot.realized_pnl),
            "known_unrealized_pnl": _decimal_text(
                snapshot.known_unrealized_pnl
            ),
            "unrealized_pnl": _decimal_text(snapshot.unrealized_pnl),
            "certified_equity": _decimal_text(snapshot.certified_equity),
            "valuation_as_of": _decimal_text(snapshot.valuation_as_of),
            "valuation_set_digest": snapshot.valuation_set_digest,
            "valuation_statuses": [
                status.value for status in snapshot.valuation_statuses
            ],
            "open_position_count": snapshot.open_position_count,
            "settled_position_count": snapshot.settled_position_count,
            "unresolved_position_count": snapshot.unresolved_position_count,
            "evidence_status": snapshot.evidence_status.value,
            "reconciliation_status": snapshot.reconciliation_status.value,
            "strategy_id": snapshot.strategy_id,
            "strategy_version": snapshot.strategy_version,
            "strategy_attribution_status": (
                snapshot.strategy_attribution_status.value
            ),
            "experiment_id": snapshot.experiment_id,
            "experiment_attribution_status": (
                snapshot.experiment_attribution_status.value
            ),
            "venue": snapshot.venue,
            "market_type": snapshot.market_type,
        },
    )


def _build_once(
    *,
    root_dir: PathLike[str] | str,
    paper_epoch_id: str,
    context: FinancialContext,
    observations: Sequence[ValuationObservation],
    valuation_as_of: Decimal,
    max_mark_age_s: Decimal,
    restart_now: float,
) -> tuple[
    tuple[Any, ...],
    PaperPortfolioState,
    RestartRecoveryPlan,
    FinancialSnapshot,
]:
    store = DurableEventStore(root_dir)
    events = store.load_epoch(paper_epoch_id)
    state = project(events)
    plan = plan_restart_recovery(state, now=restart_now)
    snapshot = build_financial_snapshot(
        events,
        context,
        observations,
        valuation_as_of=valuation_as_of,
        max_mark_age_s=max_mark_age_s,
    )
    return events, state, plan, snapshot


def certify_recovery_replay(
    *,
    root_dir: PathLike[str] | str,
    paper_epoch_id: str,
    context: FinancialContext,
    observations: Sequence[ValuationObservation],
    valuation_as_of: Decimal,
    max_mark_age_s: Decimal,
    restart_now: float,
) -> RecoveryReplayProof:
    """Prove exact replay equivalence across two independent store instances."""

    before = _build_once(
        root_dir=root_dir,
        paper_epoch_id=paper_epoch_id,
        context=context,
        observations=observations,
        valuation_as_of=valuation_as_of,
        max_mark_age_s=max_mark_age_s,
        restart_now=restart_now,
    )
    after = _build_once(
        root_dir=root_dir,
        paper_epoch_id=paper_epoch_id,
        context=context,
        observations=observations,
        valuation_as_of=valuation_as_of,
        max_mark_age_s=max_mark_age_s,
        restart_now=restart_now,
    )

    events_before, state_before, plan_before, snapshot_before = before
    events_after, state_after, plan_after, snapshot_after = after

    proof = RecoveryReplayProof(
        paper_epoch_id=paper_epoch_id,
        source_event_count=len(events_before),
        last_source_sequence=state_before.last_sequence,
        source_stream_digest_before=ppl_stream_digest(events_before),
        source_stream_digest_after=ppl_stream_digest(events_after),
        ppl_state_digest_before=ppl_state_digest(state_before),
        ppl_state_digest_after=ppl_state_digest(state_after),
        recovery_plan_digest_before=recovery_plan_digest(plan_before),
        recovery_plan_digest_after=recovery_plan_digest(plan_after),
        financial_snapshot_id_before=snapshot_before.snapshot_id,
        financial_snapshot_id_after=snapshot_after.snapshot_id,
        financial_state_digest_before=financial_state_digest(snapshot_before),
        financial_state_digest_after=financial_state_digest(snapshot_after),
    )

    if len(events_before) != len(events_after):
        raise RecoveryCertificationError(
            "durable event count changed across independent reload"
        )
    if state_before.last_sequence != state_after.last_sequence:
        raise RecoveryCertificationError(
            "PPL last sequence changed across independent reload"
        )
    if not proof.exact_replay_equivalent:
        raise RecoveryCertificationError(
            "PPL/FIN state is not exactly reproducible across restart replay"
        )
    return proof


__all__ = [
    "RecoveryCertificationError",
    "RecoveryReplayProof",
    "certify_recovery_replay",
    "financial_state_digest",
    "ppl_state_digest",
    "recovery_plan_digest",
]
