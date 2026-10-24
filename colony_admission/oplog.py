"""Pure projection of bounded operation-log bytes, never an admission verdict."""

import hashlib
from dataclasses import dataclass, field

from .formats import MAX_LINE, MAX_LINES, MAX_LOG, FormatError, digest, loads, require, validate_entry

_RESERVE = frozenset({"TERMINATED", "FAILED_CONSUMED", "ABANDONED", "SET_ASIDE_BEGIN", "SET_ASIDE_DONE",
                       "TORN_TAIL_ACKNOWLEDGED"})
_TERMINAL_CODES = frozenset({"OPERATOR_TERMINATED", "TRUST_REVOKED_AFTER_CONSUMPTION"})


@dataclass(frozen=True)
class AttemptSummary:
    operation_sha256: str
    attempt: int
    start_line: int
    end_line: int
    terminal_claim: str | None


@dataclass(frozen=True)
class LogProjection:
    status: str
    operation_sha256: str | None = None
    attempt: int | None = None
    last_completed_step: str | None = None
    pending_step: str | None = None
    d3_started: bool = False
    terminal_claim: str | None = None
    physical_lines: int = 0
    code: str = "LOG_OBSERVED"
    history: tuple[AttemptSummary, ...] = ()
    recovery_step: str | None = None
    recovery_result: str | None = None
    last_completed_source: str | None = None
    schema: str = field(default="colony-admission.log-projection/0", init=False)
    accepted: bool = field(default=False, init=False)
    external_facts: str = field(default="NOT_EVALUATED", init=False)


class _Machine:
    def __init__(self):
        self.op = None
        self.child = None
        self.mode = "EMPTY"
        self.level = 0
        self.pending = None
        self.begin_boot = None
        self.d3 = False
        self.terminal = None
        self.history = []
        self.start = 0
        self.last = 0
        self.last_code = "LOG_OBSERVED"
        self.operation_hash = None
        self.recovery_step = self.recovery_result = self.completed_source = None

    def _summary(self):
        return AttemptSummary(self.operation_hash, self.op["attempt"], self.start, self.last, self.terminal)

    def apply(self, e, position, *, acknowledged=False):
        event, step = e["event"], e["step"]
        if event == "TORN_TAIL_ACKNOWLEDGED":
            require(acknowledged)
            if self.op is None:
                self.mode = "PREPARATION_INCOMPLETE"
            else:
                require(e["operation_sha256"] == self.operation_hash and e["attempt"] == self.op["attempt"])
            self.last = position
            return
        if event == "PREPARED":
            op = e["data"]["operation"]
            if self.op is not None:
                require(self.mode == "TERMINAL_CLAIM" and self.terminal in ("REFUSED", "ABANDONED"))
                require(op["attempt"] > self.op["attempt"] and op["child_agent_id"] == self.child)
                self.history.append(self._summary())
            self.op, self.child = op, op["child_agent_id"]
            self.operation_hash = e["operation_sha256"]
            self.mode, self.level, self.pending = "OPEN", 0, None
            self.terminal, self.d3, self.start = None, False, position
            self.recovery_step = self.recovery_result = None
            self.completed_source = "PREPARED"
        else:
            require(self.op is not None)
            require(e["operation_sha256"] == self.operation_hash and e["attempt"] == self.op["attempt"])
            k = int(step[1]) if step is not None else None
            if event == "BEGIN":
                require(self.mode in ("OPEN", "RECOVERED", "PARTIAL_D2") and k == self.level + 1)
                self.mode, self.pending, self.begin_boot = "INTERRUPTED", k, e["boot_id"]
                self.d3 = self.d3 or k == 3
                self.recovery_step = self.recovery_result = None
            elif event in ("DONE", "BEGIN_CANCELLED", "INTERRUPTED_RECOVERED"):
                require(self.mode == "INTERRUPTED" and k == self.pending)
                if event == "DONE":
                    self.level, self.mode = k, "OPEN"
                    self.completed_source = "DONE"
                elif event == "BEGIN_CANCELLED":
                    require(k in (2, 3))  # D1 has no registrar commit to cancel.
                    self.mode = "OPEN"
                else:
                    result = e["data"]["result"]
                    self.recovery_step, self.recovery_result = step, result
                    if result != "ABSENT":
                        require(e["boot_id"] != self.begin_boot)
                    if result == "PRESENT":
                        self.level, self.mode = k, "RECOVERED"
                        self.completed_source = "RECOVERY_PRESENT"
                    elif result == "ABSENT":
                        self.mode = "RECOVERED"
                    else:
                        self.mode = "PARTIAL_D2" if k == 2 else "PARTIAL_D3"
                self.pending = None
            elif event == "REFUSED":
                require(self.mode in ("OPEN", "RECOVERED") and self.level == 0)
                self.mode, self.terminal = "TERMINAL_CLAIM", event
            elif event == "ABANDONED":
                require(self.mode in ("OPEN", "RECOVERED", "TERMINATING") and self.level == 0)
                self.mode, self.terminal = "TERMINAL_CLAIM", event
                self.pending = None
            elif event == "TERMINATED":
                require(self.mode in ("OPEN", "RECOVERED", "INTERRUPTED", "PARTIAL_D2", "PARTIAL_D3",
                                      "QUARANTINING", "BLOCKED_DURABILITY"))
                require(self.terminal is None and e["code"] == "OPERATOR_TERMINATED")
                self.mode = "TERMINATING"
            elif event == "FAILED_CONSUMED":
                require(e["code"] in _TERMINAL_CODES)
                if self.mode == "TERMINATING":
                    require(e["code"] == "OPERATOR_TERMINATED")
                else:
                    require(self.mode in ("OPEN", "RECOVERED") and self.level >= 1)
                    require(e["code"] == "TRUST_REVOKED_AFTER_CONSUMPTION")
                self.mode, self.terminal, self.pending = "TERMINAL_CLAIM", event, None
            elif event == "COMMITTED":
                require(self.mode in ("OPEN", "RECOVERED") and self.level == 3)
                require(e["data"]["record_sha256"] == digest(self.op["birth_plan"]["record"]))
                self.mode, self.terminal = "TERMINAL_CLAIM", event
            elif event == "DURABILITY_FAULT":
                require(self.mode in ("INTERRUPTED", "QUARANTINING", "SETTING_ASIDE"))
                require(k == (self.pending if self.mode == "INTERRUPTED" else 3))
                self.mode = "BLOCKED_DURABILITY"
            elif event == "QUARANTINE_BEGIN":
                require(self.mode == "PARTIAL_D3" and self.level == 2)
                self.mode = "QUARANTINING"
            elif event == "QUARANTINE_DONE":
                require(self.mode == "QUARANTINING")
                self.mode = "OPEN"
                self.recovery_step = self.recovery_result = None
            elif event == "SET_ASIDE_BEGIN":
                require(self.mode == "TERMINAL_CLAIM" and self.terminal == "FAILED_CONSUMED" and self.d3)
                self.mode = "SETTING_ASIDE"
            elif event == "SET_ASIDE_DONE":
                require(self.mode == "SETTING_ASIDE")
                self.mode = "CLEARED_TERMINAL"
            else:
                raise FormatError()
        self.last, self.last_code = position, e["code"]

    def projection(self, count, *, torn=False):
        history = tuple(self.history + ([self._summary()] if self.op is not None else []))
        mode = {"PARTIAL_D2": "RECOVERED", "PARTIAL_D3": "RECOVERED",
                "CLEARED_TERMINAL": "TERMINAL_CLAIM"}.get(self.mode, self.mode)
        return LogProjection("TORN_TAIL" if torn else mode, self.operation_hash,
                             None if self.op is None else self.op["attempt"],
                             None if self.op is None else f"D{self.level}",
                             None if self.pending is None else f"D{self.pending}", self.d3,
                             None if torn else self.terminal, count,
                             "TORN_TAIL" if torn else self.last_code, history,
                             self.recovery_step, self.recovery_result, self.completed_source)


