"""Operation-bound consumption: each assertion observes verdicts or persistent bytes."""

import copy
import multiprocessing
import os

import pytest

from colony_trust import trust
from tests.colony_trust.keys import ADMITTER, LAB, REVIEWER, key_entry, lab_key, pin, root
from tests.colony_trust.test_trust import ADM, QUAL, _admission, _qualification, _resign, _sign, _subject

OP = "a" * 64


def bundle(label="one"):
    record = _admission()
    return [(_sign(record, ADM, ADMITTER, "admitter-1", label=label), record)], [
        (ADM, _subject(record, ADM), pin(record))]


def consume(path, *, operation=OP, items=None, required=None, the_root=None):
    default_items, default_required = bundle()
    the_root = root() if the_root is None else the_root
    return trust.consume(default_items if items is None else items,
                         default_required if required is None else required, the_root,
                         pin_sha256=pin(the_root), minimum_version=1, lab_id=LAB, ledger=path,
                         operation_sha256=operation)


def test_fresh_consumption_and_exact_resume_are_distinct(tmp_path):
    ledger = tmp_path / "ledger"
    assert consume(ledger)["consumption"] == "CONSUMED"
    raw = ledger.read_bytes()
    line = trust.loads(raw[:-1])
    assert line["ledger_schema"] == trust.OPERATION_LEDGER_SCHEMA and line["operation_sha256"] == OP
    resume = consume(ledger)
    assert not resume["accepted"] and resume["consumption"] == "CONSUMED_BY_THIS_OPERATION"
    assert ledger.read_bytes() == raw
    evidence = trust.verify_consumed(bundle()[0][0][0], ledger, OP)
    assert evidence == {"consumed": True, "failures": []} and "accepted" not in evidence


@pytest.mark.parametrize("operation", [None, True, 5, "A" * 64, "bad"])
def test_malformed_operation_never_creates_a_file(tmp_path, operation):
    ledger = tmp_path / "ledger"
    result = consume(ledger, operation=operation)
    assert result["failures"] == ["OPERATION_INVALID"] and not ledger.exists()


def test_another_operation_and_changed_envelope_are_refused(tmp_path):
    ledger = tmp_path / "ledger"
    assert consume(ledger)["accepted"]
    before = ledger.read_bytes()
    assert consume(ledger, operation="b" * 64)["failures"] == ["ENVELOPE_REPLAYED"]
    items, required = bundle()
    changed = _resign(items[0][0], key="admitter-1", root_version=1, purpose="BIRTH_ADMITTED")
    record = {**items[0][1], "policy_sha256": "c" * 64}
    changed = trust.make_envelope(record, record_kind=ADM, lab_id=LAB, root_version=1,
                                  issuer_id=ADMITTER,
                                  private_key=lab_key("admitter-1"),
                                  envelope_id=changed["envelope_id"])
    required = [(ADM, _subject(record, ADM), pin(record))]
    assert consume(ledger, items=[(changed, record)], required=required)["failures"] == ["ENVELOPE_ID_REUSED"]
    assert ledger.read_bytes() == before


def test_check_is_read_only_and_does_not_reserve(tmp_path):
    ledger = tmp_path / "ledger"
    items, required = bundle()
    kwargs = dict(pin_sha256=pin(root()), minimum_version=1, lab_id=LAB, ledger=ledger)
    assert trust.check_bundle(items, required, root(), **kwargs)["accepted"] and not ledger.exists()
    assert consume(ledger)["accepted"]
    before = ledger.read_bytes()
    assert trust.check_bundle(items, required, root(), **kwargs)["failures"] == ["ENVELOPE_REPLAYED"]
    assert ledger.read_bytes() == before


def test_legacy_consumption_cannot_be_resumed_and_legacy_reader_rejects_new_replay(tmp_path):
    ledger = tmp_path / "ledger"
    items, required = bundle()
    kwargs = dict(pin_sha256=pin(root()), minimum_version=1, lab_id=LAB, ledger=ledger)
    assert trust.verify_bundle(items, [required[0][:2]], root(), **kwargs)["accepted"]
    assert consume(ledger)["failures"] == ["ENVELOPE_REPLAYED"]
    assert not trust.verify_consumed(items[0][0], ledger, OP)["consumed"]
    other = tmp_path / "other"
    assert consume(other)["accepted"]
    assert trust.verify_bundle(items, [required[0][:2]], root(), **{**kwargs, "ledger": other})[
        "failures"] == ["ENVELOPE_REPLAYED"]


