import json
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from observability.frontend_deploy_request import BINDINGS
from observability.frontend_ticket_signature_lab import signing_bytes, verify_signed_fixture


def fixture():
    key = Ed25519PrivateKey.generate()  # ephemeral, never persisted
    ticket = dict(ticket_id='a'*32, actor='chatgpt-ro', operator='mathieu',
                  audience='frontend-deploy-gateway', operation='activate_frontend',
                  service='crypto-operator-web.service', source_sha='b'*40,
                  source_merge_sha='c'*40, previous_release_sha='d'*40,
                  bundle_sha256='e'*64, approved=True, issued_at=100, expires_at=200)
    envelope = {'ticket': ticket, 'signature': key.sign(signing_bytes(ticket)).hex()}
    pin = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return envelope, {k: ticket[k] for k in BINDINGS}, pin


def check(envelope, request, pin, **extra):
    return verify_signed_fixture(json.dumps(envelope).encode(), request,
        pinned_public_key=pin, peer_fixture=extra.get('peer', 'chatgpt-ro'),
        now=extra.get('now', 150), revoked=extra.get('revoked', frozenset()))


def test_signed_fixture_does_not_grant_operational_authority():
    env, req, pin = fixture()
    result = check(env, req, pin)
    assert result['signature_fixture'] == 'VERIFIED_AGAINST_SUPPLIED_PIN'
    assert result['operator_key_custody'] == 'NOT_PROVEN'
    assert result['peer_identity'] == 'NOT_PROVEN'
    assert result['privileged_execution'] is False


@pytest.mark.parametrize('attack', ['attacker_key', 'altered_approval', 'altered_bundle',
    'signature', 'request_key', 'revoked', 'peer', 'expired'])
def test_hostile_signed_fixture_refused(attack):
    env, req, pin = fixture()
    extra = {}
    if attack == 'attacker_key':
        attacker = Ed25519PrivateKey.generate()
        env['signature'] = attacker.sign(signing_bytes(env['ticket'])).hex()
    elif attack == 'altered_approval':
        env['ticket']['expires_at'] = 201
    elif attack == 'altered_bundle':
        env['ticket']['bundle_sha256'] = req['bundle_sha256'] = 'f'*64
    elif attack == 'signature':
        env['signature'] = '0'*128
    elif attack == 'request_key':
        env['public_key'] = pin.hex()
    elif attack == 'revoked':
        extra['revoked'] = frozenset({'a'*32})
    elif attack == 'peer':
        extra['peer'] = 'root'
    elif attack == 'expired':
        extra['now'] = 200
    with pytest.raises(ValueError):
        check(env, req, pin, **extra)
