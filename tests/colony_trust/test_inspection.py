"""A read-only observation never creates or authorizes a consumption."""

import fcntl
import os
from pathlib import Path

import pytest

from colony_trust import trust
from tests.colony_trust.keys import LAB, pin, root
from tests.colony_trust.test_operations import OP, bundle, consume
from tests.colony_trust.test_trust import _qualification, _sign


def envelope(label="one"):
    return bundle(label)[0][0][0]


def empty(path):
    path.write_bytes(b"")
    path.chmod(0o600)
    return path


def entry(env=None, operation=OP, legacy=False, **changes):
    env = envelope() if env is None else env
    value = {"ledger_schema": trust.LEDGER_SCHEMA if legacy else trust.OPERATION_LEDGER_SCHEMA,
             "issuer_id": env["issuer_id"], "envelope_id": env["envelope_id"],
             "envelope_sha256": pin(env)}
    if not legacy:
        value["operation_sha256"] = operation
    return {**value, **changes}


def ledger(path, *entries):
    path.write_bytes(b"".join(trust._canonical(x) + b"\n" for x in entries))
    path.chmod(0o600)
    return path


def inspect(path, env=None, operation=OP):
    return trust.inspect_consumption(envelope() if env is None else env, path, operation)


def assert_observation(result):
    assert set(result) == {"inspection_schema", "status", "operation_sha256", "operation_entries", "failures",
                           "accepted", "authenticity", "authorization", "completeness"}
    assert result["inspection_schema"] == trust.INSPECTION_SCHEMA
    assert result["accepted"] is False
    assert [result[x] for x in ("authenticity", "authorization", "completeness")] == ["NOT_EVALUATED"] * 3


def test_empty_valid_file_and_missing_file_are_distinct(tmp_path):
    path = tmp_path / "ledger"
    missing = inspect(path)
    assert missing["status"] == "LEDGER_MISSING" and missing["operation_entries"] is None
    assert not path.exists() and not list(tmp_path.iterdir())
    empty(path)
    absent = inspect(path)
    assert absent["status"] == "ABSENT_IN_VALID_LEDGER" and absent["operation_entries"] == 0
    assert absent["failures"] == [] and path.read_bytes() == b""
    assert_observation(missing)
    assert_observation(absent)


def test_missing_namespace_cannot_prove_missing_entry(tmp_path):
    path = tmp_path / "not-created" / "ledger"
    result = inspect(path)
    assert result["status"] == "LEDGER_UNAVAILABLE" and result["operation_entries"] is None
    assert not path.parent.exists()


def test_exact_consumption_is_evidence_not_authorization(tmp_path):
    path = tmp_path / "ledger"
    assert consume(path)["accepted"]
    before = path.read_bytes()
    result = inspect(path)
    assert result["status"] == "CONSUMED_BY_OPERATION" and result["operation_entries"] == 1
    assert_observation(result)
    assert path.read_bytes() == before


@pytest.mark.parametrize("change,code", [
    ({"operation_sha256": "b" * 64}, "ENVELOPE_REPLAYED"),
    ({"envelope_sha256": "b" * 64}, "ENVELOPE_ID_REUSED"),
])
def test_expected_pair_bound_to_other_content_is_conflict(tmp_path, change, code):
    path = ledger(tmp_path / "ledger", entry(**change))
    result = inspect(path)
    assert result["status"] == "CONFLICT" and result["failures"] == [code]


def test_legacy_matching_envelope_cannot_be_resumed(tmp_path):
    path = ledger(tmp_path / "ledger", entry(legacy=True))
    result = inspect(path)
    assert result["status"] == "CONFLICT" and result["failures"] == ["LEGACY_CONSUMPTION"]
    assert result["operation_entries"] == 0


def test_foreign_entry_of_this_operation_is_not_absence(tmp_path):
    path = ledger(tmp_path / "ledger", entry(envelope("foreign")))
    result = inspect(path)
    assert result["status"] == "CONFLICT" and result["failures"] == ["OPERATION_FOREIGN_ENTRY"]
    assert result["operation_entries"] == 1


@pytest.mark.parametrize("include_expected", [False, True])
def test_every_line_linked_to_operation_is_counted(tmp_path, include_expected):
    first = envelope() if include_expected else envelope("foreign-first")
    path = ledger(tmp_path / "ledger", entry(first), entry(envelope("foreign-second")))
    result = inspect(path)
    assert result["status"] == "CONFLICT" and result["failures"] == ["OPERATION_MULTIPLE_ENTRIES"]
    assert result["operation_entries"] == 2