def test_partial_bundle_is_not_completed_and_never_spends_new_envelopes(tmp_path):
    ledger = tmp_path / "ledger"
    assert consume(ledger)["accepted"]
    one, req = bundle()
    two, req2 = bundle("two")
    # Distinct admission subject for completeness, not merely a second envelope of the same item.
    record = {**two[0][1], "child_agent_id": "b" * 64}
    two = [(_sign(record, ADM, ADMITTER, "admitter-1", label="two"), record)]
    req2 = [(ADM, _subject(record, ADM), pin(record))]
    before = ledger.read_bytes()
    result = consume(ledger, items=one + two, required=req + req2)
    assert result["failures"] == ["OPERATION_STATE_INCONSISTENT"]
    assert ledger.read_bytes() == before


def test_duplicate_issuer_envelope_id_in_distinct_items_never_creates_ledger(tmp_path):
    ledger = tmp_path / "ledger"
    one, req = bundle()
    record = {**one[0][1], "child_agent_id": "b" * 64}
    two = [(_sign(record, ADM, ADMITTER, "admitter-1", label="one"), record)]
    result = consume(ledger, items=one + two, required=req + [(ADM, _subject(record, ADM), pin(record))])
    assert result["failures"] == ["ENVELOPE_ID_REUSED"] and not ledger.exists()


def test_revoke_between_consumption_and_resume_never_accepts(tmp_path):
    ledger = tmp_path / "ledger"
    assert consume(ledger)["accepted"]
    issuers = root()["issuers"]
    issuers[0]["keys"] = [key_entry("admitter-1", status="REVOKED", retired=2)]
    current = root(version=2, issuers=issuers)
    before = ledger.read_bytes()
    result = consume(ledger, the_root=current)
    assert not result["accepted"] and result["consumption"] == "NOT_CONSUMED"
    assert "KEY_REVOKED" in result["failures"] and ledger.read_bytes() == before


def test_same_subject_different_record_hashes_are_distinct_required_items(tmp_path):
    one, two = _qualification(), {**_qualification(), "evidence_sha256": "b" * 64}
    items = [(_sign(one, label="one"), one), (_sign(two, label="two"), two)]
    required = [(QUAL, _subject(r), pin(r)) for r in (one, two)]
    kwargs = dict(pin_sha256=pin(root()), minimum_version=1, lab_id=LAB)
    assert trust.check_bundle(items, required, root(), **kwargs)["accepted"]
    assert trust.check_bundle(items, required + [required[0]], root(), **kwargs)["failures"] == ["BUNDLE_INVALID"]
    assert not trust.check_bundle(items[:1], required, root(), **kwargs)["accepted"]


@pytest.mark.parametrize("bad", [None, {}, [None], [(ADM, {}, "a" * 64)], [(ADM, {}, None)]])
def test_malformed_required_is_coded(tmp_path, bad):
    result = trust.consume(bundle()[0], bad, root(), pin_sha256=pin(root()), minimum_version=1,
                           lab_id=LAB, ledger=tmp_path / "ledger", operation_sha256=OP)
    assert not result["accepted"] and result["failures"] == ["BUNDLE_INVALID"]


def test_authentication_failures_create_no_file(tmp_path):
    items, required = bundle()
    bad = {**items[0][0], "signature": "0" * 128}
    ledger = tmp_path / "ledger"
    assert "SIGNATURE_INVALID" in consume(ledger, items=[(bad, items[0][1])], required=required)["failures"]
    assert not ledger.exists()


def test_short_writes_are_completed_and_zero_progress_is_uncertain(tmp_path, monkeypatch):
    real = trust.os.write
    monkeypatch.setattr(trust.os, "write", lambda fd, data: real(fd, data[:7]))
    assert consume(tmp_path / "short")["accepted"]
    monkeypatch.setattr(trust.os, "write", lambda fd, data: 0)
    assert consume(tmp_path / "zero")["failures"] == ["LEDGER_DURABILITY_UNKNOWN"]


@pytest.mark.parametrize("directory", [False, True])
def test_fsync_failure_is_distinct_and_never_retried(tmp_path, monkeypatch, directory):
    real, calls = trust.os.fsync, []

    def sync(fd):
        calls.append(fd)
        if len(calls) == (2 if directory else 1):
            raise OSError("injected sync failure")
        real(fd)
    monkeypatch.setattr(trust.os, "fsync", sync)
    assert consume(tmp_path / "ledger")["failures"] == ["LEDGER_DURABILITY_UNKNOWN"]
    assert len(calls) == (2 if directory else 1)


