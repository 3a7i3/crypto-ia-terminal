"""3C acceptance family C-01 (INV-01..03) through the public scan_population().

Real private LAB_TEST trees from the existing 3B/3C fixtures, test keys only.
Spies count calls and delegate to the real code: they never build a fact the
case has to demonstrate. Exact codes per variant are those observed and
admitted by the matrix; any divergence from the contract text is in the registry.
"""

import os
import shutil
import socket

import pytest

from colony_admission import physical_evidence as p
from colony_trust import trust
from tests.colony_admission import test_attestation_observer as ao
from tests.colony_admission import test_population_observer as tpo
from tests.colony_admission.acceptance.corpus import case

machine = tpo.machine
full_profile_machine = ao.full_profile_machine
NE = p.NE


class Spy:
    """Counts real signature verifications, ledger opens and ledger inspections of one scan."""

    def __init__(self, monkeypatch, config):
        self.signatures = self.ledger_opens = self.inspections = 0
        real, inspect, opener, spy = trust.Ed25519PublicKey, trust.inspect_operations_fd, os.open, self
        ledger = config.observer.ledger.name

        class Key:
            @staticmethod
            def from_public_bytes(data):
                key = real.from_public_bytes(data)

                class Counted:
                    def verify(self, signature, message):
                        spy.signatures += 1
                        return key.verify(signature, message)
                return Counted()

        def inspected(fd, operations):
            spy.inspections += 1
            return inspect(fd, operations)

        def opened(path, *args, **kwargs):
            spy.ledger_opens += os.path.basename(os.fsdecode(path)) == ledger
            return opener(path, *args, **kwargs)
        monkeypatch.setattr(trust, 'Ed25519PublicKey', Key)
        monkeypatch.setattr(trust, 'inspect_operations_fd', inspected)
        monkeypatch.setattr(os, 'open', opened)

    def nothing_after_inventory(self):
        # §3: step 5 (individuals/) precedes the ledger (step 6) and signatures (step 7).
        assert (self.signatures, self.ledger_opens, self.inspections) == (0, 0, 0)


def discarded(result, code):
    """BLOCKED with exactly one fixed code and no provisional payload (§12)."""
    assert result.status == 'BLOCKED' and result.blockers == (code,), result.blockers
    assert result.warnings == () and result.sources == () and result.metadata_sources == ()
    assert result.homes == () and result.operations == () and result.external_terminations == ()
    assert result.fault_bindings == () and result.action_facts == ()
    assert result.ledger_bytes is None and result.ledger_coverage == p.LedgerCoverage()
    assert result.limits.reached == ()
    # Never an empty population: every aggregate stays NE.
    assert (result.inventory, result.population, result.snapshot_completeness,
            result.global_identity_exclusions, result.log_coverage) == (NE,) * 5
    tpo.permanent(result)


def empty_universe(config):
    lab = config.observer.lab_root
    for name in ('individuals', 'admission-ops', 'registrar-admissions', 'admission-envelopes'):
        for entry in (lab / name).iterdir():
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()


@case('3C:INV-02', '3C:INV-03')
def test_spies_count_real_signatures_and_the_single_ledger_open(full_profile_machine, monkeypatch):
    # Positive control: the zero counts of INV-02/03 are meaningful only if the
    # same instruments see the real ledger open, inspection and signatures here.
    config, op = tpo.exact_own(full_profile_machine)
    tpo.proofs.home(config.observer, op)
    spy = Spy(monkeypatch, config)
    result = tpo.observe(config)
    assert result.status == 'OBSERVED', result.blockers
    assert spy.signatures > 0 and spy.ledger_opens == spy.inspections == 1


@case('3C:INV-01')
def test_inv_01_stable_empty_individuals_is_an_empty_population_not_a_failure(full_profile_machine, monkeypatch):
    config, _ = full_profile_machine
    empty_universe(config)
    spy = Spy(monkeypatch, config)
    result = tpo.observe(config)
    assert result.status == 'OBSERVED' and result.blockers == ()
    assert result.inventory == result.population == 'PASS' and result.homes == ()
    assert result.snapshot_completeness == result.global_identity_exclusions == result.log_coverage == 'PASS'
    # No candidate operation: ceilings exist only per operation (§2), so none is
    # PASS; the scope limit is the non-blocking warning, not a blocker.
    assert result.operations == ()
    assert result.warnings == ('NO_CURRENT_OPEN_OPERATION', 'NO_RUNTIME_OBSERVATION')
    assert result.ledger_coverage == p.LedgerCoverage('MATCH', 0, 0, 0, 0)
    # individuals/ was really acquired: its own directory stamp is in the metadata sources.
    individuals = (config.observer.lab_root / 'individuals').stat()
    stamp, = [x for x in result.metadata_sources if x.resource == 'individuals']
    assert (stamp.device, stamp.inode, stamp.mode & 0o7777) == (individuals.st_dev, individuals.st_ino, 0o700)
    assert (spy.signatures, spy.ledger_opens, spy.inspections) == (0, 1, 1)
    tpo.permanent(result)


