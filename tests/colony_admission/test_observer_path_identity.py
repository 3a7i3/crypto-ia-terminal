"""Real filesystem changes distinguish path ancestors from selected evidence."""

import os
from contextlib import ExitStack

import pytest

from colony_admission import _attestation_checkout as checkout_reader
from colony_admission import observer as o
from colony_admission.evidence_observer import _EvidenceAcquisition
from tests.colony_admission import test_attestation_checkout as checkout_tests
from tests.colony_admission import test_observer as base
from tests.colony_admission import test_population_observer as population

machine = base.machine
checkout = checkout_tests.checkout
family = population.family
signed_machine = population.signed_machine
full_profile_machine = population.full_profile_machine


@pytest.mark.parametrize("change", ["mkdir", "rmdir", "rename", "file", "mtime"])
def test_unrelated_ancestor_entries_do_not_invalidate_selected_sources(machine, monkeypatch, change):
    config, _ = machine
    ancestor = config.lab_root.parent
    sibling = ancestor / "unrelated"
    if change in ("rmdir", "rename"):
        sibling.mkdir()
    before = ancestor.stat()
    original = o._Acquisition.verify
    changed = []

    def mutate_then_verify(source):
        if change == "mkdir":
            sibling.mkdir()
        elif change == "rmdir":
            sibling.rmdir()
        elif change == "rename":
            sibling.rename(ancestor / "other-unrelated")
        elif change == "file":
            sibling.write_bytes(b"not selected evidence")
        else:
            os.utime(ancestor, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
        changed.append(o._identity(ancestor.stat()) != o._identity(before))
        original(source)

    monkeypatch.setattr(o._Acquisition, "verify", mutate_then_verify)
    result = base.observe(machine)
    assert changed == [True]
    assert result.status == "OBSERVED", result.blockers
    assert len(result.sources) == 6 and result.accepted is False


def test_checkout_ancestor_churn_preserves_acquired_bytes(checkout):
    with ExitStack() as stack:
        owner = _EvidenceAcquisition(stack)
        reader = checkout_reader.Checkout(owner, checkout)
        expected = reader.science()
        (checkout.parent / "unrelated").mkdir()
        reader.verify()
        owner.verify()
        assert reader.science() == expected


@pytest.mark.parametrize("change", ["entry", "mtime", "mode"])
@pytest.mark.parametrize("root_kind", ["evidence", "checkout"])
def test_selected_root_changes_still_invalidate(tmp_path, change, root_kind):
    root = tmp_path / "selected"
    root.mkdir(mode=0o700)
    with ExitStack() as stack:
        owner = _EvidenceAcquisition(stack)
        if root_kind == "checkout":
            checkout_reader.Checkout(owner, root)
        else:
            owner.directory(root)
        before = root.stat()
        if change == "entry":
            (root / "new-entry").mkdir()
        elif change == "mtime":
            os.utime(root, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
        else:
            root.chmod(0o750)
        with pytest.raises(o._Blocked, match="^SOURCE_CHANGED$"):
            owner.verify()


@pytest.mark.parametrize("change", ["replace", "symlink", "mode"])
@pytest.mark.parametrize("root_kind", ["evidence", "checkout"])
def test_ancestor_rebinding_and_permissions_still_invalidate(tmp_path, change, root_kind):
    ancestor = tmp_path / "ancestor"
    root = ancestor / "selected"
    root.mkdir(mode=0o700, parents=True)
    with ExitStack() as stack:
        owner = _EvidenceAcquisition(stack)
        if root_kind == "checkout":
            checkout_reader.Checkout(owner, root)
        else:
            owner.directory(root)
        if change == "mode":
            ancestor.chmod(0o750)
        else:
            saved = tmp_path / "original-ancestor"
            ancestor.rename(saved)
            if change == "replace":
                ancestor.mkdir()
            else:
                ancestor.symlink_to(saved, target_is_directory=True)
        with pytest.raises(o._Blocked, match="^SOURCE_CHANGED$"):
            owner.verify()


@pytest.mark.parametrize("phase", ["observation", "plan_divergence"])
def test_population_acquisition_with_unrelated_sibling_churn(full_profile_machine, monkeypatch, phase):
    tweak = (lambda plan: plan.update(children_count=1)) if phase == "plan_divergence" else None
    config, op = population.exact_own(full_profile_machine, tweak=tweak)
    population.proofs.home(config.observer, op)
    expected = population.observe(config)
    if phase == "plan_divergence":
        assert expected.status == "BLOCKED" and expected.operations[0].plan_match == "FAIL"
        assert "POPULATION_CHANGED" in expected.blockers
    else:
        assert expected.status == "OBSERVED"
    original = o._Acquisition.verify
    changed = []

    def mutate_then_verify(source):
        (config.observer.lab_root.parent / "unrelated").mkdir()
        changed.append(True)
        original(source)

    monkeypatch.setattr(o._Acquisition, "verify", mutate_then_verify)
    result = population.observe(config)
    assert changed == [True]
    assert result == expected
    assert result.operations and result.accepted is False
