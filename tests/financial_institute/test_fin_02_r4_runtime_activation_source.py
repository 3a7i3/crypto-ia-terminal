from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from observability.financial_paths import (
    DEFAULT_FINANCIAL_RECONCILIATION_PATH,
    resolve_financial_reconciliation_path,
)
from observability.financial_producer import (
    PassiveFinancialProducerResult,
    PassiveFinancialProducerStatus,
)
from observability.financial_runtime_writer import (
    DEFAULT_FIN02_MIN_REFRESH_INTERVAL_S,
    FinancialReconciliationRuntimeWriter,
    FinancialRuntimeRefreshStatus,
    load_financial_runtime_activation_config,
)
from observability.operator_api.financial_reconciliation_reader import (
    DEFAULT_FINANCIAL_RECONCILIATION_PATH as READER_DEFAULT_PATH,
)


def _enabled_env(tmp_path: Path) -> dict[str, str]:
    return {
        "FIN02_RUNTIME_ENABLED": "true",
        "FIN02_RECONCILIATION_CODE_SHA": "d" * 40,
        "FIN02_CONTEXT_EVIDENCE_REF": "F00_CONFIG_FREEZE:test",
        "FIN02_EXPERIMENT_ID": "F00-EPOCH-TEST",
        "FIN02_VENUE": "MEXC_SIM",
        "FIN02_MARKET_TYPE": "PAPER_LINEAR",
        "FINANCIAL_RECONCILIATION_SNAPSHOT_PATH": str(
            tmp_path / "financial.json"
        ),
    }


def _writer(tmp_path: Path, *, wall, mono):
    config = load_financial_runtime_activation_config(_enabled_env(tmp_path))
    assert config is not None
    return FinancialReconciliationRuntimeWriter(
        config,
        wall_time_fn=wall,
        monotonic_fn=mono,
    )


def _written_result(path: Path):
    return PassiveFinancialProducerResult(
        status=PassiveFinancialProducerStatus.WRITTEN,
        capture_id="capture-1",
        runtime_provenance_id="provenance-1",
        artifact_path=str(path),
    )


def test_r4_runtime_activation_is_disabled_by_default():
    assert load_financial_runtime_activation_config({}) is None


def test_r4_enabled_activation_requires_explicit_provenance(tmp_path):
    env = _enabled_env(tmp_path)
    del env["FIN02_RECONCILIATION_CODE_SHA"]

    with pytest.raises(ValueError, match="FIN02_RECONCILIATION_CODE_SHA"):
        load_financial_runtime_activation_config(env)


def test_r4_canonical_producer_reader_path_is_one_contract(tmp_path):
    assert READER_DEFAULT_PATH == DEFAULT_FINANCIAL_RECONCILIATION_PATH

    env = _enabled_env(tmp_path)
    config = load_financial_runtime_activation_config(env)
    assert config is not None
    assert config.artifact_path == resolve_financial_reconciliation_path(env)
    assert config.min_refresh_interval_s == DEFAULT_FIN02_MIN_REFRESH_INTERVAL_S


def test_r4_first_eligible_refresh_writes_then_skips_inside_cadence(
    monkeypatch,
    tmp_path,
):
    import observability.financial_runtime_writer as runtime_writer

    monotonic_values = iter([100.0, 110.0, 131.0])
    wall_values = iter([1_700_000_000.0, 1_700_000_031.0])
    calls = []
    fake_capture = SimpleNamespace(
        capture_id="capture-1",
        runtime_provenance=SimpleNamespace(provenance_id="provenance-1"),
    )

    def _capture(simulator, **kwargs):
        calls.append(("capture", simulator, kwargs))
        return fake_capture

    def _produce(capture, **kwargs):
        calls.append(("produce", capture, kwargs))
        return _written_result(tmp_path / "financial.json")

    monkeypatch.setattr(
        runtime_writer,
        "capture_coherent_financial_boundary",
        _capture,
    )
    monkeypatch.setattr(
        runtime_writer,
        "run_passive_financial_producer",
        _produce,
    )

    writer = _writer(
        tmp_path,
        wall=lambda: next(wall_values),
        mono=lambda: next(monotonic_values),
    )
    simulator = object()

    first = writer.maybe_refresh(simulator)
    skipped = writer.maybe_refresh(simulator)
    second = writer.maybe_refresh(simulator)

    assert first.status is FinancialRuntimeRefreshStatus.WRITTEN
    assert skipped.status is FinancialRuntimeRefreshStatus.SKIPPED_CADENCE
    assert second.status is FinancialRuntimeRefreshStatus.WRITTEN
    assert [kind for kind, *_ in calls] == [
        "capture",
        "produce",
        "capture",
        "produce",
    ]
    assert calls[0][1] is simulator
    assert calls[2][1] is simulator


