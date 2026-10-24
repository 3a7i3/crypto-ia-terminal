"""Bounded lexical formats only; embedded records require external validation."""

import hashlib
import json
import re

MAX_LINE = 262_144
MAX_LINES = 64
MAX_LOG = MAX_LINE * MAX_LINES
HEX = re.compile(r"[0-9a-f]{64}\Z")
BOOT = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
NAME = re.compile(r"[a-z][a-z0-9_.:-]{2,127}\Z")
CODE = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z")
KINDS = frozenset({"colony-lab.individual/0", "colony-lab.qualification/0",
                   "colony-registrar.admission/0", "colony-admission.attestation-statement/0"})
ENTRY_KEYS = frozenset({"schema", "operation_sha256", "attempt", "current_root_sha256",
                        "current_root_version", "boot_id", "event", "step", "code", "data"})
OP_KEYS = frozenset({"schema", "lab_id", "child_agent_id", "child_agent_spec_id", "parent_agent_id",
                     "policy_sha256", "historical_root_sha256", "historical_root_version", "items",
                     "presented", "budget", "permissions", "declared_diff", "birth_plan", "attempt", "boot_id"})
PLAN_KEYS = frozenset({"plan_schema", "policy_sha256", "parent", "child_spec", "record", "qualification",
                       "admission", "population", "population_count", "children_count", "budget_totals"})
BUDGET_KEYS = frozenset({"cpu_seconds", "wall_seconds", "memory_bytes", "output_bytes", "runs", "journal_events"})


class FormatError(ValueError):
    """Closed errors contain no submitted values."""

    def __init__(self, code="OPERATION_LOG_CORRUPT"):
        self.code = code
        super().__init__(code)


def require(condition):
    if not condition:
        raise FormatError()


def closed(value, keys):
    require(type(value) is dict and set(value) == set(keys))


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def hex64(value):
    return type(value) is str and HEX.fullmatch(value) is not None


