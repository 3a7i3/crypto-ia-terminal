"""J02 local viewer: SOURCE_ONLY, SIMULATED_ONLY, NOT_DEPLOYED, GET-only.

Separate from Governance Tower and the Operator API. It serves verified
sentinel_activity feed pages from LAB roots fixed at start-up, on loopback
only. No import-time I/O, no write path, no producer, no VPS connection.
"""

RUNTIME_DEPLOYED = False
