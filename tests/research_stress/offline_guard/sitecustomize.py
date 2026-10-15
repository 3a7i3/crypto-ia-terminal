"""Garde réseau de tests opt-in via PYTHONPATH ; jamais importé par le runtime.

Refuse résolution/connexion non loopback dans les tests et leurs subprocess
Python. Ne remplace pas un sandbox OS contre du code hostile/native non audité.
"""
from __future__ import annotations

import sys


_LOCAL = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _offline_network(event, args):
    if event in {"socket.connect", "socket.sendto"}:
        address = args[1]
        if isinstance(address, tuple) and str(address[0]) not in _LOCAL:
            raise OSError("PAPER_STRESS_OFFLINE_NETWORK_DENIED")
    if event == "socket.getaddrinfo" and args[0] is not None:
        host = args[0].decode() if isinstance(args[0], bytes) else str(args[0])
        if host not in _LOCAL:
            raise OSError("PAPER_STRESS_OFFLINE_DNS_DENIED")


sys.addaudithook(_offline_network)