def test_unrelated_legacy_and_operation_entries_do_not_fake_a_match(tmp_path):
    path = ledger(tmp_path / "ledger", entry(envelope("legacy"), legacy=True),
                  entry(envelope("other"), operation="b" * 64))
    result = inspect(path)
    assert result["status"] == "ABSENT_IN_VALID_LEDGER" and result["operation_entries"] == 0


@pytest.mark.parametrize("raw", [b'{"torn":', b"{}\n", b"garbage\n", b"{ }\n", b"\xff\n"])
def test_corrupt_data_never_becomes_absence(tmp_path, raw):
    path = empty(tmp_path / "ledger")
    path.write_bytes(raw)
    result = inspect(path)
    assert result["status"] == "LEDGER_CORRUPT" and result["operation_entries"] is None
    assert path.read_bytes() == raw


def test_duplicated_key_and_unknown_schema_are_corrupt(tmp_path):
    path = ledger(tmp_path / "ledger", entry(), entry())
    assert inspect(path)["status"] == "LEDGER_CORRUPT"
    ledger(path, entry(ledger_schema="colony-trust.consumed/99"))
    assert inspect(path)["status"] == "LEDGER_CORRUPT"


@pytest.mark.parametrize("schema", [[], {}, None, 1])
def test_malformed_schema_type_is_corruption_not_an_io_failure(tmp_path, schema):
    path = ledger(tmp_path / "ledger", entry(legacy=True, ledger_schema=schema))
    assert inspect(path)["status"] == "LEDGER_CORRUPT"
    raw = trust._canonical(entry())
    path.write_bytes(raw[:-1] + b',"issuer_id":"fixture-duplicate"}\n')
    assert inspect(path)["status"] == "LEDGER_CORRUPT"


@pytest.mark.parametrize("operation", [None, True, 0, {}, "bad", "A" * 64])
def test_invalid_operation_is_rejected_before_open(tmp_path, monkeypatch, operation):
    def never(*args, **kwargs):
        raise AssertionError("invalid inputs must not open the ledger")
    monkeypatch.setattr(trust.os, "open", never)
    result = inspect(tmp_path / "ledger", operation=operation)
    assert result["status"] == "INVALID_INPUT" and result["failures"] == ["OPERATION_INVALID"]


@pytest.mark.parametrize("env", [None, {}, "bad", {"envelope_schema": "other"}])
def test_invalid_envelope_is_rejected_before_open(tmp_path, monkeypatch, env):
    def never(*args, **kwargs):
        raise AssertionError("invalid inputs must not open the ledger")
    monkeypatch.setattr(trust.os, "open", never)
    result = trust.inspect_consumption(env, tmp_path / "ledger", OP)
    assert result["status"] == "INVALID_INPUT" and result["failures"] == ["ENVELOPE_INVALID"]


def test_durable_envelope_is_not_a_consumption_subject(tmp_path):
    env = _sign(_qualification())
    assert inspect(tmp_path / "ledger", env)["status"] == "INVALID_INPUT"


def test_no_write_descriptor_or_mutation_is_used(tmp_path, monkeypatch):
    path = ledger(tmp_path / "ledger", entry())
    raw, names, flags = path.read_bytes(), sorted(tmp_path.iterdir()), []
    real = trust.os.open

    def opened(target, access, *args, **kwargs):
        flags.append(access)
        assert access & os.O_ACCMODE == os.O_RDONLY
        assert not access & (os.O_CREAT | os.O_APPEND | os.O_TRUNC)
        return real(target, access, *args, **kwargs)

    def never(*args, **kwargs):
        raise AssertionError("read-only inspector attempted mutation")
    with monkeypatch.context() as patch:
        patch.setattr(trust.os, "open", opened)
        for name in ("write", "fsync", "chmod", "rename", "replace", "unlink", "mkdir"):
            patch.setattr(trust.os, name, never)
        result = inspect(path)
    assert flags and result["status"] == "CONSUMED_BY_OPERATION"
    assert path.read_bytes() == raw and sorted(tmp_path.iterdir()) == names


