"""
tests/conftest.py

O-02W-PRE-T1-E REM-B: the durable order-intent journal defaults to a path
under `databases/` (production convention), but no test run may write real
files there — it would contaminate the scientific data guard baseline
(.ci/scientific_data_guard_baseline.json, see root conftest.py). Redirect the
journal to a session-scoped temp path for the whole test session; individual
REM-B tests still use their own `tmp_path`-based journals directly and are
unaffected by this default.
"""

import os
import tempfile

_tmp_dir = tempfile.mkdtemp(prefix="order_intent_journal_test_")
os.environ.setdefault(
    "ORDER_INTENT_JOURNAL_PATH", os.path.join(_tmp_dir, "order_intent_journal.jsonl")
)