INV_02 = [
    ('absent', 'SOURCE_UNAVAILABLE'),
    # Root bypasses DAC, so the private-mode check refuses; otherwise open() does.
    ('mode_000', 'SOURCE_PERMISSIONS' if os.geteuid() == 0 else 'SOURCE_UNAVAILABLE'),
    ('mode_755', 'SOURCE_PERMISSIONS'),
    ('symlink_to_directory', 'SOURCE_UNAVAILABLE'),
    ('symlink_to_file', 'SOURCE_UNAVAILABLE'),
    ('regular_file', 'SOURCE_UNAVAILABLE'),
    ('fifo', 'SOURCE_UNAVAILABLE'),
]


@pytest.mark.parametrize('variant,code', INV_02, ids=[x for x, _ in INV_02])
@case('3C:INV-02')
def test_inv_02_unavailable_individuals_is_never_an_empty_population(full_profile_machine, monkeypatch, variant, code):
    config, _ = full_profile_machine
    lab = config.observer.lab_root
    individuals = lab / 'individuals'
    if variant.startswith('mode_'):
        individuals.chmod(int(variant[5:], 8))
    elif variant == 'symlink_to_directory':
        shutil.move(individuals, lab.parent / 'moved-individuals')
        individuals.symlink_to(lab.parent / 'moved-individuals')
    else:
        shutil.rmtree(individuals)
        if variant == 'symlink_to_file':
            (lab.parent / 'plain-file').write_bytes(b'')
            individuals.symlink_to(lab.parent / 'plain-file')
        elif variant == 'regular_file':
            individuals.write_bytes(b'')
            individuals.chmod(0o600)
        elif variant == 'fifo':
            os.mkfifo(individuals, 0o600)
    spy = Spy(monkeypatch, config)
    try:
        result = tpo.observe(config)
    finally:
        if variant.startswith('mode_'):
            individuals.chmod(0o700)
    discarded(result, code)
    spy.nothing_after_inventory()


# Admitted by the matrix ("SOURCE_NAMESPACE_INVALID ou refus de source"); the
# hex64 typed entries diverge from the §4 wording, recorded in the registry.
INV_03 = [
    ('regular_file_hex64', 'SOURCE_UNAVAILABLE'),
    ('fifo_hex64', 'SOURCE_UNAVAILABLE'),
    ('socket_hex64', 'SOURCE_UNAVAILABLE'),
    ('symlink_hex64', 'SOURCE_UNAVAILABLE'),
    ('symlink_not_hex', 'SOURCE_NAMESPACE_INVALID'),
    ('unknown_regular_file', 'SOURCE_NAMESPACE_INVALID'),
    ('directory_not_hex', 'SOURCE_NAMESPACE_INVALID'),
    ('directory_uppercase_hex64', 'SOURCE_NAMESPACE_INVALID'),
    ('directory_hex63', 'SOURCE_NAMESPACE_INVALID'),
    ('directory_hex65', 'SOURCE_NAMESPACE_INVALID'),
]


@pytest.mark.parametrize('variant,code', INV_03, ids=[x for x, _ in INV_03])
@case('3C:INV-03')
def test_inv_03_invalid_individuals_entry_invalidates_everything_before_any_signature(
        full_profile_machine, monkeypatch, request, variant, code):
    config, op = tpo.exact_own(full_profile_machine)
    tpo.proofs.home(config.observer, op)  # otherwise complete: OBSERVED without the entry
    individuals = config.observer.lab_root / 'individuals'
    founder = individuals / op['parent_agent_id']
    name = {'directory_not_hex': 'not-an-id', 'directory_uppercase_hex64': 'E' * 64,
            'directory_hex63': 'e' * 63, 'directory_hex65': 'e' * 65,
            'unknown_regular_file': 'README', 'symlink_not_hex': 'link'}.get(variant, 'e' * 64)
    target = individuals / name
    if variant.startswith('directory_'):
        target.mkdir(mode=0o700)
    elif variant == 'fifo_hex64':
        os.mkfifo(target, 0o600)
    elif variant == 'socket_hex64':
        listener = socket.socket(socket.AF_UNIX)
        request.addfinalizer(listener.close)
        cwd = os.getcwd()
        os.chdir(individuals)  # AF_UNIX paths are short; bind relative to the directory
        try:
            listener.bind(name)
        finally:
            os.chdir(cwd)
    elif variant.startswith('symlink_'):
        target.symlink_to(founder)
    else:
        target.write_bytes(b'{}')
        target.chmod(0o600)
    spy = Spy(monkeypatch, config)
    result = tpo.observe(config)
    discarded(result, code)
    spy.nothing_after_inventory()
