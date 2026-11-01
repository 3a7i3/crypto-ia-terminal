"""Prepared fixed-host GET transport. No import-time client and no real CLI entrypoint."""

import http.client
import re
import ssl
import signal
import threading
from contextlib import contextmanager
from .capture import Response
from .plan import RequestSpec

SAFE_HEADERS = {
    "content-type",
    "date",
    "retry-after",
    "x-bapi-limit",
    "x-bapi-limit-status",
    "x-bapi-limit-reset-timestamp",
}


@contextmanager
def request_deadline(seconds):
    if threading.current_thread() is not threading.main_thread() or not hasattr(
        signal, "setitimer"
    ):
        raise RuntimeError("UNSUPPORTED_REQUEST_DEADLINE_PLATFORM")
    previous = signal.getitimer(signal.ITIMER_REAL)
    if previous[0] or previous[1]:
        raise RuntimeError("EXISTING_PROCESS_TIMER_REFUSED")
    handler = signal.getsignal(signal.SIGALRM)

    def expired(*_):
        raise TimeoutError("PUBLIC_READ_DEADLINE")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, handler)


class PublicHTTPS:
    evidence_kind = "OBSERVATION"

    def __init__(self, *, network_enabled=False, decision_reference=None):
        self.enabled = network_enabled is True
        self.decision_reference = decision_reference
        if self.enabled and (
            not isinstance(decision_reference, str)
            or not re.fullmatch(
                r"https://github\.com/3a7i3/crypto-ia-terminal/issues/[1-9][0-9]*(?:#issuecomment-[0-9]+)?",
                decision_reference,
            )
        ):
            raise ValueError("EXPLICIT_OPERATOR_DECISION_REFERENCE_REQUIRED")
        # A reference is caller evidence, never a signed or self-issued permission.

    def fetch(self, spec, *, timeout_ms, max_bytes):
        if not self.enabled:
            raise RuntimeError("NETWORK_DISABLED")
        if type(spec) is not RequestSpec:
            raise ValueError("REQUEST_NOT_ALLOWLISTED")
        spec.validate()
        if (
            type(timeout_ms) is not int
            or not 1 <= timeout_ms <= 3000
            or type(max_bytes) is not int
            or not 256 <= max_bytes <= 65536
        ):
            raise ValueError("INVALID_TRANSPORT_LIMIT")
        connection = None
        try:
            with request_deadline(timeout_ms / 1000):
                connection = http.client.HTTPSConnection(
                    spec.host,
                    443,
                    timeout=timeout_ms / 1000,
                    context=ssl.create_default_context(),
                )
                connection.request(
                    "GET",
                    spec.target,
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                        "User-Agent": "Crypto-AI-Terminal-Passive-Pilot/539",
                    },
                )
                reply = connection.getresponse()
                headers = {
                    k.lower(): v[:256]
                    for k, v in reply.getheaders()
                    if k.lower() in SAFE_HEADERS
                }
                if (
                    reply.getheader("Content-Encoding", "identity").lower()
                    != "identity"
                ):
                    return Response(
                        reply.status, None, headers, "CONTENT_ENCODING_REFUSED", False
                    )
                body = reply.read(max_bytes + 1)
                complete = len(body) <= max_bytes
                return Response(
                    reply.status,
                    body[:max_bytes],
                    headers,
                    None if complete else "RESPONSE_TOO_LARGE",
                    complete,
                )
        except TimeoutError:
            return Response(None, None, {}, "REQUEST_TIMEOUT", False)
        except (OSError, ssl.SSLError, http.client.HTTPException):
            return Response(None, None, {}, "TRANSPORT_UNAVAILABLE", False)
        finally:
            if connection is not None:
                connection.close()
