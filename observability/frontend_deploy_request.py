"""Pure candidate validation. Never authenticates a ticket or executes a deployment."""

from __future__ import annotations

import json
import re

AUDIENCE = "frontend-deploy-gateway"
SERVICE = "crypto-operator-web.service"
OPERATIONS = frozenset({"activate_frontend", "rollback_frontend"})
BINDINGS = frozenset(
    {
        "ticket_id",
        "actor",
        "audience",
        "operation",
        "service",
        "source_sha",
        "source_merge_sha",
        "bundle_sha256",
        "previous_release_sha",
    }
)
TICKET_KEYS = BINDINGS | {"operator", "approved", "issued_at", "expires_at"}


def decode_document(raw: bytes) -> dict:
    if len(raw) > 8192:
        raise ValueError("DOCUMENT_TOO_LARGE")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_KEY")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("NON_FINITE_JSON")

    value = json.loads(
        raw, object_pairs_hook=pairs, parse_constant=constant, parse_float=constant
    )
    if type(value) is not dict:
        raise ValueError("OBJECT_REQUIRED")
    return value


def validate_candidate(
    ticket: dict, request: dict, *, now: int, consumed: frozenset[str]
) -> dict:
    """Check shape and binding against a caller-supplied ticket, not its authority.

    A future admitted broker must obtain tickets/clock/consumption from trusted
    stores and verify identity, source/CI and atomic use. No such broker exists
    in this module. A forged but well-shaped ticket can pass these checks.
    """
    if type(ticket) is not dict or set(ticket) != TICKET_KEYS:
        raise ValueError("INVALID_TICKET_KEYS")
    if type(request) is not dict or set(request) != BINDINGS:
        raise ValueError("INVALID_REQUEST_KEYS")
    if type(now) is not int or now < 0:
        raise ValueError("INVALID_CLOCK")
    if ticket["approved"] is not True or ticket["operator"] != "mathieu":
        raise ValueError("EXPLICIT_OPERATOR_APPROVAL_REQUIRED")
    if ticket["actor"] != "chatgpt-ro" or ticket["audience"] != AUDIENCE:
        raise ValueError("WRONG_ACTOR_OR_AUDIENCE")
    if (
        ticket["service"] != SERVICE
        or type(ticket["operation"]) is not str
        or ticket["operation"] not in OPERATIONS
    ):
        raise ValueError("SERVICE_OR_OPERATION_FORBIDDEN")
    for key in ("source_sha", "source_merge_sha", "previous_release_sha"):
        if type(ticket[key]) is not str or not re.fullmatch(
            r"[0-9a-f]{40}", ticket[key]
        ):
            raise ValueError("INVALID_SOURCE_IDENTITY")
    for key, length in (("ticket_id", 32), ("bundle_sha256", 64)):
        if type(ticket[key]) is not str or not re.fullmatch(
            r"[0-9a-f]{" + str(length) + r"}", ticket[key]
        ):
            raise ValueError("INVALID_TICKET_OR_BUNDLE_IDENTITY")
    issued, expires = ticket["issued_at"], ticket["expires_at"]
    if (
        type(issued) is not int
        or type(expires) is not int
        or not 0 <= issued <= now < expires
    ):
        raise ValueError("EXPIRED_OR_NOT_YET_VALID")
    if expires - issued > 3600:
        raise ValueError("UNBOUNDED_APPROVAL_WINDOW")
    if ticket["ticket_id"] in consumed:
        raise ValueError("TICKET_ALREADY_CONSUMED")
    if any(
        type(request[key]) is not str or request[key] != ticket[key] for key in BINDINGS
    ):
        raise ValueError("REQUEST_TICKET_BINDING_MISMATCH")
    return {
        "state": "CANDIDATE_VALID_REQUIRES_TRUSTED_ADMISSION",
        "ticket_id": ticket["ticket_id"],
        "service": SERVICE,
        "operation": ticket["operation"],
        "privileged_execution": False,
        "ticket_authenticity": "NOT_VERIFIED",
        "source_ci_authority": "NOT_VERIFIED",
        "atomic_consumption": "NOT_IMPLEMENTED",
    }
