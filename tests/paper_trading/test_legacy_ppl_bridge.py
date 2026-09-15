"""PPL-02C proof matrix for the read-only legacy PAPER bridge."""

from __future__ import annotations

import inspect
import json
import os
from collections import Counter
from pathlib import Path

import pytest

from paper_trading import durable_event_store as store_module
from paper_trading import legacy_ppl_bridge as bridge_module
from paper_trading.durable_event_store import AppendStatus, DurableEventStore
from paper_trading.ledger_events import LedgerEventType
from paper_trading.legacy_ppl_bridge import (
    LegacyContextProvenance,
    LegacyImportBlockedError,
    LegacyImportContext,
    LegacyImportContextError,
    LegacyImportPlanStatus,
    LegacyLifecycleStatus,
    LegacyReasonCode,
    LegacySourceChangedError,
    LegacySourceCorruptionError,
    LegacySourceNotFoundError,
    apply_legacy_import_plan,
    build_legacy_import_plan,
    inspect_legacy_journal,
)
from paper_trading.paper_portfolio_ledger import project

SOURCE_LABEL = "databases/paper_trades.jsonl"


def opened(
    trade_id="trade-1",
    *,
    timestamp=10.0,
    side="buy",
    mode="futures_demo",
    entry_fee=0.1,
    schema_version=5,
    symbol="BTC/USDT",
    size=100.0,
    price=100.0,
):
    record = {
        "event": "OPEN",
        "trade_id": trade_id,
        "ts": timestamp,
        "ts_iso": "1970-01-01T00:00:10Z",
        "symbol": symbol,
        "side": side,
        "price": price,
        "size_usd": size,
        "mode": mode,
        "schema_version": schema_version,
        "regime": "unknown",
        "score": 70,
        "score_bin": "70+",
        "order_id": trade_id,
        "runtime_config_version": "cfg-v1",
        "market_context": None,
        "decision_context": None,
    }
    if entry_fee is not ...:
        record["fee_entry_usd"] = entry_fee
    return record


def closed(
    trade_id="trade-1",
    *,
    timestamp=20.0,
    side="buy",
    mode="futures_demo",
    exit_fee=0.1,
    exit_price=110.0,
    pnl_usd=9.8,
    reason="take_profit",
    evidence_incomplete=False,
    symbol="BTC/USDT",
    size=100.0,
):
    record = {
        "event": "CLOSE",
        "trade_id": trade_id,
        "ts": timestamp,
        "ts_iso": "1970-01-01T00:00:20Z",
        "symbol": symbol,
        "side": side,
        "price": exit_price,
        "size_usd": size,
        "mode": mode,
        "schema_version": 5,
        "exit_price": exit_price,
        "pnl_usd": pnl_usd,
        "pnl_pct": 0.1,
        "reason": reason,
        "pnl_fee_evidence_incomplete": evidence_incomplete,
    }
    if exit_fee is not ...:
        record["exit_fee"] = exit_fee
    return record


def write_journal(path: Path, records, *, final_newline=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        for record in records
    )
    if final_newline and records:
        text += "\n"
    path.write_text(text, encoding="utf-8")
    return path


def snapshot(path: Path):
    return inspect_legacy_journal(path, source_label=SOURCE_LABEL)


def context(source_snapshot, **overrides):
    values = {
        "expected_source_sha256": source_snapshot.provenance.sha256,
        "paper_epoch_id": "legacy-evidenced-epoch-1",
        "epoch_created_at": 1.0,
        "initial_virtual_capital": 1_000.0,
        "code_sha": "0123456789abcdef",
        "config_snapshot_hash": "cfg-snapshot-sha256",
        "provenance": LegacyContextProvenance.EXTERNALLY_EVIDENCED,
    }
    values.update(overrides)
    return LegacyImportContext(**values)


def ready_snapshot(tmp_path):
    path = write_journal(
        tmp_path / "legacy.jsonl",
        [opened(), closed()],
    )
    return path, snapshot(path)


