"""Bounded-collection protocol: fixed target, caps, stop reasons, package digest.

The caps below are the PROTOCOL maxima. A manifest may only lower them
(``Caps.within``); nothing here can raise a cap.
"""

from dataclasses import dataclass, fields
from pathlib import Path
import hashlib

S = 1_000_000_000
MIB = 1024 * 1024

PROVIDER = "coinbase_advanced"
HOST = "advanced-trade-ws.coinbase.com"
URL = "wss://" + HOST
PRODUCT = "BTC-USD"
# Subscribe-message channel names (public, unauthenticated, no jwt) -> message channel names.
SUBSCRIBE_CHANNELS = ("level2", "market_trades", "heartbeats")
MESSAGE_CHANNELS = {"level2": "l2_data", "market_trades": "market_trades", "heartbeats": "heartbeats"}
L2_CHANNEL = "l2_data"
TRADES_CHANNEL = "market_trades"
HEARTBEAT_CHANNEL = "heartbeats"

SEQUENCE_POLICIES = ("PER_CHANNEL", "PER_PRODUCT", "PER_CONNECTION")
DEFAULT_SEQUENCE_POLICY = "PER_CHANNEL"  # conservative: no other counter fills an l2_data gap

# End reasons. Only DURATION_CAP after the full planned protocol is a COMPLETE run.
PLANNED_CUT = "PLANNED_CUT_60S"
DURATION_CAP = "DURATION_CAP"
MESSAGE_CAP = "MESSAGE_CAP"
DISK_CAP = "DISK_CAP"
MEMORY_CAP = "MEMORY_CAP"
MEMORY_UNVERIFIABLE = "MEMORY_UNVERIFIABLE"
CONNECTION_CAP = "CONNECTION_CAP"
SILENCE_HEARTBEAT = "SILENCE_HEARTBEAT"
ACCESS_REFUSED = "ACCESS_REFUSED"
PROVIDER_ERROR = "PROVIDER_ERROR_MESSAGE"
LOCAL_LOSS = "LOCAL_LOSS"
L2_SEQUENCE_SUSPECT = "L2_SEQUENCE_SUSPECT"
MALFORMED_MESSAGE = "MALFORMED_MESSAGE"
MESSAGE_TOO_LARGE = "MESSAGE_TOO_LARGE"
UNEXPECTED_PRODUCT = "UNEXPECTED_PRODUCT"
CONNECTION_LOST = "CONNECTION_LOST"
CONNECT_FAILED = "CONNECT_FAILED"
WRITE_FAILED = "WRITE_FAILED"
CLOCK_ANOMALY = "CLOCK_ANOMALY"
SESSION_UNHEALTHY_AT_CUT = "SESSION_UNHEALTHY_AT_CUT"
INTERNAL_ERROR = "INTERNAL_ERROR"

COMPLETE_REASONS = frozenset({DURATION_CAP})


@dataclass(frozen=True)
class Caps:
    max_connections: int = 2
    planned_cut_ns: int = 60 * S
    max_duration_ns: int = 180 * S
    max_messages: int = 100_000
    max_disk_bytes: int = 64 * MIB
    max_memory_bytes: int = 256 * MIB
    silence_ns: int = 5 * S
    max_message_bytes: int = 512_000  # same bound as the Flux L2 prototype's message limit
    reserve_bytes: int = 4 * MIB  # kept for trigger + final receipt inside the disk cap

    def __post_init__(self):
        for f in fields(self):
            v = getattr(self, f.name)
            if type(v) is not int or v <= 0:
                raise ValueError("CAP_POSITIVE_INTEGER_REQUIRED:" + f.name)
        if self.reserve_bytes >= self.max_disk_bytes:
            raise ValueError("RESERVE_NOT_BELOW_DISK_CAP")
        if self.planned_cut_ns >= self.max_duration_ns:
            raise ValueError("CUT_NOT_BELOW_DURATION")

    def within(self, ceiling):
        """True when every cap is <= the protocol ceiling (a manifest can only lower)."""
        return all(getattr(self, f.name) <= getattr(ceiling, f.name) for f in fields(self))

    def document(self):
        return {f.name: getattr(self, f.name) for f in fields(self)}


PROTOCOL_CAPS = Caps()


def canonical(value):
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def package_digest(root=None):
    """SHA-256 over the sorted (relative path, bytes) of this package's .py files.

    This is the identity a collection authorisation must pin. It covers the
    package itself, not the interpreter or third-party libraries.
    """
    base = Path(root) if root else Path(__file__).resolve().parent
    h = hashlib.sha256()
    for p in sorted(base.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(base).as_posix().encode()
        data = p.read_bytes()
        h.update(len(rel).to_bytes(4, "big") + rel + len(data).to_bytes(8, "big") + data)
    return h.hexdigest()
