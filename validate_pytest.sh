#!/usr/bin/env bash
# pytest validation suite — excludes problematic imports

echo "=== Crypto AI Terminal — Pytest Validation ==="
echo ""
echo "1. Testing tracker/exit deduplication (new tests)"
.venv/Scripts/pytest tests/test_tracker_exit_dedup.py -v --tb=short

echo ""
echo "2. Testing tracker schema compatibility (legacy API)"
.venv/Scripts/pytest tests/test_tracker_schema_compat.py -v --tb=short

echo ""
echo "3. Running suite (excluding problematic modules)"
.venv/Scripts/pytest tests/ \
  --ignore=tests/test_lm_studio.py \
  -q --tb=line \
  -k "not slow" 2>&1 | tail -30

echo ""
echo "=== Validation complete ==="