def test_c01_inspect_valid_paired_lifecycle(tmp_path):
    path, inspected = ready_snapshot(tmp_path)

    assert inspected.provenance.byte_length == path.stat().st_size
    assert inspected.provenance.line_count == 2
    assert inspected.open_count == 1
    assert inspected.close_count == 1
    assert inspected.schema_counts == (("5", 2),)
    assert inspected.status is LegacyImportPlanStatus.READY
    assert inspected.assessments == (
        bridge_module.LegacyLifecycleAssessment(
            trade_id="trade-1",
            open_line_number=1,
            close_line_number=2,
            status=LegacyLifecycleStatus.IMPORTABLE,
        ),
    )


def test_c02_source_and_line_hashes_are_exact_and_deterministic(tmp_path):
    path, first = ready_snapshot(tmp_path)
    second = snapshot(path)
    raw = path.read_bytes()

    assert first == second
    assert first.provenance.sha256 == bridge_module.hashlib.sha256(raw).hexdigest()
    lines = raw.splitlines(keepends=True)
    assert [record.line_sha256 for record in first._records] == [
        bridge_module.hashlib.sha256(line).hexdigest() for line in lines
    ]


def test_c03_inspection_does_not_modify_source_bytes_or_durable_metadata(tmp_path):
    path, _ = ready_snapshot(tmp_path)
    before_bytes = path.read_bytes()
    before = path.stat()

    snapshot(path)

    after = path.stat()
    assert path.read_bytes() == before_bytes
    assert (after.st_mode, after.st_size, after.st_mtime_ns) == (
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    )


def test_c04_appended_prefix_preserves_prior_event_ids(tmp_path):
    path, first_snapshot = ready_snapshot(tmp_path)
    first_plan = build_legacy_import_plan(first_snapshot, context(first_snapshot))

    records = [
        opened(),
        closed(),
        opened("trade-2", timestamp=30.0, symbol="ETH/USDT"),
        closed(
            "trade-2",
            timestamp=40.0,
            symbol="ETH/USDT",
            pnl_usd=9.8,
        ),
    ]
    write_journal(path, records)
    second_snapshot = snapshot(path)
    second_plan = build_legacy_import_plan(second_snapshot, context(second_snapshot))

    assert [event.event_id for event in first_plan.events] == [
        event.event_id for event in second_plan.events[:3]
    ]
    assert [event.sequence for event in second_plan.events] == [1, 2, 3, 4, 5]


def test_c04_event_id_exposes_exact_line_provenance(tmp_path):
    _, inspected = ready_snapshot(tmp_path)
    plan = build_legacy_import_plan(inspected, context(inspected))

    for event, record in zip(plan.events[1:], inspected._records, strict=True):
        assert f"-line-{record.line_number}-" in event.event_id
        assert record.line_sha256 in event.event_id


def test_c04_logical_source_label_domain_separates_record_ids(tmp_path):
    path, first = ready_snapshot(tmp_path)
    second = inspect_legacy_journal(path, source_label="evidence/other-journal.jsonl")

    first_plan = build_legacy_import_plan(first, context(first))
    second_plan = build_legacy_import_plan(second, context(second))

    assert first_plan.events[0].event_id == second_plan.events[0].event_id
    assert [event.event_id for event in first_plan.events[1:]] != [
        event.event_id for event in second_plan.events[1:]
    ]


def test_c05_missing_final_newline_fails_closed(tmp_path):
    path = write_journal(tmp_path / "legacy.jsonl", [opened()], final_newline=False)

    with pytest.raises(LegacySourceCorruptionError, match="final newline"):
        snapshot(path)


def test_c05_empty_source_fails_closed(tmp_path):
    path = tmp_path / "legacy.jsonl"
    path.write_bytes(b"")

    with pytest.raises(LegacySourceCorruptionError, match="empty"):
        snapshot(path)


