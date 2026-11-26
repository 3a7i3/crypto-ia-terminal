"""Identité opérateur et journal d'audit de la seule écriture de l'API (P6-GOV-02).

L'identité vient de ``tailscale serve`` (en-tête ``Tailscale-User-Login``), vérifiée par le relais
Web, qui la transmet sous ``x-cat-operator-identity`` après avoir supprimé toute valeur fournie par
le client. L'API la vérifie à nouveau contre la même liste d'autorisation ``CAT_OPERATOR_LOGINS``
(non secrète). Liste absente ou vide : aucune écriture n'est possible (fermeture par défaut).

Limite assumée : un processus local exécutant sous le même utilisateur Unix que le relais peut
appeler l'API en boucle locale et forger l'en-tête ; la frontière vaut pour le réseau.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid

IDENTITY_HEADER = "x-cat-operator-identity"
ALLOWLIST_ENV = "CAT_OPERATOR_LOGINS"
_LOGIN_RE = re.compile(r"^[A-Za-z0-9._%+@-]{1,128}$")


def allowlist() -> frozenset[str]:
    raw = os.getenv(ALLOWLIST_ENV, "")
    return frozenset(x.strip().lower() for x in raw.split(",") if _LOGIN_RE.match(x.strip()))


def identity_from(headers) -> str | None:
    v = headers.get(IDENTITY_HEADER)
    if not isinstance(v, str) or not _LOGIN_RE.match(v):
        return None
    return v.lower()


def check(headers) -> tuple[str | None, int | None, str | None]:
    """(identité, statut_refus, code_refus)."""
    allowed = allowlist()
    if not allowed:
        return None, 403, "OPERATOR_ALLOWLIST_UNSET"
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
