"""Live entry lock. Everything here runs BEFORE any DNS lookup, socket or import of a network client.

A live run needs ALL of: an approved manifest file bound to THIS package's digest,
within the protocol caps, naming the fixed target; and an environment acknowledgement
equal to the manifest's SHA-256. This is a necessary gate, not authentication: the
operator GO under #286, regional admissibility and terms of use are HUMAN decisions
that this code can only require to be referenced, never establish.
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from . import protocol as P

ENV_ACK = "FLUX_PILOT_LIVE_GO"
FORBIDDEN_KEYS = {"jwt", "api_key", "api_secret", "secret", "private_key", "password", "token"}
_MARKERS = ("TODO", "<", "À COMPLÉTER", "A COMPLETER", "FILL", "CHANGEME")
_TOKEN = object()


class LiveLocked(RuntimeError):
    """Stable reason code in the message text. Raised before any network activity."""


@dataclass(frozen=True)
class ApprovedLive:
    manifest: dict
    manifest_sha256: str
    caps: P.Caps
    sequence_policy: str
    package_digest: str
    _token: object = None

    def __post_init__(self):
        if self._token is not _TOKEN:
            raise LiveLocked("APPROVAL_ONLY_THROUGH_GATE")


def _walk(x, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            if str(k).lower() in FORBIDDEN_KEYS:
                raise LiveLocked("SECRET_FIELD_IN_MANIFEST:" + path + "/" + str(k))
            yield from _walk(v, path + "/" + str(k))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _walk(v, "%s[%d]" % (path, i))
    else:
        yield path, x


def _need(d, *path):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            raise LiveLocked("MANIFEST_FIELD_MISSING:" + ".".join(path))
        cur = cur[k]
    if isinstance(cur, str) and (not cur.strip() or any(m in cur.upper() for m in (x.upper() for x in _MARKERS))):
        raise LiveLocked("MANIFEST_FIELD_NOT_COMPLETED:" + ".".join(path))
    if cur is None or cur == "":
        raise LiveLocked("MANIFEST_FIELD_MISSING:" + ".".join(path))
    return cur


def require_live_authorization(manifest_path, env, package_root=None):
    if not manifest_path:
        raise LiveLocked("MANIFEST_MISSING")
    p = Path(manifest_path)
    if not p.is_file():
        raise LiveLocked("MANIFEST_MISSING")
    raw = p.read_bytes()
    try:
        m = json.loads(raw)
    except ValueError:
        raise LiveLocked("MANIFEST_UNPARSABLE") from None
    if not isinstance(m, dict):
        raise LiveLocked("MANIFEST_UNPARSABLE")
    list(_walk(m))  # refuses secret-looking fields anywhere
    sha = hashlib.sha256(raw).hexdigest()
    if _need(m, "status") != "APPROVED":
        raise LiveLocked("MANIFEST_NOT_APPROVED")
    if (env or {}).get(ENV_ACK) != sha:
        raise LiveLocked("OPERATOR_ACK_MISSING_OR_NOT_BOUND_TO_MANIFEST")
    digest = P.package_digest(package_root)
    if _need(m, "package_digest") != digest:
        raise LiveLocked("PACKAGE_DIGEST_MISMATCH")
    t = _need(m, "target")
    if (t.get("provider"), t.get("host"), t.get("product")) != (P.PROVIDER, P.HOST, P.PRODUCT) \
            or sorted(t.get("channels") or []) != sorted(P.SUBSCRIBE_CHANNELS):
        raise LiveLocked("TARGET_NOT_THE_FIXED_PILOT_TARGET")
    for path in (("authorization", "issue_286_exception_ref"), ("authorization", "approved_by"),
                 ("authorization", "approved_at_utc"), ("admissibility", "region_evidence_ref"),
                 ("admissibility", "terms_evidence_ref"), ("observer_clock", "before_check_ref"),
                 ("observer_clock", "after_check_ref"), ("storage", "root"), ("stop_policy",)):
        _need(m, *path)
    if not Path(m["storage"]["root"]).is_absolute():
        raise LiveLocked("STORAGE_ROOT_NOT_ABSOLUTE")
    try:
        caps = P.Caps(**_need(m, "caps"))
    except (TypeError, ValueError):
        raise LiveLocked("CAPS_INVALID") from None
    if not caps.within(P.PROTOCOL_CAPS):
        raise LiveLocked("CAPS_ABOVE_PROTOCOL")
    policy = _need(m, "sequence_policy")
    if policy not in P.SEQUENCE_POLICIES:
        raise LiveLocked("SEQUENCE_POLICY_UNKNOWN")
    return ApprovedLive(m, sha, caps, policy, digest, _TOKEN)