def test_c06_malformed_json_in_middle_fails_closed(tmp_path):
    path = write_journal(tmp_path / "legacy.jsonl", [opened(), closed()])
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(lines[0] + b"{BROKEN}\n" + lines[1])

    with pytest.raises(LegacySourceCorruptionError, match="line 2"):
        snapshot(path)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"event":"OPEN","event":"CLOSE"}\n',
        b'{"event":"OPEN","trade_id":"t","ts":NaN}\n',
    ],
)
def test_c07_duplicate_keys_and_nonfinite_constants_fail_closed(tmp_path, raw):
    path = tmp_path / "legacy.jsonl"
    path.write_bytes(raw)

    with pytest.raises(LegacySourceCorruptionError):
        snapshot(path)


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff\n",
        b"\n",
        b"[]\n",
    ],
)
def test_c07_invalid_utf8_blank_and_nonobject_records_fail_closed(tmp_path, raw):
    path = tmp_path / "legacy.jsonl"
    path.write_bytes(raw)

    with pytest.raises(LegacySourceCorruptionError):
        snapshot(path)


def test_c08_detected_source_mutation_fails_closed(tmp_path, monkeypatch):
    path, _ = ready_snapshot(tmp_path)
    real_read = bridge_module._read_descriptor

    def mutate_after_read(descriptor):
        raw = real_read(descriptor)
        with path.open("ab") as stream:
            stream.write(b"{}\n")
            stream.flush()
            os.fsync(stream.fileno())
        return raw

    monkeypatch.setattr(bridge_module, "_read_descriptor", mutate_after_read)

    with pytest.raises(LegacySourceChangedError):
        snapshot(path)


def test_c08_same_size_rewrite_with_restored_mtime_fails_closed(tmp_path, monkeypatch):
    path, _ = ready_snapshot(tmp_path)
    before = path.stat()
    real_read = bridge_module._read_descriptor

    def rewrite_after_read(descriptor):
        raw = real_read(descriptor)
        replacement = bytearray(raw)
        replacement[0] = ord("{") if replacement[0] != ord("{") else ord(" ")
        path.write_bytes(replacement)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        return raw

    monkeypatch.setattr(bridge_module, "_read_descriptor", rewrite_after_read)

    with pytest.raises(LegacySourceChangedError):
        snapshot(path)


def test_c09_symlink_nonregular_and_missing_source_fail_closed(tmp_path):
    target = write_journal(tmp_path / "target.jsonl", [opened()])
    link = tmp_path / "link.jsonl"
    link.symlink_to(target)

    with pytest.raises(LegacySourceCorruptionError, match="non-symlink"):
        snapshot(link)
    with pytest.raises(LegacySourceCorruptionError, match="regular"):
        snapshot(tmp_path)
    with pytest.raises(LegacySourceNotFoundError):
        snapshot(tmp_path / "missing.jsonl")


@pytest.mark.parametrize(
    ("records", "reason"),
    [
        ([closed()], LegacyReasonCode.ORPHAN_CLOSE),
        ([opened(), opened(timestamp=11.0)], LegacyReasonCode.DUPLICATE_OPEN),
        (
            [opened(), closed(), closed(timestamp=21.0)],
            LegacyReasonCode.DUPLICATE_CLOSE,
        ),
        (
            [closed(timestamp=10.0), opened(timestamp=20.0)],
            LegacyReasonCode.CLOSE_BEFORE_OPEN,
        ),
        (
            [opened(timestamp=20.0), closed(timestamp=10.0)],
            LegacyReasonCode.TIMESTAMP_REGRESSION,
        ),
    ],
)
def test_c10_invalid_lifecycle_is_rejected(tmp_path, records, reason):
    path = write_journal(tmp_path / "legacy.jsonl", records)

    inspected = snapshot(path)

    assert inspected.status is LegacyImportPlanStatus.BLOCKED
    assert inspected.assessments[0].status is LegacyLifecycleStatus.REJECTED
    assert reason in inspected.assessments[0].reason_codes


