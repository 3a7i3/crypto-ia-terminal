"""PPL-02B proof matrix for the durable PAPER event store."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import stat
from pathlib import Path

import pytest

import paper_trading.durable_event_store as store_module
from paper_trading.durable_event_store import (
    AppendStatus,
    DurableEventStore,
    EpochNotFoundError,
    EventDeserializationError,
    EventIdentityCollisionError,
    EventSerializationError,
    EventStoreError,
    StoreCorruptionError,
    StoreEpochMismatchError,
    StoreSequenceGapError,
    StoreSequenceRegressionError,
    UnsupportedSchemaVersionError,
)
from paper_trading.ledger_events import (
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
    make_recovery_completed_event,
)
from paper_trading.paper_portfolio_ledger import project

EPOCH_A = "pe-ppl-02b-a"
EPOCH_B = "pe-ppl-02b-b"


def epoch_created(*, epoch_id=EPOCH_A, event_id="ev-1", sequence=1, timestamp=1.0):
    return make_epoch_created_event(
        event_id=event_id,
        paper_epoch_id=epoch_id,
        sequence=sequence,
        timestamp=timestamp,
        initial_virtual_capital=100.0,
        code_sha="f9fff2f",
        config_snapshot_hash="cfg-ppl-02b",
    )


def recovery(*, epoch_id=EPOCH_A, event_id="ev-rec", sequence=2, timestamp=2.0):
    return make_recovery_completed_event(
        event_id=event_id,
        paper_epoch_id=epoch_id,
        sequence=sequence,
        timestamp=timestamp,
        restored_count=0,
        unresolved_count=0,
    )


def opened(*, epoch_id=EPOCH_A, event_id="ev-open", sequence=2, trade_id="trade-1"):
    return make_position_opened_event(
        event_id=event_id,
        paper_epoch_id=epoch_id,
        sequence=sequence,
        timestamp=float(sequence),
        trade_id=trade_id,
        symbol="BTCUSDT",
        side="LONG",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
        decision_id="decision-1",
    )


def closed(*, epoch_id=EPOCH_A, event_id="ev-close", sequence=3, trade_id="trade-1"):
    return make_position_closed_event(
        event_id=event_id,
        paper_epoch_id=epoch_id,
        sequence=sequence,
        timestamp=float(sequence),
        trade_id=trade_id,
        exit_price=110.0,
        exit_fee=0.01,
        decision_id="decision-1",
    )


def epoch_path(root: Path, epoch_id: str) -> Path:
    digest = hashlib.sha256(epoch_id.encode("utf-8")).hexdigest()
    return root / "epochs" / f"{digest}.jsonl"


def write_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def canonical_record(event) -> dict:
    payload = dict(event.payload)
    return {
        "decision_id": event.decision_id,
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "paper_epoch_id": event.paper_epoch_id,
        "payload": payload,
        "schema_version": event.schema_version,
        "sequence": event.sequence,
        "timestamp": event.timestamp,
        "trade_id": event.trade_id,
    }


def concurrent_append_worker(root, start, results, event_id):
    store = DurableEventStore(root)
    event = recovery(event_id=event_id, sequence=2)
    start.wait(timeout=5)
    try:
        outcome = store.append(EPOCH_A, event)
        results.put(outcome.status.value)
    except EventStoreError as exc:  # child returns the competing store verdict
        results.put(type(exc).__name__)


def test_t01_append_first_event(tmp_path):
    root = tmp_path / "ppl"
    result = DurableEventStore(root).append(EPOCH_A, epoch_created())

    assert result.status is AppendStatus.APPENDED
    raw = epoch_path(root, EPOCH_A).read_bytes()
    assert raw.endswith(b"\n")
    assert raw.count(b"\n") == 1


def test_t02_append_n_sequential_events(tmp_path):
    store = DurableEventStore(tmp_path / "ppl")
    expected = [epoch_created()]
    expected.extend(
        recovery(
            event_id=f"ev-{sequence}", sequence=sequence, timestamp=float(sequence)
        )
        for sequence in range(2, 22)
    )

    for event in expected:
        assert store.append(EPOCH_A, event).status is AppendStatus.APPENDED

    assert store.load_epoch(EPOCH_A) == tuple(expected)


def test_t03_close_reopen_store_and_reload_identically(tmp_path):
    root = tmp_path / "ppl"
    events = (epoch_created(), opened(), closed())
    first_store = DurableEventStore(root)
    for event in events:
        first_store.append(EPOCH_A, event)

    reopened = DurableEventStore(root)
    assert reopened.load_epoch(EPOCH_A) == events


def test_t04_deterministic_serialization_and_reload(tmp_path):
    root = tmp_path / "ppl"
    store = DurableEventStore(root)
    events = (epoch_created(), opened(), closed())
    for event in events:
        store.append(EPOCH_A, event)
    before = epoch_path(root, EPOCH_A).read_bytes()

    for event in events:
        assert store.append(EPOCH_A, event).status is AppendStatus.ALREADY_EXISTS

    after = epoch_path(root, EPOCH_A).read_bytes()
    assert after == before
    assert DurableEventStore(root).load_epoch(EPOCH_A) == events


def test_t05_duplicate_event_id_with_identical_payload_is_idempotent(tmp_path):
    root = tmp_path / "ppl"
    store = DurableEventStore(root)
    event = epoch_created()
    store.append(EPOCH_A, event)
    size_before = epoch_path(root, EPOCH_A).stat().st_size

    result = store.append(EPOCH_A, event)

    assert result.status is AppendStatus.ALREADY_EXISTS
    assert epoch_path(root, EPOCH_A).stat().st_size == size_before


def test_t06_duplicate_event_id_with_different_payload_is_rejected(tmp_path):
    store = DurableEventStore(tmp_path / "ppl")
    store.append(EPOCH_A, epoch_created())
    collision = epoch_created(timestamp=999.0)

    with pytest.raises(EventIdentityCollisionError):
        store.append(EPOCH_A, collision)


def test_t07_sequence_regression_is_rejected(tmp_path):
    store = DurableEventStore(tmp_path / "ppl")
    store.append(EPOCH_A, epoch_created())

    with pytest.raises(StoreSequenceRegressionError):
        store.append(EPOCH_A, recovery(event_id="other-id", sequence=1))


def test_t08_sequence_gap_is_rejected(tmp_path):
    store = DurableEventStore(tmp_path / "ppl")
    store.append(EPOCH_A, epoch_created())

    with pytest.raises(StoreSequenceGapError):
        store.append(EPOCH_A, recovery(event_id="ev-gap", sequence=3))


def test_t09_wrong_epoch_append_is_rejected_before_io(tmp_path):
    root = tmp_path / "ppl"

    with pytest.raises(StoreEpochMismatchError):
        DurableEventStore(root).append(EPOCH_A, epoch_created(epoch_id=EPOCH_B))

    assert not root.exists()


def test_t10_malformed_json_in_middle_fails_closed(tmp_path):
    root = tmp_path / "ppl"
    store = DurableEventStore(root)
    for event in (epoch_created(), recovery(), recovery(event_id="ev-3", sequence=3)):
        store.append(EPOCH_A, event)
    path = epoch_path(root, EPOCH_A)
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(lines[0] + b"{BROKEN}\n" + lines[2])

    with pytest.raises(EventDeserializationError):
        store.load_epoch(EPOCH_A)


def test_t11_truncated_final_json_fails_closed(tmp_path):
    root = tmp_path / "ppl"
    store = DurableEventStore(root)
    store.append(EPOCH_A, epoch_created())
    store.append(EPOCH_A, recovery())
    path = epoch_path(root, EPOCH_A)
    path.write_bytes(path.read_bytes()[:-8])

    with pytest.raises(StoreCorruptionError):
        store.load_epoch(EPOCH_A)


def test_t12_valid_final_json_without_newline_fails_closed(tmp_path):
    root = tmp_path / "ppl"
    store = DurableEventStore(root)
    store.append(EPOCH_A, epoch_created())
    path = epoch_path(root, EPOCH_A)
    path.write_bytes(path.read_bytes().removesuffix(b"\n"))

    with pytest.raises(StoreCorruptionError, match="final newline"):
        store.load_epoch(EPOCH_A)


@pytest.mark.parametrize("mutation", ["missing", "extra", "event_type", "payload"])
def test_t13_malformed_event_schema_fails_closed(tmp_path, mutation):
    root = tmp_path / mutation
    record = canonical_record(epoch_created())
    if mutation == "missing":
        del record["timestamp"]
    elif mutation == "extra":
        record["invented"] = True
    elif mutation == "event_type":
        record["event_type"] = "INVENTED"
    else:
        record["payload"] = {"initial_virtual_capital": 100.0}
    write_record(epoch_path(root, EPOCH_A), record)

    with pytest.raises(EventDeserializationError):
        DurableEventStore(root).load_epoch(EPOCH_A)


def test_t13_unsupported_schema_version_fails_closed(tmp_path):
    root = tmp_path / "ppl"
    record = canonical_record(epoch_created())
    record["schema_version"] = 3
    write_record(epoch_path(root, EPOCH_A), record)

    with pytest.raises(UnsupportedSchemaVersionError):
        DurableEventStore(root).load_epoch(EPOCH_A)


@pytest.mark.parametrize(
    ("field", "value"),
    [("schema_version", True), ("trade_id", None), ("event_id", "trade-1")],
)
def test_t13_append_rejects_forged_event_that_violates_domain_schema(
    tmp_path, field, value
):
    root = tmp_path / "ppl"
    event = opened()
    object.__setattr__(event, field, value)

    with pytest.raises(EventSerializationError):
        DurableEventStore(root).append(EPOCH_A, event)

    assert not root.exists()


def test_t14_reload_preserves_strict_sequence_order(tmp_path):
    store = DurableEventStore(tmp_path / "ppl")
    events = (
        epoch_created(),
        recovery(),
        recovery(event_id="ev-3", sequence=3, timestamp=0.5),
    )
    for event in events:
        store.append(EPOCH_A, event)

    loaded = store.load_epoch(EPOCH_A)
    assert [event.sequence for event in loaded] == [1, 2, 3]
    assert [event.timestamp for event in loaded] == [1.0, 2.0, 0.5]


def test_t15_repeated_project_load_epoch_is_deterministic(tmp_path):
    store = DurableEventStore(tmp_path / "ppl")
    for event in (epoch_created(), opened(), closed()):
        store.append(EPOCH_A, event)

    state_a = project(store.load_epoch(EPOCH_A))
    state_b = project(store.load_epoch(EPOCH_A))

    assert state_a == state_b
    assert state_a.available_cash == pytest.approx(state_b.available_cash)
    assert state_a.realized_pnl == pytest.approx(state_b.realized_pnl)


def test_t16_two_epochs_are_strictly_isolated(tmp_path):
    store = DurableEventStore(tmp_path / "ppl")
    event_a = epoch_created(epoch_id=EPOCH_A, event_id="ev-a")
    event_b = epoch_created(epoch_id=EPOCH_B, event_id="ev-b")
    store.append(EPOCH_A, event_a)
    store.append(EPOCH_B, event_b)

    assert store.load_epoch(EPOCH_A) == (event_a,)
    assert store.load_epoch(EPOCH_B) == (event_b,)
    assert epoch_path(tmp_path / "ppl", EPOCH_A) != epoch_path(
        tmp_path / "ppl", EPOCH_B
    )


def test_t17_file_and_new_directory_fsync_paths_are_executed(tmp_path, monkeypatch):
    synced_modes = []
    real_fsync = store_module.os.fsync

    def recording_fsync(descriptor):
        synced_modes.append(store_module.os.fstat(descriptor).st_mode)
        return real_fsync(descriptor)

    monkeypatch.setattr(store_module.os, "fsync", recording_fsync)
    result = DurableEventStore(tmp_path / "ppl").append(EPOCH_A, epoch_created())

    assert result.status is AppendStatus.APPENDED
    assert sum(stat.S_ISREG(mode) for mode in synced_modes) == 1
    assert sum(stat.S_ISDIR(mode) for mode in synced_modes) == 3


class _FailingStream:
    def __init__(self, wrapped, failure_point):
        self._wrapped = wrapped
        self._failure_point = failure_point

    def __enter__(self):
        self._wrapped.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self._wrapped.__exit__(exc_type, exc, traceback)

    def write(self, data):
        if self._failure_point == "write":
            raise OSError("injected write failure")
        return self._wrapped.write(data)

    def flush(self):
        if self._failure_point == "flush":
            raise OSError("injected flush failure")
        return self._wrapped.flush()

    def fileno(self):
        return self._wrapped.fileno()


@pytest.mark.parametrize("failure_point", ["write", "flush"])
def test_t18_write_or_flush_failure_never_reports_success(
    tmp_path, monkeypatch, failure_point
):
    real_open = Path.open

    def injected_open(path, *args, **kwargs):
        stream = real_open(path, *args, **kwargs)
        if path.suffix == ".jsonl" and args and args[0] == "ab":
            return _FailingStream(stream, failure_point)
        return stream

    monkeypatch.setattr(Path, "open", injected_open)

    with pytest.raises(OSError, match=failure_point):
        DurableEventStore(tmp_path / "ppl").append(EPOCH_A, epoch_created())


def test_t18_file_fsync_failure_never_reports_success(tmp_path, monkeypatch):
    root = tmp_path / "ppl"
    store = DurableEventStore(root)
    store.append(EPOCH_A, epoch_created())

    def failing_fsync(_descriptor):
        raise OSError("injected fsync failure")

    monkeypatch.setattr(store_module.os, "fsync", failing_fsync)

    with pytest.raises(OSError, match="fsync"):
        store.append(EPOCH_A, recovery())


def test_t18_retry_after_file_fsync_failure_reconfirms_durability(
    tmp_path, monkeypatch
):
    root = tmp_path / "ppl"
    store = DurableEventStore(root)
    store.append(EPOCH_A, epoch_created())
    real_fsync = store_module.os.fsync
    calls = 0

    def fail_first_fsync(descriptor):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected first fsync failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(store_module.os, "fsync", fail_first_fsync)
    event = recovery()

    with pytest.raises(OSError, match="first fsync"):
        store.append(EPOCH_A, event)

    result = store.append(EPOCH_A, event)
    assert result.status is AppendStatus.ALREADY_EXISTS
    assert calls == 3  # failed file sync, retry file sync, retry directory sync


def test_t18_directory_fsync_failure_never_reports_success(tmp_path, monkeypatch):
    root = tmp_path / "ppl"
    (root / "epochs").mkdir(parents=True)
    real_fsync_directory = DurableEventStore._fsync_directory

    def fail_epoch_directory_fsync(path):
        if path == root / "epochs":
            raise OSError("injected directory fsync failure")
        return real_fsync_directory(path)

    monkeypatch.setattr(
        DurableEventStore,
        "_fsync_directory",
        staticmethod(fail_epoch_directory_fsync),
    )

    with pytest.raises(OSError, match="directory fsync"):
        DurableEventStore(root).append(EPOCH_A, epoch_created())


def test_t18_retry_after_initial_directory_fsync_failure_is_durable(
    tmp_path, monkeypatch
):
    root = tmp_path / "ppl"
    real_fsync_directory = DurableEventStore._fsync_directory
    calls = 0

    def fail_first_directory_fsync(path):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected initial directory fsync failure")
        return real_fsync_directory(path)

    monkeypatch.setattr(
        DurableEventStore,
        "_fsync_directory",
        staticmethod(fail_first_directory_fsync),
    )
    store = DurableEventStore(root)
    event = epoch_created()

    with pytest.raises(OSError, match="initial directory fsync"):
        store.append(EPOCH_A, event)

    assert list((root / "epochs").iterdir()) == []
    assert store.append(EPOCH_A, event).status is AppendStatus.APPENDED
    assert store.load_epoch(EPOCH_A) == (event,)


def test_t19_legacy_journal_is_untouched(tmp_path):
    legacy = tmp_path / "databases" / "paper_trades.jsonl"
    legacy.parent.mkdir(parents=True)
    sentinel = b'{"legacy":"immutable-evidence"}\n'
    legacy.write_bytes(sentinel)

    store = DurableEventStore(tmp_path / "new-ppl-store")
    store.append(EPOCH_A, epoch_created())
    store.load_epoch(EPOCH_A)

    assert legacy.read_bytes() == sentinel


def test_t20_no_runtime_authority_import_or_constructor_side_effect(tmp_path):
    root = tmp_path / "never-created-by-constructor"
    DurableEventStore(root)
    assert not root.exists()

    repository_root = Path(__file__).resolve().parents[2]
    forbidden_runtime_paths = (
        repository_root / "core" / "advisor_loop.py",
        repository_root / "paper_trading" / "mexc_simulator.py",
        repository_root / "src" / "paper" / "paper_trade_notifier.py",
    )
    for path in forbidden_runtime_paths:
        assert "durable_event_store" not in path.read_text(encoding="utf-8")


def test_duplicate_physical_event_fails_closed_instead_of_hidden_deduplication(
    tmp_path,
):
    root = tmp_path / "ppl"
    store = DurableEventStore(root)
    store.append(EPOCH_A, epoch_created())
    path = epoch_path(root, EPOCH_A)
    line = path.read_bytes()
    path.write_bytes(line + line)

    with pytest.raises(StoreCorruptionError, match="duplicate physical"):
        store.load_epoch(EPOCH_A)


def test_duplicate_json_key_fails_closed(tmp_path):
    root = tmp_path / "ppl"
    path = epoch_path(root, EPOCH_A)
    path.parent.mkdir(parents=True)
    record = canonical_record(epoch_created())
    good = json.dumps(record, sort_keys=True, separators=(",", ":"))
    corrupt = good[:-1] + ',"event_id":"shadow-id"}\n'
    path.write_text(corrupt, encoding="utf-8")

    with pytest.raises(EventDeserializationError, match="duplicate JSON key"):
        DurableEventStore(root).load_epoch(EPOCH_A)


def test_non_canonical_but_valid_json_fails_closed(tmp_path):
    root = tmp_path / "ppl"
    path = epoch_path(root, EPOCH_A)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(canonical_record(epoch_created())) + "\n", encoding="utf-8"
    )

    with pytest.raises(StoreCorruptionError, match="not in the canonical"):
        DurableEventStore(root).load_epoch(EPOCH_A)


def test_invalid_utf8_and_blank_record_fail_closed(tmp_path):
    for name, data in (
        ("invalid-utf8", b"\xff\n"),
        ("blank", b"\n"),
    ):
        root = tmp_path / name
        path = epoch_path(root, EPOCH_A)
        path.parent.mkdir(parents=True)
        path.write_bytes(data)
        with pytest.raises(StoreCorruptionError):
            DurableEventStore(root).load_epoch(EPOCH_A)


def test_store_wide_event_identity_cannot_be_reused_across_epochs(tmp_path):
    store = DurableEventStore(tmp_path / "ppl")
    store.append(EPOCH_A, epoch_created(epoch_id=EPOCH_A, event_id="global-id"))

    with pytest.raises(EventIdentityCollisionError):
        store.append(EPOCH_B, epoch_created(epoch_id=EPOCH_B, event_id="global-id"))


def test_epoch_digest_layout_contains_untrusted_id_safely(tmp_path):
    root = tmp_path / "ppl"
    hostile_epoch_id = "../../paper_trades.jsonl"
    event = epoch_created(epoch_id=hostile_epoch_id)
    store = DurableEventStore(root)

    store.append(hostile_epoch_id, event)

    assert store.load_epoch(hostile_epoch_id) == (event,)
    assert epoch_path(root, hostile_epoch_id).parent == root / "epochs"
    assert not (tmp_path / "paper_trades.jsonl").exists()


def test_epoch_partition_symlink_fails_closed(tmp_path):
    root = tmp_path / "ppl"
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "epochs").parent.mkdir(parents=True)
    (root / "epochs").symlink_to(outside, target_is_directory=True)

    with pytest.raises(StoreCorruptionError, match="real directory"):
        DurableEventStore(root).append(EPOCH_A, epoch_created())

    assert list(outside.iterdir()) == []


def test_posix_process_lock_allows_only_one_writer_for_same_sequence(tmp_path):
    root = tmp_path / "ppl"
    DurableEventStore(root).append(EPOCH_A, epoch_created())
    context = multiprocessing.get_context("fork")
    start = context.Event()
    results = context.Queue()
    processes = [
        context.Process(
            target=concurrent_append_worker,
            args=(root, start, results, event_id),
        )
        for event_id in ("concurrent-a", "concurrent-b")
    ]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    outcomes = sorted(results.get(timeout=2) for _ in processes)
    assert outcomes == [AppendStatus.APPENDED.value, "StoreSequenceRegressionError"]
    assert len(DurableEventStore(root).load_epoch(EPOCH_A)) == 2


def test_missing_epoch_is_explicit_failure(tmp_path):
    with pytest.raises(EpochNotFoundError):
        DurableEventStore(tmp_path / "ppl").load_epoch("missing")


def test_append_refuses_existing_corruption_before_writing(tmp_path):
    root = tmp_path / "ppl"
    store = DurableEventStore(root)
    store.append(EPOCH_A, epoch_created())
    path = epoch_path(root, EPOCH_A)
    corrupted = path.read_bytes() + b"TRUNCATED"
    path.write_bytes(corrupted)

    with pytest.raises(StoreCorruptionError):
        store.append(EPOCH_A, recovery())

    assert path.read_bytes() == corrupted


@pytest.mark.parametrize("count", range(1, 16))
def test_property_sequence_monotonicity_and_reload(count, tmp_path):
    store = DurableEventStore(tmp_path / f"ppl-{count}")
    events = [epoch_created()]
    events.extend(
        recovery(event_id=f"ev-property-{sequence}", sequence=sequence)
        for sequence in range(2, count + 1)
    )
    for event in events:
        store.append(EPOCH_A, event)

    loaded = store.load_epoch(EPOCH_A)
    assert [event.sequence for event in loaded] == list(range(1, count + 1))
    assert len({event.event_id for event in loaded}) == count
