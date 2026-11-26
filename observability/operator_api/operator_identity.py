"""Identité opérateur et journal d'audit de la seule écriture de l'API (P6-GOV-02).

L'identité vient de ``tailscale serve`` (en-tête ``Tailscale-User-Login``), vérifiée par le relais
Web, qui la transmet sous ``x-cat-operator-identity`` après avoir supprimé toute valeur fournie par
le client. L'API la vérifie à nouveau contre la même liste d'autorisation ``CAT_OPERATOR_LOGINS``
(non secrète). Liste absente ou vide : aucune écriture n'est possible (fermeture par défaut).

Transport interne (P6-GOV-02-RV) : l'API exige en plus le jeton du relais (en-tête
``x-cat-relay-token``), lu dans le fichier ``CAT_RELAY_TOKEN_FILE``, lisible seulement par les
services API et Web (groupe supplémentaire, aucun compte interactif). Un processus local d'un autre
utilisateur Unix ne peut donc pas forger l'identité directement auprès de l'API. Fichier absent,
vide ou illisible : aucune écriture (fermeture par défaut).

Limites : root, et le relais lui-même s'il est joint en boucle locale (voir le rapport RV) ; la
liste d'autorisation n'authentifie rien seule, elle filtre une identité établie par Tailscale.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import stat
import sys
import time
import uuid

IDENTITY_HEADER = "x-cat-operator-identity"
RELAY_TOKEN_HEADER = "x-cat-relay-token"
ALLOWLIST_ENV = "CAT_OPERATOR_LOGINS"
RELAY_TOKEN_FILE_ENV = "CAT_RELAY_TOKEN_FILE"
_TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")
_LOGIN_RE = re.compile(r"^[A-Za-z0-9._%+@-]{1,128}$")


def allowlist() -> frozenset[str]:
    raw = os.getenv(ALLOWLIST_ENV, "")
    return frozenset(x.strip().lower() for x in raw.split(",") if _LOGIN_RE.match(x.strip()))


def identity_from(headers) -> str | None:
    v = headers.get(IDENTITY_HEADER)
    if not isinstance(v, str) or not _LOGIN_RE.match(v):
        return None
    return v.lower()


def relay_token() -> str | None:
    """Jeton du relais : 64 hex, fichier régulier non lisible par « autres », jamais un lien."""
    path = os.getenv(RELAY_TOKEN_FILE_ENV, "")
    if not path:
        return None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o007:
            return None
        raw = os.read(fd, 129).decode("ascii", "replace").strip()
    finally:
        os.close(fd)
    return raw if _TOKEN_RE.match(raw) else None


def relay_ok(headers) -> tuple[int | None, str | None]:
    expected = relay_token()
    if expected is None:
        return 403, "RELAY_TOKEN_UNSET"
    got = headers.get(RELAY_TOKEN_HEADER)
    if not isinstance(got, str) or not hmac.compare_digest(got.encode("ascii", "replace"), expected.encode("ascii")):
        return 401, "RELAY_TOKEN_INVALID"
    return None, None


def check(headers) -> tuple[str | None, int | None, str | None]:
    """(identité, statut_refus, code_refus). Ordre : liste, transport (jeton du relais), identité."""
    allowed = allowlist()
    if not allowed:
        return None, 403, "OPERATOR_ALLOWLIST_UNSET"
    status, code = relay_ok(headers)
    if status is not None:
        return None, status, code
    who = identity_from(headers)
    if who is None:
        return None, 401, "OPERATOR_IDENTITY_REQUIRED"
    if who not in allowed:
        return who, 403, "OPERATOR_NOT_AUTHORIZED"
    return who, None, None


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def audit(*, request_id: str, identity: str | None, agent: str, value: str | None,
          decision: str, http_status: int, reason: str | None) -> None:
    """Une ligne JSON par POST sur stderr (journald). Jamais de corps brut ni d'en-têtes."""
    safe_value = value if isinstance(value, str) and re.fullmatch(r"[a-z0-9]{1,8}", value) else None
    line = {"event": "cat.schedule.audit", "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": request_id, "identity": identity, "agent": agent[:64], "value": safe_value,
            "decision": decision, "http_status": http_status, "reason": reason}
    print(json.dumps(line, separators=(",", ":")), file=sys.stderr, flush=True)
