"""Q2 — @QuantCrypto_bot Telegram delivery ACK (TG-QC-001).

Proves the Telegram engine knows, by itself, whether its last delivery really
succeeded — `{}` is never treated as success. Covers the 10 mandatory checks:

  1. network exception      → failure, no ACK
  2. HTTP 500               → failure, no ACK
  3. HTTP 200 + invalid JSON→ failure
  4. HTTP 200 + ok=false    → failure
  5. HTTP 200 + ok=true     → ACK
  6. editMessageText failure→ last_pinned_update does NOT advance
  7. editMessageText ACK    → last_pinned_update advances
  8. getUpdates            → Telegram long-poll=20, HTTP timeout=25
  9. token absent from logs / safe errors
 10. "message is not modified" → NO_CHANGE (explicit, documented)

Q2.1 additionally proves that non-2xx HTTP can never ACK, NO_CHANGE is limited
to the exact editMessageText HTTP/TG 400 response, and delivery state separates
a fresh ACK from proof that the intended content was already current.

Transport is fully mocked — no real network, no wall-clock dependency.
"""
from __future__ import annotations

import logging

import requests

from src.telegram.quant_observer import bot
from src.telegram.quant_observer.bot import DeliveryKind, DeliveryState, TransportResult


# ── Fake HTTP layer ────────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, status_code, json_data=None, raise_json=False):
        self.status_code = status_code
        self._json = json_data
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("No JSON object could be decoded")
        return self._json


def _patch_post(monkeypatch, response=None, raiser=None, capture=None):
    def fake_post(url, **kwargs):
        if capture is not None:
            capture["url"] = url
            capture.update(kwargs)
        if raiser is not None:
            raise raiser
        return response
    monkeypatch.setattr(bot.requests, "post", fake_post)


# ── 1. network exception ───────────────────────────────────────────────────────

def test_network_exception_is_failure_no_ack(monkeypatch):
    _patch_post(monkeypatch, raiser=requests.exceptions.ConnectionError("down"))
    res = bot._post("sendMessage", json={})
    assert res.kind is DeliveryKind.NETWORK_ERROR
    assert res.is_failure
    assert not res.is_ack
    assert not res.is_delivered


# ── 2. HTTP 500 ────────────────────────────────────────────────────────────────

def test_http_500_is_failure(monkeypatch):
    _patch_post(monkeypatch, FakeResponse(500, raise_json=True))
    res = bot._post("editMessageText", json={})
    assert res.kind is DeliveryKind.HTTP_ERROR
    assert res.http_status == 500
    assert res.is_failure and not res.is_ack


def test_http_500_ok_true_can_never_ack(monkeypatch):
    """A contradictory Telegram envelope cannot override failed HTTP transport."""
    _patch_post(monkeypatch, FakeResponse(500, {"ok": True, "result": {}}))
    res = bot._post("editMessageText", json={})
    assert res.kind is DeliveryKind.HTTP_ERROR
    assert res.http_status == 500
    assert not res.is_ack
    assert not res.is_delivered
    assert res.is_failure


# ── 3. HTTP 200 + invalid JSON ─────────────────────────────────────────────────

def test_http_200_invalid_json_is_failure(monkeypatch):
    _patch_post(monkeypatch, FakeResponse(200, raise_json=True))
    res = bot._post("editMessageText", json={})
    assert res.kind is DeliveryKind.INVALID_RESPONSE
    assert res.is_failure and not res.is_ack


def test_empty_dict_is_never_success(monkeypatch):
    """A bare {} body (HTTP 200, no 'ok') must never be read as ACK."""
    _patch_post(monkeypatch, FakeResponse(200, {}))
    res = bot._post("editMessageText", json={})
    assert res.kind is DeliveryKind.INVALID_RESPONSE
    assert not res.is_ack and res.is_failure


# ── 4. HTTP 200 + ok=false ─────────────────────────────────────────────────────

