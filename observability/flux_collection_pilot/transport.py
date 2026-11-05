"""Injectable transport interface. Nothing here touches the network at import or by default.

The runner only ever sees ``Transport``. ``recv`` returns one complete application
message already bounded by ``max_bytes`` (the transport must refuse before
accumulating more). There is NO implicit reconnection: after ``ConnectionClosed``
the runner stops; a planned reconnect is a new ``Transport`` built by the factory.
"""

from dataclasses import dataclass


class TransportError(Exception):
    """Base of every transport failure."""


class AccessRefused(TransportError):
    """Handshake or close refusing access (401/403/429/451, policy close)."""


class ConnectFailed(TransportError):
    """Could not open (local or network failure before the first message)."""


class ConnectionClosed(TransportError):
    """Peer or network closed an open connection."""


class FrameTooLarge(TransportError):
    def __init__(self, size=None):
        super().__init__("FRAME_TOO_LARGE")
        self.size = size


class LocalLoss(TransportError):
    """Local queue overflow / dropped frame: the stream is no longer complete."""


@dataclass(frozen=True)
class Frame:
    raw: bytes


class Transport:
    evidence_kind = "UNSET"  # "SYNTHETIC" or "LIVE"

    def open(self, subscribe_messages):
        raise NotImplementedError

    def recv(self, timeout_ns):
        """Next Frame, or None when ``timeout_ns`` elapses without one."""
        raise NotImplementedError

    def close(self):
        raise NotImplementedError


def subscribe_messages(product, channels):
    """The exact public subscribe payloads (no jwt: unauthenticated channels only)."""
    import json

    return [json.dumps({"type": "subscribe", "product_ids": [product], "channel": c},
                       sort_keys=True, separators=(",", ":")) for c in channels]
