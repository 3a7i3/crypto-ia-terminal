#!/usr/bin/env python3
"""Create and validate requests for the read-only VPS audit bridge.

Security model:
- callers request an ACTION, never an arbitrary shell command;
- the action is validated against a closed allowlist here;
- the VPS forced-command dispatcher validates the same allowlist again.

Examples:
  python scripts/vps_audit_request.py new lmi_status
  python scripts/vps_audit_request.py new lmi_journal --request-id REQ-20260831-001
  python scripts/vps_audit_request.py validate audit_requests/request.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
ALLOWED_ACTIONS = frozenset(
    {
        "identity",
        "lmi_status",
        "lmi_health",
        "lmi_journal",
        "repo_status",
        "repo_log",
        "snapshot_manifest",
    }
)
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
ALLOWED_KEYS = frozenset({"schema_version", "request_id", "action", "requested_at_utc"})


class RequestError(ValueError):
    """Raised when an audit request violates the protocol."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_request_id() -> str:
    return datetime.now(timezone.utc).strftime("REQ-%Y%m%dT%H%M%SZ")


def validate_request(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RequestError("request must be a JSON object")

    unknown = set(payload) - ALLOWED_KEYS
    if unknown:
        raise RequestError(f"unknown field(s): {', '.join(sorted(unknown))}")

    missing = ALLOWED_KEYS - set(payload)
    if missing:
        raise RequestError(f"missing field(s): {', '.join(sorted(missing))}")

    if payload["schema_version"] != SCHEMA_VERSION:
        raise RequestError(f"schema_version must be {SCHEMA_VERSION}")

    request_id = payload["request_id"]
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise RequestError("invalid request_id")

    action = payload["action"]
    if action not in ALLOWED_ACTIONS:
        raise RequestError(
            "action not allowed; expected one of: " + ", ".join(sorted(ALLOWED_ACTIONS))
        )

    requested_at = payload["requested_at_utc"]
    if not isinstance(requested_at, str) or len(requested_at) > 40:
        raise RequestError("invalid requested_at_utc")

    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "action": action,
        "requested_at_utc": requested_at,
    }


def load_request(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RequestError(f"cannot read {path}: {exc}") from exc
    if len(raw) > 4096:
        raise RequestError("request file is too large")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RequestError(f"invalid JSON: {exc}") from exc
    return validate_request(payload)


def cmd_new(args: argparse.Namespace) -> int:
    payload = validate_request(
        {
            "schema_version": SCHEMA_VERSION,
            "request_id": args.request_id or _default_request_id(),
            "action": args.action,
            "requested_at_utc": _utc_now(),
        }
    )
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(output)
    else:
        sys.stdout.write(rendered)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    payload = load_request(Path(args.path))
    if args.github_output:
        output_path = Path(args.github_output)
        with output_path.open("a", encoding="utf-8") as handle:
            handle.write(f"request_id={payload['request_id']}\n")
            handle.write(f"action={payload['action']}\n")
    else:
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="create a strict audit request")
    new.add_argument("action", choices=sorted(ALLOWED_ACTIONS))
    new.add_argument("--request-id")
    new.add_argument("--output", default="audit_requests/request.json")
    new.set_defaults(func=cmd_new)

    validate = sub.add_parser("validate", help="validate an existing request")
    validate.add_argument("path")
    validate.add_argument("--github-output", help="append validated fields to GITHUB_OUTPUT")
    validate.set_defaults(func=cmd_validate)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except RequestError as exc:
        print(f"AUDIT_REQUEST_REJECTED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