def test_http_200_ok_false_is_failure(monkeypatch):
    _patch_post(
        monkeypatch,
        FakeResponse(200, {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}),
    )
    res = bot._post("sendMessage", json={})
    assert res.kind is DeliveryKind.TELEGRAM_ERROR
    assert res.error_code == 400
    assert res.is_failure and not res.is_ack and not res.is_delivered
    assert "chat not found" in (res.description_safe or "")


# ── 5. HTTP 200 + ok=true ──────────────────────────────────────────────────────

def test_http_200_ok_true_is_ack(monkeypatch):
    _patch_post(monkeypatch, FakeResponse(200, {"ok": True, "result": {"message_id": 42}}))
    res = bot._post("editMessageText", json={})
    assert res.kind is DeliveryKind.ACK
    assert res.is_ack and res.is_delivered and not res.is_failure
    assert res.result == {"message_id": 42}


# ── 6 & 7. pinned timer only advances on real delivery ─────────────────────────

def _prep_pinned(monkeypatch, edit_result: TransportResult):
    monkeypatch.setattr(bot, "QC_PINNED_MSG", "123")
    monkeypatch.setattr(bot, "QC_CHAT_ID", "456")
    monkeypatch.setattr(bot, "_build_pinned_text", lambda: "PINNED TEXT")
    monkeypatch.setattr(bot, "edit_message", lambda *a, **k: edit_result)
    monkeypatch.setattr(bot, "_QC_DELIVERY", DeliveryState())


def test_failed_edit_does_not_advance_timer(monkeypatch):
    _prep_pinned(
        monkeypatch,
        TransportResult(kind=DeliveryKind.HTTP_ERROR, method="editMessageText", http_status=500),
    )
    new = bot._pinned_tick(now=1000.0, last_pinned_update=0.0)
    assert new == 0.0  # unchanged — no false ACK
    assert bot._QC_DELIVERY.last_failure_ts == 1000.0
    assert bot._QC_DELIVERY.last_ack_ts is None


def test_ack_edit_advances_timer(monkeypatch):
    _prep_pinned(
        monkeypatch,
        TransportResult(kind=DeliveryKind.ACK, method="editMessageText", http_status=200),
    )
    new = bot._pinned_tick(now=1000.0, last_pinned_update=0.0)
    assert new == 1000.0  # advances only after real ACK
    assert bot._QC_DELIVERY.last_ack_ts == 1000.0
    assert bot._QC_DELIVERY.last_confirmed_current_ts == 1000.0
    assert bot._QC_DELIVERY.last_failure_ts is None


# ── 8. getUpdates timeouts: long-poll 20, HTTP 25 (HTTP > long-poll) ───────────

def test_getupdates_timeouts(monkeypatch):
    cap = {}
    _patch_post(monkeypatch, FakeResponse(200, {"ok": True, "result": []}), capture=cap)
    bot.get_updates(offset=7)
    assert cap["timeout"] == 25            # HTTP request timeout
    assert cap["json"]["timeout"] == 20    # Telegram long-poll window
    assert cap["json"]["timeout"] < cap["timeout"]  # HTTP must exceed long-poll
    assert cap["json"]["offset"] == 7


def test_getupdates_longpoll_below_http_constant():
    assert bot.QC_LONGPOLL_S == 20
    assert bot._GETUPDATES_HTTP_TIMEOUT_S == 25
    assert bot._GETUPDATES_HTTP_TIMEOUT_S > bot.QC_LONGPOLL_S


def test_default_write_timeout_is_short(monkeypatch):
    """The 25s timeout is scoped to getUpdates only; write ops keep the short one."""
    cap = {}
    _patch_post(monkeypatch, FakeResponse(200, {"ok": True, "result": {}}), capture=cap)
    bot.send_message("456", "hi")
    assert cap["timeout"] == bot._HTTP_TIMEOUT_S == 15


def test_getupdates_failure_returns_empty_list(monkeypatch):
    _patch_post(monkeypatch, FakeResponse(500, raise_json=True))
    assert bot.get_updates(offset=1) == []


# ── 9. token never leaks into logs or safe errors ─────────────────────────────

