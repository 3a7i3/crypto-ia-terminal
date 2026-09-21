"""Build the deterministic FIN-02 browser-proof artifact."""

from decimal import Decimal
from pathlib import Path
import argparse

from financial_institute.models import FinancialContext, PAPER_LINEAR_FUNDING_EVIDENCE_REF
from financial_institute.reconciliation import (
    ReconciliationPolicy,
    SimulatorFinancialObservation,
    ppl_observation_from_events,
    reconcile_financial_snapshot,
)
from financial_institute.semantics import EvidenceStatus
from financial_institute.snapshot import build_financial_snapshot
from observability.financial_reconciliation import (
    build_financial_reconciliation_document,
    write_financial_reconciliation_document,
)
from paper_trading.ledger_events import make_epoch_created_event, make_position_opened_event
from paper_trading.paper_portfolio_ledger import project

NOW = Decimal("1700000000")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)

    epoch = "fin02-visual-epoch"
    events = (
        make_epoch_created_event(
            event_id="fin02-v1",
            paper_epoch_id=epoch,
            sequence=1,
            timestamp=float(NOW - 100),
            initial_virtual_capital=1000.0,
            code_sha="a" * 40,
            config_snapshot_hash="b" * 64,
            schema_version=2,
        ),
        make_position_opened_event(
            event_id="fin02-v2",
            paper_epoch_id=epoch,
            sequence=2,
            timestamp=float(NOW - 50),
            trade_id="FIN02-VISUAL-T1",
            symbol="BTC/USDT",
            side="LONG",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.1,
            decision_id="fin02-visual-decision",
            schema_version=2,
            tp_price=110.0,
            sl_price=90.0,
            timeout_at=float(NOW + 100),
            recovery_eligible_until=float(NOW + 200),
        ),
    )
    context = FinancialContext(
        fin_code_sha="c" * 40,
        funding_status=EvidenceStatus.NOT_APPLICABLE,
        funding_evidence_ref=PAPER_LINEAR_FUNDING_EVIDENCE_REF,
        experiment_id="FIN02-VISUAL",
        venue="MEXC_SIM",
        market_type="PAPER_LINEAR",
    )
    financial = build_financial_snapshot(
        events,
        context,
        [],
        valuation_as_of=NOW,
        max_mark_age_s=Decimal("30"),
    )
    ppl = ppl_observation_from_events(events, observed_at=NOW)
    state = project(events)
    simulator = SimulatorFinancialObservation(
        observed_at=NOW,
        cash_available=Decimal(str(state.available_cash)) + Decimal("1"),
        capital_reserved=Decimal(str(state.reserved_principal)),
        open_position_ids=tuple(state.open_positions),
        lifecycle_transitions_in_flight=0,
        pending_order_count=0,
    )
    reconciliation = reconcile_financial_snapshot(
        financial,
        ppl,
        policy=ReconciliationPolicy(
            absolute_tolerance=Decimal("0.000000000001"),
            relative_tolerance=Decimal("0"),
            stale_after_s=Decimal("90"),
        ),
        as_of=NOW,
        simulator=simulator,
    )
    document = build_financial_reconciliation_document(
        financial,
        reconciliation,
        ppl=ppl,
        generated_at=NOW,
        simulator=simulator,
    )
    write_financial_reconciliation_document(document, path=path)
    assert document["reconciliation"]["overall_status"] == "DIVERGENT"
    assert document["financial"]["certified_equity"] is None
    print(f"FIN02_VISUAL_FIXTURE={path}")

if __name__ == "__main__":
    main()
