"""observability/operator_api/dev_server.py — local development entry
point for the read-only operator API.

D1 is local-source implementation only (mission §7) — this is NOT a
production deployment launcher, and there is no systemd unit or VPS
wiring anywhere in this change. Default bind address is loopback-only
(`127.0.0.1`); it is never exposed on `0.0.0.0` by default.

Usage: `python -m observability.operator_api.dev_server`
"""

from __future__ import annotations

import os

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = int(os.getenv("OPERATOR_API_DEV_PORT", "8090"))


def main() -> None:
    import uvicorn

    host = os.getenv("OPERATOR_API_DEV_HOST", DEFAULT_HOST)
    if host != "127.0.0.1" and host != "localhost":
        raise SystemExit(
            "Refusing to bind the operator API dev server to a non-loopback "
            f"host ({host!r}) — mission §7 requires loopback-only by default. "
            "Authentication and controlled external exposure are deferred to "
            "a later security/deployment mission."
        )
    uvicorn.run(
        "observability.operator_api.app:app",
        host=host,
        port=DEFAULT_PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