def test_network_error_does_not_leak_token(monkeypatch, caplog):
    token = "SUPER_SECRET_TOKEN_123"
    monkeypatch.setattr(bot, "QC_BOT_TOKEN", token)
    monkeypatch.setattr(bot, "_API_BASE", f"https://api.telegram.org/bot{token}")

    def boom(url, **kwargs):
        # requests exceptions can embed the request URL (which carries the token)
        raise requests.exceptions.ConnectionError(
            f"HTTPSConnectionPool: failed to reach {url}"
        )
    monkeypatch.setattr(bot.requests, "post", boom)

    with caplog.at_level(logging.ERROR):
        res = bot._post("editMessageText", json={})

    assert res.kind is DeliveryKind.NETWORK_ERROR
    assert token not in (res.description_safe or "")
    assert token not in res.summary_safe()
    assert token not in caplog.text


def test_redact_secrets_strips_token(monkeypatch):
    token = "TOK_ABC_999"
    monkeypatch.setattr(bot, "QC_BOT_TOKEN", token)
    monkeypatch.setattr(bot, "_API_BASE", f"https://api.telegram.org/bot{token}")
    leaky = f"could not reach https://api.telegram.org/bot{token}/editMessageText"
    red = bot._redact_secrets(leaky)
    assert token not in red
    assert "***" in red


def test_telegram_error_description_is_redacted(monkeypatch):
    token = "TOK_XYZ"
    monkeypatch.setattr(bot, "QC_BOT_TOKEN", token)
    monkeypatch.setattr(bot, "_API_BASE", f"https://api.telegram.org/bot{token}")
    _patch_post(
        monkeypatch,
        FakeResponse(200, {"ok": False, "error_code": 400, "description": f"bad {token} echoed"}),
    )
    res = bot._post("sendMessage", json={})
    assert res.kind is DeliveryKind.TELEGRAM_ERROR
    assert token not in (res.description_safe or "")


# ── 10. "message is not modified" → NO_CHANGE (documented semantics) ───────────

def test_message_not_modified_is_no_change(monkeypatch):
    """Telegram replies HTTP 400 {ok:false, "message is not modified"} when the
    pinned message already carries the exact content. Semantics (Q2.4):
    classified as NO_CHANGE (ALREADY_CURRENT) — the LIVE is up to date, so it is
    'delivered', but it is NOT a fresh edit ACK and NOT a failure."""
    _patch_post(
        monkeypatch,
        FakeResponse(400, {
            "ok": False,
            "error_code": 400,
            "description": "Bad Request: message is not modified",
        }),
    )
    res = bot._post("editMessageText", json={})
    assert res.kind is DeliveryKind.NO_CHANGE
    assert res.is_delivered      # content already current
    assert not res.is_ack        # but not a new edit ACK
    assert not res.is_failure    # and not a delivery failure


def test_message_not_modified_is_not_no_change_for_non_edit_methods(monkeypatch):
    for method in ("sendMessage", "sendPhoto"):
        _patch_post(
            monkeypatch,
            FakeResponse(400, {
                "ok": False,
                "error_code": 400,
                "description": "Bad Request: message is not modified",
            }),
        )
        res = bot._post(method, json={})
        assert res.kind is DeliveryKind.TELEGRAM_ERROR
        assert not res.is_ack and not res.is_delivered and res.is_failure


def test_message_not_modified_requires_telegram_error_400(monkeypatch):
    _patch_post(
        monkeypatch,
        FakeResponse(400, {
            "ok": False,
            "error_code": 409,
            "description": "Bad Request: message is not modified",
        }),
    )
    res = bot._post("editMessageText", json={})
    assert res.kind is DeliveryKind.TELEGRAM_ERROR
    assert not res.is_ack and not res.is_delivered and res.is_failure


def test_message_not_modified_requires_http_400(monkeypatch):
    _patch_post(
        monkeypatch,
        FakeResponse(200, {
            "ok": False,
            "error_code": 400,
            "description": "Bad Request: message is not modified",
        }),
    )
    res = bot._post("editMessageText", json={})
    assert res.kind is DeliveryKind.TELEGRAM_ERROR
    assert not res.is_ack and not res.is_delivered and res.is_failure


