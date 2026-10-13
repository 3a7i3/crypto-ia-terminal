"""Offline signature fixture verification, never operational admission."""
from __future__ import annotations

import json
import re
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from observability.frontend_deploy_request import decode_document, validate_candidate

DOMAIN = b'FRONTEND-GATEWAY-LAB-02\x00'


def signing_bytes(ticket: dict) -> bytes:
    return DOMAIN + json.dumps(ticket, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def verify_signed_fixture(raw: bytes, request: dict, *, pinned_public_key: bytes,
                          peer_fixture: str, now: int, revoked: frozenset[str]) -> dict:
    envelope = decode_document(raw)
    if set(envelope) != {'ticket', 'signature'}:
        raise ValueError('INVALID_ENVELOPE_KEYS')
    ticket, signature = envelope['ticket'], envelope['signature']
    if type(signature) is not str or not re.fullmatch(r'[0-9a-f]{128}', signature):
        raise ValueError('INVALID_SIGNATURE_ENCODING')
    if type(pinned_public_key) is not bytes or len(pinned_public_key) != 32:
        raise ValueError('PINNED_PUBLIC_KEY_REQUIRED')
    candidate = validate_candidate(ticket, request, now=now, consumed=frozenset())
    if peer_fixture != ticket['actor']:
        raise ValueError('PEER_FIXTURE_MISMATCH')
    if ticket['ticket_id'] in revoked:
        raise ValueError('REVOKED_TICKET')
    try:
        Ed25519PublicKey.from_public_bytes(pinned_public_key).verify(
            bytes.fromhex(signature), signing_bytes(ticket)
        )
    except InvalidSignature as exc:
        raise ValueError('SIGNATURE_MISMATCH') from exc
    return {**candidate, 'state': 'SIGNED_FIXTURE_VERIFIED_NO_ADMISSION',
            'signature_fixture': 'VERIFIED_AGAINST_SUPPLIED_PIN',
            'operator_key_custody': 'NOT_PROVEN', 'peer_identity': 'NOT_PROVEN',
            'ticket_authenticity': 'NOT_VERIFIED', 'privileged_execution': False}
