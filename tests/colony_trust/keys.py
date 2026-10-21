"""LAB_TEST keys for the colony trust tests: derived from public labels, they authenticate nothing.

No real key is in the repository; colony_trust refuses any trust root that is not LAB_TEST.
"""

import copy
import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from colony_trust import trust

LAB = "fixture-colony-lab"
REVIEWER = "fixture-independent-reviewer"
OPERATOR = "fixture-lab-operator"
ADMITTER = "fixture-external-admitter"


def lab_key(label: str) -> Ed25519PrivateKey:
    seed = hashlib.sha256(b"colony-trust LAB_TEST key\x00" + label.encode()).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def key_entry(label, status="ACTIVE", introduced=1, retired=None):
    public = trust.public_key_hex(lab_key(label))
    return {"key_id": trust.key_id(public), "public_key": public, "status": status,
            "introduced_in_root": introduced, "retired_in_root": retired}


def root(version=1, issuers=None, revoked=(), environment="LAB_TEST", lab_id=LAB):
    issuers = issuers if issuers is not None else [
        {"issuer_id": ADMITTER, "issuer_kind": "EXTERNAL_HUMAN", "scopes": ["colony-registrar.admission/0"],
         "keys": [key_entry("admitter-1")]},
        {"issuer_id": REVIEWER, "issuer_kind": "EXTERNAL_REVIEW_PROCESS", "scopes": ["colony-lab.qualification/0"],
         "keys": [key_entry("reviewer-1")]},
        {"issuer_id": OPERATOR, "issuer_kind": "LAB_OPERATOR", "scopes": ["colony-lab.individual/0"],
         "keys": [key_entry("operator-1")]},
    ]
    return {"root_schema": trust.ROOT_SCHEMA, "environment": environment, "lab_id": lab_id,
            "root_version": version, "issuers": copy.deepcopy(issuers), "revoked_envelopes": sorted(revoked)}


def pin(value):
    return trust.sha256_of(value)


def eid(label: str) -> str:
    return hashlib.sha256(b"envelope\x00" + label.encode()).hexdigest()