def test_writer_lock_is_refused_without_blocking_or_sidecar(tmp_path):
    path = ledger(tmp_path / "ledger", entry())
    fd = os.open(path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = inspect(path)
        assert result["status"] == "LEDGER_BUSY" and result["operation_entries"] is None
    finally:
        os.close(fd)
    assert inspect(path)["status"] == "CONSUMED_BY_OPERATION"
    assert list(tmp_path.iterdir()) == [path]


def test_other_readers_can_share_the_same_inode_lock(tmp_path):
    path = empty(tmp_path / "ledger")
    fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        assert inspect(path)["status"] == "ABSENT_IN_VALID_LEDGER"
    finally:
        os.close(fd)


def test_fifo_device_link_directory_and_permissions_do_not_become_absence(tmp_path):
    path = empty(tmp_path / "ledger")
    alias = tmp_path / "alias"
    alias.symlink_to(path)
    assert inspect(alias)["status"] == "LEDGER_UNAVAILABLE"
    alias.unlink()
    os.link(path, alias)
    assert inspect(alias)["status"] == "LEDGER_CORRUPT"
    alias.unlink()
    path.chmod(0o644)
    assert inspect(path)["status"] == "LEDGER_CORRUPT"
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo, 0o600)
    assert inspect(fifo)["status"] == "LEDGER_CORRUPT"
    assert inspect(Path("/dev/zero"))["status"] == "LEDGER_CORRUPT"
    assert inspect(tmp_path)["status"] == "LEDGER_CORRUPT"


def test_size_and_entry_bounds_never_return_a_partial_absence(tmp_path, monkeypatch):
    path = ledger(tmp_path / "ledger", entry())
    monkeypatch.setattr(trust, "INSPECTION_MAX_BYTES", path.stat().st_size - 1)
    result = inspect(path)
    assert result["status"] == "LEDGER_UNAVAILABLE" and result["failures"] == ["LEDGER_TOO_LARGE"]
    monkeypatch.setattr(trust, "INSPECTION_MAX_BYTES", path.stat().st_size)
    assert inspect(path)["status"] == "CONSUMED_BY_OPERATION"  # inclusive boundary
    monkeypatch.setattr(trust, "INSPECTION_MAX_ENTRIES", 0)
    assert inspect(path)["failures"] == ["LEDGER_TOO_LARGE"]


def test_streaming_limit_is_enforced_even_when_stat_size_understates_bytes(tmp_path, monkeypatch):
    path = ledger(tmp_path / "ledger", entry())
    real = trust.os.fstat

    def understated(fd):
        values = list(real(fd))
        values[6] = 0
        return os.stat_result(values)
    monkeypatch.setattr(trust.os, "fstat", understated)
    monkeypatch.setattr(trust, "INSPECTION_MAX_BYTES", 1)
    result = inspect(path)
    assert result["status"] == "LEDGER_UNAVAILABLE"
    assert result["failures"] == ["LEDGER_TOO_LARGE"] and result["operation_entries"] is None


@pytest.mark.parametrize("site", ["open", "read", "close"])
def test_io_failure_discards_any_observation(tmp_path, monkeypatch, site):
    path = empty(tmp_path / "ledger")
    real = getattr(trust.os, site)

    def fail(*args, **kwargs):
        if site == "close":
            real(*args, **kwargs)
        raise PermissionError("injected I/O error")
    monkeypatch.setattr(trust.os, site, fail)
    result = inspect(path)
    assert result["status"] == "LEDGER_UNAVAILABLE" and result["operation_entries"] is None


def test_read_eagain_is_not_reported_as_lock_contention(tmp_path, monkeypatch):
    path = empty(tmp_path / "ledger")

    def fail(*args, **kwargs):
        raise BlockingIOError("read failed")
    monkeypatch.setattr(trust.os, "read", fail)
    assert inspect(path)["status"] == "LEDGER_UNAVAILABLE"


def test_inspector_does_not_authenticate_even_a_matching_signature_shaped_value(tmp_path):
    env = {**envelope(), "signature": "0" * 128}
    path = ledger(tmp_path / "ledger", entry(env))
    result = inspect(path, env)
    assert result["status"] == "CONSUMED_BY_OPERATION"
    assert_observation(result)


def test_existing_consumption_and_inspection_compose_without_spending(tmp_path):
    path = tmp_path / "ledger"
    assert consume(path)["accepted"]
    before = path.read_bytes()
    assert inspect(path)["status"] == "CONSUMED_BY_OPERATION"
    assert trust.verify_consumed(envelope(), path, OP)["consumed"]
    items, required = bundle()
    verdict = trust.check_bundle(items, required, root(), pin_sha256=pin(root()), minimum_version=1,
                                 lab_id=LAB, ledger=path)
    assert not verdict["accepted"] and verdict["failures"] == ["ENVELOPE_REPLAYED"]
    assert path.read_bytes() == before
