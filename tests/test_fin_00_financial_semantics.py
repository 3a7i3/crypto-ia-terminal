from __future__ import annotations

from decimal import Decimal

import pytest

from financial_institute.semantics import (
    FinancialAccount,
    FinancialContractError,
    LedgerPosting,
    PostingSide,
    ValuationStatus,
    assert_balanced_postings,
    book_equity_at_cost,
    canonical_decimal,
    certified_equity,
    linear_price_pnl,
    realized_pnl_to_date,
    within_reconciliation_tolerance,
)


EPOCH = "F00-EPOCH-TEST"
ASSET = "USDT"


def post(
    posting_id: str,
    event_id: str,
    account: FinancialAccount,
    side: PostingSide,
    amount: str,
) -> LedgerPosting:
    return LedgerPosting(
        posting_id=posting_id,
        financial_event_id=event_id,
        account=account,
        side=side,
        asset=ASSET,
        amount=Decimal(amount),
        paper_epoch_id=EPOCH,
    )


def test_epoch_capital_postings_balance_exactly() -> None:
    postings = [
        post("p1", "f1", FinancialAccount.CASH_AVAILABLE, PostingSide.DEBIT, "1000"),
        post("p2", "f1", FinancialAccount.EPOCH_CAPITAL, PostingSide.CREDIT, "1000"),
    ]
    assert_balanced_postings(postings)


def test_open_postings_balance_principal_and_entry_fee_once() -> None:
    postings = [
        post("p1", "f-open", FinancialAccount.CAPITAL_RESERVED, PostingSide.DEBIT, "10"),
        post("p2", "f-open", FinancialAccount.FEES_EXPENSE, PostingSide.DEBIT, "0.01"),
        post("p3", "f-open", FinancialAccount.CASH_AVAILABLE, PostingSide.CREDIT, "10.01"),
    ]
    assert_balanced_postings(postings)


def test_close_gain_postings_balance_release_gain_and_exit_fee() -> None:
    postings = [
        post("p1", "f-close", FinancialAccount.CASH_AVAILABLE, PostingSide.DEBIT, "10"),
        post("p2", "f-close", FinancialAccount.CAPITAL_RESERVED, PostingSide.CREDIT, "10"),
        post("p3", "f-close", FinancialAccount.CASH_AVAILABLE, PostingSide.DEBIT, "1"),
        post(
            "p4",
            "f-close",
            FinancialAccount.REALIZED_TRADING_PNL,
            PostingSide.CREDIT,
            "1",
        ),
        post("p5", "f-close", FinancialAccount.FEES_EXPENSE, PostingSide.DEBIT, "0.01"),
        post("p6", "f-close", FinancialAccount.CASH_AVAILABLE, PostingSide.CREDIT, "0.01"),
    ]
    assert_balanced_postings(postings)


def test_close_loss_postings_balance_without_inverting_cash_semantics() -> None:
    postings = [
        post("p1", "f-close-loss", FinancialAccount.CASH_AVAILABLE, PostingSide.DEBIT, "10"),
        post(
            "p2",
            "f-close-loss",
            FinancialAccount.CAPITAL_RESERVED,
            PostingSide.CREDIT,
            "10",
        ),
        post(
            "p3",
            "f-close-loss",
            FinancialAccount.REALIZED_TRADING_PNL,
            PostingSide.DEBIT,
            "2",
        ),
        post("p4", "f-close-loss", FinancialAccount.CASH_AVAILABLE, PostingSide.CREDIT, "2"),
    ]
    assert_balanced_postings(postings)


def test_unresolved_moves_principal_without_fabricated_cash_or_pnl() -> None:
    postings = [
        post(
            "p1",
            "f-unresolved",
            FinancialAccount.CAPITAL_UNRESOLVED,
            PostingSide.DEBIT,
            "10",
        ),
        post(
            "p2",
            "f-unresolved",
            FinancialAccount.CAPITAL_RESERVED,
            PostingSide.CREDIT,
            "10",
        ),
    ]
    assert_balanced_postings(postings)


def test_unbalanced_financial_event_fails_closed() -> None:
    postings = [
        post("p1", "f-bad", FinancialAccount.CASH_AVAILABLE, PostingSide.DEBIT, "10"),
        post("p2", "f-bad", FinancialAccount.EPOCH_CAPITAL, PostingSide.CREDIT, "9.99"),
    ]
    with pytest.raises(FinancialContractError, match="unbalanced"):
        assert_balanced_postings(postings)


@pytest.mark.parametrize(
    ("side", "expected"),
    [
        ("LONG", Decimal("1")),
        ("SHORT", Decimal("-1")),
    ],
)
def test_linear_price_pnl_matches_current_ppl_price_return_contract(
    side: str, expected: Decimal
) -> None:
    pnl = linear_price_pnl(
        principal="10",
        side=side,
        entry_price="100",
        mark_or_exit_price="110",
    )
    assert pnl == expected


def test_realized_pnl_recognizes_fees_when_charged() -> None:
    assert realized_pnl_to_date(
        gross_realized_price_pnl="0",
        fees_paid="0.01",
        funding_net="0",
    ) == Decimal("-0.01")


def test_book_equity_conserves_historical_principal_when_unresolved() -> None:
    assert book_equity_at_cost(
        cash_available="989.99",
        capital_reserved="0",
        capital_unresolved="10",
    ) == Decimal("999.99")


def test_certified_equity_requires_no_unresolved_capital() -> None:
    assert (
        certified_equity(
            cash_available="989.99",
            capital_reserved="0",
            unrealized_pnl="0",
            capital_unresolved="10",
            valuation_statuses=(),
        )
        is None
    )


def test_certified_equity_requires_live_marks_for_open_positions() -> None:
    assert (
        certified_equity(
            cash_available="989.99",
            capital_reserved="10",
            unrealized_pnl="1",
            capital_unresolved="0",
            valuation_statuses=(ValuationStatus.STALE,),
        )
        is None
    )
    assert certified_equity(
        cash_available="989.99",
        capital_reserved="10",
        unrealized_pnl="1",
        capital_unresolved="0",
        valuation_statuses=(ValuationStatus.LIVE,),
    ) == Decimal("1000.99")


def test_reconciliation_tolerance_is_explicit() -> None:
    assert within_reconciliation_tolerance(
        projected="100",
        observed="100.005",
        absolute_tolerance="0.01",
        relative_tolerance="0",
    )
    assert not within_reconciliation_tolerance(
        projected="100",
        observed="100.005",
        absolute_tolerance="0",
        relative_tolerance="0",
    )


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_financial_values_fail_closed(bad: str) -> None:
    with pytest.raises(FinancialContractError):
        canonical_decimal("value", bad)
