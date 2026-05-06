from __future__ import annotations

from unittest.mock import Mock

import httpx
import pytest

from lm_studio import ai_router, client


class DummyResponse:
    def __init__(self, status_code=200, payload=None, text="OK"):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://lm.local")
            response = httpx.Response(self.status_code, text=self.text, request=request)
            raise httpx.HTTPStatusError("boom", request=request, response=response)


def test_headers_uses_default_api_key(monkeypatch):
    monkeypatch.delenv("LM_STUDIO_API_KEY", raising=False)

    assert client._headers()["Authorization"] == "Bearer lm-studio"


def test_is_available_true_on_models_endpoint(monkeypatch):
    monkeypatch.setattr(client.httpx, "get", lambda *a, **k: DummyResponse(200))

    assert client.is_available() is True


def test_is_available_false_on_connection_error(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(client.httpx, "get", fail)

    assert client.is_available() is False


def test_list_models_returns_model_ids(monkeypatch):
    monkeypatch.setattr(
        client.httpx,
        "get",
        lambda *a, **k: DummyResponse(
            payload={"data": [{"id": "mistral"}, {"id": "qwen"}]}
        ),
    )

    assert client.list_models() == ["mistral", "qwen"]


def test_list_loaded_models_uses_models_endpoint(monkeypatch):
    monkeypatch.setattr(client, "_active_model", None)
    monkeypatch.setattr(
        client.httpx,
        "get",
        lambda *a, **k: DummyResponse(
            payload={
                "data": [
                    {"id": "qwen-local", "state": "loaded", "type": "llm"},
                    {"id": "embed-local", "state": "loaded", "type": "embeddings"},
                    {"id": "phi-local", "state": "not-loaded", "type": "llm"},
                ]
            }
        ),
    )
    monkeypatch.setattr(
        client.httpx,
        "post",
        lambda *a, **k: pytest.fail("list_loaded_models should not probe chat endpoint"),
    )

    assert client.list_loaded_models() == ["qwen-local"]


def test_chat_posts_openai_compatible_payload(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return DummyResponse(
            payload={"choices": [{"message": {"content": "bonjour"}}]}
        )

    monkeypatch.setattr(client.httpx, "post", fake_post)

    assert client.chat("Analyse BTC", model="local-test") == "bonjour"
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["json"]["model"] == "local-test"
    assert captured["json"]["messages"][1]["content"] == "Analyse BTC"
    assert captured["json"]["stream"] is False


def test_chat_auto_detects_model_from_models_endpoint(monkeypatch):
    captured = {}
    monkeypatch.setattr(client, "_active_model", None)
    monkeypatch.setattr(
        client.httpx,
        "get",
        lambda *a, **k: DummyResponse(
            payload={"data": [{"id": "auto-detected", "state": "loaded", "type": "llm"}]}
        ),
    )

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return DummyResponse(payload={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(client.httpx, "post", fake_post)

    assert client.chat("Analyse BTC") == "ok"
    assert captured["json"]["model"] == "auto-detected"


def test_chat_wraps_http_status_errors(monkeypatch):
    monkeypatch.setattr(client, "_active_model", None)
    monkeypatch.setattr(
        client.httpx,
        "get",
        lambda *a, **k: DummyResponse(
            payload={"data": [{"id": "local-test", "state": "loaded", "type": "llm"}]}
        ),
    )
    monkeypatch.setattr(
        client.httpx,
        "post",
        lambda *a, **k: DummyResponse(status_code=500, text="server down"),
    )

    with pytest.raises(RuntimeError, match="erreur HTTP 500"):
        client.chat("hello")


def test_chat_falls_back_to_next_model_when_first_one_is_rejected(monkeypatch):
    attempted_models = []
    monkeypatch.setattr(client, "_active_model", None)
    monkeypatch.setattr(
        client.httpx,
        "get",
        lambda *a, **k: DummyResponse(
            payload={
                "data": [
                    {"id": "too-large-model", "state": "loaded", "type": "llm"},
                    {"id": "small-model", "state": "loaded", "type": "llm"},
                    {"id": "text-embedding-local", "state": "loaded", "type": "embeddings"},
                ]
            }
        ),
    )

    def fake_post(url, **kwargs):
        attempted_models.append(kwargs["json"].get("model"))
        if kwargs["json"].get("model") == "too-large-model":
            return DummyResponse(status_code=400, text="model failed to load")
        return DummyResponse(payload={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(client.httpx, "post", fake_post)

    assert client.chat("Analyse BTC") == "ok"
    assert attempted_models == ["too-large-model", "small-model"]
    assert client._active_model == "small-model"


def test_chat_raises_fast_when_no_model_is_loaded(monkeypatch):
    monkeypatch.setattr(client, "_active_model", None)
    monkeypatch.setattr(
        client.httpx,
        "get",
        lambda *a, **k: DummyResponse(
            payload={"data": [{"id": "phi-local", "state": "not-loaded", "type": "llm"}]}
        ),
    )
    monkeypatch.setattr(
        client.httpx,
        "post",
        lambda *a, **k: pytest.fail("chat should not call LM Studio without a loaded model"),
    )

    with pytest.raises(RuntimeError, match="aucun modele LLM charge"):
        client.chat("Analyse BTC")


def test_complete_returns_legacy_completion_text(monkeypatch):
    monkeypatch.setattr(
        client.httpx,
        "post",
        lambda *a, **k: DummyResponse(payload={"choices": [{"text": "done"}]}),
    )

    assert client.complete("hello") == "done"


def test_router_auto_uses_lm_studio_when_available(monkeypatch):
    monkeypatch.setattr(ai_router.client, "is_available", lambda: True)
    chat = Mock(return_value="local")
    monkeypatch.setattr(ai_router.client, "chat", chat)

    result = ai_router.AIRouter(fallback=lambda prompt: "fallback").ask("ping")

    assert result == "local"
    chat.assert_called_once()


def test_router_auto_falls_back_when_lm_studio_is_offline(monkeypatch):
    monkeypatch.setattr(ai_router.client, "is_available", lambda: False)

    result = ai_router.AIRouter(fallback=lambda prompt: f"fallback:{prompt}").ask(
        "ping"
    )

    assert result == "fallback:ping"


def test_router_without_fallback_raises_when_offline(monkeypatch):
    monkeypatch.setattr(ai_router.client, "is_available", lambda: False)

    with pytest.raises(RuntimeError, match="Aucun fallback"):
        ai_router.AIRouter().ask("ping")
