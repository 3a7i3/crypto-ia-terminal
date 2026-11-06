"""Network guard for every test of the pilot package.

Mechanism: in-process patches of ``socket.socket.connect/connect_ex/sendto``,
``socket.create_connection`` and every DNS resolver entry (``getaddrinfo``,
``gethostbyname``, ``gethostbyname_ex``, ``gethostbyaddr``). Each call is COUNTED
and raises ``NetworkAttempt`` (a BaseException, so ``except Exception`` in the code
under test cannot swallow it). A teardown assertion requires the counter to be zero
unless the test declared ``expect_network_attempts``.

What it covers: Python-level connection/DNS attempts in the test process.
What it does not cover: a subprocess (the few subprocess tests run only local Python
and never import a network client), non-socket channels, or C extensions that open
sockets themselves.
"""

import socket

import pytest


class NetworkAttempt(BaseException):
    pass


@pytest.fixture(autouse=True)
def network_guard(monkeypatch, request):
    calls = []

    def blocked(name):
        def _f(*a, **k):
            calls.append(name)
            raise NetworkAttempt("NETWORK_FORBIDDEN:" + name)
        return _f

    for owner, names in ((socket.socket, ("connect", "connect_ex", "sendto")),
                         (socket, ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"))):
        for n in names:
            monkeypatch.setattr(owner, n, blocked(n))
    yield calls
    if not request.node.get_closest_marker("expect_network_attempts"):
        assert calls == [], "network attempted: %r" % calls


def pytest_configure(config):
    config.addinivalue_line("markers", "expect_network_attempts: the test itself probes the network guard")