def _reserve(e, position, counts):
    if position <= 56:
        return
    event = e["event"]
    require(event in _RESERVE)
    counts[event] = counts.get(event, 0) + 1
    require(counts[event] <= (2 if event == "TORN_TAIL_ACKNOWLEDGED" else 1))


def project_log(raw: bytes) -> LogProjection:
    """Observe supplied bytes only. Even a COMMITTED claim has accepted=False.

    All external guards remain NOT_EVALUATED. Malformed input never returns a
    usable terminal prefix, nor leaks rejected text through exception messages.
    """
    if type(raw) is not bytes:
        return LogProjection("CORRUPT", code="INVALID_INPUT")
    if len(raw) > MAX_LOG:
        return LogProjection("CORRUPT", code="OPERATION_LOG_FULL")
    lines = raw.split(b"\n")
    torn = bool(lines[-1])
    if not torn:
        lines.pop()
    count = len(lines)
    if count > MAX_LINES or any(len(line) + 1 > MAX_LINE for line in lines):
        return LogProjection("CORRUPT", physical_lines=count, code="OPERATION_LOG_FULL")
    machine, reserve, index = _Machine(), {}, 0
    try:
        while index < count:
            if torn and index == count - 1:
                return machine.projection(count, torn=True)
            line = lines[index]
            try:
                value = loads(line)
            except FormatError as exc:
                if exc.code == "FORMAT_LIMIT_REACHED":
                    raise
                # Only lexical noncanonical bytes may be acknowledged. A valid
                # canonical but schema-invalid event is never erased this way.
                require(index + 1 < count and not (torn and index + 1 == count - 1))
                value = loads(lines[index + 1])
                validate_entry(value)
                require(value["event"] == "TORN_TAIL_ACKNOWLEDGED")
                require(value["data"]["fragment_sha256"] == hashlib.sha256(line).hexdigest())
                _reserve(value, index + 2, reserve)
                machine.apply(value, index + 2, acknowledged=True)
                index += 2
                continue
            validate_entry(value)
            _reserve(value, index + 1, reserve)
            machine.apply(value, index + 1)
            index += 1
        return machine.projection(count)
    except FormatError as exc:
        return LogProjection("CORRUPT", physical_lines=count, code=exc.code)
    except (TypeError, KeyError, ValueError, UnicodeError, RecursionError, OverflowError):
        return LogProjection("CORRUPT", physical_lines=count, code="OPERATION_LOG_CORRUPT")
