import socket
import pytest


@pytest.fixture(autouse=True)
def forbid_real_exchange_network(monkeypatch):
    def refused(*a, **kw):
        raise AssertionError("REAL_NETWORK_FORBIDDEN_IN_PREPARATION")

    monkeypatch.setattr(socket, "create_connection", refused)
    monkeypatch.setattr(socket, "getaddrinfo", refused)
