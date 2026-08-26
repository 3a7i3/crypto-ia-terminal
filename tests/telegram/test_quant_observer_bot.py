"""@QuantCrypto_bot — authorization, dispatch, and observer passivity.

The bot is the one component that takes untrusted input (arbitrary Telegram
messages) and turns it into reads of the scientific datasets. These tests pin
the two properties that make that safe: only allowlisted chats are served, and
no command can reach a write path (ADR-0007).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src.telegram.quant_observer import bot


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("QC_ALLOWED_CHAT_IDS", raising=False)
    monkeypatch.delenv("QC_CHAT_ID", raising=False)


@pytest.fixture
def sent(monkeypatch):
    """Capture everything the bot would publish to Telegram."""
    messages: list[tuple[str, str]] = []
    photos: list[tuple[str, bytes, str]] = []

    monkeypatch.setattr(
        bot,
        "send_message",
        lambda chat_id, text, **kw: messages.append((chat_id, text)),
    )
    monkeypatch.setattr(
        bot,
        "send_photo",
        lambda chat_id, png, caption="": photos.append((chat_id, png, caption)),
    )
    return {"messages": messages, "photos": photos}


# ── Telegram API contract ─────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_long_poll_http_timeout_exceeds_telegram_timeout(monkeypatch):
    """The HTTP read timeout must outlast the long poll it is waiting on.

    Telegram holds the getUpdates connection for the full `timeout` window when
    no update is pending. A client timeout below it aborts every idle poll and
    reports normal behaviour as a failure.
    """
    seen = {}

    def fake_post(url, timeout, **kwargs):
        seen["http_timeout"] = timeout
        seen["poll_timeout"] = kwargs["json"]["timeout"]
        return _FakeResponse({"ok": True, "result": []})

    monkeypatch.setattr(bot.requests, "post", fake_post)
    bot.get_updates(offset=1)

    assert (
        seen["http_timeout"] > seen["poll_timeout"]
    ), "HTTP timeout must exceed the long-poll window"


def test_rate_limit_429_is_retried_once_after_retry_after(monkeypatch):
    calls = []
    slept = []

    def fake_post(url, timeout, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return _FakeResponse(
                {"ok": False, "error_code": 429, "parameters": {"retry_after": 3}}
            )
        return _FakeResponse({"ok": True, "result": "sent"})

    monkeypatch.setattr(bot.requests, "post", fake_post)
    monkeypatch.setattr(bot.time, "sleep", lambda s: slept.append(s))

    out = bot.send_message("1", "hello")

    assert slept == [3.0]
    assert len(calls) == 2
    assert out["ok"] is True


def test_retry_after_is_capped(monkeypatch):
    """A huge retry_after must not park the poll loop."""
    slept = []
    monkeypatch.setattr(
        bot.requests,
        "post",
        lambda url, timeout, **kw: _FakeResponse(
            {"ok": False, "error_code": 429, "parameters": {"retry_after": 9999}}
        ),
    )
    monkeypatch.setattr(bot.time, "sleep", lambda s: slept.append(s))

    bot.send_message("1", "hello")

    assert slept == [float(bot._MAX_RETRY_AFTER_S)]


def test_429_retries_at_most_once(monkeypatch):
    """A persistent 429 must not recurse indefinitely."""
    calls = []
    monkeypatch.setattr(
        bot.requests,
        "post",
        lambda url, timeout, **kw: calls.append(1)
        or _FakeResponse(
            {"ok": False, "error_code": 429, "parameters": {"retry_after": 1}}
        ),
    )
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)

    bot.send_message("1", "hello")

    assert len(calls) == 2


def test_api_rejection_is_logged_not_swallowed(monkeypatch, caplog):
    """A 400 'can't parse entities' must not vanish silently."""
    monkeypatch.setattr(
        bot.requests,
        "post",
        lambda url, timeout, **kw: _FakeResponse(
            {
                "ok": False,
                "error_code": 400,
                "description": "Bad Request: can't parse entities",
            }
        ),
    )

    with caplog.at_level("ERROR"):
        bot.send_message("1", "<b>unbalanced")

    assert "can't parse entities" in caplog.text


# ── Authorization ─────────────────────────────────────────────────────────────


def test_empty_allowlist_authorizes_nobody(monkeypatch):
    """Fail closed — an unconfigured bot must not answer the whole internet."""
    assert bot.is_authorized("12345") is False
    assert bot.allowed_chat_ids() == set()


def test_qc_chat_id_is_the_default_allowlist(monkeypatch):
    monkeypatch.setenv("QC_CHAT_ID", "999")

    assert bot.is_authorized("999") is True
    assert bot.is_authorized("1000") is False


def test_explicit_allowlist_supports_multiple_chats(monkeypatch):
    monkeypatch.setenv("QC_ALLOWED_CHAT_IDS", "111, 222 ,333")

    assert bot.allowed_chat_ids() == {"111", "222", "333"}
    for chat_id in ("111", "222", "333"):
        assert bot.is_authorized(chat_id) is True
    assert bot.is_authorized("444") is False


def test_allowlist_overrides_qc_chat_id(monkeypatch):
    monkeypatch.setenv("QC_CHAT_ID", "999")
    monkeypatch.setenv("QC_ALLOWED_CHAT_IDS", "111")

    assert bot.is_authorized("111") is True
    assert bot.is_authorized("999") is False


def test_authorization_tolerates_whitespace_and_int(monkeypatch):
    monkeypatch.setenv("QC_ALLOWED_CHAT_IDS", "111")

    assert bot.is_authorized(" 111 ") is True
    assert bot.is_authorized(111) is True


