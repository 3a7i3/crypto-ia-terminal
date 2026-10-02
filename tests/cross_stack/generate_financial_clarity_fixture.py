"""Existing synthetic FIN producer -> artifact -> actual read-only API for U6."""

import argparse
import json
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from observability.operator_api import app as api_app
from observability.operator_api.financial_reconciliation_reader import (
    FinancialReconciliationSnapshotReader,
)
from tests.test_operator_api_financial_reconciliation import _doc
from financial_institute.reconciliation import SimulatorFinancialObservation


def generate_financial_clarity_fixture(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="fin-clarity-", dir=out))
    target = root / "financial.json"
    # Synthetic observation exercises a genuinely nonzero reconciliation delta.
    # Only the test input changes; accounting/reconciliation run through the
    # existing pure producer. Never rewrite a generated financial result.
    with patch(
        "tests.test_operator_api_financial_reconciliation.SimulatorFinancialObservation",
        side_effect=lambda **kw: SimulatorFinancialObservation(
            **(kw | {"cash_available": Decimal("989.9000000000224174531618")})
        ),
    ):
        doc = _doc()
    target.write_text(json.dumps(doc, allow_nan=False), encoding="utf-8")
    previous = api_app._financial_reconciliation_reader
    api_app._financial_reconciliation_reader = FinancialReconciliationSnapshotReader(
        target, now_fn=lambda: 20.0
    )
    try:
        with TestClient(api_app.app) as client:
            response = client.get("/api/operator/v1/financial-reconciliation")
    finally:
        api_app._financial_reconciliation_reader = previous
    result = {
        "http_status": response.status_code,
        "body": response.json(),
        "_proof": {"fixture_is_synthetic": True, "existing_fin_producer_invoked": True},
    }
    (out / "P_financial_clarity.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    generate_financial_clarity_fixture(parser.parse_args().out)
