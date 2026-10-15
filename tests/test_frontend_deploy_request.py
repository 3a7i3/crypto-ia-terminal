"""Offline request fixtures, no root service, socket, sudo or deployment."""

import pytest

from observability.frontend_deploy_request import (
    BINDINGS,
    decode_document,
    validate_candidate,
)


def fixture():
    ticket = {
        "ticket_id": "a" * 32,
        "actor": "chatgpt-ro",
        "operator": "mathieu",
        "audience": "frontend-deploy-gateway",
        "operation": "activate_frontend",
        "service": "crypto-operator-web.service",
        "source_sha": "b" * 40,
        "source_merge_sha": "c" * 40,
        "previous_release_sha": "d" * 40,
        "bundle_sha256": "e" * 64,
        "approved": True,
        "issued_at": 100,
        "expires_at": 200,
    }
    return ticket, {key: ticket[key] for key in BINDINGS}


def test_candidate_pass_never_grants_execution_or_authenticity():
    ticket, request = fixture()
    result = validate_candidate(ticket, request, now=150, consumed=frozenset())
    assert result["privileged_execution"] is False
    assert result["ticket_authenticity"] == "NOT_VERIFIED"
    assert result["atomic_consumption"] == "NOT_IMPLEMENTED"


@pytest.mark.parametrize(
    "field,value",
    [
        ("service", "crypto-advisor.service"),
        ("service", "crypto-operator-api.service"),
        ("operation", "run_shell"),
        ("operation", []),
        ("actor", "root"),
        ("audience", "another-gateway"),
        ("approved", False),
        ("approved", 1),
        ("operator", "agent"),
        ("source_sha", "main"),
        ("bundle_sha256", "bad"),
        ("expires_at", 150),
        ("issued_at", 151),
        ("issued_at", True),
        ("expires_at", 5000),
    ],
)
def test_out_of_scope_unapproved_and_expired_tickets_refused(field, value):
    ticket, request = fixture()
    ticket[field] = value
    with pytest.raises(ValueError):
        validate_candidate(ticket, request, now=150, consumed=frozenset())


def test_arbitrary_command_and_replay_refused():
    ticket, request = fixture()
    with pytest.raises(ValueError, match="TICKET_ALREADY_CONSUMED"):
        validate_candidate(
            ticket, request, now=150, consumed=frozenset({ticket["ticket_id"]})
        )
    request["command"] = "anything"
    with pytest.raises(ValueError, match="INVALID_REQUEST_KEYS"):
        validate_candidate(ticket, request, now=150, consumed=frozenset())


def test_bundle_substitution_refused():
    ticket, request = fixture()
    request["bundle_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="BINDING_MISMATCH"):
        validate_candidate(ticket, request, now=150, consumed=frozenset())


@pytest.mark.parametrize(
    "raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e400}', b"[]", b" " * 8193]
)
def test_ambiguous_or_unbounded_json_refused(raw):
    with pytest.raises(ValueError):
        decode_document(raw)