def test_run_refuses_to_start_without_allowlist(monkeypatch):
    monkeypatch.setattr(bot, "QC_BOT_TOKEN", "token")
    monkeypatch.setattr(bot, "QC_CHAT_ID", "999")

    with pytest.raises(RuntimeError, match="QC_ALLOWED_CHAT_IDS"):
        bot.run()


# ── Dispatch ──────────────────────────────────────────────────────────────────


def test_help_lists_every_command(sent):
    bot._handle_command("/help", "1")

    text = sent["messages"][0][1]
    for cmd in bot.COMMANDS:
        assert cmd in text
    assert "Lecture seule" in text


def test_unknown_command_is_reported(sent):
    bot._handle_command("/rm_rf", "1")

    assert "Commande inconnue" in sent["messages"][0][1]


def test_group_chat_handle_suffix_is_stripped(sent, monkeypatch):
    """In groups Telegram sends `/cri@QuantCrypto_bot`."""
    monkeypatch.setitem(
        bot.COMMANDS, "/cri", ("CRI", "text", lambda args: "cri-output")
    )
    bot._handle_command("/cri@QuantCrypto_bot", "1")

    assert sent["messages"][0][1] == "cri-output"


def test_arguments_are_forwarded_to_text_handler(sent, monkeypatch):
    captured: list[list[str]] = []
    monkeypatch.setitem(
        bot.COMMANDS,
        "/regret",
        ("Regret", "text", lambda args: captured.append(args) or "ok"),
    )
    bot._handle_command("/regret GOOD_REFUSAL", "1")

    assert captured == [["GOOD_REFUSAL"]]


def test_photo_command_sends_a_photo(sent, monkeypatch):
    monkeypatch.setitem(bot.COMMANDS, "/health", ("Santé", "photo", lambda: b"PNGDATA"))
    bot._handle_command("/health", "1")

    assert sent["photos"][0][1] == b"PNGDATA"
    assert sent["messages"] == []


def test_handler_exception_is_reported_not_raised(sent, monkeypatch):
    def boom(args):
        raise ValueError("dataset gone")

    monkeypatch.setitem(bot.COMMANDS, "/cri", ("CRI", "text", boom))
    bot._handle_command("/cri", "1")

    assert "Erreur" in sent["messages"][0][1]
    assert "dataset gone" in sent["messages"][0][1]


def test_empty_message_is_ignored(sent):
    bot._handle_command("   ", "1")

    assert sent["messages"] == []
    assert sent["photos"] == []


# ── Argument parsing ──────────────────────────────────────────────────────────


def test_first_int_clamps_and_defaults():
    assert bot._first_int([], default=12, maximum=25) == 12
    assert bot._first_int(["7"], default=12, maximum=25) == 7
    assert bot._first_int(["999"], default=12, maximum=25) == 25
    assert bot._first_int(["0"], default=12, maximum=25) == 1
    assert bot._first_int(["abc", "5"], default=12, maximum=25) == 5


def test_logs_command_rejects_unknown_argument(sent):
    out = bot._text_logs(["/etc/passwd"])

    assert "Argument inconnu" in out
    # The rejection must not echo an openable path back as markup.
    assert "<code>/etc/passwd</code>" in out


def test_logs_command_accepts_arguments_in_any_order(monkeypatch):
    from visualization.api import logs_api

    captured = {}

    def fake_load(log_key, n_lines, level_filter):
        captured.update(log_key=log_key, n_lines=n_lines, level_filter=level_filter)
        return logs_api.LogTailSnapshot(
            ts=None,
            source_path="logs/advisor_loop.log",
            exists=True,
            n_returned=0,
            n_scanned=0,
            level_filter=level_filter,
        )

    monkeypatch.setattr("visualization.api.load_log_tail", fake_load)
    bot._text_logs(["error", "15", "watchdog"])

    assert captured == {
        "log_key": "watchdog",
        "n_lines": 15,
        "level_filter": "ERROR",
    }


# ── Passivity (ADR-0007) ──────────────────────────────────────────────────────


def test_every_command_is_read_only():
    """No command may point at a mutating call.

    The observer is constitutionally passive: it observes, records and explains,
    but never influences a decision. A command whose handler reaches a writer
    would break that, so the surface is pinned here.
    """
    forbidden = (
        "write",
        "save",
        "restart",
        "kill",
        "calibrat",
        "apply",
        "execute_",
        "place_order",
        "set_",
        "update_",
        "delete",
    )

    for cmd, (_desc, kind, handler) in bot.COMMANDS.items():
        assert kind in ("text", "photo"), cmd
        name = handler.__name__.lower()
        assert not any(
            token in name for token in forbidden
        ), f"{cmd} → {handler.__name__} looks like a mutating handler"


def test_text_commands_do_not_import_matplotlib():
    """A text command must stay cheap.

    `visualization.renderers.base` calls matplotlib.use("Agg") at module scope,
    so a stray top-level import there would make every `/cri` pay a chart
    backend — and fail outright on a host without matplotlib installed.
    """
    import subprocess

    probe = (
        "import sys;"
        "from src.telegram.quant_observer import bot;"
        "bot._text_cri([]);"
        "bot._text_logs(['error']);"
        "print('matplotlib' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[2]),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False", "a text command pulled in matplotlib"


def test_command_kinds_are_consistent():
    for cmd, entry in bot.COMMANDS.items():
        assert cmd.startswith("/")
        assert len(entry) == 3, f"{cmd} must be (desc, kind, handler)"
        desc, kind, handler = entry
        assert desc and callable(handler)