def test_c10_global_timestamp_regression_and_field_mismatch_are_rejected(tmp_path):
    path = write_journal(
        tmp_path / "legacy.jsonl",
        [
            opened("trade-1", timestamp=20.0),
            opened("trade-2", timestamp=10.0, symbol="ETH/USDT"),
            closed("trade-1", timestamp=30.0, symbol="ETH/USDT"),
        ],
    )

    inspected = snapshot(path)
    by_trade = {item.trade_id: item for item in inspected.assessments}

    assert (
        LegacyReasonCode.GLOBAL_TIMESTAMP_REGRESSION in by_trade["trade-2"].reason_codes
    )
    assert LegacyReasonCode.LIFECYCLE_FIELD_MISMATCH in by_trade["trade-1"].reason_codes


def test_c10_equivalent_side_aliases_do_not_create_false_mismatch(tmp_path):
    path = write_journal(
        tmp_path / "legacy.jsonl",
        [opened(side="BUY"), closed(side="LONG")],
    )

    inspected = snapshot(path)

    assert inspected.assessments[0].status is LegacyLifecycleStatus.IMPORTABLE


def test_c10_equal_exit_fee_aliases_are_accepted_but_conflicts_are_rejected(tmp_path):
    accepted = closed(exit_fee=0.1)
    accepted["fee_exit_usd"] = 0.1
    accepted_path = write_journal(tmp_path / "accepted.jsonl", [opened(), accepted])
    assert snapshot(accepted_path).status is LegacyImportPlanStatus.READY

    rejected = closed(exit_fee=0.1)
    rejected["fee_exit_usd"] = 0.2
    rejected_path = write_journal(tmp_path / "rejected.jsonl", [opened(), rejected])
    assessment = snapshot(rejected_path).assessments[0]
    assert assessment.status is LegacyLifecycleStatus.REJECTED
    assert LegacyReasonCode.AMBIGUOUS_EXIT_FEE in assessment.reason_codes


@pytest.mark.parametrize(
    ("record", "reason"),
    [
        (opened(mode="live"), LegacyReasonCode.INVALID_MODE),
        (opened(side="mystery"), LegacyReasonCode.INVALID_SIDE),
    ],
)
def test_c11_real_mode_and_unknown_side_are_rejected(tmp_path, record, reason):
    path = write_journal(tmp_path / "legacy.jsonl", [record])

    inspected = snapshot(path)

    assessment = inspected.assessments[0]
    assert assessment.status is LegacyLifecycleStatus.REJECTED
    assert reason in assessment.reason_codes


def test_c11_absent_schema_is_preserved_and_unsupported_schema_is_rejected(tmp_path):
    legacy_open = opened(schema_version=5)
    legacy_open.pop("schema_version")
    absent_path = write_journal(tmp_path / "absent.jsonl", [legacy_open])

    absent = snapshot(absent_path)
    assert absent.schema_counts == (("MISSING", 1),)
    assert absent.assessments[0].status is LegacyLifecycleStatus.IMPORTABLE

    unsupported_path = write_journal(
        tmp_path / "unsupported.jsonl", [opened(schema_version=6)]
    )
    unsupported = snapshot(unsupported_path).assessments[0]
    assert unsupported.status is LegacyLifecycleStatus.REJECTED
    assert LegacyReasonCode.UNSUPPORTED_SCHEMA in unsupported.reason_codes


def test_c12_missing_entry_fee_is_unresolved_and_blocks_all_events(tmp_path):
    path = write_journal(
        tmp_path / "legacy.jsonl",
        [opened(entry_fee=...), closed(exit_fee=...)],
    )
    inspected = snapshot(path)

    assert inspected.assessments[0].status is LegacyLifecycleStatus.UNRESOLVED
    assert LegacyReasonCode.MISSING_ENTRY_FEE in inspected.assessments[0].reason_codes

    plan = build_legacy_import_plan(inspected, context(inspected))
    assert plan.status is LegacyImportPlanStatus.BLOCKED
    assert plan.events == ()


