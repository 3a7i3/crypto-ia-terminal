"""FIN-01 deterministic double-entry ledger and Treasury projection."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import MappingProxyType
from typing import Sequence

from financial_institute.models import (
    FinancialContext,
    FinancialEvent,
    FinancialLedgerState,
    TreasuryView,
)
from financial_institute.semantics import (
    ACCOUNT_KINDS,
    AccountKind,
    EvidenceStatus,
    FinancialAccount,
    FinancialContractError,
    PostingSide,
    assert_balanced_postings,
    realized_pnl_to_date,
)


class FinancialLedgerError(FinancialContractError):
    """Deterministic FIN ledger replay violation."""


_NON_NEGATIVE_ACCOUNTS = frozenset(
    {
        FinancialAccount.CASH_AVAILABLE,
        FinancialAccount.CAPITAL_RESERVED,
        FinancialAccount.CAPITAL_UNRESOLVED,
        FinancialAccount.EPOCH_CAPITAL,
        FinancialAccount.FEES_EXPENSE,
    }
)


def _balance(
    balances: dict[str, Decimal],
    account: FinancialAccount,
) -> Decimal:
    return balances.get(account.value, Decimal("0"))


def _posting_delta(account: FinancialAccount, side: PostingSide, amount: Decimal) -> Decimal:
    kind = ACCOUNT_KINDS[account]
    if kind in {AccountKind.ASSET, AccountKind.EXPENSE}:
        return amount if side is PostingSide.DEBIT else -amount
    return amount if side is PostingSide.CREDIT else -amount


def project_financial_ledger(
    events: Sequence[FinancialEvent],
    *,
    asset: str,
) -> FinancialLedgerState:
    """Replay financially-material events with exact Decimal arithmetic."""

    if not events:
        raise FinancialLedgerError("financial event stream must not be empty")
    if not asset:
        raise FinancialLedgerError("asset must be non-empty")

    first = events[0]
    epoch = first.paper_epoch_id
    expected_fin_schema = first.fin_schema_version
    expected_context_digest = first.semantic_context_digest
    expected_fin_code_sha = first.fin_code_sha
    expected_config_hash = first.config_hash
    if first.source_event_type != "EPOCH_CREATED":
        raise FinancialLedgerError("first financial event must derive from EPOCH_CREATED")

    state = FinancialLedgerState(
        paper_epoch_id=epoch,
        asset=asset,
        balances=MappingProxyType({}),
    )

    seen_source_event_ids: set[str] = set()

    for event in events:
        if event.paper_epoch_id != epoch:
            raise FinancialLedgerError("financial events span multiple PAPER epochs")
        if event.fin_schema_version != expected_fin_schema:
            raise FinancialLedgerError("financial events span multiple FIN schemas")
        if event.semantic_context_digest != expected_context_digest:
            raise FinancialLedgerError("financial events span multiple semantic contexts")
        if event.fin_code_sha != expected_fin_code_sha:
            raise FinancialLedgerError("financial events span multiple FIN code SHAs")
        if event.config_hash != expected_config_hash:
            raise FinancialLedgerError("financial events span multiple config hashes")
        if event.source_event_id in seen_source_event_ids:
            raise FinancialLedgerError(
                f"duplicate source_event_id={event.source_event_id!r}"
            )
        seen_source_event_ids.add(event.source_event_id)
        if (
            state.last_source_sequence > 0
            and event.source_event_type == "EPOCH_CREATED"
        ):
            raise FinancialLedgerError("EPOCH_CREATED may appear only once")
        if event.financial_event_id in state.applied_financial_event_ids:
            raise FinancialLedgerError(
                f"duplicate financial_event_id={event.financial_event_id!r}"
            )
        if event.source_sequence <= state.last_source_sequence:
            raise FinancialLedgerError(
                "financial event source sequences must be strictly increasing"
            )

        assert_balanced_postings(event.postings)
        balances = dict(state.balances)

        for posting in event.postings:
            if posting.financial_event_id != event.financial_event_id:
                raise FinancialLedgerError(
                    "posting financial_event_id does not match event envelope"
                )
            if posting.paper_epoch_id != event.paper_epoch_id:
                raise FinancialLedgerError(
                    "posting paper_epoch_id does not match event envelope"
                )
            if posting.asset != asset:
                raise FinancialLedgerError(
                    f"posting asset={posting.asset!r} != ledger asset={asset!r}"
                )
            delta = _posting_delta(posting.account, posting.side, posting.amount)
            balances[posting.account.value] = _balance(
                balances, posting.account
            ) + delta

        for account in _NON_NEGATIVE_ACCOUNTS:
            value = _balance(balances, account)
            if value < 0:
                raise FinancialLedgerError(
                    f"{account.value} became negative after "
                    f"{event.source_event_type}: {value}"
                )

        state = replace(
            state,
            balances=MappingProxyType(balances),
            applied_financial_event_ids=(
                state.applied_financial_event_ids | {event.financial_event_id}
            ),
            last_source_sequence=event.source_sequence,
        )

    return state


def treasury_view(
    ledger: FinancialLedgerState,
    context: FinancialContext,
) -> TreasuryView:
    """Project canonical PAPER Treasury fields from the FIN ledger."""

    if ledger.asset != context.asset:
        raise FinancialLedgerError("ledger/context asset mismatch")

    balances = dict(ledger.balances)
    initial_capital = _balance(balances, FinancialAccount.EPOCH_CAPITAL)
    cash = _balance(balances, FinancialAccount.CASH_AVAILABLE)
    reserved = _balance(balances, FinancialAccount.CAPITAL_RESERVED)
    unresolved = _balance(balances, FinancialAccount.CAPITAL_UNRESOLVED)
    gross_realized = _balance(
        balances, FinancialAccount.REALIZED_TRADING_PNL
    )
    fees = _balance(balances, FinancialAccount.FEES_EXPENSE)

    if context.funding_status is EvidenceStatus.NOT_APPLICABLE:
        funding_net = Decimal("0")
        realized = realized_pnl_to_date(
            gross_realized_price_pnl=gross_realized,
            fees_paid=fees,
            funding_net=funding_net,
        )
    elif context.funding_status is EvidenceStatus.UNRESOLVED:
        funding_net = None
        realized = None
    else:
        raise FinancialLedgerError(
            "PPL-only FIN-01 cannot establish COMPLETE/PARTIAL funding"
        )

    return TreasuryView(
        paper_epoch_id=ledger.paper_epoch_id,
        asset=ledger.asset,
        financial_model=context.financial_model,
        initial_epoch_capital=initial_capital,
        cash_available=cash,
        capital_reserved=reserved,
        capital_deployed=reserved,
        capital_unresolved=unresolved,
        gross_realized_price_pnl=gross_realized,
        fees_paid=fees,
        funding_net=funding_net,
        funding_status=context.funding_status,
        funding_evidence_ref=context.funding_evidence_ref,
        realized_pnl=realized,
    )
