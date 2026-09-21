from __future__ import annotations

from dataclasses import replace

import pytest

from financial_institute.ledger import FinancialLedgerError, project_financial_ledger
from financial_institute.models import FinancialContext
from financial_institute.ppl_adapter import adapt_ppl_stream
from financial_institute.semantics import EvidenceStatus
from paper_trading.ledger_events import (
    make_epoch_created_event,
    make_position_opened_event,
)


EPOCH = "FIN01-LEDGER-FORENSIC"


def _events():
    return [
        make_epoch_created_event(
            event_id="e1",
            paper_epoch_id=EPOCH,
            sequence=1,
            timestamp=1000.0,
            initial_virtual_capital=1000.0,
            code_sha="source-sha",
            config_snapshot_hash="config-hash",
            schema_version=2,
        ),
        make_position_opened_event(
            event_id="e2",
            paper_epoch_id=EPOCH,
            sequence=2,
            timestamp=1001.0,
            trade_id="t1",
            symbol="BTCUSDT",
            side="LONG",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.01,
            schema_version=2,
            tp_price=110.0,
            sl_price=90.0,
            timeout_at=1100.0,
            recovery_eligible_until=1200.0,
        ),
    ]


def _context() -> FinancialContext:
    return FinancialContext(
        fin_code_sha="fin-sha",
        funding_status=EvidenceStatus.NOT_APPLICABLE,
    )


def _financial_events():
    return adapt_ppl_stream(_events(), _context()).financial_events


def test_ledger_rejects_mixed_semantic_contexts() -> None:
    first, second = _financial_events()
    corrupted = replace(second, semantic_context_digest="different-context")
    with pytest.raises(FinancialLedgerError, match="semantic contexts"):
        project_financial_ledger((first, corrupted), asset="USDT")


def test_ledger_rejects_mixed_fin_code_sha() -> None:
    first, second = _financial_events()
    corrupted = replace(second, fin_code_sha="different-code")
    with pytest.raises(FinancialLedgerError, match="FIN code SHAs"):
        project_financial_ledger((first, corrupted), asset="USDT")


def test_ledger_rejects_mixed_config_hash() -> None:
    first, second = _financial_events()
    corrupted = replace(second, config_hash="different-config")
    with pytest.raises(FinancialLedgerError, match="config hashes"):
        project_financial_ledger((first, corrupted), asset="USDT")


def test_ledger_rejects_duplicate_source_event_identity() -> None:
    first, second = _financial_events()
    corrupted = replace(second, source_event_id=first.source_event_id)
    with pytest.raises(FinancialLedgerError, match="duplicate source_event_id"):
        project_financial_ledger((first, corrupted), asset="USDT")


def test_ledger_rejects_posting_event_envelope_mismatch() -> None:
    first, second = _financial_events()
    bad_posting = replace(
        second.postings[0],
        financial_event_id="wrong-financial-event",
    )
    corrupted = replace(
        second,
        postings=(bad_posting, *second.postings[1:]),
    )
    with pytest.raises(FinancialLedgerError, match="financial_event_id"):
        project_financial_ledger((first, corrupted), asset="USDT")


def test_ledger_rejects_posting_epoch_envelope_mismatch() -> None:
    first, second = _financial_events()
    bad_posting = replace(
        second.postings[0],
        paper_epoch_id="OTHER-EPOCH",
    )
    corrupted = replace(
        second,
        postings=(bad_posting, *second.postings[1:]),
    )
    with pytest.raises(FinancialLedgerError, match="paper_epoch_id"):
        project_financial_ledger((first, corrupted), asset="USDT")
