"""Tests for paper_trading/paper_epoch.py (PPL-02A)."""

import pytest

from paper_trading.paper_epoch import (
    InvalidPaperEpochTransition,
    PaperEpoch,
    PaperEpochStatus,
    create_paper_epoch,
)


def _make_epoch(**overrides):
    kwargs = dict(
        paper_epoch_id="pe-test-001",
        created_at=1000.0,
        initial_virtual_capital=100.0,
        code_sha="deadbeef",
        config_snapshot_hash="cfg-hash-1",
    )
    kwargs.update(overrides)
    return create_paper_epoch(**kwargs)


def test_create_paper_epoch_requires_explicit_identity_fields():
    epoch = _make_epoch()
    assert epoch.paper_epoch_id == "pe-test-001"
    assert epoch.status == PaperEpochStatus.ACTIVE
    assert epoch.initial_virtual_capital == 100.0
    assert epoch.code_sha == "deadbeef"
    assert epoch.config_snapshot_hash == "cfg-hash-1"
    assert epoch.schema_version == 1


def test_paper_epoch_id_never_aliases_exposure_epoch_id_field_name():
    epoch = _make_epoch()
    assert not hasattr(epoch, "exposure_epoch_id")
    assert not hasattr(epoch, "cycle_id")
    assert not hasattr(epoch, "trace_id")
    assert not hasattr(epoch, "decision_id")


@pytest.mark.parametrize(
    "field_name,bad_value",
    [
        ("paper_epoch_id", ""),
        ("initial_virtual_capital", 0.0),
        ("initial_virtual_capital", -5.0),
        ("code_sha", ""),
        ("config_snapshot_hash", ""),
    ],
)
def test_create_paper_epoch_rejects_missing_identity_fields(field_name, bad_value):
    with pytest.raises(ValueError):
        _make_epoch(**{field_name: bad_value})


def test_epoch_close_transition_returns_new_instance():
    epoch = _make_epoch()
    closed = epoch.close()
    assert epoch.status == PaperEpochStatus.ACTIVE  # original untouched
    assert closed.status == PaperEpochStatus.CLOSED
    assert closed.is_terminal
    assert closed.paper_epoch_id == epoch.paper_epoch_id


def test_epoch_supersede_transition():
    epoch = _make_epoch()
    superseded = epoch.supersede()
    assert superseded.status == PaperEpochStatus.SUPERSEDED
    assert superseded.is_terminal


def test_epoch_cannot_transition_out_of_terminal_status():
    epoch = _make_epoch().close()
    with pytest.raises(InvalidPaperEpochTransition):
        epoch.close()
    with pytest.raises(InvalidPaperEpochTransition):
        epoch.supersede()


def test_epoch_is_immutable_dataclass():
    epoch = _make_epoch()
    with pytest.raises(Exception):
        epoch.status = PaperEpochStatus.CLOSED  # type: ignore[misc]