def test_r4_failed_attempt_is_fail_passive_and_does_not_burst(
    monkeypatch,
    tmp_path,
):
    import observability.financial_runtime_writer as runtime_writer

    monotonic_values = iter([100.0, 101.0, 131.0])
    attempts = []

    def _fail_capture(*args, **kwargs):
        attempts.append("attempt")
        raise RuntimeError("controlled observation failure")

    monkeypatch.setattr(
        runtime_writer,
        "capture_coherent_financial_boundary",
        _fail_capture,
    )

    writer = _writer(
        tmp_path,
        wall=lambda: 1_700_000_000.0,
        mono=lambda: next(monotonic_values),
    )

    failed = writer.maybe_refresh(object())
    skipped = writer.maybe_refresh(object())
    retried = writer.maybe_refresh(object())

    assert failed.status is FinancialRuntimeRefreshStatus.FAILED
    assert failed.error_type == "RuntimeError"
    assert skipped.status is FinancialRuntimeRefreshStatus.SKIPPED_CADENCE
    assert retried.status is FinancialRuntimeRefreshStatus.FAILED
    assert attempts == ["attempt", "attempt"]


def test_r4_producer_failure_is_returned_not_raised(monkeypatch, tmp_path):
    import observability.financial_runtime_writer as runtime_writer

    fake_capture = SimpleNamespace(
        capture_id="capture-1",
        runtime_provenance=SimpleNamespace(provenance_id="provenance-1"),
    )

    monkeypatch.setattr(
        runtime_writer,
        "capture_coherent_financial_boundary",
        lambda *args, **kwargs: fake_capture,
    )
    monkeypatch.setattr(
        runtime_writer,
        "run_passive_financial_producer",
        lambda *args, **kwargs: PassiveFinancialProducerResult(
            status=PassiveFinancialProducerStatus.FAILED,
            capture_id="capture-1",
            runtime_provenance_id="provenance-1",
            artifact_path=str(tmp_path / "financial.json"),
            error_type="OSError",
            error_message="controlled write failure",
        ),
    )

    writer = _writer(
        tmp_path,
        wall=lambda: 1_700_000_000.0,
        mono=lambda: 100.0,
    )
    result = writer.maybe_refresh(object())

    assert result.status is FinancialRuntimeRefreshStatus.FAILED
    assert result.error_type == "OSError"
    assert result.error_message == "controlled write failure"


def test_r4_source_has_no_background_or_authority_constructor():
    source = Path("observability/financial_runtime_writer.py").read_text(
        encoding="utf-8"
    )

    for forbidden in (
        "import threading",
        "MexcSimulator(",
        "PPLAuthorityRuntime(",
        "ccxt.",
    ):
        assert forbidden not in source


def test_r4_advisor_call_is_end_of_cycle_and_defensively_fail_passive():
    source = Path("core/advisor_loop.py").read_text(encoding="utf-8")
    operator_idx = source.index(
        "# ── O-02W-C — Canonical operator snapshot (passif, ADR-0007)"
    )
    fin_idx = source.index(
        "# ── FIN-02R4 — Passive financial reconciliation observer"
    )
    watchdog_idx = source.index("# Watchdog fin de cycle", fin_idx)

    assert operator_idx < fin_idx < watchdog_idx
    block = source[fin_idx:watchdog_idx]
    assert "_fin02_runtime_writer.maybe_refresh(" in block
    assert "_virtual_portfolio" in block
    assert "except Exception as _fin02_runtime_exc" in block