def canonical(value):
    """Encoding compatible with A1 JSON convention, without importing runtime rules."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def _number(token):
    if len(token.lstrip("-")) > 128:
        raise FormatError("FORMAT_LIMIT_REACHED")
    return int(token)


def _reject(_):
    raise FormatError()


def _depth(raw):
    depth, quoted, escaped = 0, False, False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > 32:
                raise FormatError("FORMAT_LIMIT_REACHED")
        elif byte in (93, 125):
            depth -= 1


def loads(raw):
    """Strict canonical JSON; no schema validation or external authority."""
    require(type(raw) is bytes and len(raw) < MAX_LINE)
    try:
        _depth(raw)
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_int=_number, parse_float=_reject, parse_constant=_reject)
        require(canonical(value) == raw)
        return value
    except FormatError:
        raise
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise FormatError() from None


def _strings(value):
    return type(value) is list and all(type(x) is str for x in value) and value == sorted(set(value))


def validate_operation(op):
    """Lexical wrapper and visible bindings; not A1/trust/registrar acceptance."""
    closed(op, OP_KEYS)
    require(op["schema"] == "colony-admission.operation/0")
    require(type(op["lab_id"]) is str and NAME.fullmatch(op["lab_id"]))
    for key in ("child_agent_id", "child_agent_spec_id", "parent_agent_id", "policy_sha256",
                "historical_root_sha256"):
        require(hex64(op[key]))
    require(integer(op["attempt"], 1) and integer(op["historical_root_version"], 1))
    require(type(op["boot_id"]) is str and BOOT.fullmatch(op["boot_id"]))
    closed(op["budget"], BUDGET_KEYS)
    require(all(integer(x, 1) for x in op["budget"].values()))
    require(_strings(op["permissions"]) and _strings(op["declared_diff"]))
    closed(op["presented"], {"qualification", "statement", "admission"})
    for value in op["presented"].values():
        closed(value, {"record_sha256", "envelope_sha256"})
        require(all(hex64(x) for x in value.values()))
    require(type(op["items"]) is list)
    keys = []
    for item in op["items"]:
        closed(item, {"role", "kind", "subject", "record_sha256", "envelope_sha256"})
        require(item["role"] in ("DECISION", "POPULATION") and type(item["kind"]) is str
                and item["kind"] in KINDS)
        closed(item["subject"], {"agent_id", "agent_spec_id"})
        require(all(hex64(x) for x in item["subject"].values()))
        require(hex64(item["record_sha256"]) and hex64(item["envelope_sha256"]))
        keys.append((item["kind"], item["subject"]["agent_id"], item["subject"]["agent_spec_id"],
                     item["record_sha256"]))
    require(keys == sorted(set(keys)))
    plan = op["birth_plan"]
    closed(plan, PLAN_KEYS)
    require(plan["plan_schema"] == "colony-registrar.birth-plan/0")
    require(plan["policy_sha256"] == op["policy_sha256"])
    for key in ("parent", "child_spec", "record", "qualification", "admission"):
        require(type(plan[key]) is dict)
    require(type(plan["population"]) is list and all(hex64(x) for x in plan["population"]))
    require(plan["population"] == sorted(set(plan["population"])))
    require(integer(plan["population_count"]) and plan["population_count"] == len(plan["population"]))
    require(integer(plan["children_count"]) and plan["children_count"] <= plan["population_count"])
    closed(plan["budget_totals"], BUDGET_KEYS)
    require(all(integer(x) for x in plan["budget_totals"].values()))
    for obj, key, expected in ((plan["parent"], "agent_id", op["parent_agent_id"]),
                               (plan["child_spec"], "agent_id", op["child_agent_id"]),
                               (plan["child_spec"], "agent_spec_id", op["child_agent_spec_id"]),
                               (plan["record"], "agent_id", op["child_agent_id"]),
                               (plan["record"], "agent_spec_id", op["child_agent_spec_id"]),
                               (plan["record"], "budget", op["budget"]),
                               (plan["record"], "lab_permissions", op["permissions"])):
        require(canonical(obj.get(key)) == canonical(expected))
    require(digest(plan["qualification"]) == op["presented"]["qualification"]["record_sha256"])
    require(digest(plan["admission"]) == op["presented"]["admission"]["record_sha256"])


def validate_entry(entry):
    closed(entry, ENTRY_KEYS)
    require(entry["schema"] == "colony-admission.operation-entry/0")
    require(hex64(entry["operation_sha256"]) and hex64(entry["current_root_sha256"]))
    require(integer(entry["attempt"], 1) and integer(entry["current_root_version"], 1))
    require(type(entry["boot_id"]) is str and BOOT.fullmatch(entry["boot_id"]))
    require(type(entry["code"]) is str and CODE.fullmatch(entry["code"]))
    event, step, data = entry["event"], entry["step"], entry["data"]
    require(type(event) is str and type(data) is dict)
    if event == "PREPARED":
        closed(data, {"operation"})
        require(step is None)
        op = data["operation"]
        validate_operation(op)
        require(digest(op) == entry["operation_sha256"] and op["attempt"] == entry["attempt"])
        require(op["boot_id"] == entry["boot_id"])
        require(op["historical_root_sha256"] == entry["current_root_sha256"])
        require(op["historical_root_version"] == entry["current_root_version"])
    elif event == "INTERRUPTED_RECOVERED":
        closed(data, {"result"})
        require(step in ("D1", "D2", "D3") and data["result"] in ("ABSENT", "PRESENT", "PARTIAL"))
        require(not (step == "D1" and data["result"] == "PARTIAL"))
    elif event in ("TORN_TAIL_ACKNOWLEDGED", "COMMITTED", "DURABILITY_FAULT"):
        field = {"TORN_TAIL_ACKNOWLEDGED": "fragment_sha256", "COMMITTED": "record_sha256",
                 "DURABILITY_FAULT": "fault_sha256"}[event]
        closed(data, {field})
        require(hex64(data[field]))
        require(step in (None, "D1", "D2", "D3") if event == "DURABILITY_FAULT" else step is None)
    elif event in ("BEGIN", "DONE", "BEGIN_CANCELLED", "QUARANTINE_BEGIN", "QUARANTINE_DONE",
                   "SET_ASIDE_BEGIN", "SET_ASIDE_DONE"):
        closed(data, set())
        require(step in ("D1", "D2", "D3") if event in ("BEGIN", "DONE", "BEGIN_CANCELLED") else step == "D3")
    else:
        require(event in ("REFUSED", "ABANDONED", "TERMINATED", "FAILED_CONSUMED"))
        closed(data, set())
        require(step is None)
