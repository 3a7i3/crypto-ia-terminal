"""Private inventory IO tests. All trees/opaque material are temporary fixtures."""

import os
from contextlib import ExitStack

import pytest

from colony_admission import _population_inventory as inv
from colony_admission import evidence_observer as e
from colony_admission import observer as o
from colony_admission import formats as f
from tests.colony_admission import test_attestation_observer as ao
from tests.colony_admission import test_observer as base
from tests.colony_admission import test_attestation_core as pure

family = pure.family
machine = base.machine
signed_machine = ao.signed_machine


def collect(config):
    # Fixture harness only: no public scan, ledger/root/crypto claims implied.
    with ExitStack() as stack:
        source = inv.InventorySource(stack)
        lab = source.directory(config.lab_root)
        names = inv.home_names(source, lab)
        homes = inv.acquire_homes(source, lab, names)
        source.verify()
    return homes


def test_all_homes_and_each_payload_only_once(signed_machine, monkeypatch):
    config, op, _ = signed_machine
    reads, read = [], os.read
    def counted(fd, count):
        raw = read(fd, count)
        if raw:
            reads.append(os.fstat(fd).st_ino)
        return raw
    monkeypatch.setattr(os, "read", counted)
    with ExitStack() as stack:
        source = inv.InventorySource(stack)
        lab = source.directory(config.observer.lab_root)
        names = inv.home_names(source, lab)
        homes = inv.acquire_homes(source, lab, names)
        again = inv.acquire_homes(source, lab, names)
        assert again == homes and len(homes) == 1
        assert homes[0].agent_id == op["parent_agent_id"] and homes[0].individual_envelope is not None
        source.verify()
    assert len(reads) == len(set(reads))


def test_descendant_own_material_uses_derived_digests_and_all_three_roles(signed_machine):
    config, op, envs = signed_machine
    child, plan = op["child_agent_id"], op["birth_plan"]
    for name, value in (("record.json", plan["record"]), ("spec.json", plan["child_spec"]),
                        ("birth_qualification.json", plan["qualification"])):
        ao.store(config.observer, "individuals/" + child + "/" + name, f.canonical(value))
    homes = collect(config.observer)
    assert len(homes) == 2
    home = next(h for h in homes if h.agent_id == child)
    assert home.individual_envelope is None
    assert home.record_bytes == f.canonical(plan["record"])
    assert home.qualification_bytes == f.canonical(plan["qualification"])
    assert home.admission_bytes == f.canonical(plan["admission"])
    for role in ("admission", "qualification", "statement"):
        assert getattr(home, role + "_envelope") == f.canonical(envs[child + "/" + role])
    assert home.statement_bytes is not None


@pytest.mark.parametrize("case", ["absent", "file", "link", "fifo", "unknown", "mode"])
def test_invalid_namespace_is_not_empty_population(signed_machine, case):
    config = signed_machine[0].observer
    parent = config.lab_root / "individuals"
    if case == "absent":
        for child in parent.iterdir():
            import shutil
            shutil.rmtree(child)
        parent.rmdir()
    elif case == "file":
        base.write(parent / ("e" * 64), b"not a directory")
    elif case == "link":
        (parent / ("e" * 64)).symlink_to(parent)
    elif case == "fifo":
        os.mkfifo(parent / ("e" * 64), 0o600)
    elif case == "unknown":
        (parent / "not-an-id").mkdir(mode=0o700)
    else:
        parent.chmod(0o755)
    with pytest.raises((o._Blocked, OSError)):
        collect(config)


def test_empty_stable_inventory_is_distinct_from_absence(signed_machine):
    config = signed_machine[0].observer
    import shutil
    for child in (config.lab_root / "individuals").iterdir():
        shutil.rmtree(child)
    assert collect(config) == ()


def test_65_and_66_names_capacity_precedes_home_payload(signed_machine, monkeypatch):
    config = signed_machine[0].observer
    parent = config.lab_root / "individuals"
    for i in range(64):
        (parent / f"{i:064x}").mkdir(mode=0o700)
    with ExitStack() as stack:
        source = inv.InventorySource(stack)
        lab = source.directory(config.lab_root)
        assert len(inv.home_names(source, lab)) == 65
        source.verify()
    (parent / ("e" * 64)).mkdir(mode=0o700)
    def forbidden(*args, **kwargs):
        pytest.fail("payload read before namespace bound")
    monkeypatch.setattr(os, "read", forbidden)
    with pytest.raises(e._Capacity, match="SOURCE_LIMIT") as caught:
        collect(config)
    assert caught.value.limit_name == "homes"