def test_c13_missing_exit_fee_maps_to_explicit_ppl_unresolved(tmp_path):
    path = write_journal(
        tmp_path / "legacy.jsonl",
        [opened(), closed(exit_fee=...)],
    )
    inspected = snapshot(path)

    assessment = inspected.assessments[0]
    assert assessment.status is LegacyLifecycleStatus.IMPORTABLE_AS_UNRESOLVED
    assert LegacyReasonCode.MISSING_EXIT_FEE in assessment.reason_codes

    plan = build_legacy_import_plan(inspected, context(inspected))
    assert plan.status is LegacyImportPlanStatus.READY
    assert [event.event_type for event in plan.events] == [
        LedgerEventType.EPOCH_CREATED,
        LedgerEventType.POSITION_OPENED,
        LedgerEventType.POSITION_UNRESOLVED,
    ]


@pytest.mark.parametrize(
    "close_record",
    [
        closed(exit_fee=..., evidence_incomplete=True),
        closed(
            exit_fee=..., exit_price=None, pnl_usd=None, reason="expired_on_restore"
        ),
    ],
)
def test_c14_incomplete_fee_or_expired_restore_stays_unresolved(tmp_path, close_record):
    path = write_journal(tmp_path / "legacy.jsonl", [opened(), close_record])
    inspected = snapshot(path)

    assert (
        inspected.assessments[0].status
        is LegacyLifecycleStatus.IMPORTABLE_AS_UNRESOLVED
    )
    plan = build_legacy_import_plan(inspected, context(inspected))
    assert plan.events[-1].event_type is LedgerEventType.POSITION_UNRESOLVED


def test_c14_declared_incomplete_pnl_is_not_treated_as_a_known_contradiction(
    tmp_path,
):
    path = write_journal(
        tmp_path / "legacy.jsonl",
        [opened(), closed(exit_fee=0.1, evidence_incomplete=True, pnl_usd=-999.0)],
    )

    inspected = snapshot(path)

    assessment = inspected.assessments[0]
    assert assessment.status is LegacyLifecycleStatus.IMPORTABLE_AS_UNRESOLVED
    assert LegacyReasonCode.REPORTED_PNL_CONFLICT not in assessment.reason_codes