def test_no_change_advances_timer_but_is_not_ack(monkeypatch):
    _prep_pinned(
        monkeypatch,
        TransportResult(
            kind=DeliveryKind.NO_CHANGE,
            method="editMessageText",
            http_status=400,
            error_code=400,
            description_safe="Bad Request: message is not modified",
        ),
    )
    bot._QC_DELIVERY.last_ack_ts = 1500.0
    new = bot._pinned_tick(now=2000.0, last_pinned_update=0.0)
    assert new == 2000.0  # already-current ⇒ LIVE is up to date, retry not needed
    assert bot._QC_DELIVERY.last_ack_ts == 1500.0  # no fresh Telegram ACK
    assert bot._QC_DELIVERY.last_confirmed_current_ts == 2000.0
    assert bot._QC_DELIVERY.last_failure_ts is None


# ── Delivery state (Q2.5) ──────────────────────────────────────────────────────

def test_delivery_state_records_ack_then_failure():
    st = DeliveryState()
    assert st.last_attempt_ts is None

    st.record(TransportResult(kind=DeliveryKind.ACK, method="editMessageText"), now=100.0)
    assert st.last_attempt_ts == 100.0
    assert st.last_ack_ts == 100.0
    assert st.last_confirmed_current_ts == 100.0
    assert st.last_failure_ts is None

    st.record(
        TransportResult(
            kind=DeliveryKind.HTTP_ERROR, method="editMessageText",
            http_status=500, description_safe=None,
        ),
        now=200.0,
    )
    assert st.last_attempt_ts == 200.0
    assert st.last_ack_ts == 100.0            # last good ACK preserved
    assert st.last_confirmed_current_ts == 100.0  # last current-content proof preserved
    assert st.last_failure_ts == 200.0
    assert st.last_failure_kind == "HTTP_ERROR"


def test_delivery_state_no_change_confirms_current_without_new_ack():
    st = DeliveryState(last_ack_ts=50.0, last_confirmed_current_ts=50.0)
    st.record(
        TransportResult(kind=DeliveryKind.NO_CHANGE, method="editMessageText"),
        now=100.0,
    )
    assert st.last_attempt_ts == 100.0
    assert st.last_ack_ts == 50.0
    assert st.last_confirmed_current_ts == 100.0
    assert st.last_failure_ts is None


def test_delivery_state_failure_does_not_confirm_current():
    st = DeliveryState(last_ack_ts=50.0, last_confirmed_current_ts=60.0)
    st.record(
        TransportResult(
            kind=DeliveryKind.NETWORK_ERROR,
            method="editMessageText",
            description_safe="Timeout",
        ),
        now=100.0,
    )
    assert st.last_attempt_ts == 100.0
    assert st.last_ack_ts == 50.0
    assert st.last_confirmed_current_ts == 60.0
    assert st.last_failure_ts == 100.0


def test_delivery_state_has_all_required_fields():
    st = DeliveryState()
    for field in (
        "last_attempt_ts",
        "last_ack_ts",
        "last_confirmed_current_ts",
        "last_failure_ts",
        "last_failure_kind",
        "last_failure_description_safe",
    ):
        assert hasattr(st, field)


# ── Guard: no database writes / no engine coupling in the delivery layer ───────

def test_bot_delivery_layer_writes_no_database():
    """Q2 is transport observability only: the bot must not write a DB, persist
    a runtime file, or import the decision engine (checks target real code, not
    doc prose)."""
    from pathlib import Path
    src = Path("src/telegram/quant_observer/bot.py").read_text(encoding="utf-8")
    for banned in (
        "databases/",
        "sqlite",
        "import advisor_loop",
        "from core.advisor_loop",
        "risk_manager",
        ".write_text(",
    ):
        assert banned not in src, f"delivery layer must not reference {banned!r}"
