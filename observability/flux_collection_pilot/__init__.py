"""Coinbase Advanced BTC-USD spot bounded pilot, OFFLINE PREPARATION (#553).

SOURCE ONLY / NOT WIRED / NOT AUTHORISED. Importing this package opens no socket,
resolves no name and reads no clock. The default entry points work on a simulated
transport; the live entry is locked (see ``live_gate``) before any DNS lookup or
socket. A fixture is never runtime proof; a capture is never Flux admission
(the Flux contract keeps ``synthetic=true``). #286 ACTIVE.
"""

PILOT_VERSION = "coinbase-btc-usd-pilot-offline-0.1.0"
