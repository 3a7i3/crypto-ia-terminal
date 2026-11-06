"""Live WebSocket transport. NOT EXECUTED, NOT TESTED AGAINST THE PROVIDER.

Only buildable from an ``ApprovedLive`` produced by ``live_gate``. The client
library is imported inside ``open`` (never at import), so importing this module
performs no network or library work. Choices that bound the stream:
``max_size`` = the per-message cap, ``max_queue`` small, no compression (so the
cap applies to bytes on the wire), no proxy auto-detection, no keepalive pings
that could mask silence, and NO reconnect logic of any kind.
"""

from . import protocol as P
from .live_gate import ApprovedLive, LiveLocked
from .transport import (AccessRefused, ConnectFailed, ConnectionClosed, Frame, FrameTooLarge,
                        Transport)

ACCESS_STATUSES = {401, 403, 429, 451}


class LiveTransport(Transport):
    evidence_kind = "LIVE"

    def __init__(self, approval, *, max_queue=16):
        if type(approval) is not ApprovedLive:
            raise LiveLocked("APPROVAL_REQUIRED")
        self.caps, self.max_queue = approval.caps, max_queue
        self.ws = None

    def open(self, subscribe_messages):
        try:
            from websockets.sync.client import connect  # deferred: no import-time client
        except ImportError as e:
            raise ConnectFailed("WEBSOCKETS_LIBRARY_MISSING") from e
        try:
            self.ws = connect(
                P.URL, open_timeout=5, close_timeout=2, ping_interval=None, compression=None,
                proxy=None, max_size=self.caps.max_message_bytes, max_queue=self.max_queue,
            )
            for m in subscribe_messages:  # one subscribe message per channel, within 5 s of connecting
                self.ws.send(m)
        except Exception as e:
            self._map(e, opening=True)

    def _map(self, e, opening=False):
        name = type(e).__name__
        status = getattr(getattr(e, "response", None), "status_code", None)
        if name == "InvalidStatus" and status in ACCESS_STATUSES:
            raise AccessRefused("HTTP_%s" % status) from e
        if name == "ConnectionClosed" or name.startswith("ConnectionClosed"):
            code = getattr(getattr(e, "rcvd", None), "code", None)
            if code == 1009:
                raise FrameTooLarge(None) from e
            if code in (1008,):
                raise AccessRefused("CLOSE_%s" % code) from e
            raise ConnectionClosed("CLOSE_%s" % code) from e
        if opening:
            raise ConnectFailed(name) from e
        raise ConnectionClosed(name) from e

    def recv(self, timeout_ns):
        try:
            data = self.ws.recv(timeout=timeout_ns / 1e9)
        except TimeoutError:
            return None
        except Exception as e:
            self._map(e)
        raw = data if isinstance(data, bytes) else data.encode("utf-8")
        return Frame(raw)

    def close(self):
        if self.ws is not None:
            try:
                self.ws.close()
            finally:
                self.ws = None
