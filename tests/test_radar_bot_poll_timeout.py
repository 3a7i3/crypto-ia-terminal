import pytest

from scripts import radar_bot


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return b'{"ok": true, "result": []}'


def test_tg_request_forwards_explicit_http_timeout(monkeypatch):
    seen = {}

    def fake_urlopen(_request, timeout):
        seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(radar_bot.urllib.request, "urlopen", fake_urlopen)

    result = radar_bot.tg_request(
        "getUpdates",
        {"timeout": radar_bot.TELEGRAM_LONG_POLL_TIMEOUT_S},
        http_timeout_s=radar_bot.TELEGRAM_LONG_POLL_HTTP_TIMEOUT_S,
    )

    assert result["ok"] is True
    assert seen["timeout"] == radar_bot.TELEGRAM_LONG_POLL_HTTP_TIMEOUT_S


def test_long_poll_http_timeout_exceeds_server_timeout():
    assert (
        radar_bot.TELEGRAM_LONG_POLL_HTTP_TIMEOUT_S
        > radar_bot.TELEGRAM_LONG_POLL_TIMEOUT_S
    )


def test_poll_loop_uses_long_poll_http_timeout(monkeypatch):
    calls = []

    def fake_tg_request(method, payload=None, *, http_timeout_s):
        calls.append((method, payload, http_timeout_s))
        raise KeyboardInterrupt

    monkeypatch.setattr(radar_bot, "tg_request", fake_tg_request)

    with pytest.raises(KeyboardInterrupt):
        radar_bot.poll_loop()

    assert calls == [
        (
            "getUpdates",
            {"timeout": radar_bot.TELEGRAM_LONG_POLL_TIMEOUT_S, "offset": 0},
            radar_bot.TELEGRAM_LONG_POLL_HTTP_TIMEOUT_S,
        )
    ]