@pytest.mark.parametrize("directory,name", [
    ("tasks", "probe.json"), ("tasks", "a.b-c.json.tmp"), ("tasks", "a" * 64 + ".json"),
    ("results", "x.y-z.json"), ("results", "a" * 64 + ".json"),
])
def test_task_ids_follow_supervisor_grammar_and_opaque_files_are_never_read(signed_machine, monkeypatch, directory, name):
    config = signed_machine[0].observer
    home = next((config.lab_root / "individuals").iterdir())
    (home / directory).mkdir(mode=0o700)
    base.write(home / directory / name, b"opaque unread payload")
    base.write(home / "inflight.json", b"opaque")
    base.write(home / "usage.json", b"opaque")
    opaque = {(home / directory / name).stat().st_ino, (home / "inflight.json").stat().st_ino,
              (home / "usage.json").stat().st_ino}
    read = os.read
    def guard(fd, count):
        assert os.fstat(fd).st_ino not in opaque
        return read(fd, count)
    monkeypatch.setattr(os, "read", guard)
    assert len(collect(config)) == 1


@pytest.mark.parametrize("directory,name", [("tasks", "UPPER.json"), ("tasks", "a" * 65 + ".json"),
    ("tasks", "arbitrary"), ("results", "probe.json.tmp"), ("j01-lab-memory", "other.sqlite3"),
    ("home", "unexpected.json")])
def test_closed_layout_refuses_unexpected_names(signed_machine, directory, name):
    config = signed_machine[0].observer
    home = next((config.lab_root / "individuals").iterdir())
    if directory != "home":
        home = home / directory
        home.mkdir(mode=0o700)
    base.write(home / name, b"opaque")
    with pytest.raises(o._Blocked, match="SOURCE_NAMESPACE_INVALID"):
        collect(config)


@pytest.mark.parametrize("case", ["symlink", "hardlink", "fifo", "directory", "permissions"])
def test_opaque_layout_still_checks_types_and_private_permissions(signed_machine, case):
    config = signed_machine[0].observer
    home = next((config.lab_root / "individuals").iterdir())
    (home / "tasks").mkdir(mode=0o700)
    target = home / "tasks" / "probe.json"
    if case == "symlink":
        target.symlink_to(home / "record.json")
    elif case == "hardlink":
        os.link(home / "record.json", target)
    elif case == "fifo":
        os.mkfifo(target, 0o600)
    elif case == "directory":
        target.mkdir(mode=0o700)
    else:
        base.write(target, b"opaque")
        target.chmod(0o644)
    with pytest.raises((o._Blocked, OSError)):
        collect(config)


def test_private_entry_budget_is_shared_and_deduplicated(signed_machine):
    config = signed_machine[0].observer
    with ExitStack() as stack:
        source = inv.InventorySource(stack)
        lab = source.directory(config.lab_root)
        names = inv.home_names(source, lab)
        inv.acquire_homes(source, lab, names)
        count = len(source.private_entries)
        inv.acquire_homes(source, lab, names)
        source.verify()
        assert len(source.private_entries) == count
        # Boundary of the cumulative counter (not one cap per home/phase).
        for i in range(8192 - count):
            source._entry(-1, str(i))
        source._entry(-1, "0")
        with pytest.raises(e._Capacity) as caught:
            source._entry(-1, "over")
        assert caught.value.limit_name == "private_entries"


@pytest.mark.parametrize("mutation", ["added", "removed", "replaced", "read_enoent", "close"])
def test_mutation_and_io_errors_never_return_provisional_inventory(signed_machine, monkeypatch, mutation):
    config = signed_machine[0].observer
    home = next((config.lab_root / "individuals").iterdir())
    if mutation == "read_enoent":
        def fail(*args, **kwargs):
            raise FileNotFoundError("fixture read failure after open")
        monkeypatch.setattr(os, "read", fail)
    elif mutation == "close":
        close, once = os.close, []
        def fail(fd):
            close(fd)
            if not once:
                once.append(True)
                raise OSError("fixture close failure")
        monkeypatch.setattr(os, "close", fail)
    else:
        verify = inv.InventorySource.verify
        def fail(source):
            if mutation == "added":
                base.write(home / "usage.json", b"{}")
            elif mutation == "removed":
                (home / "record.json").unlink()
            else:
                raw = (home / "record.json").read_bytes()
                (home / "record.json").unlink()
                base.write(home / "record.json", raw)
            verify(source)
        monkeypatch.setattr(inv.InventorySource, "verify", fail)
    with pytest.raises((o._Blocked, OSError)):
        collect(config)


def test_stable_malformed_and_absent_material_remain_local_facts(signed_machine):
    config = signed_machine[0].observer
    home = next((config.lab_root / "individuals").iterdir())
    base.write(home / "record.json", b"not-json")
    (home / "spec.json").unlink()
    result = collect(config)
    assert result[0].record_bytes == b"not-json" and result[0].spec_bytes is None


def test_oversized_record_is_global_capacity_failure(signed_machine):
    config = signed_machine[0].observer
    home = next((config.lab_root / "individuals").iterdir())
    base.write(home / "record.json", b" " * 65537)
    with pytest.raises(e._Capacity) as caught:
        collect(config)
    assert caught.value.limit_name == "record_bytes"
