"""Read-only preparation, owner-bound locks, staged effects, frozen-plan revalidation."""

import copy
import os
import threading

import pytest

from colony_lab import lineage
from colony_lab import supervisor as sup
from colony_registrar import registrar as reg
from tests.colony_lab import builders
from tests.colony_registrar.test_registrar import Colony, _spec


def inputs(c, name="child_01"):
    spec = _spec(name)
    parent = c.founder["agent_id"]
    return parent, spec, dict(parent_qualification=builders.qualification(c.founder),
                              admission=c.admission(spec, parent),
                              lab_permissions=["DIAGNOSTIC_PRODUCE"], budget=copy.deepcopy(builders.BUDGET),
                              declared_diff=lineage.spec_diff(c.founder_spec, spec))


def files(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_prepare_creates_no_file_or_directory_and_freezes_inputs(tmp_path):
    c = Colony(tmp_path)
    parent, spec, kwargs = inputs(c)
    before, dirs = files(c.lab.root), sorted(str(p) for p in c.lab.root.rglob("*"))
    plan = c.registrar.prepare(parent, spec, **kwargs)
    assert files(c.lab.root) == before and sorted(str(p) for p in c.lab.root.rglob("*")) == dirs
    assert not (c.lab.root / reg.ADMISSIONS).exists() and not (c.lab.root / reg.LOCK).exists()
    digest = plan.sha256
    kwargs["budget"]["runs"] += 1
    plan.data["record"]["budget"]["runs"] += 1
    assert plan.sha256 == digest and plan.data["record"]["budget"]["runs"] == builders.BUDGET["runs"]
    with pytest.raises(AttributeError):
        plan._bytes = b"forged"


def test_lock_required_staged_commit_idempotence_and_nested_ownership(tmp_path):
    c = Colony(tmp_path)
    parent, spec, kwargs = inputs(c)
    plan = c.registrar.prepare(parent, spec, **kwargs)
    with pytest.raises(reg.RegistrarError, match="LOCK_REQUIRED"):
        c.registrar.commit(plan, step="ADMISSION")
    with c.registrar.exclusive():
        with c.registrar.exclusive():
            c.registrar.commit(plan, step="ADMISSION")
        path = c.lab.root / reg.ADMISSIONS / f"{spec['agent_id']}.json"
        before = path.read_bytes()
        c.registrar.commit(plan, step="ADMISSION")
        assert path.read_bytes() == before and not c.lab._home(spec["agent_id"]).exists()
        result = c.registrar.commit(plan, step="HOME")
        home_before = files(c.lab._home(spec["agent_id"]))
        assert result["record"] == plan.data["record"]
        assert c.registrar.commit(plan, step="HOME") == result
        assert files(c.lab._home(spec["agent_id"])) == home_before
    assert c.registrar._owner is None


def test_other_thread_and_other_registrar_cannot_borrow_the_lock(tmp_path):
    c = Colony(tmp_path)
    failures = []
    parent, spec, kwargs = inputs(c)
    plan = c.registrar.prepare(parent, spec, **kwargs)

    def attempt():
        try:
            with c.registrar.exclusive():
                failures.append("unexpected")
        except reg.RegistrarError as exc:
            failures.append(exc.code)
        try:
            c.registrar.commit(plan, step="ADMISSION")
        except reg.RegistrarError as exc:
            failures.append(exc.code)

    with c.registrar.exclusive():
        thread = threading.Thread(target=attempt)
        thread.start()
        thread.join(5)
        assert not thread.is_alive()
        other = reg.Registrar(c.lab, policy=c.registrar.policy, policy_sha256=c.registrar.policy_sha256)
        with pytest.raises(reg.RegistrarError, match="REGISTRAR_BUSY"):
            with other.exclusive():
                pass
    assert failures == ["REGISTRAR_BUSY", "LOCK_REQUIRED"]


def test_preexisting_conflict_is_found_without_any_effect(tmp_path):
    c = Colony(tmp_path)
    parent, spec, kwargs = inputs(c)
    directory = c.lab.root / reg.ADMISSIONS
    directory.mkdir(mode=0o700)
    path = directory / f"{spec['agent_id']}.json"
    path.write_bytes(b'{}\n')
    before = files(c.lab.root)
    with pytest.raises(reg.RegistrarError, match="ADMISSION_CONFLICT"):
        c.registrar.prepare(parent, spec, **kwargs)
    assert files(c.lab.root) == before


def test_population_changes_invalidate_frozen_plan(tmp_path):
    c = Colony(tmp_path)
    parent, spec, kwargs = inputs(c)
    plan = c.registrar.prepare(parent, spec, **kwargs)
    c.birth(parent, "other_01")
    before = files(c.lab.root)
    with c.registrar.exclusive(), pytest.raises(reg.RegistrarError, match="POPULATION_CHANGED"):
        c.registrar.commit(plan, step="ADMISSION")
    assert files(c.lab.root) == before


@pytest.mark.parametrize("field", ["record", "policy_sha256", "population_count", "children_count", "budget_totals"])
def test_forged_plan_material_is_refused(tmp_path, field):
    c = Colony(tmp_path)
    parent, spec, kwargs = inputs(c)
    data = c.registrar.prepare(parent, spec, **kwargs).data
    data[field] = {} if field in {"record", "budget_totals"} else "forged"
    plan = reg.BirthPlan(data)
    with c.registrar.exclusive():
        before = files(c.lab.root)
        with pytest.raises(reg.RegistrarError):
            c.registrar.commit(plan, step="ADMISSION")
        assert files(c.lab.root) == before


@pytest.mark.parametrize("step", ["ADMISSION", "HOME"])
def test_stop_is_a_prewrite_refusal(tmp_path, step):
    c = Colony(tmp_path)
    parent, spec, kwargs = inputs(c)
    plan = c.registrar.prepare(parent, spec, **kwargs)
    with c.registrar.exclusive():
        if step == "HOME":
            c.registrar.commit(plan, step="ADMISSION")
        c.lab.stop()
        before = files(c.lab.root)
        with pytest.raises(reg.RegistrarError, match="LAB_STOPPED"):
            c.registrar.commit(plan, step=step)
        assert files(c.lab.root) == before


def test_short_write_completes_and_sync_failure_is_not_a_prewrite_refusal(tmp_path, monkeypatch):
    c = Colony(tmp_path)
    parent, spec, kwargs = inputs(c)
    plan = c.registrar.prepare(parent, spec, **kwargs)
    real = reg.os.write
    with c.registrar.exclusive():
        monkeypatch.setattr(reg.os, "write", lambda fd, data: real(fd, data[:5]))
        c.registrar.commit(plan, step="ADMISSION")
    admission = c.lab.root / reg.ADMISSIONS / f"{spec['agent_id']}.json"
    assert admission.read_bytes() == sup._dump(kwargs["admission"])
    monkeypatch.setattr(reg.os, "write", real)
    parent, spec, kwargs = inputs(c, "second_01")
    plan = c.registrar.prepare(parent, spec, **kwargs)
    calls = []

    def fail(fd):
        calls.append(fd)
        raise OSError("injected sync failure")
    with c.registrar.exclusive():
        monkeypatch.setattr(reg.os, "fsync", fail)
        with pytest.raises(OSError):
            c.registrar.commit(plan, step="ADMISSION")
    assert len(calls) == 1 and not c.lab._home(spec["agent_id"]).exists()


def test_supervisor_error_is_not_mapped_to_registrar_refusal(tmp_path, monkeypatch):
    c = Colony(tmp_path)
    parent, spec, kwargs = inputs(c)
    plan = c.registrar.prepare(parent, spec, **kwargs)
    with c.registrar.exclusive():
        c.registrar.commit(plan, step="ADMISSION")

        def fail(*args, **kwargs):
            raise sup.LabError("INDIVIDUAL_INVALID")
        monkeypatch.setattr(c.lab, "admit", fail)
        with pytest.raises(sup.LabError, match="INDIVIDUAL_INVALID"):
            c.registrar.commit(plan, step="HOME")


def test_partial_home_is_never_accepted_or_repaired(tmp_path):
    c = Colony(tmp_path)
    parent, spec, kwargs = inputs(c)
    plan = c.registrar.prepare(parent, spec, **kwargs)
    with c.registrar.exclusive():
        c.registrar.commit(plan, step="ADMISSION")
        home = c.lab._home(spec["agent_id"])
        home.mkdir(mode=0o700)
        before = files(c.lab.root)
        with pytest.raises(reg.RegistrarError, match="HOME_CONFLICT"):
            c.registrar.commit(plan, step="HOME")
        assert files(c.lab.root) == before


def test_home_step_requires_admission_and_run_slot_io_is_coded(tmp_path):
    c = Colony(tmp_path)
    parent, spec, kwargs = inputs(c)
    plan = c.registrar.prepare(parent, spec, **kwargs)
    with c.registrar.exclusive(), pytest.raises(reg.RegistrarError, match="ADMISSION_REQUIRED"):
        c.registrar.commit(plan, step="HOME")
    slots = c.lab.root / reg.SLOTS
    slots.mkdir(mode=0o700)
    (slots / "slot-0").symlink_to(tmp_path / "outside")
    with pytest.raises(reg.RegistrarError, match="LAB_IO_ERROR"):
        c.registrar.run(c.founder["agent_id"], {})


def test_prepare_does_not_create_directories_for_a_descendant_parent(tmp_path):
    c = Colony(tmp_path)
    child = c.birth(c.founder["agent_id"], "parent_01")
    parent = child["agent_id"]
    parent_record, parent_spec = c.lab.load(parent)
    spec = _spec("grandchild_01")
    qualification = builders.qualification(parent_record)
    kwargs = dict(parent_qualification=qualification, admission=c.admission(spec, parent),
                  lab_permissions=["DIAGNOSTIC_PRODUCE"], budget=copy.deepcopy(builders.BUDGET),
                  declared_diff=lineage.spec_diff(parent_spec, spec))
    before = files(c.lab.root)
    plan = c.registrar.prepare(parent, spec, **kwargs)
    assert plan.data["record"]["lineage"]["generation"] == 2
    assert files(c.lab.root) == before


def test_a_fifo_admission_is_refused_without_opening_it_blocking(tmp_path):
    c = Colony(tmp_path)
    parent, spec, kwargs = inputs(c)
    directory = c.lab.root / reg.ADMISSIONS
    directory.mkdir(mode=0o700)
    os.mkfifo(directory / f"{spec['agent_id']}.json")
    with pytest.raises(reg.RegistrarError, match="ADMISSION_CONFLICT"):
        c.registrar.prepare(parent, spec, **kwargs)


@pytest.mark.parametrize("missing", ["usage.json", "tasks", "j01-lab-memory/activity.sqlite3"])
def test_existing_identity_files_alone_do_not_prove_a_complete_home(tmp_path, missing):
    c = Colony(tmp_path)
    parent, spec, kwargs = inputs(c)
    plan = c.registrar.prepare(parent, spec, **kwargs)
    with c.registrar.exclusive():
        c.registrar.commit(plan, step="ADMISSION")
        c.registrar.commit(plan, step="HOME")
        path = c.lab._home(spec["agent_id"]) / missing
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()
        with pytest.raises(reg.RegistrarError, match="HOME_CONFLICT"):
            c.registrar.commit(plan, step="HOME")


def test_zero_progress_write_and_legacy_error_mapping(tmp_path, monkeypatch):
    c = Colony(tmp_path)
    parent, spec, kwargs = inputs(c)
    plan = c.registrar.prepare(parent, spec, **kwargs)
    monkeypatch.setattr(reg.os, "write", lambda fd, data: 0)
    with c.registrar.exclusive(), pytest.raises(OSError, match="no progress"):
        c.registrar.commit(plan, step="ADMISSION")
    # birth() retains the legacy mapping even though commit() exposes durable uncertainty.
    with pytest.raises(reg.RegistrarError, match="LAB_IO_ERROR"):
        c.birth(parent, "another_01")
