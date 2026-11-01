import http.client
import signal
import ssl
import time
import pytest
from observability.market_venues.pilot.plan import RequestSpec
from observability.market_venues.pilot.transport import PublicHTTPS, request_deadline

REF = "https://github.com/3a7i3/crypto-ia-terminal/issues/539"


def test_network_disabled_by_default_without_constructing_a_socket(monkeypatch):
    calls = []
    monkeypatch.setattr(http.client, "HTTPSConnection", lambda *a, **k: calls.append(a))
    with pytest.raises(RuntimeError, match="NETWORK_DISABLED"):
        PublicHTTPS().fetch(
            RequestSpec("bybit", "time"), timeout_ms=1000, max_bytes=4096
        )
    assert not calls


@pytest.mark.parametrize(
    "reference", [None, "", "https://evil.invalid/allow", "KEY-SECRET"]
)
def test_network_constructor_demands_explicit_external_decision_reference(reference):
    with pytest.raises(ValueError):
        PublicHTTPS(network_enabled=True, decision_reference=reference)


def fake_connection(
    monkeypatch, *, status=200, raw=b"{}", encoding="identity", failure=None
):
    log = []

    class Reply:
        def __init__(self):
            self.status = status

        def getheaders(self):
            return [
                ("Content-Type", "application/json"),
                ("Set-Cookie", "excluded"),
                ("Authorization", "excluded"),
                ("Retry-After", "2"),
            ]

        def getheader(self, key, default=None):
            return encoding if key == "Content-Encoding" else default

        def read(self, n):
            log.append(("read", n))
            if failure:
                raise failure
            return raw

    class Connection:
        def __init__(self, host, port, **kw):
            assert (
                kw["context"].verify_mode == ssl.CERT_REQUIRED
                and kw["context"].check_hostname
            )
            log.append(("host", host, port))

        def request(self, *args, **kwargs):
            log.append(("request", args, kwargs))

        def getresponse(self):
            return Reply()

        def close(self):
            log.append(("closed",))

    monkeypatch.setattr(http.client, "HTTPSConnection", Connection)
    return log


def test_fixed_public_get_has_verified_tls_no_credentials_cookies_or_proxy_fallback(
    monkeypatch,
):
    log = fake_connection(monkeypatch)
    response = PublicHTTPS(network_enabled=True, decision_reference=REF).fetch(
        RequestSpec("bybit", "book", "BTCUSDT"), timeout_ms=1000, max_bytes=4096
    )
    assert response.status == 200 and response.body == b"{}"
    assert response.headers == {"content-type": "application/json", "retry-after": "2"}
    request = next(x for x in log if x[0] == "request")
    assert request[1] == (
        "GET",
        "/v5/market/orderbook?category=spot&symbol=BTCUSDT&limit=1",
    )
    assert not any(
        "key" in k.lower() or "auth" in k.lower() or "cookie" in k.lower()
        for k in request[2]["headers"]
    )
    assert log[-1] == ("closed",)


def test_redirect_is_not_followed(monkeypatch):
    log = fake_connection(monkeypatch, status=302)
    response = PublicHTTPS(network_enabled=True, decision_reference=REF).fetch(
        RequestSpec("okx", "time"), timeout_ms=1000, max_bytes=4096
    )
    assert response.status == 302 and len([x for x in log if x[0] == "host"]) == 1


def test_bounded_incomplete_body_is_never_claimed_complete(monkeypatch):
    log = fake_connection(monkeypatch, raw=b"x" * 4097)
    response = PublicHTTPS(network_enabled=True, decision_reference=REF).fetch(
        RequestSpec("okx", "time"), timeout_ms=1000, max_bytes=4096
    )
    assert (
        response.body == b"x" * 4096
        and response.complete is False
        and response.error == "RESPONSE_TOO_LARGE"
    )
    assert ("read", 4097) in log


def test_encoded_response_and_timeouts_are_explicit(monkeypatch):
    fake_connection(monkeypatch, encoding="gzip")
    response = PublicHTTPS(network_enabled=True, decision_reference=REF).fetch(
        RequestSpec("okx", "time"), timeout_ms=1000, max_bytes=4096
    )
    assert response.error == "CONTENT_ENCODING_REFUSED" and response.body is None
    fake_connection(monkeypatch, failure=TimeoutError())
    assert (
        PublicHTTPS(network_enabled=True, decision_reference=REF)
        .fetch(RequestSpec("okx", "time"), timeout_ms=1000, max_bytes=4096)
        .error
        == "REQUEST_TIMEOUT"
    )


def test_deadline_interrupts_a_wait_and_restores_signal_handler():
    previous = signal.getsignal(signal.SIGALRM)
    with pytest.raises(TimeoutError):
        with request_deadline(0.002):
            time.sleep(0.03)
    assert signal.getsignal(signal.SIGALRM) == previous and signal.getitimer(
        signal.ITIMER_REAL
    ) == (0.0, 0.0)


def test_an_existing_alarm_is_not_repurposed(monkeypatch):
    monkeypatch.setattr(signal, "getitimer", lambda _: (1.0, 0.0))
    with pytest.raises(RuntimeError, match="EXISTING_PROCESS_TIMER"):
        with request_deadline(1):
            pass