def test_c15_bridge_never_infers_fees_from_reported_pnl_or_environment(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MEXC_SIM_FEE", "0.001")
    path = write_journal(
        tmp_path / "legacy.jsonl",
        [opened(entry_fee=...), closed(exit_fee=..., pnl_usd=9.8)],
    )

    inspected = snapshot(path)

    assert inspected.assessments[0].status is LegacyLifecycleStatus.UNRESOLVED
    assert {
        LegacyReasonCode.MISSING_ENTRY_FEE,
        LegacyReasonCode.MISSING_EXIT_FEE,
    }.issubset(inspected.assessments[0].reason_codes)


def test_c16_explicit_source_digest_and_epoch_context_are_mandatory(tmp_path):
    _, inspected = ready_snapshot(tmp_path)

    with pytest.raises(LegacyImportContextError, match="SHA-256"):
        context(inspected, expected_source_sha256="not-a-digest")
    wrong = context(inspected, expected_source_sha256="0" * 64)
    with pytest.raises(LegacyImportContextError, match="does not match"):
        build_legacy_import_plan(inspected, wrong)
    with pytest.raises(LegacyImportContextError, match="EXTERNALLY_EVIDENCED"):
        context(inspected, provenance="ASSUMED")


def test_c16a_epoch_creation_cannot_postdate_legacy_events(tmp_path):
    _, inspected = ready_snapshot(tmp_path)

    with pytest.raises(LegacyImportContextError, match="not be later"):
        build_legacy_import_plan(inspected, context(inspected, epoch_created_at=10.1))

    plan = build_legacy_import_plan(
        inspected, context(inspected, epoch_created_at=10.0)
    )
    assert plan.events[0].timestamp == 10.0


def test_blocked_invalid_timestamp_returns_empty_plan_without_conversion_crash(
    tmp_path,
):
    path = write_journal(tmp_path / "legacy.jsonl", [opened(timestamp="invalid")])
    inspected = snapshot(path)

    plan = build_legacy_import_plan(inspected, context(inspected))

    assert plan.status is LegacyImportPlanStatus.BLOCKED
    assert plan.events == ()


def test_c17_fully_evidenced_fixture_produces_strict_ppl_sequence(tmp_path):
    _, inspected = ready_snapshot(tmp_path)

    plan = build_legacy_import_plan(inspected, context(inspected))

    assert plan.status is LegacyImportPlanStatus.READY
    assert [event.sequence for event in plan.events] == [1, 2, 3]
    assert [event.event_type for event in plan.events] == [
        LedgerEventType.EPOCH_CREATED,
        LedgerEventType.POSITION_OPENED,
        LedgerEventType.POSITION_CLOSED,
    ]
    assert all(
        event.paper_epoch_id == "legacy-evidenced-epoch-1" for event in plan.events
    )


@pytest.mark.parametrize("lifecycle_count", [1, 2, 8])
def test_c17_interleaved_lifecycles_preserve_physical_order_and_replay(
    tmp_path, lifecycle_count
):
    records = [
        opened(f"trade-{index}", timestamp=10.0 + index)
        for index in range(lifecycle_count)
    ]
    records.extend(
        closed(f"trade-{index}", timestamp=100.0 + index)
        for index in range(lifecycle_count)
    )
    path = write_journal(tmp_path / "legacy.jsonl", records)
    inspected = snapshot(path)

    plan = build_legacy_import_plan(
        inspected, context(inspected, initial_virtual_capital=10_000.0)
    )
    state = project(plan.events)

    assert [event.sequence for event in plan.events] == list(range(1, len(records) + 2))
    assert state.realized_pnl == pytest.approx(9.8 * lifecycle_count)
    assert state.open_positions == {}


def test_c18_generated_events_replay_deterministically(tmp_path):
    _, inspected = ready_snapshot(tmp_path)
    plan = build_legacy_import_plan(inspected, context(inspected))

    first = project(plan.events)
    second = project(plan.events)

    assert first == second
    assert first.realized_pnl == pytest.approx(9.8)
    assert first.open_positions == {}


def test_c19_reported_pnl_contradiction_rejects_import(tmp_path):
    path = write_journal(
        tmp_path / "legacy.jsonl",
        [opened(), closed(pnl_usd=-999.0)],
    )
    inspected = snapshot(path)

    assessment = inspected.assessments[0]
    assert assessment.status is LegacyLifecycleStatus.REJECTED
    assert LegacyReasonCode.REPORTED_PNL_CONFLICT in assessment.reason_codes


def test_c19_short_pnl_consistency_uses_canonical_side_direction(tmp_path):
    path = write_journal(
        tmp_path / "legacy.jsonl",
        [
            opened(side="SELL"),
            closed(side="SHORT", exit_price=90.0, pnl_usd=9.8),
        ],
    )

    inspected = snapshot(path)
    plan = build_legacy_import_plan(inspected, context(inspected))

    assert inspected.status is LegacyImportPlanStatus.READY
    assert project(plan.events).realized_pnl == pytest.approx(9.8)


def test_c20_any_unmappable_lifecycle_yields_no_partial_events(tmp_path):
    path = write_journal(
        tmp_path / "legacy.jsonl",
        [
            opened(),
            closed(),
            opened("trade-2", timestamp=30.0, entry_fee=..., symbol="ETH/USDT"),
        ],
    )
    inspected = snapshot(path)

    plan = build_legacy_import_plan(inspected, context(inspected))

    assert Counter(item.status for item in plan.assessments) == {
        LegacyLifecycleStatus.IMPORTABLE: 1,
        LegacyLifecycleStatus.UNRESOLVED: 1,
    }
    assert plan.status is LegacyImportPlanStatus.BLOCKED
    assert plan.events == ()


def test_c21_identical_plans_are_logically_equal(tmp_path):
    path, first_snapshot = ready_snapshot(tmp_path)
    second_snapshot = snapshot(path)

    first = build_legacy_import_plan(first_snapshot, context(first_snapshot))
    second = build_legacy_import_plan(second_snapshot, context(second_snapshot))

    assert first == second


def test_c22_offline_apply_is_idempotent_across_reopen(tmp_path):
    _, inspected = ready_snapshot(tmp_path)
    plan = build_legacy_import_plan(inspected, context(inspected))
    root = tmp_path / "ppl"

    first = apply_legacy_import_plan(plan, DurableEventStore(root))
    second = apply_legacy_import_plan(plan, DurableEventStore(root))

    assert [result.status for result in first] == [AppendStatus.APPENDED] * 3
    assert [result.status for result in second] == [AppendStatus.ALREADY_EXISTS] * 3
    assert (
        DurableEventStore(root).load_epoch(plan.context.paper_epoch_id) == plan.events
    )


def test_c23_target_fsync_failure_never_reports_full_success(tmp_path, monkeypatch):
    _, inspected = ready_snapshot(tmp_path)
    plan = build_legacy_import_plan(inspected, context(inspected))

    def fail_fsync(_descriptor):
        raise OSError("injected target fsync failure")

    monkeypatch.setattr(store_module.os, "fsync", fail_fsync)

    with pytest.raises(OSError, match="target fsync"):
        apply_legacy_import_plan(plan, DurableEventStore(tmp_path / "ppl"))


def test_blocked_plan_refuses_target_io_before_store_construction_side_effect(tmp_path):
    path = write_journal(tmp_path / "legacy.jsonl", [opened(entry_fee=...)])
    inspected = snapshot(path)
    plan = build_legacy_import_plan(inspected, context(inspected))
    target = tmp_path / "never-created"

    with pytest.raises(LegacyImportBlockedError):
        apply_legacy_import_plan(plan, DurableEventStore(target))

    assert not target.exists()


def test_c24_no_production_default_or_import_time_side_effect(tmp_path):
    source = tmp_path / "never-read.jsonl"
    signature = inspect.signature(inspect_legacy_journal)

    assert signature.parameters["source_path"].default is inspect.Parameter.empty
    assert signature.parameters["source_label"].default is inspect.Parameter.empty
    assert not source.exists()

    with pytest.raises(ValueError, match="source_label"):
        inspect_legacy_journal(source, source_label="   ")


def test_c25_production_modules_do_not_import_or_construct_bridge():
    repository_root = Path(__file__).resolve().parents[2]
    bridge_path = repository_root / "paper_trading" / "legacy_ppl_bridge.py"
    production_paths = (
        path
        for path in repository_root.rglob("*.py")
        if path != bridge_path
        and "tests" not in path.relative_to(repository_root).parts
        and ".git" not in path.relative_to(repository_root).parts
    )

    for path in production_paths:
        assert "legacy_ppl_bridge" not in path.read_text(encoding="utf-8")


def test_c26_legacy_source_is_untouched_and_no_partial_target_is_created(tmp_path):
    legacy = write_journal(
        tmp_path / "databases" / "paper_trades.jsonl",
        [opened(entry_fee=...), closed(exit_fee=...)],
    )
    sentinel = legacy.read_bytes()
    before = legacy.stat()
    inspected = inspect_legacy_journal(legacy, source_label=SOURCE_LABEL)
    plan = build_legacy_import_plan(inspected, context(inspected))
    target = tmp_path / "new-ppl-store"

    with pytest.raises(LegacyImportBlockedError):
        apply_legacy_import_plan(plan, DurableEventStore(target))

    after = legacy.stat()
    assert legacy.read_bytes() == sentinel
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)
    assert not target.exists()