def test_fifo_link_permissions_and_corruption_are_refused(tmp_path):
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    assert consume(fifo)["failures"] == ["LEDGER_CORRUPT"]
    target = tmp_path / "target"
    target.write_bytes(b"")
    link = tmp_path / "link"
    link.symlink_to(target)
    assert consume(link)["failures"] == ["LEDGER_CORRUPT"]
    assert consume(target)["failures"] == ["LEDGER_CORRUPT"]  # not private
    target.chmod(0o600)
    target.write_bytes(b'{"torn":')
    assert consume(target)["failures"] == ["LEDGER_CORRUPT"]


def test_genuine_but_revoked_requires_the_signature_and_all_bindings():
    record = _qualification()
    envelope = _sign(record)
    issuers = root()["issuers"]
    issuers[1]["keys"] = [key_entry("reviewer-1", status="REVOKED", retired=2)]
    current = root(version=2, issuers=issuers)
    kwargs = dict(pin_sha256=pin(current), minimum_version=1, lab_id=LAB, record_kind=QUAL, subject=_subject(record))
    verdict = trust.classify_envelope(envelope, record, current, **kwargs)
    assert verdict["genuine_but_revoked"] and not verdict["attested"]
    assert not trust.classify_envelope({**envelope, "signature": "0" * 128}, record, current,
                                      **kwargs)["genuine_but_revoked"]
    assert not trust.classify_envelope(envelope, {**record, "evidence_sha256": "f" * 64}, current,
                                      **kwargs)["genuine_but_revoked"]


def _race(path, queue):
    queue.put(consume(path, operation=pin(str(os.getpid()))))


def test_competing_operations_accept_only_one(tmp_path):
    ctx = multiprocessing.get_context("fork")
    queue = ctx.Queue()
    ledger = tmp_path / "ledger"
    workers = [ctx.Process(target=_race, args=(ledger, queue)) for _ in range(6)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(15)
        assert w.exitcode == 0
    verdicts = [queue.get(timeout=5) for _ in workers]
    assert sum(v["accepted"] for v in verdicts) == 1
    assert len(ledger.read_bytes().splitlines()) == 1


def test_statement_kind_binds_external_issuer_and_subject():
    kind = "colony-admission.attestation-statement/0"
    record = {"statement_schema": kind, "subject_agent_id": "a" * 64, "subject_agent_spec_id": "b" * 64,
              "issuer_kind": "EXTERNAL_REVIEW_PROCESS", "issuer_id": REVIEWER}
    current = copy.deepcopy(root())
    current["issuers"][1]["scopes"] = sorted([QUAL, kind])
    envelope = _sign(record, kind=kind)
    kwargs = dict(pin_sha256=pin(current), minimum_version=1, lab_id=LAB,
                  record_kind=kind, subject={"agent_id": "a" * 64, "agent_spec_id": "b" * 64})
    assert trust.verify_envelope(envelope, record, current, **kwargs)["attested"]
    # Statement semantics remain the future controller's responsibility.


def test_mixed_ledger_formats_remain_strict_and_only_v1_can_resume(tmp_path):
    ledger = tmp_path / "ledger"
    first, req = bundle("legacy")
    assert trust.verify_bundle(first, [req[0][:2]], root(), pin_sha256=pin(root()), minimum_version=1,
                               lab_id=LAB, ledger=ledger)["accepted"]
    second, req2 = bundle()
    assert consume(ledger, items=second, required=req2)["accepted"]
    entries = [trust.loads(line) for line in ledger.read_bytes().splitlines()]
    assert [e["ledger_schema"] for e in entries] == [trust.LEDGER_SCHEMA, trust.OPERATION_LEDGER_SCHEMA]
    assert not trust.verify_consumed(first[0][0], ledger, OP)["consumed"]
    assert trust.verify_consumed(second[0][0], ledger, OP)["consumed"]
    before = ledger.read_bytes()
    line = dict(entries[-1], operation_sha256=True)
    ledger.write_bytes(before.splitlines(keepends=True)[0] + trust._canonical(line) + b"\n")
    assert consume(ledger)["failures"] == ["LEDGER_CORRUPT"]


@pytest.mark.parametrize("field,value", [("lab_id", "other-lab"), ("environment", "PRODUCTION")])
def test_current_root_constraints_apply_to_resume(tmp_path, field, value):
    ledger = tmp_path / "ledger"
    assert consume(ledger)["accepted"]
    current = {**root(), field: value}
    before = ledger.read_bytes()
    assert not consume(ledger, the_root=current)["accepted"]
    assert ledger.read_bytes() == before


def test_partial_mixed_consumption_does_not_allow_legacy_replay(tmp_path):
    ledger = tmp_path / "ledger"
    assert consume(ledger)["accepted"]
    envelope = bundle()[0][0][0]
    for operation in ("b" * 64, "bad", None):
        result = trust.verify_consumed(envelope, ledger, operation)
        assert not result["consumed"]
