"""Births under external control, with limits the lab itself does not have.

A descendant may become a parent once it is qualified by someone else under
criteria the frozen policy lists. Every birth also needs an admission decided
outside the lineage, keeps the child's identity distinct from every ancestor
and every admitted individual, stays within the policy's depth, population,
children, concurrency and cost limits, and grants nothing the parent does not
have. Records are re-verified from the founder down through the lab.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import stat
import threading
from contextlib import contextmanager
from typing import Any

from colony_lab import lineage
from colony_lab import supervisor as sup
from colony_lab.a1_identity import IdentityError, _canonical

POLICY_SCHEMA = "colony-registrar.policy/0"
ADMISSION_SCHEMA = "colony-registrar.admission/0"
POLICY_FILE = sup.REPO / "docs" / "colony_registrar" / "POLICY_G0.json"
POLICY_SHA256 = "1226d889505e84b970be47b442c1db33ab85bcdba953a4f818a1f5a7dec4caff"
POLICY_FIELDS = frozenset({"policy_schema", "revision", "max_generation", "max_population",
                           "max_children_per_parent", "max_concurrent_runs", "colony_budget",
                           "admissible_parent_criteria_sha256", "admitter_kinds"})
ADMISSION_FIELDS = frozenset({"admission_schema", "child_agent_id", "child_agent_spec_id", "parent_agent_id",
                              "admitter_kind", "admitter_id", "policy_sha256", "parent_qualification_sha256",
                              "budget", "lab_permissions", "declared_diff"})
# Hard ceilings: a caller's own policy can be stricter, never looser.
CEILINGS = {"max_generation": sup.MAX_LINEAGE_DEPTH, "max_population": 64, "max_children_per_parent": 8,
            "max_concurrent_runs": 4}
BUDGET_CEILING = {name: 64 * value for name, value in lineage.BUDGET_MAX.items()}
LOCK = "registrar.lock"
SLOTS = "registrar-slots"
ADMISSIONS = "registrar-admissions"


class RegistrarError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class BirthPlan:
    """Canonical immutable bytes; data returns a detached snapshot, never writable plan state."""
    __slots__ = ("_bytes", "_sha256")

    def __init__(self, data: dict) -> None:
        object.__setattr__(self, "_bytes", _canonical(data))
        object.__setattr__(self, "_sha256", hashlib.sha256(self._bytes).hexdigest())

    def __setattr__(self, name, value):
        raise AttributeError("BirthPlan is immutable")

    @property
    def sha256(self):
        return self._sha256

    @property
    def data(self):
        return json.loads(self._bytes)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def check_policy(policy: Any, pin_sha256: str) -> dict:
    """A copy of the policy equal to its pin, within the hard ceilings; POLICY_* refusals otherwise."""
    try:
        return copy.deepcopy(_check_policy(policy, pin_sha256))
    except TypeError:
        raise RegistrarError("POLICY_INVALID") from None


def _check_policy(policy: Any, pin_sha256: str) -> dict:
    try:
        digest = _sha(policy)
    except IdentityError:
        raise RegistrarError("POLICY_INVALID") from None
    if digest != pin_sha256:
        raise RegistrarError("POLICY_PIN_MISMATCH")
    if type(policy) is not dict or set(policy) != POLICY_FIELDS or policy["policy_schema"] != POLICY_SCHEMA or \
            type(policy["revision"]) is not str:
        raise RegistrarError("POLICY_INVALID")
    for name, ceiling in CEILINGS.items():
        if type(policy[name]) is not int or not 1 <= policy[name] <= ceiling:
            raise RegistrarError("POLICY_INVALID")
    budget = policy["colony_budget"]
    if type(budget) is not dict or set(budget) != set(BUDGET_CEILING) or \
            any(type(budget[n]) is not int or not 1 <= budget[n] <= c for n, c in BUDGET_CEILING.items()):
        raise RegistrarError("POLICY_INVALID")
    criteria, kinds = policy["admissible_parent_criteria_sha256"], policy["admitter_kinds"]
    if type(criteria) is not list or not criteria or criteria != sorted(set(criteria)) or \
            any(type(c) is not str or not lineage._HEX64.fullmatch(c) for c in criteria):
        raise RegistrarError("POLICY_INVALID")
    if type(kinds) is not list or not kinds or kinds != sorted(set(kinds)) or \
            not set(kinds) <= lineage.REVIEWER_KINDS:
        raise RegistrarError("POLICY_INVALID")
    return policy


def load_policy() -> tuple[dict, str]:
    """The frozen policy g0 and its pin."""
    try:
        policy = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RegistrarError("POLICY_INVALID") from None
    return check_policy(policy, POLICY_SHA256), POLICY_SHA256


def _excluded_in(name: str, agents: set) -> bool:
    return any(type(agent) is str and agent[:16] in name for agent in agents)


def _same(a: Any, b: Any) -> bool:
    """Equal canonical encodings: true or 1.0 never stand for 1."""
    try:
        return _canonical(a) == _canonical(b)
    except IdentityError:
        return False


def _read_admission(path):
    """Bounded regular-file read; never block on a FIFO supplied in the lab root."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise sup.LabError("INDIVIDUAL_INVALID")
            raw = bytearray()
            while len(raw) <= sup.MAX_FILE_BYTES:
                chunk = os.read(fd, min(65536, sup.MAX_FILE_BYTES + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
        finally:
            os.close(fd)
        if len(raw) > sup.MAX_FILE_BYTES:
            raise sup.LabError("INDIVIDUAL_INVALID")
        return sup._strict_json(bytes(raw), "INDIVIDUAL_INVALID")
    except OSError:
        raise sup.LabError("INDIVIDUAL_INVALID") from None


@contextmanager
def _flock(path, busy: str):
    """An advisory lock on a file that is never deleted; the kernel releases it if the process dies."""
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RegistrarError(busy) from None
        yield
    finally:
        os.close(fd)


class Registrar:
    """The operator's gate for births; it holds no handle an individual can reach."""

    def __init__(self, supervisor: sup.Supervisor, *, policy: Any = None, policy_sha256: str | None = None) -> None:
        if policy is None:
            self.policy, self.policy_sha256 = load_policy()
        else:
            self.policy, self.policy_sha256 = check_policy(policy, policy_sha256), policy_sha256
        self.lab = supervisor
        self._owner = None
        self._depth = 0

    # ── Population and admissions, read through the lab ────────────────────
    def _population(self, exclude=None) -> list[dict]:
        """Every admitted individual, each re-verified; an unreadable one refuses the birth."""
        individuals = self.lab.root / "individuals"
        if not individuals.is_dir():
            return []
        records = []
        for home in sorted(individuals.iterdir()):
            if home.name == exclude:
                continue
            try:
                records.append(self.lab.load(home.name)[0])
            except (sup.LabError, IdentityError, TypeError, KeyError, AttributeError):
                raise RegistrarError("POPULATION_UNVERIFIABLE") from None
        return records

    def _admissions(self, *, create=True):
        """The admissions directory, which must be a real directory of the lab root, never a link."""
        path = self.lab.root / ADMISSIONS
        if create:
            try:
                os.mkdir(path, 0o700)
            except FileExistsError:
                pass
        if not path.exists() and not path.is_symlink() and not create:
            return path
        info = os.lstat(path)
        if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
            raise RegistrarError("LAB_IO_ERROR")
        return path

    def _check_admitted(self, record: dict, parent: dict, colony: frozenset) -> None:
        """A descendant ancestor passes today the admission checks its own birth needed."""
        try:
            admission = _read_admission(self._admissions(create=False) / f"{record['agent_id']}.json")
            qualification = sup._read_json(self.lab._home(record["agent_id"]) / "birth_qualification.json")
            ids = {"agent_id": record["agent_id"], "agent_spec_id": record["agent_spec_id"]}
            self._check_admission(admission, ids, parent, colony)
            lineage.check_qualification(qualification, parent, also_excluded=colony)
            bound = qualification["criteria_sha256"] in self.policy["admissible_parent_criteria_sha256"] and \
                _same(admission["parent_qualification_sha256"], _sha(qualification)) and \
                _same(admission["budget"], record["budget"]) and \
                _same(admission["lab_permissions"], record["lab_permissions"]) and \
                _same(admission["declared_diff"], record["genotype"]["declared_diff"])
        except (RegistrarError, sup.LabError, lineage.LineageError, IdentityError, TypeError, KeyError):
            bound = False
        if not bound:
            raise RegistrarError("ANCESTOR_NOT_ADMITTED")

    def _ancestry(self, record: dict) -> list[dict]:
        """The record and its ancestors, from the record up to the founder."""
        chain = [record]
        while chain[-1]["role"] == "DESCENDANT":
            chain.append(self.lab.load(chain[-1]["lineage"]["parent_agent_id"])[0])
        return chain

    # ── Births ─────────────────────────────────────────────────────────────
    def birth(self, parent_agent_id: str, child_spec: dict, *, parent_qualification: Any, admission: Any,
              lab_permissions: Any, budget: Any, declared_diff: Any) -> dict:
        if self.lab.stopped:
            raise RegistrarError("LAB_STOPPED")
        try:
            with self.exclusive():
                plan = self.prepare(parent_agent_id, child_spec, parent_qualification=parent_qualification,
                                    admission=admission, lab_permissions=lab_permissions,
                                    budget=budget, declared_diff=declared_diff)
                self.commit(plan, step="ADMISSION")
                return self.commit(plan, step="HOME")
        except (sup.LabError, lineage.LineageError) as exc:
            raise RegistrarError(exc.code) from None
        except (TypeError, KeyError, AttributeError, IdentityError):
            raise RegistrarError("BIRTH_INPUT_INVALID") from None
        except OSError:
            raise RegistrarError("LAB_IO_ERROR") from None

    @contextmanager
    def exclusive(self):
        """L1, reentrant only on this instance and the same owning thread."""
        owner = (os.getpid(), threading.get_ident())
        if self._owner == owner:
            self._depth += 1
            try:
                yield self
            finally:
                self._depth -= 1
            return
        with _flock(self.lab.root / LOCK, "REGISTRAR_BUSY"):
            self._owner, self._depth = owner, 1
            try:
                yield self
            finally:
                self._owner, self._depth = None, 0

    def prepare(self, parent_agent_id, child_spec, *, parent_qualification, admission,
                lab_permissions, budget, declared_diff):
        """No locks, directories or records created. Caller holds L1 across a transaction."""
        try:
            return self._prepare(parent_agent_id, child_spec, parent_qualification, admission,
                                 lab_permissions, budget, declared_diff)
        except (sup.LabError, lineage.LineageError) as exc:
            raise RegistrarError(exc.code) from None
        except (TypeError, KeyError, AttributeError, IdentityError):
            raise RegistrarError("BIRTH_INPUT_INVALID") from None
        except OSError:
            raise RegistrarError("LAB_IO_ERROR") from None

    def _prepare(self, parent_agent_id, child_spec, qualification, admission, permissions, budget,
                 declared_diff, *, own_child=None):
        if self.lab.stopped:
            raise RegistrarError("LAB_STOPPED")
        policy = check_policy(self.policy, self.policy_sha256)
        parent, parent_spec = self.lab.load(parent_agent_id)
        ancestry = self._ancestry(parent)
        ids = lineage._spec(child_spec)
        child_id = ids["agent_id"]
        ancestors = {agent["agent_id"] for agent in ancestry}
        if child_id in ancestors:
            raise RegistrarError("CYCLE_DENIED")
        population = self._population(exclude=own_child)
        admitted = {agent["agent_id"] for agent in population}
        if child_id in admitted:
            raise RegistrarError("ALREADY_ADMITTED")
        excluded = frozenset({child_id, *ancestors, *admitted})
        for agent, its_parent in zip(ancestry, ancestry[1:]):  # every descendant ancestor, parent first
            self._check_admitted(agent, its_parent, excluded)
        if parent["lineage"]["generation"] + 1 > policy["max_generation"]:
            raise RegistrarError("GENERATION_LIMIT")
        if len(population) + 1 > policy["max_population"]:
            raise RegistrarError("POPULATION_LIMIT")
        children = [a for a in population if a["lineage"]["parent_agent_id"] == parent["agent_id"]]
        if len(children) + 1 > policy["max_children_per_parent"]:
            raise RegistrarError("CHILDREN_LIMIT")
        # Prior qualification by someone outside the whole colony, under admissible criteria.
        lineage.check_qualification(qualification, parent, also_excluded=excluded)
        if qualification["criteria_sha256"] not in policy["admissible_parent_criteria_sha256"]:
            raise RegistrarError("CRITERIA_NOT_ADMISSIBLE")
        self._check_admission(admission, ids, parent, excluded)
        # Explicit, narrower permissions; costs bounded by the parent and by the colony.
        child_budget = lineage._budget(budget)
        if any(child_budget[name] > parent["budget"][name] for name in child_budget):
            raise RegistrarError("BUDGET_ESCALATION")
        for name, cap in policy["colony_budget"].items():
            if sum(agent["budget"][name] for agent in population) + child_budget[name] > cap:
                raise RegistrarError("COLONY_BUDGET_EXCEEDED")
        if declared_diff != lineage.spec_diff(parent_spec, child_spec):
            raise RegistrarError("UNDECLARED_MUTATION")
        granted = lineage._permissions(permissions, child_spec)
        if not set(granted) <= set(parent["lab_permissions"]):
            raise RegistrarError("PERMISSION_ESCALATION")
        # The admission decided exactly this birth: this qualification, budget, permissions and diff.
        if not (_same(admission["parent_qualification_sha256"], _sha(qualification)) and
                _same(admission["budget"], child_budget) and _same(admission["lab_permissions"], granted) and
                _same(admission["declared_diff"], declared_diff)):
            raise RegistrarError("ADMISSION_NOT_FOR_THIS_BIRTH")
        source = parent["lineage"]
        record = lineage._seal({
            "individual_schema": lineage.INDIVIDUAL_SCHEMA, **ids, "role": "DESCENDANT",
            "lineage": {"lineage_id": source["lineage_id"], "founder_agent_id": source["founder_agent_id"],
                        "parent_agent_id": parent["agent_id"], "parent_agent_spec_id": parent["agent_spec_id"],
                        "generation": source["generation"] + 1},
            "genotype": {"base_agent_spec_id": parent["agent_spec_id"], "declared_diff": list(declared_diff)},
            "lab_permissions": granted, "budget": child_budget, "memory": dict(lineage.MEMORY),
            "credentials": "NONE", "registry": dict(lineage.REGISTRY), "operational_authority": "DENIED",
        })
        lineage.verify_record(record, child_spec, parent, parent_spec)
        if self.lab.stopped:  # read again: STOP may have been set while the checks ran
            raise RegistrarError("LAB_STOPPED")
        existing = self._admissions(create=False) / f"{child_id}.json"
        if existing.exists() or existing.is_symlink():
            try:
                same = _same(_read_admission(existing), admission)
            except sup.LabError:
                same = False
            if not same:
                raise RegistrarError("ADMISSION_CONFLICT")
        return BirthPlan({"plan_schema": "colony-registrar.birth-plan/0", "policy_sha256": self.policy_sha256,
                          "parent": parent, "child_spec": child_spec, "record": record,
                          "qualification": qualification, "admission": admission,
                          "population": sorted([_sha(a) for a in population]),
                          "population_count": len(population), "children_count": len(children),
                          "budget_totals": {n: sum(a["budget"][n] for a in population) for n in child_budget}})

    def commit(self, plan, *, step):
        """D2 or D3 under L1. RegistrarError = pre-write refusal; write/Supervisor errors stay distinct."""
        if self._owner != (os.getpid(), threading.get_ident()):
            raise RegistrarError("LOCK_REQUIRED")
        if type(plan) is not BirthPlan or step not in {"ADMISSION", "HOME"}:
            raise RegistrarError("PLAN_INVALID")
        try:
            data = plan.data
            if _sha(data) != plan.sha256:
                raise RegistrarError("PLAN_INVALID")
            record = data["record"]
            # Validate the frozen material against current facts, without replacing it.
            checked = self._prepare(data["parent"]["agent_id"], data["child_spec"], data["qualification"],
                                    data["admission"], record["lab_permissions"], record["budget"],
                                    record["genotype"]["declared_diff"], own_child=record["agent_id"])
            if checked.sha256 != plan.sha256:
                raise RegistrarError("POPULATION_CHANGED")
            if self.lab.stopped:
                raise RegistrarError("LAB_STOPPED")
            if step == "HOME":
                admission_path = self._admissions(create=False) / f"{record['agent_id']}.json"
                if not admission_path.is_file() or not _same(_read_admission(admission_path), data["admission"]):
                    raise RegistrarError("ADMISSION_REQUIRED")
                home = self.lab._home(record["agent_id"])
                if home.exists() or home.is_symlink():
                    self._check_own_home(home, data)
                    return self._result(record)
        except (sup.LabError, lineage.LineageError) as exc:
            raise RegistrarError(exc.code) from None
        except (KeyError, TypeError, AttributeError, IdentityError, ValueError) as exc:
            if isinstance(exc, RegistrarError):
                raise
            raise RegistrarError("PLAN_INVALID") from None
        # Everything below is an effect: never map a failure to a pre-write refusal.
        if step == "ADMISSION":
            try:
                self._record_admission(record["agent_id"], data["admission"])
            except RegistrarError as exc:
                raise OSError("admission write boundary: " + exc.code) from exc
            return {"status": "ADMISSION_RECORDED", "agent_id": record["agent_id"]}
        result = self.lab.admit(record, data["child_spec"], parent_qualification=data["qualification"])
        return {**result, "generation": record["lineage"]["generation"], "record": record}

    @staticmethod
    def _result(record):
        return {"status": "ADMITTED_TO_LAB", "agent_id": record["agent_id"], "registry": record["registry"],
                "generation": record["lineage"]["generation"], "record": record}

    def _check_own_home(self, home, data):
        if home.is_symlink() or not home.is_dir():
            raise RegistrarError("HOME_CONFLICT")
        for name, expected in (("spec.json", data["child_spec"]), ("record.json", data["record"]),
                               ("birth_qualification.json", data["qualification"])):
            path = home / name
            if path.is_symlink() or not path.is_file() or not _same(sup._read_json(path), expected):
                raise RegistrarError("HOME_CONFLICT")
        for name in ("tasks", "results", sup.JOURNAL_DIR):
            path = home / name
            if path.is_symlink() or not path.is_dir():
                raise RegistrarError("HOME_CONFLICT")
        usage_path = home / "usage.json"
        if usage_path.is_symlink() or not usage_path.is_file():
            raise RegistrarError("HOME_CONFLICT")
        usage = sup._read_json(usage_path)
        if type(usage) is not dict or set(usage) != {"runs"} or type(usage["runs"]) is not int or usage["runs"] < 0:
            raise RegistrarError("HOME_CONFLICT")
        store = home / sup.JOURNAL_DIR / "activity.sqlite3"
        if store.is_symlink() or not store.is_file() or store.stat().st_size == 0:
            raise RegistrarError("HOME_CONFLICT")
        # Runtime files may have changed after DONE D3. The controller alone decides cold recovery.
        self.lab.load(data["record"]["agent_id"])

    def _record_admission(self, child_id: str, admission: dict) -> None:
        path, data = self._admissions() / f"{child_id}.json", sup._dump(admission)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            # Prechecked under L1; a bypass racing us is an I/O uncertainty, not a pre-write refusal.
            if _same(_read_admission(path), admission):
                return
            raise OSError("admission changed during commit") from None
        try:
            view = memoryview(data)
            while view:
                count = os.write(fd, view)
                if count <= 0:
                    raise OSError("admission write made no progress")
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        for directory in (path.parent, self.lab.root):
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def _check_admission(self, admission: Any, ids: dict, parent: dict, excluded: frozenset) -> None:
        if type(admission) is not dict or set(admission) != ADMISSION_FIELDS or \
                admission["admission_schema"] != ADMISSION_SCHEMA:
            raise RegistrarError("ADMISSION_INVALID")
        if not (_same(admission["child_agent_id"], ids["agent_id"]) and
                _same(admission["child_agent_spec_id"], ids["agent_spec_id"]) and
                _same(admission["parent_agent_id"], parent["agent_id"]) and
                _same(admission["policy_sha256"], self.policy_sha256)):
            raise RegistrarError("ADMISSION_NOT_FOR_THIS_BIRTH")
        admitter = admission["admitter_id"]
        if admission["admitter_kind"] not in self.policy["admitter_kinds"] or type(admitter) is not str or \
                not lineage._REVIEWER_ID.fullmatch(admitter) or \
                _excluded_in(admitter, excluded):
            raise RegistrarError("SELF_ADMISSION_DENIED")

    # ── Runs, within the colony's concurrency ──────────────────────────────
    def run(self, agent_id: str, task: Any) -> dict:
        try:
            return self._run(agent_id, task)
        except OSError:
            raise RegistrarError("LAB_IO_ERROR") from None

    def _run(self, agent_id: str, task: Any) -> dict:
        slots = self.lab.root / SLOTS
        slots.mkdir(mode=0o700, exist_ok=True)
        if not stat.S_ISDIR(os.lstat(slots).st_mode):
            raise RegistrarError("LAB_IO_ERROR")
        for index in range(self.policy["max_concurrent_runs"]):
            try:
                with _flock(slots / f"slot-{index}", "SLOT_BUSY"):
                    return self.lab.run(agent_id, task)
            except RegistrarError as exc:
                if exc.code != "SLOT_BUSY":
                    raise
        raise RegistrarError("CONCURRENCY_LIMIT")
